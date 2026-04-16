from __future__ import annotations

from .models import ApolloAccount, ApolloContact, Competitor, CompetitorSignal, Severity, SignalType, SourceEvidence


def demo_competitors() -> list[Competitor]:
    return [
        Competitor(
            name="AcmeCRM",
            category="Sales engagement",
            product_positioning="A faster revenue platform that combines prospect data, intent, and outreach in one workflow.",
            technology_uid="acmecrm_demo_uid",
            customer_domains=["northstar.example", "orbit.example", "summit.example"],
        ),
        Competitor(
            name="PipelinePilot",
            category="RevOps automation",
            product_positioning="Replace brittle point tools with AI-guided pipeline generation and account intelligence.",
            customer_domains=["atlas.example", "brightpath.example"],
        ),
    ]


def demo_signal(competitor: Competitor) -> CompetitorSignal:
    return CompetitorSignal(
        competitor_id=competitor.id,
        competitor_name=competitor.name,
        type=SignalType.PRICE_INCREASE,
        severity=Severity.HIGH,
        urgency_score=84,
        headline=f"{competitor.name} customers react to packaging and pricing changes",
        pain_hypothesis="Customers with budget pressure may be actively reassessing whether the incumbent still delivers enough value.",
        recommended_angle="Lead with a low-friction migration assessment and a cost-neutral pilot timed around renewal risk.",
        evidence=[
            SourceEvidence(
                title=f"{competitor.name} pricing update draws customer discussion",
                url=f"https://example.com/{competitor.name.lower()}-pricing-update",
                snippet="Public customer comments mention packaging confusion and renewal pressure.",
            )
        ],
    )


def demo_accounts(competitor: Competitor) -> list[ApolloAccount]:
    domains = competitor.customer_domains or ["northstar.example", "orbit.example", "summit.example"]
    return [
        ApolloAccount(
            id=f"demo-org-{index}",
            name=domain.split(".")[0].replace("-", " ").title(),
            domain=domain,
            industry="Computer Software",
            employee_count=250 + index * 175,
            technologies=[competitor.name, "Salesforce", "Google Cloud"],
        )
        for index, domain in enumerate(domains, start=1)
    ]


def demo_contacts(account: ApolloAccount) -> list[ApolloContact]:
    return [
        ApolloContact(
            id=f"{account.id}-revops",
            first_name="Jordan",
            last_name="Lee",
            title="VP Revenue Operations",
            email_status="verified",
            linkedin_url=f"https://linkedin.com/in/{account.name.lower().replace(' ', '-')}-revops",
            account_name=account.name,
            organization_id=account.id,
        ),
        ApolloContact(
            id=f"{account.id}-sales",
            first_name="Sam",
            last_name="Patel",
            title="Head of Sales Development",
            email_status="likely",
            linkedin_url=f"https://linkedin.com/in/{account.name.lower().replace(' ', '-')}-sales",
            account_name=account.name,
            organization_id=account.id,
        ),
    ]
