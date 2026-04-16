from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from .demo_data import demo_accounts, demo_contacts
from .models import ApolloAccount, ApolloContact, Competitor, CompetitorSignal, SignalType


APOLLO_BASE_URL = "https://api.apollo.io/api/v1"

PERSONA_TITLES_BY_SIGNAL: dict[SignalType, list[str]] = {
    SignalType.PRICE_INCREASE: [
        "VP of Sales",
        "Chief Revenue Officer",
        "VP Revenue Operations",
        "Head of Sales Operations",
        "Procurement",
    ],
    SignalType.REVIEW_WAVE: [
        "VP of Sales",
        "Revenue Operations Director",
        "Head of Sales Enablement",
        "Chief Revenue Officer",
    ],
    SignalType.EXECUTIVE_DEPARTURE: [
        "CEO",
        "Chief Executive Officer",
        "VP of Sales",
        "Chief Revenue Officer",
    ],
    SignalType.OUTAGE: [
        "CTO",
        "VP of Engineering",
        "VP Infrastructure",
        "Head of Platform Engineering",
        "IT",
        "Security",
    ],
    SignalType.LAYOFFS: ["Revenue Operations", "Finance", "Operations", "Chief Revenue Officer"],
    SignalType.CONTRACT_COMPLAINT: ["Procurement", "Finance", "Revenue Operations", "Sales Operations"],
    SignalType.OTHER: ["Revenue Operations", "VP Sales", "Marketing Operations"],
}


@dataclass(frozen=True)
class ApolloQueryPlan:
    organization_payload: dict[str, Any]
    people_payload: dict[str, Any]


class ApolloClient:
    """Small Apollo REST wrapper with demo fallbacks.

    The MVP uses Apollo as the data layer for account/contact discovery. Write
    endpoints are intentionally wrappered but not called by the scanner because
    the default product mode is draft-only.
    """

    def __init__(self, api_key: str | None, base_url: str = APOLLO_BASE_URL, demo_mode: bool = True):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.demo_mode = demo_mode
        self._client = httpx.Client(timeout=20)

    def close(self) -> None:
        self._client.close()

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.api_key:
            headers["x-api-key"] = self.api_key
        return headers

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = self._client.post(f"{self.base_url}{path}", json=payload, headers=self._headers())
        response.raise_for_status()
        return response.json()

    def build_query_plan(self, competitor: Competitor, signal: CompetitorSignal) -> ApolloQueryPlan:
        org_payload: dict[str, Any] = {
            "page": 1,
            "per_page": 10,
            "q_organization_keyword_tags": [competitor.category] if competitor.category else [],
            "q_keywords": f"{competitor.name} customer {competitor.category}".strip(),
        }
        if competitor.technology_uid:
            org_payload["currently_using_any_of_technology_uids"] = [competitor.technology_uid]
        if competitor.customer_domains:
            org_payload["q_organization_domains"] = competitor.customer_domains

        persona_titles = PERSONA_TITLES_BY_SIGNAL.get(signal.type, PERSONA_TITLES_BY_SIGNAL[SignalType.OTHER])
        people_payload = {
            "page": 1,
            "per_page": 5,
            "person_titles": persona_titles,
            "contact_email_status": ["verified", "likely to engage", "unverified"],
        }
        return ApolloQueryPlan(organization_payload=org_payload, people_payload=people_payload)

    def search_accounts(self, competitor: Competitor, signal: CompetitorSignal) -> list[ApolloAccount]:
        if self.demo_mode or not self.api_key:
            return demo_accounts(competitor)
        payload = self.build_query_plan(competitor, signal).organization_payload
        data = self._post("/mixed_companies/search", payload)
        organizations = data.get("organizations") or data.get("accounts") or []
        return [self._parse_account(item) for item in organizations]

    def search_contacts(self, account: ApolloAccount, signal: CompetitorSignal) -> list[ApolloContact]:
        if self.demo_mode or not self.api_key:
            return demo_contacts(account)
        payload = {
            **self.build_query_plan(Competitor(id="tmp", name=signal.competitor_name), signal).people_payload,
            "organization_ids": [account.id] if account.id else [],
            "q_organization_domains": [account.domain] if account.domain else [],
        }
        data = self._post("/mixed_people/search", payload)
        people = data.get("people") or data.get("contacts") or []
        return [self._parse_contact(item, account) for item in people]

    def decision_maker_titles(self, signal: CompetitorSignal) -> list[str]:
        return PERSONA_TITLES_BY_SIGNAL.get(signal.type, PERSONA_TITLES_BY_SIGNAL[SignalType.OTHER])

    def create_contact_payload(self, contact: ApolloContact, account: ApolloAccount) -> dict[str, Any]:
        return {
            "first_name": contact.first_name,
            "last_name": contact.last_name,
            "title": contact.title,
            "organization_name": account.name,
            "account_id": account.id,
            "linkedin_url": contact.linkedin_url,
            "run_dedupe": True,
        }

    def add_contacts_to_sequence_payload(self, contact_ids: list[str], sequence_id: str, sender_email_account_id: str) -> dict[str, Any]:
        return {
            "contact_ids": contact_ids,
            "emailer_campaign_id": sequence_id,
            "send_email_from_email_account_id": sender_email_account_id,
        }

    @staticmethod
    def _parse_account(item: dict[str, Any]) -> ApolloAccount:
        return ApolloAccount(
            id=item.get("id"),
            name=item.get("name") or item.get("organization_name") or "Unknown account",
            domain=item.get("primary_domain") or item.get("website_url") or item.get("domain"),
            industry=item.get("industry"),
            employee_count=item.get("estimated_num_employees") or item.get("employee_count"),
            technologies=[tech.get("name", str(tech)) if isinstance(tech, dict) else str(tech) for tech in item.get("technologies", [])],
            raw=item,
        )

    @staticmethod
    def _parse_contact(item: dict[str, Any], account: ApolloAccount) -> ApolloContact:
        return ApolloContact(
            id=item.get("id"),
            first_name=item.get("first_name") or item.get("name", "").split(" ", 1)[0] or "",
            last_name=item.get("last_name")
            or (item.get("name", "").split(" ", 1)[1] if " " in item.get("name", "") else ""),
            title=item.get("title") or "",
            email_status=item.get("email_status"),
            linkedin_url=item.get("linkedin_url"),
            account_name=account.name,
            organization_id=account.id,
            raw=item,
        )
