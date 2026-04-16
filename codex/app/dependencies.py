from __future__ import annotations

from functools import lru_cache

from .apollo import ApolloClient
from .campaign import CampaignGenerator, OpportunityScorer
from .claude_discovery import ClaudeCompetitorDiscovery
from .claude_signals import ClaudeSignalDiscovery
from .config import get_settings
from .gemini import GeminiReasoner
from .monitor import CompetitorMonitor
from .prospecting import ClaudeApolloProspector, OpenAIProspector
from .services import DisplacementAgent
from .storage import FirestoreStore, JsonStore, Repository


@lru_cache
def get_repository() -> Repository:
    settings = get_settings()
    if settings.firestore_database:
        return Repository(FirestoreStore(settings.google_cloud_project, settings.firestore_database))
    return Repository(JsonStore(settings.data_path, seed_path=settings.seed_data_path))


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
    prospector = None
    # Prefer Claude CLI + Apollo MCP when explicitly enabled.
    if settings.prefer_claude_mcp_prospecting:
        prospector = ClaudeApolloProspector(
            mcp_config=settings.claude_mcp_config,
            max_budget_usd=settings.claude_max_budget_usd,
            timeout_seconds=settings.claude_timeout_seconds,
        )
    elif settings.openai_api_key:
        prospector = OpenAIProspector(
            api_key=settings.openai_api_key,
            model=settings.openai_model,
            timeout_seconds=settings.claude_timeout_seconds,
        )
    else:
        prospector = ClaudeApolloProspector(
            mcp_config=settings.claude_mcp_config,
            max_budget_usd=settings.claude_max_budget_usd,
            timeout_seconds=settings.claude_timeout_seconds,
        )
    return DisplacementAgent(
        repository=get_repository(),
        monitor=CompetitorMonitor(
            reasoner=reasoner,
            demo_mode=settings.demo_mode,
            claude_signal_discovery=ClaudeSignalDiscovery(
                max_budget_usd=settings.claude_max_budget_usd,
                timeout_seconds=settings.claude_timeout_seconds,
            ),
        ),
        apollo=ApolloClient(api_key=settings.apollo_api_key, demo_mode=settings.demo_mode),
        scorer=OpportunityScorer(),
        prospector=prospector,
        prefer_claude_mcp_prospecting=settings.prefer_claude_mcp_prospecting,
        campaign_generator=CampaignGenerator(
            reasoner=reasoner,
            claude_runner=CampaignGenerator._run_claude if settings.claude_draft_emails else None,
            claude_mcp_config=settings.claude_mcp_config,
            claude_max_budget_usd=settings.claude_max_budget_usd,
            claude_timeout_seconds=settings.claude_timeout_seconds,
        ),
        max_competitors_per_scan=settings.max_competitors_per_scan,
        max_customers_per_competitor=settings.max_customers_per_competitor,
    )
