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
    claude_mcp_config: str | None = Field(default=None, alias="CLAUDE_MCP_CONFIG")
    claude_max_budget_usd: float | None = Field(default=0.25, alias="CLAUDE_MAX_BUDGET_USD")
    claude_timeout_seconds: int = Field(default=45, alias="CLAUDE_TIMEOUT_SECONDS")
    claude_draft_emails: bool = Field(default=False, alias="CLAUDE_DRAFT_EMAILS")
    max_competitors_per_scan: int = Field(default=4, alias="MAX_COMPETITORS_PER_SCAN")
    max_customers_per_competitor: int = Field(default=5, alias="MAX_CUSTOMERS_PER_COMPETITOR")
    demo_mode: bool = Field(default=False, alias="DEMO_MODE")
    data_path: Path = Field(default=Path(".data/displacement-agent.json"), alias="DATA_PATH")

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
