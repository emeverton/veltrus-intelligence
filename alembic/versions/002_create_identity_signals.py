"""create identity_signals

Revision ID: 002
Revises: 001
Create Date: 2026-06-23
"""

from typing import Sequence, Union

from alembic import op

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE identity_signals (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            profile_id      UUID NOT NULL REFERENCES identity_profiles(id) ON DELETE CASCADE,
            signal_type     TEXT NOT NULL,
            signal_hash     TEXT NOT NULL,
            confidence      FLOAT NOT NULL DEFAULT 1.0,
            source          TEXT,
            first_seen      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            last_seen       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_signal UNIQUE (signal_type, signal_hash)
        )
        """
    )
    op.execute("CREATE INDEX idx_signals_hash ON identity_signals(signal_hash)")
    op.execute("CREATE INDEX idx_signals_profile ON identity_signals(profile_id)")
    op.execute("CREATE INDEX idx_signals_type ON identity_signals(signal_type)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS identity_signals")
