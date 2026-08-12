"""Vital Sync — Workflow 03: HeyGen Production Queue

Deterministically orchestrates one run of the queue-builder: reads Content
Pipeline + Avatar Library + HeyGen Queue + Automation Logs fresh from the
Google Sheet every run (no local state, no memory of past executions),
selects rows with Approval = "Approved" AND Status = "Ready for Video",
matches each to a coach avatar, validates the production package, appends
one row per item to HeyGen Queue, flips the matching Content Pipeline row to
"HeyGen Queued", logs the run, and emails a summary.

This tool NEVER rewrites Script/Hook/CTA/Caption, never calls the HeyGen
API, never generates a video, never performs quality control, and never
publishes anything. It only packages already-approved content for a human
(or a future Workflow) to hand to HeyGen.

Usage:
    python tools/build_heygen_queue.py --dry-run
    python tools/build_heygen_queue.py --live --trigger manual
    python tools/build_heygen_queue.py --live --no-email
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

WORKFLOW_NAME = "Vital Sync HeyGen Production Queue"

CONTENT_PIPELINE_TAB = "Content Pipeline"
AVATAR_LIBRARY_TAB = "Avatar Library"
HEYGEN_QUEUE_TAB = "HeyGen Queue"
AUTOMATION_LOGS_TAB = "Automation Logs"

AUTOMATION_LOGS_HEADERS = ["Date", "Workflow", "Success", "Time", "Errors"]

HEYGEN_QUEUE_HEADERS = [
    "Queue ID", "Content ID", "Brand", "Content Pillar", "Coach", "Hook",
    "Script", "CTA", "Caption", "On-Screen Text", "Hashtags", "Promotion",
    "Avatar Name", "Avatar ID", "Voice Name", "Voice ID", "Video Orientation",
    "Target Duration", "Delivery Style", "Visual Style", "Queue Status",
    "Date Queued", "Source Row Number", "Video URL", "Notes",
]

APPROVAL_INPUT = "Approved"
STATUS_INPUT = "Ready for Video"
STATUS_QUEUED = "HeyGen Queued"

# Statuses that must never be re-selected. Redundant with the exact-match
# filter above (only STATUS_INPUT rows are selected) but kept explicit per
# the workflow spec, and as a guard if Status naming ever drifts.
SKIP_STATUSES = {
    "heygen queued", "video processing", "video complete", "published",
    "rejected", "needs review",
}

# Core fields Step 1 of the spec requires non-empty before a row even
# becomes a "candidate". Rows failing this are excluded from "approved items
# found" entirely (not logged as a per-row result) — same as the spec's
# Step 1 selection gate.
REQUIRED_SELECTION_FIELDS = ["ID", "Script", "Hook", "Content Pillar", "Avatar"]

# Recognized coach types (Step 2). "Avatar" in Content Pipeline is already
# written by Workflow 01 as one of these coach-type strings directly (not a
# bare pillar keyword) — confirmed against live data. The pillar-keyword
# mapping below is kept as a fallback in case a future row ever stores a
# bare pillar word instead. Discipline Coach was deliberately dropped — the
# spec's own allowed-pillar list (below) never included "Discipline", so it
# was a dead path that could resolve an avatar but never pass validation.
COACH_TYPES = ["Fitness Coach", "Nutrition Coach", "Recovery Specialist"]
PILLAR_KEYWORD_TO_COACH = {
    "fitness": "Fitness Coach",
    "nutrition": "Nutrition Coach",
    "recovery": "Recovery Specialist",
}
COACH_TO_PILLAR = {
    "Fitness Coach": "Fitness",
    "Nutrition Coach": "Nutrition",
    "Recovery Specialist": "Recovery",
}
# Spec's allowed Content Pillar list for the HeyGen package (Step 4). See
# workflows/03_heygen_queue.md "Content Pillar resolution" for why this tool
# derives the package's Content Pillar from Avatar/coach rather than from
# Content Pipeline's own (much more granular) Content Pillar column.
ALLOWED_PILLARS = {"Fitness", "Nutrition", "Recovery"}

VIDEO_ORIENTATION = "9:16"
TARGET_DURATION = "15-30 seconds"
DELIVERY_STYLE = (
    "Natural, conversational, confident, active hand gestures, direct eye "
    "contact, arms not folded"
)
VISUAL_STYLE = (
    "Premium short-form fitness education, clean modern background, "
    "Vital Sync aesthetic"
)

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
        "Success": 1 if phase == "completed" and (extra or {}).get("items_queued", 0) > 0 else (
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


def select_candidates(content_pipeline_rows):
    """Step 1: Approved + Ready for Video, with the five core fields
    non-empty. Rows failing the non-empty check are excluded entirely (not
    logged as a result), per spec."""
    candidates = []
    for r in content_pipeline_rows:
        if norm(r.get("Approval")) != norm(APPROVAL_INPUT):
            continue
        if norm(r.get("Status")) != norm(STATUS_INPUT):
            continue
        if norm(r.get("Status")) in SKIP_STATUSES:
            continue
        if any(not (r.get(f) or "").strip() for f in REQUIRED_SELECTION_FIELDS):
            continue
        candidates.append(r)
    return candidates


def build_avatar_index(avatar_rows):
    """Coach Type (normalized) -> avatar library row."""
    index = {}
    for r in avatar_rows:
        coach_type = (r.get("Coach Type") or "").strip()
        if coach_type:
            index[coach_type.lower()] = r
    return index


def resolve_coach(avatar_field):
    val = (avatar_field or "").strip()
    val_lower = val.lower()
    for coach in COACH_TYPES:
        if val_lower == coach.lower():
            return coach
    if val_lower in PILLAR_KEYWORD_TO_COACH:
        return PILLAR_KEYWORD_TO_COACH[val_lower]
    return None


def existing_queue_content_ids(queue_rows):
    return {(r.get("Content ID") or "").strip() for r in queue_rows if (r.get("Content ID") or "").strip()}


def validate_package(row, coach, pillar, avatar_row):
    """Step 4. Returns (ok, missing_field_description)."""
    if not (row.get("ID") or "").strip():
        return False, "Content ID"
    if not (row.get("Hook") or "").strip():
        return False, "Hook"
    if not (row.get("Script") or "").strip():
        return False, "Script"
    # CTA is allowed to be intentionally blank — never blocks.
    if not (row.get("Caption") or "").strip():
        return False, "Caption"
    if not (row.get("On-Screen Text") or "").strip():
        return False, "On-Screen Text"
    if not (row.get("Hashtags") or "").strip():
        return False, "Hashtags"
    if pillar not in ALLOWED_PILLARS:
        return False, f"Content Pillar (resolved '{pillar}' not in {sorted(ALLOWED_PILLARS)})"
    if coach not in COACH_TYPES:
        return False, "Coach"
    promotion = (row.get("Promotion") or "").strip().lower()
    if promotion not in ("yes", "no"):
        return False, "Promotion (must be Yes or No)"
    return True, None


def make_queue_id(run_token, item_number):
    date_str = datetime.now().strftime("%Y%m%d")
    return f"HG-VS-{date_str}-{run_token}-{item_number:03d}"


def build_package(row, queue_id, coach, pillar, avatar_row, now_iso):
    avatar_row = avatar_row or {}
    return {
        "Queue ID": queue_id,
        "Content ID": row.get("ID", ""),
        "Brand": "Vital Sync",
        "Content Pillar": pillar,
        "Coach": coach,
        "Hook": row.get("Hook", ""),
        "Script": row.get("Script", ""),
        "CTA": row.get("CTA", ""),
        "Caption": row.get("Caption", ""),
        "On-Screen Text": row.get("On-Screen Text", ""),
        "Hashtags": row.get("Hashtags", ""),
        "Promotion": row.get("Promotion", ""),
        "Avatar Name": avatar_row.get("Avatar Name", ""),
        "Avatar ID": avatar_row.get("Avatar ID", ""),
        "Voice Name": avatar_row.get("Voice Name", ""),
        "Voice ID": avatar_row.get("Voice ID", ""),
        "Video Orientation": VIDEO_ORIENTATION,
        "Target Duration": TARGET_DURATION,
        "Delivery Style": avatar_row.get("Delivery Style") or DELIVERY_STYLE,
        "Visual Style": VISUAL_STYLE,
        "Queue Status": "Ready",
        "Date Queued": now_iso,
        "Source Row Number": row.get("_row", ""),
        "Video URL": "",
        "Notes": "",
    }


def run(dry_run: bool, send_email: bool, trigger: str):
    cfg = load_config()
    sheet_id = cfg["sheet_id"]
    service = sheets_io.get_sheets_service()

    if dry_run:
        rows = with_sheets_retry(sheets_io.read_tab, sheet_id, CONTENT_PIPELINE_TAB, service=service)
        candidates = select_candidates(rows)
        queue_rows = with_sheets_retry(sheets_io.read_tab, sheet_id, HEYGEN_QUEUE_TAB, service=service)
        already_queued_ids = existing_queue_content_ids(queue_rows)
        print(f"Selected {len(candidates)} candidate row(s) with Approval='{APPROVAL_INPUT}' "
              f"AND Status='{STATUS_INPUT}':")
        for r in candidates:
            tag = " (already queued)" if (r.get("ID") or "").strip() in already_queued_ids else ""
            print(f"  - [{r['_row']}] {r.get('ID')} :: {r.get('Topic')}{tag}")
        print("\n--dry-run: stopping before any sheet writes or email.")
        return

    run_id = uuid.uuid4().hex[:12]
    run_token = uuid.uuid4().hex[:5]

    blocking_run_id = check_self_overlap(sheet_id, service)
    if blocking_run_id:
        reason = f"previous {WORKFLOW_NAME} run '{blocking_run_id}' still active (started < {STALE_RUN_TIMEOUT_MINUTES}m ago)"
        write_log(sheet_id, service, run_id, "skipped", trigger, {"reason": reason})
        print(f"SKIPPED: {reason}")
        return

    write_log(sheet_id, service, run_id, "started", trigger)
    start_time = datetime.now(timezone.utc)

    try:
        headers = with_sheets_retry(sheets_io.get_headers, sheet_id, CONTENT_PIPELINE_TAB, service=service)
        status_col_letter = sheets_io.col_letter(headers.index("Status"))
        optional_write_cols = {
            h: sheets_io.col_letter(headers.index(h))
            for h in ("HeyGen Queue ID", "HeyGen Queued Date", "Automation Result")
            if h in headers
        }

        all_rows = with_sheets_retry(sheets_io.read_tab, sheet_id, CONTENT_PIPELINE_TAB, service=service)
        candidates = select_candidates(all_rows)
        print(f"Found {len(candidates)} candidate row(s).")

        avatar_rows = with_sheets_retry(sheets_io.read_tab, sheet_id, AVATAR_LIBRARY_TAB, service=service)
        avatar_index = build_avatar_index(avatar_rows)

        queue_rows = with_sheets_retry(sheets_io.read_tab, sheet_id, HEYGEN_QUEUE_TAB, service=service)
        already_queued_ids = existing_queue_content_ids(queue_rows)

        if not candidates:
            duration = (datetime.now(timezone.utc) - start_time).total_seconds()
            summary = {
                "approved_items_found": 0, "items_queued": 0, "already_queued": 0,
                "needs_avatar_review": 0, "skipped": 0, "failed": 0,
                "duration_seconds": duration, "errors": [],
            }
            write_log(sheet_id, service, run_id, "completed", trigger, summary)
            print("No approved/ready candidates. Run complete (no-op).")
            if send_email and cfg["email_to"]:
                gmail_send.send_email(
                    to=cfg["email_to"],
                    subject=f"Vital Sync HeyGen Queue Report — {datetime.now().strftime('%Y-%m-%d')}",
                    body_text=(
                        "No approved Vital Sync scripts were ready for the HeyGen "
                        "queue. No existing data was changed."
                    ),
                )
                print(f"Summary email sent to {cfg['email_to']}.")
            return

        results = []
        queue_ids_added = []
        item_number = 0
        items_queued = already_queued = needs_avatar_review = skipped = failed = 0

        for row in candidates:
            content_id = (row.get("ID") or "").strip()
            topic = row.get("Topic", "")
            result_entry = {"content_id": content_id, "topic": topic, "coach": None,
                             "result": None, "queue_id": None, "error": None}

            # Step 3 — dedup against existing HeyGen Queue (Content ID key).
            if content_id in already_queued_ids:
                result_entry["result"] = "Already Queued"
                already_queued += 1
                results.append(result_entry)
                print(f"  Already Queued: {content_id}")
                continue

            # Step 2 — avatar/coach match.
            coach = resolve_coach(row.get("Avatar"))
            avatar_row = avatar_index.get(coach.lower()) if coach else None
            result_entry["coach"] = coach
            if not coach or not avatar_row:
                result_entry["result"] = "Needs Avatar Review"
                result_entry["error"] = (
                    f"No Avatar Library match for Avatar='{row.get('Avatar')}'"
                    if coach else f"Unrecognized Avatar value '{row.get('Avatar')}'"
                )
                needs_avatar_review += 1
                results.append(result_entry)
                print(f"  Needs Avatar Review: {content_id} ({result_entry['error']})")
                continue

            pillar = COACH_TO_PILLAR.get(coach, "")

            # Step 4 — validate production package.
            ok, missing = validate_package(row, coach, pillar, avatar_row)
            if not ok:
                result_entry["result"] = "Skipped — Missing Production Field"
                result_entry["error"] = f"Missing/invalid field: {missing}"
                skipped += 1
                results.append(result_entry)
                print(f"  Skipped (missing field): {content_id} -> {missing}")
                continue

            # Step 5/8 — build package + unique Queue ID.
            item_number += 1
            queue_id = make_queue_id(run_token, item_number)
            now_iso = datetime.now(timezone.utc).isoformat()
            package = build_package(row, queue_id, coach, pillar, avatar_row, now_iso)

            # Step 6 — append to HeyGen Queue.
            try:
                with_sheets_retry(
                    sheets_io.append_rows, sheet_id, HEYGEN_QUEUE_TAB, HEYGEN_QUEUE_HEADERS, [package], service=service
                )
            except Exception as e:
                result_entry["result"] = "Queue Append Failed"
                result_entry["error"] = str(e)
                failed += 1
                results.append(result_entry)
                print(f"  ERROR appending {content_id}: {e}")
                continue

            already_queued_ids.add(content_id)  # guards duplicate appends within this same run

            # Step 7 — update Content Pipeline (only after successful append).
            cell_updates = [(f"{CONTENT_PIPELINE_TAB}!{status_col_letter}{row['_row']}", STATUS_QUEUED)]
            if "HeyGen Queue ID" in optional_write_cols:
                cell_updates.append((f"{CONTENT_PIPELINE_TAB}!{optional_write_cols['HeyGen Queue ID']}{row['_row']}", queue_id))
            if "HeyGen Queued Date" in optional_write_cols:
                cell_updates.append((f"{CONTENT_PIPELINE_TAB}!{optional_write_cols['HeyGen Queued Date']}{row['_row']}", now_iso))
            if "Automation Result" in optional_write_cols:
                cell_updates.append((f"{CONTENT_PIPELINE_TAB}!{optional_write_cols['Automation Result']}{row['_row']}", "Success"))
            try:
                with_sheets_retry(sheets_io.batch_update_cells, sheet_id, cell_updates, service=service)
            except Exception as e:
                # The queue row is already the source of truth for dedup, so a
                # failure here doesn't risk a duplicate on the next run — it
                # just leaves the Content Pipeline Status stale. Still counts
                # as Queued; logged as a warning, not a per-item failure.
                result_entry["error"] = f"Queued, but Content Pipeline update failed: {e}"
                print(f"  WARNING: {content_id} queued but pipeline row update failed: {e}")

            result_entry["result"] = "Queued"
            result_entry["queue_id"] = queue_id
            queue_ids_added.append(queue_id)
            items_queued += 1
            results.append(result_entry)
            print(f"  Queued: {content_id} -> {queue_id}")

        duration = (datetime.now(timezone.utc) - start_time).total_seconds()
        summary = {
            "approved_items_found": len(candidates),
            "items_queued": items_queued,
            "already_queued": already_queued,
            "needs_avatar_review": needs_avatar_review,
            "skipped": skipped,
            "failed": failed,
            "duration_seconds": duration,
            "queue_ids": queue_ids_added,
            "results": results[:50],
        }
        write_log(sheet_id, service, run_id, "completed", trigger, summary)

        print(f"\nDone. Found {len(candidates)}, queued {items_queued}, already queued {already_queued}, "
              f"needs avatar review {needs_avatar_review}, skipped {skipped}, failed {failed}.")

        if send_email and cfg["email_to"]:
            body_lines = [
                f"Workflow:\n{WORKFLOW_NAME}",
                "",
                f"Run ID:\n{run_id}",
                "",
                f"Approved items found:\n{len(candidates)}",
                "",
                f"Added to HeyGen Queue:\n{items_queued}",
                "",
                f"Already queued:\n{already_queued}",
                "",
                f"Needs avatar review:\n{needs_avatar_review}",
                "",
                f"Skipped:\n{skipped}",
                "",
                f"Failed:\n{failed}",
                "",
                "Queue IDs:",
            ]
            body_lines += [f"  - {qid}" for qid in queue_ids_added] if queue_ids_added else ["  (none)"]
            body_lines += ["", "Errors:"]
            error_lines = [f"  - {r['content_id']}: {r['error']}" for r in results if r.get("error")]
            body_lines += error_lines if error_lines else ["  (none)"]

            gmail_send.send_email(
                to=cfg["email_to"],
                subject=f"Vital Sync HeyGen Queue Report — {datetime.now().strftime('%Y-%m-%d')}",
                body_text="\n".join(body_lines),
            )
            print(f"Summary email sent to {cfg['email_to']}.")

    except Exception as e:
        write_log(sheet_id, service, run_id, "completed", trigger, {
            "approved_items_found": 0, "items_queued": 0, "already_queued": 0,
            "needs_avatar_review": 0, "skipped": 0, "failed": 1,
            "errors": [{"error": f"run crashed: {e}"}],
        })
        raise


def _cli():
    parser = argparse.ArgumentParser(description="Vital Sync Workflow 03: HeyGen Production Queue")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="Select candidates only, no writes or email")
    mode.add_argument("--live", action="store_true", help="Full run: validates, appends, updates, emails")
    parser.add_argument("--trigger", choices=["manual"], default="manual",
                         help="Workflow 03 is manual-trigger only per spec — no 'scheduled' option")
    parser.add_argument("--no-email", action="store_true")
    args = parser.parse_args()

    run(dry_run=args.dry_run, send_email=not args.no_email, trigger=args.trigger)


if __name__ == "__main__":
    _cli()
