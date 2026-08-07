"""initial schema: documents, chunks, embeddings + pgvector extension

Revision ID: 0001
Revises:
Create Date: 2026-08-07
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

EMBEDDING_DIM = 1024  # mxbai-embed-large; bump + new migration if EMBEDDING_MODEL changes


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "documents",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("type", sa.String(20), nullable=False),
        sa.Column("source_url", sa.Text, nullable=True),
        sa.Column("platform", sa.String(50), nullable=True),
        sa.Column("title", sa.Text, nullable=True),
        sa.Column("language", sa.String(10), nullable=True),
        sa.Column("transcription_text", sa.Text, nullable=True),
        sa.Column("summary", sa.Text, nullable=True),
        sa.Column("tutorial", sa.Text, nullable=True),
        sa.Column("objectives", sa.Text, nullable=True),
        sa.Column("tags", sa.JSON, nullable=True),
        sa.Column("raw_file_path", sa.Text, nullable=True),
        sa.Column("llm_provider", sa.String(50), nullable=True),
        sa.Column("llm_model", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_table(
        "chunks",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "document_id", sa.Integer,
            sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("chunk_text", sa.Text, nullable=False),
        sa.Column("chunk_index", sa.Integer, nullable=False),
    )
    op.create_table(
        "embeddings",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "chunk_id", sa.Integer,
            sa.ForeignKey("chunks.id", ondelete="CASCADE"), nullable=False, unique=True,
        ),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("vector", Vector(EMBEDDING_DIM), nullable=False),
    )
    op.create_index(
        "ix_chunks_text_tsv",
        "chunks",
        [sa.text("to_tsvector('portuguese', chunk_text)")],
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_index("ix_chunks_text_tsv", table_name="chunks")
    op.drop_table("embeddings")
    op.drop_table("chunks")
    op.drop_table("documents")
