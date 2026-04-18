"""
Level 1 scraper: extract the list of exhibiting companies from the listing page.
Returns a list of Company objects with partial data (name, stand, profile URL).
"""
from __future__ import annotations
import re
from playwright.async_api import Page
from models import Company
from scraper.utils import normalize_name, make_absolute

# Ordered list of CSS selectors to try for company blocks
_BLOCK_SELECTORS = [
    # Platform-specific
    ".exhibitor-item", ".expositor-item", ".expositor-card",
    "[class*='exhibitor-list'] > *", "[class*='expositor-list'] > *",
    "[class*='company-card']", "[class*='empresa-card']",
    "[class*='participant-item']", "[class*='brand-item']",
    # IFEMA / Feria Barcelona
    ".node--type-expositor", ".views-row",
    # Generic cards and grids
    ".card", ".listing-card", ".grid-item",
    "[data-exhibitor]", "[data-company-id]",
    # Last resort
    "li:has(a[href])", "article:has(h2)",
]

# Ordered list of selectors for the company name within a block
_NAME_SELECTORS = ["h2", "h3", "h4", ".company-name", ".nombre", ".title", ".name",
                   "[class*='name']", "[class*='title']", "strong"]

_STAND_RE = re.compile(
    r"(?:stand|booth|pabellón|hall)[:\s]*([A-Z\d][\w\-/]*)", re.IGNORECASE
)
_CATEGORY_RE = re.compile(
    r"(?:categoría|category|sector|actividad)[:\s]+([^\n]{3,60})", re.IGNORECASE
)

# Keywords in a URL that suggest it's an exhibitor profile
_PROFILE_KEYWORDS = ("expositor", "exhibitor", "empresa", "company", "stand",
                     "participant", "brand", "patrocinador")


async def scrape_listing(
    page: Page,
    listing_url: str,
    max_companies: int | None = None,
) -> list[Company]:
    """
    Extract companies from the exhibitor listing page.
    Falls back to link-based extraction if no structured blocks are found.
    """
    companies: list[Company] = []
    seen_norms: set[str] = set()

    # Find the best selector
    blocks = None
    for selector in _BLOCK_SELECTORS:
        try:
            count = await page.locator(selector).count()
            if count >= 3:
                blocks = page.locator(selector)
                break
        except Exception:
            continue

    if blocks is None:
        return await _fallback_links(page, listing_url, max_companies)

    total = await blocks.count()
    limit = min(total, max_companies) if max_companies else total

    for i in range(limit):
        block = blocks.nth(i)
        try:
            block_text = (await block.inner_text()).strip()
            if not block_text:
                continue

            # ── Name ─────────────────────────────────────────────────────────
            name = None
            for ns in _NAME_SELECTORS:
                try:
                    el = block.locator(ns).first
                    if await el.count() > 0:
                        t = (await el.inner_text()).strip()
                        if len(t) > 1:
                            name = t
                            break
                except Exception:
                    continue
            if not name:
                lines = [l.strip() for l in block_text.split("\n") if l.strip()]
                name = lines[0] if lines else None
            if not name or len(name) < 2:
                continue

            norm = normalize_name(name)
            if norm in seen_norms or len(norm) < 2:
                continue
            seen_norms.add(norm)

            # ── Stand ─────────────────────────────────────────────────────────
            stand = None
            m = _STAND_RE.search(block_text)
            if m:
                stand = m.group(1).strip()

            # ── Category ──────────────────────────────────────────────────────
            category = None
            m = _CATEGORY_RE.search(block_text)
            if m:
                category = m.group(1).strip()

            # ── Profile URL ───────────────────────────────────────────────────
            profile_url = None
            try:
                links = await block.locator("a[href]").all()
                # Prefer links that look like exhibitor profiles
                for link in links:
                    href = await link.get_attribute("href") or ""
                    if href.startswith(("mailto:", "tel:", "javascript:")):
                        continue
                    abs_href = make_absolute(href, listing_url)
                    if any(kw in abs_href.lower() for kw in _PROFILE_KEYWORDS):
                        profile_url = abs_href
                        break
                if not profile_url and links:
                    href = await links[0].get_attribute("href") or ""
                    if not href.startswith(("mailto:", "tel:", "javascript:")):
                        profile_url = make_absolute(href, listing_url)
            except Exception:
                pass

            companies.append(Company(
                name_original=name,
                name_normalized=norm,
                stand=stand,
                category=category,
                exhibitor_profile_url=profile_url,
            ))

        except Exception:
            continue

    return companies


async def _fallback_links(
    page: Page, base_url: str, max_companies: int | None
) -> list[Company]:
    """Fallback: harvest unique-looking text links as company names."""
    companies: list[Company] = []
    seen: set[str] = set()
    links = await page.locator("a[href]").all()

    for link in links:
        try:
            href = await link.get_attribute("href") or ""
            text = (await link.inner_text()).strip()
            if not text or len(text) < 3 or href.startswith(("mailto:", "tel:", "#")):
                continue
            norm = normalize_name(text)
            if norm in seen or len(norm) < 3:
                continue
            seen.add(norm)
            companies.append(Company(
                name_original=text,
                name_normalized=norm,
                exhibitor_profile_url=make_absolute(href, base_url),
            ))
            if max_companies and len(companies) >= max_companies:
                break
        except Exception:
            continue

    return companies
