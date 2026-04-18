"""
Test: write a fake company and event to Google Sheets.
Verifies that sheets/client.py + sheets/writer.py work end-to-end.

Run with: python test_writer.py
"""
from models import Company, ContactData, EventMeta, make_event_id
from sheets.schema import event_tab_name
from sheets.writer import ensure_base_tabs, write_event_tab, update_index, upsert_base
from config import SHEETS_ID

# ── Fake data ──────────────────────────────────────────────────────────────────

EVENT_NAME = "Test Event 2025"
EVENT_DATE = "2025-06-15"

contact = ContactData(
    email_general="info@empresa-test.com",
    email_marketing="marketing@empresa-test.com",
    phone="+34 91 000 00 00",
    best_contact="marketing@empresa-test.com",
    best_contact_role="Marketing",
    recommended_channel="Email",
    contact_priority="Alta",
    confidence_level="Alta",
    reason_no_events="No hay email de eventos publicado en la web",
    reason_no_ceo="No hay emails directivos publicados (habitual por GDPR)",
    reason_no_cco="No hay emails directivos publicados (habitual por GDPR)",
    reason_no_telegram="No aparece Telegram en la web ni en perfiles enlazados",
)

company = Company(
    name_original="Empresa Test S.L.",
    name_normalized="empresa test",
    stand="B12",
    exhibitor_profile_url="https://www.evento-test.com/expositores/empresa-test",
    description="Empresa de prueba para validar la escritura en Google Sheets.",
    website_from_event="https://www.empresa-test.com",
    corporate_website="https://www.empresa-test.com",
    domain="empresa-test.com",
    country="España",
    sector="Tecnología",
    category="Software",
    contact=contact,
    commercial_status="Nueva",
    is_known=False,
)

tab = event_tab_name(EVENT_DATE, EVENT_NAME)
event = EventMeta(
    event_name=EVENT_NAME,
    event_date=EVENT_DATE,
    listing_url="https://www.evento-test.com/expositores",
    tab_name=tab,
    event_id=make_event_id(EVENT_NAME, EVENT_DATE),
    companies_detected=1,
    companies_new=1,
    companies_known=0,
    status="Completado",
)

# ── Run ────────────────────────────────────────────────────────────────────────

print(f"\nEscribiendo en Google Sheets…")
print(f"  Spreadsheet: {SHEETS_ID[:12]}…")
print(f"  Pestaña evento: «{tab}»\n")

print("1. Creando pestañas base (ÍNDICE EVENTOS + BASE EMPRESAS)…")
ensure_base_tabs()
print("   ✓")

print("2. Escribiendo empresa en la pestaña del evento…")
n = write_event_tab([company], event)
print(f"   ✓ {n} fila(s) escritas en «{tab}»")

print("3. Actualizando ÍNDICE EVENTOS…")
update_index(event)
print("   ✓")

print("4. Upsert en BASE EMPRESAS…")
inserted, updated = upsert_base([company], event)
print(f"   ✓ {inserted} nueva(s), {updated} actualizada(s)")

print(f"""
════════════════════════════════════════════════════
  TODO OK. Abre el Sheets para verificar:
  https://docs.google.com/spreadsheets/d/{SHEETS_ID}/edit

  Deberías ver 3 pestañas nuevas:
    · ÍNDICE EVENTOS
    · BASE EMPRESAS
    · {tab}
════════════════════════════════════════════════════
""")
