"""
Level 5: LinkedIn personal contact finder.
Uses Google (better LinkedIn indexing than DuckDuckGo) to find individual
LinkedIn profiles linked to the company.
Extracts name, job title, and LinkedIn URL from search result snippets —
no LinkedIn login required, no invented data.
"""
from __future__ import annotations
import asyncio
import re
from urllib.parse import quote_plus
from playwright.async_api import BrowserContext
from models import Company

_GOOGLE = "https://www.google.com/search?q={q}&num=10&hl=en"

# Role combinations in priority order for iGaming / affiliate prospecting
_ROLE_QUERIES = [
    "events sponsorship partnerships",
    "marketing communications",
    "affiliate business development",
    "CEO CCO director",
]

_LI_URL_RE = re.compile(r"linkedin\.com/in/([\w%\-]+)", re.IGNORECASE)

# Google result title: "Name - Title at Company | LinkedIn"
_TITLE_RE = re.compile(
    r"^(.+?)\s*[-–]\s*(.+?)\s*(?:\bat\b|\ben\b)?.*?(?:[|\-]\s*LinkedIn|$)",
    re.IGNORECASE | re.UNICODE,
)


async def find_personal_contacts(company: Company, context: BrowserContext) -> Company:
    """
    Search Google for individual LinkedIn profiles related to the company.
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
            contacts = await _google_search(context, query, company.name_original)
            for c in contacts:
                slug = c["url"].split("/in/")[-1].strip("/").lower()
                if slug and slug not in found:
                    found[slug] = c
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


async def _google_search(context: BrowserContext, query: str, company_name: str) -> list[dict]:
    """Search Google and extract LinkedIn profile cards from results."""
    url = _GOOGLE.format(q=quote_plus(query))
    page = await context.new_page()
    contacts: list[dict] = []
    try:
        await page.goto(url, timeout=30_000, wait_until="domcontentloaded")
        await page.wait_for_timeout(1_500)

        # Handle cookie consent if shown
        for btn_text in ["Accept all", "Aceptar todo", "I agree"]:
            btn = page.locator(f"button:has-text('{btn_text}')")
            if await btn.count() > 0:
                await btn.first.click()
                await page.wait_for_timeout(800)
                break

        # Google result blocks: each is a <div class="g"> or similar
        # Extract title + URL from each result
        result_links = await page.locator("a[href*='linkedin.com/in/']").all()
        seen_urls: set[str] = set()

        for link in result_links[:20]:
            try:
                href = await link.get_attribute("href") or ""
                m_url = _LI_URL_RE.search(href)
                if not m_url:
                    continue
                slug = m_url.group(1).lower()
                if slug in seen_urls:
                    continue
                seen_urls.add(slug)
                linkedin_url = f"https://www.linkedin.com/in/{m_url.group(1)}"

                # Get the visible title text from the parent result block
                # Try h3 inside the same result, then the link text itself
                title_text = ""
                try:
                    h3 = link.locator("xpath=ancestor::div[contains(@class,'g')]//h3")
                    if await h3.count() > 0:
                        title_text = await h3.first.inner_text()
                except Exception:
                    pass
                if not title_text:
                    title_text = await link.inner_text()

                contact = _parse_title(title_text, linkedin_url, company_name)
                if contact:
                    contacts.append(contact)
            except Exception:
                continue

    finally:
        await page.close()
    return contacts


def _parse_title(title_text: str, linkedin_url: str, company_name: str) -> dict | None:
    """Parse 'Name - Job Title at Company | LinkedIn' into a contact dict."""
    if not title_text:
        return None

    # Strip "| LinkedIn" and everything after
    clean = re.sub(r"\s*[|\-]\s*LinkedIn.*$", "", title_text, flags=re.IGNORECASE).strip()

    m = _TITLE_RE.match(clean)
    if not m:
        # Fallback: if we can't parse a name-title, still return the URL with raw title
        words = clean.split()
        if len(words) >= 2:
            return {"name": clean[:60], "title": "—", "url": linkedin_url}
        return None

    name = m.group(1).strip()
    title = m.group(2).strip()

    # Sanity checks
    if len(name.split()) < 2 or len(name) > 60:
        return None
    if len(title) < 3:
        return None

    return {"name": name, "title": title, "url": linkedin_url}
