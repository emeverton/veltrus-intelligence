"""019 vtex stores

Revision ID: 019
Revises: 018
Create Date: 2026-06-25
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "019"
down_revision: Union[str, None] = "018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "vtex_stores",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("account_name", sa.Text, nullable=False, unique=True),
        sa.Column("display_name", sa.Text, nullable=True),
        sa.Column("app_key", sa.Text, nullable=False),
        sa.Column("app_token", sa.Text, nullable=False),
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
    op.create_index("idx_vtex_stores_account", "vtex_stores", ["account_name"])


def downgrade() -> None:
    op.drop_index("idx_vtex_stores_account", table_name="vtex_stores")
    op.drop_table("vtex_stores")
