# Workflow 01 — Vital Sync Script Factory

## Objective

Generate high-quality, on-brand short-form video content (hook, script, caption,
hashtags, CTA, etc.) from unused topics in the Search Bank, and append it to the
Content Pipeline for downstream review.

This workflow **only generates content**. It never creates videos, publishes
content, performs quality control, or reads analytics — those are Workflows
02–05.

## Source of truth

Google Sheet: `https://docs.google.com/spreadsheets/d/1-5FXa8Qg0dYwOjP-eD83tkoqaWPL5YlZaY5ICC0VPE8`
(ID stored in `.env` as `GOOGLE_SHEET_ID`). Tabs used:

- **Brand Guidelines** — `Field` / `Value` pairs (Brand, Catchphrase, Mission, Tone, Avoid).
- **Search Bank** — candidate topics. Columns: `Search Query, Topic, Category,
  Search Intent, Difficulty, Search Score, Trend Score, Follower Potential,
  Product Opportunity, Status`. `Status` follows a strict lifecycle (see
  below) — only rows with `Status = Unused` are ever selected.
- **Content Pipeline** — output. Columns: `ID, Brand, Status, Priority, Content
  Pillar, Content Type, Search Query, Topic, Hook, Problem, Cause, Solution,
  CTA, Script, Caption, On-Screen Text, Hashtags, Promotion, Avatar, Platform,
  Date Generated, Approval, Video URL, Published, Quality Score, Hook Score,
  CTA Score, Grammar Score, Readability Score, Brand Voice Score, Review
  Notes, Date Checked`.
- **Automation Logs** — Columns: `Date, Workflow, Success, Time, Errors`. Since
  this tab only has 5 columns, the richer run details required by CLAUDE.md
  (items processed/failed, retry count, per-item failures) are packed as a
  JSON string into the `Errors` cell rather than adding new columns to a
  shared sheet.

Never assume cached data is current — every run reads these tabs fresh, and
nothing about scheduling, locking, or batch-size decisions is ever derived
from local memory or temp files — it's all recomputed from Automation Logs
and Search Bank history on every run.

## Search Bank status lifecycle

```
Unused → Processing → Used
                    → Duplicate
                    → Failed
```

- **Unused** — eligible for selection.
- **Processing** — reserved by a run in progress. Set immediately after
  selection, before any OpenAI call, so no other run can double-pick it.
- **Used** — its Content Pipeline row was generated, validated, *and*
  successfully appended.
- **Duplicate** — generation kept producing a topic/hook/script that exact-
  matched something already in Content Pipeline, even after retry.
- **Failed** — generation, validation, or the Content Pipeline append itself
  failed after retry.

Rows in `Processing`, `Used`, `Duplicate`, or `Failed` are never re-selected.
`Duplicate`/`Failed` rows require a human to reset them to `Unused` in the
sheet if they should be retried — this is intentional, not a bug: a topic
that failed twice needs a look, not an automatic infinite retry.

## Tool

`tools/generate_content.py` — the deterministic orchestrator. Claude's job is
to decide when/how to invoke it, interpret the result, and handle any
top-level failure (e.g. missing credentials) — not to reimplement its logic
by hand.

```
# Step 1 — always dry-run first. No OpenAI calls, no writes. Confirms sheet
# connectivity/auth and shows exactly which topics would be used.
python tools/generate_content.py --dry-run

# Step 2 — the real run. Makes paid OpenAI calls (gpt-4o) and writes to the
# sheet. Get the user's go-ahead before running this, per CLAUDE.md's rule on
# paid API calls.
python tools/generate_content.py --live --trigger manual

# Optional flags
python tools/generate_content.py --live --batch-size 3   # override auto batch size
python tools/generate_content.py --live --no-email        # skip summary email
python tools/generate_content.py --live --trigger scheduled  # used by launchd only
```

Run inside the project venv: `.venv/bin/python tools/generate_content.py ...`

## Inputs

- `.env`: `OPENAI_API_KEY`, `OPENAI_MODEL` (default `gpt-4o`), `GOOGLE_SHEET_ID`,
  `SUMMARY_EMAIL_TO`, `SCRIPT_FACTORY_BATCH_SIZE` (default `10`, the manual/
  starting batch size), `SCRIPT_FACTORY_ESCALATED_BATCH_SIZE` (default `100`,
  see auto-escalation below).
- `credentials.json` at project root — Google OAuth client (Desktop app) with
  the Sheets and Gmail APIs enabled. Never committed (gitignored).
- First run only: `flow.run_local_server()` opens a browser for one-time
  consent; the resulting token is cached at `token.json` (also gitignored),
  includes a refresh token, and auto-refreshes after that — no browser
  needed again, including for the unattended scheduled runs.

## Outputs

- New rows appended to **Content Pipeline** with `Status = Draft`,
  `Approval = Pending`, `Published = No`, and all QC score columns left
  blank (Workflow 02 fills those in later).
- Source **Search Bank** rows resolved to `Used`, `Duplicate`, or `Failed`
  per the lifecycle above.
- Two rows appended to **Automation Logs** per run: a `started` marker
  (written before any work begins) and a `completed` marker (written in a
  `finally` block, so it's written even if the run crashes) — or a single
  `skipped` row if a previous run was still active. See "Overlap prevention"
  below.
- One summary email to `SUMMARY_EMAIL_TO` (unless `--no-email`, `--dry-run`,
  or the run was skipped due to overlap).

## Step by step (what the tool does internally)

1. Read Automation Logs fresh; check for overlap (see below) and compute the
   scheduled clean-run streak. If another run is active, log a `skipped` row
   with the reason and stop — nothing else happens.
2. Write a `started` log row (run ID + trigger) before touching anything else.
3. Decide batch size (see auto-escalation below).
4. Read Search Bank fresh. Any row still `Processing` at this point is a
   stale leftover from a crashed run (self-heal) — reset it to `Unused` in
   one batch call and re-read the tab.
5. Read Brand Guidelines and Content Pipeline (existing Topic/Hook/Script
   sets for de-dup).
6. Rank `Unused` rows by `Search Score + Trend Score` (descending), take the
   top `batch_size`, and immediately mark them `Processing` in one batch
   call — this is the reservation step.
7. For each reserved topic, call OpenAI (JSON-mode) with the brand
   guidelines, the topic brief, and a sample of existing topics/hooks to
   avoid duplicating. One unexpected exception (network error, API error)
   is caught per item so it can't take down the rest of the batch.
8. Validate the returned JSON deterministically:
   - all required fields present and non-empty
   - exactly 5 hashtags, each starting with `#`
   - `promotion` is exactly `Yes` or `No`
   - topic/hook/script not an exact duplicate of anything already in Content
     Pipeline (or already generated earlier in this same run)
   - hook/CTA/caption/script don't contain an obvious banned/clickbait phrase
9. On validation failure: retry once with the specific errors fed back to
   the model. If it still fails, classify as `Duplicate` (if the only
   remaining errors were duplicate-content errors) or `Failed` (anything
   else) and continue — one bad item never stops the run.
10. Mark all `Duplicate`/`Failed` topics from this run in one batch call.
    Append all successful rows to Content Pipeline in a single batch call;
    only if that append succeeds, mark those topics `Used` in one more batch
    call. If the append itself throws, none of those topics get marked
    `Used` — they're marked `Failed` instead, since we can't be sure what
    was actually written.
11. Write the `completed` log row (counts, streak, `clean` flag).
12. Email the summary (counts, new IDs/topics, duplicates, failures) to
    `SUMMARY_EMAIL_TO`.

This keeps total Sheets API calls small and constant regardless of batch
size (roughly a dozen calls whether the batch is 10 or 100), which is what
makes the 100-item scheduled batch safe against rate limits.

## Overlap prevention (no lock files — the sheet is the lock)

Every run writes a `started` marker to Automation Logs (with a random run
ID) before doing anything else, and a `completed` (or `skipped`) marker with
the same run ID when it finishes. Before starting real work, a run scans
Automation Logs for any `started` marker with no matching `completed`/
`skipped` marker:

- If one exists **and** is less than `STALE_RUN_TIMEOUT_MINUTES` (90) old →
  treat it as still active, log a `skipped` row with the reason, and exit
  without touching Search Bank or Content Pipeline.
- If one exists but is **older** than 90 minutes → treat it as a crashed run,
  not active. Proceed normally (and self-heal any `Processing` rows it left
  behind, per step 4 above).

This means a crashed run self-recovers within 90 minutes with no manual
cleanup, matching the "never require manual resetting between runs" rule —
the only exception is topics that individually ended up `Duplicate`/`Failed`,
which are deliberately left for human review rather than auto-retried.

## Batch size auto-escalation (scheduled runs only)

- Manual runs (`--trigger manual`, the default) always use
  `SCRIPT_FACTORY_BATCH_SIZE` (10) unless `--batch-size` is passed explicitly.
- Scheduled runs (`--trigger scheduled`, used only by the launchd job) start
  at 10 too, but auto-escalate to `SCRIPT_FACTORY_ESCALATED_BATCH_SIZE` (100)
  once the most recent `ESCALATION_STREAK_THRESHOLD` (3) **consecutive**
  scheduled runs were all "clean" — `items_failed == 0`,
  `items_duplicate == 0`, and `reclaimed_stuck_rows == 0`.
- The streak is recomputed fresh from Automation Logs history every run (not
  stored anywhere) — manual runs are ignored entirely when computing it, so
  testing manually never advances or resets the scheduled streak. If a
  scheduled run comes back unclean after escalating, the very next scheduled
  run automatically drops back to batch size 10 until three more consecutive
  clean runs rebuild the streak.
- `--batch-size` always overrides this logic entirely, for both triggers.

## Idempotency

Re-running the workflow never duplicates work: only topics that produced
valid content **and** a successful Content Pipeline append get marked
`Used`, and topic selection always re-reads the sheet fresh, so a second run
naturally picks the next batch of `Unused` topics rather than regenerating
the same ones. Overlap prevention additionally guarantees two runs can never
process the same topics concurrently.

## Scheduled run (daily, 8:00 AM Asia/Dubai)

A `launchd` LaunchAgent runs this workflow automatically every day —
`--trigger scheduled` is the only difference from a manual run.

- **Label/plist**: `com.vitalsync.mscriptfactory` —
  `~/Library/LaunchAgents/com.vitalsync.mscriptfactory.plist`. (Not
  `com.vitalsync.scriptfactory` — that label is permanently retired, see
  "Known constraints / learnings" below. Don't recreate anything under it.)
- **Command**: the plist's `ProgramArguments` inlines the full command
  directly as `/bin/bash -c "cd ... && '<abs path>/.venv/bin/python' -u
  '<abs path>/tools/generate_content.py' --live --trigger scheduled >>
  tmp/script_factory_scheduled.log 2>&1"` — every path is absolute. It does
  **not** call `tools/run_scheduled.sh` (that script still exists and works
  fine for manual/interactive use, but launchd itself cannot execute it —
  see below).
- **Schedule**: `StartCalendarInterval` Hour=8, Minute=0, in the *system's
  local time*. On this Mac the system clock is already UTC+4 — the same
  offset as Asia/Dubai (no DST in either), so no timezone conversion was
  needed. If this job is ever moved to a different Mac, re-check
  `date +%Z` there and adjust the Hour if its system timezone differs.
- **Why local, not a cloud routine**: cloud-scheduled agents run in an
  isolated sandbox with no access to this machine's `credentials.json`,
  `token.json`, or `.env` — and this repo has no GitHub remote or other
  mechanism to get those secrets there safely. A local `launchd` job reuses
  the exact same venv/credentials already set up here, so no secrets need
  to move anywhere.
- **Requirement**: the Mac must be powered on and awake at 8:00 AM daily —
  `launchd` does not reliably catch up a `StartCalendarInterval` job that
  was missed while asleep/off. `com.vitalsync.macstaywake` (7:58 AM,
  `caffeinate -s -t 9000`) exists specifically to guarantee this through
  both this job and Workflow 02's 9:00 AM job.

Useful commands:

```bash
# Check it's loaded
launchctl print gui/$(id -u)/com.vitalsync.mscriptfactory

# Run it immediately, outside the schedule, for testing (this IS a real
# --live run when the plist has the production command — see below)
launchctl kickstart -p gui/$(id -u)/com.vitalsync.mscriptfactory

# Watch the log
tail -f tmp/script_factory_scheduled.log

# Disable (stop future runs) without deleting the plist
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.vitalsync.mscriptfactory.plist

# Re-enable later
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.vitalsync.mscriptfactory.plist
```

Manual testing (`--trigger manual`) remains fully available side-by-side and
never interferes with the scheduled run's overlap lock or escalation streak.

### Known constraints / learnings — getting `launchd` to actually run this

This took a full diagnostic session (2026-08-08) to get right; the short
version, so it's never re-litigated:

1. **`com.vitalsync.scriptfactory` (the original label) is permanently
   broken and must never be reused.** `launchctl print` showed it as loaded
   and `bootstrap` always returned success, but it had **never once actually
   fired** — every real spawn attempt failed deep in `xpcproxy` with
   `posix_spawn(...), error 0x1 - Operation not permitted`, confirmed via
   `log show --predicate 'process == "launchd"'`. `sfltool dumpbtm` showed
   the item as `[enabled, allowed, notified]` the whole time — Background
   Task Management's own disposition is not a reliable signal that a job
   can actually run. A **reboot** cleared this specific block (a stale
   per-session security cache, not a permanent per-label ban as it first
   appeared — a fresh label tried before rebooting also failed identically,
   which is why the fix looked label-specific until the reboot test).
2. Separately, this whole project lives under `~/Downloads/...`, one of
   macOS's TCC-protected special folders. Even after the reboot fixed the
   spawn-level block, `launchd`-spawned processes still couldn't **read**
   files inside the project (`.venv/pyvenv.cfg`, etc. — `PermissionError:
   Operation not permitted`), and relative paths like `.venv/bin/python`
   failed to resolve for the same reason, even though executing an already-
   known **absolute** path worked. Fix required two things: (a) every path
   in the launchd command must be absolute, never relative to a `cd`'d
   working directory, and (b) granting **Full Disk Access to `/bin/bash`**
   in System Settings → Privacy & Security → Full Disk Access (a one-time,
   GUI-only action — there's no command-line equivalent).
3. Pointing `ProgramArguments` at an external `.sh` file (`bash
   /path/to/script.sh`) is unreliable from this environment — files written
   into this project directory (by any method, including plain shell
   redirection) can pick up a `com.apple.provenance` extended attribute
   that isn't removable with `xattr -d`, and `launchd` sometimes refuses to
   exec such a file even when a plain inline command works fine. The
   resilient pattern is to inline the entire command as a single
   `/bin/bash -c "..."` string directly in the plist, with no reference to
   any script file at all. `tools/run_scheduled.sh` is kept around only for
   convenient manual invocation — launchd does not use it.
4. Diagnostic commands worth remembering if this ever regresses:
   `log show --last 5m --predicate 'process == "launchd"' | grep <label>`
   (find the exact `posix_spawn` failure and target), `sfltool dumpbtm |
   grep -B8 <label>` (BTM disposition — often unhelpful, as above), and
   `launchctl kickstart -p gui/$(id -u)/<label>` (force an immediate run
   without waiting for the schedule — safe to do with `--dry-run` swapped
   in temporarily before trusting a `--live` config change).

## Validation limits (by design)

The checks above are structural/deterministic, not semantic. They catch
malformed output and exact duplicates, but do not score brand-voice fit,
hook quality, grammar, or readability — those live in **Workflow 02 —
Quality Checker**, which is expected to run against `Status = Draft` rows
next and fill in the QC score columns.

**Script length must match Workflow 02's rubric exactly.** The generation
prompt targets 45-80 words (~15-25 seconds spoken) in `build_prompt()`.
This was originally written as "60-90 seconds spoken" (~150-225 words at
normal speaking pace) — nothing in Workflow 01's own validation caught the
mismatch, so it silently produced scripts 2-3x too long, all of which
Workflow 02 then rejected on length alone despite otherwise-good content
(caught and fixed 2026-08-09, see `workflows/02_quality_checker.md`'s
"Quality checks and scoring" section for the exact word-count check). If
rewrite-required rows start clustering around a "SCRIPT LENGTH" review note
again, check this prompt first before assuming a content-quality problem.

## Failure handling

- Missing `.env` values or `credentials.json` → the tool exits immediately
  with a clear error before making any API calls.
- A single topic's generation/validation failure → marked `Duplicate` or
  `Failed`, logged, run continues (see steps 7–10 above) — never crashes the
  batch.
- Sheet API errors (rate limit, auth expiry) → surface the traceback to
  Claude, who should read it, fix the root cause (e.g. re-auth, retry with
  backoff), and only re-run `--live` after confirming with the user if the
  prior run may have partially written data (check Content Pipeline/Search
  Bank for partial results before re-running to avoid burning OpenAI credits
  on topics already completed).

## Known constraints / learnings

- The system's default `python3` (3.7.2, `/usr/local/bin`) is EOL and can't
  build modern dependencies (`cryptography` fails). Use the project venv at
  `.venv/` (built from Apple's native arm64 `/usr/bin/python3`, 3.9.6)
  instead: `.venv/bin/python tools/generate_content.py ...`. On this
  machine, avoid the Anaconda `python3.12` — it's an x86_64 (Rosetta)
  build and fails to install `cryptography` from source (no native wheel
  match, no local OpenSSL/pkg-config).
- The Google Sheet is viewable via the public `gviz/tq?tqx=out:csv` export
  endpoint, which is how this workflow's schema was confirmed without
  needing OAuth set up yet — useful for quick schema checks, but the actual
  tool always uses the authenticated Sheets API for reads/writes.
