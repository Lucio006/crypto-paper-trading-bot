"""
Script de diagnóstico para LinkedIn. Ejecutar en Mac:
  python debug_linkedin.py
"""
import asyncio
import re
from pathlib import Path
from urllib.parse import quote_plus
from playwright.async_api import async_playwright

_STATE_FILE = Path(__file__).parent / "credentials" / "linkedin_state.json"
_COMPANY = "iGB Live"  # Cambia por cualquier empresa del evento

_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


async def main():
    print(f"[1] Archivo de sesión: {_STATE_FILE}")
    print(f"    Existe: {_STATE_FILE.exists()}")
    if not _STATE_FILE.exists():
        print("ERROR: No se encontró linkedin_state.json — vuelve a ejecutar setup_linkedin.py")
        return

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False)  # headless=False para ver qué pasa
        context = await browser.new_context(
            user_agent=_UA,
            viewport={"width": 1280, "height": 900},
            storage_state=str(_STATE_FILE),
        )
        page = await context.new_page()

        query = f"{_COMPANY} events sponsorship"
        url = (
            "https://www.linkedin.com/search/results/people/"
            f"?keywords={quote_plus(query)}&origin=GLOBAL_SEARCH_HEADER"
        )
        print(f"\n[2] Abriendo: {url}")
        await page.goto(url, timeout=30_000, wait_until="domcontentloaded")
        await page.wait_for_timeout(4_000)

        final_url = page.url
        print(f"[3] URL final: {final_url}")

        if "login" in final_url or "authwall" in final_url:
            print("ERROR: Redirigido al login — la sesión ha expirado. Vuelve a ejecutar setup_linkedin.py")
            await browser.close()
            return

        # Contar links /in/
        link_els = await page.locator("a[href*='/in/']").all()
        print(f"\n[4] Links /in/ encontrados: {len(link_els)}")

        for i, el in enumerate(link_els[:10]):
            try:
                href = await el.get_attribute("href") or ""
                raw = (await el.inner_text()).strip()
                m = re.search(r"linkedin\.com/in/([\w\-%]+)", href)
                slug = m.group(1) if m else "?"
                print(f"    [{i+1}] slug={slug} | texto={repr(raw[:80])}")
            except Exception as e:
                print(f"    [{i+1}] ERROR: {e}")

        # Guardar HTML para inspección
        html = await page.content()
        out = Path("/tmp/linkedin_debug.html")
        out.write_text(html, encoding="utf-8")
        print(f"\n[5] HTML guardado en {out} ({len(html)} bytes)")

        input("\nPulsa Enter para cerrar el navegador...")
        await browser.close()


asyncio.run(main())
