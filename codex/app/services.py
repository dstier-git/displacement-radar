from __future__ import annotations

from .apollo import ApolloClient
from .campaign import CampaignGenerator, OpportunityScorer
from .demo_data import demo_competitors
from .models import Competitor, ScanResult
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
        for competitor in demo_competitors():
            self.repository.save_competitor(competitor)

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
                    campaign = self.campaign_generator.generate(signal, opportunity)
                    self.repository.save_campaign(campaign)
                    campaigns_created += 1

        result = ScanResult(
            competitors_scanned=len(competitors),
            signals_created=signals_created,
            opportunities_created=opportunities_created,
            campaigns_created=campaigns_created,
        )
        self.repository.save_scan_result(result)
        return result

    def _opportunity_exists(self, signal_id: str, account_key: str) -> bool:
        normalized = account_key.strip().lower()
        for opportunity in self.repository.list_opportunities(signal_id=signal_id):
            existing = (opportunity.account.domain or opportunity.account.name).strip().lower()
            if existing == normalized:
                return True
        return False
