from __future__ import annotations
import uuid
from datetime import date
from loguru import logger
from models.company import Company, EventMeta
from sheets.client import get_or_create_worksheet, get_spreadsheet
from config import TAB_INDEX, TAB_BASE

# ──────────────────────────────────────────────
# Column definitions
# ──────────────────────────────────────────────

INDEX_HEADERS = [
    "ID evento", "Fecha del evento", "Nombre del evento", "Nombre de la pestaña",
    "Enlace del listado de expositores", "Fecha de análisis",
    "Empresas detectadas", "Empresas nuevas", "Empresas ya registradas",
    "Estado del análisis", "Observaciones",
]

BASE_HEADERS = [
    "ID empresa", "Nombre original", "Nombre normalizado", "Otros nombres detectados",
    "Dominio principal", "Web principal", "País", "Sector",
    "Primer evento detectado", "Fecha de primera detección",
    "Último evento detectado", "Fecha de última detección",
    "Veces detectada", "Veces contactada", "Última fecha de contacto",
    "Estado comercial", "Mejor contacto conocido", "Cargo del mejor contacto",
    "Email principal", "Teléfono principal", "Telegram", "Canal recomendado",
    "Última fuente encontrada", "Nivel de confianza", "Método de coincidencia",
    "Requiere revisión", "Motivo de revisión", "Notas internas",
]

EVENT_HEADERS = [
    "ID fila", "ID evento", "Fecha del evento", "Nombre del evento",
    "Nombre de la empresa", "Nombre normalizado", "Número de stand",
    "Ficha del expositor", "Categoría del expositor",
    "Empresa ya registrada", "Ya se contactó antes",
    "Descripción del expositor", "Web encontrada en la ficha",
    "Enlace corporativo validado", "Web principal", "Dominio",
    "País", "Sector", "Teléfono general", "Email general",
    "Email de marketing", "Email de eventos", "Email del CEO", "Email del CCO",
    "Telegram", "Mejor contacto encontrado", "Cargo del mejor contacto",
    "Canal recomendado", "Prioridad del contacto",
    "Primer evento detectado", "Último evento detectado",
    "Última fecha de contacto", "Estado comercial",
    "Motivo si falta email de marketing", "Motivo si falta email de eventos",
    "Motivo si falta email del CEO", "Motivo si falta email del CCO",
    "Motivo si falta Telegram", "Motivo si falta web corporativa",
    "Página donde se encontró el mejor dato", "Texto de evidencia",
    "Nivel de confianza", "Método de coincidencia",
    "Requiere revisión", "Motivo de revisión", "Notas internas",
    "Contacto realizado", "Fecha de contacto", "Resultado del contacto",
    "Responsable",
]


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def _ensure_headers(ws, headers: list[str]) -> None:
    first_row = ws.row_values(1)
    if first_row != headers:
        ws.update("A1", [headers])
        logger.debug(f"Headers written to '{ws.title}'")


def _company_to_event_row(company: Company, event: EventMeta) -> list:
    c = company.contact
    return [
        str(uuid.uuid4())[:8],
        event.event_id,
        event.event_date,
        event.event_name,
        company.name_original,
        company.name_normalized,
        company.stand or "",
        company.exhibitor_profile_url or "",
        company.category or "",
        "Sí" if company.is_known else "No",
        "Sí" if company.times_contacted > 0 else "No",
        company.description or "",
        company.website_from_event or "",
        company.corporate_website or "",
        company.corporate_website or "",
        company.domain or "",
        company.country or "",
        company.sector or "",
        c.phone or "",
        c.email_general or "",
        c.email_marketing or "",
        c.email_events or "",
        c.email_ceo or "",
        c.email_cco or "",
        c.telegram or "",
        c.best_contact or "",
        c.best_contact_role or "",
        c.recommended_channel or "",
        c.contact_priority or "",
        company.first_event or "",
        company.last_event or event.event_name,
        company.last_contact_date or "",
        company.commercial_status,
        c.reason_no_marketing or "",
        c.reason_no_events or "",
        c.reason_no_ceo or "",
        c.reason_no_cco or "",
        c.reason_no_telegram or "",
        c.reason_no_website or "",
        c.page_where_found or "",
        c.evidence_text or "",
        c.confidence_level or "",
        company.match_method or "",
        "Sí" if company.requires_review else "No",
        company.review_reason or "",
        company.notes or "",
        "",  # Contacto realizado (manual)
        "",  # Fecha de contacto (manual)
        "Sin acción",  # Resultado del contacto
        "",  # Responsable (manual)
    ]


def _company_to_base_row(company: Company, event: EventMeta) -> list:
    c = company.contact
    company_id = company.existing_id or str(uuid.uuid4())[:8]
    return [
        company_id,
        company.name_original,
        company.name_normalized,
        company.other_names or "",
        company.domain or "",
        company.corporate_website or "",
        company.country or "",
        company.sector or "",
        company.first_event or event.event_name,
        company.first_event_date or event.event_date,
        event.event_name,
        event.event_date,
        max(company.times_detected, 1),
        company.times_contacted,
        company.last_contact_date or "",
        company.commercial_status,
        c.best_contact or "",
        c.best_contact_role or "",
        c.email_general or "",
        c.phone or "",
        c.telegram or "",
        c.recommended_channel or "",
        event.listing_url,
        c.confidence_level or "",
        company.match_method or "",
        "Sí" if company.requires_review else "No",
        company.review_reason or "",
        company.notes or "",
    ]


# ──────────────────────────────────────────────
# Public write functions
# ──────────────────────────────────────────────

def ensure_base_tabs() -> None:
    index_ws = get_or_create_worksheet(TAB_INDEX)
    _ensure_headers(index_ws, INDEX_HEADERS)
    base_ws = get_or_create_worksheet(TAB_BASE)
    _ensure_headers(base_ws, BASE_HEADERS)


def write_event_tab(companies: list[Company], event: EventMeta) -> None:
    ws = get_or_create_worksheet(event.tab_name)
    _ensure_headers(ws, EVENT_HEADERS)
    rows = [_company_to_event_row(c, event) for c in companies]
    if rows:
        ws.append_rows(rows, value_input_option="USER_ENTERED")
    logger.info(f"Written {len(rows)} companies to tab '{event.tab_name}'")


def update_index(event: EventMeta) -> None:
    ws = get_or_create_worksheet(TAB_INDEX)
    _ensure_headers(ws, INDEX_HEADERS)
    row = [
        event.event_id,
        event.event_date,
        event.event_name,
        event.tab_name,
        event.listing_url,
        event.analysis_date,
        event.companies_detected,
        event.companies_new,
        event.companies_known,
        event.status,
        event.observations or "",
    ]
    ws.append_row(row, value_input_option="USER_ENTERED")
    logger.info(f"Index updated for event '{event.event_name}'")


def upsert_base(companies: list[Company], event: EventMeta) -> None:
    ws = get_or_create_worksheet(TAB_BASE)
    _ensure_headers(ws, BASE_HEADERS)
    all_rows = ws.get_all_values()
    # Build domain→row_index and name→row_index lookups (skip header)
    domain_idx: dict[str, int] = {}
    name_idx: dict[str, int] = {}
    for i, row in enumerate(all_rows[1:], start=2):
        if len(row) > 4 and row[4]:
            domain_idx[row[4].lower()] = i
        if len(row) > 2 and row[2]:
            name_idx[row[2].lower()] = i

    for company in companies:
        new_row = _company_to_base_row(company, event)
        # Find existing row
        existing_row_num = None
        if company.domain:
            existing_row_num = domain_idx.get(company.domain.lower())
        if existing_row_num is None and company.name_normalized:
            existing_row_num = name_idx.get(company.name_normalized.lower())

        if existing_row_num is not None:
            # Update existing: only update dynamic fields, preserve manual notes
            ws.update(f"A{existing_row_num}", [new_row])
            logger.debug(f"Updated base row for '{company.name_original}'")
        else:
            ws.append_row(new_row, value_input_option="USER_ENTERED")
            logger.debug(f"Added new base row for '{company.name_original}'")


def read_base_companies() -> list[dict]:
    ws = get_or_create_worksheet(TAB_BASE)
    records = ws.get_all_records()
    return records
