"""Knowledge base storage: Postgres + pgvector via SQLAlchemy ORM."""
from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Callable, Optional

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, create_engine, delete, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker

EMBEDDING_DIM = int(os.environ.get("EMBEDDING_DIM", "1024"))  # mxbai-embed-large


class Base(DeclarativeBase):
    pass


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    type: Mapped[str] = mapped_column(String(20))
    source_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    platform: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    language: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    transcription_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tutorial: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    objectives: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tags: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    raw_file_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    llm_provider: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    llm_model: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    chunks: Mapped[list["Chunk"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    chunk_text: Mapped[str] = mapped_column(Text)
    chunk_index: Mapped[int] = mapped_column(Integer)

    document: Mapped["Document"] = relationship(back_populates="chunks")
    embedding: Mapped[Optional["Embedding"]] = relationship(
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

    chunk: Mapped["Chunk"] = relationship(back_populates="embedding")


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


def chunk_text(text: str, max_chars: int = 1000, overlap: int = 100) -> list[str]:
    """Split text into overlapping chunks for embedding/search."""
    text = text.strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]
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
) -> Document:
    """Insert a Document + its chunks + their embeddings in one transaction."""
    doc = Document(
        type=type, source_url=source_url, platform=platform, title=title,
        language=language, transcription_text=transcription_text, summary=summary,
        tutorial=tutorial, objectives=objectives, tags=tags,
        raw_file_path=raw_file_path, llm_provider=llm_provider, llm_model=llm_model,
    )
    session.add(doc)
    session.flush()  # assigns doc.id

    text_for_chunks = "\n\n".join(filter(None, [summary, tutorial, transcription_text]))
    for idx, piece in enumerate(chunk_text(text_for_chunks)):
        chunk = Chunk(document_id=doc.id, chunk_text=piece, chunk_index=idx)
        session.add(chunk)
        session.flush()  # assigns chunk.id
        vector = embed_fn(piece)
        session.add(Embedding(chunk_id=chunk.id, model=embedding_model, vector=vector))

    session.commit()
    session.refresh(doc)
    return doc


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

    merged: dict[int, dict[str, Any]] = {}
    for row in keyword_rows:
        entry = merged.setdefault(
            row.document_id, {"document_id": row.document_id, "snippets": [], "score": 0.0}
        )
        entry["snippets"].append(row.chunk_text)
        entry["score"] += float(row.score)
    for row in semantic_rows:
        similarity = 1.0 - float(row.distance)
        entry = merged.setdefault(
            row.document_id, {"document_id": row.document_id, "snippets": [], "score": 0.0}
        )
        entry["snippets"].append(row.chunk_text)
        entry["score"] += similarity

    ranked = sorted(merged.values(), key=lambda r: r["score"], reverse=True)[:top_k]
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
