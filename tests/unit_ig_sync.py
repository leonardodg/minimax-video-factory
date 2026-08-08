#!/usr/bin/env python3
"""Unit tests for ig_sync.py — duck-typed Media objects, injected client."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

FAIL = 0


def ok(label: str) -> None:
    print(f"  [ok]   {label}")


def bad(label: str) -> None:
    global FAIL
    FAIL += 1
    print(f"  [BAD]  {label}")


from minimax_mcp import ig_sync


class User:
    username = "anajcodes"


class Media:
    def __init__(self, pk, media_type, caption="", user=None):
        self.pk = pk
        self.media_type = media_type
        self.caption_text = caption
        self.user = user or User()


print("== unit_ig_sync: to_messages ==")
items = [
    Media("1001", 2, "Reel de teste\nsegunda linha"),
    Media("1002", 1, "Foto"),
    Media("1003", 8),
    Media(None, 2),
]
msgs = ig_sync.to_messages(items)

if len(msgs) == 3:
    ok("to_messages keeps video/image/carousel, drops pk-less")
else:
    bad(f"to_messages returned {len(msgs)} messages")

m0 = msgs[0]
if (
    m0["ig_pk"] == "1001"
    and m0["media_type"] == "video"
    and m0["url"] == "https://www.instagram.com/p/1001/"
    and m0["owner_username"] == "anajcodes"
    and m0["title"] == "Reel de teste"
    and m0["collection_name"] is None
    and m0["status"] == "queued"
):
    ok("to_messages maps video Media to the message contract")
else:
    bad(f"video message = {m0!r}")

if msgs[1]["media_type"] == "image" and msgs[2]["media_type"] == "carousel":
    ok("image and carousel media_types map correctly")
else:
    bad(f"media types = {[m['media_type'] for m in msgs]}")

print("== unit_ig_sync: split_new ==")
new, skipped = ig_sync.split_new(msgs, existing_pks={"1001"})
if len(new) == 2 and skipped == 1:
    ok("split_new drops existing ig_pks")
else:
    bad(f"split_new = new={len(new)} skipped={skipped}")

print("== unit_ig_sync: sync_saved_posts ==")
published = []


def fake_publish(msg):
    published.append(msg)


class FakeClient:
    def saved_posts(self):
        return items


result = ig_sync.sync_saved_posts(FakeClient(), existing_pks={"1001"}, publish_fn=fake_publish)
if (
    result["ok"]
    and result["published"] == 2
    and result["skipped_existing"] == 1
    and result["total"] == 3
    and len(published) == 2
):
    ok("sync_saved_posts publishes only new posts and reports counts")
else:
    bad(f"sync_saved_posts = {result!r}")

print()
if FAIL:
    print(f"FAIL: {FAIL}")
    sys.exit(1)
print("PASS")
