from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from typing import Callable

from .demo_data import demo_competitors
from .models import CompanyProfile, Competitor

Runner = Callable[[list[str], str, int], str]


@dataclass(frozen=True)
class DiscoveryResult:
    company: CompanyProfile
    competitors: list[Competitor]
    source: str
    error: str = ""


class ClaudeCompetitorDiscovery:
    """Find competitors from only the seller company name via Claude CLI/MCP.

    Claude MCP access is user-authorized outside this app, so this service shells
    out to the local Claude CLI instead of embedding Apollo/Claude credentials.
    The result contract is strict JSON and the fallback keeps demos/test runs
    deterministic when Claude or MCP is unavailable.
    """

    def __init__(
        self,
        mcp_config: str | None = None,
        max_budget_usd: float | None = 0.25,
        timeout_seconds: int = 45,
        runner: Runner | None = None,
    ):
        self.mcp_config = mcp_config
        self.max_budget_usd = max_budget_usd
        self.timeout_seconds = timeout_seconds
        self.runner = runner or self._run_claude

    def discover(self, company_name: str) -> DiscoveryResult:
        company = CompanyProfile(company_name=company_name)
        try:
            raw = self.runner(self._command(), self._prompt(company.company_name), self.timeout_seconds)
            payload = self._parse_object(raw)
            company = self._parse_company(company.company_name, payload)
            competitors = self._parse_competitors(payload)
            if competitors:
                return DiscoveryResult(company=company, competitors=competitors, source="claude")
            raise ValueError("Claude returned no competitors")
        except Exception as exc:
            competitors = self._fallback_competitors(company.company_name)
            return DiscoveryResult(company=company, competitors=competitors, source="fallback", error=str(exc))

    def _command(self) -> list[str]:
        # `-p` is appended by the runner so it always directly precedes the prompt.
        command = ["claude", "--output-format", "text", "--permission-mode", "dontAsk"]
        if self.max_budget_usd is not None:
            command.extend(["--max-budget-usd", str(self.max_budget_usd)])
        if self.mcp_config:
            command.extend(["--mcp-config", self.mcp_config])
        return command

    @staticmethod
    def _prompt(company_name: str) -> str:
        return f"""Use Claude MCP tools if available, especially Apollo/company data tools, to identify the most relevant B2B competitors for this seller company: {company_name}.

Return ONLY strict JSON with no markdown and this shape:
{{
  "company": {{
    "company_name": "{company_name}",
    "category": "short market category",
    "positioning": "one-sentence value proposition or best inference",
    "website": "https://... or null"
  }},
  "competitors": [
    {{
      "name": "Competitor name",
      "category": "same/adjacent category",
      "product_positioning": "why customers compare them",
      "customer_domains": ["example.com"],
      "technology_uid": null
    }}
  ]
}}

Choose 3-5 competitors. Prefer real competitors, but omit fields rather than inventing private data. Do not create records or write to Apollo."""

    @staticmethod
    def _run_claude(command: list[str], prompt: str, timeout_seconds: int) -> str:
        completed = subprocess.run([*command, "-p", prompt], capture_output=True, text=True, timeout=timeout_seconds)
        if completed.returncode != 0:
            stderr = (completed.stderr or "").strip()
            stdout = (completed.stdout or "").strip()
            raise RuntimeError(f"claude CLI failed (exit={completed.returncode}). stderr={stderr!r} stdout={stdout!r}")
        return completed.stdout

    @classmethod
    def _parse_object(cls, text: str) -> dict:
        cleaned = text.strip()
        code_block_start = cleaned.find("```")
        if code_block_start >= 0:
            cleaned = cleaned[code_block_start + 3 :]
            if cleaned.lstrip().startswith("json"):
                cleaned = cleaned.lstrip()[4:]
            code_block_end = cleaned.find("```")
            if code_block_end >= 0:
                cleaned = cleaned[:code_block_end]
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start < 0 or end < start:
            raise ValueError("Claude output did not contain a JSON object")
        data = json.loads(cleaned[start : end + 1])
        if not isinstance(data, dict):
            raise ValueError("Claude output JSON must be an object")
        return data

    @staticmethod
    def _parse_company(default_name: str, payload: dict) -> CompanyProfile:
        company_data = payload.get("company") if isinstance(payload.get("company"), dict) else {}
        return CompanyProfile(
            company_name=str(company_data.get("company_name") or default_name),
            category=str(company_data.get("category") or ""),
            positioning=str(company_data.get("positioning") or ""),
            website=company_data.get("website") or None,
        )

    @staticmethod
    def _parse_competitors(payload: dict) -> list[Competitor]:
        raw_competitors = payload.get("competitors") or []
        if not isinstance(raw_competitors, list):
            raise ValueError("competitors must be a list")
        competitors: list[Competitor] = []
        seen: set[str] = set()
        for item in raw_competitors:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            key = name.lower()
            if not name or key in seen:
                continue
            seen.add(key)
            domains = item.get("customer_domains") or []
            if not isinstance(domains, list):
                domains = []
            competitors.append(
                Competitor(
                    name=name,
                    category=str(item.get("category") or ""),
                    product_positioning=str(item.get("product_positioning") or item.get("positioning") or ""),
                    technology_uid=item.get("technology_uid") or None,
                    customer_domains=[str(domain).strip() for domain in domains if str(domain).strip()],
                )
            )
        return competitors

    @staticmethod
    def _fallback_competitors(company_name: str) -> list[Competitor]:
        competitors = demo_competitors()
        for competitor in competitors:
            competitor.product_positioning = (
                competitor.product_positioning
                or f"Likely compared by buyers evaluating alternatives to {company_name}."
            )
        return competitors
