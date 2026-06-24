"""009 creative assets

Revision ID: 009
Revises: 008
Create Date: 2026-06-23
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "creative_assets",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("campaign_id", sa.Text, nullable=True),
        sa.Column("channel", sa.Text, nullable=False),
        sa.Column("creative_type", sa.Text, nullable=False),
        sa.Column("name", sa.Text, nullable=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("external_id", sa.Text, nullable=True),
        sa.Column("qdrant_id", sa.Text, nullable=True),
        sa.Column("metadata", JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_creative_campaign", "creative_assets", ["campaign_id"])
    op.create_index("idx_creative_channel", "creative_assets", ["channel"])
    op.create_index("idx_creative_external", "creative_assets", ["external_id"])


def downgrade() -> None:
    op.drop_index("idx_creative_external", table_name="creative_assets")
    op.drop_index("idx_creative_channel", table_name="creative_assets")
    op.drop_index("idx_creative_campaign", table_name="creative_assets")
    op.drop_table("creative_assets")
