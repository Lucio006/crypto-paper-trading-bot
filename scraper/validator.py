"""
Validate that a URL is a genuine exhibitor listing before running the full scraper.
Returns (True, reason) or (False, reason).
"""
from __future__ import annotations
import re
from playwright.async_api import Page

# Minimum number of company-like elements to consider the page valid
_MIN_BLOCKS = 3

# CSS selectors that suggest an exhibitor listing
_LISTING_SELECTORS = [
    "[class*='exhibitor']",
    "[class*='expositor']",
    "[class*='company-list']",
    "[class*='empresa']",
    "[class*='participant']",
    "[class*='brand-list']",
    "[class*='sponsor-list']",
    "[class*='patrocinador']",
    # IFEMA / Feria Barcelona / Fira
    ".node--type-expositor",
    ".views-row",
    # Common card/grid patterns
    ".card-grid .card",
    ".listing .item",
    ".grid .item",
    # Last resort
    "ul.list > li:has(a)",
    "article:has(h2):has(a)",
]

# Text patterns that strongly suggest an exhibitor listing
_TEXT_SIGNALS = [
    re.compile(r"\bstand\b", re.I),
    re.compile(r"\bpabellón\b", re.I),
    re.compile(r"\bhall\s*\d", re.I),
    re.compile(r"\bbooth\b", re.I),
    re.compile(r"\bexpositor", re.I),
    re.compile(r"\bexhibitor", re.I),
    re.compile(r"\bparticipante", re.I),
    re.compile(r"\bexpositores", re.I),
]


async def is_valid_listing(page: Page) -> tuple[bool, str]:
    body_text = await page.inner_text("body")

    # ── Check 1: CSS selectors ──────────────────────────────────────────────
    for selector in _LISTING_SELECTORS:
        try:
            count = await page.locator(selector).count()
            if count >= _MIN_BLOCKS:
                return True, f"Estructura de listado detectada ({count} bloques con '{selector}')"
        except Exception:
            continue

    # ── Check 2: text signals ───────────────────────────────────────────────
    hits = [p.pattern for p in _TEXT_SIGNALS if p.search(body_text)]
    if len(hits) >= 2:
        return True, f"Señales de texto de listado: {hits}"

    # ── Check 3: density of title-cased short phrases (company names) ───────
    names = re.findall(r"\b[A-ZÁÉÍÓÚÑ][a-záéíóúñA-Z&]{2,}(?:\s+[A-ZÁÉÍÓÚÑ][a-z]+){0,3}\b", body_text)
    unique_names = len(set(names))
    if unique_names >= 15:
        return True, f"Múltiples nombres de empresa detectados ({unique_names})"

    return (
        False,
        "La URL proporcionada no parece un listado válido de expositores. "
        "No se encontraron suficientes señales de empresas, stands o fichas de expositor.",
    )
