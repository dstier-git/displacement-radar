from __future__ import annotations

import json
from pathlib import Path
from threading import RLock
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel

from .models import CampaignDraft, Competitor, CompetitorSignal, Opportunity, ScanResult

T = TypeVar("T", bound=BaseModel)


def document_key(document: BaseModel) -> str:
    return str(getattr(document, "id", None) or getattr(document, "scan_run_id"))


class Store(Protocol):
    def put(self, collection: str, document: BaseModel) -> None: ...
    def get_all(self, collection: str, model: type[T]) -> list[T]: ...
    def get(self, collection: str, document_id: str, model: type[T]) -> T | None: ...


class JsonStore:
    """Tiny JSON document store used locally and in hackathon demos."""

    def __init__(self, path: Path):
        self.path = path
        self._lock = RLock()
        self._data = self._load()

    def _load(self) -> dict[str, dict[str, dict]]:
        if not self.path.exists():
            return self._empty()
        with self.path.open("r", encoding="utf-8") as handle:
            loaded = json.load(handle)
        empty = self._empty()
        empty.update({key: value for key, value in loaded.items() if isinstance(value, dict)})
        return empty

    @staticmethod
    def _empty() -> dict[str, dict[str, dict]]:
        return {
            "competitors": {},
            "signals": {},
            "opportunities": {},
            "campaign_drafts": {},
            "scan_runs": {},
        }

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as handle:
            json.dump(self._data, handle, indent=2, sort_keys=True)

    def put(self, collection: str, document: BaseModel) -> None:
        with self._lock:
            self._data.setdefault(collection, {})[document_key(document)] = document.model_dump(mode="json")
            self._save()

    def get_all(self, collection: str, model: type[T]) -> list[T]:
        with self._lock:
            return [model.model_validate(item) for item in self._data.get(collection, {}).values()]

    def get(self, collection: str, document_id: str, model: type[T]) -> T | None:
        with self._lock:
            item = self._data.get(collection, {}).get(document_id)
        return model.model_validate(item) if item else None

    def clear(self) -> None:
        with self._lock:
            self._data = self._empty()
            self._save()


class FirestoreStore:
    """Firestore-backed store for Cloud Run deployments.

    Import is deferred so local demo/test environments do not need Google Cloud
    packages installed unless they opt into Firestore.
    """

    def __init__(self, project: str | None, database: str | None = None):
        try:
            from google.cloud import firestore  # type: ignore
        except ImportError as exc:  # pragma: no cover - exercised only without optional deps
            raise RuntimeError("google-cloud-firestore is required for FIRESTORE_DATABASE") from exc
        kwargs: dict[str, Any] = {}
        if project:
            kwargs["project"] = project
        if database:
            kwargs["database"] = database
        self.client = firestore.Client(**kwargs)

    def put(self, collection: str, document: BaseModel) -> None:
        self.client.collection(collection).document(document_key(document)).set(document.model_dump(mode="json"))

    def get_all(self, collection: str, model: type[T]) -> list[T]:
        return [model.model_validate(snapshot.to_dict()) for snapshot in self.client.collection(collection).stream()]

    def get(self, collection: str, document_id: str, model: type[T]) -> T | None:
        snapshot = self.client.collection(collection).document(document_id).get()
        return model.model_validate(snapshot.to_dict()) if snapshot.exists else None


class Repository:
    def __init__(self, store: Store):
        self.store = store

    def save_competitor(self, competitor: Competitor) -> None:
        self.store.put("competitors", competitor)

    def list_competitors(self) -> list[Competitor]:
        return sorted(self.store.get_all("competitors", Competitor), key=lambda item: item.created_at)

    def save_signal(self, signal: CompetitorSignal) -> None:
        if self.find_signal_by_fingerprint(signal.competitor_id, signal.headline):
            return
        self.store.put("signals", signal)

    def list_signals(self) -> list[CompetitorSignal]:
        return sorted(self.store.get_all("signals", CompetitorSignal), key=lambda item: item.detected_at, reverse=True)

    def get_signal(self, signal_id: str) -> CompetitorSignal | None:
        return self.store.get("signals", signal_id, CompetitorSignal)

    def find_signal_by_fingerprint(self, competitor_id: str, headline: str) -> CompetitorSignal | None:
        normalized = headline.strip().lower()
        for signal in self.list_signals():
            if signal.competitor_id == competitor_id and signal.headline.strip().lower() == normalized:
                return signal
        return None

    def save_opportunity(self, opportunity: Opportunity) -> None:
        self.store.put("opportunities", opportunity)

    def list_opportunities(self, signal_id: str | None = None) -> list[Opportunity]:
        opportunities = self.store.get_all("opportunities", Opportunity)
        if signal_id:
            opportunities = [item for item in opportunities if item.signal_id == signal_id]
        return sorted(opportunities, key=lambda item: item.fit_score, reverse=True)

    def get_opportunity(self, opportunity_id: str) -> Opportunity | None:
        return self.store.get("opportunities", opportunity_id, Opportunity)

    def save_campaign(self, campaign: CampaignDraft) -> None:
        self.store.put("campaign_drafts", campaign)

    def list_campaigns(self, opportunity_id: str | None = None) -> list[CampaignDraft]:
        campaigns = self.store.get_all("campaign_drafts", CampaignDraft)
        if opportunity_id:
            campaigns = [item for item in campaigns if item.opportunity_id == opportunity_id]
        return sorted(campaigns, key=lambda item: item.created_at, reverse=True)

    def get_campaign(self, campaign_id: str) -> CampaignDraft | None:
        return self.store.get("campaign_drafts", campaign_id, CampaignDraft)

    def save_scan_result(self, result: ScanResult) -> None:
        self.store.put("scan_runs", result)

    def list_scan_runs(self) -> list[ScanResult]:
        return sorted(self.store.get_all("scan_runs", ScanResult), key=lambda item: item.created_at, reverse=True)
