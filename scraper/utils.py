from __future__ import annotations
import re
import unicodedata
from urllib.parse import urlparse, urljoin

# ──────────────────────────────────────────────
# Regex patterns
# ──────────────────────────────────────────────

EMAIL_RE = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}",
    re.IGNORECASE,
)

PHONE_RE = re.compile(
    r"(?:\+?\d[\d\s\-().]{7,}\d)",
)

TELEGRAM_RE = re.compile(
    r"(?:t\.me|telegram\.me|telegram\.org)/([A-Za-z0-9_]{3,})",
    re.IGNORECASE,
)

# Suffixes to strip for name normalization
COMPANY_SUFFIXES = re.compile(
    r"\b(?:s\.?l\.?u?\.?|s\.?a\.?u?\.?|s\.?a\.?|s\.?l\.?|ltd\.?|inc\.?|llc\.?|"
    r"gmbh\.?|corp\.?|bv\.?|nv\.?|plc\.?|s\.?r\.?l\.?|s\.?p\.?a\.?|"
    r"s\.?c\.?p\.?|c\.?b\.?|s\.?c\.?)\s*$",
    re.IGNORECASE,
)

MARKETING_EMAIL_RE = re.compile(
    r"(?:marketing|mkt|comunicacion|comunica|prensa|press|media|publicidad|ads)\b",
    re.IGNORECASE,
)
EVENTS_EMAIL_RE = re.compile(
    r"(?:eventos|events|feria|expo|exhibition|sponsor|partnership|patrocin)",
    re.IGNORECASE,
)
CEO_EMAIL_RE = re.compile(
    r"(?:ceo|director|directora|gerente|presidente|president|cto|coo|founder)\b",
    re.IGNORECASE,
)
CCO_EMAIL_RE = re.compile(
    r"(?:cco|comercial|ventas|sales|business|desarrollo)\b",
    re.IGNORECASE,
)


# ──────────────────────────────────────────────
# Text normalization
# ──────────────────────────────────────────────

def normalize_name(name: str) -> str:
    """Lowercase, remove accents, punctuation and common company suffixes."""
    text = name.strip()
    # Remove accents
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = text.lower()
    # Remove company suffixes
    text = COMPANY_SUFFIXES.sub("", text).strip()
    # Remove punctuation except spaces
    text = re.sub(r"[^\w\s]", " ", text)
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


def extract_domain(url: str) -> str | None:
    try:
        parsed = urlparse(url if url.startswith("http") else "https://" + url)
        host = parsed.netloc or parsed.path
        # Strip www.
        host = re.sub(r"^www\.", "", host).lower()
        return host or None
    except Exception:
        return None


def normalize_url(url: str) -> str:
    if not url:
        return url
    if not url.startswith("http"):
        return "https://" + url
    return url


# ──────────────────────────────────────────────
# Email extraction and classification
# ──────────────────────────────────────────────

def extract_emails(text: str) -> list[str]:
    found = EMAIL_RE.findall(text)
    # Deduplicate preserving order
    seen: set[str] = set()
    result = []
    for email in found:
        low = email.lower()
        if low not in seen:
            seen.add(low)
            result.append(email.lower())
    return result


def classify_emails(emails: list[str]) -> dict[str, str | None]:
    result: dict[str, str | None] = {
        "email_general": None,
        "email_marketing": None,
        "email_events": None,
        "email_ceo": None,
        "email_cco": None,
    }
    for email in emails:
        local = email.split("@")[0]
        if not result["email_marketing"] and MARKETING_EMAIL_RE.search(local):
            result["email_marketing"] = email
        elif not result["email_events"] and EVENTS_EMAIL_RE.search(local):
            result["email_events"] = email
        elif not result["email_ceo"] and CEO_EMAIL_RE.search(local):
            result["email_ceo"] = email
        elif not result["email_cco"] and CCO_EMAIL_RE.search(local):
            result["email_cco"] = email
        elif not result["email_general"]:
            result["email_general"] = email
    return result


def extract_phone(text: str) -> str | None:
    matches = PHONE_RE.findall(text)
    for m in matches:
        cleaned = re.sub(r"[\s\-()]", "", m)
        if len(cleaned) >= 9:
            return m.strip()
    return None


def extract_telegram(text: str) -> str | None:
    m = TELEGRAM_RE.search(text)
    if m:
        return f"t.me/{m.group(1)}"
    return None


def is_valid_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except Exception:
        return False


def make_absolute(href: str, base_url: str) -> str:
    return urljoin(base_url, href)


def reason_for_missing(field: str, page_status: str, page_content_hints: list[str]) -> str:
    """Generate a human-readable reason why a field is missing."""
    if "timeout" in page_status or "error" in page_status:
        return f"La web corporativa no cargó ({page_status})"
    if "no_website" in page_status:
        return "No aparece web corporativa en la ficha del evento"
    if "form_only" in page_content_hints:
        return "Solo hay formulario de contacto, no hay email publicado"
    if "no_contact_page" in page_content_hints:
        return "No se encontró página de contacto en la web"
    if field in ("email_ceo", "email_cco"):
        return "No hay emails directivos publicados en la web (habitual por GDPR)"
    if field == "email_marketing":
        return "No hay email de marketing publicado en la web"
    if field == "email_events":
        return "No hay email de eventos/sponsorship publicado en la web"
    if field == "telegram":
        return "No aparece Telegram en la web ni en perfiles enlazados"
    return "No encontrado tras revisar la web corporativa"
