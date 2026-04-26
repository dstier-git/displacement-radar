from __future__ import annotations

from .gemini import GeminiReasoner
from .models import ApolloAccount, ApolloContact, CampaignDraft, CompanyProfile, CompetitorSignal, Opportunity


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
        return Opportunity(signal_id=signal.id, account=account, contacts=contacts, fit_score=fit_score, displacement_rationale=rationale)


class CampaignGenerator:
    def __init__(self, reasoner: GeminiReasoner):
        self.reasoner = reasoner

    def generate(self, signal: CompetitorSignal, opportunity: Opportunity) -> CampaignDraft:
        drafts = self.reasoner.draft_outreach({"signal": signal, "account": opportunity.account, "contacts": opportunity.contacts})
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
        seller = company.company_name if company else "our team"
        first_name = contact.first_name or contact.full_name.split(" ", 1)[0]
        body = (
            f"Hi {first_name} — saw {signal.headline}. "
            f"If {opportunity.account.name} is reviewing vendors, that usually means {signal.pain_hypothesis.lower()} "
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

    @staticmethod
    def apollo_claude_prompt(signal: CompetitorSignal, opportunity: Opportunity) -> str:
        contact_lines = "\n".join(
            f"- {contact.full_name}, {contact.title}, LinkedIn: {contact.linkedin_url or 'unknown'}"
            for contact in opportunity.contacts
        ) or "- Find 2-3 RevOps or sales leadership contacts"
        evidence_lines = "\n".join(f"- {item.title}: {item.url}" for item in signal.evidence)
        return f"""Use Apollo to review this draft-only displacement opportunity. Do not create contacts, write records, or enroll anyone in a sequence until I explicitly approve each action.

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

Please use Apollo to verify the account and contacts, suggest any better buyer personas, and prepare a sequence draft around the vulnerability. Keep it in draft/review mode only."""
