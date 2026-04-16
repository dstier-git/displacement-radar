from pathlib import Path

from app.apollo import ApolloClient
from app.campaign import CampaignGenerator, OpportunityScorer
from app.claude_discovery import ClaudeCompetitorDiscovery
from app.demo_data import demo_contacts
from app.gemini import GeminiReasoner
from app.models import ApolloAccount, CompanyProfile, Competitor, Severity, SignalType, SourceEvidence
from app.monitor import CompetitorMonitor
from app.prospecting import ClaudeApolloProspector
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
        SourceEvidence(
            title="AcmeCRM announces pricing increase",
            url="https://example.com",
            snippet="Customers complain about renewal cost",
        ),
    )

    assert signal.type == SignalType.PRICE_INCREASE
    assert signal.severity == Severity.HIGH
    assert "renewal" in signal.pain_hypothesis


def test_apollo_query_plan_uses_technology_uid_and_aahan_persona_titles() -> None:
    client = ApolloClient(api_key="test", demo_mode=True)
    competitor = Competitor(name="AcmeCRM", category="Sales engagement", technology_uid="tech-123")
    signal = CompetitorMonitor(GeminiReasoner(None, "global", "test"), demo_mode=True).discover_signals(competitor)[0]

    plan = client.build_query_plan(competitor, signal)

    assert plan.organization_payload["currently_using_any_of_technology_uids"] == ["tech-123"]
    assert "AcmeCRM" in plan.organization_payload["q_keywords"]
    assert "VP of Sales" in plan.people_payload["person_titles"]
    assert "Chief Revenue Officer" in plan.people_payload["person_titles"]


def test_claude_discovery_parses_company_and_competitors() -> None:
    def runner(_command: list[str], _prompt: str, _timeout: int) -> str:
        return """
        {"company":{"company_name":"Rippling","category":"HRIS","positioning":"Workforce platform"},
         "competitors":[{"name":"Workday","category":"HRIS","product_positioning":"Enterprise HR suite"}]}
        """

    result = ClaudeCompetitorDiscovery(runner=runner).discover("Rippling")

    assert result.source == "claude"
    assert result.company.company_name == "Rippling"
    assert result.company.category == "HRIS"
    assert result.company.positioning == "Workforce platform"
    assert [competitor.name for competitor in result.competitors] == ["Workday"]


def test_claude_discovery_falls_back_on_invalid_output() -> None:
    discovery = ClaudeCompetitorDiscovery(runner=lambda _command, _prompt, _timeout: "not json")

    result = discovery.discover("Apollo")

    assert result.source == "fallback"
    assert result.error
    assert len(result.competitors) >= 1


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


def test_prospecting_parser_maps_contacts_and_impact_summary() -> None:
    signal = CompetitorMonitor(GeminiReasoner(None, "global", "test"), demo_mode=True).discover_signals(
        Competitor(name="AcmeCRM")
    )[0]
    prospector = ClaudeApolloProspector(
        runner=lambda _command, _prompt, _timeout: """
        [{"company":"Northstar","domain":"northstar.example","industry":"Software","employee_count":500,
          "competitor_usage_confidence":"verified","impact_summary":"Budget pressure at renewal.",
          "source_notes":["Apollo technology match"],
          "contacts":[{"first_name":"Jordan","last_name":"Lee","title":"VP RevOps",
                       "email":"jordan@northstar.example","email_status":"verified"}]}]
        """
    )

    candidates = prospector.find_impacted_customers(
        signal,
        Competitor(name="AcmeCRM"),
        CompanyProfile(company_name="Apollo"),
    )

    assert len(candidates) == 1
    assert candidates[0].account.name == "Northstar"
    assert candidates[0].impact_summary == "Budget pressure at renewal."
    assert candidates[0].contacts[0].email == "jordan@northstar.example"
    assert candidates[0].source_notes == ["Apollo technology match"]


def test_production_impacted_customer_search_does_not_invent_without_apollo_or_claude(tmp_path: Path) -> None:
    reasoner = GeminiReasoner(project=None, location="global", model="test-model")
    repo = Repository(JsonStore(tmp_path / "prod-store.json"))
    agent = DisplacementAgent(
        repository=repo,
        monitor=CompetitorMonitor(reasoner=reasoner, demo_mode=True),
        apollo=ApolloClient(api_key=None, demo_mode=False),
        scorer=OpportunityScorer(),
        campaign_generator=CampaignGenerator(reasoner=reasoner),
        prospector=ClaudeApolloProspector(runner=lambda _command, _prompt, _timeout: "[]"),
    )
    competitor = Competitor(name="AcmeCRM", category="Sales engagement")
    repo.save_competitor(competitor)
    signal = CompetitorMonitor(reasoner, demo_mode=True).discover_signals(competitor)[0]
    repo.save_signal(signal)

    opportunities = agent.find_impacted_customers(signal.id)

    assert opportunities == []
    assert repo.list_opportunities(signal_id=signal.id) == []


def test_scan_creates_opportunities_then_generates_selected_decision_maker_emails(tmp_path: Path) -> None:
    agent = make_agent(tmp_path)
    agent.repository.save_company_profile(CompanyProfile(company_name="Apollo"))
    agent.add_competitor("AcmeCRM", "Sales engagement", customer_domains=["northstar.example", "orbit.example"])

    first = agent.run_scan()
    second = agent.run_scan()

    assert first.signals_created == 1
    assert first.opportunities_created == 2
    assert first.campaigns_created == 0
    assert second.signals_created == 0
    assert second.opportunities_created == 0
    assert second.campaigns_created == 0
    assert len(agent.repository.list_campaigns()) == 0

    opportunity = agent.repository.list_opportunities()[0]
    assert opportunity.impact_summary
    assert opportunity.primary_contact_id
    assert opportunity.competitor_usage_confidence == "verified"
    contacts = agent.find_decision_makers(opportunity.id)
    drafts = agent.generate_emails_for_contacts(opportunity.id, [contacts[0].id or contacts[0].full_name])

    assert len(drafts) == 1
    draft = drafts[0]
    assert draft.contact == contacts[0]
    assert "15-minute" in draft.email_body
    assert "Apollo" in draft.email_body.split(".")[-2]
    assert len(draft.email_body.split()) < 100
