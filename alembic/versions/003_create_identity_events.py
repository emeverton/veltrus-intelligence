"""create identity_events

Revision ID: 003
Revises: 002
Create Date: 2026-06-23
"""

from typing import Sequence, Union

from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE identity_events (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            profile_id  UUID NOT NULL REFERENCES identity_profiles(id) ON DELETE CASCADE,
            event_type  TEXT NOT NULL,
            event_data  JSONB NOT NULL DEFAULT '{}',
            source      TEXT,
            session_id  TEXT,
            occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute("CREATE INDEX idx_events_profile ON identity_events(profile_id)")
    op.execute("CREATE INDEX idx_events_occurred ON identity_events(occurred_at DESC)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS identity_events")
