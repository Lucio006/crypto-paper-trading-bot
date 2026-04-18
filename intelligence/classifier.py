from __future__ import annotations
import json
from loguru import logger
from anthropic import Anthropic
from models.company import Company
from config import ANTHROPIC_API_KEY

_client: Anthropic | None = None


def _get_client() -> Anthropic:
    global _client
    if _client is None:
        _client = Anthropic(api_key=ANTHROPIC_API_KEY)
    return _client


SYSTEM_PROMPT = """Eres un asistente de prospección comercial B2B especializado en eventos.
Tu trabajo es ayudar a clasificar los datos de contacto de empresas expositoras.
Responde siempre en JSON válido, sin markdown, sin explicaciones fuera del JSON.
Sé conciso y directo. No inventes datos que no existen."""

CLASSIFY_TEMPLATE = """Empresa: {name}
Sector: {sector}
País: {country}
Email general: {email_general}
Email marketing: {email_marketing}
Email eventos: {email_events}
Email CEO: {email_ceo}
Email CCO: {email_cco}
Telegram: {telegram}
Teléfono: {phone}

Basándote únicamente en los datos anteriores, devuelve este JSON:
{{
  "best_contact": "el mejor email o número de contacto disponible",
  "best_contact_role": "rol estimado de ese contacto (ej: Marketing, Eventos, General, Dirección)",
  "recommended_channel": "Email" | "Teléfono" | "Telegram" | "Formulario web",
  "contact_priority": "Alta" | "Media" | "Baja",
  "confidence_level": "Alta" | "Media" | "Baja",
  "reasoning": "una frase breve explicando la elección"
}}"""


async def enrich_with_claude(company: Company) -> Company:
    """
    Use Claude Haiku to choose the best contact, recommend channel
    and set confidence level. Falls back gracefully if API fails.
    """
    c = company.contact
    prompt = CLASSIFY_TEMPLATE.format(
        name=company.name_original,
        sector=company.sector or "desconocido",
        country=company.country or "desconocido",
        email_general=c.email_general or "—",
        email_marketing=c.email_marketing or "—",
        email_events=c.email_events or "—",
        email_ceo=c.email_ceo or "—",
        email_cco=c.email_cco or "—",
        telegram=c.telegram or "—",
        phone=c.phone or "—",
    )

    # Skip if there's nothing to classify
    has_any_contact = any([
        c.email_general, c.email_marketing, c.email_events,
        c.email_ceo, c.email_cco, c.telegram, c.phone,
    ])
    if not has_any_contact:
        c.best_contact = None
        c.recommended_channel = "Formulario web" if company.corporate_website else None
        c.contact_priority = "Baja"
        c.confidence_level = "Baja"
        return company

    try:
        client = _get_client()
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=256,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
        # Strip accidental markdown fences
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        data = json.loads(raw)

        c.best_contact = data.get("best_contact") or c.email_general
        c.best_contact_role = data.get("best_contact_role")
        c.recommended_channel = data.get("recommended_channel", "Email")
        c.contact_priority = data.get("contact_priority", "Media")
        if not c.confidence_level:
            c.confidence_level = data.get("confidence_level", "Media")

        logger.debug(
            f"Claude classified {company.name_original}: "
            f"best={c.best_contact} channel={c.recommended_channel}"
        )
    except Exception as e:
        logger.warning(f"Claude classification failed for {company.name_original}: {e}")
        # Fallback: pick first available contact
        c.best_contact = (
            c.email_events or c.email_marketing or c.email_general
            or c.email_cco or c.phone or None
        )
        c.recommended_channel = "Email" if c.best_contact and "@" in (c.best_contact or "") else "Teléfono"
        c.contact_priority = "Media"

    return company
