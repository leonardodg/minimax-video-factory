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


def saved_posts(client: Any, max_per_collection: int = 200) -> list[dict]:
    """Enumerate saved posts across the "All posts" collection + named ones.

    instagrapi v2 renamed saved_posts() to collections()/collection_medias();
    older versions keep saved_posts(). This prefers the modern API (which also
    carries the collection name for the message) and falls back to the legacy
    single list.

    Returns a flat list of {"media": Media, "collection_name": str} dicts.
    """
    if hasattr(client, "collection_medias"):
        results: list[dict] = []
        cols = list(client.collections())
        for col in cols:
            if getattr(col, "type", "") == "ALL_MEDIA_AUTO_COLLECTION":
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
            for m in medias:
                results.append({"media": m, "collection_name": name})
        return results
    # Legacy API
    return [{"media": m, "collection_name": None} for m in client.saved_posts()]


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
            "url": f"https://www.instagram.com/p/{pk}/",
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
) -> dict:
    """Enumerate saved posts, filter to new ig_pks, publish each. Returns counts.

    `publish_fn` is injected so the tool can wire it to ig_queue.publish with a
    real channel while tests pass a recorder.
    """
    posts = saved_posts(client)
    messages = to_messages(posts)
    new, skipped = split_new(messages, existing_pks)
    for msg in new:
        publish_fn(msg)
    return {
        "ok": True,
        "published": len(new),
        "skipped_existing": skipped,
        "total": len(messages),
    }
