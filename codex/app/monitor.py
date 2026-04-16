from __future__ import annotations

import logging

from .claude_signals import ClaudeSignalDiscovery
from .demo_data import demo_signal
from .gemini import GeminiReasoner
from .models import Competitor, CompetitorSignal

logger = logging.getLogger(__name__)


class CompetitorMonitor:
    def __init__(
        self,
        reasoner: GeminiReasoner,
        demo_mode: bool = True,
        claude_signal_discovery: ClaudeSignalDiscovery | None = None,
    ):
        self.reasoner = reasoner
        self.demo_mode = demo_mode
        self.claude_signal_discovery = claude_signal_discovery

    def discover_signals(self, competitor: Competitor) -> list[CompetitorSignal]:
        if self.demo_mode:
            return [demo_signal(competitor)]
        evidence_items = []
        if self.claude_signal_discovery:
            try:
                evidence_items = self.claude_signal_discovery.discover_evidence(competitor)
            except Exception as exc:
                logger.exception("claude_signal_discovery.failed competitor=%s error=%s", competitor.name, exc)
                evidence_items = []
        if not evidence_items:
            logger.warning("competitor_monitor.no_article_backed_signals competitor=%s", competitor.name)
            return []
        return [self.reasoner.classify_signal(competitor, evidence) for evidence in evidence_items]
