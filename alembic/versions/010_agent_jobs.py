"""010 agent jobs

Revision ID: 010
Revises: 009
Create Date: 2026-06-23
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_jobs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("task", sa.Text, nullable=False),
        sa.Column("context", JSONB, nullable=False, server_default="{}"),
        sa.Column("status", sa.Text, nullable=False, server_default="pending"),
        sa.Column("result", JSONB, nullable=True),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_jobs_status", "agent_jobs", ["status"])
    op.create_index("idx_jobs_created", "agent_jobs", ["created_at"])


def downgrade() -> None:
    op.drop_index("idx_jobs_created", table_name="agent_jobs")
    op.drop_index("idx_jobs_status", table_name="agent_jobs")
    op.drop_table("agent_jobs")
