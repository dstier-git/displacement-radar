from __future__ import annotations

from .apollo import ApolloClient
from .campaign import CampaignGenerator, OpportunityScorer
from .claude_discovery import ClaudeCompetitorDiscovery, DiscoveryResult
from .demo_data import demo_competitors
from .models import ApolloContact, CampaignDraft, CompanyProfile, Competitor, ScanResult
from .monitor import CompetitorMonitor
from .prospecting import ClaudeApolloProspector, ProspectCandidate
from .storage import Repository


class DisplacementAgent:
    def __init__(
        self,
        repository: Repository,
        monitor: CompetitorMonitor,
        apollo: ApolloClient,
        scorer: OpportunityScorer,
        campaign_generator: CampaignGenerator,
        prospector: ClaudeApolloProspector | None = None,
        max_competitors_per_scan: int = 4,
        max_customers_per_competitor: int = 5,
    ):
        self.repository = repository
        self.monitor = monitor
        self.apollo = apollo
        self.scorer = scorer
        self.campaign_generator = campaign_generator
        self.prospector = prospector
        self.max_competitors_per_scan = max(1, max_competitors_per_scan)
        self.max_customers_per_competitor = max(1, max_customers_per_competitor)

    def seed_demo_if_empty(self) -> None:
        if self.repository.list_competitors():
            return
        if not self.repository.get_company_profile():
            self.repository.save_company_profile(self._demo_company())
        for competitor in demo_competitors():
            self.repository.save_competitor(competitor)

    @staticmethod
    def _demo_company() -> CompanyProfile:
        return CompanyProfile(
            company_name="Apollo",
            category="Sales intelligence",
            positioning="An AI-guided go-to-market platform for data, intent, and outreach.",
        )

    def discover_company(self, company_name: str, discovery: ClaudeCompetitorDiscovery) -> DiscoveryResult:
        result = discovery.discover(company_name)
        self.repository.save_company_profile(result.company)
        existing = {competitor.name.strip().lower() for competitor in self.repository.list_competitors()}
        for competitor in result.competitors:
            if competitor.name.strip().lower() not in existing:
                self.repository.save_competitor(competitor)
                existing.add(competitor.name.strip().lower())
        return result

    def add_competitor(
        self,
        name: str,
        category: str = "",
        product_positioning: str = "",
        technology_uid: str | None = None,
        customer_domains: list[str] | None = None,
    ) -> Competitor:
        competitor = Competitor(
            name=name,
            category=category,
            product_positioning=product_positioning,
            technology_uid=technology_uid or None,
            customer_domains=customer_domains or [],
        )
        self.repository.save_competitor(competitor)
        return competitor

    def run_scan(self) -> ScanResult:
        competitors = self.repository.list_competitors()[: self.max_competitors_per_scan]
        signals_created = opportunities_created = campaigns_created = 0

        for competitor in competitors:
            for signal in self.monitor.discover_signals(competitor):
                existing_signal = self.repository.find_signal_by_fingerprint(signal.competitor_id, signal.headline)
                if existing_signal:
                    signal = existing_signal
                else:
                    self.repository.save_signal(signal)
                    signals_created += 1

                before = len(self.repository.list_opportunities(signal_id=signal.id))
                self.find_impacted_customers(signal.id)
                after = len(self.repository.list_opportunities(signal_id=signal.id))
                opportunities_created += max(0, after - before)

        result = ScanResult(
            competitors_scanned=len(competitors),
            signals_created=signals_created,
            opportunities_created=opportunities_created,
            campaigns_created=campaigns_created,
        )
        self.repository.save_scan_result(result)
        return result

    def find_decision_makers(self, opportunity_id: str) -> list[ApolloContact]:
        opportunity = self.repository.get_opportunity(opportunity_id)
        if not opportunity:
            raise ValueError("opportunity not found")
        signal = self.repository.get_signal(opportunity.signal_id)
        if not signal:
            raise ValueError("signal not found")
        contacts = self.apollo.search_contacts(opportunity.account, signal)[:8]
        opportunity.contacts = contacts
        opportunity.primary_contact_id = self._primary_contact_id(contacts)
        self.repository.save_opportunity(opportunity)
        return contacts

    def find_impacted_customers(self, signal_id: str) -> list:
        signal = self.repository.get_signal(signal_id)
        if not signal:
            raise ValueError("signal not found")
        competitor = self._get_competitor_for_signal(signal.competitor_id)
        if not competitor:
            raise ValueError("competitor not found")

        candidates: list[ProspectCandidate] = []
        if self.prospector and not self.apollo.demo_mode:
            try:
                candidates = self.prospector.find_impacted_customers(
                    signal,
                    competitor,
                    self.repository.get_company_profile(),
                    limit=self.max_customers_per_competitor,
                )
            except Exception:
                candidates = []

        if not candidates and (self.apollo.demo_mode or self.apollo.api_key):
            try:
                accounts = self.apollo.search_accounts(competitor, signal)[: self.max_customers_per_competitor]
            except Exception:
                accounts = []
            candidates = []
            for account in accounts:
                try:
                    contacts = self.apollo.search_contacts(account, signal)[:5]
                except Exception:
                    contacts = []
                candidates.append(
                    ProspectCandidate(
                        account=account,
                        contacts=contacts,
                        impact_summary=(
                            f"{account.name} may be vulnerable to {signal.competitor_name}'s recent signal: "
                            f"{signal.pain_hypothesis} {signal.recommended_angle}"
                        ),
                        competitor_usage_confidence="verified"
                        if signal.competitor_name in account.technologies
                        else "likely",
                        source_notes=[f"Found through Apollo account/contact search for {signal.competitor_name}."],
                    )
                )

        opportunities = []
        for candidate in candidates:
            existing = self._find_opportunity(signal.id, candidate.account.domain or candidate.account.name)
            if existing:
                existing.contacts = candidate.contacts or existing.contacts
                existing.impact_summary = candidate.impact_summary or existing.impact_summary
                existing.primary_contact_id = self._primary_contact_id(existing.contacts)
                existing.competitor_usage_confidence = (
                    candidate.competitor_usage_confidence or existing.competitor_usage_confidence
                )
                existing.source_notes = candidate.source_notes or existing.source_notes
                self.repository.save_opportunity(existing)
                opportunities.append(existing)
                continue
            opportunity = self.scorer.score(signal, candidate.account, candidate.contacts)
            opportunity.impact_summary = candidate.impact_summary or opportunity.impact_summary
            opportunity.primary_contact_id = self._primary_contact_id(candidate.contacts)
            opportunity.competitor_usage_confidence = candidate.competitor_usage_confidence or "unknown"
            opportunity.source_notes = candidate.source_notes or opportunity.source_notes
            self.repository.save_opportunity(opportunity)
            opportunities.append(opportunity)
        return opportunities

    def generate_emails_for_contacts(self, opportunity_id: str, contact_ids: list[str]) -> list[CampaignDraft]:
        opportunity = self.repository.get_opportunity(opportunity_id)
        if not opportunity:
            raise ValueError("opportunity not found")
        signal = self.repository.get_signal(opportunity.signal_id)
        if not signal:
            raise ValueError("signal not found")
        company = self.repository.get_company_profile()
        by_id = {contact.id or contact.full_name: contact for contact in opportunity.contacts}
        selected = [by_id[contact_id] for contact_id in contact_ids if contact_id in by_id]
        drafts: list[CampaignDraft] = []
        for contact in selected:
            if self._campaign_exists_for_contact(opportunity.id, contact):
                continue
            draft = self.campaign_generator.generate_email_for_contact(signal, opportunity, contact, company)
            self.repository.save_campaign(draft)
            drafts.append(draft)
        return drafts

    def generate_signal_emails(self, signal_id: str, selected_contact_keys: list[str]) -> list[CampaignDraft]:
        signal = self.repository.get_signal(signal_id)
        if not signal:
            raise ValueError("signal not found")
        selected = set(selected_contact_keys)
        drafts: list[CampaignDraft] = []
        for opportunity in self.repository.list_opportunities(signal_id=signal.id):
            contacts = opportunity.contacts or self.find_decision_makers(opportunity.id)
            for contact in contacts:
                contact_key = self._signal_contact_key(opportunity.id, contact)
                if contact_key not in selected:
                    continue
                if self._campaign_exists_for_contact(opportunity.id, contact):
                    continue
                company = self.repository.get_company_profile()
                draft = self.campaign_generator.generate_email_for_contact(signal, opportunity, contact, company)
                self.repository.save_campaign(draft)
                drafts.append(draft)
        return drafts

    def _opportunity_exists(self, signal_id: str, account_key: str) -> bool:
        return self._find_opportunity(signal_id, account_key) is not None

    def _find_opportunity(self, signal_id: str, account_key: str):
        normalized = account_key.strip().lower()
        for opportunity in self.repository.list_opportunities(signal_id=signal_id):
            existing = (opportunity.account.domain or opportunity.account.name).strip().lower()
            if existing == normalized:
                return opportunity
        return None

    def _campaign_exists_for_contact(self, opportunity_id: str, contact: ApolloContact) -> bool:
        contact_key = contact.id or contact.full_name
        for campaign in self.repository.list_campaigns(opportunity_id=opportunity_id):
            if campaign.contact and (campaign.contact.id or campaign.contact.full_name) == contact_key:
                return True
        return False

    def _get_competitor_for_signal(self, competitor_id: str) -> Competitor | None:
        for competitor in self.repository.list_competitors():
            if competitor.id == competitor_id:
                return competitor
        return None

    @staticmethod
    def _primary_contact_id(contacts: list[ApolloContact]) -> str | None:
        if not contacts:
            return None
        primary = contacts[0]
        return primary.id or primary.full_name

    @staticmethod
    def _signal_contact_key(opportunity_id: str, contact: ApolloContact) -> str:
        return f"{opportunity_id}::{contact.id or contact.full_name}"
