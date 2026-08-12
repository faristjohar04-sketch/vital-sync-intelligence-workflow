"""Vital Sync — Workflow 01: Script Factory

Deterministically orchestrates one run of the content generation pipeline:
reads Brand Guidelines + Search Bank + Content Pipeline + Automation Logs
fresh from the Google Sheet every run (no local state, no memory of past
executions), picks Unused topics, reserves them, generates structured
content via OpenAI, validates it, appends valid rows to Content Pipeline,
resolves each reserved topic to Used/Duplicate/Failed, logs the run, and
emails a summary.

Status lifecycle for Search Bank rows: Unused -> Processing -> Used
                                                            -> Duplicate
                                                            -> Failed
Topics marked Used, Processing, Duplicate, or Failed are never re-selected.

Overlapping runs are prevented via paired "started"/"completed" markers in
Automation Logs (the sheet is the only source of truth — no lock files).
A run whose "started" marker is older than STALE_RUN_TIMEOUT_MINUTES with
no matching "completed" marker is treated as crashed, not active, and any
Search Bank rows left in Processing are self-healed back to Unused.

Scheduled runs (--trigger scheduled) auto-escalate their batch size from
SCRIPT_FACTORY_BATCH_SIZE to SCRIPT_FACTORY_ESCALATED_BATCH_SIZE once the
most recent N consecutive scheduled runs were clean (see
ESCALATION_STREAK_THRESHOLD) — computed fresh from Automation Logs history
each run, never from persisted state. Manual runs are unaffected and never
count toward or reset that streak.

This tool makes paid OpenAI API calls. Do not run --live without the
user's go-ahead for the run. Use --dry-run first to verify sheet
connectivity and topic selection at no cost.

Usage:
    python tools/generate_content.py --dry-run
    python tools/generate_content.py --live --trigger manual
    python tools/generate_content.py --live --trigger scheduled
    python tools/generate_content.py --live --batch-size 3 --no-email
"""

import argparse
import json
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from openai import OpenAI

import gmail_send
import sheets_io

WORKFLOW_NAME = "Vital Sync Script Factory"

CONTENT_PIPELINE_TAB = "Content Pipeline"
SEARCH_BANK_TAB = "Search Bank"
BRAND_GUIDELINES_TAB = "Brand Guidelines"
AUTOMATION_LOGS_TAB = "Automation Logs"

CONTENT_PIPELINE_HEADERS = [
    "ID", "Brand", "Status", "Priority", "Content Pillar", "Content Type",
    "Search Query", "Topic", "Hook", "Problem", "Cause", "Solution", "CTA",
    "Script", "Caption", "On-Screen Text", "Hashtags", "Promotion", "Avatar",
    "Date Generated", "Approval", "Quality Score", "Hook Score", "CTA Score",
    "Grammar Score", "Readability Score", "Brand Voice Score", "Review Notes",
    "Date Checked", "Platform URL", "Published Date",
]
# Schema updated 2026-07-30 to match a manual restructure of the live sheet:
# "Platform", "Video URL", "Published" were removed; "Platform URL" and
# "Published Date" were added (populated by later workflows, left blank
# here). This list must always match the live Content Pipeline column
# order exactly — append_rows() writes by position, not by header lookup.

AUTOMATION_LOGS_HEADERS = ["Date", "Workflow", "Success", "Time", "Errors"]

REQUIRED_GENERATED_FIELDS = [
    "content_pillar", "content_type", "hook", "problem", "cause", "solution",
    "cta", "script", "caption", "on_screen_text", "hashtags", "promotion",
    "avatar",
]

BANNED_PHRASES = [
    "click now", "buy now", "you won't believe", "guaranteed results",
    "miracle", "limited time only", "act now",
]

# Search Bank status lifecycle
STATUS_UNUSED = "Unused"
STATUS_PROCESSING = "Processing"
STATUS_USED = "Used"
STATUS_DUPLICATE = "Duplicate"
STATUS_FAILED = "Failed"

MAX_RETRIES_PER_ITEM = 1
DEDUP_CONTEXT_SIZE = 50
STALE_RUN_TIMEOUT_MINUTES = 90
ESCALATION_STREAK_THRESHOLD = 3


def load_config():
    load_dotenv()
    sheet_id = os.environ.get("GOOGLE_SHEET_ID")
    openai_key = os.environ.get("OPENAI_API_KEY")
    model = os.environ.get("OPENAI_MODEL", "gpt-4o")
    email_to = os.environ.get("SUMMARY_EMAIL_TO")
    base_batch_size = int(os.environ.get("SCRIPT_FACTORY_BATCH_SIZE", "10"))
    escalated_batch_size = int(os.environ.get("SCRIPT_FACTORY_ESCALATED_BATCH_SIZE", "100"))
    if not sheet_id:
        sys.exit("GOOGLE_SHEET_ID is not set in .env")
    return {
        "sheet_id": sheet_id,
        "openai_key": openai_key,
        "model": model,
        "email_to": email_to,
        "base_batch_size": base_batch_size,
        "escalated_batch_size": escalated_batch_size,
    }


def next_content_id(existing_rows):
    import re

    max_n = 0
    for row in existing_rows:
        m = re.match(r"VS-(\d+)$", (row.get("ID") or "").strip())
        if m:
            max_n = max(max_n, int(m.group(1)))
    return max_n + 1


def select_topics(search_bank_rows, batch_size):
    unused = [
        r for r in search_bank_rows
        if (r.get("Status") or "").strip().lower() == STATUS_UNUSED.lower()
    ]

    def score(row):
        try:
            return int(row.get("Search Score") or 0) + int(row.get("Trend Score") or 0)
        except ValueError:
            return 0

    unused.sort(key=score, reverse=True)
    return unused[:batch_size]


def build_prompt(brand, topic_row, existing_topics, existing_hooks):
    system = (
        "You are the copywriting engine for Vital Sync, a premium fitness and "
        "performance brand. Brand voice: premium, athletic, modern, scientific, "
        "practical, calm, confident, helpful. Never sound like military software, "
        "cyberpunk UI, hacker interface, generic fitness influencer, bro-science, "
        "or clickbait.\n\n"
        f"Mission: {brand.get('Mission', '')}\n"
        f"Catchphrase: {brand.get('Catchphrase', '')}\n"
        f"Tone: {brand.get('Tone', '')}\n"
        f"Avoid: {brand.get('Avoid', '')}\n\n"
        "Return ONLY a JSON object with exactly these keys: content_pillar, "
        "content_type, hook, problem, cause, solution, cta, script, caption, "
        "on_screen_text, hashtags, promotion, avatar.\n"
        "- hashtags: an array of EXACTLY 5 strings, each starting with '#', no spaces.\n"
        "- promotion: exactly 'Yes' or 'No'.\n"
        "- hook: a single scroll-stopping opening line, on-brand, not clickbait.\n"
        "- cta: a natural, specific call to action (not generic/salesy).\n"
        "- script: the full short-form video script. Target 45-80 words "
        "(roughly 15-25 seconds spoken) — this must match Workflow 02's QC "
        "rubric exactly, or the content gets rejected on length alone "
        "regardless of quality.\n"
        "- on_screen_text: short on-screen text cues, newline separated.\n"
        "- avatar: a persona label such as 'Fitness Coach', 'Nutrition Coach', etc.\n"
        "The topic and hook must be genuinely different from the existing ones "
        "listed below — do not restate them."
    )
    user = (
        f"New content brief:\n"
        f"Search Query: {topic_row.get('Search Query', '')}\n"
        f"Topic: {topic_row.get('Topic', '')}\n"
        f"Category: {topic_row.get('Category', '')}\n"
        f"Search Intent: {topic_row.get('Search Intent', '')}\n\n"
        f"Existing topics already in the pipeline (avoid duplicating):\n"
        f"{json.dumps(existing_topics[-DEDUP_CONTEXT_SIZE:])}\n\n"
        f"Existing hooks already in the pipeline (avoid duplicating):\n"
        f"{json.dumps(existing_hooks[-DEDUP_CONTEXT_SIZE:])}"
    )
    return system, user


def validate(data, existing_topics, existing_hooks, existing_scripts, topic_row):
    errors = []

    for field in REQUIRED_GENERATED_FIELDS:
        if field not in data or data[field] in (None, "", []):
            errors.append(f"missing or empty required field: {field}")

    if errors:
        return errors

    hashtags = data.get("hashtags")
    if not isinstance(hashtags, list) or len(hashtags) != 5:
        errors.append("hashtags must be an array of exactly 5 items")
    elif not all(isinstance(h, str) and h.startswith("#") for h in hashtags):
        errors.append("every hashtag must be a string starting with '#'")

    if data.get("promotion") not in ("Yes", "No"):
        errors.append("promotion must be exactly 'Yes' or 'No'")

    topic_name = (topic_row.get("Topic") or "").strip().lower()
    hook = (data.get("hook") or "").strip().lower()
    script = (data.get("script") or "").strip().lower()

    if topic_name and topic_name in existing_topics:
        errors.append(f"duplicate topic: '{topic_name}' already exists in Content Pipeline")
    if hook and hook in existing_hooks:
        errors.append("duplicate hook: already exists in Content Pipeline")
    if script and script in existing_scripts:
        errors.append("duplicate script: already exists in Content Pipeline")

    haystack = " ".join(
        str(data.get(f, "")) for f in ("hook", "cta", "caption", "script")
    ).lower()
    for phrase in BANNED_PHRASES:
        if phrase in haystack:
            errors.append(f"contains banned phrase: '{phrase}'")

    return errors


def generate_one(client, model, brand, topic_row, existing_topics, existing_hooks, existing_scripts):
    system, user = build_prompt(brand, topic_row, list(existing_topics), list(existing_hooks))
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]

    attempt = 0
    last_errors = []
    while attempt <= MAX_RETRIES_PER_ITEM:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            response_format={"type": "json_object"},
            temperature=0.8,
        )
        raw = response.choices[0].message.content
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            last_errors = ["response was not valid JSON"]
            attempt += 1
            messages.append({"role": "assistant", "content": raw})
            messages.append({"role": "user", "content": "That was not valid JSON. Return ONLY the JSON object."})
            continue

        errors = validate(data, existing_topics, existing_hooks, existing_scripts, topic_row)
        if not errors:
            return data, attempt, None

        last_errors = errors
        attempt += 1
        if attempt <= MAX_RETRIES_PER_ITEM:
            messages.append({"role": "assistant", "content": raw})
            messages.append({
                "role": "user",
                "content": "Fix these validation errors and return the corrected JSON object only:\n"
                + "\n".join(f"- {e}" for e in errors),
            })

    return None, attempt, last_errors


def parse_log_entry(row):
    """Best-effort parse of a legacy or current Automation Logs row's Errors
    JSON payload. Returns {} for legacy/non-JSON rows (they simply don't
    participate in lock/streak logic)."""
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
        "Success": 1 if phase == "completed" and not (extra or {}).get("items_failed") else (
            0 if phase == "completed" else ""
        ),
        "Time": now_iso,
        "Errors": json.dumps(payload),
    }
    sheets_io.append_rows(sheet_id, AUTOMATION_LOGS_TAB, AUTOMATION_LOGS_HEADERS, [row], service=service)
    return now_iso


def check_overlap_and_compute_streak(sheet_id, service, trigger):
    """Returns (blocking_run_id_or_None, scheduled_clean_streak)."""
    logs = sheets_io.read_tab(sheet_id, AUTOMATION_LOGS_TAB, service=service)
    workflow_logs = [
        (r, parse_log_entry(r)) for r in logs if r.get("Workflow") == WORKFLOW_NAME
    ]

    started = {}
    resolved_run_ids = set()
    for row, payload in workflow_logs:
        run_id = payload.get("run_id")
        phase = payload.get("phase")
        if not run_id or not phase:
            continue
        if phase == "started":
            started[run_id] = row.get("Date")
        elif phase in ("completed", "skipped"):
            resolved_run_ids.add(run_id)

    now = datetime.now(timezone.utc)
    blocking_run_id = None
    for run_id, started_at in started.items():
        if run_id in resolved_run_ids:
            continue
        try:
            started_dt = datetime.fromisoformat(started_at)
        except (TypeError, ValueError):
            continue
        if now - started_dt < timedelta(minutes=STALE_RUN_TIMEOUT_MINUTES):
            blocking_run_id = run_id
            break

    dated = [
        (row.get("Date", ""), payload)
        for row, payload in workflow_logs
        if payload.get("phase") == "completed" and payload.get("trigger") == "scheduled"
    ]
    dated.sort(key=lambda t: t[0], reverse=True)

    streak = 0
    for _, payload in dated:
        if payload.get("clean"):
            streak += 1
        else:
            break

    return blocking_run_id, streak


def run(dry_run: bool, batch_size_override, send_email: bool, trigger: str):
    cfg = load_config()
    sheet_id = cfg["sheet_id"]
    service = sheets_io.get_sheets_service()

    if dry_run:
        search_bank_rows = sheets_io.read_tab(sheet_id, SEARCH_BANK_TAB, service=service)
        selected = select_topics(search_bank_rows, batch_size_override or cfg["base_batch_size"])
        print(f"Selected {len(selected)} unused topic(s) from Search Bank "
              f"(batch size {batch_size_override or cfg['base_batch_size']}):")
        for r in selected:
            print(f"  - [{r['_row']}] {r.get('Topic')} :: {r.get('Search Query')}")
        print("\n--dry-run: stopping before any OpenAI calls or sheet writes.")
        return

    run_id = uuid.uuid4().hex[:12]
    blocking_run_id, scheduled_streak = check_overlap_and_compute_streak(sheet_id, service, trigger)

    if blocking_run_id:
        reason = f"previous run '{blocking_run_id}' still active (started < {STALE_RUN_TIMEOUT_MINUTES}m ago)"
        write_log(sheet_id, service, run_id, "skipped", trigger, {"reason": reason})
        print(f"SKIPPED: {reason}")
        return

    write_log(sheet_id, service, run_id, "started", trigger)

    if batch_size_override:
        batch_size = batch_size_override
    elif trigger == "scheduled":
        batch_size = (
            cfg["escalated_batch_size"]
            if scheduled_streak >= ESCALATION_STREAK_THRESHOLD
            else cfg["base_batch_size"]
        )
    else:
        batch_size = cfg["base_batch_size"]

    print(f"Trigger: {trigger} | scheduled clean streak: {scheduled_streak} | batch size: {batch_size}")

    if not cfg["openai_key"]:
        write_log(sheet_id, service, run_id, "completed", trigger, {
            "error": "OPENAI_API_KEY not set", "items_processed": 0, "items_failed": 0,
            "items_duplicate": 0, "reclaimed_stuck_rows": 0, "clean": False,
        })
        sys.exit("OPENAI_API_KEY is not set in .env")

    try:
        # Self-heal: reset any stray Processing rows left by a crashed run
        # (safe to do here — we've just confirmed no other run is active).
        search_bank_headers = sheets_io.get_headers(sheet_id, SEARCH_BANK_TAB, service=service)
        status_col = sheets_io.col_letter(search_bank_headers.index("Status"))
        search_bank_rows = sheets_io.read_tab(sheet_id, SEARCH_BANK_TAB, service=service)

        stray_processing = [
            r for r in search_bank_rows
            if (r.get("Status") or "").strip().lower() == STATUS_PROCESSING.lower()
        ]
        reclaimed_count = len(stray_processing)
        if stray_processing:
            sheets_io.batch_update_cells(sheet_id, [
                (f"{SEARCH_BANK_TAB}!{status_col}{r['_row']}", STATUS_UNUSED) for r in stray_processing
            ], service=service)
            print(f"Self-healed {reclaimed_count} stale Processing row(s) back to Unused.")
            search_bank_rows = sheets_io.read_tab(sheet_id, SEARCH_BANK_TAB, service=service)

        brand_rows = sheets_io.read_tab(sheet_id, BRAND_GUIDELINES_TAB, service=service)
        brand = {r.get("Field"): r.get("Value") for r in brand_rows if r.get("Field")}

        content_pipeline_rows = sheets_io.read_tab(sheet_id, CONTENT_PIPELINE_TAB, service=service)
        existing_topics = {
            (r.get("Topic") or "").strip().lower() for r in content_pipeline_rows if r.get("Topic")
        }
        existing_hooks = {
            (r.get("Hook") or "").strip().lower() for r in content_pipeline_rows if r.get("Hook")
        }
        existing_scripts = {
            (r.get("Script") or "").strip().lower() for r in content_pipeline_rows if r.get("Script")
        }

        selected = select_topics(search_bank_rows, batch_size)
        print(f"Selected {len(selected)} unused topic(s) from Search Bank:")
        for r in selected:
            print(f"  - [{r['_row']}] {r.get('Topic')} :: {r.get('Search Query')}")

        if not selected:
            summary = {
                "items_processed": 0, "items_failed": 0, "items_duplicate": 0,
                "reclaimed_stuck_rows": reclaimed_count, "retry_count": 0,
                "batch_size": batch_size, "scheduled_clean_streak": scheduled_streak,
                "clean": reclaimed_count == 0,
            }
            write_log(sheet_id, service, run_id, "completed", trigger, summary)
            print("No unused topics available. Run complete (no-op).")
            return

        # Reserve immediately so no other run (or a future overlapping one)
        # can pick the same topics.
        sheets_io.batch_update_cells(sheet_id, [
            (f"{SEARCH_BANK_TAB}!{status_col}{r['_row']}", STATUS_PROCESSING) for r in selected
        ], service=service)

        client = OpenAI(api_key=cfg["openai_key"])
        next_id = next_content_id(content_pipeline_rows)
        today = datetime.now().strftime("%Y-%m-%d")

        new_rows = []
        row_to_topic = []
        duplicate_topics = []
        failed_topics = []
        retry_count = 0

        for topic_row in selected:
            try:
                data, attempts, errors = generate_one(
                    client, cfg["model"], brand, topic_row,
                    existing_topics, existing_hooks, existing_scripts,
                )
                retry_count += attempts

                if data is None:
                    is_duplicate = any("duplicate" in e.lower() for e in (errors or []))
                    if is_duplicate:
                        duplicate_topics.append(topic_row)
                        print(f"  DUPLICATE: {topic_row.get('Topic')} -> {errors}")
                    else:
                        failed_topics.append((topic_row, "; ".join(errors or [])))
                        print(f"  FAILED: {topic_row.get('Topic')} -> {errors}")
                    continue

                content_id = f"VS-{next_id:03d}"
                next_id += 1
                row = {
                    "ID": content_id,
                    "Brand": brand.get("Brand", "Vital Sync"),
                    "Status": "Draft",
                    "Priority": "Medium",
                    "Content Pillar": data["content_pillar"],
                    "Content Type": data["content_type"],
                    "Search Query": topic_row.get("Search Query", ""),
                    "Topic": topic_row.get("Topic", ""),
                    "Hook": data["hook"],
                    "Problem": data["problem"],
                    "Cause": data["cause"],
                    "Solution": data["solution"],
                    "CTA": data["cta"],
                    "Script": data["script"],
                    "Caption": data["caption"],
                    "On-Screen Text": data["on_screen_text"],
                    "Hashtags": " ".join(data["hashtags"]),
                    "Promotion": data["promotion"],
                    "Avatar": data["avatar"],
                    "Date Generated": today,
                    "Approval": "Pending",
                    "Quality Score": "", "Hook Score": "", "CTA Score": "",
                    "Grammar Score": "", "Readability Score": "", "Brand Voice Score": "",
                    "Review Notes": "", "Date Checked": "",
                    "Platform URL": "", "Published Date": "",
                }
                new_rows.append(row)
                row_to_topic.append(topic_row)

                existing_topics.add((topic_row.get("Topic") or "").strip().lower())
                existing_hooks.add(data["hook"].strip().lower())
                existing_scripts.add(data["script"].strip().lower())

                print(f"  OK: {content_id} :: {topic_row.get('Topic')} (attempts={attempts + 1})")

            except Exception as e:
                failed_topics.append((topic_row, f"unexpected error: {e}"))
                print(f"  FAILED (exception): {topic_row.get('Topic')} -> {e}")
                continue

        # Resolve generation-time failures/duplicates immediately.
        status_updates = [
            (f"{SEARCH_BANK_TAB}!{status_col}{r['_row']}", STATUS_DUPLICATE) for r in duplicate_topics
        ] + [
            (f"{SEARCH_BANK_TAB}!{status_col}{r['_row']}", STATUS_FAILED) for r, _ in failed_topics
        ]
        if status_updates:
            sheets_io.batch_update_cells(sheet_id, status_updates, service=service)

        append_failed = False
        if new_rows:
            try:
                sheets_io.append_rows(sheet_id, CONTENT_PIPELINE_TAB, CONTENT_PIPELINE_HEADERS, new_rows, service=service)
                sheets_io.batch_update_cells(sheet_id, [
                    (f"{SEARCH_BANK_TAB}!{status_col}{t['_row']}", STATUS_USED) for t in row_to_topic
                ], service=service)
            except Exception as e:
                append_failed = True
                sheets_io.batch_update_cells(sheet_id, [
                    (f"{SEARCH_BANK_TAB}!{status_col}{t['_row']}", STATUS_FAILED) for t in row_to_topic
                ], service=service)
                failed_topics.extend((t, f"Content Pipeline append failed: {e}") for t in row_to_topic)
                items_processed = 0
                print(f"  APPEND FAILED for batch: {e}")
            else:
                items_processed = len(new_rows)
        else:
            items_processed = 0

        items_failed = len(failed_topics)
        items_duplicate = len(duplicate_topics)
        clean = (items_failed == 0 and items_duplicate == 0 and reclaimed_count == 0 and not append_failed)

        summary = {
            "items_processed": items_processed,
            "items_failed": items_failed,
            "items_duplicate": items_duplicate,
            "reclaimed_stuck_rows": reclaimed_count,
            "retry_count": retry_count,
            "batch_size": batch_size,
            "scheduled_clean_streak": scheduled_streak,
            "clean": clean,
            "failures": [{"topic": t.get("Topic"), "error": err} for t, err in failed_topics][:20],
            "duplicates": [t.get("Topic") for t in duplicate_topics][:20],
        }
        write_log(sheet_id, service, run_id, "completed", trigger, summary)

        print(f"\nDone. Appended {items_processed} row(s) to Content Pipeline, "
              f"{items_duplicate} duplicate(s), {items_failed} failure(s).")

        if send_email and cfg["email_to"]:
            body_lines = [
                f"Workflow: {WORKFLOW_NAME}",
                f"Trigger: {trigger} (run {run_id})",
                f"Batch size: {batch_size} (scheduled clean streak: {scheduled_streak})",
                f"Items processed: {items_processed}",
                f"Items duplicate: {items_duplicate}",
                f"Items failed: {items_failed}",
                f"Retry count: {retry_count}",
                f"Reclaimed stuck rows: {reclaimed_count}",
                "",
                "New content:",
            ] + [f"  - {r['ID']}: {r['Topic']}" for r in new_rows]
            if duplicate_topics:
                body_lines += ["", "Duplicates skipped:"] + [f"  - {t.get('Topic')}" for t in duplicate_topics]
            if failed_topics:
                body_lines += ["", "Failures:"] + [f"  - {t.get('Topic')}: {err}" for t, err in failed_topics]
            gmail_send.send_email(
                to=cfg["email_to"],
                subject=f"{WORKFLOW_NAME} — {items_processed} new, {items_duplicate} dup, {items_failed} failed",
                body_text="\n".join(body_lines),
            )
            print(f"Summary email sent to {cfg['email_to']}.")

    except Exception as e:
        write_log(sheet_id, service, run_id, "completed", trigger, {
            "error": f"run crashed: {e}", "items_processed": 0, "items_failed": 0,
            "items_duplicate": 0, "reclaimed_stuck_rows": 0, "clean": False,
        })
        raise


def _cli():
    parser = argparse.ArgumentParser(description="Vital Sync Workflow 01: Script Factory")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="Select topics only, no OpenAI calls or writes")
    mode.add_argument("--live", action="store_true", help="Full run: generates, writes, emails")
    parser.add_argument("--batch-size", type=int, default=None, help="Override auto-computed batch size")
    parser.add_argument("--trigger", choices=["manual", "scheduled"], default="manual")
    parser.add_argument("--no-email", action="store_true")
    args = parser.parse_args()

    run(dry_run=args.dry_run, batch_size_override=args.batch_size,
        send_email=not args.no_email, trigger=args.trigger)


if __name__ == "__main__":
    _cli()
