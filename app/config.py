from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Competitor Displacement Agent"
    apollo_api_key: str | None = Field(default=None, alias="APOLLO_API_KEY")
    google_cloud_project: str | None = Field(default=None, alias="GOOGLE_CLOUD_PROJECT")
    google_cloud_location: str = Field(default="global", alias="GOOGLE_CLOUD_LOCATION")
    vertex_model: str = Field(default="gemini-2.5-flash", alias="VERTEX_MODEL")
    firestore_database: str | None = Field(default=None, alias="FIRESTORE_DATABASE")
    scheduler_shared_secret: str | None = Field(default=None, alias="SCHEDULER_SHARED_SECRET")
    demo_mode: bool = Field(default=True, alias="DEMO_MODE")
    data_path: Path = Field(default=Path(".data/displacement-agent.json"), alias="DATA_PATH")

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
