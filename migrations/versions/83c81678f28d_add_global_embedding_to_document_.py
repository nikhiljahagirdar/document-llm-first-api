"""Add global embedding to document_versions

Revision ID: 83c81678f28d
Revises: fc1a84ebb364
Create Date: 2026-04-26 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '83c81678f28d'
down_revision: Union[str, Sequence[str], None] = 'fc1a84ebb364'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add embedding column to document_versions
    op.execute("ALTER TABLE document_versions ADD COLUMN IF NOT EXISTS embedding vector(768)")
    # Create an index for faster similarity searches
    op.execute("CREATE INDEX IF NOT EXISTS idx_doc_versions_embedding_ivfflat ON document_versions USING ivfflat (embedding vector_cosine_ops) WITH (lists=100)")


def downgrade() -> None:
    op.drop_index('idx_doc_versions_embedding_ivfflat', table_name='document_versions')
    op.drop_column('document_versions', 'embedding')
