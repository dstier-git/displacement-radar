from __future__ import annotations

from .models import ApolloContact, Competitor, Opportunity
from .storage import Repository


GraphNode = dict[str, object]
GraphLink = dict[str, str]


def build_relationship_graph(repo: Repository) -> dict[str, object]:
    """Map competitors to customer accounts and people at those accounts."""
    competitors = repo.list_competitors()
    signals = repo.list_signals()
    opportunities = repo.list_opportunities()

    competitor_by_id = {competitor.id: competitor for competitor in competitors}
    signal_by_id = {signal.id: signal for signal in signals}
    nodes: dict[str, GraphNode] = {}
    links: dict[tuple[str, str, str], GraphLink] = {}

    for competitor in competitors:
        competitor_id = _competitor_node_id(competitor)
        nodes[competitor_id] = _competitor_node(competitor)
        for domain in competitor.customer_domains:
            customer_id = _customer_node_id(domain)
            nodes.setdefault(
                customer_id,
                {
                    "id": customer_id,
                    "type": "customer",
                    "label": _customer_label(domain),
                    "subtitle": domain,
                    "detail": f"Known customer domain for {competitor.name}.",
                    "domain": domain,
                    "contactCount": 0,
                    "opportunityCount": 0,
                },
            )
            _put_link(links, competitor_id, customer_id, "customer")

    for opportunity in opportunities:
        signal = signal_by_id.get(opportunity.signal_id)
        if not signal:
            continue

        competitor = competitor_by_id.get(signal.competitor_id)
        if competitor:
            competitor_id = _competitor_node_id(competitor)
            nodes.setdefault(competitor_id, _competitor_node(competitor))
        else:
            competitor_id = f"competitor:{signal.competitor_id}"
            nodes.setdefault(
                competitor_id,
                {
                    "id": competitor_id,
                    "type": "competitor",
                    "label": signal.competitor_name,
                    "subtitle": "Signal source",
                    "detail": signal.headline,
                    "signalCount": 1,
                },
            )

        customer_id = _customer_node_id(opportunity.account.domain or opportunity.account.name)
        nodes[customer_id] = _customer_node(opportunity)
        _put_link(links, competitor_id, customer_id, "customer")

        for contact in opportunity.contacts:
            contact_id = _contact_node_id(opportunity, contact)
            nodes[contact_id] = _contact_node(opportunity, contact)
            _put_link(links, customer_id, contact_id, "person")

    return {
        "nodes": sorted(nodes.values(), key=lambda node: (str(node["type"]), str(node["label"]).lower())),
        "links": sorted(links.values(), key=lambda link: (link["source"], link["target"], link["type"])),
        "summary": {
            "competitors": len([node for node in nodes.values() if node["type"] == "competitor"]),
            "customers": len([node for node in nodes.values() if node["type"] == "customer"]),
            "people": len([node for node in nodes.values() if node["type"] == "person"]),
            "relationships": len(links),
        },
    }


def _competitor_node(competitor: Competitor) -> GraphNode:
    return {
        "id": _competitor_node_id(competitor),
        "type": "competitor",
        "label": competitor.name,
        "subtitle": competitor.category or "Competitor",
        "detail": competitor.product_positioning or "Ready for signal scanning.",
        "customerCount": len(competitor.customer_domains),
    }


def _customer_node(opportunity: Opportunity) -> GraphNode:
    account = opportunity.account
    domain = account.domain or ""
    return {
        "id": _customer_node_id(account.domain or account.name),
        "type": "customer",
        "label": account.name,
        "subtitle": domain or account.industry or "Customer account",
        "detail": opportunity.impact_summary or opportunity.displacement_rationale,
        "domain": domain,
        "fitScore": opportunity.fit_score,
        "contactCount": len(opportunity.contacts),
        "opportunityCount": 1,
        "href": f"/opportunities/{opportunity.id}",
        "confidence": opportunity.competitor_usage_confidence,
    }


def _contact_node(opportunity: Opportunity, contact: ApolloContact) -> GraphNode:
    return {
        "id": _contact_node_id(opportunity, contact),
        "type": "person",
        "label": contact.full_name,
        "subtitle": contact.title or "Decision maker",
        "detail": contact.email or contact.linkedin_url or "No contact channel shown yet.",
        "email": contact.email or "",
        "emailStatus": contact.email_status or "unknown",
        "href": contact.linkedin_url or f"/opportunities/{opportunity.id}",
    }


def _put_link(links: dict[tuple[str, str, str], GraphLink], source: str, target: str, link_type: str) -> None:
    links[(source, target, link_type)] = {"source": source, "target": target, "type": link_type}


def _competitor_node_id(competitor: Competitor) -> str:
    return f"competitor:{competitor.id}"


def _customer_node_id(account_key: str) -> str:
    return f"customer:{account_key.strip().lower()}"


def _contact_node_id(opportunity: Opportunity, contact: ApolloContact) -> str:
    return f"person:{opportunity.id}:{contact.id or contact.full_name.strip().lower()}"


def _customer_label(domain: str) -> str:
    return domain.split(".", 1)[0].replace("-", " ").title()
