#!/usr/bin/env python3
"""Unit tests for db.py ranking fusion and chunking edge cases — no Postgres.

Covers:
- _fuse_rankings (RRF): the keyword branch (ts_rank ~0.01-0.1) must stop being
  dwarfed by the semantic branch (cosine ~0.6-0.9). RRF is scale-free.
- chunk_text guard: overlap >= max_chars must not infinite-loop.

Run: uv run --directory . python tests/unit_db.py
Exit 0 = all pass. Any failure prints [BAD] and exits non-zero.
"""
import signal
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


from minimax_mcp import db

print("== unit_db: _fuse_rankings (RRF) keyword vs semantic balance ==")

# Doc 1: strong keyword only. Doc 2: strong semantic only.
# Old sum score -> semantic (0.9) dwarfs keyword (0.05). RRF -> rank 1 each, tie.
kw = [(1, "chunk kw do doc1")]
sem = [(2, "chunk sem do doc2")]
ranked = db._fuse_rankings(kw, sem, top_k=5)
scores = {r["document_id"]: r["score"] for r in ranked}
if set(scores) == {1, 2} and abs(scores[1] - scores[2]) < 1e-9:
    ok("keyword-only rank-1 doc ties semantic-only rank-1 doc (RRF is scale-free)")
else:
    bad(f"RRF scores = {scores!r}; keyword still dwarfed?")

# A doc matching BOTH lists is boosted above any single-list match.
kw = [(1, "kw doc1"), (2, "kw doc2")]
sem = [(2, "sem doc2"), (3, "sem doc3")]
ranked = db._fuse_rankings(kw, sem, top_k=5)
order = [r["document_id"] for r in ranked]
scores = {r["document_id"]: r["score"] for r in ranked}
if order == [2, 1, 3]:
    ok("matched-by-both doc2 ranks first; then kw-rank1 doc1, then sem-rank2 doc3")
else:
    bad(f"RRF order = {order!r}, scores = {scores!r}")

# Keyword rank matters: kw rank1 > sem rank2 (not swallowed by magnitude).
if scores[1] > scores[3]:
    ok("keyword rank 1 outranks semantic rank 2")
else:
    bad(f"kw rank1 ({scores[1]}) should beat sem rank2 ({scores[3]})")

# top_k truncation.
ranked = db._fuse_rankings(kw, sem, top_k=1)
if [r["document_id"] for r in ranked] == [2]:
    ok("top_k=1 keeps only the best-fused document")
else:
    bad(f"top_k=1 result = {ranked!r}")

# Empty inputs are safe.
if db._fuse_rankings([], [], top_k=5) == []:
    ok("_fuse_rankings([], []) == []")
else:
    bad("_fuse_rankings([], []) should be []")

print("== unit_db: chunk_text never infinite-loops ==")
class _Alarm(Exception):
    pass


def _handler(signum, frame):
    raise _Alarm("chunk_text hung (overlap >= max_chars)")


signal.signal(signal.SIGALRM, _handler)
signal.alarm(5)
try:
    chunks = db.chunk_text("x" * 500, max_chars=100, overlap=150)
    signal.alarm(0)
    if chunks and all(len(c) <= 100 for c in chunks) and len(chunks) < 500:
        ok(f"chunk_text(max=100, overlap=150) -> {len(chunks)} chunks, no infinite loop")
    else:
        bad(f"chunk_text returned weird chunks: {[len(c) for c in chunks][:5]}")
except _Alarm:
    bad("chunk_text with overlap >= max_chars infinite-loops")
finally:
    signal.alarm(0)

# Sanity: normal overlap still produces correct overlap.
chunks = db.chunk_text("a" * 2500, max_chars=1000, overlap=100)
if len(chunks) == 3 and chunks[0][-100:] == chunks[1][:100]:
    ok("normal overlap (100) still yields 3 overlapping chunks")
else:
    bad(f"normal overlap broken: {[len(c) for c in chunks]}")

print()
if FAIL:
    print(f"FAIL: {FAIL}")
    sys.exit(1)
print("PASS")
