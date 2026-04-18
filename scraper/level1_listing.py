"""
Level 1 scraper: extract the list of exhibiting companies from the listing page.
Returns a list of Company objects with partial data (name, stand, profile URL).
"""
from __future__ import annotations
import re
from playwright.async_api import Page
from models import Company
from scraper.utils import normalize_name, make_absolute

# ── Block selectors (tried in order, first with ≥3 matches wins) ──────────────
# More specific selectors first, generic fallbacks last.
_BLOCK_SELECTORS = [
    # asp.events / iGB / Reed / Informa platform (m-exhibitors-list pattern)
    ".m-exhibitors-list__items__item",
    "li.m-exhibitors-list__items__item",
    # Other common event platforms
    ".exhibitor-card", ".exhibitor-item", ".exhibitor-tile",
    ".exhibitor-list-item", ".exhibitor-grid-item",
    "[class='exhibitor']",
    ".js-exhibitor", ".exhibitor-listing__item",
    "[class*='ExhibitorCard']", "[class*='exhibitor-card']",
    "[class*='CompanyCard']", "[class*='company-card']",
    # IFEMA / Feria Barcelona
    ".node--type-expositor", ".views-row",
    # Generic cards
    ".card--exhibitor", ".card--company",
    "ul.exhibitors > li", "ul.companies > li",
    # Last resort
    "li:has(h2)", "li:has(h3)", "article:has(h2)",
]

# ── Name selectors within a block ─────────────────────────────────────────────
_NAME_SELECTORS = [
    # asp.events platform
    ".m-exhibitors-list__items__item__header__title__link",
    ".m-exhibitors-list__items__item__header__title",
    # Generic
    "h2 a", "h3 a", "h2", "h3", "h4",
    ".company-name", ".nombre", ".title a", ".name a",
    "[class*='title__link']", "[class*='name__link']",
    "[class*='title']", "[class*='name']",
    "strong",
]

# ── Stand selectors within a block ────────────────────────────────────────────
_STAND_SELECTORS = [
    ".m-exhibitors-list__items__item__header__meta__stand",
    "[class*='stand']", "[class*='booth']", "[class*='pabellon']",
]

_STAND_RE = re.compile(
    r"(?:stand|booth|pabellón|hall)[:\s]*([A-Z\d][\w\-/]*)", re.IGNORECASE
)
_CATEGORY_RE = re.compile(
    r"(?:categoría|category|sector|actividad)[:\s]+([^\n]{3,60})", re.IGNORECASE
)

# Keywords in a URL that suggest it's an exhibitor profile
_PROFILE_KEYWORDS = (
    "expositor", "exhibitor", "empresa", "company",
    "stand", "participant", "brand", "patrocinador",
)


# ── Infinite scroll helper ────────────────────────────────────────────────────

async def _scroll_to_load_all(page: Page, max_companies: int | None) -> None:
    """
    Scroll the page incrementally to trigger lazy loading.
    Stops when no new content appears or we likely have enough companies.
    """
    prev_height = 0
    for _ in range(40):  # max 40 scroll steps
        curr_height = await page.evaluate("document.body.scrollHeight")
        if curr_height == prev_height:
            break
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(1200)
        prev_height = curr_height
        # If we already have more blocks than needed, stop early
        if max_companies:
            try:
                count = await page.locator(_BLOCK_SELECTORS[0]).count()
                if count >= max_companies * 2:
                    break
            except Exception:
                pass


# ── Main extraction ───────────────────────────────────────────────────────────

async def scrape_listing(
    page: Page,
    listing_url: str,
    max_companies: int | None = None,
) -> list[Company]:
    """
    Extract companies from the exhibitor listing page.
    Handles infinite scroll. Falls back to link-based extraction if needed.
    """
    # Scroll to load all (or enough) companies
    await _scroll_to_load_all(page, max_companies)

    companies: list[Company] = []
    seen_norms: set[str] = set()

    # Find the best block selector
    blocks = None
    used_selector = None
    for selector in _BLOCK_SELECTORS:
        try:
            count = await page.locator(selector).count()
            if count >= 3:
                blocks = page.locator(selector)
                used_selector = selector
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

            # ── Name ──────────────────────────────────────────────────────────
            name = await _extract_name(block, block_text)
            if not name or len(name) < 2:
                continue

            norm = normalize_name(name)
            if norm in seen_norms or len(norm) < 2:
                continue
            seen_norms.add(norm)

            # ── Stand ──────────────────────────────────────────────────────────
            stand = await _extract_stand(block, block_text)

            # ── Category ───────────────────────────────────────────────────────
            category = None
            m = _CATEGORY_RE.search(block_text)
            if m:
                category = m.group(1).strip()

            # ── Profile URL ────────────────────────────────────────────────────
            profile_url = await _extract_profile_url(block, listing_url)

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


# ── Name extraction ───────────────────────────────────────────────────────────

async def _extract_name(block, block_text: str) -> str | None:
    # Try structured selectors first
    for sel in _NAME_SELECTORS:
        try:
            el = block.locator(sel).first
            if await el.count() > 0:
                # Try aria-label first (often cleaner)
                aria = await el.get_attribute("aria-label")
                if aria and len(aria.strip()) > 1:
                    return aria.strip()
                t = (await el.inner_text()).strip()
                if len(t) > 1:
                    return t
        except Exception:
            continue

    # Try aria-label on any link in the block
    try:
        links = await block.locator("a[aria-label]").all()
        for link in links:
            label = await link.get_attribute("aria-label")
            if label and len(label.strip()) > 2:
                return label.strip()
    except Exception:
        pass

    # Try alt text of the first image
    try:
        img = block.locator("img[alt]").first
        if await img.count() > 0:
            alt = (await img.get_attribute("alt") or "").strip()
            if len(alt) > 2 and alt.lower() not in ("logo", "imagen", "image", "photo"):
                return alt
    except Exception:
        pass

    # Fallback: first non-empty line of text
    lines = [l.strip() for l in block_text.split("\n") if l.strip()]
    return lines[0] if lines else None


# ── Stand extraction ──────────────────────────────────────────────────────────

async def _extract_stand(block, block_text: str) -> str | None:
    for sel in _STAND_SELECTORS:
        try:
            el = block.locator(sel).first
            if await el.count() > 0:
                t = (await el.inner_text()).strip()
                if t:
                    m = _STAND_RE.search(t)
                    return m.group(1).strip() if m else t
        except Exception:
            continue
    m = _STAND_RE.search(block_text)
    return m.group(1).strip() if m else None


# ── Profile URL extraction ────────────────────────────────────────────────────

async def _extract_profile_url(block, listing_url: str) -> str | None:
    try:
        links = await block.locator("a[href]").all()
        # Prefer links that look like exhibitor profiles
        for link in links:
            href = await link.get_attribute("href") or ""
            if href.startswith(("mailto:", "tel:", "javascript:", "#")):
                continue
            abs_href = make_absolute(href, listing_url)
            if any(kw in abs_href.lower() for kw in _PROFILE_KEYWORDS):
                return abs_href
        # Fallback: first valid link
        for link in links:
            href = await link.get_attribute("href") or ""
            if not href.startswith(("mailto:", "tel:", "javascript:", "#")):
                return make_absolute(href, listing_url)
    except Exception:
        pass
    return None


# ── Fallback: harvest links ───────────────────────────────────────────────────

async def _fallback_links(
    page: Page, base_url: str, max_companies: int | None
) -> list[Company]:
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
