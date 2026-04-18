"""
Google Sheets connection — singleton client and worksheet helpers.
"""
from __future__ import annotations
import gspread
from google.oauth2.service_account import Credentials
from config import SHEETS_ID, CREDENTIALS_PATH

_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

_client: gspread.Client | None = None
_spreadsheet: gspread.Spreadsheet | None = None


def get_client() -> gspread.Client:
    global _client
    if _client is None:
        creds = Credentials.from_service_account_file(CREDENTIALS_PATH, scopes=_SCOPES)
        _client = gspread.authorize(creds)
    return _client


def get_spreadsheet() -> gspread.Spreadsheet:
    global _spreadsheet
    if _spreadsheet is None:
        _spreadsheet = get_client().open_by_key(SHEETS_ID)
    return _spreadsheet


def get_or_create_worksheet(name: str, rows: int = 2000, cols: int = 60) -> gspread.Worksheet:
    ss = get_spreadsheet()
    try:
        return ss.worksheet(name)
    except gspread.WorksheetNotFound:
        return ss.add_worksheet(title=name, rows=rows, cols=cols)


def worksheet_exists(name: str) -> bool:
    return any(ws.title == name for ws in get_spreadsheet().worksheets())


def validate_connection() -> tuple[bool, str]:
    """Return (ok, message). Safe to call before any other operation."""
    try:
        ss = get_spreadsheet()
        return True, f"Conectado a: «{ss.title}»"
    except FileNotFoundError:
        return False, f"Credenciales no encontradas: {CREDENTIALS_PATH}"
    except gspread.exceptions.APIError as e:
        return False, f"Error de API: {e}"
    except Exception as e:
        return False, f"Error de conexión: {e}"
