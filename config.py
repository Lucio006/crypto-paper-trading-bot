from __future__ import annotations
from pathlib import Path
from dotenv import load_dotenv
import os

load_dotenv()

BASE_DIR = Path(__file__).parent

# ── Google Sheets ─────────────────────────────────────────────────────────────
SHEETS_ID: str = os.environ.get("GOOGLE_SHEETS_ID", "")
CREDENTIALS_PATH: str = os.environ.get(
    "GOOGLE_SERVICE_ACCOUNT_PATH",
    str(BASE_DIR / "credentials" / "service_account.json"),
)

# ── Anthropic ─────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY: str = os.environ.get("ANTHROPIC_API_KEY", "")

# ── Playwright ────────────────────────────────────────────────────────────────
PAGE_TIMEOUT_MS: int = 30_000   # per-page load
NAV_TIMEOUT_MS: int = 60_000    # browser navigation

# ── Pipeline limits ───────────────────────────────────────────────────────────
MAX_COMPANIES: int | None = None   # None = no limit

# ── Deduplication thresholds (rapidfuzz token_sort_ratio 0–100) ───────────────
FUZZY_HIGH: int = 85   # ≥ this → automatic match
FUZZY_LOW: int = 70    # between LOW and HIGH → flag for manual review

# ── Debug ─────────────────────────────────────────────────────────────────────
DEBUG: bool = os.environ.get("DEBUG", "false").lower() == "true"


def validate() -> list[str]:
    """Return a list of configuration errors. Empty list means all good."""
    errors = []
    if not SHEETS_ID:
        errors.append("GOOGLE_SHEETS_ID no definido en .env")
    if not Path(CREDENTIALS_PATH).exists():
        errors.append(f"Credenciales no encontradas: {CREDENTIALS_PATH}")
    return errors


if __name__ == "__main__":
    print(f"SHEETS_ID         : {SHEETS_ID[:12]}…" if SHEETS_ID else "SHEETS_ID         : ✗ no definido")
    print(f"CREDENTIALS_PATH  : {CREDENTIALS_PATH}")
    print(f"  existe          : {'✓' if Path(CREDENTIALS_PATH).exists() else '✗'}")
    print(f"ANTHROPIC_API_KEY : {'✓ definida' if ANTHROPIC_API_KEY else '✗ no definida'}")
    print(f"DEBUG             : {DEBUG}")
    errors = validate()
    if errors:
        print("\nErrores:")
        for e in errors:
            print(f"  ✗ {e}")
    else:
        print("\n✓ Configuración OK")
