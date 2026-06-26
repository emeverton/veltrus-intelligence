"""030 kairos outreach log

Revision ID: 030
Revises: 029
Create Date: 2026-06-26
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "030"
down_revision: Union[str, None] = "029"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "kairos_outreach_log",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "sequence_id",
            UUID(as_uuid=True),
            sa.ForeignKey("kairos_sequences.id"),
            nullable=False,
        ),
        sa.Column("profile_id", UUID(as_uuid=True), nullable=False),
        sa.Column("channel", sa.Text, nullable=False),
        sa.Column("action", sa.Text, nullable=False),
        sa.Column("message_preview", sa.Text, nullable=True),
        sa.Column("provider_id", sa.Text, nullable=True),
        sa.Column("metadata_", JSONB, nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )
    op.create_index("idx_kairos_log_seq", "kairos_outreach_log", ["sequence_id"])
    op.create_index("idx_kairos_log_profile", "kairos_outreach_log", ["profile_id"])
    op.create_index("idx_kairos_log_created", "kairos_outreach_log", ["created_at"])


def downgrade() -> None:
    op.drop_index("idx_kairos_log_created", table_name="kairos_outreach_log")
    op.drop_index("idx_kairos_log_profile", table_name="kairos_outreach_log")
    op.drop_index("idx_kairos_log_seq", table_name="kairos_outreach_log")
    op.drop_table("kairos_outreach_log")
