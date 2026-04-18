"""
Test the 3-level scraper on a real exhibitor listing URL.
Requires Playwright: pip install playwright && playwright install chromium

Usage:
    python test_scraper.py <URL> [max_companies]

Example:
    python test_scraper.py "https://www.ifema.es/expositores" 5
"""
import sys
import asyncio
from playwright.async_api import async_playwright
from scraper.validator import is_valid_listing
from scraper.level1_listing import scrape_listing
from scraper.level2_profile import scrape_profile
from scraper.level3_corporate import scrape_corporate
from scraper.utils import extract_domain


async def test(url: str, max_companies: int = 5):
    print(f"\nURL      : {url}")
    print(f"Límite   : {max_companies} empresas\n")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
        )

        # ── Validation ────────────────────────────────────────────────────────
        print("── Paso 1: Validar URL ──────────────────────────────")
        page = await context.new_page()
        await page.goto(url, timeout=60_000, wait_until="domcontentloaded")
        await page.wait_for_timeout(2000)
        valid, reason = await is_valid_listing(page)
        print(f"  {'✓' if valid else '✗'} {reason}")
        if not valid:
            await browser.close()
            return
        event_domain = extract_domain(url) or ""

        # ── Level 1 ───────────────────────────────────────────────────────────
        print(f"\n── Paso 2: Nivel 1 — listado de expositores ─────────")
        companies = await scrape_listing(page, url, max_companies)
        await page.close()
        print(f"  ✓ {len(companies)} empresa(s) extraídas")
        for c in companies:
            print(f"    · {c.name_original:<35} stand={c.stand or '—':<8} perfil={'sí' if c.exhibitor_profile_url else 'no'}")

        if not companies:
            print("  No se encontraron empresas. Prueba con otra URL.")
            await browser.close()
            return

        # ── Level 2 ───────────────────────────────────────────────────────────
        print(f"\n── Paso 3: Nivel 2 — fichas de expositor ────────────")
        for company in companies:
            company = await scrape_profile(company, context, event_domain)
            web = company.website_from_event or "—"
            desc = (company.description or "—")[:60].replace("\n", " ")
            print(f"  · {company.name_original:<35} web={web}")
            print(f"    descripción: {desc}")

        # ── Level 3 ───────────────────────────────────────────────────────────
        print(f"\n── Paso 4: Nivel 3 — webs corporativas ──────────────")
        for company in companies:
            if not (company.website_from_event or company.corporate_website):
                print(f"  · {company.name_original:<35} sin web corporativa")
                continue
            company = await scrape_corporate(company, context)
            c = company.contact
            print(f"  · {company.name_original}")
            print(f"    email general  : {c.email_general or '—'}")
            print(f"    email marketing: {c.email_marketing or '—'}")
            print(f"    email eventos  : {c.email_events or '—'}")
            print(f"    teléfono       : {c.phone or '—'}")
            print(f"    telegram       : {c.telegram or '—'}")
            print(f"    confianza      : {c.confidence_level or '—'}")

        await browser.close()

    print("\n✓ Test de scraper completado\n")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    url = sys.argv[1]
    max_c = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    asyncio.run(test(url, max_c))
