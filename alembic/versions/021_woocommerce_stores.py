"""021 woocommerce stores

Revision ID: 021
Revises: 020
Create Date: 2026-06-25
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "021"
down_revision: Union[str, None] = "020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "woocommerce_stores",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("store_url", sa.Text, nullable=False, unique=True),
        sa.Column("display_name", sa.Text, nullable=True),
        sa.Column("webhook_secret", sa.Text, nullable=False),
        sa.Column("consumer_key", sa.Text, nullable=True),
        sa.Column("consumer_secret", sa.Text, nullable=True),
        sa.Column("meta_pixel_id", sa.Text, nullable=True),
        sa.Column("meta_access_token", sa.Text, nullable=True),
        sa.Column("meta_test_event_code", sa.Text, nullable=True),
        sa.Column("google_ads_customer_id", sa.Text, nullable=True),
        sa.Column("google_ads_conversion_action", sa.Text, nullable=True),
        sa.Column("active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )
    op.create_index("idx_wc_stores_url", "woocommerce_stores", ["store_url"])


def downgrade() -> None:
    op.drop_index("idx_wc_stores_url", table_name="woocommerce_stores")
    op.drop_table("woocommerce_stores")
