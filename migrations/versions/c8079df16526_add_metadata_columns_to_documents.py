"""add_metadata_columns_to_documents

Revision ID: c8079df16526
Revises: 4e70cb5a67e9
Create Date: 2026-04-24 17:35:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'c8079df16526'
down_revision: Union[str, Sequence[str], None] = '4e70cb5a67e9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add columns to documents table
    op.add_column('documents', sa.Column('file_type', sa.String(length=100), nullable=True))
    op.add_column('documents', sa.Column('page_count', sa.Integer(), nullable=True))
    op.add_column('documents', sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    # Remove columns from documents table
    op.drop_column('documents', 'metadata')
    op.drop_column('documents', 'page_count')
    op.drop_column('documents', 'file_type')
