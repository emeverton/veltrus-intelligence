"""031 kairos opt outs

Revision ID: 031
Revises: 030
Create Date: 2026-06-26
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "031"
down_revision: Union[str, None] = "030"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "kairos_opt_outs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "profile_id",
            UUID(as_uuid=True),
            sa.ForeignKey("identity_profiles.id"),
            nullable=True,
        ),
        sa.Column("email", sa.Text, nullable=True),
        sa.Column("phone", sa.Text, nullable=True),
        sa.Column("reason", sa.Text, nullable=True),
        sa.Column(
            "opted_out_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("profile_id", name="uq_opt_out_profile"),
    )
    op.create_index("idx_opt_out_email", "kairos_opt_outs", ["email"])
    op.create_index("idx_opt_out_phone", "kairos_opt_outs", ["phone"])


def downgrade() -> None:
    op.drop_index("idx_opt_out_phone", table_name="kairos_opt_outs")
    op.drop_index("idx_opt_out_email", table_name="kairos_opt_outs")
    op.drop_table("kairos_opt_outs")
