"""create identity_profile_merges

Revision ID: 004
Revises: 003
Create Date: 2026-06-23
"""

from typing import Sequence, Union

from alembic import op

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE identity_profile_merges (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            source_profile_id   UUID NOT NULL REFERENCES identity_profiles(id),
            target_profile_id   UUID NOT NULL REFERENCES identity_profiles(id),
            merge_reason        TEXT,
            merged_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute("CREATE INDEX idx_merges_source ON identity_profile_merges(source_profile_id)")
    op.execute("CREATE INDEX idx_merges_target ON identity_profile_merges(target_profile_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS identity_profile_merges")
