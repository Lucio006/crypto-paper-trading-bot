from pathlib import Path
from dotenv import load_dotenv
import os

load_dotenv()

BASE_DIR = Path(__file__).parent

ANTHROPIC_API_KEY: str = os.environ.get("ANTHROPIC_API_KEY", "")
GOOGLE_SHEETS_ID: str = os.environ.get("GOOGLE_SHEETS_ID", "")
GOOGLE_SERVICE_ACCOUNT_PATH: str = os.environ.get(
    "GOOGLE_SERVICE_ACCOUNT_PATH", "./credentials/service_account.json"
)
MAX_COMPANIES: int | None = (
    int(os.environ["MAX_COMPANIES"]) if os.environ.get("MAX_COMPANIES") else None
)
DEBUG: bool = os.environ.get("DEBUG", "false").lower() == "true"

# Playwright timeouts (ms)
PAGE_TIMEOUT = 30_000
NAV_TIMEOUT = 60_000

# Fuzzy match threshold for deduplication
FUZZY_MATCH_HIGH = 85   # auto-match
FUZZY_MATCH_LOW = 70    # needs review

# Commercial status values
STATUS_NEW = "Nueva"
STATUS_NOT_CONTACTED = "No contactada"
STATUS_CONTACTED = "Contactada"
STATUS_FOLLOW_UP = "Pendiente de volver a contactar"
STATUS_IN_CONVERSATION = "En conversación"
STATUS_WON = "Ganada"
STATUS_LOST = "Perdida"
STATUS_DO_NOT_CONTACT = "No contactar"

# Google Sheets tab names
TAB_INDEX = "ÍNDICE EVENTOS"
TAB_BASE = "BASE EMPRESAS"
