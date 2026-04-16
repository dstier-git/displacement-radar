from __future__ import annotations

from dataclasses import dataclass
import re
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
        headers = {"Content-Type": "application/json", "Accept": "application/json", "Cache-Control": "no-cache"}
        if self.api_key:
            headers["x-api-key"] = self.api_key
        return headers

    def _post(
        self,
        path: str,
        payload: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        response = self._client.post(
            f"{self.base_url}{path}",
            json=payload or {},
            params=self._flatten_params(params),
            headers=self._headers(),
        )
        response.raise_for_status()
        return response.json()

    @staticmethod
    def _is_auth_failure(exc: Exception) -> bool:
        return isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in {401, 403}

    def _post_first_success(self, paths: list[str], payload: dict[str, Any]) -> dict[str, Any]:
        last_exc: Exception | None = None
        for path in paths:
            try:
                return self._post(path, payload)
            except Exception as exc:  # pragma: no cover - depends on Apollo API behavior
                last_exc = exc
        if last_exc:
            raise last_exc
        raise RuntimeError("no paths provided")

    def resolve_organization_id(self, domain: str) -> str | None:
        """Best-effort mapping from a domain to an Apollo organization id."""
        if self.demo_mode or not self.api_key:
            return None
        cleaned = domain.strip().lower().removeprefix("http://").removeprefix("https://")
        cleaned = cleaned.split("/")[0]
        cleaned = cleaned.removeprefix("www.")
        if not cleaned:
            return None
        payload = {"page": 1, "per_page": 1, "q_organization_domains": [cleaned]}
        try:
            data = self._post("/mixed_companies/search", payload)
        except Exception as exc:
            if self._is_auth_failure(exc):
                return None
            raise
        organizations = data.get("organizations") or data.get("accounts") or []
        if not organizations:
            return None
        org_id = (organizations[0] or {}).get("id")
        return str(org_id) if org_id else None

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
        if self.demo_mode:
            return demo_accounts(competitor)
        if not self.api_key:
            return []
        payload = self.build_query_plan(competitor, signal).organization_payload
        try:
            data = self._post("/mixed_companies/search", payload)
        except Exception as exc:
            if self._is_auth_failure(exc):
                return []
            raise
        organizations = data.get("organizations") or data.get("accounts") or []
        return [self._parse_account(item) for item in organizations]

    def search_prospects(self, competitor: Competitor, signal: CompetitorSignal, limit: int = 8) -> list[tuple[ApolloAccount, list[ApolloContact]]]:
        """Find competitor customer accounts and email-bearing buyer contacts via Apollo.

        Apollo's people search returns net-new people but not emails. The reliable
        flow is: search people at organizations using the competitor technology,
        then enrich those person IDs to reveal work emails and organization
        domains before grouping them into account/contact pairs.
        """
        if self.demo_mode:
            accounts = demo_accounts(competitor)[:limit]
            return [(account, demo_contacts(account)[:5]) for account in accounts]
        if not self.api_key:
            return []

        people = self._search_people_for_competitor(competitor, signal, limit)
        enriched_people = self._bulk_match_people(people) or people

        by_key: dict[str, tuple[ApolloAccount, list[ApolloContact]]] = {}
        for person in enriched_people:
            if not isinstance(person, dict):
                continue
            account = self._parse_account_from_person(person)
            if not account:
                continue
            contact = self._parse_contact(person, account)
            if not contact.email:
                matched = self._match_person(contact, account)
                if matched:
                    account = self._parse_account_from_person(matched) or account
                    contact = self._parse_contact(matched, account)
            key = str(account.domain or account.id or account.name).strip().lower()
            if not key:
                continue
            entry = by_key.get(key)
            if not entry:
                by_key[key] = (account, [contact])
            else:
                entry[1].append(contact)

        results: list[tuple[ApolloAccount, list[ApolloContact]]] = []
        for _key, (account, contacts) in by_key.items():
            deduped: list[ApolloContact] = []
            seen_contact: set[str] = set()
            for c in sorted(contacts, key=lambda item: (0 if item.email else 1, item.email_status or "z")):
                fingerprint = (c.email or c.id or c.full_name).strip().lower()
                if fingerprint in seen_contact:
                    continue
                seen_contact.add(fingerprint)
                deduped.append(c)
            results.append((account, deduped[:5]))

        # Put accounts with usable emails first; stable name sort keeps UI deterministic.
        results.sort(key=lambda pair: (0 if any(c.email for c in pair[1]) else 1, pair[0].name.lower()))
        return results[:limit]

    def search_contacts(self, account: ApolloAccount, signal: CompetitorSignal) -> list[ApolloContact]:
        if self.demo_mode:
            return demo_contacts(account)
        if not self.api_key:
            return []
        # If the account came from OpenAI (or another source), its `id` may not be a real Apollo org id.
        # Resolve the real org id from the domain when possible.
        resolved_org_id = None
        if account.domain:
            try:
                resolved_org_id = self.resolve_organization_id(account.domain)
            except Exception:
                resolved_org_id = None

        payload = {
            **self.build_query_plan(Competitor(id="tmp", name=signal.competitor_name), signal).people_payload,
            "organization_ids": [resolved_org_id or account.id] if (resolved_org_id or account.id) else [],
            "q_organization_domains_list": [account.domain] if account.domain else [],
        }
        try:
            data = self._post_first_success(["/mixed_people/api_search"], payload)
        except Exception as exc:
            if self._is_auth_failure(exc):
                return []
            raise
        people = data.get("people") or data.get("contacts") or []
        enriched_people = self._bulk_match_people([item for item in people if isinstance(item, dict)]) or people
        return [self._parse_contact(item, self._parse_account_from_person(item) or account) for item in enriched_people if isinstance(item, dict)]

    def _reveal_emails(self, contacts: list[ApolloContact], account: ApolloAccount) -> list[ApolloContact]:
        """Reveal emails for contacts missing them via /people/match."""
        if not self.api_key or not contacts:
            return contacts
        revealed: list[ApolloContact] = []
        for contact in contacts:
            if contact.email:
                revealed.append(contact)
                continue
            try:
                email = self._match_person_email(contact, account)
            except Exception:
                email = None
            if email:
                revealed.append(ApolloContact(
                    id=contact.id,
                    first_name=contact.first_name,
                    last_name=contact.last_name,
                    title=contact.title,
                    email=email,
                    email_status="verified",
                    linkedin_url=contact.linkedin_url,
                    account_name=contact.account_name,
                    organization_id=contact.organization_id,
                    raw=contact.raw,
                ))
            else:
                revealed.append(contact)
        return revealed

    def _match_person_email(self, contact: ApolloContact, account: ApolloAccount) -> str | None:
        person = self._match_person(contact, account)
        return (person or {}).get("email") or None

    def _match_person(self, contact: ApolloContact, account: ApolloAccount) -> dict[str, Any] | None:
        params: dict[str, Any] = {
            "reveal_personal_emails": False,
            "reveal_phone_number": False,
        }
        if contact.id:
            params["id"] = contact.id
        elif contact.full_name != "Unknown contact":
            params["name"] = contact.full_name
        else:
            params["first_name"] = contact.first_name
            params["last_name"] = contact.last_name
        if account.domain:
            params["domain"] = account.domain
        else:
            params["organization_name"] = account.name
        if contact.linkedin_url:
            params["linkedin_url"] = contact.linkedin_url
        try:
            data = self._post("/people/match", params=params)
        except Exception as exc:
            if self._is_auth_failure(exc):
                return None
            raise
        person = data.get("person") or None
        return person if isinstance(person, dict) else None


    def _search_people_for_competitor(
        self, competitor: Competitor, signal: CompetitorSignal, limit: int
    ) -> list[dict[str, Any]]:
        persona_titles = self.decision_maker_titles_for_competitor(competitor, signal)
        per_page = min(max(limit * 4, 10), 25)
        technology_uid = competitor.technology_uid or self._technology_uid_guess(competitor.name)
        payload: dict[str, Any] = {
            "page": 1,
            "per_page": per_page,
            "person_titles": persona_titles,
            "person_seniorities": ["c_suite", "vp", "head", "director"],
            "contact_email_status": ["verified", "likely to engage", "unverified"],
        }
        if technology_uid:
            payload["currently_using_any_of_technology_uids"] = [technology_uid]
        try:
            data = self._post_first_success(["/mixed_people/api_search"], payload)
        except Exception as exc:
            if self._is_auth_failure(exc):
                return []
            raise
        people = [item for item in (data.get("people") or data.get("contacts") or []) if isinstance(item, dict)]

        # If the guessed technology UID did not match Apollo's taxonomy, fall back
        # to a keyword search rather than returning nothing. Explicit UIDs should
        # not fall back because the caller intentionally provided the taxonomy key.
        if not people and technology_uid and not competitor.technology_uid:
            fallback_payload = {
                "page": 1,
                "per_page": per_page,
                "person_titles": persona_titles,
                "person_seniorities": ["c_suite", "vp", "head", "director"],
                "q_keywords": competitor.name,
            }
            data = self._post_first_success(["/mixed_people/api_search"], fallback_payload)
            people = [item for item in (data.get("people") or data.get("contacts") or []) if isinstance(item, dict)]
        return people

    def _bulk_match_people(self, people: list[dict[str, Any]]) -> list[dict[str, Any]]:
        ids: list[str] = []
        seen: set[str] = set()
        for person in people:
            person_id = person.get("id") or person.get("person_id")
            if not person_id:
                continue
            person_id = str(person_id)
            if person_id in seen:
                continue
            seen.add(person_id)
            ids.append(person_id)
        if not ids:
            return []

        matched_by_id: dict[str, dict[str, Any]] = {}
        for start in range(0, len(ids), 10):
            chunk = ids[start : start + 10]
            try:
                data = self._post(
                    "/people/bulk_match",
                    {"details": [{"id": person_id} for person_id in chunk]},
                    params={"reveal_personal_emails": False, "reveal_phone_number": False},
                )
            except Exception as exc:
                if self._is_auth_failure(exc):
                    return []
                raise
            for item in data.get("matches") or data.get("people") or []:
                if isinstance(item, dict) and item.get("id"):
                    matched_by_id[str(item["id"])] = item

        enriched: list[dict[str, Any]] = []
        for person in people:
            person_id = person.get("id") or person.get("person_id")
            enriched.append(matched_by_id.get(str(person_id), person) if person_id else person)
        return enriched

    def decision_maker_titles_for_competitor(
        self, competitor: Competitor, signal: CompetitorSignal
    ) -> list[str]:
        base_titles = PERSONA_TITLES_BY_SIGNAL.get(signal.type, PERSONA_TITLES_BY_SIGNAL[SignalType.OTHER])
        context = " ".join(
            [
                competitor.name,
                competitor.category,
                competitor.product_positioning,
                signal.headline,
                signal.pain_hypothesis,
                signal.recommended_angle,
            ]
        ).lower()
        if any(
            term in context
            for term in (
                "security",
                "appsec",
                "application security",
                "devsecops",
                "vulnerability",
                "compliance",
                "ciso",
            )
        ):
            security_titles = [
                "Chief Information Security Officer",
                "CISO",
                "VP Security",
                "Vice President Security",
                "Head of Security",
                "Head of Application Security",
                "Director Application Security",
                "Director Security",
                "VP Engineering",
                "CTO",
            ]
            return self._dedupe_strings([*security_titles, *base_titles])
        return base_titles

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
    def _flatten_params(params: dict[str, Any] | None) -> list[tuple[str, str]] | None:
        if not params:
            return None
        flattened: list[tuple[str, str]] = []
        for key, value in params.items():
            if value is None or value == []:
                continue
            if isinstance(value, list):
                for item in value:
                    flattened.append((key, str(item)))
            elif isinstance(value, bool):
                flattened.append((key, str(value).lower()))
            else:
                flattened.append((key, str(value)))
        return flattened

    @staticmethod
    def _technology_uid_guess(name: str) -> str | None:
        slug = re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_")
        return slug or None

    @staticmethod
    def _dedupe_strings(values: list[str]) -> list[str]:
        deduped: list[str] = []
        seen: set[str] = set()
        for value in values:
            key = value.strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            deduped.append(value)
        return deduped

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
            email=item.get("email"),
            email_status=item.get("email_status"),
            linkedin_url=item.get("linkedin_url"),
            account_name=account.name,
            organization_id=account.id,
            raw=item,
        )

    @staticmethod
    def _parse_account_from_person(person: dict[str, Any]) -> ApolloAccount | None:
        org = person.get("organization") or person.get("account") or {}
        if not isinstance(org, dict):
            org = {}
        org_id = person.get("organization_id") or org.get("id")
        org_name = person.get("organization_name") or org.get("name") or org.get("organization_name")
        domain = (
            org.get("primary_domain")
            or org.get("domain")
            or org.get("website_url")
            or person.get("organization_domain")
            or person.get("primary_domain")
        )
        if not (org_name or domain):
            return None
        return ApolloAccount(
            id=str(org_id) if org_id else None,
            name=str(org_name or domain or "Unknown account"),
            domain=str(domain) if domain else None,
            industry=org.get("industry") or person.get("industry"),
            employee_count=org.get("estimated_num_employees") or org.get("employee_count"),
            technologies=[],
            raw={"person": person, "organization": org},
        )
