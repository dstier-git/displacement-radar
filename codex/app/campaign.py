from __future__ import annotations

import json
import re
import subprocess
from typing import Callable

from .gemini import GeminiReasoner
from .models import ApolloAccount, ApolloContact, CampaignDraft, CompanyProfile, CompetitorSignal, Opportunity

Runner = Callable[[list[str], str, int], str]


class OpportunityScorer:
    def score(self, signal: CompetitorSignal, account: ApolloAccount, contacts: list[ApolloContact]) -> Opportunity:
        technology_match = 20 if signal.competitor_name in account.technologies else 0
        contact_depth = min(len(contacts) * 10, 25)
        employee_fit = 20 if (account.employee_count or 0) >= 100 else 10
        urgency = int(signal.urgency_score * 0.35)
        fit_score = min(100, technology_match + contact_depth + employee_fit + urgency)
        rationale = (
            f"{account.name} appears exposed to {signal.competitor_name}; "
            f"the signal suggests {signal.pain_hypothesis} Apollo found {len(contacts)} relevant buyer personas."
        )
        primary_contact = contacts[0] if contacts else None
        return Opportunity(
            signal_id=signal.id,
            account=account,
            contacts=contacts,
            fit_score=fit_score,
            displacement_rationale=rationale,
            impact_summary=(
                f"{account.name} may need to reassess {signal.competitor_name} because {signal.pain_hypothesis} "
                f"{signal.recommended_angle}"
            ),
            primary_contact_id=(primary_contact.id or primary_contact.full_name) if primary_contact else None,
            competitor_usage_confidence="verified" if signal.competitor_name in account.technologies else "likely",
            source_notes=[f"Matched through Apollo account/contact search for {signal.competitor_name}."],
        )


class CampaignGenerator:
    def __init__(
        self,
        reasoner: GeminiReasoner,
        claude_runner: Runner | None = None,
        claude_mcp_config: str | None = None,
        claude_max_budget_usd: float | None = 0.25,
        claude_timeout_seconds: int = 45,
    ):
        self.reasoner = reasoner
        self.claude_runner = claude_runner
        self.claude_mcp_config = claude_mcp_config
        self.claude_max_budget_usd = claude_max_budget_usd
        self.claude_timeout_seconds = claude_timeout_seconds

    def generate(self, signal: CompetitorSignal, opportunity: Opportunity) -> CampaignDraft:
        drafts = self.reasoner.draft_outreach(
            {"signal": signal, "account": opportunity.account, "contacts": opportunity.contacts}
        )
        prompt = self.apollo_claude_prompt(signal, opportunity)
        return CampaignDraft(
            signal_id=signal.id,
            opportunity_id=opportunity.id,
            subject=drafts["subject"],
            email_body=drafts["email_body"],
            linkedin_note=drafts["linkedin_note"],
            call_opener=drafts["call_opener"],
            apollo_claude_prompt=prompt,
            evidence_urls=[item.url for item in signal.evidence],
        )

    def generate_email_for_contact(
        self,
        signal: CompetitorSignal,
        opportunity: Opportunity,
        contact: ApolloContact,
        company: CompanyProfile | None,
    ) -> CampaignDraft:
        claude_draft = self._generate_claude_email_for_contact(signal, opportunity, contact, company)
        if claude_draft:
            return claude_draft
        return self._fallback_email_for_contact(signal, opportunity, contact, company)

    def _fallback_email_for_contact(
        self,
        signal: CompetitorSignal,
        opportunity: Opportunity,
        contact: ApolloContact,
        company: CompanyProfile | None,
    ) -> CampaignDraft:
        seller = company.company_name if company else "our team"
        first_name = contact.first_name or contact.full_name.split(" ", 1)[0]
        account_pain = opportunity.impact_summary or opportunity.displacement_rationale
        body = (
            f"Hi {first_name} — saw {signal.headline}. "
            f"For {opportunity.account.name}, that could mean {account_pain.lower()} "
            "Open to a 15-minute chat this week? "
            f"{seller} can help your team compare risk, cost, and migration paths around this situation."
        )
        subject = f"After the {signal.competitor_name} news"
        if len(subject) > 60:
            subject = f"After {signal.competitor_name[:42]}..."
        return CampaignDraft(
            signal_id=signal.id,
            opportunity_id=opportunity.id,
            subject=subject,
            preview="Quick idea tied to the recent signal",
            email_body=body,
            linkedin_note=(
                f"Saw the {signal.competitor_name} signal and thought it might be relevant for "
                f"{opportunity.account.name}. Happy to share a quick benchmark."
            ),
            call_opener=(
                f"I’m calling because {signal.competitor_name} just had a public signal: {signal.headline}. "
                f"Are you looking at how that affects {opportunity.account.name}?"
            ),
            apollo_claude_prompt=self.apollo_claude_prompt(signal, opportunity),
            evidence_urls=[item.url for item in signal.evidence],
            contact=contact,
            seller_company_name=seller,
        )

    def _generate_claude_email_for_contact(
        self,
        signal: CompetitorSignal,
        opportunity: Opportunity,
        contact: ApolloContact,
        company: CompanyProfile | None,
    ) -> CampaignDraft | None:
        if not self.claude_runner:
            return None
        seller = company.company_name if company else "our team"
        prompt = self._claude_email_prompt(signal, opportunity, contact, company)
        try:
            raw = self.claude_runner(self._claude_command(), prompt, self.claude_timeout_seconds)
            parsed = self._parse_json_object(raw)
        except Exception:
            return None
        subject = str(parsed.get("subject") or f"After the {signal.competitor_name} news").strip()
        body = str(parsed.get("email_body") or parsed.get("body") or "").strip()
        if not body or len(body.split()) > 120:
            return None
        return CampaignDraft(
            signal_id=signal.id,
            opportunity_id=opportunity.id,
            subject=subject[:80],
            preview=str(parsed.get("preview") or "Quick idea tied to the recent signal").strip(),
            email_body=body,
            linkedin_note=str(parsed.get("linkedin_note") or self._default_linkedin_note(signal, opportunity)).strip(),
            call_opener=str(parsed.get("call_opener") or self._default_call_opener(signal, opportunity)).strip(),
            apollo_claude_prompt=self.apollo_claude_prompt(signal, opportunity),
            evidence_urls=[item.url for item in signal.evidence],
            contact=contact,
            seller_company_name=seller,
        )

    def _claude_command(self) -> list[str]:
        # `-p` is appended by the runner so it always directly precedes the prompt.
        command = ["claude", "--output-format", "text", "--permission-mode", "dontAsk"]
        if self.claude_max_budget_usd is not None:
            command.extend(["--max-budget-usd", str(self.claude_max_budget_usd)])
        if self.claude_mcp_config:
            command.extend(["--mcp-config", self.claude_mcp_config])
        return command

    @staticmethod
    def _run_claude(command: list[str], prompt: str, timeout_seconds: int) -> str:
        completed = subprocess.run([*command, "-p", prompt], capture_output=True, text=True, timeout=timeout_seconds)
        if completed.returncode != 0:
            return (completed.stdout or "") + ("\n" + completed.stderr if completed.stderr else "")
        return completed.stdout

    @staticmethod
    def _parse_json_object(text: str) -> dict:
        cleaned = re.sub(r"```[\w-]*\n?", "", text).replace("```", "").strip()
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start < 0 or end < start:
            raise ValueError("Claude output did not contain a JSON object")
        data = json.loads(cleaned[start : end + 1])
        if not isinstance(data, dict):
            raise ValueError("Claude output JSON must be an object")
        return data

    @staticmethod
    def _claude_email_prompt(
        signal: CompetitorSignal,
        opportunity: Opportunity,
        contact: ApolloContact,
        company: CompanyProfile | None,
    ) -> str:
        seller = company.company_name if company else "our team"
        positioning = company.positioning if company else ""
        evidence_lines = "\n".join(f"- {item.title}: {item.url}" for item in signal.evidence) or "- No evidence URL"
        return f"""Draft a reviewed cold outreach email. Do not send or create Apollo records.

Seller: {seller}
Seller positioning: {positioning or 'unknown'}
Recipient: {contact.full_name}, {contact.title or 'unknown title'} at {opportunity.account.name}
Recipient email status: {contact.email_status or 'unknown'}
Competitor signal: {signal.headline}
Signal context: {signal.pain_hypothesis}
Account impact summary: {opportunity.impact_summary or opportunity.displacement_rationale}
Recommended angle: {signal.recommended_angle}
Evidence:
{evidence_lines}

Rules:
- first sentence references the exact competitor signal
- email body under 100 words
- peer tone, no "hope you're well"
- one soft 15-20 minute CTA
- focus on why switching or comparing alternatives is timely

Return ONLY strict JSON:
{{
  "subject":"under 9 words",
  "preview":"15-word preview",
  "email_body":"full email with greeting and sign-off",
  "linkedin_note":"short LinkedIn note",
  "call_opener":"one sentence call opener"
}}"""

    @staticmethod
    def _default_linkedin_note(signal: CompetitorSignal, opportunity: Opportunity) -> str:
        return (
            f"Saw the {signal.competitor_name} signal and thought it might be relevant for "
            f"{opportunity.account.name}. Happy to share a quick benchmark."
        )

    @staticmethod
    def _default_call_opener(signal: CompetitorSignal, opportunity: Opportunity) -> str:
        return (
            f"I’m calling because {signal.competitor_name} just had a public signal: {signal.headline}. "
            f"Are you looking at how that affects {opportunity.account.name}?"
        )

    @staticmethod
    def apollo_claude_prompt(signal: CompetitorSignal, opportunity: Opportunity) -> str:
        contact_lines = "\n".join(
            f"- {contact.full_name}, {contact.title}, LinkedIn: {contact.linkedin_url or 'unknown'}"
            for contact in opportunity.contacts
        ) or "- Find 2-3 RevOps or sales leadership contacts"
        evidence_lines = "\n".join(f"- {item.title}: {item.url}" for item in signal.evidence)
        return f"""Use Apollo to review this draft-only displacement opportunity.
Do not create contacts, write records, or enroll anyone in a sequence until I explicitly approve each action.

Competitive signal:
- Competitor: {signal.competitor_name}
- Headline: {signal.headline}
- Pain hypothesis: {signal.pain_hypothesis}
- Recommended angle: {signal.recommended_angle}

Target account:
- Company: {opportunity.account.name}
- Domain: {opportunity.account.domain or 'unknown'}
- Fit score: {opportunity.fit_score}/100
- Rationale: {opportunity.displacement_rationale}

Candidate contacts from Apollo:
{contact_lines}

Evidence:
{evidence_lines}

Please use Apollo to verify the account and contacts, suggest any better buyer personas,
and prepare a sequence draft around the vulnerability. Keep it in draft/review mode only."""
