"""create urls, tags and clicks tables

Revision ID: 43ca2d65d774
Revises: 76c834f8c667
Create Date: 2026-11-15 10:18:59.949991

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "43ca2d65d774"
down_revision = "76c834f8c667"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "tags",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tags")),
        sa.UniqueConstraint("name", name=op.f("uq_tags_name")),
    )
    op.create_table(
        "urls",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("original_url", sa.String(length=2083), nullable=False),
        sa.Column("short_code", sa.String(length=10), nullable=False),
        sa.Column("custom_alias", sa.String(length=50), nullable=True),
        sa.Column("owner_id", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("description", sa.String(length=1000), nullable=True),
        sa.Column("favicon", sa.String(length=2083), nullable=True),
        sa.Column("click_count", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "click_count >= 0", name=op.f("ck_urls_click_count_positive")
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
            name=op.f("fk_urls_owner_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_urls")),
        sa.UniqueConstraint("custom_alias", name=op.f("uq_urls_custom_alias")),
    )
    op.create_index(op.f("ix_urls_created_at"), "urls", ["created_at"], unique=False)
    op.create_index(op.f("ix_urls_owner_id"), "urls", ["owner_id"], unique=False)
    op.create_index(op.f("ix_urls_short_code"), "urls", ["short_code"], unique=True)
    op.create_table(
        "clicks",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("url_id", sa.Integer(), nullable=False),
        sa.Column(
            "clicked_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("ip_address", postgresql.INET(), nullable=False),
        sa.Column("city", sa.String(length=100), nullable=True),
        sa.Column("country", sa.String(length=2), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=False),
        sa.Column("referrer", sa.String(length=2083), nullable=True),
        sa.ForeignKeyConstraint(
            ["url_id"],
            ["urls.id"],
            name=op.f("fk_clicks_url_id_urls"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_clicks")),
    )
    op.create_index(
        "ix_clicks_url_id_clicked_at", "clicks", ["url_id", "clicked_at"], unique=False
    )
    op.create_table(
        "url_tags",
        sa.Column("url_id", sa.Integer(), nullable=False),
        sa.Column("tag_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tag_id"],
            ["tags.id"],
            name=op.f("fk_url_tags_tag_id_tags"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["url_id"],
            ["urls.id"],
            name=op.f("fk_url_tags_url_id_urls"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("url_id", "tag_id", name=op.f("pk_url_tags")),
    )


def downgrade():
    op.drop_table("url_tags")
    op.drop_index("ix_clicks_url_id_clicked_at", table_name="clicks")
    op.drop_table("clicks")
    op.drop_index(op.f("ix_urls_short_code"), table_name="urls")
    op.drop_index(op.f("ix_urls_owner_id"), table_name="urls")
    op.drop_index(op.f("ix_urls_created_at"), table_name="urls")
    op.drop_table("urls")
    op.drop_table("tags")
