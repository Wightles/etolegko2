from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.editor import bring_back_offer, pin_offer, rebalance, remove_offer, validate_for_publish
from app.models import ManagedCampaign, ManagedStream, Offer, StreamOffer


def make_stream() -> tuple[Session, ManagedStream]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    campaign = ManagedCampaign(keitaro_campaign_id=1, name="Test campaign")
    stream = ManagedStream(keitaro_stream_id=10, name="Offer stream", campaign=campaign)
    for index in range(3):
        offer = Offer(keitaro_offer_id=100 + index, name=f"Offer {index}")
        stream.offers.append(StreamOffer(offer=offer, status="active", share=33))
    session.add(campaign)
    session.flush()
    rebalance(stream)
    stream.published_snapshot = [
        {
            "offer_id": link.offer.keitaro_offer_id,
            "name": link.offer.name,
            "status": link.status,
            "share": link.share,
            "is_weight_pinned": link.is_weight_pinned,
            "pinned_share": link.pinned_share,
        }
        for link in stream.offers
    ]
    session.commit()
    return session, stream


def test_add_like_rebalance_keeps_total_at_100():
    session, stream = make_stream()
    stream.offers.append(
        StreamOffer(
            offer=Offer(keitaro_offer_id=103, name="Offer 3"), status="active", share=0
        )
    )
    rebalance(stream)
    assert [link.share for link in stream.offers] == [25, 25, 25, 25]
    assert sum(link.share for link in stream.offers) == 100
    validate_for_publish(stream)
    session.close()


def test_remove_and_bring_back_archive_the_binding():
    session, stream = make_stream()
    remove_offer(session, stream.keitaro_stream_id, 100)
    removed = next(link for link in stream.offers if link.offer.keitaro_offer_id == 100)
    assert removed.status == "removed"
    assert removed.share == 0
    assert sum(link.share for link in stream.offers if link.status == "active") == 100

    bring_back_offer(session, stream.keitaro_stream_id, 100)
    restored = next(link for link in stream.offers if link.offer.keitaro_offer_id == 100)
    assert restored.status == "active"
    assert sum(link.share for link in stream.offers if link.status == "active") == 100
    session.close()


def test_pinned_weight_is_not_changed_by_rebalance():
    session, stream = make_stream()
    pin_offer(session, stream.keitaro_stream_id, 100, True)
    pinned = next(link for link in stream.offers if link.offer.keitaro_offer_id == 100)
    assert pinned.share == 34
    assert pinned.pinned_share == 34

    remove_offer(session, stream.keitaro_stream_id, 101)
    assert pinned.share == 34
    assert sum(link.share for link in stream.offers if link.status == "active") == 100
    session.close()
