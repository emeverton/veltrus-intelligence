"""create attribution_conversions

Revision ID: 006
Revises: 005
Create Date: 2026-06-23
"""

from typing import Sequence, Union

from alembic import op

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE attribution_conversions (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            profile_id  UUID NOT NULL REFERENCES identity_profiles(id) ON DELETE CASCADE,
            revenue     FLOAT NOT NULL,
            currency    TEXT NOT NULL DEFAULT 'BRL',
            occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            metadata    JSONB NOT NULL DEFAULT '{}'
        )
        """
    )
    op.execute("CREATE INDEX idx_conv_profile ON attribution_conversions(profile_id)")
    op.execute("CREATE INDEX idx_conv_occurred ON attribution_conversions(occurred_at DESC)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS attribution_conversions")
