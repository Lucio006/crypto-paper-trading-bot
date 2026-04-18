from __future__ import annotations
import gspread
from gspread.utils import rowcol_to_a1
from loguru import logger
from sheets.client import get_spreadsheet, get_or_create_worksheet
from config import TAB_INDEX, TAB_BASE

# Row colors (RGB 0-1 scale for Sheets API)
COLOR_NEW = {"red": 0.91, "green": 0.96, "blue": 0.91}        # #E8F5E9 green
COLOR_KNOWN = {"red": 1.0, "green": 0.99, "blue": 0.88}       # #FFFDE7 yellow
COLOR_CONTACTED = {"red": 1.0, "green": 0.95, "blue": 0.88}   # #FFF3E0 orange
COLOR_NO_CONTACT = {"red": 1.0, "green": 0.92, "blue": 0.93}  # #FFEBEE red
COLOR_REVIEW = {"red": 0.96, "green": 0.96, "blue": 0.96}     # #F5F5F5 grey
COLOR_HEADER = {"red": 0.23, "green": 0.44, "blue": 0.72}     # dark blue header


def _rgb(r255: int, g255: int, b255: int) -> dict:
    return {"red": r255 / 255, "green": g255 / 255, "blue": b255 / 255}


def format_worksheet(ws: gspread.Worksheet, companies_data: list[dict] | None = None) -> None:
    ss = get_spreadsheet()
    ws_id = ws.id
    requests = []

    # Freeze first row
    requests.append({
        "updateSheetProperties": {
            "properties": {"sheetId": ws_id, "gridProperties": {"frozenRowCount": 1}},
            "fields": "gridProperties.frozenRowCount",
        }
    })

    # Auto-resize all columns
    requests.append({
        "autoResizeDimensions": {
            "dimensions": {"sheetId": ws_id, "dimension": "COLUMNS", "startIndex": 0, "endIndex": 60}
        }
    })

    # Bold + colored header row
    requests.append({
        "repeatCell": {
            "range": {"sheetId": ws_id, "startRowIndex": 0, "endRowIndex": 1},
            "cell": {
                "userEnteredFormat": {
                    "backgroundColor": COLOR_HEADER,
                    "textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
                    "horizontalAlignment": "CENTER",
                }
            },
            "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)",
        }
    })

    # Set filter on header row
    requests.append({
        "setBasicFilter": {
            "filter": {"range": {"sheetId": ws_id, "startRowIndex": 0, "startColumnIndex": 0}}
        }
    })

    if requests:
        ss.batch_update({"requests": requests})
        logger.debug(f"Base formatting applied to '{ws.title}'")

    # Color rows based on status (only for event tabs with company data)
    if companies_data:
        _color_event_rows(ws, companies_data)


def _color_event_rows(ws: gspread.Worksheet, companies: list[dict]) -> None:
    ss = get_spreadsheet()
    ws_id = ws.id
    requests = []

    for i, company in enumerate(companies, start=2):  # row 1 is header
        status = company.get("commercial_status", "Nueva")
        is_known = company.get("is_known", False)
        times_contacted = company.get("times_contacted", 0)
        do_not_contact = status == "No contactar"
        requires_review = company.get("requires_review", False)

        if do_not_contact:
            color = COLOR_NO_CONTACT
        elif requires_review:
            color = COLOR_REVIEW
        elif times_contacted > 0:
            color = COLOR_CONTACTED
        elif is_known:
            color = COLOR_KNOWN
        else:
            color = COLOR_NEW

        requests.append({
            "repeatCell": {
                "range": {
                    "sheetId": ws_id,
                    "startRowIndex": i - 1,
                    "endRowIndex": i,
                    "startColumnIndex": 0,
                    "endColumnIndex": 60,
                },
                "cell": {"userEnteredFormat": {"backgroundColor": color}},
                "fields": "userEnteredFormat.backgroundColor",
            }
        })

    if requests:
        ss.batch_update({"requests": requests})
        logger.debug(f"Row colors applied to '{ws.title}'")


def format_all_tabs(event_tab_name: str | None = None, companies: list | None = None) -> None:
    for tab_name in [TAB_INDEX, TAB_BASE]:
        try:
            ws = get_or_create_worksheet(tab_name)
            format_worksheet(ws)
        except Exception as e:
            logger.warning(f"Could not format tab '{tab_name}': {e}")

    if event_tab_name:
        try:
            ws = get_or_create_worksheet(event_tab_name)
            companies_data = [
                {
                    "commercial_status": c.commercial_status,
                    "is_known": c.is_known,
                    "times_contacted": c.times_contacted,
                    "requires_review": c.requires_review,
                }
                for c in (companies or [])
            ]
            format_worksheet(ws, companies_data)
        except Exception as e:
            logger.warning(f"Could not format event tab '{event_tab_name}': {e}")
