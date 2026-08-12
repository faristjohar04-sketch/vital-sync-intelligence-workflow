# Vital Sync — Weekly Cleanup

## Objective

Keep Content Pipeline and Search Bank small and fast to work with by moving
fully-processed rows out to dedicated archive tabs, without ever actually
losing data. This automates what the user was previously doing by hand —
manually clearing Content Pipeline every day (see
[[project_manual_approval_and_pipeline_cleanup]] in memory).

This is a maintenance/housekeeping job, not a pipeline stage — it doesn't
sit in the Workflow 00→01→02→03 numbered flow, so it isn't numbered either.

## What gets archived (deliberately conservative)

| Sheet | Archived when | Left alone |
|---|---|---|
| **Content Pipeline** | `Status` is `HeyGen Queued` or `Rewrite Required` | `Draft`, `Ready for Video`, `Review Required` — anything still in flight |
| **Search Bank** | `Status` is `Used` | `Unused`, `Processing` (Workflow 01's territory), `Rejected`/`Duplicate`/`Failed` (require a human reset per Workflow 01's own documented lifecycle — archiving them would remove the human's chance to notice and retry) |

This means a cleanup run mid-week, or on a day the user hasn't manually
approved/queued anything yet, is always safe — nothing awaiting a decision
ever gets swept up.

## Destination tabs

**Content Pipeline Archive** and **Search Bank Archive** — created
automatically on first run (`sheets_io.create_tab`, idempotent) with the
same columns as their source tab plus one extra: `Archived Date`. Nothing
about the source tabs' own columns changes.

## Tool

`tools/weekly_cleanup.py`.

```bash
# Always dry-run first — shows exactly what would move, no writes/email.
python tools/weekly_cleanup.py --dry-run

# Real run: archives, deletes from the source tab, logs, emails.
python tools/weekly_cleanup.py --live --trigger manual

# Used by launchd only:
python tools/weekly_cleanup.py --live --trigger scheduled
```

Run inside the project venv: `.venv/bin/python tools/weekly_cleanup.py ...`

No AI calls — pure Sheets I/O, same as Workflow 03.

## How archiving works (and why nothing can be lost)

For each sheet, eligible rows are appended to the archive tab **first**;
only after that append succeeds are the matching rows deleted from the
source tab (`sheets_io.delete_rows` — deletes by internal row index,
highest-index-first within one batch so deleting one row never shifts the
index of another row still waiting to be deleted in the same run).

**Idempotency / crash safety:** before archiving, the tool reads the
archive tab's existing rows and builds a set of already-archived IDs
(`ID` for Content Pipeline, `Search ID` for Search Bank). A candidate row
whose ID is already in the archive is never re-appended — it's just
deleted from the source (cleaning up a stray leftover from a prior run
where the append succeeded but the delete step failed for some reason).
This is the same defensive pattern Workflow 03 uses against HeyGen Queue:
the archive itself is the source of truth for "already archived," not the
source sheet's state.

If the archive append fails outright, nothing is deleted — the source rows
stay exactly as they were and get picked up again on the next run.

## Logging & email

Same paired `started`/`completed` (or `skipped`, on self-overlap) pattern
as the other workflows, logged to the existing Automation Logs under
`Vital Sync Weekly Cleanup`. Self-overlap lock only (90-minute stale-run
timeout) — no cross-workflow wait, since this tool only ever touches rows
already in a terminal state that no other workflow will revisit.

Summary email always sent (even on a 0-row no-op run, so a quiet week is
still visibly confirmed): counts found/archived per sheet, duration, errors.

## Schedule

Weekly, **Sunday 2:00 AM Asia/Dubai** (`StartCalendarInterval` Weekday=0,
Hour=2, Minute=0, system local time — same UTC+4 clock the other
`launchd` jobs use) — ahead of Workflow 00's ~7:52 AM Sunday run, so the
week starts with clean sheets. Label:
`com.vitalsync.weeklycleanup` —
`~/Library/LaunchAgents/com.vitalsync.weeklycleanup.plist`, same inline
`/bin/bash -c "cd ... && '<venv>/bin/python' -u '<abs path>/tools/weekly_cleanup.py' --live --trigger scheduled >> tmp/weekly_cleanup_scheduled.log 2>&1"`
pattern as the other jobs (absolute paths, no reference to a wrapper
script — see Workflow 01's "Known constraints" for why).

## Verified (2026-08-11)

Live-tested against real data, not fixtures: 10 Content Pipeline rows
(`HeyGen Queued`) and 40 Search Bank rows (`Used`) archived cleanly on the
first run; the 10 Content Pipeline rows still `Review Required` (today's
in-flight batch) were correctly left untouched. Immediate second run found
0 eligible rows in both sheets — clean no-op, confirming idempotency.
