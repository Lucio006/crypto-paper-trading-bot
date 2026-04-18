"""
Diagnostic: inspect the DOM structure of an exhibitor listing or profile page.
Helps identify the correct CSS selectors for level1_listing.py and level2_profile.py.

Usage: python diagnose_page.py <URL>
"""
import sys
import asyncio
from playwright.async_api import async_playwright

SELECTORS_TO_TEST = [
    ".exhibitor-card", ".exhibitor-item", ".exhibitor-tile",
    ".exhibitor-list-item", ".exhibitor-grid-item",
    "[class='exhibitor']",
    ".js-exhibitor", ".exhibitor-listing__item",
    "[class*='ExhibitorCard']", "[class*='exhibitor-card']",
    "[class*='CompanyCard']", "[class*='company-card']",
    ".m-exhibitors-list__items__item",
    "[data-exhibitor-id]", "[data-company-id]",
    ".card--exhibitor", ".card--company",
    "ul.exhibitors > li", "ul.companies > li",
    ".node--type-expositor", ".views-row",
    "[data-testid*='exhibitor']", "[data-testid*='company']",
    "article", "li:has(h2)", "li:has(h3)",
]

COOKIE_BUTTONS = [
    "#onetrust-accept-btn-handler",
    ".ot-btn-accept-all",
    "button#accept-all",
    "button[id*='accept']",
]
COOKIE_TEXTS = ["Aceptar todo", "Aceptar todas", "Accept All", "Accept all", "Aceptar"]


async def accept_cookies(page):
    for sel in COOKIE_BUTTONS:
        try:
            btn = page.locator(sel).first
            if await btn.count() > 0 and await btn.is_visible():
                await btn.click()
                await page.wait_for_timeout(800)
                return
        except Exception:
            continue
    for text in COOKIE_TEXTS:
        try:
            btn = page.get_by_role("button", name=text)
            if await btn.count() > 0 and await btn.is_visible():
                await btn.click()
                await page.wait_for_timeout(800)
                return
        except Exception:
            continue


async def diagnose(url: str):
    print(f"\nDiagnosticando: {url}\n")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        )
        page = await context.new_page()

        print("Cargando página…")
        await page.goto(url, timeout=60_000, wait_until="networkidle")
        await page.wait_for_timeout(2000)
        print("Aceptando cookies si las hay…")
        await accept_cookies(page)
        await page.wait_for_timeout(1500)
        print("Listo.\n")

        print(f"Título   : {await page.title()}")
        print(f"URL final: {page.url}\n")

        # ── Selector counts ───────────────────────────────────────────────────
        print("── Selectores con ≥3 coincidencias ─────────────────────────────")
        hits = []
        for sel in SELECTORS_TO_TEST:
            try:
                count = await page.locator(sel).count()
                if count >= 3:
                    hits.append((count, sel))
            except Exception:
                continue
        hits.sort(reverse=True)
        if hits:
            for count, sel in hits:
                print(f"  {count:4d}  {sel}")
        else:
            print("  Ningún selector conocido devolvió ≥3 elementos.")

        # ── Sample HTML of top selector ───────────────────────────────────────
        if hits:
            best_sel = hits[0][1]
            print(f"\n── HTML del primer elemento con «{best_sel}» ───────────────────")
            try:
                html = await page.locator(best_sel).first.inner_html()
                print(html[:800])
            except Exception as e:
                print(f"  Error: {e}")

        # ── All external links ────────────────────────────────────────────────
        print("\n── Links externos encontrados (primeros 20) ─────────────────────")
        try:
            links = await page.locator("a[href^='http']").all()
            shown = 0
            for link in links:
                href = await link.get_attribute("href") or ""
                text = (await link.inner_text()).strip().replace("\n", " ")[:40]
                if href and "igblive" not in href and "igb-live" not in href:
                    print(f"  {text:<40}  →  {href}")
                    shown += 1
                    if shown >= 20:
                        break
        except Exception as e:
            print(f"  Error: {e}")

        # ── Most frequent CSS classes ─────────────────────────────────────────
        print("\n── Clases CSS más frecuentes ────────────────────────────────────")
        classes: dict[str, int] = {}
        try:
            for el in await page.locator("[class]").all()[:500]:
                try:
                    cls = await el.get_attribute("class") or ""
                    for c in cls.split():
                        classes[c] = classes.get(c, 0) + 1
                except Exception:
                    continue
        except Exception:
            pass
        for cls, count in sorted(classes.items(), key=lambda x: -x[1])[:25]:
            print(f"  {count:4d}  .{cls}")

        await browser.close()

    print("\nDiagnóstico completado.\n")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    asyncio.run(diagnose(sys.argv[1]))
