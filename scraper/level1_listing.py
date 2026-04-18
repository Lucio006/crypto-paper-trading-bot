from __future__ import annotations
import re
from playwright.async_api import Page
from loguru import logger
from models.company import Company
from scraper.utils import normalize_name, normalize_url, extract_domain, make_absolute

# ──────────────────────────────────────────────
# Selectors tried in order for each event platform
# ──────────────────────────────────────────────

COMPANY_BLOCK_SELECTORS = [
    # Platform-specific
    ".exhibitor-item", ".expositor-item", ".expositor-card",
    "[class*='exhibitor-list'] > *", "[class*='expositor-list'] > *",
    "[class*='company-card']", "[class*='empresa-card']",
    "[class*='participant-item']", "[class*='brand-item']",
    # IFEMA / Feria Barcelona / Fira
    ".node--type-expositor", ".views-row", ".field--name-title",
    # Generic
    ".card", ".listing-card", ".grid-card",
    "[data-exhibitor]", "[data-company-id]",
    # Last resort: any <li> or <article> with a link inside
    "li:has(a)", "article:has(a)",
]

NAME_SELECTORS = [
    "h2", "h3", "h4", ".company-name", ".nombre-empresa",
    ".exhibitor-name", ".expositor-name", ".title", ".name",
    "[class*='name']", "[class*='title']",
    "strong", "b",
]

STAND_PATTERNS = [
    re.compile(r"stand[:\s]*([A-Z\d][\w\-/]*)", re.IGNORECASE),
    re.compile(r"pabellón[:\s]*(\d+[\w\-/]*)", re.IGNORECASE),
    re.compile(r"hall[:\s]*([A-Z\d][\w\-/]*)", re.IGNORECASE),
    re.compile(r"booth[:\s]*([A-Z\d][\w\-/]*)", re.IGNORECASE),
    re.compile(r"stand\s+([\w\d]+)", re.IGNORECASE),
]


def _extract_stand_from_text(text: str) -> str | None:
    for pattern in STAND_PATTERNS:
        m = pattern.search(text)
        if m:
            return m.group(1).strip()
    return None


async def scrape_listing(page: Page, listing_url: str, max_companies: int | None = None) -> list[Company]:
    """
    Level 1: Extract companies from the event exhibitor listing page.
    Returns a list of Company objects with partial data (name, stand, profile URL).
    """
    logger.info(f"Level 1: scraping listing {listing_url}")
    companies: list[Company] = []
    seen_names: set[str] = set()

    # Try each selector until we find blocks
    blocks = None
    used_selector = None
    for selector in COMPANY_BLOCK_SELECTORS:
        try:
            count = await page.locator(selector).count()
            if count >= 3:
                blocks = page.locator(selector)
                used_selector = selector
                logger.info(f"Using selector '{selector}' → {count} blocks")
                break
        except Exception:
            continue

    if blocks is None:
        logger.warning("No structured blocks found, falling back to link extraction")
        return await _fallback_link_extraction(page, listing_url, max_companies)

    total = await blocks.count()
    limit = min(total, max_companies) if max_companies else total

    for i in range(limit):
        block = blocks.nth(i)
        try:
            block_text = await block.inner_text()
            block_html = await block.inner_html()
            if not block_text.strip():
                continue

            # Extract company name
            name = None
            for ns in NAME_SELECTORS:
                try:
                    el = block.locator(ns).first
                    if await el.count() > 0:
                        text = (await el.inner_text()).strip()
                        if text and len(text) > 1:
                            name = text
                            break
                except Exception:
                    continue
            if not name:
                # Fallback: first non-empty line
                lines = [l.strip() for l in block_text.split("\n") if l.strip()]
                name = lines[0] if lines else None
            if not name or len(name) < 2:
                continue

            norm = normalize_name(name)
            if norm in seen_names:
                continue
            seen_names.add(norm)

            # Extract stand
            stand = _extract_stand_from_text(block_text)

            # Extract category (text between stand and next heading, heuristic)
            category = None
            cat_match = re.search(
                r"(?:categoría|category|sector)[:\s]+([^\n]+)", block_text, re.IGNORECASE
            )
            if cat_match:
                category = cat_match.group(1).strip()

            # Extract profile link (first internal link in block)
            profile_url = None
            try:
                links = await block.locator("a").all()
                for link in links:
                    href = await link.get_attribute("href")
                    if href and not href.startswith(("mailto:", "tel:", "javascript:")):
                        abs_href = make_absolute(href, listing_url)
                        # Prefer links that look like exhibitor profiles
                        if any(kw in abs_href.lower() for kw in
                               ["expositor", "exhibitor", "empresa", "company", "stand", "participant"]):
                            profile_url = abs_href
                            break
                if not profile_url and links:
                    href = await links[0].get_attribute("href")
                    if href and not href.startswith(("mailto:", "tel:", "javascript:")):
                        profile_url = make_absolute(href, listing_url)
            except Exception:
                pass

            company = Company(
                name_original=name,
                name_normalized=norm,
                stand=stand,
                exhibitor_profile_url=profile_url,
                category=category,
            )
            companies.append(company)
            logger.debug(f"  Found: {name} | stand={stand} | profile={profile_url}")

        except Exception as e:
            logger.warning(f"Error parsing block {i}: {e}")
            continue

    logger.info(f"Level 1 complete: {len(companies)} companies extracted")
    return companies


async def _fallback_link_extraction(
    page: Page, base_url: str, max_companies: int | None
) -> list[Company]:
    """Fallback: extract unique-looking company links from the page."""
    companies = []
    seen: set[str] = set()

    links = await page.locator("a[href]").all()
    limit = max_companies or len(links)

    for link in links[:limit * 5]:  # scan more links to find enough
        try:
            href = await link.get_attribute("href")
            text = (await link.inner_text()).strip()
            if not href or not text or len(text) < 3:
                continue
            abs_href = make_absolute(href, base_url)
            norm = normalize_name(text)
            if norm in seen or len(norm) < 3:
                continue
            seen.add(norm)
            companies.append(Company(
                name_original=text,
                name_normalized=norm,
                exhibitor_profile_url=abs_href,
            ))
            if max_companies and len(companies) >= max_companies:
                break
        except Exception:
            continue

    logger.info(f"Fallback extracted {len(companies)} companies via links")
    return companies
