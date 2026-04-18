"""
Level 5: LinkedIn personal contact finder.
Searches DuckDuckGo for individual LinkedIn profiles linked to the company.
Extracts name, job title, and LinkedIn URL from search result snippets —
no LinkedIn login required, no invented data.
"""
from __future__ import annotations
import asyncio
import re
from urllib.parse import quote_plus
from playwright.async_api import BrowserContext
from models import Company

_DDG_HTML = "https://html.duckduckgo.com/html/?q={q}&kl=es-es"

# Role combinations to search for — ordered by priority for prospecting
_ROLE_QUERIES = [
    "events sponsorship partnerships",
    "marketing communications media",
    "business development sales affiliate",
    "CEO CCO director managing",
]

_LI_URL_RE = re.compile(r"linkedin\.com/in/([\w%\-]+)", re.IGNORECASE)

# Matches "Firstname Lastname - Job Title at Company | LinkedIn"
# or "Firstname Lastname - Job Title - LinkedIn"
_TITLE_RE = re.compile(
    r"^(.+?)\s*[-–]\s*(.+?)\s*(?:[-–|]|$)",
    re.UNICODE,
)


async def find_personal_contacts(company: Company, context: BrowserContext) -> Company:
    """
    Search for individual LinkedIn profiles related to the company.
    Mutates company.personal_contacts. Never raises.
    """
    if not company.name_original:
        return company

    found: dict[str, dict] = {}  # slug → {name, title, url}

    for role_terms in _ROLE_QUERIES:
        if len(found) >= 5:
            break
        query = f'site:linkedin.com/in "{company.name_original}" {role_terms}'
        try:
            contacts = await _search(context, query, company.name_original)
            for c in contacts:
                slug = c["url"].split("/in/")[-1].strip("/").lower()
                if slug and slug not in found:
                    found[slug] = c
            await asyncio.sleep(2)
        except Exception:
            continue

    if found:
        lines = [
            f"{c['name']} — {c['title']} — {c['url']}"
            for c in list(found.values())[:5]
        ]
        company.personal_contacts = "\n".join(lines)

    return company


async def _search(context: BrowserContext, query: str, company_name: str) -> list[dict]:
    """Fetch DuckDuckGo results and extract LinkedIn person cards."""
    url = _DDG_HTML.format(q=quote_plus(query))
    page = await context.new_page()
    contacts: list[dict] = []
    try:
        await page.goto(url, timeout=30_000, wait_until="domcontentloaded")
        await page.wait_for_timeout(1_000)

        results = await page.locator(".result").all()
        for result in results[:15]:
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
    """Extract name, title, LinkedIn URL from a single DuckDuckGo result block."""
    try:
        url_text = await result.locator(".result__url").inner_text()
    except Exception:
        url_text = ""

    # Only process LinkedIn personal profile URLs
    if "linkedin.com/in/" not in url_text.lower():
        return None

    url_match = _LI_URL_RE.search(url_text)
    if not url_match:
        return None
    linkedin_url = f"https://www.linkedin.com/in/{url_match.group(1)}"

    try:
        title_text = await result.locator(".result__title").inner_text()
    except Exception:
        return None

    # Clean "| LinkedIn" suffix and parse "Name - Title"
    title_text = re.sub(r"\s*[|\-]\s*LinkedIn.*$", "", title_text, flags=re.IGNORECASE).strip()
    m = _TITLE_RE.match(title_text)
    if not m:
        return None

    name = m.group(1).strip()
    title = m.group(2).strip()

    # Basic sanity: name should look like a real name (2+ words, no weird chars)
    if len(name.split()) < 2 or len(name) > 50:
        return None
    # Title should not be the company name repeated
    if company_name.lower() in title.lower() and len(title) < 20:
        return None

    return {"name": name, "title": title, "url": linkedin_url}
