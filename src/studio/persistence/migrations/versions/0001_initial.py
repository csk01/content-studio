"""initial Phase 0 schema

Revision ID: 0001
Revises:
"""
import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "connected_account",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("platform", sa.String(32), nullable=False),
        sa.Column("account_key", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("platform", "account_key"),
    )
    op.create_table(
        "post",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("caption", sa.Text, nullable=False),
        sa.Column("media_path", sa.Text, nullable=False),
        sa.Column("media_size", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "publish_target",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("post_id", sa.String(32), sa.ForeignKey("post.id"), nullable=False),
        sa.Column(
            "account_id", sa.String(32), sa.ForeignKey("connected_account.id"), nullable=False
        ),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("platform_post_id", sa.String(128), nullable=True),
        sa.Column("url", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "publish_attempt",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("target_id", sa.String(32), sa.ForeignKey("publish_target.id"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("outcome", sa.String(32), nullable=True),
        sa.Column("error_kind", sa.String(64), nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
    )


def downgrade() -> None:
    op.drop_table("publish_attempt")
    op.drop_table("publish_target")
    op.drop_table("post")
    op.drop_table("connected_account")
