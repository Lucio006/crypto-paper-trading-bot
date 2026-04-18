"""
Diagnostic: inspect the DOM structure of an exhibitor listing page.
Helps identify the correct CSS selectors for level1_listing.py.

Usage: python diagnose_page.py <URL>
"""
import sys
import asyncio
from playwright.async_api import async_playwright

SELECTORS_TO_TEST = [
    # Specific to common event platforms
    ".exhibitor-card", ".exhibitor-item", ".exhibitor-tile",
    ".exhibitor-list-item", ".exhibitor-grid-item",
    "[class='exhibitor']",
    # Common patterns
    ".company-card", ".company-item", ".company-tile",
    "[data-exhibitor-id]", "[data-company-id]",
    # Cards and grids
    ".card--exhibitor", ".card--company",
    # List items with links
    "ul.exhibitors > li", "ul.companies > li",
    ".grid > .item", ".list > .item",
    # IFEMA / Feria Barcelona / common EU platforms
    ".node--type-expositor", ".views-row",
    # iGB / Reed / Informa platforms
    ".js-exhibitor", ".exhibitor-listing__item",
    "[class*='ExhibitorCard']", "[class*='exhibitor-card']",
    "[class*='CompanyCard']", "[class*='company-card']",
    # React/Vue component names often appear in data attributes
    "[data-testid*='exhibitor']", "[data-testid*='company']",
    # Broad fallbacks
    "article", "li:has(h2)", "li:has(h3)",
]

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

        print("Cargando página (esperando JS)…")
        await page.goto(url, timeout=60_000, wait_until="networkidle")
        await page.wait_for_timeout(3000)
        print("Página cargada.\n")

        # ── Title and URL after redirects ─────────────────────────────────────
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
                first = page.locator(best_sel).first
                html = await first.inner_html()
                print(html[:800])
            except Exception as e:
                print(f"  Error: {e}")

        # ── Classes that appear on many elements (helps spot patterns) ────────
        print("\n── Clases CSS más frecuentes en la página ───────────────────────")
        classes: dict[str, int] = {}
        try:
            all_els = await page.locator("[class]").all()
            for el in all_els[:500]:
                try:
                    cls = await el.get_attribute("class") or ""
                    for c in cls.split():
                        classes[c] = classes.get(c, 0) + 1
                except Exception:
                    continue
        except Exception:
            pass
        top = sorted(classes.items(), key=lambda x: -x[1])[:30]
        for cls, count in top:
            print(f"  {count:4d}  .{cls}")

        await browser.close()

    print("\nDiagnóstico completado.\n")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    asyncio.run(diagnose(sys.argv[1]))
