from __future__ import annotations

import argparse
from typing import Iterable

from .dependencies import get_agent, get_competitor_discovery, get_repository
from .models import ApolloContact, CampaignDraft, Opportunity
from .storage import Repository


def _format_contact(contact: ApolloContact) -> str:
    name = f"{contact.first_name} {contact.last_name}".strip() or "Unknown"
    pieces: list[str] = [name]
    if contact.title:
        pieces.append(f"({contact.title})")
    if contact.account_name:
        pieces.append(f"at {contact.account_name}")
    return " ".join(pieces)


def _print_opportunities(opportunities: Iterable[Opportunity], repo: Repository) -> None:
    for idx, opp in enumerate(opportunities, start=1):
        signal = repo.get_signal(opp.signal_id)
        print(f"\n[{idx}] Opportunity: {opp.account.name} (fit score {opp.fit_score}/100)")
        if signal:
            print(f"    Competitor: {signal.competitor_name}")
            print(f"    Signal type: {signal.type.value}")
            print(f"    Headline: {signal.headline}")
            if signal.evidence:
                print(f"    Evidence URL: {signal.evidence[0].url}")
        else:
            print("    (Signal details unavailable; record may have been pruned.)")


def _print_email_drafts(drafts: Iterable[CampaignDraft]) -> None:
    for draft in drafts:
        contact = draft.contact
        print("\n--- Email Draft ----------------------------------------")
        print(f"To: {_format_contact(contact) if contact else 'Unknown contact'}")
        print(f"Subject: {draft.subject}")
        print("\nBody:\n")
        print(draft.email_body)
        print("--------------------------------------------------------")


def run(company_name: str) -> None:
    """End-to-end competitor displacement workflow.

    High level:
    - Use Claude + MCP to infer Apollo-style competitors for the given seller company.
    - For each competitor, use Gemini/web search to find negative signals (outages, price hikes, etc.).
    - Use Apollo's REST API (or demo data) to find that competitor's customers and decision makers.
    - Generate cold email drafts that position the seller as a better alternative.
    """
    repo = get_repository()
    agent = get_agent()
    discovery = get_competitor_discovery()

    print(f"🔍 Discovering competitors for seller company: {company_name!r}")
    discovery_result = agent.discover_company(company_name, discovery)
    print(f"Identified seller profile: {discovery_result.company.company_name} – {discovery_result.company.positioning}")
    print("Competitors discovered:")
    for competitor in repo.list_competitors():
        print(f"  • {competitor.name} – {competitor.product_positioning}")

    print("\n🌐 Scanning web for competitor issues and Apollo-qualified opportunities...")
    scan_result = agent.run_scan()
    print(
        f"Scan complete: {scan_result.competitors_scanned} competitors, "
        f"{scan_result.signals_created} new signals, {scan_result.opportunities_created} new opportunities."
    )

    opportunities = repo.list_opportunities()
    if not opportunities:
        print("\nNo opportunities found yet. Try disabling DEMO_MODE or tweaking your inputs.")
        return

    _print_opportunities(opportunities, repo)

    print("\n👥 Finding decision makers and generating cold email drafts...")
    all_drafts: list[CampaignDraft] = []

    for opportunity in opportunities:
        # Find contacts at the account that are likely to care about the competitor signal.
        contacts = agent.find_decision_makers(opportunity.id)
        if not contacts:
            continue
        contact_ids = [contact.id or contact.full_name for contact in contacts]
        drafts = agent.generate_emails_for_contacts(opportunity.id, contact_ids)
        all_drafts.extend(drafts)

    if not all_drafts:
        print("\nNo email drafts were generated. Check your Apollo configuration and DEMO_MODE setting.")
        return

    _print_email_drafts(all_drafts)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Run a full Apollo-powered competitor outreach flow.\n\n"
            "Give me the name of your seller company (for example 'Apollo' or your own company). "
            "I will:\n"
            "- Use Claude + MCP tools to discover your top B2B competitors\n"
            "- Use Gemini + web search to surface negative signals about those competitors\n"
            "- Use the Apollo REST API (or demo data) to find their customers and decision makers\n"
            "- Generate cold email drafts that pitch you as the better alternative"
        )
    )
    parser.add_argument(
        "company_name",
        help="Name of the seller company (whose competitors you want to displace).",
    )

    args = parser.parse_args()
    run(args.company_name)


if __name__ == "__main__":  # pragma: no cover - manual execution entrypoint
    main()

