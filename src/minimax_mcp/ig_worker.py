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
    # Inglês. Metade do que o usuário salva é de conta gringa, e o vocabulário
    # só existia em português -- por isso "😱Still not Following me?? You'll
    # miss all of it.." virou TÍTULO do doc 212, e "Follow @darpan.decoded"
    # entrou no conteúdo pelo texto lido da tela.
    #
    # Os padrões são estreitos de propósito. `follow` sozinho apagaria "follow
    # the steps below" e "follow this pattern", que é exatamente o conteúdo que
    # esta base existe para guardar: um CTA que sobrevive é ruído, uma instrução
    # apagada é perda.
    # "follow me/us" SÓ quando fecha a oração ou vem seguido de on/for/@ --
    # senão apaga "the compiler will follow us through the type graph", que é
    # conteúdo. Um CTA que sobrevive é ruído; uma instrução apagada é perda.
    r"follow(?:ing)? (?:me|us)(?=\W*(?:on\b|for\b|@|$|[.!?]))",
    r"follow @",
    r"follow (?:for|to get) more",
    r"still not following",
    r"save (?:this|the) (?:post|video|reel|one)",
    r"share (?:this|it) with (?:a|your|ur)",
    r"tag (?:a|your) (?:friend|buddy)",
    r"link in (?:the )?bio",
    r"(?:double.?tap|smash that)",
    r"(?:comment|drop a comment)[^.!?]*(?:below|and i(?:'|’)?ll|to get)",
    r"turn on (?:the )?notifications",
)
# Fim de frase é `.!?` SEGUIDO de espaço ou fim do texto -- não qualquer ponto.
# O separador antigo quebrava dentro de `main.py`, `Python 3.11` e do handle
# `@darpan.decoded`, e essa última quebra fez o padrão de CTA atravessar o ponto
# e engolir a frase seguinte inteira ("How can I scale containers?" sumiu junto
# com o "Follow @..."). Este conteúdo é cheio de nome de arquivo e versão, então
# o defeito não era teórico.
_TERM = r"[.!?](?=\s|$)"
_NAO_TERM = r"(?:(?!" + _TERM + r").)"

_CTA_SENTENCE_RE = re.compile(
    _NAO_TERM + r"*(?:" + "|".join(_CTA_PATTERNS) + r")" + _NAO_TERM + r"*" + _TERM,
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
    _NAO_TERM + r"*(?:" + "|".join(_CTA_PATTERNS) + r")" + _NAO_TERM + r"*$",
    re.IGNORECASE | re.DOTALL,
)
# Num TÍTULO, qualquer CTA condena a linha inteira. O título vem da primeira
# linha da legenda, é curto, e quando ele cai o `ingest_text` deriva um a partir
# do resumo -- então descartar é barato e o resultado é melhor. Recortar um
# pedaço deixava sobras sem sentido: "😱Still not Following me?? You'll miss all
# of it.." virava "? You'll miss all of it..", que tem duas palavras e passava
# no teste de tamanho.
_CTA_QUALQUER_RE = re.compile("|".join(_CTA_PATTERNS), re.IGNORECASE)
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
    # CTA na PRIMEIRA frase condena o título inteiro; depois dela, basta aparar.
    # A posição é o que separa os dois casos reais:
    #   "😱Still not Following me?? You'll miss all of it.."  -> abre com CTA, a
    #      linha é promocional inteira, e aparar deixava "You'll miss all of it..",
    #      que não é título de nada;
    #   "Estude comigo na Fluency. Link na Bio."              -> o CTA é o rabo,
    #      e "Estude comigo na Fluency." é um título legítimo -- foi para isso
    #      que o clean_title nasceu.
    if _CTA_QUALQUER_RE.search(re.split(_TERM, raw, maxsplit=1)[0]):
        return None
    t = _CTA_TAIL_RE.sub("", strip_cta(raw))
    t = _HASHTAG_RE.sub("", t)
    # Corta só espaço e separador órfão. Ponto final e exclamação FICAM: tirá-los
    # mudaria títulos perfeitamente bons ("Uma receita simples." -> "Uma receita
    # simples") e encheria a comparação de diferenças que não são limpeza de CTA.
    t = re.sub(r"\s+", " ", t).strip(" -–—|·•,;:")
    return t if len(_WORD_RE.findall(t)) >= 2 else None

IG_DOWNLOADS_DIR = Path(os.environ.get("IG_DOWNLOADS_DIR", "downloads/ig"))
# Guardar a mídia é o padrão, e o motivo é uma assimetria de custo, não disco
# sobrando: uma requisição ao Instagram é escassa e punível (em 2026-08-09 duas
# varreduras numa hora derrubaram a listagem), enquanto reprocessar na GPU é
# lento mas local, repetível e sem consequência externa. Apagar a mídia amarra
# as duas -- qualquer conserto no lado barato (transcrever com um Whisper
# melhor, descrever a imagem com outro modelo) só se paga voltando ao lado caro.
#
# O que NÃO depende disto: refazer resumo, categoria, tags ou prompt do LLM. A
# transcrição inteira já fica em `documents.transcription_text` (medido: 585 a
# 4035 caracteres nos 12 primeiros), e para imagem é a descrição da visão que
# cai lá. Esse reprocessamento -- o mais provável de todos -- nunca precisou de
# mídia nem de Instagram.
#
# O padrão é `false` de propósito: se o .env não for carregado, o pior caso
# passa a ser encher o disco (visível e reversível) em vez de perder trabalho de
# rede em silêncio (invisível e caro).
IG_DELETE_AFTER_INGEST = os.environ.get("IG_DELETE_AFTER_INGEST", "false").lower() in (
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
    read_screen: Callable[[str], dict] | None = None,
    ingest: Callable[[str], dict],
    categories: list[str] | None = None,
) -> dict:
    """Download -> transcribe/describe -> ingest. Pure; all IO injected.

    Videos transcribe the first downloaded file. Images/carousels describe
    cada arquivo de IMAGEM e juntam os `conteudo_principal` num texto só, para
    o conteúdo espalhado pelas fotos do carrossel não se perder. A categoria da
    primeira foto vira a tag `categoria:<nome>`.

    **Carrossel misto tem foto E vídeo, e o `kind` é decidido pelo primeiro
    arquivo.** Um post que começa com foto entrava aqui como imagem e mandava
    os `.mp4` junto para o modelo de visão, que devolvia o mesmo
    `Failed to load image or audio file` do WebP -- 9 posts na DLQ de
    2026-08-18, todos carrosséis mistos. Descrever só as imagens é o que faz
    sentido: o modelo de visão não lê vídeo, e a foto do carrossel carrega o
    conteúdo que interessa.
    """
    from minimax_mcp import ig_sync

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

        # O que está NA TELA e o áudio não diz. Roda aqui, no mesmo processo e em
        # sequência, porque a folga já existe: o post leva ~46 s dentro de uma
        # janela de 90 s, e a leitura custou ~14 s no teste de 2026-08-10. O
        # `pace_sleep_seconds` conta do início da mensagem, então isso encolhe a
        # pausa em vez de esticar a corrida -- custo de cronograma ZERO.
        #
        # Sequencial, não paralelo, e a diferença é a VRAM: o pico do worker é
        # 10,8 GB dos 12,3 GB da placa, sobrando 1,4 GB. O modelo de visão pede
        # ~6 GB. Dois processos disputando a GPU colidiriam -- um de cada vez, não.
        tela = ""
        if read_screen is not None:
            rs = read_screen(filepaths[0])
            if rs.get("ok"):
                tela = (rs.get("text") or "").strip()
            else:
                # Ler a tela é ganho, não requisito: a falha não pode custar a
                # transcrição que já foi paga.
                logger.warning("leitura de tela falhou: %s", rs.get("error"))
        if tela and (text or "").strip():
            text = f"{text}\n\n--- texto na tela ---\n{tela}"
        elif tela:
            # Sem fala, a tela É o conteúdo -- e vem antes da legenda, que é
            # material de divulgação. É o caso dos posts de dica sobre imagem
            # parada com música, que o usuário apontou em 2026-08-10.
            # A MESMA cadeia de reserva do ramo de baixo. Ela existia lá e
            # faltava aqui, e a diferença custou 21 documentos: quando a
            # mídia vem do disco não há `media_info`, `dl["caption"]` volta
            # vazio, e a legenda era descartada em silêncio. A mensagem da
            # fila agora carrega a legenda inteira; o título é o último
            # reserva, para as mensagens antigas que não a têm.
            legenda = (dl.get("caption") or message.get("caption")
                       or message.get("title") or "").strip()
            text = f"--- texto na tela ---\n{tela}"
            if legenda:
                text = f"{text}\n\n--- legenda ---\n{legenda}"
            lang = "pt"
            logger.info(
                "ig_pk=%s sem fala; usando a tela (%d caracteres)",
                message.get("ig_pk"), len(tela),
            )
        if not (text or "").strip():
            # Vídeo sem fala nenhuma -- reel de música. Medido no piloto de
            # 2026-08-10: 4 dos 40 primeiros posts (10%), com o VAD do Whisper
            # removendo 100% do áudio ("VAD filter removed 00:10.613" num clipe
            # de 00:10.613). O `ingest_text` recusa texto vazio, então isso
            # falhava e ia para a DLQ depois de TRÊS tentativas.
            #
            # As três tentativas eram desperdício garantido: transcrever o mesmo
            # arquivo dá o mesmo vazio, sempre. Na escala da corrida, ~15 h de
            # GPU para re-falhar.
            #
            # A legenda completa vem do `media_info` que o download já fez; o
            # título da mensagem é o reserva, e é pior (primeira linha, 80
            # caracteres) -- só serve quando a mídia veio reaproveitada do disco
            # e não houve `media_info`.
            text = (dl.get("caption") or message.get("caption")
                    or message.get("title") or "").strip()
            lang = "pt"
            if not text:
                # Sem fala e sem legenda não existe documento possível: não há
                # texto nenhum para resumir. `permanent` manda direto para a
                # DLQ, sem gastar as duas tentativas restantes num resultado
                # que já se sabe.
                return {
                    "status": "error", "error": "sem fala e sem legenda",
                    "permanent": True, "filepaths": filepaths,
                }
            logger.info(
                "ig_pk=%s sem fala; usando a legenda (%d caracteres)",
                message.get("ig_pk"), len(text),
            )
    else:
        if describe is None:
            return {"status": "error", "error": "no describe provided for image", "filepaths": filepaths}
        pieces: list[str] = []
        escritos: list[str] = []
        # Só as imagens. O modelo de visão não lê vídeo, e mandar um `.mp4`
        # para ele devolvia HTTP 400 -- que, pela linha de baixo, matava o post
        # inteiro mesmo com as fotos boas do lado.
        imagens = [fp for fp in filepaths if classify_file(fp) == "image"]
        if not imagens:
            return {"status": "error", "error": "carrossel sem nenhuma imagem para descrever",
                    "filepaths": filepaths}
        if len(imagens) < len(filepaths):
            logger.info(
                "ig_pk=%s: carrossel misto, descrevendo %d imagem(ns) e ignorando %d vídeo(s)",
                message.get("ig_pk"), len(imagens), len(filepaths) - len(imagens),
            )
        falhas: list[str] = []
        for fp in imagens:
            de = describe(fp)
            if not de.get("ok"):
                # Uma foto que não descreve não pode custar as outras. É o mesmo
                # erro estrutural que fazia um post malformado derrubar a
                # coleção inteira na listagem: o item ruim leva junto tudo o que
                # já estava pago. Só falha o post se NENHUMA imagem descrever.
                falhas.append(str(de.get("error", "describe failed")))
                logger.warning("descrição falhou em %s: %s", Path(fp).name, de.get("error"))
                continue
            pieces.append(de.get("conteudo_principal") or de.get("text") or "")
            if categoria is None:
                categoria = de.get("categoria")
            # DESCREVER não é LER. O `describe_image` devolvia "Como adicionar
            # aspas automáticas em um bloco de citação usando HTML e CSS" para um
            # carrossel que MOSTRAVA o CSS inteiro na imagem -- a descrição do
            # que o post ensina, não o que está escrito nele. Num post de
            # infográfico ou print de código, o texto É o conteúdo, e ele estava
            # sendo perdido inteiro (doc 333, apontado pelo usuário).
            if read_screen is not None:
                rs = read_screen(fp)
                if rs.get("ok") and (rs.get("text") or "").strip():
                    escritos.append(rs["text"].strip())
                elif not rs.get("ok"):
                    logger.warning("leitura de texto da imagem falhou: %s", rs.get("error"))
        if falhas and not pieces:
            # NENHUMA imagem descreveu -- aí não há post. Devolve o primeiro
            # erro, que é o que o diagnóstico precisa; contar as falhas diz se
            # foi um azar ou o post todo.
            return {"status": "error",
                    "error": f"describe falhou em todas as {len(falhas)} imagem(ns): {falhas[0]}",
                    "filepaths": filepaths}
        descricao = "\n\n".join(p for p in pieces if p)
        lido = merge_screen_text(escritos)
        # REGRA: post só de imagem, sem fala nenhuma -> o TEXTO DA IMAGEM é o
        # conteúdo, e a descrição é apoio. Antes vinha ao contrário, e o que o
        # modelo lia primeiro era "Como adicionar aspas automáticas em um bloco
        # de citação usando HTML e CSS" -- a descrição do que o post ensina, com
        # o CSS de verdade relegado ao fim.
        if lido:
            text = f"--- texto na imagem ---\n{lido}"
            if descricao:
                text = f"{text}\n\n--- descrição da imagem ---\n{descricao}"
        else:
            text = descricao
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
        # Recalculado do pk em vez de confiado à mensagem. As 3111 mensagens
        # publicadas em 2026-08-10 08:29 carregam `/p/{pk}/`, que não abre, e
        # elas não se reescrevem -- consertar só a listagem deixaria a corrida
        # inteira com link quebrado. Cálculo local, sem rede.
        source_url=ig_sync.post_url(message.get("ig_pk")) if message.get("ig_pk")
        else message.get("url"),
        title=title,
        platform="instagram",
        doc_type=doc_type,
        language=lang,
        ig_pk=message.get("ig_pk"),
        extra_tags=extra_tags,
        # Onde a mídia ficou. A coluna sempre existiu e estava `None` nos 12
        # primeiros documentos -- o esquema já previa guardar a origem, e apagar
        # o arquivo tornava o campo morto. Guardando a mídia, ele volta a ter
        # uso: é por ele que se acha o que re-transcrever sem voltar ao
        # Instagram. Aponta para o primeiro arquivo; num carrossel, os irmãos
        # estão na mesma pasta (uma por `ig_pk`).
        raw_file_path=filepaths[0],
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
    """Trata start/stop, mutando `state` E a assinatura da fila de trabalho.

    O booleano sozinho não pausava nada -- era lido só numa linha de log, e o
    worker continuava consumindo depois de responder "paused". Aqui o efeito é
    real: `basic_cancel` faz o broker parar de entregar; `basic_consume` volta a
    receber. `state["canal"]` e `state["tag"]` são preenchidos pelo laço de
    consumo a cada conexão, e ficam None nos testes, onde só o booleano importa.
    """
    canal, tag = state.get("canal"), state.get("tag")
    if command == "start":
        ja_rodando = not state["paused"]
        state["paused"] = False
        if canal is not None and not ja_rodando:
            try:
                state["tag"] = canal.basic_consume(
                    queue=ig_queue.QUEUE, on_message_callback=state["on_work"]
                )
            except Exception as exc:
                logger.warning("não consegui retomar o consumo: %s", exc)
        return "resumed"
    if command == "stop":
        ja_parado = state["paused"]
        state["paused"] = True
        if canal is not None and tag is not None and not ja_parado:
            try:
                canal.basic_cancel(tag)
                state["tag"] = None
            except Exception as exc:
                logger.warning("não consegui cancelar o consumo: %s", exc)
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
    return _targets_from_info(client.media_info(pk), pk)


def _targets_from_info(info: Any, pk: str) -> list[tuple[str, str]]:
    """A parte pura de `_download_targets`: dado o `media_info`, quais downloads.

    Separado para que quem já tem o `info` na mão não peça de novo. O
    `media_info` é a chamada AUTENTICADA do consumo, uma por post e 3111 numa
    corrida -- duplicá-la só para ler a legenda seria dobrar exatamente o
    recurso escasso.
    """
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
        # Pela URL assinada, não pelo pk -- e é o MESMO defeito que o conserto de
        # carrossel (43453e2) resolveu para o álbum e deixou passar aqui.
        # `photo_download(pk)` re-resolve a mídia por dentro do instagrapi, cai
        # no GraphQL PÚBLICO, leva 401 e bate na parede de login. Observado em
        # 2026-08-10 11:57 no post 3780736256808395559: media_info privado 200,
        # depois três 401 públicos e um HTML de login em ~25 s. O post foi
        # ingerido assim mesmo, então isso nunca apareceu como falha -- só como
        # 62 imagens da fila cutucando a parede de graça, que é justamente o
        # padrão que atrai bloqueio de verdade.
        url = getattr(info, "thumbnail_url", None)
        if url:
            return [("photo_download_by_url", str(url))]
        logger.warning("imagem %s sem thumbnail_url, caindo no download por pk", pk)
        return [("photo_download", pk)]
    return [("clip_download", pk)]


def post_media_dir(pk: str) -> Path:
    """Onde a mídia de um post vive: uma pasta por `ig_pk`.

    Sem isso não dá para perguntar "a mídia deste post já está no disco?". Os
    nomes de arquivo vêm do instagrapi e, num carrossel, carregam o pk do
    **recurso**, não o do post -- então o pk do post não aparece em lugar nenhum
    e nada liga os oito arquivos de um álbum ao álbum.
    """
    return IG_DOWNLOADS_DIR / str(pk)


def existing_media(pk: str) -> list[str]:
    """Arquivos já baixados deste post, em ordem de download.

    Ordena por mtime (e nome, para desempatar) porque a ordem importa: num
    carrossel, `process_message` junta a descrição de cada foto NA ORDEM, e uma
    reordenação mudaria o texto do documento entre a primeira passada e um
    reprocessamento.
    """
    d = post_media_dir(pk)
    if not d.is_dir():
        return []
    files = [p for p in d.iterdir() if p.is_file()]
    files.sort(key=lambda p: (p.stat().st_mtime, p.name))
    return [str(p) for p in files]


def _default_download(message: dict) -> dict:
    """Download the media for a saved post — ou reaproveita o que já está no disco.

    Prefers the authenticated instagrapi client (the worker already has
    IG_SESSIONID, and saved/private posts are unreachable by anonymous yt-dlp),
    falling back to yt-dlp (public posts, or when IG_SESSIONID is unset).
    Carousels download every resource; the result exposes both `filepath`
    (first item) and `filepaths` (all items) for back-compat.

    Os pares vindos de `_download_targets` são `(método, argumento)`, e o
    argumento é um **pk ou uma URL** conforme o método — os três aceitam o
    primeiro posicional mais `folder=`, então a chamada aqui serve para ambos.

    **O reuso vem antes de qualquer requisição, e é ele que dá sentido a guardar
    a mídia.** Guardar arquivo sem conferir se ele existe não pouparia nada: o
    worker baixaria de novo do mesmo jeito, e cada retry da DLQ (são três) seria
    mais uma ida ao Instagram. O que se evita aqui não é só o download -- é o
    `media_info` de `_download_targets`, que é a chamada AUTENTICADA, uma por
    post, 3606 vezes numa corrida completa.
    """
    url = message.get("url", "")
    pk = message.get("ig_pk", "")
    if pk:
        cached = existing_media(pk)
        if cached:
            logger.info(
                "post %s: reaproveitando %d arquivo(s) do disco, sem tocar o Instagram",
                pk, len(cached),
            )
            return {"ok": True, "filepath": cached[0], "filepaths": cached, "reused": True}
    if pk:
        try:
            dest = post_media_dir(pk)
            dest.mkdir(parents=True, exist_ok=True)
            from minimax_mcp import ig_sync

            client = ig_sync.make_client()
            client.delay_range = [0.5, 1.0]
            # Um media_info só, e dele saem as duas coisas: o que baixar e a
            # legenda COMPLETA. A mensagem da fila só carrega a primeira linha
            # cortada em 80 caracteres (`to_messages`), que é pouco para virar
            # documento quando o vídeo não tem fala nenhuma.
            info = client.media_info(pk)
            legenda = (getattr(info, "caption_text", "") or "").strip()
            filepaths: list[str] = []
            for method, target in _targets_from_info(info, pk):
                out = getattr(client, method)(target, folder=str(dest))
                if out and Path(out).exists():
                    filepaths.append(str(Path(out)))
            if filepaths:
                return {
                    "ok": True, "filepath": filepaths[0],
                    "filepaths": filepaths, "caption": legenda,
                }
        except Exception as e:
            logger.warning("instagrapi download failed for %s: %s", pk, e)

    from minimax_mcp.downloader import VideoDownloader

    dest = post_media_dir(pk) if pk else IG_DOWNLOADS_DIR
    dest.mkdir(parents=True, exist_ok=True)
    downloader = VideoDownloader(output_dir=dest, browser="chrome")
    dl = downloader.download(url)
    if dl.get("ok") and dl.get("filepath"):
        dl["filepaths"] = [dl["filepath"]]
    return dl


IG_SCREEN_FRAMES = int(os.environ.get("IG_SCREEN_FRAMES", "4") or 4)


def extract_frames(video_path: str, n: int = IG_SCREEN_FRAMES) -> list[str]:
    """`n` quadros espalhados pelo vídeo, num diretório temporário.

    Espalhados e não do começo: o código costuma entrar depois da abertura, e os
    últimos segundos costumam ser CTA. Medido em 2026-08-10 num vídeo de 14,6 s,
    4 quadros custaram **0,15 s** de ffmpeg -- irrelevante perto dos ~14 s da
    visão, então não vale otimizar aqui.

    Os quadros são descartáveis: o que se guarda é o vídeo, e refazer custa 0,15 s.
    """
    import subprocess
    import tempfile

    try:
        dur = float(subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", video_path],
            capture_output=True, text=True, timeout=30, check=True,
        ).stdout.strip())
    except Exception as exc:
        logger.warning("ffprobe falhou em %s: %s", video_path, exc)
        return []
    if dur <= 0:
        return []

    d = Path(tempfile.mkdtemp(prefix="igframes_"))
    try:
        subprocess.run(
            ["ffmpeg", "-nostdin", "-v", "error", "-i", video_path,
             "-vf", f"fps={n}/{dur},scale=1080:-1", "-frames:v", str(n),
             "-q:v", "2", str(d / "f_%02d.jpg")],
            capture_output=True, timeout=120, check=True,
        )
    except Exception as exc:
        logger.warning("ffmpeg falhou em %s: %s", video_path, exc)
        return []
    return sorted(str(p) for p in d.glob("*.jpg"))


def merge_screen_text(pedacos: list[str]) -> str:
    """Junta o texto dos quadros sem repetir o que já apareceu.

    Quadros vizinhos de um vídeo parado mostram quase a mesma tela -- no teste de
    2026-08-10 os quadros 3 e 4 devolveram o mesmo bloco de código, um deles
    truncado no meio de uma linha. Repetir isso três vezes no documento não
    acrescenta nada e ainda empurra o resumo para o lado errado.

    Deduplica por LINHA e preserva a ordem: a linha truncada some porque a
    completa já entrou, e o que é genuinamente novo em cada quadro fica.
    """
    saida: list[str] = []      # a linha como veio, para o documento
    chaves: list[str] = []      # a mesma, normalizada, para comparar
    for p in pedacos:
        for linha in (p or "").splitlines():
            chave = " ".join(linha.split())
            if not chave:
                continue
            # O truncamento pode chegar nos DOIS sentidos: a versão cortada vem
            # antes da inteira quando o quadro mais cedo pegou a digitação no
            # meio, e depois dela quando o vídeo já rolou. Tratar só um sentido
            # deixava as duas no documento -- foi o que o teste pegou.
            contida = next((i for i, k in enumerate(chaves) if chave in k), None)
            if contida is not None:
                continue
            contem = next((i for i, k in enumerate(chaves) if k in chave), None)
            if contem is not None:
                saida[contem] = linha.rstrip()
                chaves[contem] = chave
                continue
            chaves.append(chave)
            saida.append(linha.rstrip())
    return "\n".join(saida).strip()


def guardar_capa(quadros: list[str], video_path: str) -> str | None:
    """Guarda UM quadro como capa do post, ao lado do vídeo.

    De graça: os quadros já foram extraídos para ler a tela, e o que se guarda é
    uma cópia de ~100 KB (~310 MB nos 3111 posts). Converter para GIF daria uma
    prévia mais expressiva num meme, mas custa outra passada de ffmpeg por post
    e pesa bem mais -- e o mp4 inteiro continua no disco de qualquer forma.

    O segundo quadro, não o primeiro: a abertura costuma ser rosto falando ou
    tela preta, e o fim costuma ser CTA. O miolo representa melhor o post.
    """
    if not quadros:
        return None
    escolhido = quadros[1] if len(quadros) > 1 else quadros[0]
    destino = Path(video_path).parent / "capa.jpg"
    try:
        destino.write_bytes(Path(escolhido).read_bytes())
        return str(destino)
    except OSError as exc:
        logger.warning("não consegui guardar a capa de %s: %s", video_path, exc)
        return None


def _default_read_screen(video_path: str) -> dict:
    """Lê o texto que está escrito na mídia. Aceita vídeo e imagem.

    Imagem vai direto para a visão; vídeo precisa de quadros antes. Sem esse
    desvio, uma foto entraria no ffmpeg como se fosse filme e não sobraria
    quadro nenhum -- e é justamente no post de imagem (infográfico, print de
    código) que o texto escrito É o conteúdo.
    """
    import shutil

    if classify_file(video_path) == "image":
        return llm.read_screen(video_path)

    quadros = extract_frames(video_path)
    if not quadros:
        return {"ok": True, "text": ""}
    pai = str(Path(quadros[0]).parent)
    try:
        capa = guardar_capa(quadros, video_path)
        pedacos = []
        for q in quadros:
            r = llm.read_screen(q)
            if r.get("ok") and r.get("text"):
                pedacos.append(r["text"])
            elif not r.get("ok"):
                logger.warning("leitura de tela falhou em %s: %s", q, r.get("error"))
        return {"ok": True, "text": merge_screen_text(pedacos), "capa": capa}
    finally:
        # Os quadros são descartáveis (0,15 s para refazer); a capa já foi
        # copiada para fora daqui.
        shutil.rmtree(pai, ignore_errors=True)


_categories_cache: list[str] | None = None


def _discard_media(res: dict) -> None:
    """Apaga a mídia baixada, tenha a ingestão dado certo ou não.

    Só roda quando `IG_DELETE_AFTER_INGEST` é ligado explicitamente, e hoje o
    padrão é NÃO apagar -- ver a nota em cima da constante. Guardar troca disco
    (barato, local, mensurável) por requisição ao Instagram (escassa e punível).

    A frase que ficava aqui, "se ele for retentado, baixa de novo", deixou de
    ser o comportamento normal e passou a descrever só o caso de quem liga a
    variável: com a mídia no disco, `_default_download` reaproveita e o retry
    não volta à rede.
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

    # `paused` precisa CANCELAR a assinatura da fila de trabalho, não só virar um
    # booleano. Até 2026-08-10 ele era escrito por `apply_command` e lido em UM
    # lugar: a linha de log da conexão. `/ig-worker-stop` respondia "paused", o
    # log dizia "paused", e o worker continuava consumindo.
    #
    # Custou um OOM de verdade: confiando na pausa, a GPU foi entregue a um
    # reprocessamento, o worker seguiu transcrevendo, e o Whisper caiu para CPU
    # com "CUDA failed with error out of memory". Os dois usos da GPU não cabem
    # juntos -- o pico do worker é 10,8 GB dos 12,3 GB da placa.
    #
    # `basic_cancel` para o broker de ENTREGAR; nack/requeue não serviria, porque
    # a mensagem voltaria na hora e o worker giraria em falso consumindo CPU e
    # incrementando `attempts` até a DLQ.
    state: dict = {"paused": False, "tag": None, "canal": None}

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
            read_screen=_default_read_screen,
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
            permanente = bool(res.get("permanent"))
            logger.warning(
                "processing failed ig_pk=%s: %s%s",
                message["ig_pk"], res["error"], " (permanente)" if permanente else "",
            )
            try:
                # Uma falha determinística não melhora na segunda tentativa. Só
                # o que depende do mundo lá fora -- timeout de CDN, soluço de
                # rede -- merece o retry; repetir o que já se sabe custa dois
                # ciclos de IG_WORKER_MIN_INTERVAL por post e, na escala desta
                # corrida, horas de GPU para chegar no mesmo lugar.
                if permanente:
                    ig_queue.dead_letter(ch, properties, body)
                else:
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
            # A fila de CONTROLE é assinada sempre; a de trabalho, só quando não
            # está pausado. Assim uma reconexão no meio de uma pausa não a
            # desfaz em silêncio -- e `start` continua chegando para retomar.
            state["canal"], state["on_work"] = channel, on_work
            state["tag"] = None if state["paused"] else channel.basic_consume(
                queue=ig_queue.QUEUE, on_message_callback=on_work
            )
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
