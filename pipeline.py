from __future__ import annotations
import asyncio
import uuid
import re
from datetime import date
from loguru import logger
from playwright.async_api import async_playwright, BrowserContext

from models.company import Company, EventMeta
from scraper.validator import is_valid_listing
from scraper.level1_listing import scrape_listing
from scraper.level2_profile import scrape_profile
from scraper.level3_corporate import scrape_corporate
from scraper.utils import extract_domain, normalize_name
from intelligence.classifier import enrich_with_claude
from intelligence.deduplicator import check_against_base
from sheets.writer import (
    ensure_base_tabs, write_event_tab, update_index, upsert_base, read_base_companies,
)
from sheets.formatter import format_all_tabs
from config import MAX_COMPANIES, NAV_TIMEOUT


def make_tab_name(event_date: str, event_name: str) -> str:
    safe_name = re.sub(r"[^\w\s\-]", "", event_name)[:30].strip()
    return f"{event_date} | {safe_name}"


def make_event_id(event_name: str, event_date: str) -> str:
    slug = re.sub(r"\W+", "-", event_name.lower())[:20]
    return f"{event_date}-{slug}"


async def run_pipeline(
    event_name: str,
    event_date: str,
    listing_url: str,
    max_companies: int | None = None,
    progress_callback=None,
) -> dict:
    """
    Main pipeline. Returns a result dict with status, counts and any errors.
    progress_callback(step: str, current: int, total: int) is called if provided.
    """

    def progress(step: str, current: int = 0, total: int = 0):
        logger.info(f"[{step}] {current}/{total}")
        if progress_callback:
            progress_callback(step, current, total)

    result = {
        "success": False,
        "event_name": event_name,
        "tab_name": make_tab_name(event_date, event_name),
        "companies_total": 0,
        "companies_new": 0,
        "companies_known": 0,
        "error": None,
    }

    limit = max_companies or MAX_COMPANIES

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context: BrowserContext = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
        )
        context.set_default_timeout(NAV_TIMEOUT)

        try:
            # ── Validation ──────────────────────────────────────────────────
            progress("Validando URL", 0, 1)
            page = await context.new_page()
            await page.goto(listing_url, timeout=NAV_TIMEOUT, wait_until="domcontentloaded")
            await page.wait_for_timeout(2000)
            valid, reason = await is_valid_listing(page)
            if not valid:
                await page.close()
                result["error"] = reason
                return result

            event_base_domain = extract_domain(listing_url) or ""
            progress("URL validada", 1, 1)

            # ── Level 1: listing ─────────────────────────────────────────────
            progress("Extrayendo listado de expositores", 0, 1)
            companies = await scrape_listing(page, listing_url, limit)
            await page.close()

            if not companies:
                result["error"] = "No se encontraron empresas en el listado."
                return result

            progress("Listado extraído", len(companies), len(companies))

            # ── Load base for deduplication ──────────────────────────────────
            progress("Cargando base de empresas", 0, 1)
            try:
                ensure_base_tabs()
                base_records = read_base_companies()
            except Exception as e:
                logger.warning(f"Could not load base companies: {e}")
                base_records = []
            progress("Base cargada", 1, 1)

            # ── Process each company ─────────────────────────────────────────
            total = len(companies)
            for i, company in enumerate(companies):
                progress(f"Procesando {company.name_original}", i + 1, total)
                company.name_normalized = normalize_name(company.name_original)

                # Level 2: profile
                try:
                    company = await scrape_profile(company, context, event_base_domain)
                except Exception as e:
                    logger.warning(f"L2 error for {company.name_original}: {e}")

                # Level 3: corporate website
                try:
                    company = await scrape_corporate(company, context)
                except Exception as e:
                    logger.warning(f"L3 error for {company.name_original}: {e}")

                # Claude enrichment
                try:
                    company = await enrich_with_claude(company)
                except Exception as e:
                    logger.warning(f"Claude error for {company.name_original}: {e}")

                # Deduplication
                company = check_against_base(company, base_records)

                companies[i] = company

            # ── Build event metadata ─────────────────────────────────────────
            known = [c for c in companies if c.is_known]
            new = [c for c in companies if not c.is_known]
            event = EventMeta(
                event_id=make_event_id(event_name, event_date),
                event_name=event_name,
                event_date=event_date,
                tab_name=make_tab_name(event_date, event_name),
                listing_url=listing_url,
                analysis_date=date.today().isoformat(),
                companies_detected=len(companies),
                companies_new=len(new),
                companies_known=len(known),
                status="Completado",
            )

            # ── Write to Sheets ──────────────────────────────────────────────
            progress("Escribiendo en Google Sheets", 0, 3)
            write_event_tab(companies, event)
            progress("Escribiendo en Google Sheets", 1, 3)
            upsert_base(companies, event)
            progress("Escribiendo en Google Sheets", 2, 3)
            update_index(event)
            progress("Aplicando formato", 3, 3)
            format_all_tabs(event.tab_name, companies)

            result.update({
                "success": True,
                "tab_name": event.tab_name,
                "companies_total": len(companies),
                "companies_new": len(new),
                "companies_known": len(known),
            })
            progress("Completado", len(companies), len(companies))

        except Exception as e:
            logger.exception(f"Pipeline error: {e}")
            result["error"] = str(e)
        finally:
            await browser.close()

    return result
