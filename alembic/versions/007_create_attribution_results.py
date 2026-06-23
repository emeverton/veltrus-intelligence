"""create attribution_results

Revision ID: 007
Revises: 006
Create Date: 2026-06-23
"""

from typing import Sequence, Union

from alembic import op

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE attribution_results (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            conversion_id   UUID NOT NULL REFERENCES attribution_conversions(id) ON DELETE CASCADE,
            profile_id      UUID NOT NULL REFERENCES identity_profiles(id),
            model           TEXT NOT NULL,
            channel         TEXT NOT NULL,
            campaign_id     TEXT,
            credit          FLOAT NOT NULL,
            revenue_credit  FLOAT,
            computed_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_result ON attribution_results (
            conversion_id, model, channel, COALESCE(campaign_id, '')
        )
        """
    )
    op.execute("CREATE INDEX idx_results_conversion ON attribution_results(conversion_id)")
    op.execute("CREATE INDEX idx_results_profile ON attribution_results(profile_id)")
    op.execute("CREATE INDEX idx_results_model ON attribution_results(model)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS attribution_results")
