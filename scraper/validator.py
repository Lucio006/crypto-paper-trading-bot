from __future__ import annotations
from playwright.async_api import Page
from loguru import logger

# Minimum signals required to consider a page a valid exhibitor listing
MIN_COMPANIES = 3

# CSS selectors / text patterns that suggest an exhibitor listing
LISTING_SIGNALS = [
    # Common class names / attributes used by event platforms
    "[class*='exhibitor']",
    "[class*='expositor']",
    "[class*='company']",
    "[class*='empresa']",
    "[class*='stand']",
    "[class*='participant']",
    "[class*='participante']",
    "[class*='brand']",
    "[class*='sponsor']",
    "[class*='patrocinador']",
    # Generic card/list structures that might contain companies
    ".card", ".listing-item", ".grid-item",
    "[data-company]", "[data-exhibitor]",
    # IFEMA and common Spanish event platforms
    "[class*='feria']",
    "[class*='exposicion']",
]

# Text patterns suggesting company names (heuristic: multiple items with similar structure)
TEXT_SIGNALS = [
    r"stand\s*[A-Z]?\d+",          # "Stand B12"
    r"pabellón\s*\d+",              # "Pabellón 6"
    r"hall\s*[A-Z]?\d+",            # "Hall 4"
    r"booth\s*[A-Z]?\d+",           # "Booth 12"
    r"expositor",
    r"exhibitor",
]


async def is_valid_listing(page: Page) -> tuple[bool, str]:
    """
    Returns (is_valid, reason).
    Checks for signals that the page is genuinely an exhibitor listing.
    """
    import re

    body_text = await page.inner_text("body")
    body_lower = body_text.lower()

    # Check for minimum number of company-like blocks via CSS
    signal_hits = 0
    matched_selector = None
    for selector in LISTING_SIGNALS:
        try:
            count = await page.locator(selector).count()
            if count >= MIN_COMPANIES:
                signal_hits += 1
                matched_selector = selector
                logger.debug(f"Selector '{selector}' matched {count} elements")
                break
        except Exception:
            continue

    # Check for text signals
    text_hits = 0
    for pattern in TEXT_SIGNALS:
        if re.search(pattern, body_lower, re.IGNORECASE):
            text_hits += 1

    # Count potential company names: look for multiple title-cased short phrases
    potential_names = len(re.findall(r"\b[A-Z][a-záéíóúñA-Z&]{2,}\b(?:\s+[A-Z][a-z]+){0,4}", body_text))

    logger.debug(
        f"Validation: css_hits={signal_hits}, text_hits={text_hits}, "
        f"potential_names={potential_names}"
    )

    if signal_hits > 0:
        return True, f"Estructura de listado detectada (selector: {matched_selector})"
    if text_hits >= 2 and potential_names >= MIN_COMPANIES * 3:
        return True, f"Señales de texto de listado detectadas ({text_hits} patrones)"
    if potential_names >= 20:
        return True, f"Múltiples nombres de empresa detectados ({potential_names})"

    return (
        False,
        "La URL proporcionada no parece un listado válido de expositores. "
        "No se encontraron suficientes señales de empresas, stands o fichas.",
    )
