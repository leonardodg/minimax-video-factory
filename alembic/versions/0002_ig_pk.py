"""add ig_pk to documents for Instagram saved-posts dedup

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-08
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("ig_pk", sa.String(64), nullable=True))
    op.create_index("ix_documents_ig_pk", "documents", ["ig_pk"])


def downgrade() -> None:
    op.drop_index("ix_documents_ig_pk", table_name="documents")
    op.drop_column("documents", "ig_pk")
