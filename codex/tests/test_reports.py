from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.campaign import OpportunityScorer
from app.models import ApolloAccount, Competitor, CompetitorSignal, Severity, SignalType, SourceEvidence
from app.reports import CompetitiveLandscapeReportGenerator
from app.storage import JsonStore, Repository


def test_markdown_report_includes_mermaid_graphs_and_monthly_deltas(tmp_path: Path) -> None:
    now = datetime(2026, 4, 16, tzinfo=timezone.utc)
    repo = Repository(JsonStore(tmp_path / "report-store.json"))
    competitor = Competitor(name="AcmeCRM", category="Sales engagement", created_at=now - timedelta(days=90))
    repo.save_competitor(competitor)

    current_signal = CompetitorSignal(
        competitor_id=competitor.id,
        competitor_name=competitor.name,
        type=SignalType.OUTAGE,
        severity=Severity.HIGH,
        urgency_score=88,
        headline="AcmeCRM outage frustrates customers",
        pain_hypothesis="operators may be questioning reliability.",
        recommended_angle="Offer a resilience review.",
        evidence=[SourceEvidence(title="Outage", url="https://example.com/outage")],
        detected_at=now - timedelta(days=2),
    )
    previous_signal = CompetitorSignal(
        competitor_id=competitor.id,
        competitor_name=competitor.name,
        type=SignalType.PRICE_INCREASE,
        severity=Severity.MEDIUM,
        urgency_score=50,
        headline="AcmeCRM raised prices last quarter",
        pain_hypothesis="buyers may compare costs.",
        recommended_angle="Offer a renewal benchmark.",
        evidence=[SourceEvidence(title="Pricing", url="https://example.com/pricing")],
        detected_at=now - timedelta(days=45),
    )
    repo.save_signal(current_signal)
    repo.save_signal(previous_signal)

    account = ApolloAccount(name="Northstar", domain="northstar.example", technologies=["AcmeCRM"], employee_count=500)
    opportunity = OpportunityScorer().score(current_signal, account, [])
    opportunity.created_at = now - timedelta(days=1)
    repo.save_opportunity(opportunity)

    report = CompetitiveLandscapeReportGenerator(repo, now=now).generate()

    assert "# Competitive Landscape Report" in report
    assert "```mermaid" in report
    assert "flowchart LR" in report
    assert "xychart-beta" in report
    assert "pie title Last 30 days signal mix" in report
    assert "| AcmeCRM | 1 | +0 | 1 | +1 | 88 |" in report
    assert "AcmeCRM outage frustrates customers" in report
    assert "Northstar" in report
