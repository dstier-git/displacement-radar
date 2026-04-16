from __future__ import annotations

import json
import logging
import re
import subprocess
from dataclasses import dataclass
from typing import Callable

from .models import ApolloAccount, ApolloContact, CompanyProfile, Competitor, CompetitorSignal

Runner = Callable[[list[str], str, int], str]

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProspectCandidate:
    account: ApolloAccount
    contacts: list[ApolloContact]
    impact_summary: str
    competitor_usage_confidence: str = "unknown"
    source_notes: list[str] | None = None


class ClaudeApolloProspector:
    """Find impacted competitor customers through Claude with Apollo MCP.

    The class shells out to the local Claude CLI so Apollo MCP authorization
    remains user-managed outside the web app. It returns an empty list on any
    failure; production callers should show a review/unavailable state rather
    than invent prospects.
    """

    def __init__(
        self,
        mcp_config: str | None = None,
        max_budget_usd: float | None = 0.35,
        timeout_seconds: int = 60,
        runner: Runner | None = None,
    ):
        self.mcp_config = mcp_config
        self.max_budget_usd = max_budget_usd
        self.timeout_seconds = timeout_seconds
        self.runner = runner or self._run_claude

    def find_impacted_customers(
        self,
        signal: CompetitorSignal,
        competitor: Competitor,
        company: CompanyProfile | None,
        limit: int = 8,
    ) -> list[ProspectCandidate]:
        try:
            raw = self.runner(self._command(), self._prompt(signal, competitor, company, limit), self.timeout_seconds)
            payload = self._parse_list(raw)
            return self._parse_candidates(payload, signal, limit)
        except Exception as exc:
            logger.info(
                "claude_prospector.unavailable competitor=%s signal_id=%s error=%s",
                competitor.name,
                signal.id,
                exc,
            )
            return []

    def _command(self) -> list[str]:
        # IMPORTANT: `-p` consumes the next argument as the prompt.
        # Do NOT include `-p` here. The runner appends `-p <prompt>` at the end.
        command = ["claude", "--output-format", "text", "--permission-mode", "dontAsk"]
        if self.max_budget_usd is not None:
            command.extend(["--max-budget-usd", str(self.max_budget_usd)])
        if self.mcp_config:
            command.extend(["--mcp-config", self.mcp_config])
        return command

    @staticmethod
    def _prompt(
        signal: CompetitorSignal,
        competitor: Competitor,
        company: CompanyProfile | None,
        limit: int,
    ) -> str:
        seller = company.company_name if company else "our company"
        evidence_lines = "\n".join(f"- {item.title}: {item.url}" for item in signal.evidence) or "- No evidence URL"
        return f"""Use Apollo MCP tools to find up to {limit} real companies likely using {competitor.name}.
Focus on accounts exposed to this displacement signal.
Do not create contacts, write Apollo records, enroll sequences, or send messages.

Seller company: {seller}
Competitor: {competitor.name}
Competitor category: {competitor.category or 'unknown'}
Signal headline: {signal.headline}
Signal pain hypothesis: {signal.pain_hypothesis}
Recommended angle: {signal.recommended_angle}
Evidence:
{evidence_lines}

Return ONLY strict JSON array, no markdown:
[
  {{
    "company": "Real company name",
    "domain": "company.com",
    "industry": "industry or null",
    "employee_count": 500,
    "competitor_usage_confidence": "verified|likely|unknown",
    "impact_summary": "1-2 sentences explaining how this signal could affect this customer",
    "source_notes": ["Apollo evidence or note"],
    "contacts": [
      {{
        "id": "Apollo person id if available",
        "first_name": "Jane",
        "last_name": "Smith",
        "title": "VP Revenue Operations",
        "email": "jane@company.com or null",
        "email_status": "verified|likely|unknown",
        "linkedin_url": "https://... or null"
      }}
    ]
  }}
]

Only include accounts and contacts supported by Apollo or explicit source notes.
If you cannot verify prospects, return [] rather than inventing."""

    @staticmethod
    def _run_claude(command: list[str], prompt: str, timeout_seconds: int) -> str:
        completed = subprocess.run([*command, "-p", prompt], capture_output=True, text=True, timeout=timeout_seconds)
        if completed.returncode != 0:
            stderr = (completed.stderr or "").strip()
            stdout = (completed.stdout or "").strip()
            raise RuntimeError(f"claude CLI failed (exit={completed.returncode}). stderr={stderr!r} stdout={stdout!r}")
        return completed.stdout

    @staticmethod
    def _parse_list(text: str) -> list[dict]:
        cleaned = re.sub(r"```[\w-]*\n?", "", text).replace("```", "").strip()
        start = cleaned.find("[")
        end = cleaned.rfind("]")
        if start < 0 or end < start:
            raise ValueError("Claude output did not contain a JSON array")
        data = json.loads(cleaned[start : end + 1])
        if not isinstance(data, list):
            raise ValueError("Claude output JSON must be a list")
        return [item for item in data if isinstance(item, dict)]

    @staticmethod
    def _parse_candidates(items: list[dict], signal: CompetitorSignal, limit: int) -> list[ProspectCandidate]:
        candidates: list[ProspectCandidate] = []
        seen: set[str] = set()
        for index, item in enumerate(items[:limit], start=1):
            company = str(item.get("company") or item.get("name") or "").strip()
            if not company:
                continue
            domain = item.get("domain") or item.get("website_url") or None
            key = str(domain or company).strip().lower()
            if key in seen:
                continue
            seen.add(key)
            account = ApolloAccount(
                id=item.get("id") or item.get("organization_id") or f"claude-apollo-{signal.id}-{index}",
                name=company,
                domain=domain,
                industry=item.get("industry") or None,
                employee_count=ClaudeApolloProspector._parse_employee_count(
                    item.get("employee_count") or item.get("size")
                ),
                technologies=[signal.competitor_name],
                raw=item,
            )
            contacts = [
                ClaudeApolloProspector._parse_contact(contact, account)
                for contact in item.get("contacts", [])
                if isinstance(contact, dict)
            ]
            candidates.append(
                ProspectCandidate(
                    account=account,
                    contacts=contacts[:5],
                    impact_summary=str(item.get("impact_summary") or item.get("pain") or "").strip(),
                    competitor_usage_confidence=str(item.get("competitor_usage_confidence") or "unknown"),
                    source_notes=[str(note) for note in item.get("source_notes", []) if str(note).strip()]
                    if isinstance(item.get("source_notes"), list)
                    else [],
                )
            )
        return candidates

    @staticmethod
    def _parse_employee_count(value: object) -> int | None:
        if isinstance(value, int):
            return value
        if value is None:
            return None
        digits = re.findall(r"\d+", str(value).replace(",", ""))
        if not digits:
            return None
        return int(digits[-1])

    @staticmethod
    def _parse_contact(item: dict, account: ApolloAccount) -> ApolloContact:
        name = str(item.get("name") or "").strip()
        first_name = str(item.get("first_name") or (name.split(" ", 1)[0] if name else "")).strip()
        last_name = str(
            item.get("last_name") or (name.split(" ", 1)[1] if name and " " in name else "")
        ).strip()
        return ApolloContact(
            id=item.get("id") or item.get("person_id"),
            first_name=first_name,
            last_name=last_name,
            title=str(item.get("title") or "").strip(),
            email=item.get("email"),
            email_status=item.get("email_status"),
            linkedin_url=item.get("linkedin_url"),
            account_name=account.name,
            organization_id=account.id,
            raw=item,
        )


class OpenAIProspector:
    """Find likely competitor customers using OpenAI + web search.

    This is intentionally "best-effort": it returns [] on failure rather than inventing prospects.
    It does not create any external records and does not require Apollo.
    """

    def __init__(self, api_key: str, model: str = "gpt-4.1-mini", timeout_seconds: int = 45):
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds

    def find_impacted_customers(
        self,
        signal: CompetitorSignal,
        competitor: Competitor,
        company: CompanyProfile | None,
        limit: int = 8,
    ) -> list[ProspectCandidate]:
        try:
            payload = self._fetch_candidates(signal, competitor, company, limit)
            return self._parse_candidates(payload, signal, limit)
        except Exception as exc:
            logger.warning(
                "openai_prospector.failed competitor=%s signal_id=%s error=%s",
                competitor.name,
                signal.id,
                exc,
                exc_info=True,
            )
            return []

    def _fetch_candidates(
        self,
        signal: CompetitorSignal,
        competitor: Competitor,
        company: CompanyProfile | None,
        limit: int,
    ) -> list[dict]:
        # Lazy import so the app can run without OpenAI installed in demo-only contexts.
        from openai import OpenAI  # type: ignore

        client = OpenAI(api_key=self.api_key, timeout=self.timeout_seconds)

        seller = company.company_name if company else "our company"
        evidence_lines = "\n".join(f"- {item.title}: {item.url}" for item in signal.evidence) or "- No evidence URL"

        prompt = f"""You are helping a B2B seller ({seller}) identify companies likely using a competitor product.

Competitor: {competitor.name}
Competitor category: {competitor.category or 'unknown'}

Context (displacement signal):
- Headline: {signal.headline}
- Pain hypothesis: {signal.pain_hypothesis}
- Recommended angle: {signal.recommended_angle}
Evidence:
{evidence_lines}

Task:
Use web search to find up to {limit} real companies that are likely customers/users of {competitor.name}.
Prefer evidence-backed claims (case studies, customer pages, press releases, docs, integrations, job posts mentioning the tool, etc.).

Return ONLY strict JSON array (no markdown, no commentary):
[
  {{
    "company": "Real company name",
    "domain": "company.com or null",
    "industry": "industry or null",
    "employee_count": 500 or null,
    "competitor_usage_confidence": "verified|likely|unknown",
    "impact_summary": "1-2 sentences explaining how the signal could affect this customer",
    "source_notes": ["short note with at least one URL that supports the claim"]
  }}
]

Rules:
- If you cannot find any credible candidates, return [].
- Never fabricate sources; every item should include at least one URL in source_notes.
"""

        response = None
        try:
            response = client.responses.create(
                model=self.model,
                input=prompt,
                # Use OpenAI's built-in web search tool when available.
                tools=[{"type": "web_search"}],
            )
        except Exception as exc:
            # Some models/accounts don't have web search enabled. Fall back to a no-tool run
            # (less reliable, but better than returning nothing for the demo).
            logger.info(
                "openai_prospector.web_search_unavailable competitor=%s signal_id=%s error=%s",
                competitor.name,
                signal.id,
                exc,
                exc_info=True,
            )
            response = client.responses.create(model=self.model, input=prompt)

        text = (getattr(response, "output_text", None) or "").strip()
        if not text:
            # Fallback: try to stitch text from output parts if SDK doesn't expose output_text.
            text = self._response_to_text(response).strip()
        return self._parse_list(text)

    @staticmethod
    def _response_to_text(response: object) -> str:
        # Best-effort extraction across OpenAI SDK response shapes.
        try:
            output = getattr(response, "output", None)
            if not isinstance(output, list):
                return ""
            chunks: list[str] = []
            for item in output:
                for part in getattr(item, "content", []) or []:
                    if getattr(part, "type", None) in {"output_text", "text"}:
                        chunks.append(getattr(part, "text", "") or "")
            return "\n".join(chunks)
        except Exception:
            return ""

    @staticmethod
    def _parse_list(text: str) -> list[dict]:
        cleaned = re.sub(r"```[\w-]*\n?", "", text).replace("```", "").strip()
        start = cleaned.find("[")
        end = cleaned.rfind("]")
        if start < 0 or end < start:
            raise ValueError("OpenAI output did not contain a JSON array")
        data = json.loads(cleaned[start : end + 1])
        if not isinstance(data, list):
            raise ValueError("OpenAI output JSON must be a list")
        return [item for item in data if isinstance(item, dict)]

    @staticmethod
    def _parse_candidates(items: list[dict], signal: CompetitorSignal, limit: int) -> list[ProspectCandidate]:
        candidates: list[ProspectCandidate] = []
        seen: set[str] = set()
        for index, item in enumerate(items[:limit], start=1):
            company = str(item.get("company") or item.get("name") or "").strip()
            if not company:
                continue
            domain = item.get("domain") or item.get("website_url") or None
            key = str(domain or company).strip().lower()
            if key in seen:
                continue
            seen.add(key)
            account = ApolloAccount(
                id=f"openai-web-{signal.id}-{index}",
                name=company,
                domain=domain,
                industry=item.get("industry") or None,
                employee_count=ClaudeApolloProspector._parse_employee_count(item.get("employee_count") or item.get("size")),
                technologies=[signal.competitor_name],
                raw=item,
            )
            source_notes = []
            if isinstance(item.get("source_notes"), list):
                source_notes = [str(note) for note in item.get("source_notes", []) if str(note).strip()]
            candidates.append(
                ProspectCandidate(
                    account=account,
                    contacts=[],
                    impact_summary=str(item.get("impact_summary") or "").strip(),
                    competitor_usage_confidence=str(item.get("competitor_usage_confidence") or "unknown"),
                    source_notes=source_notes,
                )
            )
        return candidates
