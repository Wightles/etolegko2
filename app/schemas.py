from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class LookupItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: int
    name: str


class CreateCampaignRequest(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    geo_code: str = Field(min_length=2, max_length=8, description="ISO 3166-1 alpha-2 country code")
    offer_id: int = Field(gt=0)
    domain_id: int | None = Field(default=None, gt=0)
    group_id: int | None = Field(default=None, gt=0)
    traffic_source_id: int | None = Field(default=None, gt=0)
    google_url: str = Field(default="https://www.google.com", min_length=8, max_length=2048)

    @field_validator("geo_code")
    @classmethod
    def normalize_geo(cls, value: str) -> str:
        value = value.strip().upper()
        if not value.isalpha():
            raise ValueError("GEO-код должен содержать только латинские буквы")
        return value


class CreateCampaignResponse(BaseModel):
    campaign: dict[str, Any]
    streams: list[dict[str, Any]]
    campaign_url: str | None = None


class LookupResponse(BaseModel):
    offers: list[dict[str, Any]]
    domains: list[dict[str, Any]]
    groups: list[dict[str, Any]]
    traffic_sources: list[dict[str, Any]]
