from unittest.mock import AsyncMock

import httpx
import pytest

from app.config import Settings
from app.keitaro import KeitaroClient
from app.schemas import CreateCampaignRequest


def request() -> CreateCampaignRequest:
    return CreateCampaignRequest(
        name="Mexico Beauty",
        geo_code="mx",
        offer_id=3749,
        domain_id=11,
        group_id=22,
        traffic_source_id=33,
    )


@pytest.mark.asyncio
async def test_create_campaign_creates_two_expected_streams():
    client = AsyncMock(spec=httpx.AsyncClient)
    client.request.side_effect = [
        AsyncMock(is_error=False, json=lambda: {"id": 101, "alias": "mexico-beauty-ab12"}),
        AsyncMock(is_error=False, json=lambda: {"id": 201, "name": "GEO MX → Google"}),
        AsyncMock(is_error=False, json=lambda: {"id": 202, "name": "Offer 3749"}),
    ]
    settings = Settings(KEITARO_API_KEY="secret", KEITARO_BASE_URL="https://tracker.test")
    async with KeitaroClient(settings, client) as api:
        campaign, streams = await api.create_campaign(request())

    assert campaign["id"] == 101
    assert [stream["id"] for stream in streams] == [201, 202]
    calls = client.request.await_args_list
    assert calls[0].args == ("POST", "/campaigns")
    assert calls[0].kwargs["json"]["domain_id"] == 11
    assert calls[0].kwargs["json"]["group_id"] == 22
    assert calls[0].kwargs["json"]["traffic_source_id"] == 33
    assert calls[1].kwargs["json"]["filters"] == [
        {"name": "country", "mode": "accept", "payload": ["MX"]}
    ]
    assert calls[1].kwargs["json"]["action_payload"] == "https://www.google.com"
    assert calls[2].kwargs["json"]["offers"] == [
        {"offer_id": 3749, "share": 100, "state": "active"}
    ]


@pytest.mark.asyncio
async def test_update_stream_offers_preserves_non_offer_settings():
    client = AsyncMock(spec=httpx.AsyncClient)
    client.request.return_value = AsyncMock(is_error=False, json=lambda: {"id": 201})
    settings = Settings(KEITARO_API_KEY="secret", KEITARO_BASE_URL="https://tracker.test")
    stream = {
        "id": 201,
        "campaign_id": 101,
        "type": "default",
        "name": "Offer stream",
        "position": 2,
        "schema": "landings",
        "action_type": "http",
        "action_payload": "https://example.test",
        "filters": [{"name": "country", "mode": "accept", "payload": ["MX"]}],
        "triggers": [{"action": "stop"}],
        "landings": [],
        "offers": [{"offer_id": 1, "share": 100}],
    }
    async with KeitaroClient(settings, client) as api:
        await api.update_stream_offers(
            stream, [{"offer_id": 2, "share": 100, "state": "active"}]
        )

    payload = client.request.await_args.kwargs["json"]
    assert payload["filters"] == stream["filters"]
    assert payload["triggers"] == stream["triggers"]
    assert payload["action_payload"] == stream["action_payload"]
    assert payload["offers"] == [{"offer_id": 2, "share": 100, "state": "active"}]


def test_request_normalizes_geo_and_rejects_invalid_code():
    assert request().geo_code == "MX"
    with pytest.raises(ValueError):
        CreateCampaignRequest(name="Test", geo_code="1!", offer_id=1)
