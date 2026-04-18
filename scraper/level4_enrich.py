"""
Level 4: Web search enrichment via DuckDuckGo.
For each company, launches targeted searches to find emails and phones
from across the internet (company directories, press releases, LinkedIn, etc.).
Falls back gracefully if blocked or no results.
"""
from __future__ import annotations
import asyncio
import re
from urllib.parse import quote_plus
from playwright.async_api import BrowserContext
from models import Company
from scraper.utils import extract_emails, classify_emails, extract_phone, extract_telegram

_DDG_HTML = "https://html.duckduckgo.com/html/?q={q}&kl=es-es"

# Noisy/irrelevant domains to ignore when collecting emails from search results
_NOISE_DOMAINS = {
    "example.com", "sentry.io", "w3.org", "schema.org",
    "google.com", "bing.com", "duckduckgo.com", "facebook.com",
    "twitter.com", "youtube.com", "instagram.com",
    "wix.com", "wordpress.com", "squarespace.com",
}


async def enrich_web(company: Company, context: BrowserContext) -> Company:
    """
    Search DuckDuckGo for contact info for this company.
    Mutates and returns company. Never raises.
    """
    queries = _build_queries(company)
    all_text: list[str] = []

    for query in queries:
        try:
            text = await _ddg_search(context, query)
            if text:
                all_text.append(text)
            await asyncio.sleep(2)
        except Exception:
            continue

    if all_text:
        _merge(company, " ".join(all_text))

    return company


def _build_queries(company: Company) -> list[str]:
    name = company.name_original
    domain = company.domain or ""
    queries: list[str] = []

    # Most targeted: any page on the web mentioning an email from their domain
    if domain:
        queries.append(f'"@{domain}"')

    # General contact search
    queries.append(f'"{name}" email contact')

    # LinkedIn company page
    queries.append(f'"{name}" site:linkedin.com/company')

    return queries


async def _ddg_search(context: BrowserContext, query: str) -> str:
    """Fetch DuckDuckGo HTML results and return all visible text."""
    url = _DDG_HTML.format(q=quote_plus(query))
    page = await context.new_page()
    try:
        await page.goto(url, timeout=30_000, wait_until="domcontentloaded")
        await page.wait_for_timeout(1_000)

        # Check if we got blocked / redirected to a CAPTCHA
        current = page.url
        if "duckduckgo.com" not in current and "html" not in current:
            return ""

        # Extract snippet text from result elements
        snippets: list[str] = []

        # DuckDuckGo HTML result selectors
        for sel in [".result__snippet", ".result__body", ".result__title", "a.result__url"]:
            els = await page.locator(sel).all()
            for el in els[:30]:
                try:
                    t = await el.inner_text()
                    if t:
                        snippets.append(t)
                except Exception:
                    pass

        # Fallback: full body text (slower but catches everything)
        if not snippets:
            snippets.append(await page.inner_text("body"))

        return " ".join(snippets)
    finally:
        await page.close()


def _merge(company: Company, text: str) -> None:
    """Extract contact info from search result text and fill empty fields."""
    c = company.contact

    # ── Emails ────────────────────────────────────────────────────────────────
    emails = extract_emails(text)

    # Prefer emails from the company's own domain
    if company.domain:
        own = [e for e in emails if company.domain in e]
        # Use own-domain emails first, then fall back to anything found
        prioritized = own + [e for e in emails if company.domain not in e]
    else:
        prioritized = emails

    # Filter out obvious noise
    prioritized = [
        e for e in prioritized
        if not any(nd in e for nd in _NOISE_DOMAINS)
    ]

    if prioritized:
        classified = classify_emails(prioritized)
        if not c.email_marketing:
            c.email_marketing = classified.get("email_marketing")
        if not c.email_events:
            c.email_events = classified.get("email_events")
        if not c.email_ceo:
            c.email_ceo = classified.get("email_ceo")
        if not c.email_cco:
            c.email_cco = classified.get("email_cco")
        # Only fill general if no specialized email was found at all
        if not c.email_general and not c.any_email():
            c.email_general = classified.get("email_general") or prioritized[0]

    # ── Phone ─────────────────────────────────────────────────────────────────
    if not c.phone:
        c.phone = extract_phone(text)

    # ── Telegram ──────────────────────────────────────────────────────────────
    if not c.telegram:
        c.telegram = extract_telegram(text)

    # ── LinkedIn URL ──────────────────────────────────────────────────────────
    m = re.search(r"linkedin\.com/company/[\w\-]+", text, re.IGNORECASE)
    if m and not company.notes:
        company.notes = f"LinkedIn: https://{m.group(0)}"
