from __future__ import annotations
import re
from playwright.async_api import BrowserContext
from loguru import logger
from models.company import Company
from scraper.utils import (
    extract_emails, classify_emails, extract_phone, extract_telegram,
    normalize_url, extract_domain, reason_for_missing,
)

# Pages to visit within a corporate website (in priority order)
CONTACT_PATHS = [
    "/contacto", "/contact", "/contact-us", "/contactenos",
    "/sobre-nosotros/contacto", "/about/contact",
]

ABOUT_PATHS = [
    "/quienes-somos", "/about", "/about-us", "/nosotros", "/empresa",
    "/sobre-nosotros", "/our-team", "/nuestro-equipo",
]

# What to look for to determine page has only a form (no direct email)
FORM_INDICATORS = ["<form", "<input", "<textarea"]


def _has_only_form(html: str) -> bool:
    lower = html.lower()
    has_form = any(ind in lower for ind in FORM_INDICATORS)
    has_email = re.search(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", lower)
    return has_form and not has_email


async def _visit_page(context: BrowserContext, url: str) -> tuple[str, str, str]:
    """Returns (text, html, status). status: ok | timeout | error | blocked."""
    page = await context.new_page()
    try:
        response = await page.goto(url, timeout=20_000, wait_until="domcontentloaded")
        await page.wait_for_timeout(1500)
        if response and response.status >= 400:
            return "", "", f"http_{response.status}"
        text = await page.inner_text("body")
        html = await page.content()
        return text, html, "ok"
    except Exception as e:
        err_str = str(e).lower()
        if "timeout" in err_str:
            return "", "", "timeout"
        return "", "", f"error: {err_str[:60]}"
    finally:
        await page.close()


async def scrape_corporate(company: Company, context: BrowserContext) -> Company:
    """
    Level 3: Visit the corporate website and extract contact information.
    Fills ContactData fields and reasons for missing data.
    """
    website = company.website_from_event or company.corporate_website
    if not website:
        company.contact.reason_no_website = "No aparece web corporativa en la ficha del evento"
        _fill_all_missing_reasons(company, "no_website")
        logger.debug(f"No corporate URL for {company.name_original}")
        return company

    website = normalize_url(website)
    company.corporate_website = website
    company.domain = extract_domain(website)

    logger.info(f"Level 3: {company.name_original} → {website}")

    # Collect text from multiple pages
    all_emails: list[str] = []
    all_text: str = ""
    page_status = "ok"
    content_hints: list[str] = []
    visited_pages: list[str] = []

    # 1. Homepage
    text, html, status = await _visit_page(context, website)
    page_status = status
    if status == "ok":
        all_text += text + "\n"
        all_emails += extract_emails(text)
        visited_pages.append(website)
        if _has_only_form(html):
            content_hints.append("form_only")
    else:
        logger.warning(f"  Homepage {status}: {website}")
        _fill_all_missing_reasons(company, status)
        return company

    # 2. Contact page(s)
    contact_found = False
    for path in CONTACT_PATHS:
        url = website.rstrip("/") + path
        text, html, status = await _visit_page(context, url)
        if status == "ok":
            all_text += text + "\n"
            new_emails = extract_emails(text)
            all_emails += new_emails
            visited_pages.append(url)
            if _has_only_form(html) and not new_emails:
                content_hints.append("form_only")
            contact_found = True
            break
    if not contact_found:
        content_hints.append("no_contact_page")

    # 3. About/team page
    for path in ABOUT_PATHS:
        url = website.rstrip("/") + path
        text, html, status = await _visit_page(context, url)
        if status == "ok":
            all_text += text + "\n"
            all_emails += extract_emails(text)
            visited_pages.append(url)
            break

    # Classify emails
    classified = classify_emails(list(dict.fromkeys(all_emails)))  # dedup preserving order
    c = company.contact
    c.email_general = classified["email_general"]
    c.email_marketing = classified["email_marketing"]
    c.email_events = classified["email_events"]
    c.email_ceo = classified["email_ceo"]
    c.email_cco = classified["email_cco"]

    # Phone and Telegram
    c.phone = extract_phone(all_text)
    c.telegram = extract_telegram(all_text)

    # Source tracking
    c.page_where_found = " | ".join(visited_pages)
    if all_emails:
        c.evidence_text = f"Emails encontrados: {', '.join(set(all_emails))[:200]}"
    c.confidence_level = _confidence(classified, c.phone)

    # Fill missing reasons
    _fill_missing_reasons(company, page_status, content_hints)

    logger.info(
        f"  Emails: general={c.email_general} mkt={c.email_marketing} "
        f"events={c.email_events} phone={c.phone} telegram={c.telegram}"
    )
    return company


def _confidence(classified: dict, phone: str | None) -> str:
    found = sum(1 for v in classified.values() if v) + (1 if phone else 0)
    if found >= 3:
        return "Alta"
    if found >= 1:
        return "Media"
    return "Baja"


def _fill_all_missing_reasons(company: Company, status: str) -> None:
    _fill_missing_reasons(company, status, [])


def _fill_missing_reasons(company: Company, page_status: str, hints: list[str]) -> None:
    c = company.contact
    if not c.email_marketing:
        c.reason_no_marketing = reason_for_missing("email_marketing", page_status, hints)
    if not c.email_events:
        c.reason_no_events = reason_for_missing("email_events", page_status, hints)
    if not c.email_ceo:
        c.reason_no_ceo = reason_for_missing("email_ceo", page_status, hints)
    if not c.email_cco:
        c.reason_no_cco = reason_for_missing("email_cco", page_status, hints)
    if not c.telegram:
        c.reason_no_telegram = reason_for_missing("telegram", page_status, hints)
    if not company.corporate_website:
        c.reason_no_website = reason_for_missing("website", "no_website", hints)
