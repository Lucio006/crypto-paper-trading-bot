"""
Event Prospector – Local interface
Run with: streamlit run app.py
"""
from __future__ import annotations
import asyncio
import threading
from datetime import date, datetime
from loguru import logger
import streamlit as st

from config import GOOGLE_SHEETS_ID, ANTHROPIC_API_KEY, GOOGLE_SERVICE_ACCOUNT_PATH, DEBUG
from sheets.client import validate_connection
from pipeline import run_pipeline

# ──────────────────────────────────────────────
# Page config
# ──────────────────────────────────────────────
st.set_page_config(
    page_title="Event Prospector",
    page_icon="📋",
    layout="centered",
)

# ──────────────────────────────────────────────
# Minimal CSS
# ──────────────────────────────────────────────
st.markdown(
    """
    <style>
    .stApp { max-width: 760px; margin: 0 auto; }
    .status-box { background: #f0f2f6; border-radius: 8px; padding: 12px 16px; font-size: 14px; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ──────────────────────────────────────────────
# Header
# ──────────────────────────────────────────────
st.title("📋 Event Prospector")
st.caption("Extrae empresas expositoras de eventos y las escribe en Google Sheets")

# ──────────────────────────────────────────────
# Config status
# ──────────────────────────────────────────────
with st.expander("Estado de configuración", expanded=False):
    sheets_ok, sheets_msg = validate_connection() if GOOGLE_SHEETS_ID else (False, "GOOGLE_SHEETS_ID no configurado")
    api_ok = bool(ANTHROPIC_API_KEY)
    creds_ok = bool(GOOGLE_SERVICE_ACCOUNT_PATH)

    col1, col2, col3 = st.columns(3)
    col1.metric("Google Sheets", "✅ OK" if sheets_ok else "❌ Error", sheets_msg[:40] if not sheets_ok else "")
    col2.metric("Anthropic API", "✅ OK" if api_ok else "❌ Falta clave", "")
    col3.metric("Service Account", "✅ OK" if creds_ok else "❌ Falta JSON", "")

    if GOOGLE_SHEETS_ID:
        sheets_url = f"https://docs.google.com/spreadsheets/d/{GOOGLE_SHEETS_ID}/edit"
        st.markdown(f"[Abrir Google Sheets]({sheets_url})")

st.divider()

# ──────────────────────────────────────────────
# Input form
# ──────────────────────────────────────────────
with st.form("event_form", clear_on_submit=False):
    event_name = st.text_input(
        "Nombre del evento",
        placeholder="Ej: IFEMA Madrid 2025",
    )
    event_date = st.date_input(
        "Fecha del evento",
        value=date.today(),
        format="YYYY-MM-DD",
    )
    listing_url = st.text_input(
        "URL del listado de expositores",
        placeholder="https://www.evento.com/expositores",
    )

    with st.expander("Opciones avanzadas"):
        max_companies = st.number_input(
            "Máximo de empresas (0 = sin límite)",
            min_value=0,
            max_value=1000,
            value=0,
            step=10,
        )

    submitted = st.form_submit_button("🔍 Analizar evento", use_container_width=True)

# ──────────────────────────────────────────────
# Run pipeline
# ──────────────────────────────────────────────
if submitted:
    errors = []
    if not event_name.strip():
        errors.append("El nombre del evento es obligatorio.")
    if not listing_url.strip():
        errors.append("La URL del listado de expositores es obligatoria.")
    if not sheets_ok:
        errors.append(f"Google Sheets no está configurado correctamente: {sheets_msg}")

    if errors:
        for e in errors:
            st.error(e)
    else:
        limit = int(max_companies) if max_companies > 0 else None
        date_str = event_date.isoformat()

        st.info(f"Iniciando análisis de **{event_name}** ({date_str})…")

        # Progress placeholders
        progress_bar = st.progress(0)
        status_text = st.empty()
        log_area = st.empty()
        log_lines: list[str] = []

        def on_progress(step: str, current: int, total: int):
            pct = int((current / total) * 100) if total > 0 else 0
            progress_bar.progress(pct)
            status_text.markdown(f"**{step}** — {current}/{total}" if total else f"**{step}**")
            ts = datetime.now().strftime("%H:%M:%S")
            log_lines.append(f"`{ts}` {step}")
            if len(log_lines) > 20:
                log_lines.pop(0)
            log_area.markdown("\n".join(log_lines))

        # Run the async pipeline from sync Streamlit context
        try:
            result = asyncio.run(
                run_pipeline(
                    event_name=event_name.strip(),
                    event_date=date_str,
                    listing_url=listing_url.strip(),
                    max_companies=limit,
                    progress_callback=on_progress,
                )
            )
        except Exception as exc:
            result = {"success": False, "error": str(exc)}

        progress_bar.progress(100)

        if result.get("success"):
            st.success(
                f"✅ Análisis completado: **{result['companies_total']}** empresas procesadas "
                f"({result['companies_new']} nuevas, {result['companies_known']} ya conocidas)"
            )
            if GOOGLE_SHEETS_ID:
                sheets_url = f"https://docs.google.com/spreadsheets/d/{GOOGLE_SHEETS_ID}/edit"
                st.markdown(f"[Ver resultados en Google Sheets →]({sheets_url})")
        else:
            st.error(f"❌ Error: {result.get('error', 'Error desconocido')}")

# ──────────────────────────────────────────────
# Footer
# ──────────────────────────────────────────────
st.divider()
st.caption("Event Prospector · Herramienta privada de uso local")
