from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SignalType(str, Enum):
    PRICE_INCREASE = "price_increase"
    REVIEW_WAVE = "review_wave"
    EXECUTIVE_DEPARTURE = "executive_departure"
    OUTAGE = "outage"
    LAYOFFS = "layoffs"
    CONTRACT_COMPLAINT = "contract_complaint"
    OTHER = "other"


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Competitor(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    category: str = ""
    product_positioning: str = ""
    technology_uid: str | None = None
    customer_domains: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utcnow)

    @field_validator("name")
    @classmethod
    def name_required(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("competitor name is required")
        return value


class CompanyProfile(BaseModel):
    id: str = Field(default="current")
    company_name: str
    category: str = ""
    positioning: str = ""
    website: str | None = None
    created_at: datetime = Field(default_factory=utcnow)

    @field_validator("company_name")
    @classmethod
    def company_name_required(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("company name is required")
        return value


class SourceEvidence(BaseModel):
    title: str
    url: str
    snippet: str = ""
    published_at: datetime | None = None


class CompetitorSignal(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    competitor_id: str
    competitor_name: str
    type: SignalType
    severity: Severity
    urgency_score: int = Field(ge=0, le=100)
    headline: str
    pain_hypothesis: str
    recommended_angle: str
    evidence: list[SourceEvidence]
    detected_at: datetime = Field(default_factory=utcnow)


class ApolloAccount(BaseModel):
    id: str | None = None
    name: str
    domain: str | None = None
    industry: str | None = None
    employee_count: int | None = None
    technologies: list[str] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)


class ApolloContact(BaseModel):
    id: str | None = None
    first_name: str = ""
    last_name: str = ""
    title: str = ""
    email_status: str | None = None
    linkedin_url: str | None = None
    account_name: str | None = None
    organization_id: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)

    @property
    def full_name(self) -> str:
        return " ".join(part for part in [self.first_name, self.last_name] if part).strip() or "Unknown contact"


class Opportunity(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    signal_id: str
    account: ApolloAccount
    contacts: list[ApolloContact] = Field(default_factory=list)
    fit_score: int = Field(ge=0, le=100)
    displacement_rationale: str
    created_at: datetime = Field(default_factory=utcnow)


class CampaignDraft(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    signal_id: str
    opportunity_id: str
    subject: str
    preview: str = ""
    email_body: str
    linkedin_note: str
    call_opener: str
    apollo_claude_prompt: str
    evidence_urls: list[str]
    contact: ApolloContact | None = None
    seller_company_name: str = ""
    created_at: datetime = Field(default_factory=utcnow)


class ScanResult(BaseModel):
    scan_run_id: str = Field(default_factory=lambda: str(uuid4()))
    competitors_scanned: int
    signals_created: int
    opportunities_created: int
    campaigns_created: int
    created_at: datetime = Field(default_factory=utcnow)
