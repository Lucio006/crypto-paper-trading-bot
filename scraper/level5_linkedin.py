"""
Level 5: LinkedIn personal contact finder.
Uses a saved li_at session cookie to search LinkedIn directly.
Searches for employees by company name + role keywords.
Falls back gracefully if cookie missing or LinkedIn blocks.
"""
from __future__ import annotations
import asyncio
import re
from urllib.parse import quote_plus
from playwright.async_api import BrowserContext
from models import Company
from config import LINKEDIN_COOKIE

_SEARCH_URL = (
    "https://www.linkedin.com/search/results/people/"
    "?keywords={q}&origin=GLOBAL_SEARCH_HEADER"
)

_ROLE_FILTERS = [
    "events sponsorship",
    "marketing communications",
    "affiliate partnerships",
    "CEO CCO director",
]


async def find_personal_contacts(company: Company, context: BrowserContext) -> Company:
    """
    Search LinkedIn for employees of this company. Never raises.
    Requires LINKEDIN_COOKIE in .env — skips silently if missing.
    """
    if not LINKEDIN_COOKIE or not company.name_original:
        return company

    found: dict[str, dict] = {}

    for role in _ROLE_FILTERS:
        if len(found) >= 5:
            break
        query = f"{company.name_original} {role}"
        try:
            contacts = await _search_people(context, query, company.name_original)
            for c in contacts:
                key = c["url"].split("/in/")[-1].strip("/").lower()
                if key and key not in found:
                    found[key] = c
            await asyncio.sleep(3)
        except Exception:
            continue

    if found:
        lines = [
            f"{c['name']} — {c['title']} — {c['url']}"
            for c in list(found.values())[:5]
        ]
        company.personal_contacts = "\n".join(lines)

    return company


async def _search_people(context: BrowserContext, query: str, company_name: str) -> list[dict]:
    page = await context.new_page()
    contacts: list[dict] = []
    try:
        url = _SEARCH_URL.format(q=quote_plus(query))
        await page.goto(url, timeout=30_000, wait_until="domcontentloaded")
        await page.wait_for_timeout(2_500)

        # If redirected to login wall, cookie has expired
        if "linkedin.com/login" in page.url or "authwall" in page.url:
            return []

        # LinkedIn people search results
        results = await page.locator("li.reusable-search__result-container").all()
        if not results:
            # Fallback selector for newer LinkedIn UI
            results = await page.locator("[data-view-name='search-entity-result-universal-template']").all()

        for result in results[:8]:
            try:
                contact = await _parse_result(result, company_name)
                if contact:
                    contacts.append(contact)
            except Exception:
                continue

    finally:
        await page.close()
    return contacts


async def _parse_result(result, company_name: str) -> dict | None:
    # Name
    name = ""
    for sel in [
        ".entity-result__title-text a span[aria-hidden='true']",
        ".app-aware-link span[aria-hidden='true']",
        "span.entity-result__title-line span[aria-hidden]",
    ]:
        try:
            el = result.locator(sel).first
            if await el.count() > 0:
                name = (await el.inner_text()).strip()
                if name and name != "LinkedIn Member":
                    break
        except Exception:
            pass

    if not name or name == "LinkedIn Member":
        return None

    # Title / headline
    title = ""
    for sel in [
        ".entity-result__primary-subtitle",
        ".entity-result__summary",
        "[data-anonymize='job-title']",
    ]:
        try:
            el = result.locator(sel).first
            if await el.count() > 0:
                title = (await el.inner_text()).strip()
                if title:
                    break
        except Exception:
            pass

    # Profile URL
    url = ""
    for sel in [
        "a.app-aware-link[href*='/in/']",
        ".entity-result__title-text a[href*='/in/']",
    ]:
        try:
            el = result.locator(sel).first
            if await el.count() > 0:
                href = await el.get_attribute("href") or ""
                m = re.search(r"linkedin\.com/in/([\w\-%]+)", href)
                if m:
                    url = f"https://www.linkedin.com/in/{m.group(1)}"
                    break
        except Exception:
            pass

    if not url:
        return None

    return {"name": name, "title": title or "—", "url": url}
