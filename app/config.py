from functools import lru_cache
from typing import Annotated, Any

from pydantic import BeforeValidator, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def empty_string_to_none(value: Any) -> Any:
    return None if value == "" else value


OptionalInt = Annotated[int | None, BeforeValidator(empty_string_to_none)]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    keitaro_base_url: str = Field("https://tlgk.host", validation_alias="KEITARO_BASE_URL")
    keitaro_api_key: str = Field("", validation_alias="KEITARO_API_KEY")
    keitaro_default_domain_id: OptionalInt = Field(None, validation_alias="KEITARO_DEFAULT_DOMAIN_ID")
    keitaro_default_group_id: OptionalInt = Field(None, validation_alias="KEITARO_DEFAULT_GROUP_ID")
    keitaro_default_traffic_source_id: OptionalInt = Field(
        None, validation_alias="KEITARO_DEFAULT_TRAFFIC_SOURCE_ID"
    )
    keitaro_offer_stream_schema: str = Field(
        "landings", validation_alias="KEITARO_OFFER_STREAM_SCHEMA"
    )
    keitaro_geo_filter_name: str = Field("country", validation_alias="KEITARO_GEO_FILTER_NAME")
    keitaro_timeout_seconds: float = Field(20, validation_alias="KEITARO_TIMEOUT_SECONDS")
    database_url: str = Field("sqlite:///./data/app.db", validation_alias="DATABASE_URL")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
