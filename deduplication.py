"""
Deterministic deduplication — no LLM needed.
Compares a company against existing BASE EMPRESAS records.
Match priority: domain exact → name exact → fuzzy → needs review.
"""
from __future__ import annotations
from rapidfuzz import fuzz
from models import Company
from scraper.utils import normalize_name, extract_domain
from config import FUZZY_HIGH, FUZZY_LOW

MATCH_DOMAIN = "domain_exact"
MATCH_NAME   = "name_exact"
MATCH_FUZZY  = "name_fuzzy"
MATCH_REVIEW = "needs_review"


def check(company: Company, base_records: list[dict]) -> Company:
    """
    Match company against BASE EMPRESAS records.
    Mutates and returns the company with deduplication fields filled.
    """
    if not base_records:
        return company

    norm = company.name_normalized or normalize_name(company.name_original)

    # ── 1. Domain exact ───────────────────────────────────────────────────────
    if company.domain:
        for rec in base_records:
            rec_domain = str(rec.get("Dominio principal", "")).strip().lower()
            if rec_domain and rec_domain == company.domain.lower():
                return _apply(company, rec, MATCH_DOMAIN)

    # ── 2. Normalized name exact ──────────────────────────────────────────────
    for rec in base_records:
        rec_norm = str(rec.get("Nombre normalizado", "")).strip().lower()
        if rec_norm and rec_norm == norm.lower():
            return _apply(company, rec, MATCH_NAME)

    # ── 3. Fuzzy match ────────────────────────────────────────────────────────
    best_score, best_rec = 0, None
    for rec in base_records:
        rec_norm = str(rec.get("Nombre normalizado", "")).strip()
        if not rec_norm:
            continue
        score = fuzz.token_sort_ratio(norm, rec_norm.lower())
        if score > best_score:
            best_score, best_rec = score, rec

    if best_score >= FUZZY_HIGH and best_rec:
        return _apply(company, best_rec, MATCH_FUZZY)

    if FUZZY_LOW <= best_score < FUZZY_HIGH and best_rec:
        company = _apply(company, best_rec, MATCH_REVIEW)
        company.requires_review = True
        company.review_reason = (
            f"Similitud {best_score}% con «{best_rec.get('Nombre original', '')}» "
            "— verificar si es la misma empresa"
        )
        return company

    # ── 4. No match — new company ─────────────────────────────────────────────
    return company


def _apply(company: Company, rec: dict, method: str) -> Company:
    company.is_known    = True
    company.match_method = method
    company.existing_id  = str(rec.get("ID empresa", ""))
    company.first_event       = str(rec.get("Primer evento detectado", "")) or None
    company.first_event_date  = str(rec.get("Fecha de primera detección", "")) or None
    company.times_detected    = int(rec.get("Veces detectada", 0)) + 1
    company.times_contacted   = int(rec.get("Veces contactada", 0))
    company.last_contact_date = str(rec.get("Última fecha de contacto", "")) or None

    status = str(rec.get("Estado comercial", "")).strip()
    if status:
        company.commercial_status = status

    # Enrich from base if current scrape didn't find these
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

    return company
