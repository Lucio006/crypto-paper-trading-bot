"""
Test scraper/utils.py — pure Python, no network, no Playwright.
Run with: python test_utils.py
"""
from scraper.utils import (
    normalize_name, extract_domain, normalize_url,
    extract_emails, classify_emails, extract_phone,
    extract_telegram, reason_for_missing,
)

PASS = "✓"
FAIL = "✗"

def check(label: str, got, expected):
    ok = got == expected
    print(f"  {PASS if ok else FAIL} {label}")
    if not ok:
        print(f"      esperado : {expected!r}")
        print(f"      obtenido : {got!r}")
    return ok

results = []

print("\n── normalize_name ───────────────────────────────────")
results += [
    check("quita tildes",          normalize_name("Café Español"),         "cafe espanol"),
    check("quita sufijo S.L.",     normalize_name("Empresa Ejemplo S.L."), "empresa ejemplo"),
    check("quita sufijo LLC",      normalize_name("Acme Corp LLC"),        "acme corp"),
    check("colapsa espacios",      normalize_name("  Foo   Bar  "),        "foo bar"),
    check("quita puntuación",      normalize_name("Foo & Bar, S.A."),      "foo bar"),
]

print("\n── extract_domain ───────────────────────────────────")
results += [
    check("quita www.",            extract_domain("https://www.empresa.com/contacto"), "empresa.com"),
    check("sin scheme",            extract_domain("empresa.com"),                      "empresa.com"),
    check("subdominio",            extract_domain("https://blog.empresa.com"),         "blog.empresa.com"),
    check("None en vacío",         extract_domain(""),                                 None),
]

print("\n── extract_emails ───────────────────────────────────")
text = "Contacta con info@empresa.com o escribe a marketing@empresa.com y CEO@empresa.com"
emails = extract_emails(text)
results += [
    check("extrae 3 emails",       len(emails), 3),
    check("todo minúsculas",       emails[2],   "ceo@empresa.com"),
    check("sin duplicados",        len(extract_emails("a@b.com A@b.com")), 1),
]

print("\n── classify_emails ──────────────────────────────────")
classified = classify_emails([
    "info@empresa.com",
    "marketing@empresa.com",
    "eventos@empresa.com",
    "ceo@empresa.com",
    "ventas@empresa.com",
])
results += [
    check("general",               classified["email_general"],   "info@empresa.com"),
    check("marketing",             classified["email_marketing"], "marketing@empresa.com"),
    check("events",                classified["email_events"],    "eventos@empresa.com"),
    check("ceo",                   classified["email_ceo"],       "ceo@empresa.com"),
    check("cco (ventas)",          classified["email_cco"],       "ventas@empresa.com"),
]

print("\n── extract_phone ────────────────────────────────────")
results += [
    check("teléfono ES",           extract_phone("Llámanos al +34 91 123 45 67"), "+34 91 123 45 67"),
    check("teléfono con guiones",  extract_phone("Tel: 91-123-45-67"),            "91-123-45-67"),
    check("sin teléfono",          extract_phone("no hay número aquí"),            None),
]

print("\n── extract_telegram ─────────────────────────────────")
results += [
    check("t.me link",             extract_telegram("Únete en t.me/micanal"),       "t.me/micanal"),
    check("telegram.me link",      extract_telegram("Ver telegram.me/otro"),         "t.me/otro"),
    check("sin Telegram",          extract_telegram("solo twitter.com/cuenta"),      None),
]

print("\n── reason_for_missing ───────────────────────────────")
results += [
    check("sin web",    reason_for_missing("email_marketing", "no_website", []),
          "No aparece web corporativa en la ficha del evento"),
    check("timeout",    reason_for_missing("email_events", "timeout", []),
          "La web corporativa no cargó (timeout)"),
    check("solo form",  reason_for_missing("email_general", "ok", ["form_only"]),
          "Solo hay formulario de contacto, no hay email publicado"),
    check("ceo gdpr",   reason_for_missing("email_ceo", "ok", []),
          "No hay emails directivos publicados en la web (habitual por GDPR)"),
    check("telegram",   reason_for_missing("telegram", "ok", []),
          "No aparece Telegram en la web ni en perfiles enlazados"),
]

# ── Summary ───────────────────────────────────────────────────────────────────
passed = sum(results)
total  = len(results)
print(f"\n{'═'*52}")
print(f"  {passed}/{total} tests OK {'✓' if passed == total else '✗ hay fallos'}")
print(f"{'═'*52}\n")
