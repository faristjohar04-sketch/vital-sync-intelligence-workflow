"""Vital Sync — Weekly Cleanup

Archives fully-processed rows out of Content Pipeline and Search Bank into
dedicated archive tabs, then removes them from the working sheets. This is
the automated version of what the user was doing by hand daily: keeping the
working sheets small without ever actually losing history.

Nothing is ever deleted without first being copied to its archive tab, and
a row already present in the archive (matched by its own ID column) is
never re-appended, even if a previous run archived it but failed to delete
the source row afterward — the archive is the source of truth for "already
archived", the same pattern Workflow 03 uses against HeyGen Queue.

What gets archived (deliberately conservative — see workflows/weekly_cleanup.md):
- Content Pipeline: Status in {HeyGen Queued, Rewrite Required}. Anything
  still Draft / Ready for Video / Review Required is left alone, so a
  cleanup mid-week never sweeps up in-progress work.
- Search Bank: Status == Used. Unused/Processing are never touched (that's
  Workflow 01's territory); Rejected/Duplicate/Failed are left for a human
  to reset per Workflow 01's own documented lifecycle, not archived here.

Usage:
    python tools/weekly_cleanup.py --dry-run
    python tools/weekly_cleanup.py --live --trigger manual
"""

import argparse
import json
import os
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv

import gmail_send
import sheets_io

WORKFLOW_NAME = "Vital Sync Weekly Cleanup"

CONTENT_PIPELINE_TAB = "Content Pipeline"
CONTENT_PIPELINE_ARCHIVE_TAB = "Content Pipeline Archive"
SEARCH_BANK_TAB = "Search Bank"
SEARCH_BANK_ARCHIVE_TAB = "Search Bank Archive"
AUTOMATION_LOGS_TAB = "Automation Logs"

AUTOMATION_LOGS_HEADERS = ["Date", "Workflow", "Success", "Time", "Errors"]

CONTENT_PIPELINE_ID_FIELD = "ID"
SEARCH_BANK_ID_FIELD = "Search ID"

CONTENT_PIPELINE_ARCHIVE_STATUSES = {"heygen queued", "rewrite required"}
SEARCH_BANK_ARCHIVE_STATUSES = {"used"}

ARCHIVED_DATE_FIELD = "Archived Date"
STALE_RUN_TIMEOUT_MINUTES = 90
MAX_SHEETS_RETRIES = 2


def load_config():
    load_dotenv()
    sheet_id = os.environ.get("GOOGLE_SHEET_ID")
    email_to = os.environ.get("SUMMARY_EMAIL_TO")
    if not sheet_id:
        sys.exit("GOOGLE_SHEET_ID is not set in .env")
    return {"sheet_id": sheet_id, "email_to": email_to}


def with_sheets_retry(fn, *args, **kwargs):
    last_err = None
    for attempt in range(MAX_SHEETS_RETRIES + 1):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            last_err = e
            if attempt < MAX_SHEETS_RETRIES:
                time.sleep(2 * (attempt + 1))
                continue
            raise
    raise last_err  # pragma: no cover


def norm(s):
    return (s or "").strip().lower()


def parse_log_entry(row):
    try:
        payload = json.loads(row.get("Errors") or "{}")
        return payload if isinstance(payload, dict) else {}
    except json.JSONDecodeError:
        return {}


def write_log(sheet_id, service, run_id, phase, trigger, extra=None):
    now_iso = datetime.now(timezone.utc).isoformat()
    payload = {"run_id": run_id, "phase": phase, "trigger": trigger}
    payload.update(extra or {})
    row = {
        "Date": now_iso,
        "Workflow": WORKFLOW_NAME,
        "Success": 1 if phase == "completed" and not (extra or {}).get("error_count") else (
            0 if phase == "completed" else ""
        ),
        "Time": now_iso,
        "Errors": json.dumps(payload),
    }
    with_sheets_retry(
        sheets_io.append_rows, sheet_id, AUTOMATION_LOGS_TAB, AUTOMATION_LOGS_HEADERS, [row], service=service
    )
    return now_iso


def find_unresolved_started(logs, workflow_name):
    started = {}
    resolved = set()
    for row in logs:
        if row.get("Workflow") != workflow_name:
            continue
        payload = parse_log_entry(row)
        run_id, phase = payload.get("run_id"), payload.get("phase")
        if not run_id or not phase:
            continue
        if phase == "started":
            started[run_id] = row.get("Date")
        elif phase in ("completed", "skipped"):
            resolved.add(run_id)

    now = datetime.now(timezone.utc)
    for run_id, started_at in started.items():
        if run_id in resolved:
            continue
        try:
            started_dt = datetime.fromisoformat(started_at)
        except (TypeError, ValueError):
            continue
        if now - started_dt < timedelta(minutes=STALE_RUN_TIMEOUT_MINUTES):
            return run_id, started_at
    return None, None


def check_self_overlap(sheet_id, service):
    logs = with_sheets_retry(sheets_io.read_tab, sheet_id, AUTOMATION_LOGS_TAB, service=service)
    run_id, _ = find_unresolved_started(logs, WORKFLOW_NAME)
    return run_id


def select_archive_candidates(rows, eligible_statuses):
    return [r for r in rows if norm(r.get("Status")) in eligible_statuses]


def archive_and_remove(sheet_id, service, source_tab, archive_tab, id_field, candidates, dry_run=False):
    """Archives `candidates` (rows already selected by status) out of
    source_tab into archive_tab, then deletes them from source_tab. Rows
    whose ID already exists in the archive are not re-appended (idempotent
    against a prior partial failure) but are still removed from the source.
    Returns (archived_count, already_archived_count, error_or_None)."""
    if not candidates:
        return 0, 0, None

    if dry_run:
        return len(candidates), 0, None

    try:
        source_headers = with_sheets_retry(sheets_io.get_headers, sheet_id, source_tab, service=service)
        with_sheets_retry(
            sheets_io.create_tab, sheet_id, archive_tab, source_headers + [ARCHIVED_DATE_FIELD], service=service
        )
        archive_headers = with_sheets_retry(sheets_io.get_headers, sheet_id, archive_tab, service=service)
        existing_archive_rows = with_sheets_retry(sheets_io.read_tab, sheet_id, archive_tab, service=service)
        already_archived_ids = {
            (r.get(id_field) or "").strip() for r in existing_archive_rows if (r.get(id_field) or "").strip()
        }

        to_append, to_delete_only, to_append_and_delete = [], [], []
        now_iso = datetime.now(timezone.utc).isoformat()
        for row in candidates:
            row_id = (row.get(id_field) or "").strip()
            if row_id and row_id in already_archived_ids:
                to_delete_only.append(row)
            else:
                package = {h: row.get(h, "") for h in source_headers}
                package[ARCHIVED_DATE_FIELD] = now_iso
                to_append.append(package)
                to_append_and_delete.append(row)

        if to_append:
            with_sheets_retry(sheets_io.append_rows, sheet_id, archive_tab, archive_headers, to_append, service=service)

        rows_to_delete = to_append_and_delete + to_delete_only
        if rows_to_delete:
            with_sheets_retry(
                sheets_io.delete_rows, sheet_id, source_tab, [r["_row"] for r in rows_to_delete], service=service
            )

        return len(to_append), len(to_delete_only), None

    except Exception as e:
        return 0, 0, str(e)


def run(dry_run: bool, send_email: bool, trigger: str):
    cfg = load_config()
    sheet_id = cfg["sheet_id"]
    service = sheets_io.get_sheets_service()

    if dry_run:
        cp_rows = with_sheets_retry(sheets_io.read_tab, sheet_id, CONTENT_PIPELINE_TAB, service=service)
        cp_candidates = select_archive_candidates(cp_rows, CONTENT_PIPELINE_ARCHIVE_STATUSES)
        sb_rows = with_sheets_retry(sheets_io.read_tab, sheet_id, SEARCH_BANK_TAB, service=service)
        sb_candidates = select_archive_candidates(sb_rows, SEARCH_BANK_ARCHIVE_STATUSES)

        print(f"Content Pipeline: {len(cp_candidates)} row(s) eligible for archive "
              f"(Status in {sorted(CONTENT_PIPELINE_ARCHIVE_STATUSES)}):")
        for r in cp_candidates:
            print(f"  - [{r['_row']}] {r.get('ID')} :: {r.get('Status')}")

        print(f"\nSearch Bank: {len(sb_candidates)} row(s) eligible for archive "
              f"(Status in {sorted(SEARCH_BANK_ARCHIVE_STATUSES)}):")
        for r in sb_candidates[:20]:
            print(f"  - [{r['_row']}] {r.get('Search ID') or r.get('Search Query')} :: {r.get('Status')}")
        if len(sb_candidates) > 20:
            print(f"  ... and {len(sb_candidates) - 20} more")

        print("\n--dry-run: stopping before any sheet writes or email.")
        return

    run_id = uuid.uuid4().hex[:12]

    blocking_run_id = check_self_overlap(sheet_id, service)
    if blocking_run_id:
        reason = f"previous {WORKFLOW_NAME} run '{blocking_run_id}' still active (started < {STALE_RUN_TIMEOUT_MINUTES}m ago)"
        write_log(sheet_id, service, run_id, "skipped", trigger, {"reason": reason})
        print(f"SKIPPED: {reason}")
        return

    write_log(sheet_id, service, run_id, "started", trigger)
    start_time = datetime.now(timezone.utc)
    errors = []

    cp_rows = with_sheets_retry(sheets_io.read_tab, sheet_id, CONTENT_PIPELINE_TAB, service=service)
    cp_candidates = select_archive_candidates(cp_rows, CONTENT_PIPELINE_ARCHIVE_STATUSES)
    cp_archived, cp_already, cp_error = archive_and_remove(
        sheet_id, service, CONTENT_PIPELINE_TAB, CONTENT_PIPELINE_ARCHIVE_TAB, CONTENT_PIPELINE_ID_FIELD, cp_candidates
    )
    if cp_error:
        errors.append({"sheet": "Content Pipeline", "error": cp_error})
        print(f"  ERROR archiving Content Pipeline: {cp_error}")
    else:
        print(f"Content Pipeline: archived {cp_archived}, already-archived cleanup {cp_already} "
              f"(found {len(cp_candidates)} eligible).")

    sb_rows = with_sheets_retry(sheets_io.read_tab, sheet_id, SEARCH_BANK_TAB, service=service)
    sb_candidates = select_archive_candidates(sb_rows, SEARCH_BANK_ARCHIVE_STATUSES)
    sb_archived, sb_already, sb_error = archive_and_remove(
        sheet_id, service, SEARCH_BANK_TAB, SEARCH_BANK_ARCHIVE_TAB, SEARCH_BANK_ID_FIELD, sb_candidates
    )
    if sb_error:
        errors.append({"sheet": "Search Bank", "error": sb_error})
        print(f"  ERROR archiving Search Bank: {sb_error}")
    else:
        print(f"Search Bank: archived {sb_archived}, already-archived cleanup {sb_already} "
              f"(found {len(sb_candidates)} eligible).")

    duration = (datetime.now(timezone.utc) - start_time).total_seconds()
    summary = {
        "content_pipeline_found": len(cp_candidates),
        "content_pipeline_archived": cp_archived,
        "search_bank_found": len(sb_candidates),
        "search_bank_archived": sb_archived,
        "duration_seconds": duration,
        "error_count": len(errors),
        "errors": errors,
    }
    write_log(sheet_id, service, run_id, "completed", trigger, summary)

    print(f"\nDone. Content Pipeline archived {cp_archived}/{len(cp_candidates)}, "
          f"Search Bank archived {sb_archived}/{len(sb_candidates)}, errors {len(errors)}.")

    if send_email and cfg["email_to"]:
        body_lines = [
            f"Workflow:\n{WORKFLOW_NAME}",
            "",
            f"Run ID:\n{run_id}",
            "",
            f"Content Pipeline — eligible: {len(cp_candidates)}, archived: {cp_archived}",
            f"Search Bank — eligible: {len(sb_candidates)}, archived: {sb_archived}",
            "",
            f"Duration: {duration:.1f}s",
            "",
            "Errors:",
        ]
        body_lines += [f"  - {e['sheet']}: {e['error']}" for e in errors] if errors else ["  (none)"]
        gmail_send.send_email(
            to=cfg["email_to"],
            subject=f"Vital Sync Weekly Cleanup Report — {datetime.now().strftime('%Y-%m-%d')}",
            body_text="\n".join(body_lines),
        )
        print(f"Summary email sent to {cfg['email_to']}.")


def _cli():
    parser = argparse.ArgumentParser(description="Vital Sync Weekly Cleanup: archive fully-processed rows")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="Show what would be archived, no writes or email")
    mode.add_argument("--live", action="store_true", help="Full run: archives, deletes, emails")
    parser.add_argument("--trigger", choices=["manual", "scheduled"], default="manual")
    parser.add_argument("--no-email", action="store_true")
    args = parser.parse_args()

    run(dry_run=args.dry_run, send_email=not args.no_email, trigger=args.trigger)


if __name__ == "__main__":
    _cli()
