"""Google Sheet tracker (M4): the permanent, append-only job list.

- Auth comes from the service-account JSON string itself (GOOGLE_SERVICE_ACCOUNT_JSON),
  never from a file on disk.
- Everything lives in one tab, `Jobs`, laid out as models.SHEET_COLUMNS. The tab and its
  header row are created on first use. A header that doesn't match stops the run, so rows
  are never written under the wrong columns.
- Rows are only ever appended, with value_input_option="RAW": job text is untrusted, and RAW
  keeps a title like "=IMPORTXML(...)" as plain text instead of running it as a formula.
  Existing rows are never touched, so the owner's hand edits to `status` are safe.
- `setup_sheet` applies the one-time look (frozen bold header, widths, wrap, hidden id,
  score colours, status dropdown, filter). It is safe to run again.

gspread and google-auth come from the `sheets` extra, so they are imported lazily.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable

from jobagent.models import SHEET_COLUMNS, TrackerRow

log = logging.getLogger("jobagent")

TAB_NAME = "Jobs"
SCOPES = ("https://www.googleapis.com/auth/spreadsheets",)
STATUS_CHOICES = ("new", "applied", "skipped", "interviewing", "rejected", "offer")
TIMEOUT_SECONDS = 60

ID_COL = SHEET_COLUMNS.index("id") + 1  # 1-based, for col_values

# Column widths in pixels, by header name.
COLUMN_WIDTHS: dict[str, int] = {
    "date": 90,
    "source": 110,
    "company": 150,
    "title": 260,
    "link": 200,
    "location rule": 100,
    "salary": 120,
    "score": 60,
    "reason": 320,
    "draft note": 420,
    "status": 110,
    "category": 100,
    "id": 130,
}
WRAP_COLUMNS = ("reason", "draft note")

GREEN = {"red": 0.72, "green": 0.88, "blue": 0.80}
YELLOW = {"red": 1.0, "green": 0.95, "blue": 0.70}
HEADER_GREY = {"red": 0.93, "green": 0.93, "blue": 0.93}


class SheetError(RuntimeError):
    """A Sheet problem the owner can fix. The message names no secrets and no Sheet id."""


# --- Connecting ----------------------------------------------------------------------


def parse_service_account(raw: str) -> dict[str, Any]:
    """The service-account JSON as a dict. Errors never echo the value."""
    try:
        info = json.loads(raw)
    except ValueError:
        raise SheetError(
            "GOOGLE_SERVICE_ACCOUNT_JSON is not valid JSON. Paste the whole key file on one line."
        ) from None
    if not isinstance(info, dict) or info.get("type") != "service_account" or "private_key" not in info:
        raise SheetError("GOOGLE_SERVICE_ACCOUNT_JSON is not a service-account key file.")
    return info


def open_spreadsheet(service_account_json: str, sheet_id: str):
    """Open the Sheet as the service account. Returns a gspread Spreadsheet."""
    import gspread
    from google.oauth2.service_account import Credentials

    info = parse_service_account(service_account_json)
    creds = Credentials.from_service_account_info(info, scopes=list(SCOPES))
    client = gspread.authorize(creds)
    client.set_timeout(TIMEOUT_SECONDS)
    try:
        return client.open_by_key(sheet_id)
    except gspread.exceptions.SpreadsheetNotFound:
        raise SheetError(
            "The Sheet was not found. Check SHEET_ID (the long id between /d/ and /edit in the "
            "Sheet's address) and that the Sheet is shared with the service account."
        ) from None
    except PermissionError:
        raise SheetError(
            "No access to the Sheet. Share it as Editor with the service account's email "
            "(client_email in the key file)."
        ) from None


def get_or_create_tab(spreadsheet):
    """The `Jobs` worksheet, created (as the first tab) if it's missing."""
    from gspread.exceptions import WorksheetNotFound

    try:
        return spreadsheet.worksheet(TAB_NAME)
    except WorksheetNotFound:
        log.info("sheet: creating the %s tab", TAB_NAME)
        return spreadsheet.add_worksheet(title=TAB_NAME, rows=1000, cols=len(SHEET_COLUMNS), index=0)


def ensure_header(worksheet) -> None:
    """Write the header to an empty tab; stop if an existing header doesn't match.

    Extra columns the owner adds to the right of the known ones are allowed: appended rows
    still line up, because they start at column A.
    """
    header = [str(v).strip() for v in worksheet.row_values(1)]
    if not any(header):
        worksheet.update(values=[list(SHEET_COLUMNS)], range_name="A1", value_input_option="RAW")
        log.info("sheet: wrote the header row")
        return
    expected = list(SHEET_COLUMNS)
    if header[: len(expected)] != expected:
        raise SheetError(
            f"The {TAB_NAME} tab's first row doesn't match the expected columns "
            f"({' | '.join(expected)}). Nothing was written. Fix the header row, or rename "
            f"the tab so a fresh one is created."
        )


# --- Tracker -------------------------------------------------------------------------


class SheetTracker:
    """Tracker backed by the `Jobs` tab. Connects on first use."""

    def __init__(self, spreadsheet_factory: Callable[[], Any]):
        self._factory = spreadsheet_factory
        self._ws = None

    @classmethod
    def from_settings(cls, settings) -> SheetTracker:
        parse_service_account(settings.google_service_account_json)  # fail before fetching
        return cls(lambda: open_spreadsheet(settings.google_service_account_json, settings.sheet_id))

    def worksheet(self):
        if self._ws is None:
            ws = get_or_create_tab(self._factory())
            ensure_header(ws)
            self._ws = ws
        return self._ws

    def seen_ids(self) -> set[str]:
        values = self.worksheet().col_values(ID_COL)[1:]  # skip the header
        ids = {str(v).strip() for v in values if v not in (None, "")}
        log.info("sheet: %d ids already tracked", len(ids))
        return ids

    def append(self, rows: list[TrackerRow]) -> None:
        if not rows:
            return
        self.worksheet().append_rows(
            [r.as_list() for r in rows],
            value_input_option="RAW",
            insert_data_option="INSERT_ROWS",
            table_range="A1",
        )
        log.info("sheet: appended %d rows", len(rows))


# --- One-time setup ------------------------------------------------------------------


def _col_range(sheet_id: int, col: int, *, start_row: int = 0) -> dict:
    """A whole-column GridRange (0-based col), open-ended downwards."""
    return {"sheetId": sheet_id, "startRowIndex": start_row, "startColumnIndex": col, "endColumnIndex": col + 1}


def setup_requests(sheet_id: int, existing_rules: list[dict]) -> list[dict]:
    """batchUpdate requests that give the `Jobs` tab its look. Same result every time.

    existing_rules: this tab's current conditional-format rules, so the old score rules
    can be removed before the new ones are added (other rules are left alone).
    """
    col = {name: i for i, name in enumerate(SHEET_COLUMNS)}
    ncols = len(SHEET_COLUMNS)
    reqs: list[dict] = [
        {
            "updateSheetProperties": {
                "properties": {"sheetId": sheet_id, "gridProperties": {"frozenRowCount": 1}},
                "fields": "gridProperties.frozenRowCount",
            }
        },
        {
            "repeatCell": {
                "range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1, "startColumnIndex": 0, "endColumnIndex": ncols},
                "cell": {"userEnteredFormat": {"textFormat": {"bold": True}, "backgroundColor": HEADER_GREY}},
                "fields": "userEnteredFormat.textFormat.bold,userEnteredFormat.backgroundColor",
            }
        },
        {
            "repeatCell": {
                "range": {"sheetId": sheet_id, "startRowIndex": 1, "startColumnIndex": 0, "endColumnIndex": ncols},
                "cell": {"userEnteredFormat": {"verticalAlignment": "TOP"}},
                "fields": "userEnteredFormat.verticalAlignment",
            }
        },
    ]
    for name, width in COLUMN_WIDTHS.items():
        reqs.append(
            {
                "updateDimensionProperties": {
                    "range": {"sheetId": sheet_id, "dimension": "COLUMNS", "startIndex": col[name], "endIndex": col[name] + 1},
                    "properties": {"pixelSize": width},
                    "fields": "pixelSize",
                }
            }
        )
    for name in WRAP_COLUMNS:
        reqs.append(
            {
                "repeatCell": {
                    "range": _col_range(sheet_id, col[name], start_row=1),
                    "cell": {"userEnteredFormat": {"wrapStrategy": "WRAP"}},
                    "fields": "userEnteredFormat.wrapStrategy",
                }
            }
        )
    reqs.append(
        {
            "updateDimensionProperties": {
                "range": {"sheetId": sheet_id, "dimension": "COLUMNS", "startIndex": col["id"], "endIndex": col["id"] + 1},
                "properties": {"hiddenByUser": True},
                "fields": "hiddenByUser",
            }
        }
    )

    # Score colours: drop any earlier rules on the score column (highest index first, so
    # the remaining indexes stay valid), then add >=70 green and 50-69 yellow.
    score = col["score"]
    for index in sorted(
        (i for i, rule in enumerate(existing_rules) if _targets_column(rule, sheet_id, score)), reverse=True
    ):
        reqs.append({"deleteConditionalFormatRule": {"sheetId": sheet_id, "index": index}})
    score_range = _col_range(sheet_id, score, start_row=1)
    reqs.append(
        {
            "addConditionalFormatRule": {
                "index": 0,
                "rule": {
                    "ranges": [score_range],
                    "booleanRule": {
                        "condition": {"type": "NUMBER_GREATER_THAN_EQ", "values": [{"userEnteredValue": "70"}]},
                        "format": {"backgroundColor": GREEN},
                    },
                },
            }
        }
    )
    reqs.append(
        {
            "addConditionalFormatRule": {
                "index": 1,
                "rule": {
                    "ranges": [score_range],
                    "booleanRule": {
                        "condition": {
                            "type": "NUMBER_BETWEEN",
                            "values": [{"userEnteredValue": "50"}, {"userEnteredValue": "69"}],
                        },
                        "format": {"backgroundColor": YELLOW},
                    },
                },
            }
        }
    )

    reqs.append(
        {
            "setDataValidation": {
                "range": _col_range(sheet_id, col["status"], start_row=1),
                "rule": {
                    "condition": {"type": "ONE_OF_LIST", "values": [{"userEnteredValue": v} for v in STATUS_CHOICES]},
                    "strict": True,
                    "showCustomUi": True,
                },
            }
        }
    )
    reqs.append(
        {
            "setBasicFilter": {
                "filter": {"range": {"sheetId": sheet_id, "startRowIndex": 0, "startColumnIndex": 0, "endColumnIndex": ncols}}
            }
        }
    )
    return reqs


def _targets_column(rule: dict, sheet_id: int, column: int) -> bool:
    return any(
        r.get("sheetId", 0) == sheet_id
        and r.get("startColumnIndex") == column
        and r.get("endColumnIndex") == column + 1
        for r in rule.get("ranges", [])
    )


def setup_sheet(spreadsheet) -> int:
    """Create the tab and header if needed, then format it. Returns the number of requests."""
    ws = get_or_create_tab(spreadsheet)
    ensure_header(ws)
    meta = spreadsheet.fetch_sheet_metadata({"fields": "sheets(properties.sheetId,conditionalFormats)"})
    rules: list[dict] = []
    for sheet in meta.get("sheets", []):
        if sheet.get("properties", {}).get("sheetId") == ws.id:
            rules = sheet.get("conditionalFormats", [])
    reqs = setup_requests(ws.id, rules)
    spreadsheet.batch_update({"requests": reqs})
    return len(reqs)
