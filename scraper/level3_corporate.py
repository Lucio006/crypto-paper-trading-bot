"""
Level 3 scraper: visit the corporate website and extract contact information.
Fills ContactData fields and reasons for any missing fields.
"""
from __future__ import annotations
import re
from playwright.async_api import BrowserContext
from models import Company
from scraper.utils import (
    extract_emails, classify_emails,
    extract_phone, extract_telegram,
    normalize_url, extract_domain,
    reason_for_missing,
)

# Sub-pages to visit within the corporate site, in priority order
_CONTACT_PATHS = [
    "/contacto", "/contact", "/contact-us", "/contactenos",
    "/contacta", "/contacta-con-nosotros",
    "/sobre-nosotros/contacto", "/about/contact",
]
_ABOUT_PATHS = [
    "/quienes-somos", "/about", "/about-us", "/nosotros",
    "/empresa", "/sobre-nosotros", "/our-team",
]


def _has_only_form(html: str) -> bool:
    """True if the page has a form but no visible email address."""
    lower = html.lower()
    has_form = "<form" in lower or "<input" in lower
    has_email = bool(re.search(r"[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}", lower))
    return has_form and not has_email


async def _fetch(context: BrowserContext, url: str) -> tuple[str, str, str]:
    """
    Load a URL and return (body_text, html, status).
    status: 'ok' | 'timeout' | 'http_NNN' | 'error'
    """
    page = await context.new_page()
    try:
        resp = await page.goto(url, timeout=18_000, wait_until="domcontentloaded")
        await page.wait_for_timeout(1000)
        if resp and resp.status >= 400:
            return "", "", f"http_{resp.status}"
        text = await page.inner_text("body")
        html = await page.content()
        return text, html, "ok"
    except Exception as e:
        status = "timeout" if "timeout" in str(e).lower() else f"error"
        return "", "", status
    finally:
        await page.close()


async def scrape_corporate(company: Company, context: BrowserContext) -> Company:
    """
    Visit the corporate website (up to 3 pages) and populate ContactData.
    Always fills 'reason_no_*' fields when data is absent — never leaves them blank.
    """
    url = company.website_from_event or company.corporate_website
    if not url:
        company.contact.reason_no_website = "No aparece web corporativa en la ficha del evento"
        _fill_all_reasons(company, "no_website", [])
        return company

    url = normalize_url(url)
    company.corporate_website = url
    company.domain = extract_domain(url)

    all_text = ""
    all_emails: list[str] = []
    hints: list[str] = []
    visited: list[str] = []
    page_status = "ok"

    # ── Homepage ─────────────────────────────────────────────────────────────
    text, html, status = await _fetch(context, url)
    page_status = status
    if status != "ok":
        _fill_all_reasons(company, status, [])
        return company
    all_text += text + "\n"
    all_emails += extract_emails(text)
    visited.append(url)
    if _has_only_form(html):
        hints.append("form_only")

    # ── Contact page ─────────────────────────────────────────────────────────
    contact_found = False
    for path in _CONTACT_PATHS:
        contact_url = url.rstrip("/") + path
        text, html, status = await _fetch(context, contact_url)
        if status == "ok":
            new_emails = extract_emails(text)
            all_text += text + "\n"
            all_emails += new_emails
            visited.append(contact_url)
            if _has_only_form(html) and not new_emails:
                hints.append("form_only")
            contact_found = True
            break
    if not contact_found:
        hints.append("no_contact_page")

    # ── About / team page ─────────────────────────────────────────────────────
    for path in _ABOUT_PATHS:
        about_url = url.rstrip("/") + path
        text, _, status = await _fetch(context, about_url)
        if status == "ok":
            all_text += text + "\n"
            all_emails += extract_emails(text)
            visited.append(about_url)
            break

    # ── Classify ─────────────────────────────────────────────────────────────
    unique_emails = list(dict.fromkeys(all_emails))   # deduplicate, preserve order
    classified = classify_emails(unique_emails)

    c = company.contact
    c.email_general   = classified["email_general"]
    c.email_marketing = classified["email_marketing"]
    c.email_events    = classified["email_events"]
    c.email_ceo       = classified["email_ceo"]
    c.email_cco       = classified["email_cco"]
    c.phone           = extract_phone(all_text)
    c.telegram        = extract_telegram(all_text)

    # Evidence
    c.page_where_found = " | ".join(visited)
    if unique_emails:
        c.evidence_text = f"Emails: {', '.join(unique_emails[:5])}"
    found_count = sum(1 for v in [c.email_general, c.email_marketing, c.email_events,
                                   c.email_ceo, c.email_cco, c.phone] if v)
    c.confidence_level = "Alta" if found_count >= 3 else ("Media" if found_count >= 1 else "Baja")

    # Fill reasons for missing fields
    _fill_all_reasons(company, page_status, hints)
    return company


def _fill_all_reasons(company: Company, status: str, hints: list[str]) -> None:
    c = company.contact
    if not c.email_marketing:
        c.reason_no_marketing = reason_for_missing("email_marketing", status, hints)
    if not c.email_events:
        c.reason_no_events = reason_for_missing("email_events", status, hints)
    if not c.email_ceo:
        c.reason_no_ceo = reason_for_missing("email_ceo", status, hints)
    if not c.email_cco:
        c.reason_no_cco = reason_for_missing("email_cco", status, hints)
    if not c.telegram:
        c.reason_no_telegram = reason_for_missing("telegram", status, hints)
    if not company.corporate_website:
        c.reason_no_website = reason_for_missing("website", "no_website", hints)
