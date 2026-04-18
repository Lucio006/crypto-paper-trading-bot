"""
Data classes for the event prospector.
Using stdlib dataclasses — no external dependency needed for V1.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
from datetime import date as _date


@dataclass
class ContactData:
    # Direct contact info
    phone: Optional[str] = None
    email_general: Optional[str] = None
    email_marketing: Optional[str] = None
    email_events: Optional[str] = None
    email_ceo: Optional[str] = None
    email_cco: Optional[str] = None
    telegram: Optional[str] = None

    # Best contact (chosen by classifier)
    best_contact: Optional[str] = None
    best_contact_role: Optional[str] = None
    recommended_channel: Optional[str] = None
    contact_priority: Optional[str] = None     # Alta / Media / Baja

    # Evidence
    page_where_found: Optional[str] = None
    evidence_text: Optional[str] = None
    confidence_level: Optional[str] = None    # Alta / Media / Baja

    # Reasons for missing fields (never left empty when data is absent)
    reason_no_marketing: Optional[str] = None
    reason_no_events: Optional[str] = None
    reason_no_ceo: Optional[str] = None
    reason_no_cco: Optional[str] = None
    reason_no_telegram: Optional[str] = None
    reason_no_website: Optional[str] = None

    def any_email(self) -> Optional[str]:
        """Return the first available email in priority order."""
        return (
            self.email_events
            or self.email_marketing
            or self.email_general
            or self.email_cco
            or self.email_ceo
        )

    def has_any_contact(self) -> bool:
        return any([
            self.email_general, self.email_marketing, self.email_events,
            self.email_ceo, self.email_cco, self.telegram, self.phone,
        ])


@dataclass
class Company:
    # ── From event listing / profile ──────────────────────────────────────────
    name_original: str = ""
    name_normalized: str = ""
    stand: Optional[str] = None
    exhibitor_profile_url: Optional[str] = None
    description: Optional[str] = None
    website_from_event: Optional[str] = None   # URL found on the event page
    category: Optional[str] = None

    # ── From corporate website ────────────────────────────────────────────────
    corporate_website: Optional[str] = None    # validated URL
    domain: Optional[str] = None
    country: Optional[str] = None
    sector: Optional[str] = None

    contact: ContactData = field(default_factory=ContactData)

    # ── Deduplication / memory ────────────────────────────────────────────────
    is_known: bool = False
    match_method: Optional[str] = None   # domain_exact | name_exact | name_fuzzy | needs_review
    existing_id: Optional[str] = None   # row ID in BASE EMPRESAS if already known
    other_names: Optional[str] = None   # pipe-separated previous names seen

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
    notes: Optional[str] = None
    personal_contacts: Optional[str] = None  # "Nombre — Cargo — linkedin.com/in/..." (one per line)


@dataclass
class EventMeta:
    event_name: str
    event_date: str           # ISO format: YYYY-MM-DD
    listing_url: str
    tab_name: str
    event_id: str = ""
    analysis_date: str = field(default_factory=lambda: _date.today().isoformat())
    companies_detected: int = 0
    companies_new: int = 0
    companies_known: int = 0
    status: str = "En proceso"
    observations: Optional[str] = None


# ── Helpers ───────────────────────────────────────────────────────────────────

def empty_contact() -> ContactData:
    return ContactData()


def make_event_id(event_name: str, event_date: str) -> str:
    import re
    slug = re.sub(r"\W+", "-", event_name.lower())[:20].strip("-")
    return f"{event_date}-{slug}"


# ── Quick smoke test ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    c = ContactData(
        email_general="info@empresa.com",
        email_marketing="marketing@empresa.com",
        phone="+34 91 000 00 00",
    )
    company = Company(
        name_original="Empresa Ejemplo S.L.",
        name_normalized="empresa ejemplo",
        stand="B12",
        contact=c,
    )
    event = EventMeta(
        event_name="IFEMA Madrid 2025",
        event_date="2025-06-15",
        listing_url="https://www.ifema.es/expositores",
        tab_name="2025-06-15 | IFEMA Madrid 2025",
        event_id=make_event_id("IFEMA Madrid 2025", "2025-06-15"),
    )

    print("── Company ──────────────────────────────")
    print(f"  nombre    : {company.name_original}")
    print(f"  stand     : {company.stand}")
    print(f"  email     : {company.contact.email_general}")
    print(f"  mkt email : {company.contact.email_marketing}")
    print(f"  teléfono  : {company.contact.phone}")
    print(f"  any_email : {company.contact.any_email()}")
    print(f"  known     : {company.is_known}")
    print(f"  status    : {company.commercial_status}")

    print("\n── EventMeta ────────────────────────────")
    print(f"  evento    : {event.event_name}")
    print(f"  fecha     : {event.event_date}")
    print(f"  id        : {event.event_id}")
    print(f"  pestaña   : {event.tab_name}")

    print("\n✓ models.py OK")
