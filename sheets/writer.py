"""
Write companies and event metadata to Google Sheets.
Column order is always driven by sheets/schema.py — never hardcoded here.
"""
from __future__ import annotations
import uuid
from models import Company, EventMeta
from sheets.client import get_or_create_worksheet
from sheets.schema import (
    TAB_INDEX, TAB_BASE,
    INDEX_COLUMNS, BASE_COLUMNS, EVENT_COLUMNS,
)


# ── Internal row builders ──────────────────────────────────────────────────────

def _v(value) -> str:
    """Convert any value to a clean string for Sheets."""
    if value is None:
        return ""
    return str(value)


def _bool_es(value: bool) -> str:
    return "Sí" if value else "No"


def _index_row(event: EventMeta) -> list[str]:
    return [
        _v(event.event_id),
        _v(event.event_date),
        _v(event.event_name),
        _v(event.tab_name),
        _v(event.listing_url),
        _v(event.analysis_date),
        _v(event.companies_detected),
        _v(event.companies_new),
        _v(event.companies_known),
        _v(event.status),
        _v(event.observations),
    ]


def _base_row(company: Company, event: EventMeta) -> list[str]:
    c = company.contact
    company_id = company.existing_id or str(uuid.uuid4())[:8]
    return [
        company_id,
        _v(company.name_original),
        _v(company.name_normalized),
        _v(company.other_names),
        _v(company.domain),
        _v(company.corporate_website),
        _v(company.country),
        _v(company.sector),
        _v(company.first_event or event.event_name),
        _v(company.first_event_date or event.event_date),
        _v(event.event_name),           # last event seen
        _v(event.event_date),
        _v(max(company.times_detected, 1)),
        _v(company.times_contacted),
        _v(company.last_contact_date),
        _v(company.commercial_status),
        _v(c.best_contact),
        _v(c.best_contact_role),
        _v(c.email_general),
        _v(c.phone),
        _v(c.telegram),
        _v(c.recommended_channel),
        _v(event.listing_url),          # last source
        _v(c.confidence_level),
        _v(company.match_method),
        _bool_es(company.requires_review),
        _v(company.review_reason),
        _v(company.notes),
    ]


def _event_row(company: Company, event: EventMeta) -> list[str]:
    c = company.contact
    return [
        str(uuid.uuid4())[:8],
        _v(event.event_id),
        _v(event.event_date),
        _v(event.event_name),
        _v(company.name_original),
        _v(company.name_normalized),
        _v(company.stand),
        _v(company.exhibitor_profile_url),
        _v(company.category),
        _bool_es(company.is_known),
        _bool_es(company.times_contacted > 0),
        _v(company.description),
        _v(company.website_from_event),
        _v(company.corporate_website),
        _v(company.corporate_website),
        _v(company.domain),
        _v(company.country),
        _v(company.sector),
        _v(c.phone),
        _v(c.email_general),
        _v(c.email_marketing),
        _v(c.email_events),
        _v(c.email_ceo),
        _v(c.email_cco),
        _v(c.telegram),
        _v(c.best_contact),
        _v(c.best_contact_role),
        _v(c.recommended_channel),
        _v(c.contact_priority),
        _v(company.first_event),
        _v(company.last_event or event.event_name),
        _v(company.last_contact_date),
        _v(company.commercial_status),
        _v(c.reason_no_marketing),
        _v(c.reason_no_events),
        _v(c.reason_no_ceo),
        _v(c.reason_no_cco),
        _v(c.reason_no_telegram),
        _v(c.reason_no_website),
        _v(c.page_where_found),
        _v(c.evidence_text),
        _v(c.confidence_level),
        _v(company.match_method),
        _bool_es(company.requires_review),
        _v(company.review_reason),
        _v(company.notes),
        "",        # Contacto realizado (manual)
        "",        # Fecha de contacto (manual)
        "Sin acción",
        "",        # Responsable (manual)
    ]


# ── Header helper ──────────────────────────────────────────────────────────────

def _ensure_headers(ws, headers: list[str]) -> None:
    existing = ws.row_values(1)
    if existing != headers:
        ws.update("A1", [headers])


# ── Public API ────────────────────────────────────────────────────────────────

def ensure_base_tabs() -> None:
    """Create ÍNDICE EVENTOS and BASE EMPRESAS with headers if they don't exist."""
    for tab_name, columns in [(TAB_INDEX, INDEX_COLUMNS), (TAB_BASE, BASE_COLUMNS)]:
        ws = get_or_create_worksheet(tab_name)
        _ensure_headers(ws, columns)


def write_event_tab(companies: list[Company], event: EventMeta) -> int:
    """
    Create (or append to) the event tab and write all companies.
    Returns number of rows written.
    """
    ws = get_or_create_worksheet(event.tab_name)
    _ensure_headers(ws, EVENT_COLUMNS)
    rows = [_event_row(c, event) for c in companies]
    if rows:
        ws.append_rows(rows, value_input_option="USER_ENTERED")
    return len(rows)


def update_index(event: EventMeta) -> None:
    """Append or update the event row in ÍNDICE EVENTOS."""
    ws = get_or_create_worksheet(TAB_INDEX)
    _ensure_headers(ws, INDEX_COLUMNS)
    # Check if this event_id already exists (re-run scenario)
    all_rows = ws.get_all_values()
    for i, row in enumerate(all_rows[1:], start=2):
        if row and row[0] == event.event_id:
            ws.update(f"A{i}", [_index_row(event)])
            return
    ws.append_row(_index_row(event), value_input_option="USER_ENTERED")


def upsert_base(companies: list[Company], event: EventMeta) -> tuple[int, int]:
    """
    Insert new companies and update known ones in BASE EMPRESAS.
    Returns (inserted, updated).
    """
    ws = get_or_create_worksheet(TAB_BASE)
    _ensure_headers(ws, BASE_COLUMNS)

    all_rows = ws.get_all_values()
    # Build lookup: domain → row_number, name_normalized → row_number
    domain_row: dict[str, int] = {}
    name_row: dict[str, int] = {}
    for i, row in enumerate(all_rows[1:], start=2):
        if len(row) > 4 and row[4]:
            domain_row[row[4].lower()] = i
        if len(row) > 2 and row[2]:
            name_row[row[2].lower()] = i

    inserted = updated = 0
    for company in companies:
        new_row = _base_row(company, event)
        existing_row_num = None
        if company.domain:
            existing_row_num = domain_row.get(company.domain.lower())
        if existing_row_num is None and company.name_normalized:
            existing_row_num = name_row.get(company.name_normalized.lower())

        if existing_row_num is not None:
            ws.update(f"A{existing_row_num}", [new_row])
            updated += 1
        else:
            ws.append_row(new_row, value_input_option="USER_ENTERED")
            inserted += 1

    return inserted, updated


def read_base_companies() -> list[dict]:
    """Read all rows from BASE EMPRESAS as list of dicts. Used by deduplicator."""
    ws = get_or_create_worksheet(TAB_BASE)
    return ws.get_all_records()
