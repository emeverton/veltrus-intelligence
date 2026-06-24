"""008 graph sync log

Revision ID: 008
Revises: 007
Create Date: 2026-06-23
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "graph_sync_log",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("conversion_id", UUID(as_uuid=True), sa.ForeignKey("attribution_conversions.id"), nullable=False),
        sa.Column("synced_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("status", sa.Text, nullable=False, server_default="ok"),
        sa.Column("error", sa.Text, nullable=True),
    )
    op.create_index("idx_sync_conversion", "graph_sync_log", ["conversion_id"])


def downgrade() -> None:
    op.drop_index("idx_sync_conversion", table_name="graph_sync_log")
    op.drop_table("graph_sync_log")
