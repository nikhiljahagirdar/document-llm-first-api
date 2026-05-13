"""Add user_id and prompt text to usage_logs, google integration to documents, and create user_credentials table

Revision ID: fc1a84ebb364
Revises: c8079df16526
Create Date: 2026-04-26 20:39:02.464097

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'fc1a84ebb364'
down_revision: Union[str, Sequence[str], None] = 'c8079df16526'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Update usage_logs
    op.execute("""
        DO $$ 
        BEGIN 
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='usage_logs' AND column_name='user_id') THEN
                ALTER TABLE usage_logs ADD COLUMN user_id UUID REFERENCES users(user_id) ON DELETE SET NULL;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='usage_logs' AND column_name='input_text') THEN
                ALTER TABLE usage_logs ADD COLUMN input_text TEXT;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='usage_logs' AND column_name='output_text') THEN
                ALTER TABLE usage_logs ADD COLUMN output_text TEXT;
            END IF;
        END $$;
    """)

    # 2. Update documents
    op.execute("""
        DO $$ 
        BEGIN 
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='documents' AND column_name='google_file_id') THEN
                ALTER TABLE documents ADD COLUMN google_file_id VARCHAR(255);
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='documents' AND column_name='google_last_modified') THEN
                ALTER TABLE documents ADD COLUMN google_last_modified TIMESTAMP;
            END IF;
        END $$;
    """)

    # 3. Create user_credentials table
    op.execute("""
        CREATE TABLE IF NOT EXISTS user_credentials (
            credential_id UUID PRIMARY KEY,
            user_id UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
            provider VARCHAR(50) NOT NULL,
            access_token TEXT,
            refresh_token TEXT,
            expires_at TIMESTAMP,
            scopes TEXT[],
            created_on TIMESTAMP DEFAULT NOW(),
            updated_on TIMESTAMP DEFAULT NOW(),
            UNIQUE (user_id, provider)
        );
    """)

    # 4. Sync document_chunks embedding dimension (Ensure 3072 for current model)
    # Note: Using execute for vector type as it's an extension
    op.execute("ALTER TABLE document_chunks ALTER COLUMN embedding TYPE vector(3072)")


def downgrade() -> None:
    # Dropping columns and tables
    op.drop_table('user_credentials')
    op.drop_column('documents', 'google_last_modified')
    op.drop_column('documents', 'google_file_id')
    op.drop_column('usage_logs', 'output_text')
    op.drop_column('usage_logs', 'input_text')
    op.drop_column('usage_logs', 'user_id')
