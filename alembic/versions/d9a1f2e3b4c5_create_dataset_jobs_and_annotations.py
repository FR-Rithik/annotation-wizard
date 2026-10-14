"""create dataset jobs and annotations tables

Revision ID: d9a1f2e3b4c5
Revises: c8e5f1b29a34
Create Date: 2026-10-12 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d9a1f2e3b4c5"
down_revision: Union[str, None] = "c8e5f1b29a34"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "dataset_jobs",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("client_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=True),
        sa.Column("total_images", sa.Integer(), nullable=True),
        sa.Column("reviewed_images", sa.Integer(), nullable=True),
        sa.Column("total_annotations", sa.Integer(), nullable=True),
        sa.Column("storage_dir", sa.String(length=500), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["client_id"], ["api_clients.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_dataset_jobs_id"), "dataset_jobs", ["id"], unique=False)

    op.create_table(
        "dataset_images",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("job_id", sa.String(length=64), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("relative_path", sa.String(length=500), nullable=False),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=True),
        sa.Column("order_index", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["job_id"], ["dataset_jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_dataset_images_id"), "dataset_images", ["id"], unique=False)
    op.create_index(op.f("ix_dataset_images_job_id"), "dataset_images", ["job_id"], unique=False)

    op.create_table(
        "annotations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("image_id", sa.Integer(), nullable=False),
        sa.Column("class_id", sa.Integer(), nullable=False),
        sa.Column("class_name", sa.String(length=50), nullable=False),
        sa.Column("x_min", sa.Float(), nullable=False),
        sa.Column("y_min", sa.Float(), nullable=False),
        sa.Column("x_max", sa.Float(), nullable=False),
        sa.Column("y_max", sa.Float(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("is_prediction", sa.Boolean(), nullable=True),
        sa.Column("is_modified", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["image_id"], ["dataset_images.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_annotations_id"), "annotations", ["id"], unique=False)
    op.create_index(op.f("ix_annotations_image_id"), "annotations", ["image_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_annotations_image_id"), table_name="annotations")
    op.drop_index(op.f("ix_annotations_id"), table_name="annotations")
    op.drop_table("annotations")

    op.drop_index(op.f("ix_dataset_images_job_id"), table_name="dataset_images")
    op.drop_index(op.f("ix_dataset_images_id"), table_name="dataset_images")
    op.drop_table("dataset_images")

    op.drop_index(op.f("ix_dataset_jobs_id"), table_name="dataset_jobs")
    op.drop_table("dataset_jobs")
