"""
Main pipeline: orchestrates validation → L1 → L2 → L3 → classify → dedup → Sheets.
"""
from __future__ import annotations
import asyncio
import re
from datetime import date
from playwright.async_api import async_playwright, BrowserContext

from models import Company, EventMeta, make_event_id
from scraper.utils import extract_domain, normalize_name
from scraper.validator import is_valid_listing
from scraper.level1_listing import scrape_listing
from scraper.level2_profile import scrape_profile
from scraper.level3_corporate import scrape_corporate
from scraper.level4_enrich import enrich_web
from intelligence.classifier import enrich
from deduplication import check as dedup_check
from sheets.schema import event_tab_name
from sheets.writer import (
    ensure_base_tabs, write_event_tab,
    update_index, upsert_base, read_base_companies,
)
from config import MAX_COMPANIES, NAV_TIMEOUT_MS

_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


async def run(
    event_name: str,
    event_date: str,
    listing_url: str,
    max_companies: int | None = None,
    on_progress=None,
) -> dict:
    """
    Run the full pipeline.
    on_progress(step: str, current: int, total: int) is called at each stage.
    Returns a result dict.
    """

    def progress(step: str, current: int = 0, total: int = 0):
        if on_progress:
            on_progress(step, current, total)

    result = {
        "success": False,
        "tab_name": event_tab_name(event_date, event_name),
        "companies_total": 0,
        "companies_new": 0,
        "companies_known": 0,
        "error": None,
    }

    limit = max_companies or MAX_COMPANIES

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context: BrowserContext = await browser.new_context(
            user_agent=_UA,
            viewport={"width": 1280, "height": 900},
        )

        try:
            # ── Validate URL ─────────────────────────────────────────────────
            progress("Validando URL")
            page = await context.new_page()
            await page.goto(listing_url, timeout=NAV_TIMEOUT_MS, wait_until="domcontentloaded")
            await page.wait_for_timeout(2000)
            valid, reason = await is_valid_listing(page)
            if not valid:
                result["error"] = reason
                return result
            event_domain = extract_domain(listing_url) or ""

            # ── Level 1: listing ─────────────────────────────────────────────
            progress("Extrayendo listado de expositores")
            companies = await scrape_listing(page, listing_url, limit)
            await page.close()
            if not companies:
                result["error"] = "No se encontraron empresas en el listado."
                return result
            progress("Listado extraído", len(companies), len(companies))

            # ── Load base for deduplication ──────────────────────────────────
            progress("Cargando base de empresas")
            ensure_base_tabs()
            base_records = read_base_companies()

            # ── Process each company ─────────────────────────────────────────
            total = len(companies)
            for i, company in enumerate(companies):
                company.name_normalized = normalize_name(company.name_original)
                progress(f"Procesando: {company.name_original}", i + 1, total)

                try:
                    company = await scrape_profile(company, context, event_domain)
                except Exception:
                    pass
                try:
                    company = await scrape_corporate(company, context)
                except Exception:
                    pass
                try:
                    company = await enrich_web(company, context)
                except Exception:
                    pass
                try:
                    company = await enrich(company)
                except Exception:
                    pass

                company = dedup_check(company, base_records)
                companies[i] = company

            # ── Build event metadata ─────────────────────────────────────────
            new_cos   = [c for c in companies if not c.is_known]
            known_cos = [c for c in companies if c.is_known]
            tab = event_tab_name(event_date, event_name)
            event = EventMeta(
                event_id=make_event_id(event_name, event_date),
                event_name=event_name,
                event_date=event_date,
                tab_name=tab,
                listing_url=listing_url,
                analysis_date=date.today().isoformat(),
                companies_detected=len(companies),
                companies_new=len(new_cos),
                companies_known=len(known_cos),
                status="Completado",
            )

            # ── Write to Sheets ──────────────────────────────────────────────
            progress("Escribiendo en Google Sheets", 0, 3)
            write_event_tab(companies, event)
            progress("Escribiendo en Google Sheets", 1, 3)
            upsert_base(companies, event)
            progress("Escribiendo en Google Sheets", 2, 3)
            update_index(event)
            progress("Completado", len(companies), len(companies))

            result.update({
                "success": True,
                "tab_name": tab,
                "companies_total": len(companies),
                "companies_new": len(new_cos),
                "companies_known": len(known_cos),
            })

        except Exception as e:
            result["error"] = str(e)
        finally:
            await browser.close()

    return result
