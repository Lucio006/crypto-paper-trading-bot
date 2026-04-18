from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional
from datetime import date


class ContactData(BaseModel):
    phone: Optional[str] = None
    email_general: Optional[str] = None
    email_marketing: Optional[str] = None
    email_events: Optional[str] = None
    email_ceo: Optional[str] = None
    email_cco: Optional[str] = None
    telegram: Optional[str] = None
    best_contact: Optional[str] = None
    best_contact_role: Optional[str] = None
    recommended_channel: Optional[str] = None
    contact_priority: Optional[str] = None
    # Source tracking
    page_where_found: Optional[str] = None
    evidence_text: Optional[str] = None
    confidence_level: Optional[str] = None  # Alta / Media / Baja
    # Reasons for missing data
    reason_no_marketing: Optional[str] = None
    reason_no_events: Optional[str] = None
    reason_no_ceo: Optional[str] = None
    reason_no_cco: Optional[str] = None
    reason_no_telegram: Optional[str] = None
    reason_no_website: Optional[str] = None


class Company(BaseModel):
    # From event listing / profile
    name_original: str
    name_normalized: str = ""
    stand: Optional[str] = None
    exhibitor_profile_url: Optional[str] = None
    description: Optional[str] = None
    website_from_event: Optional[str] = None
    category: Optional[str] = None

    # From corporate website
    corporate_website: Optional[str] = None
    domain: Optional[str] = None
    country: Optional[str] = None
    sector: Optional[str] = None

    contact: ContactData = Field(default_factory=ContactData)

    # Deduplication / memory
    is_known: bool = False
    match_method: Optional[str] = None  # domain_exact | name_exact | name_fuzzy | needs_review
    existing_id: Optional[str] = None   # ID in BASE EMPRESAS if known
    first_event: Optional[str] = None
    first_event_date: Optional[str] = None
    last_event: Optional[str] = None
    last_event_date: Optional[str] = None
    times_detected: int = 0
    times_contacted: int = 0
    last_contact_date: Optional[str] = None
    commercial_status: str = "Nueva"
    requires_review: bool = False
    review_reason: Optional[str] = None
    other_names: Optional[str] = None
    notes: Optional[str] = None


class EventMeta(BaseModel):
    event_id: str
    event_name: str
    event_date: str
    tab_name: str
    listing_url: str
    analysis_date: str = Field(default_factory=lambda: date.today().isoformat())
    companies_detected: int = 0
    companies_new: int = 0
    companies_known: int = 0
    status: str = "En proceso"
    observations: Optional[str] = None
