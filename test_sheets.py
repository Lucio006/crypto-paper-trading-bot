"""
Prueba mínima de conexión con Google Sheets.
Verifica credenciales y escribe una fila de prueba en la hoja TEST.

Uso:
    python test_sheets.py
"""
import os
import sys
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

SHEETS_ID = os.environ.get("GOOGLE_SHEETS_ID", "")
SA_PATH = os.environ.get("GOOGLE_SERVICE_ACCOUNT_PATH", "./credentials/service_account.json")

def check_env():
    errors = []
    if not SHEETS_ID:
        errors.append("  ✗ GOOGLE_SHEETS_ID no está en el .env")
    else:
        print(f"  ✓ GOOGLE_SHEETS_ID encontrado: {SHEETS_ID[:12]}…")

    sa_file = Path(SA_PATH)
    if not sa_file.exists():
        errors.append(f"  ✗ No se encuentra el archivo de credenciales: {SA_PATH}")
    else:
        print(f"  ✓ Credenciales encontradas: {SA_PATH}")

    if errors:
        for e in errors:
            print(e)
        sys.exit(1)


def connect():
    import gspread
    from google.oauth2.service_account import Credentials

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_file(SA_PATH, scopes=scopes)
    client = gspread.authorize(creds)
    return client


def run_test():
    print("\n── Paso 1: Variables de entorno ────────────────────")
    check_env()

    print("\n── Paso 2: Conexión con Google Sheets ──────────────")
    try:
        client = connect()
        print("  ✓ Cliente gspread inicializado")
    except FileNotFoundError:
        print(f"  ✗ Archivo no encontrado: {SA_PATH}")
        sys.exit(1)
    except Exception as e:
        print(f"  ✗ Error al conectar: {e}")
        sys.exit(1)

    print("\n── Paso 3: Abrir el Spreadsheet ────────────────────")
    try:
        ss = client.open_by_key(SHEETS_ID)
        print(f"  ✓ Spreadsheet abierto: '{ss.title}'")
        tabs = [ws.title for ws in ss.worksheets()]
        print(f"  ✓ Pestañas actuales: {tabs}")
    except gspread.exceptions.APIError as e:
        print(f"  ✗ Error de API: {e}")
        print("     Verifica que compartiste el Sheets con el email del service account.")
        sys.exit(1)
    except Exception as e:
        print(f"  ✗ Error: {e}")
        sys.exit(1)

    print("\n── Paso 4: Escribir fila de prueba ─────────────────")
    try:
        # Get or create TEST tab
        try:
            ws = ss.worksheet("TEST")
        except Exception:
            ws = ss.add_worksheet(title="TEST", rows=10, cols=5)
            print("  ✓ Pestaña 'TEST' creada")

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ws.append_row(["✓ Conexión OK", now, "prueba desde test_sheets.py"])
        print(f"  ✓ Fila de prueba escrita en la pestaña 'TEST' ({now})")
    except Exception as e:
        print(f"  ✗ Error al escribir: {e}")
        sys.exit(1)

    print("\n════════════════════════════════════════════════════")
    print("  TODO OK. Google Sheets está correctamente configurado.")
    print(f"  https://docs.google.com/spreadsheets/d/{SHEETS_ID}/edit")
    print("════════════════════════════════════════════════════\n")


if __name__ == "__main__":
    import gspread  # imported here so error is clear if not installed
    run_test()
