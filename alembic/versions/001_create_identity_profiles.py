"""create identity_profiles

Revision ID: 001
Revises:
Create Date: 2026-06-23
"""

from typing import Sequence, Union

from alembic import op

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute(
        """
        CREATE TABLE identity_profiles (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            is_known    BOOLEAN NOT NULL DEFAULT FALSE,
            confidence  FLOAT NOT NULL DEFAULT 1.0,
            metadata    JSONB NOT NULL DEFAULT '{}'
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS identity_profiles")
