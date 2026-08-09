"""Knowledge base storage: Postgres + pgvector via SQLAlchemy ORM."""
from __future__ import annotations

import os
import re
from collections.abc import Callable
from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    delete,
    func,
    select,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    mapped_column,
    relationship,
    sessionmaker,
)

EMBEDDING_DIM = int(os.environ.get("EMBEDDING_DIM", "1024"))  # mxbai-embed-large


class Base(DeclarativeBase):
    pass


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    type: Mapped[str] = mapped_column(String(20))
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    ig_pk: Mapped[str | None] = mapped_column(String(64), nullable=True)
    platform: Mapped[str | None] = mapped_column(String(50), nullable=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    language: Mapped[str | None] = mapped_column(String(10), nullable=True)
    transcription_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    tutorial: Mapped[str | None] = mapped_column(Text, nullable=True)
    objectives: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags: Mapped[list | None] = mapped_column(JSON, nullable=True)
    raw_file_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    llm_provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    llm_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    chunks: Mapped[list[Chunk]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    chunk_text: Mapped[str] = mapped_column(Text)
    chunk_index: Mapped[int] = mapped_column(Integer)

    document: Mapped[Document] = relationship(back_populates="chunks")
    embedding: Mapped[Embedding | None] = relationship(
        back_populates="chunk", uselist=False, cascade="all, delete-orphan"
    )


class Embedding(Base):
    __tablename__ = "embeddings"

    id: Mapped[int] = mapped_column(primary_key=True)
    chunk_id: Mapped[int] = mapped_column(
        ForeignKey("chunks.id", ondelete="CASCADE"), unique=True
    )
    model: Mapped[str] = mapped_column(String(100))
    vector: Mapped[Any] = mapped_column(Vector(EMBEDDING_DIM))

    chunk: Mapped[Chunk] = relationship(back_populates="embedding")


_engine: Engine | None = None
_SessionLocal: sessionmaker | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        url = os.environ["KB_DATABASE_URL"]
        _engine = create_engine(url, future=True)
    return _engine


def get_session() -> Session:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine(), expire_on_commit=False)
    return _SessionLocal()


_TIMESTAMP_RE = re.compile(r"\[\s*\d+(?:\.\d+)?s\s*-\s*\d+(?:\.\d+)?s\s*\]\s*")


def strip_timestamps(text: str | None) -> str | None:
    """Drop `[12.34s - 56.78s]` markers from a Whisper transcription.

    The stored `transcription_text` keeps them -- they are how a claim is traced
    back to a moment in the video. But the chunks are what gets embedded, and
    there the markers are pure noise: they carry no meaning, they compete for
    room inside the 700-char budget, and they end up matching numeric queries.
    """
    if not text:
        return text
    return _TIMESTAMP_RE.sub("", text).strip()


def chunk_text(text: str, max_chars: int = 700, overlap: int = 100) -> list[str]:
    """Split text into overlapping chunks for embedding/search.

    max_chars defaults to 700 so dense content (code/JSON heavy) stays below the
    Ollama embedding batch limit (~512 tokens) even at ~0.75 tokens/char.
    """
    text = text.strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]
    overlap = max(0, min(overlap, max_chars - 1))
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        chunks.append(text[start:end])
        if end == len(text):
            break
        start = end - overlap
    return chunks


def save_document(
    session: Session,
    *,
    type: str,
    source_url: str | None,
    platform: str | None,
    title: str | None,
    language: str | None,
    transcription_text: str | None,
    summary: str | None,
    tutorial: str | None,
    objectives: str | None,
    tags: list[str] | None,
    raw_file_path: str | None,
    llm_provider: str | None,
    llm_model: str | None,
    embed_fn: Callable[[str], list[float]],
    embedding_model: str,
    ig_pk: str | None = None,
) -> Document:
    """Insert a Document + its chunks + their embeddings in one transaction."""
    doc = Document(
        type=type, source_url=source_url, platform=platform, title=title,
        language=language, transcription_text=transcription_text, summary=summary,
        tutorial=tutorial, objectives=objectives, tags=tags,
        raw_file_path=raw_file_path, llm_provider=llm_provider, llm_model=llm_model,
        ig_pk=ig_pk,
    )
    session.add(doc)
    session.flush()  # assigns doc.id

    text_for_chunks = "\n\n".join(
        filter(None, [summary, tutorial, strip_timestamps(transcription_text)])
    )
    for idx, piece in enumerate(chunk_text(text_for_chunks)):
        chunk = Chunk(document_id=doc.id, chunk_text=piece, chunk_index=idx)
        session.add(chunk)
        session.flush()  # assigns chunk.id
        vector = embed_fn(piece)
        session.add(Embedding(chunk_id=chunk.id, model=embedding_model, vector=vector))

    session.commit()
    session.refresh(doc)
    return doc


def _fuse_rankings(
    keyword_rows: list[tuple[int, str]],
    semantic_rows: list[tuple[int, str]],
    top_k: int,
    rrf_k: float = 60.0,
) -> list[dict[str, Any]]:
    """Fuse keyword (ts_rank) and semantic (cosine) results with Reciprocal Rank
    Fusion (RRF).

    ts_rank scores live in ~0.01-0.1 while cosine similarity is ~0.6-0.9; summing
    them directly lets the semantic branch silently dominate. RRF is scale-free:
    each list contributes 1/(k + rank) per document, so a keyword-only match and a
    semantic-only match at the same rank weigh the same, and documents present in
    both lists get boosted. k=60 is the conventional RRF constant.

    Rows are (document_id, snippet) pairs, already ordered by relevance (keyword
    by ts_rank desc, semantic by distance asc). Returns merged docs sorted by the
    fused score, each with its accumulated snippets.
    """
    merged: dict[int, dict[str, Any]] = {}
    for rank, (doc_id, snippet) in enumerate(keyword_rows, start=1):
        entry = merged.setdefault(
            doc_id, {"document_id": doc_id, "snippets": [], "score": 0.0}
        )
        entry["snippets"].append(snippet)
        entry["score"] += 1.0 / (rrf_k + rank)
    for rank, (doc_id, snippet) in enumerate(semantic_rows, start=1):
        entry = merged.setdefault(
            doc_id, {"document_id": doc_id, "snippets": [], "score": 0.0}
        )
        entry["snippets"].append(snippet)
        entry["score"] += 1.0 / (rrf_k + rank)
    return sorted(merged.values(), key=lambda r: r["score"], reverse=True)[:top_k]


def search_documents(
    session: Session, query: str, embed_fn: Callable[[str], list[float]], top_k: int = 5
) -> list[dict[str, Any]]:
    """Combine Postgres full-text search with pgvector cosine similarity."""
    tsquery = func.plainto_tsquery("portuguese", query)
    keyword_rows = session.execute(
        select(
            Chunk.document_id,
            Chunk.chunk_text,
            func.ts_rank(func.to_tsvector("portuguese", Chunk.chunk_text), tsquery).label("score"),
        )
        .where(func.to_tsvector("portuguese", Chunk.chunk_text).op("@@")(tsquery))
        .order_by(func.ts_rank(func.to_tsvector("portuguese", Chunk.chunk_text), tsquery).desc())
        .limit(top_k)
    ).all()

    query_vector = embed_fn(query)
    semantic_rows = session.execute(
        select(
            Chunk.document_id,
            Chunk.chunk_text,
            Embedding.vector.cosine_distance(query_vector).label("distance"),
        )
        .join(Embedding, Embedding.chunk_id == Chunk.id)
        .order_by(Embedding.vector.cosine_distance(query_vector))
        .limit(top_k)
    ).all()

    ranked = _fuse_rankings(
        keyword_rows=[(r.document_id, r.chunk_text) for r in keyword_rows],
        semantic_rows=[(r.document_id, r.chunk_text) for r in semantic_rows],
        top_k=top_k,
    )
    doc_ids = [r["document_id"] for r in ranked]
    if doc_ids:
        docs_by_id = {
            d.id: d for d in session.execute(select(Document).where(Document.id.in_(doc_ids))).scalars()
        }
        for r in ranked:
            d = docs_by_id.get(r["document_id"])
            if d is not None:
                r["title"] = d.title
                r["source_url"] = d.source_url
                r["summary"] = d.summary
    return ranked


def reindex_all(session: Session, embed_fn: Callable[[str], list[float]], embedding_model: str) -> int:
    """Recompute chunks + embeddings for every document (e.g. after changing EMBEDDING_MODEL)."""
    docs = session.execute(select(Document)).scalars().all()
    for doc in docs:
        session.execute(delete(Chunk).where(Chunk.document_id == doc.id))
        session.flush()
        text_for_chunks = "\n\n".join(filter(None, [doc.summary, doc.tutorial, doc.transcription_text]))
        for idx, piece in enumerate(chunk_text(text_for_chunks)):
            chunk = Chunk(document_id=doc.id, chunk_text=piece, chunk_index=idx)
            session.add(chunk)
            session.flush()
            vector = embed_fn(piece)
            session.add(Embedding(chunk_id=chunk.id, model=embedding_model, vector=vector))
    session.commit()
    return len(docs)


def delete_documents(session: Session, *, source_url: str | None = None) -> int:
    """Delete documents (cascades chunks/embeddings via FK ondelete). Returns count.

    Optional source_url filter is useful for idempotent tests.
    """
    stmt = select(Document)
    if source_url is not None:
        stmt = stmt.where(Document.source_url == source_url)
    docs = session.execute(stmt).scalars().all()
    for doc in docs:
        session.delete(doc)
    session.commit()
    return len(docs)


def document_exists(
    session: Session,
    *,
    ig_pk: str | None = None,
    source_url: str | None = None,
) -> bool:
    """True if a document with that ig_pk (or source_url) already exists."""
    if ig_pk is not None:
        stmt = select(Document.id).where(Document.ig_pk == ig_pk)
    elif source_url is not None:
        stmt = select(Document.id).where(Document.source_url == source_url)
    else:
        return False
    return session.execute(stmt.limit(1)).first() is not None


def list_ig_pks(session: Session) -> set[str]:
    """Every non-null ig_pk currently stored (used to skip re-publishing)."""
    rows = session.execute(
        select(Document.ig_pk).where(Document.ig_pk.isnot(None))
    ).all()
    return {r[0] for r in rows}
