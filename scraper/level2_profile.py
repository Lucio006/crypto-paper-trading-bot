"""
Level 2 scraper: visit each exhibitor's profile page within the event website.
Fills: description, website_from_event, stand and category (if missing from L1).
"""
from __future__ import annotations
import re
from playwright.async_api import BrowserContext, Page
from models import Company
from scraper.utils import normalize_url, is_valid_url, make_absolute, extract_domain

# ── Domains that are NEVER a company's corporate website ──────────────────────
_SKIP_DOMAINS = {
    "facebook.com", "instagram.com", "twitter.com", "x.com",
    "linkedin.com", "youtube.com", "tiktok.com", "pinterest.com",
    "google.com", "maps.google.com", "bing.com",
    "whatsapp.com", "wa.me", "t.me", "telegram.me",
    "reg.buzz", "forms.reg.buzz",
    "eventbrite.com", "cvent.com", "hopin.com",
    "eventtia.com", "accelevents.com",
    "hubspot.com", "mailchimp.com",
    "cloudflare.com", "amazonaws.com", "azure.com",
}

# ── "Website" link text patterns ──────────────────────────────────────────────
_WEBSITE_TEXT_RE = re.compile(
    r"(?:web(?:site)?|sitio\s*web|visitar\s*web|visit\s*website|"
    r"ver\s*web|go\s*to\s*website|homepage|página\s*web)",
    re.IGNORECASE,
)

# ── Description selectors ─────────────────────────────────────────────────────
_DESC_SELECTORS = [
    "[class*='description']", "[class*='descripcion']",
    "[class*='about']", "[class*='profile-text']",
    "[class*='company-info']", "[class*='bio']",
    "[class*='resumen']", "[class*='summary']",
    ".panel__body", ".panel",
    ".field--name-body",
    "article p", "section p",
]

_STAND_RE = re.compile(
    r"(?:stand|booth|pabellón|hall)[:\s]*([A-Z\d][\w\-/.]*)", re.IGNORECASE
)
_CATEGORY_RE = re.compile(
    r"(?:categoría|category|sector|actividad)[:\s]+([^\n]{3,60})", re.IGNORECASE
)


# ── Cookie consent handler ────────────────────────────────────────────────────

async def _accept_cookies(page: Page) -> None:
    """
    Try to dismiss cookie consent banners before reading page content.
    Tries common button selectors silently — never raises.
    """
    selectors = [
        "#onetrust-accept-btn-handler",
        ".ot-btn-accept-all",
        "button#accept-all",
        "button[id*='accept']",
        "button[class*='accept']",
    ]
    texts = [
        "Aceptar todo", "Aceptar todas", "Aceptar",
        "Accept All", "Accept all", "Accept",
        "Akzeptieren", "Tout accepter",
    ]
    for sel in selectors:
        try:
            btn = page.locator(sel).first
            if await btn.count() > 0 and await btn.is_visible():
                await btn.click()
                await page.wait_for_timeout(800)
                return
        except Exception:
            continue
    for text in texts:
        try:
            btn = page.get_by_role("button", name=text)
            if await btn.count() > 0 and await btn.is_visible():
                await btn.click()
                await page.wait_for_timeout(800)
                return
        except Exception:
            continue


# ── URL validation ────────────────────────────────────────────────────────────

def _is_corporate(url: str, event_domain: str) -> bool:
    if not url or not is_valid_url(url):
        return False
    domain = extract_domain(url)
    if not domain or "." not in domain:
        return False
    for skip in _SKIP_DOMAINS:
        if domain == skip or domain.endswith("." + skip):
            return False
    if event_domain and (domain == event_domain or domain.endswith("." + event_domain)):
        return False
    return True


# ── Main ──────────────────────────────────────────────────────────────────────

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

        # Dismiss cookie banner if present
        await _accept_cookies(page)
        await page.wait_for_timeout(1000)

        body_text = await page.inner_text("body")

        # ── Description ────────────────────────────────────────────────────────
        if not company.description:
            for sel in _DESC_SELECTORS:
                try:
                    el = page.locator(sel).first
                    if await el.count() > 0:
                        text = (await el.inner_text()).strip()
                        # Reject cookie consent text
                        if len(text) > 40 and "cookie" not in text.lower()[:80]:
                            company.description = text[:1000]
                            break
                except Exception:
                    continue

        # ── Stand / Category ───────────────────────────────────────────────────
        if not company.stand:
            m = _STAND_RE.search(body_text)
            if m:
                company.stand = m.group(1).strip()
        if not company.category:
            m = _CATEGORY_RE.search(body_text)
            if m:
                company.category = m.group(1).strip()

        # ── Corporate website — 4 passes ───────────────────────────────────────
        corporate_url = await _find_corporate_url(page, body_text, event_domain)
        if corporate_url:
            company.website_from_event = normalize_url(corporate_url)

    except Exception:
        pass
    finally:
        await page.close()

    return company


async def _find_corporate_url(page: Page, body_text: str, event_domain: str) -> str | None:
    # Pass 1: links whose text explicitly says "website"
    try:
        for link in await page.locator("a[href]").all():
            text = (await link.inner_text()).strip()
            href = (await link.get_attribute("href") or "").strip()
            if _WEBSITE_TEXT_RE.search(text) and _is_corporate(href, event_domain):
                return href
    except Exception:
        pass

    # Pass 2: links in elements with "website" or "web" in the class name
    try:
        for link in await page.locator("[class*='website'] a, [class*='web-link'] a").all():
            href = (await link.get_attribute("href") or "").strip()
            if _is_corporate(href, event_domain):
                return href
    except Exception:
        pass

    # Pass 3: any valid external link not on the skip list
    try:
        for link in await page.locator("a[href^='http']").all():
            href = (await link.get_attribute("href") or "").strip()
            if _is_corporate(href, event_domain):
                return href
    except Exception:
        pass

    # Pass 4: raw URLs in body text
    for raw in re.findall(r"https?://[^\s\"'<>]{8,}", body_text):
        if _is_corporate(raw, event_domain):
            return raw

    return None
