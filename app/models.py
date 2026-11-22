from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class CampaignCreationLog(Base):
    __tablename__ = "campaign_creation_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    campaign_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    geo_code: Mapped[str] = mapped_column(String(8), nullable=False)
    offer_id: Mapped[int] = mapped_column(Integer, nullable=False)
    request_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    response_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )


class ManagedCampaign(Base):
    __tablename__ = "managed_campaigns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    keitaro_campaign_id: Mapped[int] = mapped_column(
        Integer, unique=True, index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    streams: Mapped[list["ManagedStream"]] = relationship(
        back_populates="campaign", cascade="all, delete-orphan", order_by="ManagedStream.id"
    )


class ManagedStream(Base):
    __tablename__ = "managed_streams"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    keitaro_stream_id: Mapped[int] = mapped_column(Integer, unique=True, index=True, nullable=False)
    campaign_id: Mapped[int] = mapped_column(
        ForeignKey("managed_campaigns.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    has_pending_changes: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    published_snapshot: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)

    campaign: Mapped[ManagedCampaign] = relationship(back_populates="streams")
    offers: Mapped[list["StreamOffer"]] = relationship(
        back_populates="stream", cascade="all, delete-orphan", order_by="StreamOffer.id"
    )


class Offer(Base):
    __tablename__ = "offers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    keitaro_offer_id: Mapped[int] = mapped_column(Integer, unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(512), nullable=False)

    stream_links: Mapped[list["StreamOffer"]] = relationship(back_populates="offer")


class StreamOffer(Base):
    __tablename__ = "stream_offers"
    __table_args__ = (UniqueConstraint("stream_id", "offer_id", name="uq_stream_offer"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    stream_id: Mapped[int] = mapped_column(
        ForeignKey("managed_streams.id", ondelete="CASCADE"), nullable=False, index=True
    )
    offer_id: Mapped[int] = mapped_column(
        ForeignKey("offers.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False)
    share: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_weight_pinned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    pinned_share: Mapped[int | None] = mapped_column(Integer, nullable=True)

    stream: Mapped[ManagedStream] = relationship(back_populates="offers")
    offer: Mapped[Offer] = relationship(back_populates="stream_links")
