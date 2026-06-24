"""012 shopify orders

Revision ID: 012
Revises: 011
Create Date: 2026-06-23
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "012"
down_revision: Union[str, None] = "011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "shopify_orders",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("shopify_order_id", sa.Text, nullable=False, unique=True),
        sa.Column(
            "profile_id",
            UUID(as_uuid=True),
            sa.ForeignKey("identity_profiles.id"),
            nullable=True,
        ),
        sa.Column(
            "conversion_id",
            UUID(as_uuid=True),
            sa.ForeignKey("attribution_conversions.id"),
            nullable=True,
        ),
        sa.Column("email", sa.Text, nullable=True),
        sa.Column("phone", sa.Text, nullable=True),
        sa.Column("total_price", sa.Float, nullable=False),
        sa.Column("currency", sa.Text, nullable=False, server_default="BRL"),
        sa.Column("utm_source", sa.Text, nullable=True),
        sa.Column("utm_medium", sa.Text, nullable=True),
        sa.Column("utm_campaign", sa.Text, nullable=True),
        sa.Column("gclid", sa.Text, nullable=True),
        sa.Column("fbclid", sa.Text, nullable=True),
        sa.Column("channel", sa.Text, nullable=True),
        sa.Column("referring_site", sa.Text, nullable=True),
        sa.Column("line_items", JSONB, nullable=False, server_default="[]"),
        sa.Column("raw_payload", JSONB, nullable=False, server_default="{}"),
        sa.Column(
            "processing_status",
            sa.Text,
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )
    op.create_index("idx_shopify_order_id", "shopify_orders", ["shopify_order_id"])
    op.create_index("idx_shopify_profile", "shopify_orders", ["profile_id"])
    op.create_index("idx_shopify_created", "shopify_orders", ["created_at"])
    op.create_index("idx_shopify_channel", "shopify_orders", ["channel"])


def downgrade() -> None:
    op.drop_index("idx_shopify_channel", table_name="shopify_orders")
    op.drop_index("idx_shopify_created", table_name="shopify_orders")
    op.drop_index("idx_shopify_profile", table_name="shopify_orders")
    op.drop_index("idx_shopify_order_id", table_name="shopify_orders")
    op.drop_table("shopify_orders")
