"""Safe read/write access to Vital_Sync_Marketing_Intelligence_Workflow.xlsx.

Failure-safety (workflow section 31): every write goes through SafeWrite,
which edits a TEMP COPY, validates it, backs up the current good workbook,
and only then atomically replaces the original. A crash or bad write mid-run
never corrupts the file a human might have open or the next run relies on.

Formula protection (workflow section 13): several sheets ship with
spreadsheet formulas pre-filled down every templated row (e.g. Market
Signals!O = Opportunity Score, Campaign Opportunities!T/U). This module
auto-detects those formula columns per sheet and refuses to write into them
— callers only ever set the raw scored inputs, and the workbook computes
the derived score itself, exactly as it does when a human edits it by hand.
"""

import shutil
import tempfile
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

import openpyxl

from config import REQUIRED_SHEETS, STATE_DIR, workbook_path

BACKUP_DIR = STATE_DIR / "backups"
BACKUP_DIR.mkdir(exist_ok=True)
MAX_BACKUPS = 10


class WorkbookNotFoundError(Exception):
    pass


class WorkbookValidationError(Exception):
    def __init__(self, errors):
        self.errors = errors
        super().__init__("; ".join(errors))


def locate() -> str:
    path = workbook_path()
    if not Path(path).exists():
        raise WorkbookNotFoundError(
            f"Workbook not found at {path}. Set VITAL_SYNC_MARKETING_WORKBOOK "
            "in .env if it has moved."
        )
    return path


def load(path: str = None, data_only: bool = False):
    return openpyxl.load_workbook(path or locate(), data_only=data_only)


def get_headers(ws) -> list:
    return [c.value for c in ws[1]]


def ensure_sheet(wb, name: str, headers: list):
    """Non-destructive: creates the sheet with a header row ONLY if it
    doesn't already exist. Never touches an existing sheet's structure —
    mirrors the additive-only philosophy used everywhere else (append
    rows, update in place, never restructure). Used for the "Product
    Demand Signals" tab (Product Intelligence integration, section 21):
    a genuinely new kind of record the original 10-sheet template didn't
    anticipate, added the same way sheets_io.create_tab() has always added
    new tabs to the older Vital Sync Google Sheet — additively, non-
    destructively. Returns the worksheet either way."""
    if name in wb.sheetnames:
        return wb[name]
    ws = wb.create_sheet(name)
    ws.append(headers)
    return ws


def header_index(ws) -> dict:
    """{header_name: 1-based column index}"""
    return {h: i + 1 for i, h in enumerate(get_headers(ws)) if h}


def formula_columns(ws, sample_rows: int = 20) -> set:
    """1-based column indices that contain spreadsheet formulas in this
    sheet's templated rows — never written to directly."""
    cols = set()
    for row in ws.iter_rows(min_row=2, max_row=min(ws.max_row, 2 + sample_rows)):
        for cell in row:
            if isinstance(cell.value, str) and cell.value.startswith("="):
                cols.add(cell.column)
    return cols


def _row_is_empty(ws, row_idx: int, formula_cols: set) -> bool:
    for cell in ws[row_idx]:
        if cell.column in formula_cols:
            continue
        if cell.value not in (None, ""):
            return False
    return True


def next_empty_row(ws, formula_cols: set = None) -> int:
    formula_cols = formula_cols if formula_cols is not None else formula_columns(ws)
    for row_idx in range(2, ws.max_row + 1):
        if _row_is_empty(ws, row_idx, formula_cols):
            return row_idx
    return ws.max_row + 1


def write_row(ws, row_idx: int, values: dict, formula_cols: set = None) -> None:
    """values: {header_name: value}. Silently skips any header that maps to
    a formula column — that cell keeps its existing formula."""
    formula_cols = formula_cols if formula_cols is not None else formula_columns(ws)
    idx = header_index(ws)
    for header, value in values.items():
        col = idx.get(header)
        if col is None or col in formula_cols:
            continue
        ws.cell(row=row_idx, column=col, value=value)


def iter_data_rows(ws, formula_cols: set = None):
    """Yields (row_idx, {header: value}) for every non-empty data row."""
    formula_cols = formula_cols if formula_cols is not None else formula_columns(ws)
    idx = header_index(ws)
    inv_idx = {v: k for k, v in idx.items()}
    for row_idx in range(2, ws.max_row + 1):
        if _row_is_empty(ws, row_idx, formula_cols):
            continue
        record = {}
        for cell in ws[row_idx]:
            header = inv_idx.get(cell.column)
            if header:
                record[header] = cell.value
        yield row_idx, record


def validate_file(path: str) -> tuple:
    """Opens the file fresh and checks it's structurally sound. Returns
    (ok, errors)."""
    errors = []
    try:
        wb = openpyxl.load_workbook(path)
    except Exception as exc:  # noqa: BLE001 - report, don't crash
        return False, [f"Workbook failed to open: {exc}"]
    for sheet_name in REQUIRED_SHEETS:
        if sheet_name not in wb.sheetnames:
            errors.append(f"Missing required sheet: {sheet_name}")
            continue
        ws = wb[sheet_name]
        headers = [h for h in get_headers(ws) if h]
        if not headers:
            errors.append(f"Sheet '{sheet_name}' has no header row")
    return (len(errors) == 0), errors


def _prune_backups(stem: str):
    # Namespaced by the source workbook's own filename stem — otherwise a
    # test run against an isolated copy (VITAL_SYNC_MARKETING_WORKBOOK
    # pointed elsewhere) pollutes and prunes the real workbook's backup
    # history, which happened during this integration's own testing
    # (2026-08-19) before this fix.
    backups = sorted(BACKUP_DIR.glob(f"{stem}_*.xlsx"))
    while len(backups) > MAX_BACKUPS:
        backups.pop(0).unlink(missing_ok=True)


@contextmanager
def safe_write():
    """Context manager yielding an editable openpyxl Workbook. On clean
    exit: validates the edited copy, backs up the current original, then
    atomically replaces it. On exception: discards the temp copy and leaves
    the original untouched.

    Usage:
        with workbook.safe_write() as wb:
            ws = wb["Market Signals"]
            ...edit ws...
        # workbook is now safely written back on disk
    """
    original_path = locate()
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".xlsx")
    import os

    os.close(tmp_fd)
    shutil.copy2(original_path, tmp_path)
    wb = openpyxl.load_workbook(tmp_path)
    try:
        yield wb
    except Exception:
        Path(tmp_path).unlink(missing_ok=True)
        raise
    else:
        wb.save(tmp_path)
        ok, errors = validate_file(tmp_path)
        if not ok:
            Path(tmp_path).unlink(missing_ok=True)
            raise WorkbookValidationError(errors)
        stem = Path(original_path).stem
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_path = BACKUP_DIR / f"{stem}_{timestamp}.xlsx"
        shutil.copy2(original_path, backup_path)
        _prune_backups(stem)
        shutil.move(tmp_path, original_path)
