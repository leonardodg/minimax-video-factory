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

print("== unit_db: ig_pk column on Document ==")
from minimax_mcp.db import Document

cols = {c.name for c in Document.__table__.columns}
if "ig_pk" in cols:
    ok("Document model has an ig_pk column")
else:
    bad("Document model is missing ig_pk")

print("== unit_db: strip_timestamps keeps text out of the embeddings ==")

TRANSCRIPT = (
    "[0.00s - 2.72s] Onde você guarda o token JWT no seu front?\n"
    "[2.72s - 4.72s] No local storage ou no cookie?\n"
    "[4.72s - 8.72s] Eu fiz esse post há dois dias atrás."
)
clean = db.strip_timestamps(TRANSCRIPT)

if "[" not in clean and "s -" not in clean:
    ok("timestamp markers are removed")
else:
    bad(f"markers survived: {clean[:80]!r}")

for phrase in ("token JWT", "local storage", "dois dias atrás"):
    if phrase not in clean:
        bad(f"stripping ate real text: {phrase!r} is gone")
        break
else:
    ok("every word of the speech survives")

# 62 of 426 chunks carried these markers into pgvector before this existed.
if db.strip_timestamps(None) is None and db.strip_timestamps("") == "":
    ok("None and empty pass through untouched")
else:
    bad("strip_timestamps mangles None/empty")

if db.strip_timestamps("sem marcador nenhum") == "sem marcador nenhum":
    ok("text without markers is returned unchanged")
else:
    bad("strip_timestamps altered text that had no markers")

# A marker glued to the next word must not swallow it.
if db.strip_timestamps("[1.00s - 2.00s]palavra") == "palavra":
    ok("a marker with no trailing space still leaves the word")
else:
    bad(f"glued marker mishandled: {db.strip_timestamps('[1.00s - 2.00s]palavra')!r}")

print()
if FAIL:
    print(f"FAIL: {FAIL}")
    sys.exit(1)
print("PASS")
