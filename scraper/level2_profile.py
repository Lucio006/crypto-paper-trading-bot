"""
Level 2 scraper: visit each exhibitor's profile page within the event website.
Fills: description, website_from_event, stand and category (if missing from L1).
"""
from __future__ import annotations
import re
from playwright.async_api import BrowserContext
from models import Company
from scraper.utils import normalize_url, is_valid_url, make_absolute, extract_domain

# Domains to skip when looking for the corporate website
_SKIP_DOMAINS = {
    "facebook.com", "instagram.com", "twitter.com", "x.com",
    "linkedin.com", "youtube.com", "tiktok.com", "pinterest.com",
    "google.com", "whatsapp.com", "wa.me",
}

# Selectors for description text within an exhibitor profile
_DESC_SELECTORS = [
    "[class*='description']", "[class*='descripcion']",
    "[class*='about']", "[class*='profile-text']",
    "[class*='company-info']", "[class*='bio']",
    "[class*='resumen']", "[class*='summary']",
    ".field--name-body", ".field--name-field-descripcion",
    "article p", "section p",
]

_STAND_RE = re.compile(
    r"(?:stand|booth|pabellón|hall)[:\s]*([A-Z\d][\w\-/.]*)", re.IGNORECASE
)
_CATEGORY_RE = re.compile(
    r"(?:categoría|category|sector|actividad)[:\s]+([^\n]{3,60})", re.IGNORECASE
)


def _is_corporate(url: str, event_domain: str) -> bool:
    domain = extract_domain(url)
    if not domain:
        return False
    for skip in _SKIP_DOMAINS:
        if domain.endswith(skip):
            return False
    # Reject URLs that belong to the event site itself
    if event_domain and (domain == event_domain or domain.endswith("." + event_domain)):
        return False
    return True


async def scrape_profile(
    company: Company,
    context: BrowserContext,
    event_domain: str,
) -> Company:
    """
    Visit the exhibitor's profile page and enrich the Company object in place.
    Never raises — failures are silently skipped so the pipeline continues.
    """
    if not company.exhibitor_profile_url:
        return company

    page = await context.new_page()
    try:
        await page.goto(
            company.exhibitor_profile_url,
            timeout=25_000,
            wait_until="domcontentloaded",
        )
        await page.wait_for_timeout(1200)
        body_text = await page.inner_text("body")

        # ── Description ───────────────────────────────────────────────────────
        if not company.description:
            for sel in _DESC_SELECTORS:
                try:
                    el = page.locator(sel).first
                    if await el.count() > 0:
                        text = (await el.inner_text()).strip()
                        if len(text) > 40:
                            company.description = text[:1000]
                            break
                except Exception:
                    continue

        # ── Stand (if not found in L1) ────────────────────────────────────────
        if not company.stand:
            m = _STAND_RE.search(body_text)
            if m:
                company.stand = m.group(1).strip()

        # ── Category (if not found in L1) ─────────────────────────────────────
        if not company.category:
            m = _CATEGORY_RE.search(body_text)
            if m:
                company.category = m.group(1).strip()

        # ── Corporate website ─────────────────────────────────────────────────
        corporate_url = None

        # Pass 1: external links in the page
        try:
            links = await page.locator("a[href^='http']").all()
            for link in links:
                href = (await link.get_attribute("href") or "").strip()
                if is_valid_url(href) and _is_corporate(href, event_domain):
                    corporate_url = href
                    break
        except Exception:
            pass

        # Pass 2: raw URLs in body text (e.g., in a "Visitar web" text node)
        if not corporate_url:
            for raw in re.findall(r"https?://[^\s\"'<>]{6,}", body_text):
                if _is_corporate(raw, event_domain):
                    corporate_url = raw
                    break

        if corporate_url:
            company.website_from_event = normalize_url(corporate_url)

    except Exception:
        pass
    finally:
        await page.close()

    return company
