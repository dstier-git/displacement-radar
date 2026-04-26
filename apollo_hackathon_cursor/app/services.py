from __future__ import annotations

from .apollo import ApolloClient
from .campaign import CampaignGenerator, OpportunityScorer
from .claude_discovery import ClaudeCompetitorDiscovery, DiscoveryResult
from .demo_data import demo_competitors
from .models import ApolloContact, CampaignDraft, CompanyProfile, Competitor, ScanResult
from .monitor import CompetitorMonitor
from .storage import Repository


class DisplacementAgent:
    def __init__(
        self,
        repository: Repository,
        monitor: CompetitorMonitor,
        apollo: ApolloClient,
        scorer: OpportunityScorer,
        campaign_generator: CampaignGenerator,
    ):
        self.repository = repository
        self.monitor = monitor
        self.apollo = apollo
        self.scorer = scorer
        self.campaign_generator = campaign_generator

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
        competitors = self.repository.list_competitors()
        signals_created = opportunities_created = campaigns_created = 0

        for competitor in competitors:
            for signal in self.monitor.discover_signals(competitor):
                existing_signal = self.repository.find_signal_by_fingerprint(signal.competitor_id, signal.headline)
                if existing_signal:
                    signal = existing_signal
                else:
                    self.repository.save_signal(signal)
                    signals_created += 1

                for account in self.apollo.search_accounts(competitor, signal)[:5]:
                    contacts = self.apollo.search_contacts(account, signal)[:3]
                    opportunity = self.scorer.score(signal, account, contacts)
                    if self._opportunity_exists(signal.id, account.domain or account.name):
                        continue
                    self.repository.save_opportunity(opportunity)
                    opportunities_created += 1

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
        self.repository.save_opportunity(opportunity)
        return contacts

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

    def _opportunity_exists(self, signal_id: str, account_key: str) -> bool:
        normalized = account_key.strip().lower()
        for opportunity in self.repository.list_opportunities(signal_id=signal_id):
            existing = (opportunity.account.domain or opportunity.account.name).strip().lower()
            if existing == normalized:
                return True
        return False

    def _campaign_exists_for_contact(self, opportunity_id: str, contact: ApolloContact) -> bool:
        contact_key = contact.id or contact.full_name
        for campaign in self.repository.list_campaigns(opportunity_id=opportunity_id):
            if campaign.contact and (campaign.contact.id or campaign.contact.full_name) == contact_key:
                return True
        return False
