from __future__ import annotations
from loguru import logger
from rapidfuzz import fuzz
from models.company import Company
from scraper.utils import normalize_name
from config import FUZZY_MATCH_HIGH, FUZZY_MATCH_LOW

# Match method labels
MATCH_DOMAIN = "domain_exact"
MATCH_NAME_EXACT = "name_exact"
MATCH_NAME_FUZZY = "name_fuzzy"
MATCH_REVIEW = "needs_review"


def check_against_base(company: Company, base_records: list[dict]) -> Company:
    """
    Compare company against existing BASE EMPRESAS records.
    Sets: is_known, match_method, existing_id, first_event, times_detected,
          times_contacted, last_contact_date, commercial_status, requires_review.
    """
    if not base_records:
        return company

    # ── Step 1: domain exact match ────────────────────────────────────────
    if company.domain:
        for rec in base_records:
            rec_domain = str(rec.get("Dominio principal", "")).strip().lower()
            if rec_domain and rec_domain == company.domain.lower():
                return _apply_match(company, rec, MATCH_DOMAIN)

    # ── Step 2: normalized name exact match ───────────────────────────────
    comp_norm = company.name_normalized or normalize_name(company.name_original)
    if comp_norm:
        for rec in base_records:
            rec_norm = str(rec.get("Nombre normalizado", "")).strip().lower()
            if rec_norm and rec_norm == comp_norm.lower():
                return _apply_match(company, rec, MATCH_NAME_EXACT)

    # ── Step 3: fuzzy match ───────────────────────────────────────────────
    best_score = 0
    best_rec = None
    for rec in base_records:
        rec_norm = str(rec.get("Nombre normalizado", "")).strip()
        if not rec_norm:
            continue
        score = fuzz.token_sort_ratio(comp_norm, rec_norm.lower())
        if score > best_score:
            best_score = score
            best_rec = rec

    if best_score >= FUZZY_MATCH_HIGH and best_rec:
        return _apply_match(company, best_rec, MATCH_NAME_FUZZY)

    if FUZZY_MATCH_LOW <= best_score < FUZZY_MATCH_HIGH and best_rec:
        company = _apply_match(company, best_rec, MATCH_REVIEW)
        company.requires_review = True
        company.review_reason = (
            f"Similitud {best_score}% con '{best_rec.get('Nombre original', '')}' — "
            "verificar si es la misma empresa"
        )
        return company

    # ── No match: new company ─────────────────────────────────────────────
    logger.debug(f"New company: {company.name_original}")
    return company


def _apply_match(company: Company, rec: dict, method: str) -> Company:
    company.is_known = True
    company.match_method = method
    company.existing_id = str(rec.get("ID empresa", ""))

    # Preserve historical data from base
    company.first_event = str(rec.get("Primer evento detectado", ""))
    company.first_event_date = str(rec.get("Fecha de primera detección", ""))
    company.times_detected = int(rec.get("Veces detectada", 0)) + 1
    company.times_contacted = int(rec.get("Veces contactada", 0))
    company.last_contact_date = str(rec.get("Última fecha de contacto", "")) or None

    existing_status = str(rec.get("Estado comercial", "")).strip()
    if existing_status:
        company.commercial_status = existing_status

    # Enrich with any existing data we might be missing
    if not company.domain:
        company.domain = str(rec.get("Dominio principal", "")) or None
    if not company.country:
        company.country = str(rec.get("País", "")) or None
    if not company.sector:
        company.sector = str(rec.get("Sector", "")) or None
    if not company.contact.best_contact:
        company.contact.best_contact = str(rec.get("Mejor contacto conocido", "")) or None
    if not company.contact.best_contact_role:
        company.contact.best_contact_role = str(rec.get("Cargo del mejor contacto", "")) or None

    logger.info(
        f"Matched '{company.name_original}' via {method} "
        f"(base: '{rec.get('Nombre original', '')}', "
        f"contacted {company.times_contacted}x)"
    )
    return company


def build_lookup(base_records: list[dict]) -> dict[str, dict]:
    """Build domain→record lookup for fast dedup during a run."""
    lookup: dict[str, dict] = {}
    for rec in base_records:
        domain = str(rec.get("Dominio principal", "")).strip().lower()
        if domain:
            lookup[domain] = rec
    return lookup
