"""011 generation jobs

Revision ID: 011
Revises: 010
Create Date: 2026-06-23
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "generation_jobs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("job_type", sa.Text, nullable=False),
        sa.Column("prompt", sa.Text, nullable=True),
        sa.Column("status", sa.Text, nullable=False, server_default="pending"),
        sa.Column("result_data", JSONB, nullable=True),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("gpu_used", sa.Boolean, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_gen_type", "generation_jobs", ["job_type"])
    op.create_index("idx_gen_status", "generation_jobs", ["status"])


def downgrade() -> None:
    op.drop_index("idx_gen_status", table_name="generation_jobs")
    op.drop_index("idx_gen_type", table_name="generation_jobs")
    op.drop_table("generation_jobs")
