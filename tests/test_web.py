from pathlib import Path

from fastapi.testclient import TestClient

from app.apollo import ApolloClient
from app.campaign import CampaignGenerator, OpportunityScorer
from app.dependencies import get_agent, get_repository
from app.gemini import GeminiReasoner
from app.main import app
from app.monitor import CompetitorMonitor
from app.services import DisplacementAgent
from app.storage import JsonStore, Repository


def build_test_agent(tmp_path: Path) -> DisplacementAgent:
    reasoner = GeminiReasoner(project=None, location="global", model="test-model")
    repo = Repository(JsonStore(tmp_path / "web-store.json"))
    return DisplacementAgent(
        repository=repo,
        monitor=CompetitorMonitor(reasoner=reasoner, demo_mode=True),
        apollo=ApolloClient(api_key="test", demo_mode=True),
        scorer=OpportunityScorer(),
        campaign_generator=CampaignGenerator(reasoner=reasoner),
    )


def test_dashboard_scan_and_prompt_routes(tmp_path: Path) -> None:
    agent = build_test_agent(tmp_path)
    agent.seed_demo_if_empty()
    app.dependency_overrides[get_agent] = lambda: agent
    app.dependency_overrides[get_repository] = lambda: agent.repository

    try:
        client = TestClient(app)
        assert client.get("/healthz").json() == {"status": "ok"}
        response = client.post("/scan", follow_redirects=False)
        assert response.status_code == 303

        dashboard = client.get("/")
        assert dashboard.status_code == 200
        assert "Campaign drafts" in dashboard.text
        assert "/reports/competitive-landscape" in dashboard.text

        rendered_report = client.get("/reports/competitive-landscape")
        assert rendered_report.status_code == 200
        assert "Rendered competitive landscape report" in rendered_report.text
        assert 'class="rendered-graph flow-graph"' in rendered_report.text

        report = client.get("/reports/competitive-landscape.md")
        assert report.status_code == 200
        assert "# Competitive Landscape Report" in report.text
        assert "```mermaid" in report.text

        campaign = agent.repository.list_campaigns()[0]
        prompt = client.post(f"/campaigns/{campaign.id}/apollo-claude-prompt")
        assert prompt.status_code == 200
        assert "Do not create contacts" in prompt.text
    finally:
        app.dependency_overrides.clear()
