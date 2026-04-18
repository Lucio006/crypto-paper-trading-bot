"""
Deterministic extraction utilities — no LLM, no Playwright.
Pure regex and string operations on HTML text.
"""
from __future__ import annotations
import re
import unicodedata
from urllib.parse import urlparse, urljoin

# ── Regex patterns ────────────────────────────────────────────────────────────

_EMAIL_RE = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}",
    re.IGNORECASE,
)

_PHONE_RE = re.compile(
    r"(?:\+?\d[\d\s\-().]{6,}\d)"
)

_TELEGRAM_RE = re.compile(
    r"(?:t\.me|telegram\.me|telegram\.org)/([A-Za-z0-9_]{3,})",
    re.IGNORECASE,
)

# Company name suffixes to strip before normalization
_SUFFIXES_RE = re.compile(
    r"\b(?:s\.?l\.?u?\.?|s\.?a\.?u?\.?|s\.?a\.?|s\.?l\.?|ltd\.?|inc\.?|llc\.?|"
    r"gmbh\.?|corp\.?|bv\.?|nv\.?|plc\.?|s\.?r\.?l\.?|s\.?p\.?a\.?|"
    r"s\.?c\.?p\.?|c\.?b\.?|s\.?c\.?|s\.?l\.?u\.?)\s*$",
    re.IGNORECASE,
)

# Email local-part classifiers
_MKT_RE    = re.compile(r"(?:marketing|mkt|comunicacion|comunica|prensa|press|media|publicidad)", re.I)
_EVENTS_RE = re.compile(r"(?:eventos|events|feria|expo|exhibition|sponsor|partnership|patrocin)", re.I)
_CEO_RE    = re.compile(r"(?:ceo|director|directora|gerente|presidente|president|founder|cto|coo)", re.I)
_CCO_RE    = re.compile(r"(?:cco|comercial|ventas|sales|business|desarrollo|bdm)", re.I)


# ── Name normalization ────────────────────────────────────────────────────────

def normalize_name(name: str) -> str:
    """Lowercase, strip accents, remove company suffixes and punctuation."""
    text = name.strip()
    # Remove accent marks
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = text.lower()
    # Remove known company suffixes
    text = _SUFFIXES_RE.sub("", text).strip()
    # Replace punctuation with space
    text = re.sub(r"[^\w\s]", " ", text)
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


# ── URL helpers ───────────────────────────────────────────────────────────────

def extract_domain(url: str) -> str | None:
    """Return bare domain without www., e.g. 'empresa.com'."""
    if not url:
        return None
    try:
        parsed = urlparse(url if "://" in url else "https://" + url)
        host = parsed.netloc or parsed.path.split("/")[0]
        host = re.sub(r"^www\.", "", host).lower().strip()
        return host or None
    except Exception:
        return None


def normalize_url(url: str) -> str:
    """Ensure URL has a scheme."""
    if not url:
        return url
    return url if url.startswith("http") else "https://" + url


def is_valid_url(url: str) -> bool:
    try:
        p = urlparse(url)
        return p.scheme in ("http", "https") and bool(p.netloc)
    except Exception:
        return False


def make_absolute(href: str, base_url: str) -> str:
    return urljoin(base_url, href)


# ── Email extraction and classification ───────────────────────────────────────

def extract_emails(text: str) -> list[str]:
    """Extract all unique emails from a block of text, preserving order."""
    found = _EMAIL_RE.findall(text)
    seen: set[str] = set()
    result = []
    for email in found:
        low = email.lower()
        if low not in seen:
            seen.add(low)
            result.append(low)
    return result


def classify_emails(emails: list[str]) -> dict[str, str | None]:
    """
    Assign emails to roles based on the local part.
    Priority: marketing > events > ceo > cco > general.
    Returns a dict with keys: email_general, email_marketing,
    email_events, email_ceo, email_cco.
    """
    result: dict[str, str | None] = {
        "email_general": None,
        "email_marketing": None,
        "email_events": None,
        "email_ceo": None,
        "email_cco": None,
    }
    for email in emails:
        local = email.split("@")[0]
        if not result["email_marketing"] and _MKT_RE.search(local):
            result["email_marketing"] = email
        elif not result["email_events"] and _EVENTS_RE.search(local):
            result["email_events"] = email
        elif not result["email_ceo"] and _CEO_RE.search(local):
            result["email_ceo"] = email
        elif not result["email_cco"] and _CCO_RE.search(local):
            result["email_cco"] = email
        elif not result["email_general"]:
            result["email_general"] = email
    return result


# ── Phone extraction ──────────────────────────────────────────────────────────

def extract_phone(text: str) -> str | None:
    """Return the first phone-looking string with ≥9 digits."""
    for match in _PHONE_RE.finditer(text):
        raw = match.group(0).strip()
        digits = re.sub(r"\D", "", raw)
        if len(digits) >= 9:
            return raw
    return None


# ── Telegram extraction ───────────────────────────────────────────────────────

def extract_telegram(text: str) -> str | None:
    m = _TELEGRAM_RE.search(text)
    return f"t.me/{m.group(1)}" if m else None


# ── Missing data reasons ──────────────────────────────────────────────────────

def reason_for_missing(field: str, page_status: str, hints: list[str]) -> str:
    """
    Return a human-readable explanation for why a contact field is absent.
    This is always shown in the sheet — no field is ever left blank without a reason.
    """
    if page_status in ("no_website",):
        return "No aparece web corporativa en la ficha del evento"
    if "timeout" in page_status or "error" in page_status:
        return f"La web corporativa no cargó ({page_status})"
    if "http_4" in page_status or "http_5" in page_status:
        return f"La web corporativa devolvió error {page_status.replace('http_', '')}"
    if "form_only" in hints and field in ("email_general", "email_marketing", "email_events"):
        return "Solo hay formulario de contacto, no hay email publicado"
    if "no_contact_page" in hints and field in ("email_marketing", "email_events"):
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
