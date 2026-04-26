from pathlib import Path

import httpx

from app.apollo import ApolloClient
from app.campaign import CampaignGenerator, OpportunityScorer
from app.claude_discovery import ClaudeCompetitorDiscovery
from app.claude_signals import ClaudeSignalDiscovery
from app.demo_data import demo_contacts
from app.gemini import GeminiReasoner
from app.models import ApolloAccount, ApolloContact, CompanyProfile, Competitor, Opportunity, Severity, SignalType, SourceEvidence
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


def test_json_store_seeds_from_permanent_demo_snapshot(tmp_path: Path) -> None:
    seed = tmp_path / "seed.json"
    data_path = tmp_path / ".data" / "store.json"
    seed.write_text(
        """
        {
          "company_profiles": {
            "current": {
              "id": "current",
              "company_name": "Specular AI",
              "category": "Application security"
            }
          },
          "competitors": {},
          "signals": {},
          "opportunities": {},
          "campaign_drafts": {},
          "scan_runs": {}
        }
        """,
        encoding="utf-8",
    )

    repo = Repository(JsonStore(data_path, seed_path=seed))

    assert repo.get_company_profile().company_name == "Specular AI"  # type: ignore[union-attr]
    assert data_path.exists()


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


def test_claude_signal_discovery_parses_only_article_backed_sources() -> None:
    discovery = ClaudeSignalDiscovery(
        runner=lambda _command, _prompt, _timeout: """
        [
          {"title":"AcmeCRM outage frustrates customers","url":"https://status.acme.test/incidents/123",
           "snippet":"AcmeCRM reported an outage that disrupted users.","published_at":"2026-04-15"},
          {"title":"No URL","url":"","snippet":"ignore me"},
          {"title":"Bad URL","url":"not-a-url","snippet":"ignore me"},
          {"title":"Missing snippet","url":"https://example.com/no-snippet"}
        ]
        """
    )

    evidence = discovery.discover_evidence(Competitor(name="AcmeCRM"), limit=2)

    assert len(evidence) == 1
    assert evidence[0].title == "AcmeCRM outage frustrates customers"
    assert evidence[0].url == "https://status.acme.test/incidents/123"
    assert evidence[0].published_at is not None


def test_claude_signal_discovery_logs_raw_and_accepted_counts(caplog) -> None:
    discovery = ClaudeSignalDiscovery(
        runner=lambda _command, _prompt, _timeout: """
        [{"title":"AcmeCRM pricing increase","url":"https://example.com/pricing",
          "snippet":"Customers discuss pricing pressure."}]
        """
    )

    with caplog.at_level("INFO", logger="app.claude_signals"):
        evidence = discovery.discover_evidence(Competitor(name="AcmeCRM"), limit=2)

    assert len(evidence) == 1
    assert "claude_signal_discovery.raw_response" in caplog.text
    assert "accepted_sources=1" in caplog.text


def test_real_mode_monitor_does_not_save_fallback_search_urls_without_claude_sources() -> None:
    monitor = CompetitorMonitor(
        reasoner=GeminiReasoner(None, "global", "test"),
        demo_mode=False,
        claude_signal_discovery=ClaudeSignalDiscovery(runner=lambda _command, _prompt, _timeout: "[]"),
    )

    signals = monitor.discover_signals(Competitor(name="AcmeCRM"))

    assert signals == []


def test_real_mode_monitor_classifies_claude_article_sources() -> None:
    monitor = CompetitorMonitor(
        reasoner=GeminiReasoner(None, "global", "test"),
        demo_mode=False,
        claude_signal_discovery=ClaudeSignalDiscovery(
            runner=lambda _command, _prompt, _timeout: """
            [{"title":"AcmeCRM pricing increase hits customers",
              "url":"https://example.com/acme-pricing",
              "snippet":"Customers complain about renewal cost after a pricing increase."}]
            """
        ),
    )

    signals = monitor.discover_signals(Competitor(name="AcmeCRM"))

    assert len(signals) == 1
    assert signals[0].type == SignalType.PRICE_INCREASE
    assert signals[0].evidence[0].url == "https://example.com/acme-pricing"


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


def test_prospecting_returns_empty_list_for_non_json_output() -> None:
    signal = CompetitorMonitor(GeminiReasoner(None, "global", "test"), demo_mode=True).discover_signals(
        Competitor(name="AcmeCRM")
    )[0]
    prospector = ClaudeApolloProspector(runner=lambda _command, _prompt, _timeout: "Claude could not verify prospects.")

    candidates = prospector.find_impacted_customers(
        signal,
        Competitor(name="AcmeCRM"),
        CompanyProfile(company_name="Apollo"),
    )

    assert candidates == []


def test_apollo_search_prospects_returns_empty_list_on_unauthorized_response() -> None:
    client = ApolloClient(api_key="test", demo_mode=False)
    competitor = Competitor(name="AcmeCRM", category="Sales engagement")
    signal = CompetitorMonitor(GeminiReasoner(None, "global", "test"), demo_mode=True).discover_signals(competitor)[0]

    def fake_post_first_success(_paths: list[str], _payload: dict) -> dict:
        request = httpx.Request("POST", "https://api.apollo.io/api/v1/mixed_people/search")
        response = httpx.Response(401, request=request, text="Unauthorized")
        raise httpx.HTTPStatusError("401 Unauthorized", request=request, response=response)

    client._post_first_success = fake_post_first_success  # type: ignore[method-assign]

    assert client.search_prospects(competitor, signal) == []


def test_apollo_search_prospects_uses_api_search_then_enriches_email_and_domain() -> None:
    client = ApolloClient(api_key="test", demo_mode=False)
    competitor = Competitor(name="Snyk", category="Application security")
    signal = CompetitorMonitor(GeminiReasoner(None, "global", "test"), demo_mode=True).discover_signals(competitor)[0]
    post_calls = []

    def fake_post_first_success(paths: list[str], payload: dict) -> dict:
        assert paths == ["/mixed_people/api_search"]
        assert payload["currently_using_any_of_technology_uids"] == ["snyk"]
        assert "Chief Information Security Officer" in payload["person_titles"]
        return {
            "people": [
                {
                    "id": "person-1",
                    "first_name": "Jane",
                    "last_name_obfuscated": "Sm***",
                    "title": "Chief Information Security Officer",
                    "organization": {"name": "Northstar"},
                }
            ]
        }

    def fake_post(path: str, payload: dict | None = None, params: dict | None = None) -> dict:
        post_calls.append((path, payload, params))
        assert path == "/people/bulk_match"
        assert payload == {"details": [{"id": "person-1"}]}
        return {
            "matches": [
                {
                    "id": "person-1",
                    "first_name": "Jane",
                    "last_name": "Smith",
                    "name": "Jane Smith",
                    "title": "Chief Information Security Officer",
                    "email": "jane.smith@northstar.example",
                    "email_status": "verified",
                    "organization_id": "org-1",
                    "organization": {
                        "id": "org-1",
                        "name": "Northstar",
                        "primary_domain": "northstar.example",
                        "industry": "Software",
                        "estimated_num_employees": 500,
                    },
                }
            ]
        }

    client._post_first_success = fake_post_first_success  # type: ignore[method-assign]
    client._post = fake_post  # type: ignore[method-assign]

    pairs = client.search_prospects(competitor, signal, limit=1)

    assert len(pairs) == 1
    account, contacts = pairs[0]
    assert account.name == "Northstar"
    assert account.domain == "northstar.example"
    assert contacts[0].full_name == "Jane Smith"
    assert contacts[0].email == "jane.smith@northstar.example"
    assert post_calls


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


def test_impacted_customer_refresh_replaces_stale_self_account_without_email(tmp_path: Path) -> None:
    reasoner = GeminiReasoner(project=None, location="global", model="test-model")
    repo = Repository(JsonStore(tmp_path / "store.json"))
    competitor = Competitor(name="Snyk", category="Application security")
    repo.save_competitor(competitor)
    signal = CompetitorMonitor(reasoner, demo_mode=True).discover_signals(competitor)[0]
    repo.save_signal(signal)
    stale = Opportunity(
        signal_id=signal.id,
        account=ApolloAccount(name="Snyk", domain="snyk.io"),
        contacts=[ApolloContact(first_name="No", last_name="Email", title="VP Sales")],
        fit_score=80,
        displacement_rationale="stale",
    )
    repo.save_opportunity(stale)

    class FakeApollo(ApolloClient):
        def __init__(self) -> None:
            super().__init__(api_key="test", demo_mode=False)

        def search_prospects(self, _competitor: Competitor, _signal, limit: int = 8):
            account = ApolloAccount(name="Northstar", domain="northstar.example")
            contact = ApolloContact(
                id="person-1",
                first_name="Jane",
                last_name="Smith",
                title="Chief Information Security Officer",
                email="jane@northstar.example",
                email_status="verified",
            )
            return [(account, [contact])]

    agent = DisplacementAgent(
        repository=repo,
        monitor=CompetitorMonitor(reasoner=reasoner, demo_mode=True),
        apollo=FakeApollo(),
        scorer=OpportunityScorer(),
        campaign_generator=CampaignGenerator(reasoner=reasoner),
    )

    opportunities = agent.find_impacted_customers(signal.id)
    stored = repo.list_opportunities(signal_id=signal.id)

    assert [op.account.domain for op in opportunities] == ["northstar.example"]
    assert [op.account.domain for op in stored] == ["northstar.example"]
    assert stored[0].contacts[0].email == "jane@northstar.example"


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


def test_scan_limits_real_work_to_four_competitors_and_five_customers_each(tmp_path: Path) -> None:
    agent = make_agent(tmp_path)
    agent.max_competitors_per_scan = 4
    agent.max_customers_per_competitor = 5
    agent.repository.save_company_profile(CompanyProfile(company_name="Apollo"))
    for index in range(6):
        domains = [f"customer-{index}-{customer}.example" for customer in range(7)]
        agent.add_competitor(f"Competitor {index}", "Sales engagement", customer_domains=domains)

    result = agent.run_scan()

    assert result.competitors_scanned == 4
    assert result.signals_created == 4
    assert result.opportunities_created == 20
    assert len(agent.repository.list_signals()) == 4
    assert len(agent.repository.list_opportunities()) == 20
