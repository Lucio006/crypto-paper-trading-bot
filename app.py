"""
Event Prospector — interfaz local en localhost:8501
Ejecutar con: streamlit run app.py
"""
import asyncio
from datetime import date, datetime
import streamlit as st
from config import SHEETS_ID, ANTHROPIC_API_KEY
from sheets.client import validate_connection
from pipeline import run as run_pipeline

st.set_page_config(page_title="Event Prospector", page_icon="📋", layout="centered")

st.markdown("""
<style>
.stApp { max-width: 720px; margin: 0 auto; }
</style>
""", unsafe_allow_html=True)

st.title("📋 Event Prospector")
st.caption("Extrae expositores de eventos y los escribe en Google Sheets")

# ── Config status ──────────────────────────────────────────────────────────────
with st.expander("Estado de configuración", expanded=False):
    sheets_ok, sheets_msg = (
        validate_connection() if SHEETS_ID else (False, "GOOGLE_SHEETS_ID no configurado")
    )
    col1, col2 = st.columns(2)
    col1.metric("Google Sheets", "✅ OK" if sheets_ok else "❌ Error")
    col2.metric("Anthropic API", "✅ OK" if ANTHROPIC_API_KEY else "⚠️ Opcional")
    if not sheets_ok:
        st.error(sheets_msg)
    if SHEETS_ID and sheets_ok:
        st.markdown(f"[Abrir Google Sheets](https://docs.google.com/spreadsheets/d/{SHEETS_ID}/edit)")

st.divider()

# ── Form ───────────────────────────────────────────────────────────────────────
with st.form("event_form"):
    event_name = st.text_input("Nombre del evento", placeholder="Ej: iGB Live 2026")
    event_date = st.date_input("Fecha del evento", value=date.today(), format="YYYY-MM-DD")
    listing_url = st.text_input(
        "URL del listado de expositores",
        placeholder="https://www.evento.com/expositores",
    )
    with st.expander("Opciones avanzadas"):
        max_companies = st.number_input(
            "Máximo de empresas (0 = sin límite)", min_value=0, max_value=1000, value=0, step=10
        )
    submitted = st.form_submit_button("🔍 Analizar evento", use_container_width=True)

# ── Run ────────────────────────────────────────────────────────────────────────
if submitted:
    errors = []
    if not event_name.strip():
        errors.append("El nombre del evento es obligatorio.")
    if not listing_url.strip():
        errors.append("La URL del listado de expositores es obligatoria.")
    if not sheets_ok:
        errors.append("Google Sheets no está correctamente configurado.")

    if errors:
        for e in errors:
            st.error(e)
    else:
        limit = int(max_companies) if max_companies > 0 else None
        date_str = event_date.isoformat()

        st.info(f"Analizando **{event_name}** ({date_str})…")
        bar = st.progress(0)
        status = st.empty()
        log = st.empty()
        lines: list[str] = []

        def on_progress(step: str, current: int = 0, total: int = 0):
            pct = int(current / total * 100) if total else 0
            bar.progress(pct)
            status.markdown(f"**{step}**" + (f" — {current}/{total}" if total else ""))
            ts = datetime.now().strftime("%H:%M:%S")
            lines.append(f"`{ts}` {step}")
            if len(lines) > 15:
                lines.pop(0)
            log.markdown("\n".join(lines))

        try:
            result = asyncio.run(run_pipeline(
                event_name=event_name.strip(),
                event_date=date_str,
                listing_url=listing_url.strip(),
                max_companies=limit,
                on_progress=on_progress,
            ))
        except Exception as exc:
            result = {"success": False, "error": str(exc)}

        bar.progress(100)

        if result.get("success"):
            st.success(
                f"✅ **{result['companies_total']}** empresas procesadas — "
                f"{result['companies_new']} nuevas, {result['companies_known']} ya conocidas"
            )
            if SHEETS_ID:
                st.markdown(
                    f"[Ver resultados en Google Sheets →]"
                    f"(https://docs.google.com/spreadsheets/d/{SHEETS_ID}/edit)"
                )
        else:
            st.error(f"❌ {result.get('error', 'Error desconocido')}")

st.divider()
st.caption("Event Prospector · herramienta local privada")
