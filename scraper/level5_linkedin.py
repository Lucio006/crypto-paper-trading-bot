"""
Level 5: LinkedIn personal contact finder.
Uses Google (better LinkedIn indexing) to find individual LinkedIn profiles.
Parses result titles and decoded URLs from the HTML source.
No LinkedIn login required. No invented data.
"""
from __future__ import annotations
import asyncio
import re
from urllib.parse import quote_plus, unquote
from playwright.async_api import BrowserContext
from models import Company

_GOOGLE = "https://www.google.com/search?q={q}&num=10&hl=en&gl=es"

_ROLE_QUERIES = [
    "events sponsorship partnerships",
    "marketing communications",
    "affiliate business development",
    "CEO CCO director",
]

_LI_SLUG_RE = re.compile(r"linkedin\.com/in/([\w\-%]+)", re.IGNORECASE)

# "Firstname Lastname - Job Title at Company | LinkedIn"
_NAME_TITLE_RE = re.compile(
    r"^(.+?)\s*[-–]\s*(.+?)(?:\s+(?:at|en|@)\s+.+?)?(?:\s*[|·]\s*LinkedIn.*)?$",
    re.IGNORECASE | re.UNICODE,
)


async def find_personal_contacts(company: Company, context: BrowserContext) -> Company:
    """Search Google for LinkedIn profiles of people at this company. Never raises."""
    if not company.name_original:
        return company

    found: dict[str, dict] = {}

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


async def _search(context: BrowserContext, query: str, company_name: str) -> list[dict]:
    page = await context.new_page()
    contacts: list[dict] = []
    try:
        await page.goto(_GOOGLE.format(q=quote_plus(query)), timeout=30_000,
                        wait_until="domcontentloaded")
        await page.wait_for_timeout(2_000)

        # Accept Google cookie consent if shown
        for sel in ["#L2AGLb", "button:has-text('Accept all')",
                    "button:has-text('Aceptar todo')"]:
            try:
                el = page.locator(sel)
                if await el.count() > 0:
                    await el.first.click()
                    await page.wait_for_timeout(1_000)
                    break
            except Exception:
                pass

        # Google wraps result URLs as /url?q=https%3A%2F%2Flinkedin.com%2Fin%2F...
        # Decode the full HTML to find real LinkedIn URLs
        html = await page.content()
        decoded_html = unquote(html)

        # Find all LinkedIn /in/ slugs from decoded HTML
        slugs_found = _LI_SLUG_RE.findall(decoded_html)

        # Find result titles: h3 elements containing "LinkedIn"
        h3_elements = await page.locator("h3").all()
        titles: list[str] = []
        for h3 in h3_elements[:20]:
            try:
                text = await h3.inner_text()
                if "linkedin" in text.lower() or "–" in text or " - " in text:
                    titles.append(text)
            except Exception:
                pass

        # Pair each unique slug with the corresponding title
        seen: set[str] = set()
        for i, slug in enumerate(slugs_found):
            clean_slug = slug.strip("/").lower()
            if clean_slug in seen or len(clean_slug) < 3:
                continue
            seen.add(clean_slug)

            title_text = titles[i] if i < len(titles) else ""
            linkedin_url = f"https://www.linkedin.com/in/{slug}"
            contact = _parse_title(title_text, linkedin_url, company_name)
            if contact:
                contacts.append(contact)

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
