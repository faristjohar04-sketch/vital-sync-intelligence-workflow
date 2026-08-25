"""Vital Sync — Weekly Intelligence: finish what the cloud routine can't.

The cloud routine (`Vital Sync Weekly Intelligence`, cron 0 4 * * 1 UTC =
Monday 8am Asia/Dubai) does the research, generates the PDF, and pushes its
work — but only to a fresh `claude/*` branch (its GitHub App install opens
a PR rather than pushing straight to main), and it can never send email
(no secrets mechanism exists for cloud routines as of this writing — see
tools/gmail_smtp_send.py's docstring). Both of those remaining steps ARE
fully deterministic once the cloud run has finished, so this script does
them without needing Claude in the loop each week:

  1. Fetch the repo; fast-forward local main to origin/main (NEVER a hard
     reset — if local main has diverged from origin for any reason, this
     step fails loudly and stops rather than silently discarding local
     work. That's deliberate: a script that runs unattended on a schedule
     must never be the thing that deletes uncommitted or unpushed work).
  2. Merge any not-yet-merged `claude/*` branches into main (a plain
     `git merge`, not fast-forward-only, since two branches can be based
     on the same older commit — the .gitattributes union-merge driver on
     automation_log.jsonl means this resolves without manual conflict
     handling in the common case).
  3. Push main.
  4. Scan reports/vital_sync/automation_log.jsonl for entries where a PDF
     was generated but the email was not sent (pdf_generated=true,
     email_sent=false, pdf_path set) — these are exactly the reports a
     cloud run finished but couldn't email. Send each one, oldest first,
     via the LOCAL OAuth-based gmail_send.py (this script runs on the same
     machine as that OAuth token, unlike the cloud routine).
  5. Rewrite those log entries' email_sent/email_message_id fields to
     reflect reality, commit, and push again.

This intentionally does NOT do any research, competitor discovery, or
WEEK_DATA authoring — that's Claude's job in the cloud routine, per the WAT
split of concerns. If the cloud routine hasn't run yet this week (no new
branch, nothing unsent), this script is a safe no-op.

Usage:
    python tools/vital_sync_weekly_finish.py --live --trigger scheduled
    python tools/vital_sync_weekly_finish.py --dry-run
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from typing import Optional

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_PATH = os.path.join(REPO_ROOT, "reports", "vital_sync", "automation_log.jsonl")
REMOTE_URL = "https://github.com/faristjohar04-sketch/vital-sync-intelligence-workflow.git"
RECIPIENT = "faristjohar04@gmail.com"


class SyncError(Exception):
    pass


def run(cmd, **kwargs):
    return subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True, **kwargs)


def authed_remote():
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise RuntimeError("GITHUB_TOKEN not set in the environment — cannot push.")
    return REMOTE_URL.replace("https://", f"https://x-access-token:{token}@")


def sync_repo(live: bool) -> list:
    """Fast-forward main, merge pending claude/* branches, push. Returns notes.

    Never destructive: every step either fast-forwards or fails loudly.
    """
    notes = []
    remote = authed_remote()

    fetch = run(["git", "fetch", remote, "+refs/heads/*:refs/remotes/origin/*"])
    if fetch.returncode != 0:
        raise SyncError(f"git fetch failed: {fetch.stderr}")

    checkout = run(["git", "checkout", "main"])
    if checkout.returncode != 0:
        raise SyncError(f"git checkout main failed (uncommitted local changes?): {checkout.stderr}")

    # Fast-forward only. If local main has unpushed commits or has otherwise
    # diverged, this fails instead of guessing — surface it, don't erase it.
    ff = run(["git", "merge", "--ff-only", "origin/main"])
    if ff.returncode != 0:
        raise SyncError(
            "Local main has diverged from origin/main and cannot be fast-forwarded "
            f"— refusing to reset or force anything. Resolve manually first.\n{ff.stderr}"
        )
    notes.append("Local main fast-forwarded to origin/main.")

    branches = run(["git", "branch", "-r", "--no-merged", "main"]).stdout
    pending = sorted({
        b.strip().replace("origin/", "")
        for b in branches.splitlines()
        if "origin/claude/" in b
    })
    if not pending:
        notes.append("No pending claude/* branches — cloud routine hasn't produced new work.")
        return notes

    for branch in pending:
        result = run(["git", "merge", f"origin/{branch}", "-m", f"Merge {branch} (weekly auto-sync)"])
        if result.returncode != 0:
            status = run(["git", "status", "--short"]).stdout
            unresolved = [l for l in status.splitlines() if l.startswith("UU")]
            only_log_conflicts = unresolved and all("automation_log.jsonl" in l for l in unresolved)
            if not only_log_conflicts:
                run(["git", "merge", "--abort"])
                notes.append(f"MERGE_FAILED for {branch}: unexpected conflict, needs manual attention.\n{result.stderr}")
                continue
            run(["git", "add", LOG_PATH])
            run(["git", "commit", "--no-edit"])
        notes.append(f"Merged {branch} into main.")

    if live:
        push = run(["git", "push", remote, "main:main"])
        notes.append("Pushed main." if push.returncode == 0 else f"PUSH_FAILED: {push.stderr}")
    else:
        notes.append("[dry-run] Would push main.")

    return notes


def find_unsent() -> list:
    if not os.path.exists(LOG_PATH):
        return []
    unsent = []
    with open(LOG_PATH) as f:
        lines = [l for l in f if l.strip()]
    for i, line in enumerate(lines):
        entry = json.loads(line)
        if entry.get("pdf_generated") and entry.get("pdf_path") and not entry.get("email_sent"):
            unsent.append((i, entry))
    return unsent


def send_report(entry: dict, live: bool) -> Optional[str]:
    pdf_path = os.path.join(REPO_ROOT, entry["pdf_path"])
    if not os.path.exists(pdf_path):
        print(f"  SKIP: {pdf_path} not found on disk after sync.")
        return None

    report_date = entry.get("report_date") or entry["run_id"].split("-", 2)[-1].rsplit("-", 1)[0]
    subject = f"Vital Sync — Weekly Competition Intelligence — {report_date}"
    body = (
        f"Weekly Vital Sync competition intelligence for {report_date}.\n\n"
        f"Sent automatically by the weekly-finish sync job (the cloud routine that "
        f"generated this report has no way to send email itself — see "
        f"tools/gmail_smtp_send.py's docstring for why).\n\n"
        f"Run notes: {entry.get('notes', '(none)')}\n\n"
        f"Full findings are in the attached PDF."
    )

    if not live:
        print(f"  [dry-run] Would email {pdf_path} with subject: {subject}")
        return "DRY-RUN"

    sys.path.insert(0, os.path.join(REPO_ROOT, "tools"))
    from gmail_send import send_email  # local OAuth sender — this script only ever runs locally

    result = send_email(RECIPIENT, subject, body, attachments=[pdf_path])
    print(f"  Sent. Message ID: {result.get('id')}")
    return result.get("id")


def _cli():
    parser = argparse.ArgumentParser(description="Finish the weekly Vital Sync intelligence loop (merge + email)")
    parser.add_argument("--live", action="store_true", help="Actually push/send. Without this, dry-run only.")
    parser.add_argument("--dry-run", action="store_true", help="Explicit dry-run (default if --live omitted).")
    parser.add_argument("--trigger", default="manual", choices=["manual", "scheduled"])
    args = parser.parse_args()
    live = args.live and not args.dry_run

    print(f"=== Vital Sync weekly-finish ({args.trigger}) at {datetime.now(timezone.utc).isoformat()} ===")
    print(f"Mode: {'LIVE' if live else 'DRY-RUN'}")

    try:
        sync_notes = sync_repo(live)
    except SyncError as e:
        print(f"[sync] ABORTED: {e}")
        sys.exit(1)
    for n in sync_notes:
        print(f"[sync] {n}")

    unsent = find_unsent()
    if not unsent:
        print("No unsent reports found. Nothing to email.")
        return

    print(f"Found {len(unsent)} unsent report(s).")
    with open(LOG_PATH) as f:
        lines = [l for l in f if l.strip()]

    changed = False
    for idx, entry in unsent:
        print(f"Sending {entry['run_id']} ({entry.get('pdf_path')})...")
        message_id = send_report(entry, live)
        if message_id and live:
            entry["email_sent"] = True
            entry["email_message_id"] = message_id
            lines[idx] = json.dumps(entry) + "\n"
            changed = True

    if changed:
        with open(LOG_PATH, "w") as f:
            f.writelines(lines)
        run(["git", "add", LOG_PATH])
        run(["git", "commit", "-m", "Record email delivery for weekly report(s) (auto-sync)"])
        if live:
            push = run(["git", "push", authed_remote(), "main:main"])
            print("[log] Pushed delivery record." if push.returncode == 0 else f"[log] PUSH_FAILED: {push.stderr}")

    print("=== Done ===")


if __name__ == "__main__":
    _cli()
