"""add local stream editor models

Revision ID: 0002_stream_editor
Revises: 0001_creation_log
"""

import sqlalchemy as sa

from alembic import op

revision = "0002_stream_editor"
down_revision = "0001_creation_log"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "managed_campaigns",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("keitaro_campaign_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("keitaro_campaign_id", name="uq_managed_campaigns_keitaro_id"),
    )
    op.create_index(
        "ix_managed_campaigns_keitaro_campaign_id",
        "managed_campaigns",
        ["keitaro_campaign_id"],
    )

    op.create_table(
        "managed_streams",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("keitaro_stream_id", sa.Integer(), nullable=False),
        sa.Column("campaign_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("has_pending_changes", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_snapshot", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["campaign_id"], ["managed_campaigns.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("keitaro_stream_id", name="uq_managed_streams_keitaro_id"),
    )
    op.create_index(
        "ix_managed_streams_keitaro_stream_id",
        "managed_streams",
        ["keitaro_stream_id"],
    )
    op.create_index("ix_managed_streams_campaign_id", "managed_streams", ["campaign_id"])

    op.create_table(
        "offers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("keitaro_offer_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=512), nullable=False),
        sa.UniqueConstraint("keitaro_offer_id", name="uq_offers_keitaro_id"),
    )
    op.create_index("ix_offers_keitaro_offer_id", "offers", ["keitaro_offer_id"])

    op.create_table(
        "stream_offers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("stream_id", sa.Integer(), nullable=False),
        sa.Column("offer_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("share", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_weight_pinned", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("pinned_share", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["stream_id"], ["managed_streams.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["offer_id"], ["offers.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("stream_id", "offer_id", name="uq_stream_offer"),
    )
    op.create_index("ix_stream_offers_stream_id", "stream_offers", ["stream_id"])
    op.create_index("ix_stream_offers_offer_id", "stream_offers", ["offer_id"])


def downgrade() -> None:
    op.drop_index("ix_stream_offers_offer_id", table_name="stream_offers")
    op.drop_index("ix_stream_offers_stream_id", table_name="stream_offers")
    op.drop_table("stream_offers")
    op.drop_index("ix_offers_keitaro_offer_id", table_name="offers")
    op.drop_table("offers")
    op.drop_index("ix_managed_streams_campaign_id", table_name="managed_streams")
    op.drop_index("ix_managed_streams_keitaro_stream_id", table_name="managed_streams")
    op.drop_table("managed_streams")
    op.drop_index("ix_managed_campaigns_keitaro_campaign_id", table_name="managed_campaigns")
    op.drop_table("managed_campaigns")
