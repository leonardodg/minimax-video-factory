"""Enumerate the user's Instagram saved posts and publish them to the queue.

instagrapi is used only here (enumeration) — the worker downloads by pk via
yt-dlp, so IG_SESSIONID is only needed for enumeration. Business logic
(to_messages/split_new) is pure and unit-tested with duck-typed Media objects.
"""
from __future__ import annotations

import logging
import os
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

IG_SESSIONID = os.environ.get("IG_SESSIONID", "")
SESSIONID_MISSING = "IG_SESSIONID not configured"

# instagrapi MediaType values: 1 = image, 2 = video, 8 = album/carousel
MEDIA_TYPES = {1: "image", 2: "video", 8: "carousel"}

# Auto-collections that are not real categories; kept out of the vocabulary.
AUTO_COLLECTION_NAMES = {"all posts", "todos os posts", "all", "todos"}

# Static fallback used when collections are unavailable (offline, API error).
FALLBACK_CATEGORIES = [
    "receita", "dica", "tutorial", "tech", "curso", "estudo", "inglês",
    "viagem", "house", "bitcoin", "treino", "car", "dog", "livro",
    "notícia", "outros",
]


def list_categories(client: Any) -> list[str]:
    """Normalized unique collection names — the category vocabulary for vision.

    Auto-collections ("All posts"/"Todos os posts") are excluded. Names are
    stripped, inner whitespace collapsed, and deduplicated case-insensitively
    keeping the first spelling. Any failure (or a None client) returns the
    static fallback list, never raises.
    """
    if client is None:
        return list(FALLBACK_CATEGORIES)
    try:
        names: list[str] = []
        seen: set[str] = set()
        for col in client.collections():
            raw = (getattr(col, "name", "") or "").strip()
            key = " ".join(raw.lower().split())
            if not key or key in AUTO_COLLECTION_NAMES or key in seen:
                continue
            seen.add(key)
            names.append(" ".join(raw.split()))
        return names or list(FALLBACK_CATEGORIES)
    except Exception:
        return list(FALLBACK_CATEGORIES)


def post_url(pk: Any, code: str | None = None) -> str:
    """O link do post. `/p/` quer o SHORTCODE, não o pk numérico.

    Estava montado como `/p/{pk}/`, e isso quebrava duas coisas ao mesmo tempo:
    o `source_url` de todo documento apontava para um link que não abre, e o
    fallback de yt-dlp -- que recebe essa URL quando o download autenticado
    falha -- levava HTTP 400 e nunca poderia funcionar. Medido em 2026-08-10,
    num post cujo download travou por timeout do CDN.

    Sem `code` à mão, o shortcode se CALCULA a partir do pk: é o mesmo número
    noutra base, e o instagrapi traz o codec. Nenhuma requisição de rede -- o
    que importa porque isso corrige em massa documentos já gravados.
    """
    if code:
        return f"https://www.instagram.com/p/{code}/"
    try:
        from instagrapi.utils import InstagramIdCodec

        return f"https://www.instagram.com/p/{InstagramIdCodec.encode(int(pk))}/"
    except Exception:
        # Um link torto é melhor que uma exceção no meio da listagem.
        return f"https://www.instagram.com/p/{pk}/"


def make_client() -> Any:
    """Build an authenticated instagrapi Client from IG_SESSIONID."""
    from instagrapi import Client

    client = Client()
    client.delay_range = [1, 3]  # avoid Instagram checkpoint/rate-limit
    # instagrapi renamed set_sessionid -> login_by_sessionid (v2+); the old
    # name was removed, not just deprecated.
    login = getattr(client, "login_by_sessionid", None)
    if login is None:
        login = client.set_sessionid
    login(IG_SESSIONID)
    return client


def saved_posts(client: Any, max_per_collection: int = 0) -> list[dict]:
    """Enumerate saved posts across the "All posts" collection + named ones.

    instagrapi v2 renamed saved_posts() to collections()/collection_medias();
    older versions keep saved_posts(). This prefers the modern API (which also
    carries the collection name for the message) and falls back to the legacy
    single list.

    `max_per_collection=0` means "todas as páginas" -- é o padrão porque
    qualquer teto trunca ESTA sincronização **em silêncio**, que é exatamente o
    modo de falha que o plano manda vigiar. O padrão antigo era 200, e medido
    em 2026-08-10 a conta que ele dava era: a catch-all "All posts" guarda
    TODOS os posts salvos (3618) e entregaria 200; Receitas (1124), Inglês
    (564) e Dev (287) também passam do teto. O resultado seria um lote parcial
    indistinguível de uma punição do Instagram -- e a reação a cada um dos dois
    é oposta (esperar horas contra mudar um parâmetro).

    Vale registrar a suspeita, que não é conclusão: o incidente de 2026-08-09
    em que uma varredura "viu 202 posts em vez de 2157" bate com 200 + 2.

    Returns a flat list of {"media": Media, "collection_name": str} dicts.
    """
    return [entry for _, entries in saved_posts_by_collection(client, max_per_collection)
            for entry in entries]


def saved_posts_by_collection(client: Any, max_per_collection: int = 0):
    """Igual a `saved_posts`, mas rende UMA coleção por vez.

    Existe para que a sincronização publique conforme enumera, em vez de
    acumular tudo e publicar no fim. A coleção "All posts" tinha 3618 posts na
    medição de 2026-08-10; enumerar tudo antes de publicar a primeira mensagem
    é o que fazia o `ig_sync_saved` ser morto por silêncio -- 1800 s sem emitir
    nada, e o MCP corta.

    ⚠️ **A ordem importa, e não é a que o Instagram devolve.** As coleções
    NOMEADAS vêm primeiro e a catch-all por último. O `dedupe_by_pk` prefere a
    mensagem que nomeia uma coleção, mas essa preferência só funciona quando as
    duas estão no mesmo lote -- publicando incrementalmente, quem sai primeiro
    ganha. Como a catch-all guarda TODOS os posts com `collection_name=None`,
    enumerá-la primeiro faria cada post ser publicado sem coleção, e o
    "Dev"/"Receitas" chegaria depois, tarde demais. É a mesma falha que o
    docstring do `dedupe_by_pk` descreve, só que causada pela ordem.

    Rende `(collection_name, [{"media": ..., "collection_name": ...}, ...])`.
    """
    if not hasattr(client, "collection_medias"):
        # Legacy API: uma "coleção" só, sem nome.
        yield None, [{"media": m, "collection_name": None} for m in client.saved_posts()]
        return

    cols = list(client.collections())

    def eh_catch_all(col) -> bool:
        return getattr(col, "type", "") == "ALL_MEDIA_AUTO_COLLECTION"

    # nomeadas primeiro, catch-all por último
    for col in sorted(cols, key=eh_catch_all):
        if eh_catch_all(col):
            # The catch-all holds every saved post, so its name carries no
            # information -- but it was being written as a tag on almost
            # every document, diluting tag search for nothing. None means
            # "no collection", and the worker then adds no tag.
            name = None
        else:
            name = getattr(col, "name", "") or None
        try:
            medias = list(client.collection_medias(col.id, amount=max_per_collection))
        except Exception as exc:
            # One unreadable collection must not abort the whole sync, but
            # silence here means a collection can go missing from every run
            # with nothing to show for it.
            logger.warning("skipping collection %r: %s", name, exc)
            continue
        yield name, [{"media": m, "collection_name": name} for m in medias]


def to_messages(items: list[dict]) -> list[dict]:
    """Map saved-post entries (from saved_posts) to queue message dicts.

    `items` is a list of {"media": Media-like, "collection_name": str}. The
    Media is duck-typed on .pk/.media_type/.caption_text/.user.username so tests
    can pass simple stand-ins. Skips items with no pk or unknown media_type.
    """
    messages: list[dict] = []
    for entry in items:
        m = entry["media"]
        pk = getattr(m, "pk", None)
        media_type = MEDIA_TYPES.get(getattr(m, "media_type", None))
        if not pk or not media_type:
            continue
        caption = (getattr(m, "caption_text", "") or "").strip()
        # None, not "sem título": knowledge.ingest_text already derives a title
        # from the generated summary when none is given, and a placeholder here
        # is truthy enough to block it -- which is how a document ended up
        # literally titled "sem título".
        title = caption.splitlines()[0][:80] if caption else None
        user = getattr(m, "user", None)
        messages.append({
            "ig_pk": str(pk),
            "media_type": media_type,
            "url": post_url(pk, getattr(m, "code", None)),
            "title": title,
            "owner_username": getattr(user, "username", None),
            "collection_name": entry.get("collection_name"),
            "status": "queued",
        })
    return messages


def dedupe_by_pk(messages: list[dict]) -> list[dict]:
    """One message per ig_pk, preferring the one that names a collection.

    `saved_posts` yields one entry per (post, collection) pair, so a post saved
    in three collections becomes three messages. They all carry the same media
    and the worker acks the extras via `document_exists` -- but whichever one
    happens to be consumed FIRST decides the document's collection tag, and the
    catch-all (collection_name=None) is as likely to win as the real one. That
    is how a post filed under "Dev" could land with no collection at all.

    Order is preserved so the priority ordering a caller applies still holds.
    """
    best: dict[str, dict] = {}
    order: list[str] = []
    for msg in messages:
        pk = msg["ig_pk"]
        if pk not in best:
            best[pk] = msg
            order.append(pk)
        elif not best[pk].get("collection_name") and msg.get("collection_name"):
            best[pk] = msg
    return [best[pk] for pk in order]


def split_new(messages: list[dict], existing_pks: set[str]) -> tuple[list[dict], int]:
    """Partition messages into not-yet-ingested vs already-known ig_pks.

    Deduplicates within the batch first: `existing_pks` only knows what is
    already in the database, so without this a post saved in three collections
    is published three times on the very first sync.
    """
    new: list[dict] = []
    skipped = 0
    for msg in dedupe_by_pk(messages):
        if msg["ig_pk"] in existing_pks:
            skipped += 1
        else:
            new.append(msg)
    return new, skipped


def sync_saved_posts(
    client: Any,
    *,
    existing_pks: set[str],
    publish_fn: Callable[[dict], None],
    progress_fn: Callable[[dict], None] | None = None,
    reprocessar: bool = False,
) -> dict:
    """Enumera os salvos e publica CONFORME enumera. Devolve as contagens.

    `publish_fn` é injetado para a tool ligá-lo ao `ig_queue.publish` com um
    canal real enquanto os testes passam um gravador.

    **Publica por coleção, não no fim.** A versão anterior acumulava tudo antes
    da primeira mensagem, e com 3618 posts na catch-all isso significava ~30 min
    sem emitir nada -- o `ig_sync_saved` foi morto duas vezes assim
    (SIGTERM e o corte de 1800 s do MCP). Publicando por coleção:

      - o worker começa a consumir enquanto a enumeração ainda corre
      - uma interrupção no meio preserva o que já foi enfileirado
      - `progress_fn` recebe um resumo por coleção, então há sinal de vida

    `reprocessar=True` ignora `existing_pks` e reenfileira tudo. O worker
    ainda pula o que já está no banco (`document_exists`), então isso só faz
    sentido junto com uma limpeza -- ou para reprocessar de propósito.
    """
    publicados = 0
    pulados = 0
    total = 0
    vistos: set[str] = set()

    for nome, entradas in saved_posts_by_collection(client):
        mensagens = to_messages(entradas)
        total += len(mensagens)

        # `vistos` faz o papel que o `dedupe_by_pk` fazia dentro de um lote só:
        # sem ele, um post salvo em três coleções seria publicado três vezes,
        # agora que os lotes são separados.
        conhecidos = vistos if reprocessar else (vistos | existing_pks)
        novas, pulou = split_new(mensagens, conhecidos)

        for msg in novas:
            publish_fn(msg)
            vistos.add(msg["ig_pk"])

        publicados += len(novas)
        pulados += pulou
        if progress_fn:
            progress_fn({
                "collection": nome or "(todos os salvos)",
                "in_collection": len(mensagens),
                "published": len(novas),
                "skipped": pulou,
                "published_total": publicados,
            })

    return {
        "ok": True,
        "published": publicados,
        "skipped_existing": pulados,
        "total": total,
    }
