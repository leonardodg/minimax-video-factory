"""Enumerate the user's Instagram saved posts and publish them to the queue.

instagrapi is used only here (enumeration) — the worker downloads by pk via
yt-dlp, so IG_SESSIONID is only needed for enumeration. Business logic
(to_messages/split_new) is pure and unit-tested with duck-typed Media objects.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Callable

from minimax_mcp import db, ig_queue

logger = logging.getLogger(__name__)

IG_SESSIONID = os.environ.get("IG_SESSIONID", "")
SESSIONID_MISSING = "IG_SESSIONID not configured"

# instagrapi MediaType values: 1 = image, 2 = video, 8 = album/carousel
MEDIA_TYPES = {1: "image", 2: "video", 8: "carousel"}


def make_client() -> Any:
    """Build an authenticated instagrapi Client from IG_SESSIONID."""
    from instagrapi import Client

    client = Client()
    client.delay_range = [1, 3]  # avoid Instagram checkpoint/rate-limit
    client.set_sessionid(IG_SESSIONID)
    return client


def to_messages(media_items: list[Any]) -> list[dict]:
    """Map instagrapi Media-like objects to queue message dicts.

    Duck-typed on .pk/.media_type/.caption_text/.user.username so tests can
    pass simple stand-ins. Skips items with no pk or unknown media_type.
    """
    messages: list[dict] = []
    for m in media_items:
        pk = getattr(m, "pk", None)
        media_type = MEDIA_TYPES.get(getattr(m, "media_type", None))
        if not pk or not media_type:
            continue
        caption = (getattr(m, "caption_text", "") or "").strip()
        title = caption.splitlines()[0][:80] if caption else "sem título"
        user = getattr(m, "user", None)
        messages.append({
            "ig_pk": str(pk),
            "media_type": media_type,
            "url": f"https://www.instagram.com/p/{pk}/",
            "title": title,
            "owner_username": getattr(user, "username", None),
            "collection_name": getattr(m, "collection_name", None),
            "status": "queued",
        })
    return messages


def split_new(messages: list[dict], existing_pks: set[str]) -> tuple[list[dict], int]:
    """Partition messages into not-yet-ingested vs already-known ig_pks."""
    new: list[dict] = []
    skipped = 0
    for msg in messages:
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
    posts = list(client.saved_posts())
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
