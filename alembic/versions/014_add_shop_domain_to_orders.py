"""014 add shop domain to shopify orders

Revision ID: 014
Revises: 013
Create Date: 2026-06-24
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "014"
down_revision: Union[str, None] = "013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("shopify_orders", sa.Column("shop_domain", sa.Text, nullable=True))
    op.create_index("idx_shopify_orders_domain", "shopify_orders", ["shop_domain"])
    op.execute(
        "UPDATE shopify_orders SET shop_domain = 'mdadqp-ar.myshopify.com' "
        "WHERE shop_domain IS NULL"
    )


def downgrade() -> None:
    op.drop_index("idx_shopify_orders_domain", table_name="shopify_orders")
    op.drop_column("shopify_orders", "shop_domain")
