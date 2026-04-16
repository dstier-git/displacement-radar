from __future__ import annotations

from .demo_data import demo_signal
from .gemini import GeminiReasoner
from .models import Competitor, CompetitorSignal


class CompetitorMonitor:
    def __init__(self, reasoner: GeminiReasoner, demo_mode: bool = True):
        self.reasoner = reasoner
        self.demo_mode = demo_mode

    def discover_signals(self, competitor: Competitor) -> list[CompetitorSignal]:
        if self.demo_mode:
            return [demo_signal(competitor)]
        evidence_items = self.reasoner.discover_grounded_evidence(competitor)
        return [self.reasoner.classify_signal(competitor, evidence) for evidence in evidence_items]
