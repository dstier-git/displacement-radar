from __future__ import annotations

from functools import lru_cache

from .apollo import ApolloClient
from .campaign import CampaignGenerator, OpportunityScorer
from .claude_discovery import ClaudeCompetitorDiscovery
from .config import get_settings
from .gemini import GeminiReasoner
from .monitor import CompetitorMonitor
from .services import DisplacementAgent
from .storage import FirestoreStore, JsonStore, Repository


@lru_cache
def get_repository() -> Repository:
    settings = get_settings()
    if settings.firestore_database:
        return Repository(FirestoreStore(settings.google_cloud_project, settings.firestore_database))
    return Repository(JsonStore(settings.data_path))


@lru_cache
def get_competitor_discovery() -> ClaudeCompetitorDiscovery:
    settings = get_settings()
    return ClaudeCompetitorDiscovery(
        mcp_config=settings.claude_mcp_config,
        max_budget_usd=settings.claude_max_budget_usd,
        timeout_seconds=settings.claude_timeout_seconds,
    )


@lru_cache
def get_agent() -> DisplacementAgent:
    settings = get_settings()
    reasoner = GeminiReasoner(settings.google_cloud_project, settings.google_cloud_location, settings.vertex_model)
    return DisplacementAgent(
        repository=get_repository(),
        monitor=CompetitorMonitor(reasoner=reasoner, demo_mode=settings.demo_mode),
        apollo=ApolloClient(api_key=settings.apollo_api_key, demo_mode=settings.demo_mode),
        scorer=OpportunityScorer(),
        campaign_generator=CampaignGenerator(reasoner=reasoner),
    )
