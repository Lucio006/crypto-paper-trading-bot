"""
Claude Haiku classifier — picks best contact, recommends channel, justifies absences.
Only called when there's at least one contact to classify.
Falls back gracefully if the API key is missing or the call fails.
"""
from __future__ import annotations
import json
from anthropic import Anthropic
from models import Company
from config import ANTHROPIC_API_KEY

_client: Anthropic | None = None

_SYSTEM = (
    "Eres un asistente de prospección comercial B2B especializado en eventos. "
    "Responde siempre en JSON válido, sin markdown. Sé conciso."
)

_PROMPT = """Empresa: {name}
Sector: {sector}
Email general: {email_general}
Email marketing: {email_marketing}
Email eventos: {email_events}
Email CEO: {email_ceo}
Email CCO: {email_cco}
Telegram: {telegram}
Teléfono: {phone}

Devuelve este JSON (sin más texto):
{{
  "best_contact": "el mejor email o teléfono disponible, o null",
  "best_contact_role": "rol estimado (Marketing / Eventos / General / Dirección / null)",
  "recommended_channel": "Email" | "Teléfono" | "Telegram" | "Formulario web",
  "contact_priority": "Alta" | "Media" | "Baja"
}}"""


def _get_client() -> Anthropic:
    global _client
    if _client is None:
        _client = Anthropic(api_key=ANTHROPIC_API_KEY)
    return _client


async def enrich(company: Company) -> Company:
    """
    Use Claude Haiku to choose the best contact and recommend a channel.
    Mutates and returns the company. Never raises.
    """
    c = company.contact
    if not c.has_any_contact():
        c.recommended_channel = "Formulario web" if company.corporate_website else None
        c.contact_priority = "Baja"
        return company

    if not ANTHROPIC_API_KEY:
        _fallback(company)
        return company

    prompt = _PROMPT.format(
        name=company.name_original,
        sector=company.sector or "desconocido",
        email_general=c.email_general or "—",
        email_marketing=c.email_marketing or "—",
        email_events=c.email_events or "—",
        email_ceo=c.email_ceo or "—",
        email_cco=c.email_cco or "—",
        telegram=c.telegram or "—",
        phone=c.phone or "—",
    )

    try:
        response = _get_client().messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=200,
            system=_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1].lstrip("json").strip()
        data = json.loads(raw)
        c.best_contact        = data.get("best_contact") or c.any_email()
        c.best_contact_role   = data.get("best_contact_role")
        c.recommended_channel = data.get("recommended_channel", "Email")
        c.contact_priority    = data.get("contact_priority", "Media")
    except Exception:
        _fallback(company)

    return company


def _fallback(company: Company) -> None:
    c = company.contact
    c.best_contact = c.any_email() or c.phone
    c.recommended_channel = (
        "Email" if c.best_contact and "@" in (c.best_contact or "")
        else "Teléfono" if c.phone
        else "Formulario web"
    )
    c.contact_priority = "Media"
