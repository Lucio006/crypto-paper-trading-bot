"""
Level 2 scraper: visit each exhibitor's profile page within the event website.
Fills: description, website_from_event, stand and category (if missing from L1).
"""
from __future__ import annotations
import re
from playwright.async_api import BrowserContext
from models import Company
from scraper.utils import normalize_url, is_valid_url, make_absolute, extract_domain

# ── Domains that are NEVER a company's corporate website ──────────────────────
# (event registration forms, booking platforms, social media, etc.)
_SKIP_DOMAINS = {
    # Social
    "facebook.com", "instagram.com", "twitter.com", "x.com",
    "linkedin.com", "youtube.com", "tiktok.com", "pinterest.com",
    # Search / maps
    "google.com", "maps.google.com", "bing.com",
    # Messaging
    "whatsapp.com", "wa.me", "t.me", "telegram.me",
    # Event registration / booking platforms (common false positives)
    "reg.buzz", "forms.reg.buzz",
    "eventbrite.com", "cvent.com", "hopin.com",
    "eventtia.com", "accelevents.com",
    "hubspot.com", "mailchimp.com",
    # Common CDNs and infrastructure
    "cloudflare.com", "amazonaws.com", "azure.com",
}

# ── Text patterns that indicate a "website" link ──────────────────────────────
_WEBSITE_LINK_TEXT = re.compile(
    r"(?:web(?:site)?|sitio\s*web|visitar\s*web|visit\s*website|"
    r"ver\s*web|go\s*to\s*website|homepage|página\s*web)",
    re.IGNORECASE,
)

# ── CSS selectors for the website field on exhibitor profile pages ─────────────
_WEBSITE_FIELD_SELECTORS = [
    # asp.events / iGB platform
    "[class*='website']",
    "[class*='web-link']",
    "[class*='company-website']",
    "[class*='exhibitor-website']",
    # Generic
    "[class*='social'] a[href^='http']",
    "[data-field='website'] a",
    "[data-label='website'] a",
    "a[title*='website' i]",
    "a[title*='web' i]",
]

# ── Selectors for description text ─────────────────────────────────────────────
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
    """Return True only if this URL could be a real company website."""
    if not url or not is_valid_url(url):
        return False
    domain = extract_domain(url)
    if not domain:
        return False
    for skip in _SKIP_DOMAINS:
        if domain == skip or domain.endswith("." + skip):
            return False
    # Reject if it belongs to the event site itself
    if event_domain and (domain == event_domain or domain.endswith("." + event_domain)):
        return False
    return True


async def scrape_profile(
    company: Company,
    context: BrowserContext,
    event_domain: str,
) -> Company:
    if not company.exhibitor_profile_url:
        return company

    page = await context.new_page()
    try:
        await page.goto(
            company.exhibitor_profile_url,
            timeout=25_000,
            wait_until="domcontentloaded",
        )
        await page.wait_for_timeout(1500)
        body_text = await page.inner_text("body")

        # ── Description ────────────────────────────────────────────────────────
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

        # ── Stand / Category (if missing from L1) ──────────────────────────────
        if not company.stand:
            m = _STAND_RE.search(body_text)
            if m:
                company.stand = m.group(1).strip()
        if not company.category:
            m = _CATEGORY_RE.search(body_text)
            if m:
                company.category = m.group(1).strip()

        # ── Corporate website — 3 passes ───────────────────────────────────────
        corporate_url = None

        # Pass 1: dedicated "website" field selectors
        for sel in _WEBSITE_FIELD_SELECTORS:
            try:
                links = await page.locator(sel).all()
                for link in links:
                    href = (await link.get_attribute("href") or "").strip()
                    if _is_corporate(href, event_domain):
                        corporate_url = href
                        break
                if corporate_url:
                    break
            except Exception:
                continue

        # Pass 2: links whose visible text says "website" or "web"
        if not corporate_url:
            try:
                all_links = await page.locator("a[href^='http']").all()
                for link in all_links:
                    text = (await link.inner_text()).strip()
                    href = (await link.get_attribute("href") or "").strip()
                    if _WEBSITE_LINK_TEXT.search(text) and _is_corporate(href, event_domain):
                        corporate_url = href
                        break
            except Exception:
                pass

        # Pass 3: any external link that's not a known non-corporate domain
        if not corporate_url:
            try:
                all_links = await page.locator("a[href^='http']").all()
                for link in all_links:
                    href = (await link.get_attribute("href") or "").strip()
                    if _is_corporate(href, event_domain):
                        corporate_url = href
                        break
            except Exception:
                pass

        # Pass 4: raw URLs in body text
        if not corporate_url:
            for raw in re.findall(r"https?://[^\s\"'<>]{8,}", body_text):
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
