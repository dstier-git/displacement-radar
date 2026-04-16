from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from .models import Competitor, CompetitorSignal, Opportunity, Severity
from .storage import Repository


@dataclass(frozen=True)
class CompetitorChange:
    competitor_name: str
    current_signals: int
    previous_signals: int
    signal_delta: int
    current_opportunities: int
    previous_opportunities: int
    opportunity_delta: int
    avg_urgency: int


class CompetitiveLandscapeReportGenerator:
    """Builds markdown reports with Mermaid graphs for competitive motion."""

    def __init__(self, repository: Repository, now: datetime | None = None):
        self.repository = repository
        self.now = now or datetime.now(timezone.utc)
        if self.now.tzinfo is None:
            self.now = self.now.replace(tzinfo=timezone.utc)

    def generate(self) -> str:
        competitors = self.repository.list_competitors()
        signals = self.repository.list_signals()
        opportunities = self.repository.list_opportunities()
        changes = self._competitor_changes(competitors, signals, opportunities)
        last_30_signals = self._signals_between(signals, self.now - timedelta(days=30), self.now)
        last_30_opportunities = self._opportunities_between(opportunities, self.now - timedelta(days=30), self.now)
        top_opportunities = sorted(last_30_opportunities or opportunities, key=lambda item: item.fit_score, reverse=True)[:10]

        lines = [
            "# Competitive Landscape Report",
            "",
            f"Generated: {self.now.date().isoformat()}",
            "Window: trailing 30 days compared with the previous 30 days.",
            "",
            "## Executive Summary",
            "",
            f"- Watched competitors: **{len(competitors)}**",
            f"- New/active signals in the last 30 days: **{len(last_30_signals)}**",
            f"- Pipeline opportunities created in the last 30 days: **{len(last_30_opportunities)}**",
            f"- Highest-pressure competitor: **{self._highest_pressure_competitor(changes)}**",
            "",
            "## Competitor Movement Table",
            "",
            "| Competitor | Signals (30d) | Δ Signals | Opportunities (30d) | Δ Opportunities | Avg urgency |",
            "|---|---:|---:|---:|---:|---:|",
        ]
        lines.extend(self._movement_rows(changes))
        lines.extend(
            [
                "",
                "## Competitive Landscape Graph",
                "",
                "```mermaid",
                self._landscape_graph(competitors, signals, top_opportunities),
                "```",
                "",
                "## Last-Month Change Graph",
                "",
                "```mermaid",
                self._change_graph(changes),
                "```",
                "",
                "## Signal Mix Graph",
                "",
                "```mermaid",
                self._signal_mix_graph(last_30_signals),
                "```",
                "",
                "## Notable Last-30-Day Signals",
                "",
            ]
        )
        lines.extend(self._signal_bullets(last_30_signals))
        lines.extend(
            [
                "",
                "## Top Displacement Opportunities",
                "",
            ]
        )
        lines.extend(self._opportunity_bullets(top_opportunities))
        lines.extend(
            [
                "",
                "## Recommended Plays",
                "",
                "- Prioritize competitors with positive signal and opportunity deltas; they show fresh market movement.",
                "- Use high-urgency price, outage, and executive-departure signals for fast, pain-specific outreach.",
                "- Keep Apollo Claude execution in draft/review mode until a human validates sources and contacts.",
                "",
            ]
        )
        return "\n".join(lines)

    def _competitor_changes(
        self,
        competitors: list[Competitor],
        signals: list[CompetitorSignal],
        opportunities: list[Opportunity],
    ) -> list[CompetitorChange]:
        current_start = self.now - timedelta(days=30)
        previous_start = self.now - timedelta(days=60)
        current_signals = self._signals_between(signals, current_start, self.now)
        previous_signals = self._signals_between(signals, previous_start, current_start)
        current_opportunities = self._opportunities_between(opportunities, current_start, self.now)
        previous_opportunities = self._opportunities_between(opportunities, previous_start, current_start)

        current_signal_counts = Counter(signal.competitor_name for signal in current_signals)
        previous_signal_counts = Counter(signal.competitor_name for signal in previous_signals)
        current_opp_counts = Counter(self._signal_name_for_opportunity(opp, signals) for opp in current_opportunities)
        previous_opp_counts = Counter(self._signal_name_for_opportunity(opp, signals) for opp in previous_opportunities)
        urgency_by_competitor: dict[str, list[int]] = defaultdict(list)
        for signal in current_signals:
            urgency_by_competitor[signal.competitor_name].append(signal.urgency_score)

        names = {competitor.name for competitor in competitors}
        names.update(current_signal_counts)
        names.update(previous_signal_counts)
        changes = [
            CompetitorChange(
                competitor_name=name,
                current_signals=current_signal_counts[name],
                previous_signals=previous_signal_counts[name],
                signal_delta=current_signal_counts[name] - previous_signal_counts[name],
                current_opportunities=current_opp_counts[name],
                previous_opportunities=previous_opp_counts[name],
                opportunity_delta=current_opp_counts[name] - previous_opp_counts[name],
                avg_urgency=round(sum(urgency_by_competitor[name]) / len(urgency_by_competitor[name]))
                if urgency_by_competitor[name]
                else 0,
            )
            for name in sorted(names)
        ]
        return sorted(changes, key=lambda item: (item.current_signals + item.current_opportunities, item.avg_urgency), reverse=True)

    def _signals_between(self, signals: list[CompetitorSignal], start: datetime, end: datetime) -> list[CompetitorSignal]:
        return [signal for signal in signals if start <= self._aware(signal.detected_at) <= end]

    def _opportunities_between(self, opportunities: list[Opportunity], start: datetime, end: datetime) -> list[Opportunity]:
        return [opportunity for opportunity in opportunities if start <= self._aware(opportunity.created_at) <= end]

    @staticmethod
    def _aware(value: datetime) -> datetime:
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)

    @staticmethod
    def _signal_name_for_opportunity(opportunity: Opportunity, signals: list[CompetitorSignal]) -> str:
        for signal in signals:
            if signal.id == opportunity.signal_id:
                return signal.competitor_name
        return "Unknown"

    @staticmethod
    def _highest_pressure_competitor(changes: list[CompetitorChange]) -> str:
        if not changes:
            return "None yet"
        top = max(changes, key=lambda item: (item.current_signals * 3 + item.current_opportunities + item.avg_urgency / 20))
        return top.competitor_name if top.current_signals or top.current_opportunities else "None yet"

    @staticmethod
    def _movement_rows(changes: list[CompetitorChange]) -> list[str]:
        if not changes:
            return ["| No competitors yet | 0 | 0 | 0 | 0 | 0 |"]
        return [
            "| {name} | {signals} | {signal_delta:+d} | {opps} | {opp_delta:+d} | {urgency} |".format(
                name=change.competitor_name,
                signals=change.current_signals,
                signal_delta=change.signal_delta,
                opps=change.current_opportunities,
                opp_delta=change.opportunity_delta,
                urgency=change.avg_urgency,
            )
            for change in changes
        ]

    def _landscape_graph(
        self,
        competitors: list[Competitor],
        signals: list[CompetitorSignal],
        opportunities: list[Opportunity],
    ) -> str:
        if not competitors:
            return "flowchart LR\n    Market[Market] --> Empty[No competitors watched yet]"
        lines = ["flowchart LR", "    Seller[Our displacement offer] --> Market[Watched market]"]
        signal_by_competitor: dict[str, list[CompetitorSignal]] = defaultdict(list)
        for signal in signals:
            signal_by_competitor[signal.competitor_name].append(signal)
        opportunities_by_signal = defaultdict(list)
        for opportunity in opportunities:
            opportunities_by_signal[opportunity.signal_id].append(opportunity)

        for index, competitor in enumerate(competitors, start=1):
            competitor_id = f"C{index}"
            lines.append(f"    Market --> {competitor_id}[{self._mermaid_label(competitor.name)}]")
            lines.append(f"    {competitor_id} --> {competitor_id}Cat[{self._mermaid_label(competitor.category or 'Uncategorized')}]")
            for signal_index, signal in enumerate(signal_by_competitor.get(competitor.name, [])[:3], start=1):
                signal_id = f"{competitor_id}S{signal_index}"
                lines.append(
                    f"    {competitor_id} --> {signal_id}[{self._mermaid_label(signal.type.value.replace('_', ' '))}: {signal.urgency_score}/100]"
                )
                for opp_index, opportunity in enumerate(opportunities_by_signal.get(signal.id, [])[:2], start=1):
                    opp_id = f"{signal_id}O{opp_index}"
                    lines.append(f"    {signal_id} --> {opp_id}[{self._mermaid_label(opportunity.account.name)} · {opportunity.fit_score}]")
        return "\n".join(lines)

    @staticmethod
    def _change_graph(changes: list[CompetitorChange]) -> str:
        if not changes:
            return "xychart-beta\n    title \"Last 30 days movement\"\n    x-axis [\"None\"]\n    y-axis \"Count\" 0 --> 1\n    bar [0]"
        top = changes[:8]
        labels = ", ".join(f'"{CompetitiveLandscapeReportGenerator._short_label(item.competitor_name)}"' for item in top)
        signal_counts = ", ".join(str(item.current_signals) for item in top)
        opportunity_counts = ", ".join(str(item.current_opportunities) for item in top)
        max_value = max([1, *(item.current_signals for item in top), *(item.current_opportunities for item in top)])
        return "\n".join(
            [
                "xychart-beta",
                '    title "Last 30 days: signals vs opportunities"',
                f"    x-axis [{labels}]",
                f'    y-axis "Count" 0 --> {max_value + 1}',
                f"    bar [{signal_counts}]",
                f"    line [{opportunity_counts}]",
            ]
        )

    @staticmethod
    def _signal_mix_graph(signals: list[CompetitorSignal]) -> str:
        if not signals:
            return 'pie title Last 30 days signal mix\n    "No signals" : 1'
        counts = Counter(signal.type.value.replace("_", " ") for signal in signals)
        lines = ["pie title Last 30 days signal mix"]
        lines.extend(f'    "{label}" : {count}' for label, count in sorted(counts.items()))
        return "\n".join(lines)

    @staticmethod
    def _signal_bullets(signals: list[CompetitorSignal]) -> list[str]:
        if not signals:
            return ["- No competitor signals were detected in the last 30 days."]
        severity_rank = {Severity.CRITICAL: 4, Severity.HIGH: 3, Severity.MEDIUM: 2, Severity.LOW: 1}
        ranked = sorted(signals, key=lambda item: (severity_rank[item.severity], item.urgency_score), reverse=True)[:10]
        return [
            f"- **{signal.competitor_name}** — {signal.headline} ({signal.type.value.replace('_', ' ')}, {signal.severity.value}, urgency {signal.urgency_score}/100)"
            for signal in ranked
        ]

    @staticmethod
    def _opportunity_bullets(opportunities: list[Opportunity]) -> list[str]:
        if not opportunities:
            return ["- No displacement opportunities have been created yet."]
        return [
            f"- **{opportunity.account.name}** ({opportunity.fit_score}/100): {opportunity.displacement_rationale}"
            for opportunity in opportunities[:10]
        ]

    @staticmethod
    def _mermaid_label(value: str) -> str:
        cleaned = re.sub(r"[\[\]{}|<>]", "", value).replace('"', "'")
        return cleaned[:80] or "Unknown"

    @staticmethod
    def _short_label(value: str) -> str:
        cleaned = re.sub(r"[^A-Za-z0-9 ]", "", value).strip()
        return (cleaned[:14] + "…") if len(cleaned) > 15 else (cleaned or "Unknown")
