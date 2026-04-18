from __future__ import annotations
from playwright.async_api import Page, BrowserContext
from loguru import logger
from models.company import Company
from scraper.utils import (
    extract_emails, extract_phone, normalize_url,
    is_valid_url, make_absolute, extract_domain,
)
import re

# Selectors for the corporate website link inside an exhibitor profile
WEBSITE_SELECTORS = [
    "a[href*='http']:not([href*='facebook']):not([href*='instagram'])"
    ":not([href*='twitter']):not([href*='linkedin']):not([href*='youtube'])"
    ":not([href*='tiktok']):not([href*='google'])",
    "[class*='website'] a", "[class*='web'] a",
    "[class*='url'] a", "[class*='link'] a",
    "a[rel='external']", "a[target='_blank']",
]

DESCRIPTION_SELECTORS = [
    "[class*='description']", "[class*='descripcion']", "[class*='about']",
    "[class*='profile-text']", "[class*='company-info']", "[class*='empresa-info']",
    "[class*='bio']", "[class*='resumen']", "[class*='summary']",
    "p",
]

# Domains to explicitly skip (social, etc.)
SKIP_DOMAINS = {
    "facebook.com", "instagram.com", "twitter.com", "x.com",
    "linkedin.com", "youtube.com", "tiktok.com", "pinterest.com",
    "google.com", "maps.google.com", "wa.me", "whatsapp.com",
}


def _is_corporate_url(url: str, base_domain: str) -> bool:
    domain = extract_domain(url)
    if not domain:
        return False
    # Skip known social/search domains
    for skip in SKIP_DOMAINS:
        if domain.endswith(skip):
            return False
    # Skip if same domain as the event listing itself
    if base_domain and domain.endswith(base_domain):
        return False
    return True


async def scrape_profile(
    company: Company,
    context: BrowserContext,
    event_base_domain: str,
) -> Company:
    """
    Level 2: Visit the exhibitor's profile page within the event website.
    Fills: description, website_from_event, category (if not already set).
    """
    if not company.exhibitor_profile_url:
        logger.debug(f"No profile URL for {company.name_original}, skipping L2")
        return company

    profile_url = company.exhibitor_profile_url
    logger.debug(f"Level 2: {company.name_original} → {profile_url}")

    page = await context.new_page()
    try:
        await page.goto(profile_url, timeout=30_000, wait_until="domcontentloaded")
        await page.wait_for_timeout(1500)

        body_text = await page.inner_text("body")

        # Extract description
        description = None
        for sel in DESCRIPTION_SELECTORS:
            try:
                el = page.locator(sel).first
                if await el.count() > 0:
                    text = (await el.inner_text()).strip()
                    if len(text) > 40:
                        description = text[:1000]
                        break
            except Exception:
                continue
        if description:
            company.description = description

        # Extract category if not already set
        if not company.category:
            cat_match = re.search(
                r"(?:categoría|category|sector|actividad)[:\s]+([^\n]+)",
                body_text, re.IGNORECASE
            )
            if cat_match:
                company.category = cat_match.group(1).strip()

        # Extract stand if not already set
        if not company.stand:
            stand_match = re.search(
                r"(?:stand|booth|pabellón|hall)[:\s]*([A-Z\d][\w\-/]*)",
                body_text, re.IGNORECASE
            )
            if stand_match:
                company.stand = stand_match.group(1).strip()

        # Extract corporate website
        corporate_url = None
        # First try: explicit website link
        for sel in WEBSITE_SELECTORS:
            try:
                links = await page.locator(sel).all()
                for link in links:
                    href = await link.get_attribute("href")
                    if href and is_valid_url(href) and _is_corporate_url(href, event_base_domain):
                        corporate_url = href
                        break
                if corporate_url:
                    break
            except Exception:
                continue

        # Second try: scan all links for external-looking ones
        if not corporate_url:
            try:
                all_links = await page.locator("a[href^='http']").all()
                for link in all_links:
                    href = await link.get_attribute("href")
                    if href and _is_corporate_url(href, event_base_domain):
                        corporate_url = href
                        break
            except Exception:
                pass

        # Third try: look for text that says "website" or "web" next to a URL
        if not corporate_url:
            url_like = re.findall(
                r"https?://[^\s\"'<>]+", body_text
            )
            for u in url_like:
                if _is_corporate_url(u, event_base_domain):
                    corporate_url = u
                    break

        if corporate_url:
            company.website_from_event = normalize_url(corporate_url)
            logger.debug(f"  Found corporate URL: {corporate_url}")

    except Exception as e:
        logger.warning(f"Level 2 failed for {company.name_original}: {e}")
    finally:
        await page.close()

    return company
