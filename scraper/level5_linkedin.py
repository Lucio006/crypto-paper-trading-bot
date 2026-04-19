"""
Level 5: LinkedIn personal contact finder.
Uses a saved Playwright storage_state (full session) to search LinkedIn directly.
Falls back gracefully if credentials missing or LinkedIn blocks.
"""
from __future__ import annotations
import asyncio
import re
from pathlib import Path
from urllib.parse import quote_plus
from playwright.async_api import BrowserContext
from models import Company

_STATE_FILE = Path(__file__).parent.parent / "credentials" / "linkedin_state.json"

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
    Requires credentials/linkedin_state.json — skips silently if missing.
    """
    if not _STATE_FILE.exists() or not company.name_original:
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
        await page.wait_for_timeout(3_000)

        # Bail if redirected to login wall
        if "linkedin.com/login" in page.url or "authwall" in page.url:
            return []

        # Collect all /in/ profile links on the page
        link_els = await page.locator("a[href*='/in/']").all()

        seen_slugs: set[str] = set()
        for el in link_els:
            try:
                href = await el.get_attribute("href") or ""
                m = re.search(r"linkedin\.com/in/([\w\-%]+)", href)
                if not m:
                    continue
                slug = m.group(1).lower()
                if slug in seen_slugs or slug in ("", "me"):
                    continue
                seen_slugs.add(slug)

                profile_url = f"https://www.linkedin.com/in/{m.group(1)}"

                # The link text contains "Name\n • Degree\n\nJob Title"
                raw = (await el.inner_text()).strip()
                name, title = _parse_link_text(raw, company_name)
                if not name:
                    continue

                contacts.append({"name": name, "title": title, "url": profile_url})
                if len(contacts) >= 8:
                    break
            except Exception:
                continue

    finally:
        await page.close()
    return contacts


def _parse_link_text(raw: str, company_name: str) -> tuple[str, str]:
    """Extract name and title from a LinkedIn search result link's text content."""
    # Strip degree indicators (• 1st, • 2nd, • 3er+, etc.)
    cleaned = re.sub(r"•\s*\d+(st|nd|rd|er)\+?", "", raw)
    # Collapse whitespace/newlines
    parts = [p.strip() for p in re.split(r"[\n\r]+", cleaned) if p.strip()]

    name = ""
    title = ""

    for part in parts:
        if not name:
            # First non-empty part is the name — skip "LinkedIn Member"
            if part and part.lower() != "linkedin member":
                name = part
        elif not title:
            # Second part is the headline/title
            title = part
            break

    return name, title or "—"
