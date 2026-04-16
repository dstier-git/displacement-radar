from pathlib import Path

from fastapi.testclient import TestClient

from app.apollo import ApolloClient
from app.campaign import CampaignGenerator, OpportunityScorer
from app.claude_discovery import DiscoveryResult
from app.dependencies import get_agent, get_competitor_discovery, get_repository
from app.gemini import GeminiReasoner
from app.main import app
from app.models import CompanyProfile, Competitor
from app.monitor import CompetitorMonitor
from app.services import DisplacementAgent
from app.storage import JsonStore, Repository


class FakeDiscovery:
    def discover(self, company_name: str) -> DiscoveryResult:
        return DiscoveryResult(
            company=CompanyProfile(company_name=company_name, category="Sales intelligence"),
            competitors=[
                Competitor(
                    name="AcmeCRM",
                    category="Sales engagement",
                    customer_domains=["northstar.example"],
                )
            ],
            source="claude",
        )


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


def test_dashboard_company_scan_email_and_report_routes(tmp_path: Path) -> None:
    agent = build_test_agent(tmp_path)
    app.dependency_overrides[get_agent] = lambda: agent
    app.dependency_overrides[get_repository] = lambda: agent.repository
    app.dependency_overrides[get_competitor_discovery] = lambda: FakeDiscovery()

    try:
        client = TestClient(app)
        assert client.get("/healthz").json() == {"status": "ok"}

        setup = client.post("/company/discover", data={"company_name": "Apollo"}, follow_redirects=False)
        assert setup.status_code == 303
        assert agent.repository.get_company_profile().company_name == "Apollo"  # type: ignore[union-attr]
        assert [competitor.name for competitor in agent.repository.list_competitors()] == ["AcmeCRM"]

        response = client.post("/scan", follow_redirects=False)
        assert response.status_code == 303

        dashboard = client.get("/")
        assert dashboard.status_code == 200
        assert "Company-first setup" in dashboard.text
        assert "Email drafts" in dashboard.text
        assert "/reports/competitive-landscape" in dashboard.text

        opportunity = agent.repository.list_opportunities()[0]
        prospects = client.post(f"/opportunities/{opportunity.id}/prospects", follow_redirects=False)
        assert prospects.status_code == 303
        opportunity = agent.repository.get_opportunity(opportunity.id)
        assert opportunity and opportunity.contacts

        email = client.post(
            f"/opportunities/{opportunity.id}/emails",
            data={"contact_ids": [opportunity.contacts[0].id]},
            follow_redirects=False,
        )
        assert email.status_code == 303
        campaign = agent.repository.list_campaigns()[0]
        assert campaign.contact == opportunity.contacts[0]
        assert "15-minute" in campaign.email_body

        rendered_report = client.get("/reports/competitive-landscape")
        assert rendered_report.status_code == 200
        assert "Rendered competitive landscape report" in rendered_report.text
        assert 'class="rendered-graph flow-graph"' in rendered_report.text

        report = client.get("/reports/competitive-landscape.md")
        assert report.status_code == 200
        assert "# Competitive Landscape Report" in report.text
        assert "```mermaid" in report.text

        prompt = client.post(f"/campaigns/{campaign.id}/apollo-claude-prompt")
        assert prompt.status_code == 200
        assert "Do not create contacts" in prompt.text
    finally:
        app.dependency_overrides.clear()
