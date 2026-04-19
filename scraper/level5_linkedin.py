from __future__ import annotations
import asyncio
import re
from pathlib import Path
from urllib.parse import quote_plus
from playwright.async_api import async_playwright, BrowserContext
from models import Company

_STATE_FILE = Path(__file__).parent.parent / "credentials" / "linkedin_state.json"
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
_SEARCH_PEOPLE_URL = (
    "https://www.linkedin.com/search/results/people/"
    "?keywords={q}&origin=GLOBAL_SEARCH_HEADER"
)
_SEARCH_COMPANY_URL = (
    "https://www.linkedin.com/search/results/companies/"
    "?keywords={q}&origin=GLOBAL_SEARCH_HEADER"
)

_CEO_KW    = ["ceo", "chief executive", "founder", "co-founder", "managing director",
              "director general", "president", "chairman", "general manager"]
_CCO_KW    = ["cco", "chief commercial", "chief revenue", "chief business",
              "vp commercial", "commercial director", "chief operating", "coo"]
_EVENTS_KW = ["event", "sponsor", "partnership", "affiliate", "sponsorship", "patrocin"]
_MKT_KW    = ["marketing", "brand", "communications", "content", "digital",
              "crm", "growth", "acquisition", "media"]

_ROLE_QUERIES = [
    "CEO director",
    "events sponsorship",
    "marketing communications",
    "affiliate partnerships",
]

_EMAIL_RE = re.compile(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}')
_NOISE_DOMAINS = {
    "example.com", "test.com", "sentry.io", "linkedin.com",
    "google.com", "gmail.com", "hotmail.com", "yahoo.com",
    "wixpress.com", "amazonaws.com", "cloudflare.com",
}


def _classify(title: str) -> str:
    t = title.lower()
    if any(k in t for k in _CEO_KW):
        return "CEO/Director"
    if any(k in t for k in _CCO_KW):
        return "CCO"
    if any(k in t for k in _EVENTS_KW):
        return "Eventos/Patrocinios"
    if any(k in t for k in _MKT_KW):
        return "Marketing"
    return "Otro"


async def find_personal_contacts(company: Company, context: BrowserContext) -> Company:
    if not _STATE_FILE.exists() or not company.name_original:
        return company

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False, args=[])
        li_ctx = await browser.new_context(
            user_agent=_UA,
            viewport={"width": 1280, "height": 900},
            storage_state=str(_STATE_FILE),
        )
        await li_ctx.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        try:
            # Step 1: Company page → fill corporate_website if missing
            if not company.corporate_website:
                website = await _scrape_company_website(li_ctx, company.name_original)
                if website:
                    company.corporate_website = website

            # Step 2: People search classified by role
            found: dict[str, dict] = {}
            for suffix in _ROLE_QUERIES:
                if len(found) >= 6:
                    break
                try:
                    contacts = await _search_people(
                        li_ctx, f"{company.name_original} {suffix}"
                    )
                    for c in contacts:
                        key = c["url"].split("/in/")[-1].strip("/").lower()
                        if key and key not in found:
                            found[key] = c
                    await asyncio.sleep(2)
                except Exception:
                    continue

        finally:
            await browser.close()

    if found:
        leftover: list[str] = []
        domain = company.domain or ""
        for c in list(found.values())[:8]:
            label = _classify(c["title"])
            # Try to find a real email for this person
            email = await _find_person_email(li_ctx, c["name"], company.name_original, domain)
            contact_str = email if email else f"[LinkedIn] {c['name']} — {c['title']} — {c['url']}"

            if label == "CEO/Director" and not company.contact.email_ceo:
                company.contact.email_ceo = contact_str
                company.contact.reason_no_ceo = None
            elif label == "CCO" and not company.contact.email_cco:
                company.contact.email_cco = contact_str
                company.contact.reason_no_cco = None
            elif label == "Marketing" and not company.contact.email_marketing:
                company.contact.email_marketing = contact_str
                company.contact.reason_no_marketing = None
            elif label == "Eventos/Patrocinios" and not company.contact.email_events:
                company.contact.email_events = contact_str
                company.contact.reason_no_events = None
            else:
                leftover.append(f"[{label}] {c['name']} — {c['title']} — {contact_str}")

        if leftover:
            company.personal_contacts = "\n".join(leftover)

    return company


async def _find_person_email(ctx, name: str, company_name: str, domain: str) -> str:
    """Search DuckDuckGo for a person's work email. Returns email or empty string."""
    page = await ctx.new_page()
    try:
        queries = [f'"{name}" "{company_name}" email contact']
        if domain:
            queries.insert(0, f'"{name}" site:{domain}')

        found_emails: list[str] = []
        for query in queries:
            url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
            try:
                await page.goto(url, timeout=20_000, wait_until="domcontentloaded")
                await page.wait_for_timeout(1_500)
                content = await page.content()
                for m in _EMAIL_RE.finditer(content):
                    email = m.group(0).lower()
                    d = email.split("@")[1]
                    if d not in _NOISE_DOMAINS:
                        found_emails.append((email, d))
            except Exception:
                continue

        if not found_emails:
            return ""
        # Prefer emails from the company's own domain
        if domain:
            for email, d in found_emails:
                if domain in d:
                    return email
        return found_emails[0][0]
    finally:
        await page.close()


async def _scrape_company_website(ctx, company_name: str) -> str:
    page = await ctx.new_page()
    try:
        url = _SEARCH_COMPANY_URL.format(q=quote_plus(company_name))
        await page.goto(url, timeout=30_000, wait_until="domcontentloaded")
        await page.wait_for_timeout(2_500)

        if "linkedin.com/login" in page.url or "authwall" in page.url:
            return ""

        first = page.locator("a[href*='/company/']").first
        if await first.count() == 0:
            return ""
        href = await first.get_attribute("href") or ""
        m = re.search(r"linkedin\.com/company/([\w\-%]+)", href)
        if not m:
            return ""

        about_url = f"https://www.linkedin.com/company/{m.group(1)}/about/"
        await page.goto(about_url, timeout=30_000, wait_until="domcontentloaded")
        await page.wait_for_timeout(2_500)

        for sel in [
            "a[data-tracking-control-name='about_website']",
            "dt:has-text('Sitio web') + dd a",
            "dt:has-text('Website') + dd a",
            ".org-about-company-module__website a",
            "a[href^='http']:not([href*='linkedin'])",
        ]:
            try:
                el = page.locator(sel).first
                if await el.count() > 0:
                    link = await el.get_attribute("href") or ""
                    if link and "linkedin" not in link:
                        return link
            except Exception:
                continue
        return ""
    finally:
        await page.close()


async def _search_people(ctx, query: str) -> list[dict]:
    page = await ctx.new_page()
    contacts: list[dict] = []
    try:
        url = _SEARCH_PEOPLE_URL.format(q=quote_plus(query))
        await page.goto(url, timeout=30_000, wait_until="domcontentloaded")
        await page.wait_for_timeout(3_000)

        if "linkedin.com/login" in page.url or "authwall" in page.url:
            return []

        link_els = await page.locator("a[href*='/in/']").all()
        seen: set[str] = set()
        for el in link_els:
            try:
                href = await el.get_attribute("href") or ""
                m = re.search(r"linkedin\.com/in/([\w\-%]+)", href)
                if not m:
                    continue
                slug = m.group(1).lower()
                if slug in seen or slug in ("", "me"):
                    continue
                seen.add(slug)
                raw = (await el.inner_text()).strip()
                name, title = _parse_link_text(raw)
                if not name:
                    continue
                contacts.append({
                    "name": name,
                    "title": title,
                    "url": f"https://www.linkedin.com/in/{m.group(1)}",
                })
                if len(contacts) >= 8:
                    break
            except Exception:
                continue
    finally:
        await page.close()
    return contacts


def _parse_link_text(raw: str) -> tuple[str, str]:
    cleaned = re.sub(r"•\s*\d+(st|nd|rd|er)\+?", "", raw)
    parts = [p.strip() for p in re.split(r"[\n\r]+", cleaned) if p.strip()]
    name = title = ""
    for part in parts:
        if not name:
            if part and part.lower() != "linkedin member":
                name = part
        elif not title:
            title = part
            break
    return name, title or "—"
