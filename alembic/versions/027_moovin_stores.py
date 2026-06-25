"""027 moovin stores

Revision ID: 027
Revises: 026
Create Date: 2026-06-25
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "027"
down_revision: Union[str, None] = "026"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "moovin_stores",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("store_id", sa.Text, nullable=False, unique=True),
        sa.Column("display_name", sa.Text, nullable=True),
        sa.Column("api_key", sa.Text, nullable=False),
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
    op.create_index("idx_moovin_stores_id", "moovin_stores", ["store_id"])


def downgrade() -> None:
    op.drop_index("idx_moovin_stores_id", table_name="moovin_stores")
    op.drop_table("moovin_stores")
