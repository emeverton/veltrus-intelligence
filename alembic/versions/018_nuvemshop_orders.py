"""018 nuvemshop orders

Revision ID: 018
Revises: 017
Create Date: 2026-06-25
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "018"
down_revision: Union[str, None] = "017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "nuvemshop_orders",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("nuvemshop_order_id", sa.Text, nullable=False, unique=True),
        sa.Column("store_id", sa.Text, nullable=False),
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
        sa.Column("channel", sa.Text, nullable=True),
        sa.Column(
            "processing_status",
            sa.Text,
            nullable=False,
            server_default="pending",
        ),
        sa.Column("raw_payload", JSONB, nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )
    op.create_index("idx_nuvem_orders_id", "nuvemshop_orders", ["nuvemshop_order_id"])
    op.create_index("idx_nuvem_orders_store", "nuvemshop_orders", ["store_id"])
    op.create_index("idx_nuvem_orders_created", "nuvemshop_orders", ["created_at"])


def downgrade() -> None:
    op.drop_index("idx_nuvem_orders_created", table_name="nuvemshop_orders")
    op.drop_index("idx_nuvem_orders_store", table_name="nuvemshop_orders")
    op.drop_index("idx_nuvem_orders_id", table_name="nuvemshop_orders")
    op.drop_table("nuvemshop_orders")
