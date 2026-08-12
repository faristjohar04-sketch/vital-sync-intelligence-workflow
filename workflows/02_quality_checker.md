# Workflow 02 — Vital Sync Quality Checker

## Objective

Automatically review every newly generated content package from Workflow 01
and determine whether it is ready for video generation: score it against
Vital Sync's brand/quality bar, and decide Approved / Needs Review /
Rejected. This workflow **only evaluates**. It never generates new content,
never publishes, never creates videos, and never modifies Workflow 01.

## Status naming (read this first)

The original spec for this workflow describes the input state as
`Status = Generated`. The live Content Pipeline sheet — and Workflow 01's
own docs — use the literal string **`Draft`** for freshly generated,
not-yet-reviewed rows (Workflow 01 explicitly hands off "Draft rows" to
this workflow). There is no separate `Generated` status anywhere in the
sheet. `tools/quality_check.py` therefore filters on `Status == "Draft"`
(see `STATUS_INPUT` in the tool). If a distinct `Generated` status is ever
introduced upstream, update that constant.

## Source of truth

Same Google Sheet as Workflow 01: `GOOGLE_SHEET_ID` in `.env`. Tabs used:

- **Brand Guidelines** — read-only, for scoring context.
- **Content Pipeline** — read fresh every run; this workflow only ever
  writes to the columns listed below, and only on rows it selected this run.
- **Automation Logs** — read (for overlap/locking against both this
  workflow's own history and Workflow 01's) and appended to.

Nothing about locking, batching, or scheduling is derived from local memory
or temp files — everything is recomputed fresh from Automation Logs and
Content Pipeline on every run.

## Input selection

Process only rows where:

```
Status   == "Draft"     (see "Status naming" above)
Approval == "Pending"
```

Every other row is skipped, including rows already `Approved`, `Needs
Review`, or `Rejected` — those are never touched again by this workflow.

## Tool

`tools/quality_check.py` — the deterministic orchestrator. Claude's job is
to decide when/how to invoke it and interpret the result, not reimplement
its logic by hand.

```bash
# Step 1 — always dry-run first. No OpenAI calls, no writes. Confirms sheet
# connectivity/auth and shows exactly which rows would be evaluated.
python tools/quality_check.py --dry-run

# Step 2 — the real run. Makes paid OpenAI calls and writes to the sheet.
# Get the user's go-ahead before running this, per CLAUDE.md's rule on paid
# API calls.
python tools/quality_check.py --live --trigger manual

# Optional flags
python tools/quality_check.py --live --batch-size 3   # override batch size
python tools/quality_check.py --live --no-email        # skip summary email
python tools/quality_check.py --live --trigger scheduled  # used by launchd only
```

Run inside the project venv: `.venv/bin/python tools/quality_check.py ...`

## Inputs

- `.env`: `OPENAI_API_KEY`, `OPENAI_MODEL` (fallback model), `QUALITY_CHECK_MODEL`
  (optional override — evaluation doesn't need the same model as generation;
  defaults to `OPENAI_MODEL`), `GOOGLE_SHEET_ID`, `SUMMARY_EMAIL_TO`,
  `QUALITY_CHECK_BATCH_SIZE` (default `10`), `QUALITY_CHECK_WF01_WAIT_MINUTES`
  (default `30` — see "Workflow ordering" below).
- Reuses the same `credentials.json` / `token.json` as Workflow 01 (same
  OAuth scopes: Sheets + Gmail).

## Quality checks and scoring

Each selected row is evaluated on two tracks that are then combined:

**Deterministic (Python, no AI cost, no ambiguity):**
- Hashtags: exactly 5 `#`-prefixed tokens required. A violation doesn't
  reject the row outright (hashtags aren't part of the weighted score below)
  but caps the overall score at 89 — it can never reach Approved until fixed.
- Script length: 45–80 words. Outside that range, a compliance factor
  (1.0 in range, decaying to 0 by ±40 words out) scales down the script
  sub-score rather than hard-failing.
- Generic/banned CTA phrases ("follow for more", "like this video", "comment
  below"): caps the CTA sub-score at 15.
- Banned phrase list (reused/extended from Workflow 01's list): caps brand
  voice sub-score at 20 and is folded into safety violations.
- Duplicate detection: exact-match (case-insensitive) comparison of Topic,
  Hook, Script, Caption, and Search Query against every other Content
  Pipeline row (approved, rejected, or pending — the whole sheet). Any exact
  match is a **hard reject**, regardless of score.

**AI-scored (one OpenAI JSON-mode call per row, retried up to twice on
transient/malformed-response failure):**
- Hook score (1–10): curiosity, clarity, scroll-stopping, relevance,
  specificity. A score below 7 caps the overall score at 89 (never fully
  Approved), per spec.
- Script score (0–100): natural spoken English, logical flow, one clear
  lesson, no repetition/filler, easy to understand. Combined with the
  deterministic length-compliance factor above.
- Brand voice score (0–100): premium/athletic/modern/scientific/helpful/
  confident/practical tone; scored 0–20 if any reject-list characteristic
  (clickbait, bro-science, military/cyberpunk language, fake urgency, fear
  tactics, medical claims) is present.
- CTA score (0–100): natural, specific, matches the content.
- Grammar score (0–100): grammar, spelling, capitalization, punctuation.
- Readability score (0–100): target grade 6–8, easy to read aloud.
- Safety violations (medical advice, dangerous advice, guaranteed results,
  unsupported claims): any entry here is a **hard reject**, same as
  duplicates.

**Overall Quality Score (0–100):**

```
hook_score×10 × 20%  +  script_score × 30%  +  brand_voice_score × 20%
+ cta_score × 10%  +  grammar_score × 10%  +  readability_score × 10%
```

then capped per the hashtag/hook-score rules above, and capped below 75 if
a hard-reject condition (duplicate or safety violation) fired.

## Decision

| Condition | Approval | Status |
|---|---|---|
| Duplicate or safety violation (hard reject) | Rejected | Rewrite Required |
| Score ≥ 90 | Approved | Ready for Video |
| Score 75–89 | Needs Review | Review Required |
| Score < 75 | Rejected | Rewrite Required |

Review Notes always explains every contributing reason (duplicates, safety
hits, brand-voice violations, hashtag count, script length, generic CTA,
grammar issues, low hook score, plus the AI's own summary) so nothing is a
silent score — this satisfies the "explain every reason" requirement for
rejections and gives reviewers something actionable for Needs Review.

## Google Sheets — write scope

Writes only: `Quality Score, Hook Score, CTA Score, Grammar Score,
Readability Score, Brand Voice Score, Review Notes, Date Checked, Approval,
Status`. Never touches `Script, Hook, Caption, Topic, Search Query`, or any
other column. All updates for a run are gathered and sent as a single
`batchUpdate` call (mirrors Workflow 01's approach to keeping API call count
constant regardless of batch size), wrapped in a retry-twice helper.

## Logging

One `started` and one `completed` (or `skipped`) row per run in Automation
Logs, same paired-marker pattern as Workflow 01, keyed by this workflow's own
name (`Vital Sync Quality Checker`) so the two workflows' locks never
collide. Run details (Run ID, rows checked, approved/needs-review/rejected
counts, errors, warnings, duration, avg/high/low score) are packed as JSON
into the `Errors` cell, same reasoning as Workflow 01 (`Automation Logs` only
has 5 columns).

## Email

Subject: `Vital Sync Quality Checker Report`. Sent only when at least one row
was processed (a no-op run with zero eligible rows doesn't send an email —
same behavior as Workflow 01). Includes Rows Checked, Approved, Needs
Review, Rejected, Average/Highest/Lowest Score, Errors, Duration.

## Workflow ordering (never process the same rows simultaneously)

Two separate mechanisms:

1. **Self-overlap lock** (same pattern as Workflow 01): before starting,
   scan Automation Logs for an unresolved `started` marker under this
   workflow's own name younger than `STALE_RUN_TIMEOUT_MINUTES` (90). If
   found, log a `skipped` row and exit — a second Workflow 02 run can never
   double-process rows.
2. **Cross-workflow wait for Workflow 01**: before touching Content
   Pipeline, scan Automation Logs for an unresolved Workflow 01
   (`Vital Sync Script Factory`) `started` marker. If found, poll every 30s
   for up to `QUALITY_CHECK_WF01_WAIT_MINUTES` (default 30) waiting for it to
   resolve. This is a bounded wait, not an indefinite block: if Workflow 01
   is still running after the timeout, Workflow 02 proceeds anyway (logging
   `workflow01_still_active: true` in its run summary) rather than silently
   skipping the day's QC pass. In practice this is a safety net — Workflow 01
   runs at 8:00 AM and Workflow 02 at 9:00 AM, a full hour of buffer, and
   Workflow 02 never appends new rows or touches anything Workflow 01
   writes, so even a genuine overlap can't corrupt data — the wait exists to
   honor "never run at the same time" as closely as possible without risking
   an indefinite hang if Workflow 01 ever crashes mid-run without resolving
   its own lock. `check_overlap_and_compute_streak` in Workflow 01's own code
   was **not modified** to add this — Workflow 02 only reads Automation Logs.

## Idempotency

Once a row is scored, its `Approval` becomes `Approved`/`Needs Review`/
`Rejected` (no longer `Pending`), so a re-run's fresh read of the sheet
naturally excludes it. Running the workflow twice never reprocesses a row
that already has a decision — no manual cleanup is ever required.

## Failure handling

- Google Sheets calls (reads/writes): retried up to twice with backoff
  (`with_sheets_retry` / `MAX_SHEETS_RETRIES`).
- Per-row AI evaluation: retried up to twice on request failure, invalid
  JSON, or missing required fields (`MAX_AI_RETRIES`).
- If a single row still fails after retries: logged in the run's `errors`
  list, the row is left untouched (still `Draft`/`Pending`, so it's picked
  up automatically on the next run), and processing continues — one bad row
  never stops the batch or the workflow.
- Missing `.env` values → the tool exits immediately with a clear error
  before making any API calls.

## Scheduled run (daily, 9:00 AM Asia/Dubai)

A second `launchd` LaunchAgent runs this workflow automatically every day,
one hour after Workflow 01's 8:00 AM job.

- **Label/plist**: `com.vitalsync.mqualitychecker` —
  `~/Library/LaunchAgents/com.vitalsync.mqualitychecker.plist`. (Not
  `com.vitalsync.qualitychecker` — that label was never functional and is
  retired; see Workflow 01's "Known constraints / learnings" for the full
  diagnostic story, which applies identically here.)
- **Command**: inlined directly in the plist as `/bin/bash -c "cd ... &&
  '<abs path>/.venv/bin/python' -u '<abs path>/tools/quality_check.py'
  --live --trigger scheduled >> tmp/quality_check_scheduled.log 2>&1"` —
  every path absolute, no reference to `tools/run_quality_check_scheduled.sh`
  (that script still works fine manually; launchd doesn't use it — see
  Workflow 01's notes on why external script files are unreliable here).
- **Schedule**: `StartCalendarInterval` Hour=9, Minute=0, system local time.
  This Mac's system clock is UTC+4, matching Asia/Dubai (no DST in either),
  same reasoning as Workflow 01 — re-check `date +%Z` if this ever moves to
  a different machine.
- **Manual trigger preserved**: `--trigger manual` remains fully available
  side-by-side for testing and never interferes with the scheduled run's
  overlap lock.
- **Requires Full Disk Access for `/bin/bash`** (System Settings → Privacy
  & Security → Full Disk Access) — this project lives under `~/Downloads`,
  a TCC-protected folder; without this grant, `launchd`-spawned reads of
  `.venv/pyvenv.cfg` and other project files fail with `PermissionError:
  Operation not permitted` even after the process itself spawns
  successfully. Granted 2026-08-08.

Useful commands:

```bash
# Check it's loaded
launchctl print gui/$(id -u)/com.vitalsync.mqualitychecker

# Run it immediately, outside the schedule, for testing (a real --live
# run when the plist has the production command)
launchctl kickstart -p gui/$(id -u)/com.vitalsync.mqualitychecker

# Watch the log
tail -f tmp/quality_check_scheduled.log

# Disable (stop future runs) without deleting the plist
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.vitalsync.mqualitychecker.plist

# Re-enable later
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.vitalsync.mqualitychecker.plist
```

## Known constraints / learnings

- Reuses the venv setup and Google OAuth caveats documented in Workflow 01
  (`workflows/01_script_factory.md`) — same Python 3.9 venv at `.venv/`,
  same `credentials.json`/`token.json`.
- The Content Pipeline sheet as of 2026-07-30 has no `Script Score` column,
  and the spec's own "GOOGLE SHEETS — write" list doesn't include one either
  — Script's 30% scoring weight is folded into the Quality Score
  calculation only, not written as its own column.
- See Workflow 01's "Known constraints / learnings" section for the full
  2026-08-08 diagnostic on getting `launchd` to actually execute these jobs
  (reboot to clear a stale `posix_spawn` block, absolute paths only, Full
  Disk Access for `/bin/bash`, inline commands instead of script-file
  references) — identical fix applied to both jobs.
