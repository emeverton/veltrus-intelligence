"""013 shopify stores

Revision ID: 013
Revises: 012
Create Date: 2026-06-24
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "013"
down_revision: Union[str, None] = "012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "shopify_stores",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("shop_domain", sa.Text, nullable=False, unique=True),
        sa.Column("display_name", sa.Text, nullable=True),
        sa.Column("webhook_secret", sa.Text, nullable=False),
        sa.Column("meta_pixel_id", sa.Text, nullable=True),
        sa.Column("meta_access_token", sa.Text, nullable=True),
        sa.Column("meta_test_event_code", sa.Text, nullable=True),
        sa.Column("google_ads_customer_id", sa.Text, nullable=True),
        sa.Column("google_ads_conversion_action", sa.Text, nullable=True),
        sa.Column("active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("metadata", JSONB, nullable=False, server_default="{}"),
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
    op.create_index("idx_stores_domain", "shopify_stores", ["shop_domain"])
    op.create_index("idx_stores_active", "shopify_stores", ["active"])


def downgrade() -> None:
    op.drop_index("idx_stores_active", table_name="shopify_stores")
    op.drop_index("idx_stores_domain", table_name="shopify_stores")
    op.drop_table("shopify_stores")
