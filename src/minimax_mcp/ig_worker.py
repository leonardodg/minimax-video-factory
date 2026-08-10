"""Background daemon consumer for the Instagram saved-posts queue.

Consumes ig.saved one message at a time (prefetch=1, IG_WORKER_CONCURRENCY=1
by default — Whisper/vision share the VRAM with the H3 renderer), downloads the
media with yt-dlp, transcribes (video) or describes (image) it, ingests it into
the knowledge base, optionally deletes the downloaded file, and acks. Failures
go through ig_queue.handle_failure (attempts -> DLQ).

The per-item logic (process_message/classify_file/apply_command) is pure and
injected with download/transcribe/describe/ingest callables so it can be unit
tested without RabbitMQ, GPU or network.
"""
from __future__ import annotations

import logging
import os
import re
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from minimax_mcp import db, ig_queue, knowledge, llm

logger = logging.getLogger(__name__)

_CTA_PATTERNS = (
    r"segue(?:-me| me)?(?: aqui)? (?:para|pra)(?: não| nao)? perder",
    r"j[aá] me segue",
    r"siga para mais",
    r"salva(?: esse| este| o) vídeo",
    r"salv(e|a) para fazer depois",
    r"compartilh(a|e) com (?:seus|teus|os) amigos",
    r"link na bio",
    r"curte e compartilha",
    r"ativa o sininho",
    r"coment(?:a|e)[^.!?]*que eu te mando",
)
_CTA_SENTENCE_RE = re.compile(
    r"[^.!?]*(?:" + "|".join(_CTA_PATTERNS) + r")[^.!?]*[.!?]",
    re.IGNORECASE | re.DOTALL,
)


def strip_cta(text: str) -> str:
    """Remove sentences containing Instagram call-to-action phrases.

    A sentence is delimited by `.`, `!` or `?`. Only the sentence that contains
    the CTA is removed; surrounding content is preserved. Never raises and
    returns input unchanged when no CTA pattern matches.
    """
    if not text:
        return text
    return _CTA_SENTENCE_RE.sub("", text).strip()


# O mesmo vocabulário, mas casando até o fim da string em vez de exigir `.!?`.
# Título de legenda frequentemente não tem pontuação nenhuma -- "Siga para mais
# 👉 @fulano" atravessava o strip_cta intacto porque a sentença nunca terminava.
_CTA_TAIL_RE = re.compile(
    r"[^.!?]*(?:" + "|".join(_CTA_PATTERNS) + r")[^.!?]*$",
    re.IGNORECASE | re.DOTALL,
)
_HASHTAG_RE = re.compile(r"#\S+")
_WORD_RE = re.compile(r"\w{2,}", re.UNICODE)


def clean_title(raw: str | None) -> str | None:
    """Limpa o título vindo da legenda do Instagram, ou devolve None.

    O `strip_cta` sozinho não serve aqui, e os doze documentos reais mostraram
    os dois motivos:

      "Siga para mais 👉 @fulano"          passava intacto -- sem `.!?`, a
                                            expressão de sentença nunca casa
      "Comenta 'PROCESSO' ... no privado!"  virava "#code #c" -- o CTA saía e
                                            sobrava a salada de hashtag

    Então: remove CTA com e sem pontuação final, tira hashtags (que não são
    título de coisa nenhuma) e limpa a pontuação órfã. Se o que sobrar tiver
    menos de duas palavras, não é título -- devolve None, e o `ingest` cai no
    fallback que já existe (`title or resumo[:80]`), deixando a primeira linha
    do resumo assumir.
    """
    if not raw:
        return None
    t = _CTA_TAIL_RE.sub("", strip_cta(raw))
    t = _HASHTAG_RE.sub("", t)
    # Corta só espaço e separador órfão. Ponto final e exclamação FICAM: tirá-los
    # mudaria títulos perfeitamente bons ("Uma receita simples." -> "Uma receita
    # simples") e encheria a comparação de diferenças que não são limpeza de CTA.
    t = re.sub(r"\s+", " ", t).strip(" -–—|·•,;:")
    return t if len(_WORD_RE.findall(t)) >= 2 else None

IG_DOWNLOADS_DIR = Path(os.environ.get("IG_DOWNLOADS_DIR", "downloads/ig"))
IG_DELETE_AFTER_INGEST = os.environ.get("IG_DELETE_AFTER_INGEST", "true").lower() in (
    "1", "true", "yes",
)
WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "small")

# Ritmo mínimo entre mensagens, em segundos. 0 = comportamento antigo, consumir o
# mais rápido que a máquina aguentar.
#
# Existe porque o limite deste pipeline é o Instagram, não a GPU: duas varreduras
# completas numa hora já geraram 429 e derrubaram coleções inteiras da listagem.
# O worker processa uma mensagem por vez (prefetch=1) mas não esperava nada entre
# elas -- a 39 s por post, ~92 posts/hora contínuos.
#
# E tem de ser AQUI DENTRO, não ligando e desligando o processo: o vocabulário de
# categorias é buscado uma vez por processo (`_categories_cache`), então cada
# reinício custa uma listagem das 46 coleções -- exatamente a operação que atrai
# punição. Um daemon longo com pausa interna faz UMA listagem para a corrida toda.
IG_WORKER_MIN_INTERVAL = float(os.environ.get("IG_WORKER_MIN_INTERVAL", "0") or 0)
WHISPER_DEVICE = os.environ.get("WHISPER_DEVICE", "cuda")

VIDEO_EXTS = {".mp4", ".mkv", ".webm", ".mov"}


def classify_file(filepath: str) -> str:
    return "video" if Path(filepath).suffix.lower() in VIDEO_EXTS else "image"


def pace_sleep_seconds(elapsed: float, interval: float = IG_WORKER_MIN_INTERVAL) -> float:
    """Quanto ainda falta dormir para a mensagem ter levado `interval` no total.

    Conta do INÍCIO da mensagem, não do fim. Dormir `interval` depois de
    processar daria um espaçamento real de `processamento + interval`, que varia
    com o tamanho do vídeo -- 39 s num post curto, minutos num longo -- e o ritmo
    deixaria de ser previsível justamente onde a previsibilidade importa.

    Descontando o tempo já gasto, um post que levou mais que `interval` segue
    direto (devolve 0.0) e o ritmo fica limitado pelo processamento, que é o
    comportamento certo: a pausa é um TETO de velocidade, não um imposto fixo.

    Pura de propósito -- dá para testar o ritmo sem fila, sem rede e sem GPU.
    """
    if interval <= 0:
        return 0.0
    return max(0.0, interval - max(0.0, elapsed))


def process_message(
    message: dict,
    *,
    download: Callable[[dict], dict],
    transcribe: Callable[[str], dict] | None,
    describe: Callable[[str], dict] | None,
    ingest: Callable[[str], dict],
    categories: list[str] | None = None,
) -> dict:
    """Download -> transcribe/describe -> ingest. Pure; all IO injected.

    Videos transcribe the first downloaded file. Images/carousels describe
    EVERY downloaded file and join their conteudo_principal into one text so
    content spread across carousel photos is captured. The first photo's
    categoria becomes a `categoria:<name>` tag.
    """
    if not message:
        return {"status": "error", "error": "empty message"}

    dl = download(message)
    if not dl.get("ok"):
        return {"status": "error", "error": dl.get("error", "download failed")}
    filepaths = dl.get("filepaths") or [dl.get("filepath")]
    filepaths = [f for f in filepaths if f]
    if not filepaths:
        return {"status": "error", "error": "no file downloaded"}

    kind = classify_file(filepaths[0])
    categoria = None
    if kind == "video":
        if transcribe is None:
            return {"status": "error", "error": "no transcribe provided for video", "filepaths": filepaths}
        tr = transcribe(filepaths[0])
        if not tr.get("ok"):
            return {"status": "error", "error": tr.get("error", "transcribe failed"), "filepaths": filepaths}
        text, lang = tr["text"], tr.get("language", "pt")
        doc_type = "video"
    else:
        if describe is None:
            return {"status": "error", "error": "no describe provided for image", "filepaths": filepaths}
        pieces: list[str] = []
        for fp in filepaths:
            de = describe(fp)
            if not de.get("ok"):
                return {"status": "error", "error": de.get("error", "describe failed"), "filepaths": filepaths}
            pieces.append(de.get("conteudo_principal") or de.get("text") or "")
            if categoria is None:
                categoria = de.get("categoria")
        text = "\n\n".join(p for p in pieces if p)
        lang = "pt"
        doc_type = "image"

    # Namespaced like `categoria:`: a bare collection name is indistinguishable
    # from a semantic tag the LLM produced, and it was landing on nearly every
    # document, so tag search could not tell "about Dev" from "filed under Dev".
    extra_tags = [f"colecao:{message['collection_name']}"] if message.get("collection_name") else None
    # "outros" is the vision model saying none matched -- an absence, not a
    # classification. It must not be tagged, and it must not count as "already
    # classified" further down either.
    classified = bool(categoria) and categoria != "outros"
    if classified:
        extra_tags = (extra_tags or []) + [f"categoria:{categoria}"]
    text = strip_cta(text)
    # O título também. Ele vem da primeira linha da legenda do Instagram, e é o
    # campo MAIS visível -- aparece na listagem e vira o nome do arquivo
    # exportado. Limpar só a transcrição deixava passar exatamente a superfície
    # que mais incomoda: "Comenta 'PROCESSO' que eu te mando o passo a passo",
    # "Siga para mais @fulano" e "Estude comigo na Fluency. Link na Bio." eram
    # três dos doze títulos ingeridos.
    #
    # `clean_title` e não `strip_cta`: o título não é prosa, e os dois casos que
    # o strip_cta sozinho errava estão documentados lá.
    title = clean_title(message.get("title"))
    ing = ingest(
        text,
        source_url=message.get("url"),
        title=title,
        platform="instagram",
        doc_type=doc_type,
        language=lang,
        ig_pk=message.get("ig_pk"),
        extra_tags=extra_tags,
        # Only when vision did not already classify it. Vision looks at the
        # picture; the summary model only ever sees words, so it is the weaker
        # judge -- but for a video it is the only one there is, and videos are
        # the bulk of what gets saved.
        categories=None if classified else categories,
    )
    if not ing.get("ok"):
        return {"status": "error", "error": ing.get("error", "ingest failed"), "filepaths": filepaths}

    return {
        "status": "done",
        "document_id": ing.get("document_id"),
        "kind": kind,
        "filepath": filepaths[0],
        "filepaths": filepaths,
    }


def apply_command(state: dict, command: str) -> str:
    """Handle a start/stop control message, mutating `state`."""
    if command == "start":
        state["paused"] = False
        return "resumed"
    if command == "stop":
        state["paused"] = True
        return "paused"
    return "unknown"


def _download_targets(client: Any, pk: str) -> list[tuple[str, str]]:
    """All (method, argument) download pairs for a post.

    Carousels (media_type 8) have no clip of their own — the pk is an album
    container and clip_download raises "Must been video" — so one pair comes back
    per resource and the whole album is captured. Single media returns the pk.

    **Os recursos de carrossel são baixados por URL, não por pk, e isso não é
    detalhe de estilo.** Um recurso de álbum não existe como mídia autônoma na
    API privada: `clip_download(resource_pk)` faz o instagrapi chamar
    `media_info(resource_pk)` por dentro, não achar, e cair no GraphQL
    **público** — que é anônimo, leva 401 e devolve a página de login. Medido em
    2026-08-10: três chamadas privadas 200 seguidas e, no primeiro carrossel, um
    laço de requisições públicas a cada 5 s. Vídeo simples passava; carrossel
    nunca.

    O `media_info` do álbum, buscado aqui pela via autenticada, já traz
    `video_url` e `thumbnail_url` de cada recurso — URLs **assinadas** do CDN.
    `*_download_by_url` faz um `requests.get` simples nelas.

    Note o que muda de verdade: o download nunca foi o problema, e essas funções
    nem carregam a sessão. O que some é a **re-resolução** do recurso — nenhum
    `media_info(resource_pk)`, logo nenhuma queda para o GraphQL público, logo
    nenhum 401. A autenticação continua acontecendo uma vez só, na consulta do
    álbum, que é onde ela sempre funcionou.
    """
    info = client.media_info(pk)
    mtype = int(getattr(info, "media_type", 0) or 0)
    if mtype == 8:
        resources = list(getattr(info, "resources", None) or [])
        if not resources:
            return [("photo_download", pk)]
        pairs: list[tuple[str, str]] = []
        for r in resources:
            rm = int(getattr(r, "media_type", 0) or 0)
            url = getattr(r, "video_url", None) if rm == 2 else getattr(r, "thumbnail_url", None)
            if url:
                pairs.append((
                    "video_download_by_url" if rm == 2 else "photo_download_by_url",
                    str(url),
                ))
                continue
            # Sem URL no recurso, resta o caminho antigo. Ele pode cair na API
            # pública, mas é melhor que descartar o recurso em silêncio -- e a
            # falha fica visível no log em vez de virar um álbum incompleto.
            logger.warning(
                "carousel %s: resource %s has no url, falling back to pk download",
                pk, getattr(r, "pk", "?"),
            )
            pairs.append(("clip_download" if rm == 2 else "photo_download", str(r.pk)))
        return pairs
    if mtype == 1:
        return [("photo_download", pk)]
    return [("clip_download", pk)]


def _default_download(message: dict) -> dict:
    """Download the media for a saved post.

    Prefers the authenticated instagrapi client (the worker already has
    IG_SESSIONID, and saved/private posts are unreachable by anonymous yt-dlp),
    falling back to yt-dlp (public posts, or when IG_SESSIONID is unset).
    Carousels download every resource; the result exposes both `filepath`
    (first item) and `filepaths` (all items) for back-compat.

    Os pares vindos de `_download_targets` são `(método, argumento)`, e o
    argumento é um **pk ou uma URL** conforme o método — os três aceitam o
    primeiro posicional mais `folder=`, então a chamada aqui serve para ambos.
    """
    url = message.get("url", "")
    pk = message.get("ig_pk", "")
    if pk:
        try:
            IG_DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
            from minimax_mcp import ig_sync

            client = ig_sync.make_client()
            client.delay_range = [0.5, 1.0]
            filepaths: list[str] = []
            for method, target in _download_targets(client, pk):
                out = getattr(client, method)(target, folder=str(IG_DOWNLOADS_DIR))
                if out and Path(out).exists():
                    filepaths.append(str(Path(out)))
            if filepaths:
                return {"ok": True, "filepath": filepaths[0], "filepaths": filepaths}
        except Exception as e:
            logger.warning("instagrapi download failed for %s: %s", pk, e)

    from minimax_mcp.downloader import VideoDownloader

    IG_DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
    downloader = VideoDownloader(output_dir=IG_DOWNLOADS_DIR, browser="chrome")
    dl = downloader.download(url)
    if dl.get("ok") and dl.get("filepath"):
        dl["filepaths"] = [dl["filepath"]]
    return dl


_categories_cache: list[str] | None = None


def _discard_media(res: dict) -> None:
    """Apaga a mídia baixada, tenha a ingestão dado certo ou não.

    O download é rascunho: o que fica é o documento na base. Chamar isto no
    caminho de erro é o que impede um sync completo de encher o disco, já que
    a mídia de um post que falhou não tem nenhum uso posterior -- se ele for
    retentado, baixa de novo.
    """
    if not IG_DELETE_AFTER_INGEST:
        return
    for fp in (res.get("filepaths") or [res.get("filepath")]):
        if not fp:
            continue
        try:
            Path(fp).unlink(missing_ok=True)
        except OSError as exc:
            logger.warning("could not delete %s: %s", fp, exc)


def _category_vocabulary() -> list[str]:
    """The user's collection names, fetched once per process.

    Instagram rate-limits hard (the second full sync of the morning came back
    with 429s), so this must never become per-message. Falls back to the
    built-in vocabulary when the fetch fails.
    """
    global _categories_cache
    if _categories_cache is None:
        from minimax_mcp import ig_sync

        try:
            _categories_cache = ig_sync.list_categories(ig_sync.make_client())
        except Exception as exc:
            logger.warning("could not read collections, using defaults: %s", exc)
            _categories_cache = ig_sync.list_categories(None)
    return _categories_cache


def _default_describe(filepath: str) -> dict:
    """Describe an image with the category vocabulary threaded in."""
    return llm.describe_image(filepath, categories=_category_vocabulary())


def _default_transcribe(filepath: str) -> dict:
    from minimax_mcp.transcriber import AudioTranscriber

    transcriber = AudioTranscriber(model_size=WHISPER_MODEL, device=WHISPER_DEVICE)
    try:
        return transcriber.transcribe(filepath)
    finally:
        # Release the Whisper VRAM right after transcribing, before the LLM
        # step: lfm2:24b needs ~6 GB and the worker runs on the same 12 GB GPU
        # as ComfyUI. Otherwise the next knowledge call 500s with cudaMalloc
        # out-of-memory until a retry happens to run after the cache cleared.
        #
        # Guarded because this runs in a `finally`: an exception raised here
        # would replace the transcription we just spent minutes producing, and
        # the message would be nacked and redone. Failing to free is worth a
        # warning, never worth discarding the work.
        try:
            transcriber.free()
        except Exception:
            logger.warning("could not release Whisper VRAM", exc_info=True)


def _safe_ack(ch, method) -> None:
    """Ack a delivery, swallowing channel/connection errors (e.g. the broker
    closed the transport while a long LLM/Whisper step was running). If the
    connection died the message is left unacked and RabbitMQ redelivers it once
    the worker reconnects."""
    try:
        ch.basic_ack(method.delivery_tag)
    except Exception as exc:
        logger.warning("ack failed for delivery_tag=%s (%s); will redeliver", method.delivery_tag, exc)


def run() -> None:
    """Daemon main: connect, declare, consume ig.saved + control queue.

    The connection can drop (heartbeat timeout, broker restart) while a long
    Whisper/LLM step is running; the old code crashed the whole daemon with
    StreamLostError on the post-processing ack, orphaning queued messages.
    This loop reconnects with backoff and keeps the item-paused state across
    connections.
    """
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

    state = {"paused": False}

    def _pace(started: float, pk: str | None) -> None:
        """Dorme o que faltar para fechar IG_WORKER_MIN_INTERVAL desde `started`.

        Antes do `ack`, de propósito: com prefetch=1 o broker só entrega a próxima
        depois do ack, então dormir aqui atrasa a busca seguinte no Instagram. Se
        fosse depois, a mensagem nova já estaria em mãos e a pausa não seguraria
        nada.
        """
        pausa = pace_sleep_seconds(time.monotonic() - started)
        if pausa > 0:
            logger.info("pace: aguardando %.1fs antes do próximo (ig_pk=%s)", pausa, pk)
            time.sleep(pausa)

    def on_work(ch, method, properties, body):
        started = time.monotonic()
        parsed = ig_queue.parse_message(body)
        if not parsed["ok"]:
            logger.warning("corrupted message -> DLQ: %s", parsed["error"])
            try:
                ig_queue.dead_letter(ch, properties, body)
            except Exception as exc:
                logger.warning("dead_letter failed: %s", exc)
            _safe_ack(ch, method)
            return

        message = parsed["message"]
        session = db.get_session()
        try:
            already = db.document_exists(session, ig_pk=message.get("ig_pk"))
        finally:
            session.close()
        if already:
            logger.info("duplicate ig_pk=%s -> ack without processing", message["ig_pk"])
            _safe_ack(ch, method)
            return

        res = process_message(
            message,
            download=_default_download,
            transcribe=_default_transcribe,
            describe=_default_describe,
            ingest=knowledge.ingest_text,
            categories=_category_vocabulary(),
        )
        # Unconditional: the media is scratch either way. Deleting only on
        # success meant a failing post left its download behind -- and with the
        # DLQ retrying up to IG_MAX_ATTEMPTS, one bad post downloaded and
        # abandoned its file on every attempt. Over a full sync of 2000+ saved
        # posts that is the difference between a few hundred MB of churn and
        # filling the disk.
        _discard_media(res)

        if res["status"] == "done":
            logger.info("ingested ig_pk=%s document_id=%s", message["ig_pk"], res["document_id"])
            _state = os.environ.get("IG_STATE_FILE", "downloads/ig/state.json")
            try:
                import json as _json
                from pathlib import Path as _P

                _p = _P(_state)
                _existing = _json.loads(_p.read_text(encoding="utf-8")) if _p.exists() else []
                _existing.append({"ig_pk": message["ig_pk"], "status": "done",
                                  "document_id": res["document_id"], "title": message.get("title")})
                _p.parent.mkdir(parents=True, exist_ok=True)
                _p.write_text(_json.dumps(_existing[-500:], ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception as exc:
                # The progress file is a convenience for /ig-progress, not the
                # source of truth -- the document is already in the KB. Failing
                # to write it must not nack a message that actually succeeded.
                logger.warning("could not update the progress file: %s", exc)
            _pace(started, message.get("ig_pk"))
            _safe_ack(ch, method)
        else:
            logger.warning("processing failed ig_pk=%s: %s", message["ig_pk"], res["error"])
            try:
                ig_queue.handle_failure(ch, properties, body)
            except Exception as exc:
                logger.warning("handle_failure failed: %s", exc)
            # A pausa vale para a falha também. Um post que falhou já gastou as
            # requisições dele no Instagram, e uma sequência de falhas rápidas é
            # justamente o padrão que faz a conta ser bloqueada -- foi assim que
            # o instagrapi entrou em laço de 5 s contra a página de login.
            _pace(started, message.get("ig_pk"))
            _safe_ack(ch, method)

    def on_control(ch, method, properties, body):
        import json

        try:
            command = json.loads(body).get("command", "")
        except (ValueError, TypeError):
            command = ""
        logger.info("control command: %s", apply_command(state, command))
        _safe_ack(ch, method)

    def consume_once() -> None:
        """Connect and consume until the connection dies; returns on error."""
        connection = ig_queue.connect()
        try:
            channel = connection.channel()
            ig_queue.declare(channel)
            channel.basic_qos(prefetch_count=1)
            channel.basic_consume(queue=ig_queue.QUEUE, on_message_callback=on_work)
            channel.basic_consume(queue=ig_queue.CONTROL_QUEUE, on_message_callback=on_control)
            logger.info("ig-worker consuming %s (paused=%s)", ig_queue.QUEUE, state["paused"])
            channel.start_consuming()
        except KeyboardInterrupt:
            raise
        except KeyError as exc:
            # Variável de ambiente faltando NÃO é queda de conexão, e chamá-la
            # assim custou tempo real: `KB_DATABASE_URL` ausente aparecia como
            # "consumer connection dropped: 'KB_DATABASE_URL'" com backoff
            # exponencial, o que parece rede instável e manda investigar o
            # RabbitMQ. Repetir para sempre não conserta um `.env` -- é preciso
            # dizer o que falta e por que não adianta esperar.
            logger.error(
                "variável de ambiente ausente: %s — o worker NÃO vai se recuperar "
                "sozinho, isto não é queda de conexão. Carregue o .env antes de "
                "subir o daemon: `set -a; . ./.env; set +a`", exc,
            )
        except Exception as exc:
            logger.warning("consumer connection dropped: %s", exc)
        finally:
            ig_queue.close(connection)

    backoff = 1
    while True:
        try:
            consume_once()
        except KeyboardInterrupt:
            break
        time.sleep(backoff)
        backoff = min(backoff * 2, 30)
        logger.info("reconnecting in %ss...", backoff)


if __name__ == "__main__":
    run()
