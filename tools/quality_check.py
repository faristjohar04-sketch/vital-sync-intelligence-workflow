"""Vital Sync — Workflow 02: Quality Checker

Deterministically orchestrates one run of the QC pipeline: reads Brand
Guidelines + Content Pipeline + Automation Logs fresh from the Google Sheet
every run (no local state, no memory of past executions), selects rows with
Status = Draft AND Approval = Pending (see "Status naming" below), scores
each one against Vital Sync's brand voice / hook / script / CTA / grammar /
readability / hashtag / duplicate / safety rules, writes the scores +
decision back to the same row, logs the run, and emails a summary.

Status naming: the Workflow 02 spec calls the input state "Generated". The
live Content Pipeline sheet and Workflow 01 both use the literal string
"Draft" for freshly generated, not-yet-reviewed rows (Workflow 01's own docs
say it hands off "Draft" rows to this workflow). This tool filters on
Status == "Draft" for that reason. If a distinct "Generated" status is ever
introduced, update STATUS_INPUT below.

This tool NEVER generates new content, never overwrites Script / Hook /
Caption / Topic / Search Query, never deletes or clears rows, and never
touches rows whose Approval is already something other than "Pending".

Overlap prevention mirrors Workflow 01: paired "started"/"completed"/
"skipped" markers in Automation Logs, keyed by this workflow's own name, with
the same stale-run self-heal timeout. In addition, before starting real
work this tool checks Automation Logs for an unresolved Workflow 01
("Vital Sync Script Factory") "started" marker and waits (bounded, polling)
for it to clear, so the two workflows never process rows at the same time.

This tool makes paid OpenAI API calls (one per row, JSON-mode). Do not run
--live without the user's go-ahead. Use --dry-run first to verify sheet
connectivity and row selection at no cost.

Usage:
    python tools/quality_check.py --dry-run
    python tools/quality_check.py --live --trigger manual
    python tools/quality_check.py --live --trigger scheduled
    python tools/quality_check.py --live --batch-size 3 --no-email
"""

import argparse
import json
import os
import re
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from openai import OpenAI

import gmail_send
import sheets_io

WORKFLOW_NAME = "Vital Sync Quality Checker"
SCRIPT_FACTORY_WORKFLOW_NAME = "Vital Sync Script Factory"  # Workflow 01 — read-only reference, never modified here

CONTENT_PIPELINE_TAB = "Content Pipeline"
BRAND_GUIDELINES_TAB = "Brand Guidelines"
AUTOMATION_LOGS_TAB = "Automation Logs"

AUTOMATION_LOGS_HEADERS = ["Date", "Workflow", "Success", "Time", "Errors"]

# Columns this workflow is allowed to write. Everything else on a row
# (Script, Hook, Caption, Topic, Search Query, etc.) is never touched.
WRITE_COLUMNS = [
    "Quality Score", "Hook Score", "CTA Score", "Grammar Score",
    "Readability Score", "Brand Voice Score", "Review Notes",
    "Date Checked", "Approval", "Status",
]

STATUS_INPUT = "Draft"          # see "Status naming" above
APPROVAL_INPUT = "Pending"

STATUS_READY = "Ready for Video"
STATUS_REVIEW = "Review Required"
STATUS_REWRITE = "Rewrite Required"

APPROVAL_APPROVED = "Approved"
APPROVAL_REVIEW = "Needs Review"
APPROVAL_REJECTED = "Rejected"

APPROVE_THRESHOLD = 90
REVIEW_THRESHOLD = 75

DEDUP_FIELDS = ["Topic", "Hook", "Script", "Caption", "Search Query"]
GENERIC_CTA_PHRASES = ["follow for more", "like this video", "comment below"]
BANNED_PHRASES = [
    "click now", "buy now", "you won't believe", "guaranteed results",
    "miracle", "limited time only", "act now", "cures", "diagnose",
    "medical advice",
]

MAX_AI_RETRIES = 2       # "Retry AI twice"
MAX_SHEETS_RETRIES = 2   # "Retry Google Sheets twice"
STALE_RUN_TIMEOUT_MINUTES = 90
SCRIPT_MIN_WORDS = 45
SCRIPT_MAX_WORDS = 80

REQUIRED_AI_FIELDS = [
    "hook_score", "hook_notes", "script_score", "script_notes",
    "brand_voice_score", "brand_voice_violations", "cta_score", "cta_notes",
    "grammar_score", "grammar_issues", "readability_score",
    "readability_grade_estimate", "safety_violations", "summary_notes",
]


def load_config():
    load_dotenv()
    sheet_id = os.environ.get("GOOGLE_SHEET_ID")
    openai_key = os.environ.get("OPENAI_API_KEY")
    model = os.environ.get("QUALITY_CHECK_MODEL", os.environ.get("OPENAI_MODEL", "gpt-4o"))
    email_to = os.environ.get("SUMMARY_EMAIL_TO")
    batch_size = int(os.environ.get("QUALITY_CHECK_BATCH_SIZE", "10"))
    wf01_wait_minutes = int(os.environ.get("QUALITY_CHECK_WF01_WAIT_MINUTES", "30"))
    if not sheet_id:
        sys.exit("GOOGLE_SHEET_ID is not set in .env")
    return {
        "sheet_id": sheet_id,
        "openai_key": openai_key,
        "model": model,
        "email_to": email_to,
        "batch_size": batch_size,
        "wf01_wait_minutes": wf01_wait_minutes,
    }


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
    """Returns (run_id, started_at_iso) for the most recent unresolved
    'started' marker for the given workflow name, or (None, None)."""
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


def wait_for_workflow01(sheet_id, service, max_wait_minutes, poll_seconds=30):
    """Waits (bounded) for any in-flight Workflow 01 run to clear, so the
    two workflows never touch Content Pipeline at the same time. Returns
    (was_active_at_start, waited_seconds, still_active_after_wait)."""
    deadline = time.monotonic() + max_wait_minutes * 60
    logs = with_sheets_retry(sheets_io.read_tab, sheet_id, AUTOMATION_LOGS_TAB, service=service)
    run_id, _ = find_unresolved_started(logs, SCRIPT_FACTORY_WORKFLOW_NAME)
    was_active = run_id is not None
    waited = 0
    while run_id is not None and time.monotonic() < deadline:
        time.sleep(poll_seconds)
        waited += poll_seconds
        logs = with_sheets_retry(sheets_io.read_tab, sheet_id, AUTOMATION_LOGS_TAB, service=service)
        run_id, _ = find_unresolved_started(logs, SCRIPT_FACTORY_WORKFLOW_NAME)
    return was_active, waited, run_id is not None


def select_rows(content_pipeline_rows, batch_size):
    eligible = [
        r for r in content_pipeline_rows
        if norm(r.get("Status")) == norm(STATUS_INPUT) and norm(r.get("Approval")) == norm(APPROVAL_INPUT)
    ]
    return eligible[:batch_size]


def find_duplicates(row, all_rows):
    """Exact-match duplicate detection across ALL Content Pipeline rows
    (approved/rejected/pending alike), excluding the row itself."""
    hits = []
    for field in DEDUP_FIELDS:
        value = norm(row.get(field))
        if not value:
            continue
        for other in all_rows:
            if other["_row"] == row["_row"]:
                continue
            if norm(other.get(field)) == value:
                other_label = other.get("ID") or f"row {other['_row']}"
                hits.append(f"{field} matches {other_label}")
                break
    return hits


def deterministic_checks(row):
    hashtags = [h for h in (row.get("Hashtags") or "").split() if h.startswith("#")]
    hashtag_count = len(hashtags)

    script = row.get("Script") or ""
    word_count = len(script.split())
    if word_count < SCRIPT_MIN_WORDS:
        deviation = SCRIPT_MIN_WORDS - word_count
    elif word_count > SCRIPT_MAX_WORDS:
        deviation = word_count - SCRIPT_MAX_WORDS
    else:
        deviation = 0
    script_compliance = max(0.0, 1 - deviation / 40)

    cta = norm(row.get("CTA"))
    cta_generic_hit = next((p for p in GENERIC_CTA_PHRASES if p in cta), None)

    haystack = " ".join(str(row.get(f, "")) for f in ("Hook", "CTA", "Caption", "Script")).lower()
    banned_hits = [p for p in BANNED_PHRASES if p in haystack]

    return {
        "hashtag_count": hashtag_count,
        "hashtag_ok": hashtag_count == 5,
        "word_count": word_count,
        "script_compliance": script_compliance,
        "cta_generic_hit": cta_generic_hit,
        "banned_phrase_hits": banned_hits,
    }


def build_prompt(brand, row):
    system = (
        "You are the quality-control reviewer for Vital Sync, a premium fitness "
        "and performance brand. Brand voice must be: premium, athletic, modern, "
        "scientific, helpful, confident, practical. Reject/penalize: clickbait, "
        "bro-science, military language, cyberpunk language, fake urgency, fear "
        "tactics, medical claims.\n\n"
        f"Mission: {brand.get('Mission', '')}\n"
        f"Catchphrase: {brand.get('Catchphrase', '')}\n"
        f"Tone: {brand.get('Tone', '')}\n"
        f"Avoid: {brand.get('Avoid', '')}\n\n"
        "Score this content package. Return ONLY a JSON object with exactly "
        "these keys:\n"
        "- hook_score: integer 1-10 (curiosity, clarity, scroll-stopping, "
        "relevance, specificity)\n"
        "- hook_notes: short string\n"
        "- script_score: integer 0-100 (natural spoken English, logical flow, "
        "one clear lesson, no repetition, no filler, easy to understand)\n"
        "- script_notes: short string\n"
        "- brand_voice_score: integer 0-100 (0-20 if ANY reject-list "
        "characteristic is present)\n"
        "- brand_voice_violations: array of strings, empty if none\n"
        "- cta_score: integer 0-100 (natural, specific, matches the content; "
        "0-20 if generic/salesy)\n"
        "- cta_notes: short string\n"
        "- grammar_score: integer 0-100 (grammar, spelling, capitalization, "
        "punctuation)\n"
        "- grammar_issues: array of strings, empty if none\n"
        "- readability_score: integer 0-100 (target grade 6-8, easy to read "
        "aloud; 100 = perfectly on target)\n"
        "- readability_grade_estimate: number (approximate US grade level)\n"
        "- safety_violations: array of strings — medical advice, dangerous "
        "advice, guaranteed results, unsupported claims. Empty if none.\n"
        "- summary_notes: short string, 1-3 sentences summarizing the "
        "evaluation, written for a human reviewer\n"
        "Do not rewrite or suggest new copy — evaluate only."
    )
    user = (
        f"Content package to evaluate:\n"
        f"Topic: {row.get('Topic', '')}\n"
        f"Hook: {row.get('Hook', '')}\n"
        f"Script: {row.get('Script', '')}\n"
        f"Caption: {row.get('Caption', '')}\n"
        f"CTA: {row.get('CTA', '')}\n"
        f"Hashtags: {row.get('Hashtags', '')}\n"
        f"Content Pillar: {row.get('Content Pillar', '')}\n"
        f"Content Type: {row.get('Content Type', '')}"
    )
    return system, user


def call_ai(client, model, brand, row):
    system, user = build_prompt(brand, row)
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]

    attempt = 0
    while attempt <= MAX_AI_RETRIES:
        try:
            response = client.chat.completions.create(
                model=model, messages=messages,
                response_format={"type": "json_object"}, temperature=0.2,
            )
        except Exception as e:
            attempt += 1
            if attempt > MAX_AI_RETRIES:
                return None, f"OpenAI request failed after retries: {e}"
            time.sleep(2 * attempt)
            continue

        raw = response.choices[0].message.content
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            attempt += 1
            messages.append({"role": "assistant", "content": raw})
            messages.append({"role": "user", "content": "That was not valid JSON. Return ONLY the JSON object."})
            if attempt > MAX_AI_RETRIES:
                return None, "AI did not return valid JSON after retries"
            continue

        missing = [f for f in REQUIRED_AI_FIELDS if f not in data]
        if missing:
            attempt += 1
            messages.append({"role": "assistant", "content": raw})
            messages.append({
                "role": "user",
                "content": f"Missing required fields: {missing}. Return the corrected JSON object only.",
            })
            if attempt > MAX_AI_RETRIES:
                return None, f"AI response missing fields after retries: {missing}"
            continue

        return data, None

    return None, "AI evaluation failed"  # pragma: no cover


def evaluate_row(client, model, brand, row, all_rows):
    ai_data, ai_error = call_ai(client, model, brand, row)
    if ai_data is None:
        raise RuntimeError(ai_error)

    det = deterministic_checks(row)
    dup_hits = find_duplicates(row, all_rows)

    hook_score = int(ai_data["hook_score"])
    script_score = round(int(ai_data["script_score"]) * det["script_compliance"])
    brand_voice_score = int(ai_data["brand_voice_score"])
    cta_score = int(ai_data["cta_score"])
    if det["cta_generic_hit"]:
        cta_score = min(cta_score, 15)
    grammar_score = int(ai_data["grammar_score"])
    readability_score = int(ai_data["readability_score"])

    safety_violations = list(ai_data.get("safety_violations") or [])
    for hit in det["banned_phrase_hits"]:
        note = f"banned phrase: '{hit}'"
        if note not in safety_violations:
            safety_violations.append(note)
            brand_voice_score = min(brand_voice_score, 20)

    overall = (
        hook_score * 10 * 0.20
        + script_score * 0.30
        + brand_voice_score * 0.20
        + cta_score * 0.10
        + grammar_score * 0.10
        + readability_score * 0.10
    )
    overall = round(max(0, min(100, overall)))

    if not det["hashtag_ok"]:
        overall = min(overall, 89)
    if hook_score < 7:
        overall = min(overall, 89)

    hard_reject = bool(dup_hits) or bool(safety_violations)
    if hard_reject:
        overall = min(overall, REVIEW_THRESHOLD - 1)

    if hard_reject:
        approval, status = APPROVAL_REJECTED, STATUS_REWRITE
    elif overall >= APPROVE_THRESHOLD:
        approval, status = APPROVAL_APPROVED, STATUS_READY
    elif overall >= REVIEW_THRESHOLD:
        approval, status = APPROVAL_REVIEW, STATUS_REVIEW
    else:
        approval, status = APPROVAL_REJECTED, STATUS_REWRITE

    notes = [ai_data.get("summary_notes", "").strip()]
    if dup_hits:
        notes.append("DUPLICATE: " + "; ".join(dup_hits))
    if safety_violations:
        notes.append("SAFETY: " + "; ".join(safety_violations))
    if ai_data.get("brand_voice_violations"):
        notes.append("BRAND VOICE: " + "; ".join(ai_data["brand_voice_violations"]))
    if not det["hashtag_ok"]:
        notes.append(f"HASHTAGS: found {det['hashtag_count']}, need exactly 5")
    if det["word_count"] < SCRIPT_MIN_WORDS or det["word_count"] > SCRIPT_MAX_WORDS:
        notes.append(f"SCRIPT LENGTH: {det['word_count']} words (target {SCRIPT_MIN_WORDS}-{SCRIPT_MAX_WORDS})")
    if det["cta_generic_hit"]:
        notes.append(f"CTA: generic phrase detected ('{det['cta_generic_hit']}')")
    if ai_data.get("grammar_issues"):
        notes.append("GRAMMAR: " + "; ".join(ai_data["grammar_issues"]))
    if hook_score < 7:
        notes.append("HOOK: score below 7")
    review_notes = " | ".join(n for n in notes if n)[:1500]

    return {
        "quality_score": overall,
        "hook_score": hook_score,
        "cta_score": cta_score,
        "grammar_score": grammar_score,
        "readability_score": readability_score,
        "brand_voice_score": brand_voice_score,
        "review_notes": review_notes,
        "approval": approval,
        "status": status,
    }


def run(dry_run: bool, batch_size_override, send_email: bool, trigger: str):
    cfg = load_config()
    sheet_id = cfg["sheet_id"]
    service = sheets_io.get_sheets_service()
    batch_size = batch_size_override or cfg["batch_size"]

    if dry_run:
        rows = with_sheets_retry(sheets_io.read_tab, sheet_id, CONTENT_PIPELINE_TAB, service=service)
        selected = select_rows(rows, batch_size)
        print(f"Selected {len(selected)} row(s) with Status='{STATUS_INPUT}' AND Approval='{APPROVAL_INPUT}' "
              f"(batch size {batch_size}):")
        for r in selected:
            print(f"  - [{r['_row']}] {r.get('ID')} :: {r.get('Topic')}")
        print("\n--dry-run: stopping before any OpenAI calls or sheet writes.")
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
    was_wf01_active, waited_seconds, still_active = wait_for_workflow01(
        sheet_id, service, cfg["wf01_wait_minutes"]
    )
    if was_wf01_active:
        print(f"Workflow 01 was active; waited {waited_seconds}s "
              f"({'still active, proceeding anyway' if still_active else 'cleared'}).")

    if not cfg["openai_key"]:
        write_log(sheet_id, service, run_id, "completed", trigger, {
            "error_count": 1, "rows_checked": 0, "approved": 0, "needs_review": 0,
            "rejected": 0, "errors": ["OPENAI_API_KEY not set"],
        })
        sys.exit("OPENAI_API_KEY is not set in .env")

    try:
        brand_rows = with_sheets_retry(sheets_io.read_tab, sheet_id, BRAND_GUIDELINES_TAB, service=service)
        brand = {r.get("Field"): r.get("Value") for r in brand_rows if r.get("Field")}

        headers = with_sheets_retry(sheets_io.get_headers, sheet_id, CONTENT_PIPELINE_TAB, service=service)
        col_letters = {h: sheets_io.col_letter(headers.index(h)) for h in WRITE_COLUMNS if h in headers}
        missing_cols = [h for h in WRITE_COLUMNS if h not in headers]
        if missing_cols:
            raise RuntimeError(f"Content Pipeline is missing expected column(s): {missing_cols}")

        all_rows = with_sheets_retry(sheets_io.read_tab, sheet_id, CONTENT_PIPELINE_TAB, service=service)
        selected = select_rows(all_rows, batch_size)
        print(f"Selected {len(selected)} row(s) to evaluate.")

        if not selected:
            summary = {
                "rows_checked": 0, "approved": 0, "needs_review": 0, "rejected": 0,
                "error_count": 0, "errors": [], "warnings": [],
                "waited_for_workflow01_seconds": waited_seconds,
                "workflow01_still_active": still_active,
                "duration_seconds": (datetime.now(timezone.utc) - start_time).total_seconds(),
            }
            write_log(sheet_id, service, run_id, "completed", trigger, summary)
            print("No eligible rows. Run complete (no-op).")
            return

        client = OpenAI(api_key=cfg["openai_key"])
        today = datetime.now().strftime("%Y-%m-%d")

        cell_updates = []
        errors = []
        scores = []
        approved = needs_review = rejected = 0

        for row in selected:
            row_id = row.get("ID", f"row {row['_row']}")
            try:
                result = evaluate_row(client, cfg["model"], brand, row, all_rows)
            except Exception as e:
                errors.append({"id": row_id, "row": row["_row"], "error": str(e)})
                print(f"  ERROR: {row_id} -> {e}")
                continue

            values = {
                "Quality Score": result["quality_score"],
                "Hook Score": result["hook_score"],
                "CTA Score": result["cta_score"],
                "Grammar Score": result["grammar_score"],
                "Readability Score": result["readability_score"],
                "Brand Voice Score": result["brand_voice_score"],
                "Review Notes": result["review_notes"],
                "Date Checked": today,
                "Approval": result["approval"],
                "Status": result["status"],
            }
            for col, value in values.items():
                cell_updates.append((f"{CONTENT_PIPELINE_TAB}!{col_letters[col]}{row['_row']}", value))

            scores.append(result["quality_score"])
            if result["approval"] == APPROVAL_APPROVED:
                approved += 1
            elif result["approval"] == APPROVAL_REVIEW:
                needs_review += 1
            else:
                rejected += 1

            print(f"  {result['approval']}: {row_id} (score={result['quality_score']})")

        if cell_updates:
            with_sheets_retry(sheets_io.batch_update_cells, sheet_id, cell_updates, service=service)

        duration = (datetime.now(timezone.utc) - start_time).total_seconds()
        summary = {
            "rows_checked": len(selected) - len(errors),
            "approved": approved,
            "needs_review": needs_review,
            "rejected": rejected,
            "error_count": len(errors),
            "errors": errors[:20],
            "warnings": [],
            "waited_for_workflow01_seconds": waited_seconds,
            "workflow01_still_active": still_active,
            "duration_seconds": duration,
            "avg_score": round(sum(scores) / len(scores), 1) if scores else None,
            "highest_score": max(scores) if scores else None,
            "lowest_score": min(scores) if scores else None,
        }
        write_log(sheet_id, service, run_id, "completed", trigger, summary)

        print(f"\nDone. Checked {summary['rows_checked']}, approved {approved}, "
              f"needs review {needs_review}, rejected {rejected}, errors {len(errors)}.")

        if send_email and cfg["email_to"]:
            body_lines = [
                f"Workflow: {WORKFLOW_NAME}",
                f"Trigger: {trigger} (run {run_id})",
                f"Rows Checked: {summary['rows_checked']}",
                f"Approved: {approved}",
                f"Needs Review: {needs_review}",
                f"Rejected: {rejected}",
                f"Average Score: {summary['avg_score']}",
                f"Highest Score: {summary['highest_score']}",
                f"Lowest Score: {summary['lowest_score']}",
                f"Errors: {len(errors)}",
                f"Duration: {duration:.1f}s",
            ]
            if errors:
                body_lines += ["", "Errors:"] + [f"  - {e['id']}: {e['error']}" for e in errors]
            gmail_send.send_email(
                to=cfg["email_to"],
                subject="Vital Sync Quality Checker Report",
                body_text="\n".join(body_lines),
            )
            print(f"Summary email sent to {cfg['email_to']}.")

    except Exception as e:
        write_log(sheet_id, service, run_id, "completed", trigger, {
            "error_count": 1, "errors": [{"error": f"run crashed: {e}"}],
            "rows_checked": 0, "approved": 0, "needs_review": 0, "rejected": 0,
        })
        raise


def _cli():
    parser = argparse.ArgumentParser(description="Vital Sync Workflow 02: Quality Checker")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="Select rows only, no OpenAI calls or writes")
    mode.add_argument("--live", action="store_true", help="Full run: evaluates, writes, emails")
    parser.add_argument("--batch-size", type=int, default=None, help="Override QUALITY_CHECK_BATCH_SIZE")
    parser.add_argument("--trigger", choices=["manual", "scheduled"], default="manual")
    parser.add_argument("--no-email", action="store_true")
    args = parser.parse_args()

    run(dry_run=args.dry_run, batch_size_override=args.batch_size,
        send_email=not args.no_email, trigger=args.trigger)


if __name__ == "__main__":
    _cli()
