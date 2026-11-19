from __future__ import annotations

import re
import uuid
from typing import Any

import httpx

from app.config import Settings
from app.schemas import CreateCampaignRequest


class KeitaroApiError(RuntimeError):
    def __init__(self, status_code: int, message: str, details: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.details = details


class KeitaroClient:
    def __init__(self, settings: Settings, http_client: httpx.AsyncClient | None = None):
        self.settings = settings
        self._http_client = http_client

    async def __aenter__(self) -> "KeitaroClient":
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                base_url=self._base_url,
                headers=self._headers,
                timeout=self.settings.keitaro_timeout_seconds,
            )
        return self

    async def __aexit__(self, *_: object) -> None:
        if self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None

    @property
    def _base_url(self) -> str:
        return f"{self.settings.keitaro_base_url.rstrip('/')}/admin_api/v1"

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Api-Key": self.settings.keitaro_api_key,
            "Authorization": f"Bearer {self.settings.keitaro_api_key}",
        }

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        if not self.settings.keitaro_api_key:
            raise KeitaroApiError(500, "Не задан KEITARO_API_KEY в .env")
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                base_url=self._base_url,
                headers=self._headers,
                timeout=self.settings.keitaro_timeout_seconds,
            )
        try:
            response = await self._http_client.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise KeitaroApiError(502, f"Keitaro недоступен: {exc}") from exc

        try:
            payload = response.json()
        except ValueError:
            payload = {"raw": response.text[:1000]}
        if response.is_error:
            detail = payload.get("message", payload) if isinstance(payload, dict) else payload
            raise KeitaroApiError(response.status_code, "Keitaro вернул ошибку", detail)
        return payload

    async def list_resources(self) -> dict[str, list[dict[str, Any]]]:
        offers, domains, groups, traffic_sources = await self._gather_resources()
        return {
            "offers": self._as_list(offers),
            "domains": self._as_list(domains),
            "groups": self._as_list(groups),
            "traffic_sources": self._as_list(traffic_sources),
        }

    async def _gather_resources(self) -> tuple[Any, Any, Any, Any]:
        import asyncio

        return await asyncio.gather(
            self._request("GET", "/offers"),
            self._request("GET", "/domains"),
            self._request("GET", "/groups", params={"type": "campaigns"}),
            self._request("GET", "/traffic_sources"),
        )

    async def create_campaign(self, data: CreateCampaignRequest) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        campaign_payload = {
            "alias": self._make_alias(data.name),
            "name": data.name.strip(),
            "type": "position",
            "state": "active",
            "cost_type": "CPC",
            "cost_value": 0,
            "cost_auto": False,
        }
        related_ids = {
            "domain_id": data.domain_id or self.settings.keitaro_default_domain_id,
            "group_id": data.group_id or self.settings.keitaro_default_group_id,
            "traffic_source_id": (
                data.traffic_source_id or self.settings.keitaro_default_traffic_source_id
            ),
        }
        missing = [field for field, value in related_ids.items() if value is None]
        if missing:
            labels = {
                "domain_id": "домен",
                "group_id": "группа",
                "traffic_source_id": "источник",
            }
            readable = ", ".join(labels[field] for field in missing)
            raise KeitaroApiError(422, f"Не выбраны обязательные настройки: {readable}")
        campaign_payload.update(related_ids)

        campaign = await self._request("POST", "/campaigns", json=campaign_payload)
        campaign_id = self._resource_id(campaign, "campaign")

        geo_stream_payload = {
            "campaign_id": campaign_id,
            "type": "regular",
            "schema": "redirect",
            "name": f"GEO {data.geo_code} → Google",
            "position": 1,
            "state": "active",
            "action_type": "http",
            "action_payload": data.google_url,
            "collect_clicks": True,
            "filters": [
                {
                    "name": self.settings.keitaro_geo_filter_name,
                    "mode": "accept",
                    "payload": [data.geo_code],
                }
            ],
        }
        offer_stream_payload = {
            "campaign_id": campaign_id,
            "type": "default",
            "schema": self.settings.keitaro_offer_stream_schema,
            "name": f"Offer {data.offer_id}",
            "position": 2,
            "state": "active",
            "action_type": "http",
            "collect_clicks": True,
            "offers": [{"offer_id": data.offer_id, "share": 100, "state": "active"}],
        }
        geo_stream = await self._request("POST", "/streams", json=geo_stream_payload)
        offer_stream = await self._request("POST", "/streams", json=offer_stream_payload)
        return campaign, [geo_stream, offer_stream]

    @staticmethod
    def _as_list(payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            for key in ("data", "items", "results"):
                if isinstance(payload.get(key), list):
                    return payload[key]
        return []

    @staticmethod
    def _resource_id(payload: Any, resource_name: str) -> int:
        if isinstance(payload, dict) and isinstance(payload.get("id"), int):
            return payload["id"]
        raise KeitaroApiError(502, f"Keitaro не вернул ID {resource_name}", payload)

    @staticmethod
    def _make_alias(name: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
        return f"{slug or 'campaign'}-{uuid.uuid4().hex[:8]}"
