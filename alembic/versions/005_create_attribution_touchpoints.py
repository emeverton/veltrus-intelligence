"""create attribution_touchpoints

Revision ID: 005
Revises: 004
Create Date: 2026-06-23
"""

from typing import Sequence, Union

from alembic import op

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE attribution_touchpoints (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            profile_id      UUID NOT NULL REFERENCES identity_profiles(id) ON DELETE CASCADE,
            touchpoint_type TEXT NOT NULL,
            channel         TEXT NOT NULL,
            campaign_id     TEXT,
            ad_id           TEXT,
            source          TEXT,
            medium          TEXT,
            gclid           TEXT,
            fbclid          TEXT,
            occurred_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            metadata        JSONB NOT NULL DEFAULT '{}'
        )
        """
    )
    op.execute("CREATE INDEX idx_tp_profile ON attribution_touchpoints(profile_id)")
    op.execute("CREATE INDEX idx_tp_occurred ON attribution_touchpoints(occurred_at DESC)")
    op.execute("CREATE INDEX idx_tp_channel ON attribution_touchpoints(channel)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS attribution_touchpoints")
