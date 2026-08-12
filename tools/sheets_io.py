"""Read/write helpers for the Vital Sync Google Sheet (the source of truth).

Library functions are used by orchestrator tools (e.g. generate_content.py).
Also runnable directly for ad hoc inspection:

    python tools/sheets_io.py read "Search Bank"
"""

import argparse
import json
import string
import sys

from google_auth import get_credentials
from googleapiclient.discovery import build


def get_sheets_service():
    return build("sheets", "v4", credentials=get_credentials())


def col_letter(index: int) -> str:
    """0-based column index -> spreadsheet column letter (0 -> A, 25 -> Z, 26 -> AA)."""
    letters = ""
    index += 1
    while index > 0:
        index, remainder = divmod(index - 1, 26)
        letters = string.ascii_uppercase[remainder] + letters
    return letters


def list_tabs(sheet_id: str, service=None) -> list:
    service = service or get_sheets_service()
    meta = service.spreadsheets().get(spreadsheetId=sheet_id).execute()
    return [s["properties"]["title"] for s in meta.get("sheets", [])]


def create_tab(sheet_id: str, tab_name: str, headers: list = None, service=None):
    """Creates a new tab if it doesn't already exist, and writes a header
    row if given. Never touches a tab that already exists (no clearing, no
    overwriting) — safe to call on every run."""
    service = service or get_sheets_service()
    if tab_name in list_tabs(sheet_id, service=service):
        return False
    service.spreadsheets().batchUpdate(
        spreadsheetId=sheet_id,
        body={"requests": [{"addSheet": {"properties": {"title": tab_name}}}]},
    ).execute()
    if headers:
        service.spreadsheets().values().update(
            spreadsheetId=sheet_id,
            range=f"{tab_name}!1:1",
            valueInputOption="USER_ENTERED",
            body={"values": [headers]},
        ).execute()
    return True


def get_sheet_gid(sheet_id: str, tab_name: str, service=None) -> int:
    """Returns the internal numeric sheetId (gid) for a tab — needed for
    row-deletion requests, which address sheets by gid, not name."""
    service = service or get_sheets_service()
    meta = service.spreadsheets().get(spreadsheetId=sheet_id).execute()
    for s in meta.get("sheets", []):
        if s["properties"]["title"] == tab_name:
            return s["properties"]["sheetId"]
    raise ValueError(f"Tab '{tab_name}' not found")


def delete_rows(sheet_id: str, tab_name: str, row_numbers: list, service=None):
    """Deletes the given 1-indexed spreadsheet row numbers (as returned by
    read_tab's '_row') from a tab. Safe regardless of input order — rows are
    deleted highest-index-first within a single batchUpdate so earlier
    deletions never shift the index of a row still waiting to be deleted."""
    if not row_numbers:
        return
    service = service or get_sheets_service()
    gid = get_sheet_gid(sheet_id, tab_name, service=service)
    requests = [
        {"deleteDimension": {"range": {"sheetId": gid, "dimension": "ROWS", "startIndex": r - 1, "endIndex": r}}}
        for r in sorted(set(row_numbers), reverse=True)
    ]
    service.spreadsheets().batchUpdate(spreadsheetId=sheet_id, body={"requests": requests}).execute()


def get_headers(sheet_id: str, tab_name: str, service=None) -> list:
    service = service or get_sheets_service()
    result = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=sheet_id, range=f"{tab_name}!1:1")
        .execute()
    )
    return result.get("values", [[]])[0]


def ensure_headers(sheet_id: str, tab_name: str, required_headers: list, service=None) -> list:
    """Extends an existing tab's header row with any headers it's missing,
    appended in order after the current last column. Never touches an
    existing header cell, never reorders, never clears data — safe to call
    on every run. Returns the full, final header list."""
    service = service or get_sheets_service()
    existing = get_headers(sheet_id, tab_name, service=service)
    missing = [h for h in required_headers if h not in existing]
    if not missing:
        return existing
    start_col = col_letter(len(existing))
    end_col = col_letter(len(existing) + len(missing) - 1)
    service.spreadsheets().values().update(
        spreadsheetId=sheet_id,
        range=f"{tab_name}!{start_col}1:{end_col}1",
        valueInputOption="USER_ENTERED",
        body={"values": [missing]},
    ).execute()
    return existing + missing


def read_tab(sheet_id: str, tab_name: str, service=None) -> list:
    """Returns a list of dicts, one per data row. Each dict includes '_row'
    (the 1-indexed spreadsheet row number) for later targeted updates."""
    service = service or get_sheets_service()
    result = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=sheet_id, range=tab_name)
        .execute()
    )
    values = result.get("values", [])
    if not values:
        return []
    headers = values[0]
    rows = []
    for i, row in enumerate(values[1:], start=2):
        row = row + [""] * (len(headers) - len(row))
        rows.append({"_row": i, **dict(zip(headers, row))})
    return rows


def append_rows(sheet_id: str, tab_name: str, headers: list, rows: list, service=None):
    """rows: list of dicts keyed by header name. Missing keys become blank cells."""
    if not rows:
        return
    service = service or get_sheets_service()
    values = [[row.get(h, "") for h in headers] for row in rows]
    service.spreadsheets().values().append(
        spreadsheetId=sheet_id,
        range=tab_name,
        valueInputOption="USER_ENTERED",
        insertDataOption="INSERT_ROWS",
        body={"values": values},
    ).execute()


def batch_update_cells(sheet_id: str, updates: list, service=None):
    """updates: list of (a1_range_str, value) tuples."""
    if not updates:
        return
    service = service or get_sheets_service()
    data = [{"range": r, "values": [[v]]} for r, v in updates]
    service.spreadsheets().values().batchUpdate(
        spreadsheetId=sheet_id,
        body={"valueInputOption": "USER_ENTERED", "data": data},
    ).execute()


def _cli():
    parser = argparse.ArgumentParser(description="Ad hoc Vital Sync sheet inspection")
    sub = parser.add_subparsers(dest="command", required=True)

    read_p = sub.add_parser("read", help="Read a tab and print as JSON")
    read_p.add_argument("tab_name")
    read_p.add_argument("--sheet-id", default=None)

    append_p = sub.add_parser("append", help="Append rows (JSON array of objects) to a tab")
    append_p.add_argument("tab_name")
    append_p.add_argument("--file", required=True, help="Path to a JSON file containing an array of row objects")
    append_p.add_argument("--sheet-id", default=None)

    create_p = sub.add_parser("create-tab", help="Create a new tab with a header row if it doesn't already exist")
    create_p.add_argument("tab_name")
    create_p.add_argument("--headers", help="Comma-separated header row", default=None)
    create_p.add_argument("--sheet-id", default=None)

    args = parser.parse_args()

    import os

    from dotenv import load_dotenv

    load_dotenv()
    sheet_id = args.sheet_id or os.environ.get("GOOGLE_SHEET_ID")
    if not sheet_id:
        print("No sheet ID given and GOOGLE_SHEET_ID not set in .env", file=sys.stderr)
        sys.exit(1)

    if args.command == "read":
        rows = read_tab(sheet_id, args.tab_name)
        print(json.dumps(rows, indent=2))
    elif args.command == "append":
        with open(args.file) as f:
            rows = json.load(f)
        headers = get_headers(sheet_id, args.tab_name)
        append_rows(sheet_id, args.tab_name, headers, rows)
        print(f"Appended {len(rows)} row(s) to '{args.tab_name}'.")
    elif args.command == "create-tab":
        headers = [h.strip() for h in args.headers.split(",")] if args.headers else None
        created = create_tab(sheet_id, args.tab_name, headers)
        print(f"{'Created' if created else 'Already exists, left untouched:'} '{args.tab_name}'.")


if __name__ == "__main__":
    _cli()
