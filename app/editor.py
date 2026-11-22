from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.keitaro import KeitaroClient
from app.models import ManagedCampaign, ManagedStream, Offer, StreamOffer


class EditorError(RuntimeError):
    def __init__(self, message: str, *, status_code: int = 400, details: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.details = details


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _offer_id(link: StreamOffer) -> int:
    return link.offer.keitaro_offer_id


def _snapshot(stream: ManagedStream) -> list[dict[str, Any]]:
    return [
        {
            "offer_id": _offer_id(link),
            "name": link.offer.name,
            "status": link.status,
            "share": link.share,
            "is_weight_pinned": link.is_weight_pinned,
            "pinned_share": link.pinned_share,
        }
        for link in stream.offers
    ]


def _snapshot_key(snapshot: list[dict[str, Any]] | None) -> list[tuple[Any, ...]]:
    return sorted(
        (
            item.get("offer_id"),
            item.get("status", "active"),
            int(item.get("share", 0)),
            bool(item.get("is_weight_pinned", False)),
            item.get("pinned_share"),
        )
        for item in (snapshot or [])
    )


def refresh_pending(stream: ManagedStream) -> None:
    stream.has_pending_changes = _snapshot_key(_snapshot(stream)) != _snapshot_key(
        stream.published_snapshot
    )


def rebalance(stream: ManagedStream) -> None:
    active = [link for link in stream.offers if link.status == "active"]
    if not active:
        for link in stream.offers:
            link.share = 0
        return

    pinned = [link for link in active if link.is_weight_pinned]
    unpinned = [link for link in active if not link.is_weight_pinned]
    for link in pinned:
        if link.pinned_share is None:
            link.pinned_share = link.share

    pinned_sum = sum(int(link.pinned_share or 0) for link in pinned)
    if pinned_sum > 100:
        raise EditorError(
            "Сумма закреплённых весов не может быть "
            "больше 100%."
        )
    if not unpinned:
        if pinned_sum != 100:
            raise EditorError(
                "Нельзя распределить веса: все активные "
                "офферы закреплены, "
                f"а их сумма равна {pinned_sum}%."
            )
        for link in pinned:
            link.share = int(link.pinned_share or 0)
        return

    remaining = 100 - pinned_sum
    base, remainder = divmod(remaining, len(unpinned))
    for index, link in enumerate(unpinned):
        link.share = base + (1 if index < remainder else 0)
    for link in pinned:
        link.share = int(link.pinned_share or 0)


def validate_for_publish(stream: ManagedStream) -> list[StreamOffer]:
    active = [link for link in stream.offers if link.status == "active"]
    if not active:
        raise EditorError(
            "Нельзя опубликовать поток без активных "
            "офферов."
        )
    if sum(link.share for link in active) != 100:
        raise EditorError(
            "Сумма долей активных офферов должна быть "
            "равна 100%."
        )
    if any(link.share < 0 or link.share > 100 for link in active):
        raise EditorError("Доля оффера должна быть от 0 до 100%.")
    return active


def _get_stream(db: Session, stream_id: int) -> ManagedStream:
    stream = db.scalar(
        select(ManagedStream).where(ManagedStream.keitaro_stream_id == stream_id)
    )
    if stream is None:
        raise EditorError(
            "Поток ещё не импортирован в локальную базу.",
            status_code=404,
        )
    return stream


def _get_or_create_offer(db: Session, keitaro_offer_id: int, name: str) -> Offer:
    offer = db.scalar(select(Offer).where(Offer.keitaro_offer_id == keitaro_offer_id))
    if offer is None:
        offer = Offer(
            keitaro_offer_id=keitaro_offer_id,
            name=name or f"Оффер #{keitaro_offer_id}",
        )
        db.add(offer)
        db.flush()
    elif name and offer.name != name:
        offer.name = name
    return offer


def _remote_offer_id(item: dict[str, Any]) -> int | None:
    value = item.get("offer_id", item.get("id"))
    return int(value) if isinstance(value, (int, str)) and str(value).isdigit() else None


def _stream_payload(stream: ManagedStream) -> dict[str, Any]:
    return {
        "id": stream.keitaro_stream_id,
        "name": stream.name,
        "has_pending_changes": stream.has_pending_changes,
        "offers": [
            {
                "id": link.id,
                "offer_id": _offer_id(link),
                "name": link.offer.name,
                "status": link.status,
                "share": link.share if link.status == "active" else 0,
                "is_weight_pinned": link.is_weight_pinned,
                "pinned_share": link.pinned_share,
            }
            for link in stream.offers
        ],
        "published_snapshot": stream.published_snapshot,
        "last_synced_at": stream.last_synced_at.isoformat() if stream.last_synced_at else None,
        "last_published_at": (
            stream.last_published_at.isoformat() if stream.last_published_at else None
        ),
    }


def campaign_payload(campaign: ManagedCampaign) -> dict[str, Any]:
    return {
        "id": campaign.keitaro_campaign_id,
        "name": campaign.name,
        "streams": [_stream_payload(stream) for stream in campaign.streams],
    }


def _restore_snapshot(db: Session, stream: ManagedStream) -> None:
    by_offer_id = {link.offer.keitaro_offer_id: link for link in stream.offers}
    snapshot = stream.published_snapshot or []
    snapshot_ids = set()
    for item in snapshot:
        offer_id = int(item["offer_id"])
        snapshot_ids.add(offer_id)
        link = by_offer_id.get(offer_id)
        if link is None:
            offer = Offer(
                keitaro_offer_id=offer_id,
                name=item.get("name") or f"Оффер #{offer_id}",
            )
            db.add(offer)
            db.flush()
            link = StreamOffer(stream=stream, offer=offer)
            db.add(link)
        link.status = item.get("status", "active")
        link.share = int(item.get("share", 0))
        link.is_weight_pinned = bool(item.get("is_weight_pinned", False))
        link.pinned_share = item.get("pinned_share")
    for link in list(stream.offers):
        if link.offer.keitaro_offer_id not in snapshot_ids:
            stream.offers.remove(link)
    stream.has_pending_changes = False


def cancel_stream(db: Session, stream_id: int) -> ManagedStream:
    stream = _get_stream(db, stream_id)
    if stream.published_snapshot is None:
        stream.offers.clear()
        stream.has_pending_changes = False
        return stream
    _restore_snapshot(db, stream)
    return stream


def _sync_stream_from_remote(
    db: Session,
    stream: ManagedStream,
    remote: dict[str, Any],
    offer_catalog: dict[int, dict[str, Any]],
) -> None:
    old_links = {link.offer.keitaro_offer_id: link for link in stream.offers}
    remote_ids: set[int] = set()
    for item in remote.get("offers") or []:
        offer_id = _remote_offer_id(item)
        if offer_id is None:
            continue
        remote_ids.add(offer_id)
        catalog_item = offer_catalog.get(offer_id, {})
        old_link = old_links.get(offer_id)
        name = str(
            catalog_item.get("name")
            or (old_link.offer.name if old_link is not None else f"Оффер #{offer_id}")
        )
        offer = _get_or_create_offer(db, offer_id, name)
        link = old_links.get(offer_id)
        if link is None:
            link = StreamOffer(stream=stream, offer=offer)
            db.add(link)
        link.status = "active"
        link.share = int(item.get("share") or 0)
        if link.is_weight_pinned:
            link.pinned_share = link.share

    for link in stream.offers:
        if link.offer.keitaro_offer_id not in remote_ids:
            link.status = "removed"
            link.share = 0

    stream.name = str(remote.get("name") or stream.name)
    stream.last_synced_at = utcnow()
    stream.has_pending_changes = False
    db.flush()
    stream.published_snapshot = _snapshot(stream)


async def fetch_campaign(
    db: Session, client: KeitaroClient, campaign_id: int, *, discard_pending: bool = False
) -> ManagedCampaign:
    remote_campaign, remote_streams, remote_offers = await _fetch_remote_campaign(
        client, campaign_id
    )
    campaign = db.scalar(
        select(ManagedCampaign).where(ManagedCampaign.keitaro_campaign_id == campaign_id)
    )
    pending_streams = (
        [stream for stream in campaign.streams if stream.has_pending_changes]
        if campaign
        else []
    )
    if pending_streams and not discard_pending:
        raise EditorError(
            "Есть неопубликованные изменения. Сначала "
            "нажми Cancel или подтверди сброс черновика.",
            status_code=409,
            details={
                "stream_ids": [stream.keitaro_stream_id for stream in pending_streams]
            },
        )
    if campaign is None:
        campaign = ManagedCampaign(
            keitaro_campaign_id=campaign_id,
            name=str(remote_campaign.get("name") or f"Кампания #{campaign_id}"),
        )
        db.add(campaign)
        db.flush()
    else:
        campaign.name = str(remote_campaign.get("name") or campaign.name)
        if discard_pending:
            for stream in pending_streams:
                _restore_snapshot(db, stream)

    offer_catalog = {
        int(item["id"]): item
        for item in remote_offers
        if isinstance(item.get("id"), (int, str)) and str(item["id"]).isdigit()
    }
    local_by_kt_id = {stream.keitaro_stream_id: stream for stream in campaign.streams}
    for remote_stream in remote_streams:
        stream_id = int(remote_stream["id"])
        stream = local_by_kt_id.get(stream_id)
        if stream is None:
            stream = ManagedStream(
                keitaro_stream_id=stream_id,
                campaign=campaign,
                name=str(remote_stream.get("name") or f"Поток #{stream_id}"),
            )
            db.add(stream)
            db.flush()
        _sync_stream_from_remote(db, stream, remote_stream, offer_catalog)
    db.flush()
    return campaign


async def _fetch_remote_campaign(
    client: KeitaroClient, campaign_id: int
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    import asyncio

    remote_campaign, streams, offers = await asyncio.gather(
        client.get_campaign(campaign_id),
        client.get_campaign_streams(campaign_id),
        client.list_offers(),
    )
    return remote_campaign, streams, offers


async def add_offer(
    db: Session, client: KeitaroClient, stream_id: int, offer_id: int
) -> ManagedStream:
    stream = _get_stream(db, stream_id)
    existing = next(
        (link for link in stream.offers if link.offer.keitaro_offer_id == offer_id), None
    )
    if existing and existing.status == "active":
        raise EditorError("Этот оффер уже добавлен в поток.")
    if existing is None:
        remote_offer = await client.get_offer(offer_id)
        offer = _get_or_create_offer(db, offer_id, str(remote_offer.get("name") or ""))
        existing = StreamOffer(stream=stream, offer=offer, status="active", share=0)
        db.add(existing)
    else:
        existing.status = "active"
    rebalance(stream)
    refresh_pending(stream)
    return stream


def remove_offer(db: Session, stream_id: int, offer_id: int) -> ManagedStream:
    stream = _get_stream(db, stream_id)
    link = next(
        (link for link in stream.offers if link.offer.keitaro_offer_id == offer_id), None
    )
    if link is None or link.status != "active":
        raise EditorError(
            "Активная привязка этого оффера не найдена."
        )
    link.status = "removed"
    link.share = 0
    rebalance(stream)
    refresh_pending(stream)
    return stream


def bring_back_offer(db: Session, stream_id: int, offer_id: int) -> ManagedStream:
    stream = _get_stream(db, stream_id)
    link = next(
        (link for link in stream.offers if link.offer.keitaro_offer_id == offer_id), None
    )
    if link is None or link.status != "removed":
        raise EditorError(
            "Удалённая привязка этого оффера не найдена."
        )
    link.status = "active"
    link.share = link.pinned_share if link.is_weight_pinned and link.pinned_share else 0
    rebalance(stream)
    refresh_pending(stream)
    return stream


def pin_offer(db: Session, stream_id: int, offer_id: int, pinned: bool) -> ManagedStream:
    stream = _get_stream(db, stream_id)
    link = next(
        (link for link in stream.offers if link.offer.keitaro_offer_id == offer_id), None
    )
    if link is None or link.status != "active":
        raise EditorError("Закрепить можно только активный оффер.")
    link.is_weight_pinned = pinned
    link.pinned_share = link.share if pinned else None
    rebalance(stream)
    refresh_pending(stream)
    return stream


async def push_stream(db: Session, client: KeitaroClient, stream_id: int) -> ManagedStream:
    stream = _get_stream(db, stream_id)
    active = validate_for_publish(stream)
    remote = await client.get_stream(stream.keitaro_stream_id)
    payload = [
        {"offer_id": _offer_id(link), "share": link.share, "state": "active"}
        for link in active
    ]
    await client.update_stream_offers(remote, payload)
    updated = await client.get_stream(stream.keitaro_stream_id)
    catalog = {
        int(item["id"]): item
        for item in await client.list_offers()
        if isinstance(item.get("id"), (int, str)) and str(item["id"]).isdigit()
    }
    _sync_stream_from_remote(db, stream, updated, catalog)
    stream.last_published_at = utcnow()
    stream.has_pending_changes = False
    db.flush()
    return stream


async def search_offers(client: KeitaroClient, query: str) -> list[dict[str, Any]]:
    items = await client.list_offers()
    query = query.strip().lower()
    if not query:
        return items[:20]
    return [
        item
        for item in items
        if query in str(item.get("id", "")).lower()
        or query in str(item.get("name", "")).lower()
    ][:20]
