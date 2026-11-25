from datetime import date

import pytest
from gspread.exceptions import WorksheetNotFound

from fakes import make_job
from jobagent import sheet
from jobagent.models import SHEET_COLUMNS, Assessment, Candidate, Category, TrackerRow, Verdict
from jobagent.sheet import SheetError, SheetTracker


class FakeWorksheet:
    """Just enough of gspread.Worksheet: a grid of rows, starting at A1."""

    def __init__(self, title="Jobs", rows=None, ws_id=111):
        self.title = title
        self.id = ws_id
        self.rows: list[list] = [list(r) for r in (rows or [])]
        self.append_calls: list[dict] = []
        self.update_calls: list[dict] = []

    def row_values(self, n):
        return list(self.rows[n - 1]) if len(self.rows) >= n else []

    def col_values(self, n):
        return [r[n - 1] if len(r) >= n else None for r in self.rows]

    def update(self, values, range_name=None, value_input_option=None, **kw):
        assert range_name == "A1"
        self.update_calls.append({"values": values, "value_input_option": value_input_option})
        if self.rows:
            self.rows[0] = list(values[0])
        else:
            self.rows.append(list(values[0]))

    def append_rows(self, values, value_input_option=None, insert_data_option=None, table_range=None):
        self.append_calls.append(
            {"n": len(values), "value_input_option": value_input_option, "table_range": table_range}
        )
        self.rows.extend(list(v) for v in values)


class FakeSpreadsheet:
    def __init__(self, worksheets=None, conditional_formats=None):
        self.worksheets = {ws.title: ws for ws in (worksheets or [])}
        self.conditional_formats = conditional_formats or []
        self.batches: list[dict] = []
        self.added: list[str] = []

    def worksheet(self, title):
        if title not in self.worksheets:
            raise WorksheetNotFound(title)
        return self.worksheets[title]

    def add_worksheet(self, title, rows, cols, index=None):
        self.added.append(title)
        ws = FakeWorksheet(title=title, ws_id=222)
        self.worksheets[title] = ws
        return ws

    def fetch_sheet_metadata(self, params=None):
        sheets = [{"properties": {"sheetId": ws.id}} for ws in self.worksheets.values()]
        for s in sheets:
            if s["properties"]["sheetId"] == self.worksheets.get("Jobs", FakeWorksheet(ws_id=-1)).id:
                s["conditionalFormats"] = self.conditional_formats
        return {"sheets": sheets}

    def batch_update(self, body):
        self.batches.append(body)


def row(n, **overrides):
    job = make_job(n, **overrides)
    c = Candidate(
        job=job,
        verdict=Verdict(keep=True, category=Category.STACK, location_rule="worldwide"),
        assessment=Assessment(job.id, 80, "good fit", "draft"),
    )
    return TrackerRow.from_candidate(c, date(2026, 11, 25))


def tracker_for(ss):
    return SheetTracker(lambda: ss)


# --- tab and header ------------------------------------------------------------------


def test_creates_jobs_tab_and_header_when_missing():
    ss = FakeSpreadsheet()
    assert tracker_for(ss).seen_ids() == set()
    assert ss.added == ["Jobs"]
    ws = ss.worksheets["Jobs"]
    assert ws.rows == [list(SHEET_COLUMNS)]
    assert ws.update_calls[0]["value_input_option"] == "RAW"


def test_writes_header_into_an_existing_empty_tab():
    ws = FakeWorksheet()
    ss = FakeSpreadsheet([ws])
    tracker_for(ss).seen_ids()
    assert ss.added == []
    assert ws.rows == [list(SHEET_COLUMNS)]


def test_mismatched_header_stops_before_writing():
    ws = FakeWorksheet(rows=[["date", "company", "source"]])
    t = tracker_for(FakeSpreadsheet([ws]))
    with pytest.raises(SheetError, match="first row"):
        t.append([row(1)])
    assert ws.append_calls == []


def test_extra_columns_after_the_known_ones_are_allowed():
    ws = FakeWorksheet(rows=[list(SHEET_COLUMNS) + ["my notes"]])
    t = tracker_for(FakeSpreadsheet([ws]))
    t.append([row(1)])
    assert len(ws.append_calls) == 1


# --- seen ids and append -------------------------------------------------------------


def test_seen_ids_reads_only_the_id_column():
    ws = FakeWorksheet(rows=[list(SHEET_COLUMNS), row(1).as_list(), row(2).as_list(), [""] * 13])
    assert tracker_for(FakeSpreadsheet([ws])).seen_ids() == {row(1).id, row(2).id}


def test_append_is_one_raw_batch_and_dedupes_next_time():
    ws = FakeWorksheet(rows=[list(SHEET_COLUMNS)])
    t = tracker_for(FakeSpreadsheet([ws]))
    t.append([row(1), row(2), row(3)])
    assert ws.append_calls == [{"n": 3, "value_input_option": "RAW", "table_range": "A1"}]
    assert ws.rows[1] == row(1).as_list()
    assert ws.rows[1][SHEET_COLUMNS.index("status")] == "new"
    assert t.seen_ids() == {row(1).id, row(2).id, row(3).id}


def test_formula_looking_titles_are_sent_as_raw_text():
    ws = FakeWorksheet(rows=[list(SHEET_COLUMNS)])
    tracker_for(FakeSpreadsheet([ws])).append([row(1, title='=IMPORTXML("x","y")')])
    assert ws.append_calls[0]["value_input_option"] == "RAW"
    assert ws.rows[1][SHEET_COLUMNS.index("title")] == '=IMPORTXML("x","y")'


def test_append_nothing_does_not_touch_the_sheet():
    opened = []
    t = SheetTracker(lambda: opened.append(1))
    t.append([])
    assert opened == []


def test_existing_rows_are_never_rewritten():
    first = row(1).as_list()
    first[SHEET_COLUMNS.index("status")] = "applied"
    ws = FakeWorksheet(rows=[list(SHEET_COLUMNS), first])
    tracker_for(FakeSpreadsheet([ws])).append([row(2)])
    assert ws.rows[1] == first
    assert ws.update_calls == []


def test_opens_the_spreadsheet_once():
    calls = []
    ws = FakeWorksheet(rows=[list(SHEET_COLUMNS)])
    ss = FakeSpreadsheet([ws])

    def factory():
        calls.append(1)
        return ss

    t = SheetTracker(factory)
    t.seen_ids()
    t.append([row(1)])
    assert calls == [1]


# --- credentials ---------------------------------------------------------------------


def test_bad_service_account_json_never_echoes_the_value():
    with pytest.raises(SheetError) as err:
        sheet.parse_service_account("not-json SECRETVALUE")
    assert "SECRETVALUE" not in str(err.value)
    with pytest.raises(SheetError, match="service-account"):
        sheet.parse_service_account('{"type": "authorized_user"}')


def test_from_settings_fails_fast_on_bad_json():
    class S:
        google_service_account_json = "{"
        sheet_id = "x"

    with pytest.raises(SheetError):
        SheetTracker.from_settings(S())


# --- setup-sheet ---------------------------------------------------------------------


def kinds(reqs):
    return [next(iter(r)) for r in reqs]


def test_setup_formats_the_tab():
    ss = FakeSpreadsheet()
    sheet.setup_sheet(ss)
    reqs = ss.batches[0]["requests"]
    ws = ss.worksheets["Jobs"]
    assert ws.rows == [list(SHEET_COLUMNS)]
    assert all(
        str(ws.id) in str(r) for r in reqs
    ), "every request targets the Jobs tab"

    frozen = reqs[0]["updateSheetProperties"]["properties"]["gridProperties"]["frozenRowCount"]
    assert frozen == 1
    hidden = [r for r in reqs if r.get("updateDimensionProperties", {}).get("properties", {}).get("hiddenByUser")]
    assert hidden[0]["updateDimensionProperties"]["range"]["startIndex"] == SHEET_COLUMNS.index("id")

    rules = [r["addConditionalFormatRule"]["rule"] for r in reqs if "addConditionalFormatRule" in r]
    assert [r["booleanRule"]["condition"]["type"] for r in rules] == ["NUMBER_GREATER_THAN_EQ", "NUMBER_BETWEEN"]
    assert all(r["ranges"][0]["startColumnIndex"] == SHEET_COLUMNS.index("score") for r in rules)

    dv = next(r["setDataValidation"] for r in reqs if "setDataValidation" in r)
    assert dv["range"]["startColumnIndex"] == SHEET_COLUMNS.index("status")
    assert [v["userEnteredValue"] for v in dv["rule"]["condition"]["values"]] == list(sheet.STATUS_CHOICES)

    wraps = [r["repeatCell"]["range"]["startColumnIndex"] for r in reqs if "wrapStrategy" in str(r)]
    assert sorted(wraps) == sorted(SHEET_COLUMNS.index(c) for c in ("reason", "draft note"))


def test_setup_is_idempotent_and_replaces_only_its_own_score_rules():
    score = SHEET_COLUMNS.index("score")
    old_score_rule = {"ranges": [{"sheetId": 111, "startRowIndex": 1, "startColumnIndex": score, "endColumnIndex": score + 1}]}
    owner_rule = {"ranges": [{"sheetId": 111, "startColumnIndex": 0, "endColumnIndex": 1}]}
    ws = FakeWorksheet(rows=[list(SHEET_COLUMNS)])
    ss = FakeSpreadsheet([ws], conditional_formats=[old_score_rule, owner_rule, old_score_rule])
    sheet.setup_sheet(ss)
    reqs = ss.batches[0]["requests"]
    deletes = [r["deleteConditionalFormatRule"]["index"] for r in reqs if "deleteConditionalFormatRule" in r]
    assert deletes == [2, 0]  # highest first; the owner's rule (index 1) stays
    assert kinds(reqs).count("addConditionalFormatRule") == 2
    assert ws.update_calls == []  # header already there: nothing rewritten


def test_setup_refuses_a_mismatched_header():
    ws = FakeWorksheet(rows=[["something", "else"]])
    ss = FakeSpreadsheet([ws])
    with pytest.raises(SheetError):
        sheet.setup_sheet(ss)
    assert ss.batches == []
