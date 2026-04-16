from pathlib import Path

from app.apollo import ApolloClient
from app.campaign import CampaignGenerator, OpportunityScorer
from app.demo_data import demo_contacts
from app.gemini import GeminiReasoner
from app.models import ApolloAccount, Competitor, Severity, SignalType, SourceEvidence
from app.monitor import CompetitorMonitor
from app.services import DisplacementAgent
from app.storage import JsonStore, Repository


def make_agent(tmp_path: Path) -> DisplacementAgent:
    reasoner = GeminiReasoner(project=None, location="global", model="test-model")
    return DisplacementAgent(
        repository=Repository(JsonStore(tmp_path / "store.json")),
        monitor=CompetitorMonitor(reasoner=reasoner, demo_mode=True),
        apollo=ApolloClient(api_key="test", demo_mode=True),
        scorer=OpportunityScorer(),
        campaign_generator=CampaignGenerator(reasoner=reasoner),
    )


def test_classifier_detects_price_increase() -> None:
    reasoner = GeminiReasoner(project=None, location="global", model="test-model")
    competitor = Competitor(name="AcmeCRM")
    signal = reasoner.classify_signal(
        competitor,
        SourceEvidence(title="AcmeCRM announces pricing increase", url="https://example.com", snippet="Customers complain about renewal cost"),
    )

    assert signal.type == SignalType.PRICE_INCREASE
    assert signal.severity == Severity.HIGH
    assert "renewal" in signal.pain_hypothesis


def test_apollo_query_plan_uses_technology_uid_and_persona_titles() -> None:
    client = ApolloClient(api_key="test", demo_mode=True)
    competitor = Competitor(name="AcmeCRM", category="Sales engagement", technology_uid="tech-123")
    signal = CompetitorMonitor(GeminiReasoner(None, "global", "test"), demo_mode=True).discover_signals(competitor)[0]

    plan = client.build_query_plan(competitor, signal)

    assert plan.organization_payload["currently_using_any_of_technology_uids"] == ["tech-123"]
    assert "AcmeCRM" in plan.organization_payload["q_keywords"]
    assert "Revenue Operations" in plan.people_payload["person_titles"]


def test_campaign_prompt_is_draft_only() -> None:
    reasoner = GeminiReasoner(project=None, location="global", model="test-model")
    competitor = Competitor(name="AcmeCRM")
    signal = CompetitorMonitor(reasoner, demo_mode=True).discover_signals(competitor)[0]
    account = ApolloAccount(name="Northstar", domain="northstar.example", technologies=["AcmeCRM"], employee_count=500)
    contacts = demo_contacts(account)
    opportunity = OpportunityScorer().score(signal, account, contacts)
    campaign = CampaignGenerator(reasoner).generate(signal, opportunity)

    assert "Do not create contacts" in campaign.apollo_claude_prompt
    assert "draft/review mode" in campaign.apollo_claude_prompt
    assert "Source:" in campaign.email_body


def test_scan_creates_and_dedupes_pipeline_artifacts(tmp_path: Path) -> None:
    agent = make_agent(tmp_path)
    agent.add_competitor("AcmeCRM", "Sales engagement", customer_domains=["northstar.example", "orbit.example"])

    first = agent.run_scan()
    second = agent.run_scan()

    assert first.signals_created == 1
    assert first.opportunities_created == 2
    assert first.campaigns_created == 2
    assert second.signals_created == 0
    assert second.opportunities_created == 0
    assert second.campaigns_created == 0
    assert len(agent.repository.list_campaigns()) == 2
