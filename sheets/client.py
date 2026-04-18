import gspread
from google.oauth2.service_account import Credentials
from loguru import logger
from config import GOOGLE_SERVICE_ACCOUNT_PATH, GOOGLE_SHEETS_ID

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

_client: gspread.Client | None = None
_spreadsheet: gspread.Spreadsheet | None = None


def get_client() -> gspread.Client:
    global _client
    if _client is None:
        creds = Credentials.from_service_account_file(
            GOOGLE_SERVICE_ACCOUNT_PATH, scopes=SCOPES
        )
        _client = gspread.authorize(creds)
        logger.debug("Google Sheets client initialized")
    return _client


def get_spreadsheet() -> gspread.Spreadsheet:
    global _spreadsheet
    if _spreadsheet is None:
        _spreadsheet = get_client().open_by_key(GOOGLE_SHEETS_ID)
        logger.debug(f"Opened spreadsheet: {_spreadsheet.title}")
    return _spreadsheet


def get_or_create_worksheet(name: str, rows: int = 1000, cols: int = 60) -> gspread.Worksheet:
    ss = get_spreadsheet()
    try:
        ws = ss.worksheet(name)
        logger.debug(f"Opened existing worksheet: {name}")
        return ws
    except gspread.WorksheetNotFound:
        ws = ss.add_worksheet(title=name, rows=rows, cols=cols)
        logger.info(f"Created worksheet: {name}")
        return ws


def worksheet_exists(name: str) -> bool:
    ss = get_spreadsheet()
    return any(ws.title == name for ws in ss.worksheets())


def validate_connection() -> tuple[bool, str]:
    try:
        ss = get_spreadsheet()
        return True, f"Conectado a: {ss.title}"
    except FileNotFoundError:
        return False, f"No se encontró el archivo de credenciales: {GOOGLE_SERVICE_ACCOUNT_PATH}"
    except gspread.exceptions.APIError as e:
        return False, f"Error de API de Google: {e}"
    except Exception as e:
        return False, f"Error de conexión: {e}"
