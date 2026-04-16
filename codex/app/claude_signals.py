from __future__ import annotations

import json
import logging
import re
import subprocess
from datetime import datetime
from typing import Callable

from .models import Competitor, SourceEvidence

Runner = Callable[[list[str], str, int], str]
logger = logging.getLogger(__name__)


class ClaudeSignalDiscovery:
    """Find article-backed competitor displacement signals through Claude CLI."""

    def __init__(
        self,
        max_budget_usd: float | None = 0.25,
        timeout_seconds: int = 60,
        runner: Runner | None = None,
    ):
        self.max_budget_usd = max_budget_usd
        self.timeout_seconds = timeout_seconds
        self.runner = runner or self._run_claude

    def discover_evidence(self, competitor: Competitor, limit: int = 2) -> list[SourceEvidence]:
        raw = self.runner(self._command(), self._prompt(competitor, limit), self.timeout_seconds)
        logger.info(
            "claude_signal_discovery.raw_response competitor=%s chars=%s preview=%r",
            competitor.name,
            len(raw),
            raw[:500],
        )
        payload = self._parse_list(raw)
        evidence = self._parse_evidence(payload, limit)
        logger.info(
            "claude_signal_discovery.parsed competitor=%s raw_items=%s accepted_sources=%s urls=%s",
            competitor.name,
            len(payload),
            len(evidence),
            [item.url for item in evidence],
        )
        return evidence

    def _command(self) -> list[str]:
        command = ["claude", "-p", "--output-format", "text", "--permission-mode", "dontAsk"]
        if self.max_budget_usd is not None:
            command.extend(["--max-budget-usd", str(self.max_budget_usd)])
        return command

    @staticmethod
    def _prompt(competitor: Competitor, limit: int) -> str:
        return f"""Search the public web for recent article-backed competitor displacement signals for {competitor.name}.
Focus on pricing increases, outages, negative G2/review waves, executive departures, layoffs,
security incidents, acquisitions, feature removals, and contract complaints.

Rules:
- return only real source URLs from articles, status pages, review pages, official posts, or credible discussions
- do not invent sources
- if you cannot verify real URLs, return []
- prefer signals from the last 90 days
- limit to the {limit} strongest signals

Return ONLY strict JSON array, no markdown:
[
  {{
    "title": "source-backed headline",
    "url": "https://...",
    "snippet": "1-2 sentence source summary",
    "published_at": "YYYY-MM-DD or null"
  }}
]"""

    @staticmethod
    def _run_claude(command: list[str], prompt: str, timeout_seconds: int) -> str:
        completed = subprocess.run(
            [*command, prompt],
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
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
    def _parse_evidence(items: list[dict], limit: int) -> list[SourceEvidence]:
        evidence: list[SourceEvidence] = []
        seen: set[str] = set()
        for item in items:
            url = str(item.get("url") or "").strip()
            if not url.startswith(("http://", "https://")) or url in seen:
                continue
            title = str(item.get("title") or "").strip()
            snippet = str(item.get("snippet") or "").strip()
            if not title or not snippet:
                continue
            seen.add(url)
            evidence.append(
                SourceEvidence(
                    title=title,
                    url=url,
                    snippet=snippet,
                    published_at=ClaudeSignalDiscovery._parse_date(item.get("published_at")),
                )
            )
            if len(evidence) >= limit:
                break
        return evidence

    @staticmethod
    def _parse_date(value: object) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
