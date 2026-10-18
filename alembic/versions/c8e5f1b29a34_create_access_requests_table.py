"""create access requests table

Revision ID: c8e5f1b29a34
Revises: 774d9b5f5300
Create Date: 2026-10-12 03:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c8e5f1b29a34"
down_revision: Union[str, None] = "774d9b5f5300"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "access_requests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("organization", sa.String(length=100), nullable=True),
        sa.Column("intended_use", sa.String(length=1000), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_access_requests_id"), "access_requests", ["id"], unique=False)
    op.create_index(op.f("ix_access_requests_email"), "access_requests", ["email"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_access_requests_email"), table_name="access_requests")
    op.drop_index(op.f("ix_access_requests_id"), table_name="access_requests")
    op.drop_table("access_requests")
