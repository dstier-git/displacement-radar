from __future__ import annotations

import json
from typing import Any

from .models import Competitor, CompetitorSignal, Severity, SignalType, SourceEvidence


SIGNAL_KEYWORDS: list[tuple[SignalType, list[str]]] = [
    (SignalType.PRICE_INCREASE, ["price", "pricing", "packaging", "renewal", "cost"]),
    (SignalType.OUTAGE, ["outage", "downtime", "incident", "status", "degraded"]),
    (SignalType.REVIEW_WAVE, ["review", "g2", "capterra", "complaint", "negative"]),
    (SignalType.EXECUTIVE_DEPARTURE, ["departure", "steps down", "resigns", "executive", "ceo", "cro"]),
    (SignalType.LAYOFFS, ["layoff", "restructuring", "downsizing", "cuts"]),
    (SignalType.CONTRACT_COMPLAINT, ["contract", "terms", "minimum", "lock-in", "renewal"]),
]


class GeminiReasoner:
    """Gemini wrapper with deterministic local fallback.

    In production this class can call Vertex AI Gemini with Google Search
    grounding. The fallback keeps tests and demos useful when cloud credentials
    are not available.
    """

    def __init__(self, project: str | None, location: str, model: str):
        self.project = project
        self.location = location
        self.model = model


    def discover_grounded_evidence(self, competitor: Competitor) -> list[SourceEvidence]:
        """Use Vertex AI Gemini with Google Search grounding when configured.

        Falls back to deterministic search-query placeholders if google-genai or
        Google Cloud credentials are unavailable, which keeps local demos and
        tests offline-friendly.
        """
        prompt = f"""Find recent public-web competitor displacement signals for {competitor.name}.
Focus on pricing increases, outages, negative G2/review waves, executive departures, layoffs, and contract complaints.
Return strict JSON only with this shape: [{{"title":"...", "url":"https://...", "snippet":"..."}}].
Limit to the 4 strongest signals and include source URLs.
"""
        try:
            from google import genai  # type: ignore
            from google.genai.types import GenerateContentConfig, GoogleSearch, HttpOptions, Tool  # type: ignore

            client = genai.Client(
                vertexai=True,
                project=self.project,
                location=self.location,
                http_options=HttpOptions(api_version="v1"),
            )
            response = client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=GenerateContentConfig(
                    temperature=1.0,
                    tools=[Tool(google_search=GoogleSearch())],
                ),
            )
            parsed = self._parse_json_list(response.text or "")
            evidence = [
                SourceEvidence(
                    title=str(item.get("title") or f"Signal for {competitor.name}"),
                    url=str(item.get("url") or f"https://www.google.com/search?q={competitor.name.replace(' ', '+')}"),
                    snippet=str(item.get("snippet") or "Grounded Google Search result."),
                )
                for item in parsed
                if isinstance(item, dict)
            ]
            if evidence:
                return evidence
        except Exception:
            # Cloud credentials, SDK availability, quota, or model output issues
            # should not block the hackathon demo path.
            pass

        return self._fallback_evidence(competitor)

    @staticmethod
    def _parse_json_list(text: str) -> list[dict[str, Any]]:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            if cleaned.startswith("json"):
                cleaned = cleaned[4:]
        start = cleaned.find("[")
        end = cleaned.rfind("]")
        if start >= 0 and end >= start:
            cleaned = cleaned[start : end + 1]
        data = json.loads(cleaned)
        return data if isinstance(data, list) else []

    @staticmethod
    def _fallback_evidence(competitor: Competitor) -> list[SourceEvidence]:
        queries = [
            f"{competitor.name} pricing increase customers",
            f"{competitor.name} outage incident status",
            f"{competitor.name} G2 negative reviews",
            f"{competitor.name} executive departure",
        ]
        return [
            SourceEvidence(
                title=f"Potential signal for {competitor.name}: {query}",
                url=f"https://www.google.com/search?q={query.replace(' ', '+')}",
                snippet="Grounded search candidate; configure Vertex AI grounding for live source extraction.",
            )
            for query in queries
        ]

    def classify_signal(self, competitor: Competitor, evidence: SourceEvidence) -> CompetitorSignal:
        payload = self._fallback_classification(competitor, evidence)
        return CompetitorSignal(
            competitor_id=competitor.id,
            competitor_name=competitor.name,
            type=payload["type"],
            severity=payload["severity"],
            urgency_score=payload["urgency_score"],
            headline=payload["headline"],
            pain_hypothesis=payload["pain_hypothesis"],
            recommended_angle=payload["recommended_angle"],
            evidence=[evidence],
        )

    def draft_outreach(self, context: dict[str, Any]) -> dict[str, str]:
        account = context["account"]
        signal = context["signal"]
        competitor = signal.competitor_name
        pain = signal.pain_hypothesis
        angle = signal.recommended_angle
        evidence_url = signal.evidence[0].url if signal.evidence else "the public signal"
        return {
            "subject": f"Quick idea after the {competitor} news",
            "email_body": (
                f"Hi {{first_name}},\n\n"
                f"Saw the recent {competitor} signal: {signal.headline}. For teams like {account.name}, "
                f"that usually means {pain.lower()}\n\n"
                f"{angle} We can map the migration surface and show whether there is a lower-risk path before renewal.\n\n"
                f"Worth a 15-minute displacement assessment this week?\n\n"
                f"Source: {evidence_url}"
            ),
            "linkedin_note": (
                f"Noticed the {competitor} news and thought {account.name} might be evaluating options. "
                "Happy to share a quick migration/risk checklist if useful."
            ),
            "call_opener": (
                f"I’m calling because {competitor} just had a public signal that often forces teams to re-check value before renewal. "
                f"Are you responsible for evaluating whether {account.name} should stay the course or compare alternatives?"
            ),
        }

    def _fallback_classification(self, competitor: Competitor, evidence: SourceEvidence) -> dict[str, Any]:
        text = f"{evidence.title} {evidence.snippet}".lower()
        signal_type = SignalType.OTHER
        for candidate, keywords in SIGNAL_KEYWORDS:
            if any(keyword in text for keyword in keywords):
                signal_type = candidate
                break
        severity = Severity.HIGH if signal_type in {SignalType.PRICE_INCREASE, SignalType.OUTAGE, SignalType.EXECUTIVE_DEPARTURE} else Severity.MEDIUM
        urgency = 82 if severity == Severity.HIGH else 62
        return {
            "type": signal_type,
            "severity": severity,
            "urgency_score": urgency,
            "headline": evidence.title or f"{competitor.name} competitive signal detected",
            "pain_hypothesis": self._pain_hypothesis(signal_type),
            "recommended_angle": self._recommended_angle(signal_type),
        }

    @staticmethod
    def _pain_hypothesis(signal_type: SignalType) -> str:
        return {
            SignalType.PRICE_INCREASE: "buyers are likely under pressure to justify renewal cost and compare lower-friction alternatives.",
            SignalType.OUTAGE: "operators may be questioning reliability, contingency plans, and vendor accountability.",
            SignalType.REVIEW_WAVE: "champions may be losing internal confidence because peers are surfacing similar complaints.",
            SignalType.EXECUTIVE_DEPARTURE: "customers may worry about roadmap continuity and account support stability.",
            SignalType.LAYOFFS: "customers may fear slower support and less product investment after restructuring.",
            SignalType.CONTRACT_COMPLAINT: "finance and procurement teams may be looking for leverage before the next renewal.",
            SignalType.OTHER: "customers may be open to a timely benchmark against alternatives.",
        }[signal_type]

    @staticmethod
    def _recommended_angle(signal_type: SignalType) -> str:
        return {
            SignalType.PRICE_INCREASE: "Offer a cost-neutral pilot and renewal benchmark.",
            SignalType.OUTAGE: "Offer a resilience comparison and migration risk review.",
            SignalType.REVIEW_WAVE: "Offer a peer-backed alternative workflow audit.",
            SignalType.EXECUTIVE_DEPARTURE: "Offer roadmap certainty and executive-alignment messaging.",
            SignalType.LAYOFFS: "Offer continuity, service quality, and support-risk mitigation.",
            SignalType.CONTRACT_COMPLAINT: "Offer contract flexibility and a switching-cost analysis.",
            SignalType.OTHER: "Offer a concise competitive benchmark tied to the public event.",
        }[signal_type]
