"""023 generic stores

Revision ID: 023
Revises: 022
Create Date: 2026-06-25
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "023"
down_revision: Union[str, None] = "022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "generic_stores",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("store_id", sa.Text, nullable=False, unique=True),
        sa.Column("display_name", sa.Text, nullable=True),
        sa.Column("api_key", sa.Text, nullable=False),
        sa.Column("platform", sa.Text, nullable=False, server_default="other"),
        sa.Column("meta_pixel_id", sa.Text, nullable=True),
        sa.Column("meta_access_token", sa.Text, nullable=True),
        sa.Column("meta_test_event_code", sa.Text, nullable=True),
        sa.Column("google_ads_customer_id", sa.Text, nullable=True),
        sa.Column("google_ads_conversion_action", sa.Text, nullable=True),
        sa.Column("active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("metadata_", JSONB, nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )
    op.create_index("idx_generic_stores_id", "generic_stores", ["store_id"])
    op.create_index("idx_generic_stores_platform", "generic_stores", ["platform"])


def downgrade() -> None:
    op.drop_index("idx_generic_stores_platform", table_name="generic_stores")
    op.drop_index("idx_generic_stores_id", table_name="generic_stores")
    op.drop_table("generic_stores")
