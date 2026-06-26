"""029 kairos sequences

Revision ID: 029
Revises: 028
Create Date: 2026-06-26
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "029"
down_revision: Union[str, None] = "028"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "kairos_sequences",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "profile_id",
            UUID(as_uuid=True),
            sa.ForeignKey("identity_profiles.id"),
            nullable=False,
        ),
        sa.Column("run_id", sa.Text, nullable=False),
        sa.Column("segment", sa.Text, nullable=False),
        sa.Column("trigger_type", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False, server_default="email_pending"),
        sa.Column("email", sa.Text, nullable=True),
        sa.Column("email_subject", sa.Text, nullable=True),
        sa.Column("email_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("email_opened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("email_message_id", sa.Text, nullable=True),
        sa.Column("phone", sa.Text, nullable=True),
        sa.Column("wa_text", sa.Text, nullable=True),
        sa.Column("wa_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("wa_replied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("outcome", sa.Text, nullable=True),
        sa.Column("metadata_", JSONB, nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )
    op.create_index("idx_kairos_seq_profile", "kairos_sequences", ["profile_id"])
    op.create_index("idx_kairos_seq_status", "kairos_sequences", ["status"])
    op.create_index("idx_kairos_seq_run", "kairos_sequences", ["run_id"])
    op.create_index("idx_kairos_seq_created", "kairos_sequences", ["created_at"])
    op.create_index(
        "idx_kairos_seq_wa_pending",
        "kairos_sequences",
        ["status", "email_sent_at"],
        postgresql_where=sa.text("status = 'email_sent'"),
    )


def downgrade() -> None:
    op.drop_index("idx_kairos_seq_wa_pending", table_name="kairos_sequences")
    op.drop_index("idx_kairos_seq_created", table_name="kairos_sequences")
    op.drop_index("idx_kairos_seq_run", table_name="kairos_sequences")
    op.drop_index("idx_kairos_seq_status", table_name="kairos_sequences")
    op.drop_index("idx_kairos_seq_profile", table_name="kairos_sequences")
    op.drop_table("kairos_sequences")
