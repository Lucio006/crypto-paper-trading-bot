"""
Level 5: LinkedIn personal contact finder via Bing.
Bing (owned by Microsoft/LinkedIn) has the best LinkedIn index and is
more bot-tolerant than Google. Extracts name, title, LinkedIn URL from
search snippets — no login, no invented data.
"""
from __future__ import annotations
import asyncio
import re
from urllib.parse import quote_plus, unquote
from playwright.async_api import BrowserContext
from models import Company

_BING = "https://www.bing.com/search?q={q}&count=10&setlang=en"

_ROLE_QUERIES = [
    "events sponsorship partnerships",
    "marketing communications",
    "affiliate business development",
    "CEO CCO director",
]

_LI_SLUG_RE = re.compile(r"linkedin\.com/in/([\w\-%]+)", re.IGNORECASE)

_NAME_TITLE_RE = re.compile(
    r"^(.+?)\s*[-–]\s*(.+?)(?:\s+(?:at|en|@)\s+.+?)?(?:\s*[|·]\s*LinkedIn.*)?$",
    re.IGNORECASE | re.UNICODE,
)


async def find_personal_contacts(company: Company, context: BrowserContext) -> Company:
    """Search Bing for LinkedIn profiles of people at this company. Never raises."""
    if not company.name_original:
        return company

    found: dict[str, dict] = {}

    for role_terms in _ROLE_QUERIES:
        if len(found) >= 5:
            break
        query = f'site:linkedin.com/in "{company.name_original}" {role_terms}'
        try:
            contacts = await _bing_search(context, query, company.name_original)
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


async def _bing_search(context: BrowserContext, query: str, company_name: str) -> list[dict]:
    page = await context.new_page()
    contacts: list[dict] = []
    try:
        url = _BING.format(q=quote_plus(query))
        await page.goto(url, timeout=30_000, wait_until="domcontentloaded")
        await page.wait_for_timeout(1_500)

        # Bing result structure: li.b_algo contains h2 > a (title+link) and p (snippet)
        results = await page.locator("li.b_algo").all()

        for result in results[:15]:
            try:
                # Get title and href from the main link
                link = result.locator("h2 a").first
                if await link.count() == 0:
                    continue

                title_text = await link.inner_text()
                href = await link.get_attribute("href") or ""

                # Bing uses direct hrefs (not redirects like Google)
                if "linkedin.com/in/" not in href.lower():
                    # Also check the displayed URL (cite)
                    cite = result.locator("cite")
                    if await cite.count() > 0:
                        href = await cite.first.inner_text()

                m = _LI_SLUG_RE.search(unquote(href))
                if not m:
                    continue

                linkedin_url = f"https://www.linkedin.com/in/{m.group(1)}"
                contact = _parse_title(title_text, linkedin_url, company_name)
                if contact:
                    contacts.append(contact)

            except Exception:
                continue

    finally:
        await page.close()
    return contacts


def _parse_title(title_text: str, linkedin_url: str, company_name: str) -> dict | None:
    if not title_text:
        return {"name": "—", "title": "—", "url": linkedin_url}

    clean = re.sub(r"\s*[|·]\s*LinkedIn.*$", "", title_text, flags=re.IGNORECASE).strip()
    m = _NAME_TITLE_RE.match(clean)
    if not m:
        return {"name": clean[:60] or "—", "title": "—", "url": linkedin_url}

    name = m.group(1).strip()
    title = m.group(2).strip()

    if len(name.split()) < 2 or len(name) > 60:
        return {"name": clean[:60], "title": title or "—", "url": linkedin_url}

    return {"name": name, "title": title, "url": linkedin_url}
