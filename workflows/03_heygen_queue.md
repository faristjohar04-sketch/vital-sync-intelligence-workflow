# Workflow 03 — Vital Sync HeyGen Production Queue

## Objective

Take Content Pipeline rows that have already been approved by Workflow 02
(`Approval = Approved`, `Status = Ready for Video`) and package each one into
a clean, structured, HeyGen-ready production package appended to a dedicated
**HeyGen Queue** tab.

This workflow **only packages approved content for production**. It never
generates new topics, never rewrites an approved script, never performs
quality control, never calls the HeyGen API, never generates a video, never
publishes, and never analyzes performance. Those are other workflows (01, 02)
or not yet built (video generation/publishing).

## Trigger

**Manual only.** Node/command name: `Manual Run — HeyGen Queue`. This
workflow is intentionally never scheduled via `launchd` — moving approved
scripts into video production stays a deliberate human decision.

## Source of truth

Same Google Sheet as Workflows 01/02: `GOOGLE_SHEET_ID` in `.env`. Tabs used:

- **Content Pipeline** — read fresh every run; this workflow only ever
  writes `Status` (and `HeyGen Queue ID` / `HeyGen Queued Date` /
  `Automation Result` if those columns exist — they don't yet on the live
  sheet), and only on rows it successfully queued this run. Never touches
  `Script, Hook, CTA, Caption, Quality Score`, `Approval`, or `Published`.
- **HeyGen Queue** — created by this project (didn't previously exist on the
  live sheet; added via `sheets_io.create_tab`, see "Setup" below). Appended
  to, never cleared, never overwritten, never deleted from.
- **Avatar Library** — created by this project (also didn't previously
  exist). Read-only. Maps a coach type to its HeyGen Avatar ID / Voice ID
  and delivery defaults. **This tool never invents an avatar/voice ID** — an
  unmatched coach becomes `Needs Avatar Review`, not a guess.
- **Automation Logs** — read (for this workflow's own self-overlap lock) and
  appended to.

Nothing is derived from local memory, temp files, or pinned/cached data —
every run reads all four tabs fresh.

## Setup (one-time)

`HeyGen Queue` and `Avatar Library` didn't exist on the live
`Vital_Sync_Content_Engine_v2` sheet before this workflow was built. Created
once via:

```bash
python tools/sheets_io.py create-tab "HeyGen Queue" --headers "Queue ID,Content ID,Brand,Content Pillar,Coach,Hook,Script,CTA,Caption,On-Screen Text,Hashtags,Promotion,Avatar Name,Avatar ID,Voice Name,Voice ID,Video Orientation,Target Duration,Delivery Style,Visual Style,Queue Status,Date Queued,Source Row Number,Video URL,Notes"

python tools/sheets_io.py create-tab "Avatar Library" --headers "Coach Type,Avatar ID,Avatar Name,Voice ID,Voice Name,Gender,Delivery Style,Default Emotion"
```

`create_tab` is idempotent (checks the tab list first, never touches an
existing tab), so re-running it is always safe.

**Avatar Library starts empty.** Until real HeyGen Avatar ID / Voice ID rows
are added (one row per coach type — `Fitness Coach`, `Nutrition Coach`,
`Recovery Specialist`, as available), every candidate resolves to `Needs
Avatar Review` rather than queuing — this is correct behavior per spec
("do not invent one"), not a bug.

## Content Pillar resolution (read this first)

The spec's Step 4 validation requires `Content Pillar` to be one of
`Fitness, Nutrition, Recovery`. Content Pipeline's own `Content Pillar`
column (written by Workflow 01) is far more granular in practice — live
values include `Training`, `Mindset`, `Recovery Nutrition`, `Building
Sustainable Habits` — none of which match that three-value list.

Content Pipeline's `Avatar` column, however, is already written by Workflow
01 as a resolved coach-type string (`Fitness Coach`, `Nutrition Coach`,
`Recovery Specialist`) rather than a bare pillar keyword. So this tool
derives the HeyGen package's `Content Pillar` from the matched coach type
(`Fitness Coach` → `Fitness`, `Nutrition Coach` → `Nutrition`, `Recovery
Specialist` → `Recovery`) instead of from the raw `Content Pillar` column.
`COACH_TO_PILLAR` in `tools/build_heygen_queue.py` is the single source of
truth for this mapping. Content Pipeline's own `Content Pillar` value is
still required to be non-empty for a row to become a candidate (Step 1 gate)
but is not itself validated against the three-value list.

Note: the original spec's Step 2 also listed a `Discipline Coach` mapping,
but since its own Step 4 allowed-pillar list never included "Discipline",
that path could resolve an avatar but never actually pass validation — a
dead path. It was dropped entirely (not just left unpopulated) from
`COACH_TYPES` / `PILLAR_KEYWORD_TO_COACH` / `COACH_TO_PILLAR` in
`tools/build_heygen_queue.py` per explicit instruction, rather than kept
around as unreachable code.

## Tool

`tools/build_heygen_queue.py` — the deterministic orchestrator. Claude's job
is to decide when to run it and interpret the result, not to hand-build
queue rows itself.

```bash
# Step 1 — always dry-run first. No writes, no email. Shows exactly which
# Content Pipeline rows would be processed.
python tools/build_heygen_queue.py --dry-run

# Step 2 — the real run. No paid API calls (this tool makes zero AI calls),
# but does write to the sheet and send an email — still a real run.
python tools/build_heygen_queue.py --live --trigger manual

# Optional
python tools/build_heygen_queue.py --live --no-email
```

Run inside the project venv: `.venv/bin/python tools/build_heygen_queue.py ...`

Unlike Workflows 01/02, this tool makes no OpenAI calls at all — it's pure
Python validation and Sheets I/O — so there's no "paid API" gate before a
`--live` run. The Google Sheets writes themselves are still real, so it's
still worth a dry-run first.

## Inputs

- `.env`: `GOOGLE_SHEET_ID`, `SUMMARY_EMAIL_TO`. No AI model/key needed.
- Reuses the same `credentials.json` / `token.json` as Workflows 01/02
  (same OAuth scopes: Sheets + Gmail).

## Step by step

1. **Select candidates** — Content Pipeline rows where `Approval = Approved`
   AND `Status = Ready for Video`, AND `ID`, `Script`, `Hook`, `Content
   Pillar`, `Avatar` are all non-empty. Rows failing the non-empty check are
   excluded from the candidate set entirely (not logged as a per-row
   result) — this mirrors the spec's Step 1 wording literally. Any other
   `Status` (`HeyGen Queued`, `Video Processing`, `Video Complete`,
   `Published`, `Rejected`, `Needs Review`) is excluded by the exact-match
   filter itself.
2. **Read Avatar Library** and index by `Coach Type` (case-insensitive).
3. **Read HeyGen Queue** and build the set of already-present `Content ID`s
   — the dedup key for the whole workflow.
4. For each candidate, in order:
   - **Already Queued** — `Content ID` already in HeyGen Queue → skip, no
     new row, no Content Pipeline change.
   - **Needs Avatar Review** — `Avatar` doesn't resolve to a known coach
     type, or no Avatar Library row matches that coach type → logged, move
     on to the next candidate. Original row is untouched.
   - **Skipped — Missing Production Field** — resolves an avatar fine but
     fails validation (missing Caption/On-Screen Text/Hashtags, invalid
     Promotion value, or the pillar/coach checks above) → logs the exact
     missing/invalid field, original row untouched.
   - **Queued** — builds the production package (see below), appends one
     row to HeyGen Queue, then — only after that append succeeds — updates
     the Content Pipeline row's `Status` to `HeyGen Queued` (plus `HeyGen
     Queue ID` / `HeyGen Queued Date` / `Automation Result` if those columns
     exist). If the append itself fails, the row is logged **Queue Append
     Failed** and the original row's `Status` stays `Ready for Video` — it
     will be retried automatically on the next run.
5. Log one `completed` row to Automation Logs and send the summary email
   (see below) — always, even on a no-candidate run.

## Production package fields

`Queue ID, Content ID, Brand, Content Pillar, Coach, Hook, Script, CTA,
Caption, On-Screen Text, Hashtags, Promotion, Avatar Name, Avatar ID, Voice
Name, Voice ID, Video Orientation, Target Duration, Delivery Style, Visual
Style, Queue Status, Date Queued, Source Row Number, Video URL, Notes`

Fixed values on every row: `Brand = Vital Sync`, `Video Orientation = 9:16`,
`Target Duration = 15-30 seconds`, `Visual Style` = the premium/athletic
short-form description from the spec, `Queue Status = Ready`, `Video URL`
blank, `Date Queued` = current UTC timestamp. `Delivery Style` uses the
matched Avatar Library row's own value if present, else falls back to the
spec's default conversational/eye-contact/hand-gesture description.

**Script is copied verbatim** from Content Pipeline — this tool never
rewrites, trims, or rephrases an approved script.

## Queue ID format

`HG-VS-YYYYMMDD-RUNTOKEN-ITEMNUMBER`, e.g. `HG-VS-20260808-a91f3-001`.
`RUNTOKEN` is a random 5-character hex token generated once per run (not a
sequential run counter — no run counter exists anywhere in this system), so
IDs stay unique across runs without needing to track state. `ITEMNUMBER` is
a zero-padded, per-run counter that only increments for items that actually
reach the Queued state (skipped/needs-review/already-queued items don't
consume a number).

## Results tracked per candidate

`Content ID, Topic, Coach, Result, Queue ID, Error` — `Result` is one of
`Queued, Already Queued, Needs Avatar Review, Skipped — Missing Production
Field, Queue Append Failed`. One failed/skipped item never stops the batch —
every candidate is attempted.

## Logging

One `started` and one `completed` (or `skipped`, on self-overlap) row per
run in Automation Logs, same paired-marker pattern as Workflows 01/02, keyed
by this workflow's own name (`Vital Sync HeyGen Production Queue`). Run
details (Run ID, approved items found, items queued/already-queued/needs-
avatar-review/skipped/failed, queue IDs, per-item errors, duration) are
packed as JSON into the `Errors` cell, same reasoning as Workflows 01/02
(`Automation Logs` only has 5 columns). `Success = 1` if at least one item
was queued.

Self-overlap lock only (no cross-workflow wait): before starting, scans
Automation Logs for an unresolved `started` marker under this workflow's own
name younger than 90 minutes. Workflow 03 never touches rows Workflow 01/02
are still working on (it only selects rows already fully resolved to
`Approved` + `Ready for Video`), so no cross-workflow wait is needed the way
Workflow 02 waits on Workflow 01.

## Email

Subject: `Vital Sync HeyGen Queue Report — <YYYY-MM-DD>`. **Always sent**
(unlike Workflows 01/02, which skip the email on a zero-row run) — the
no-candidate path sends the exact fallback message from the spec: "No
approved Vital Sync scripts were ready for the HeyGen queue. No existing
data was changed." Otherwise includes Run ID, approved items found, items
queued, already queued, needs avatar review, skipped, failed, the list of
new Queue IDs, and any per-item errors.

## Idempotency

Two independent guarantees, both required by the spec's repeat-execution
tests:

1. **Content Pipeline side** — once a row is queued, its `Status` becomes
   `HeyGen Queued`, so the next run's fresh Step-1 filter (`Status = Ready
   for Video`) naturally excludes it.
2. **HeyGen Queue side** — even if the Content Pipeline `Status` write ever
   fails after a successful queue append (logged as a warning, not a
   failure — see the tool's inline comment), the `Content ID`-keyed dedup
   check against HeyGen Queue itself still prevents a duplicate row on the
   next run. This is the real source of truth for "already queued", not the
   Content Pipeline status.

Running the workflow twice in a row with nothing newly approved in between
is always a no-op after the first run.

## Failure handling

- Google Sheets calls (reads/writes): retried up to twice with backoff
  (`with_sheets_retry`).
- Per-row: a failed HeyGen Queue append is logged as `Queue Append Failed`
  and the original Content Pipeline row is left as `Ready for Video` (picked
  up automatically next run) — one bad row never stops the rest of the
  batch.
- Missing `.env` values (`GOOGLE_SHEET_ID`) → exits immediately with a clear
  error before any API calls.

## Known constraints / learnings

- `HeyGen Queue` and `Avatar Library` tabs did not exist on the live sheet
  before this workflow — created via the new `sheets_io.create_tab` /
  `sheets_io.list_tabs` helpers (also usable ad hoc: `python
  tools/sheets_io.py create-tab "<name>" --headers "a,b,c"`).
- Content Pipeline's `Content Pillar` column doesn't match the spec's
  three-value allowed-pillar list — see "Content Pillar resolution" above
  for the resolution (same kind of naming mismatch Workflow 02 hit and
  documented for `Status = Draft` vs the spec's `Generated`).
- `.env` already had `VIDEO_GEN_*` / `VIDEO_EDIT_*` settings and a
  `workflows/03_video_generator.md` reference left over from an earlier,
  different plan for "Workflow 03" (direct HeyGen video generation +
  editing). That file was never actually created and no code reads those
  video-gen/-edit settings today. This workflow is the current, narrower
  Workflow 03 (queue-building only, no HeyGen API calls) — those `.env`
  lines are stale/forward-looking, not a conflict, but worth cleaning up if
  a future workflow finally implements real HeyGen video generation under a
  different number.
- As of first build (2026-08-08), all 10 live Content Pipeline rows were
  still `Status = Draft` / `Approval = Pending` — none had been through
  Workflow 02 yet. For the required manual test, 2 rows (VS-001, VS-002)
  were flipped directly to `Approval = Approved` / `Status = Ready for
  Video` (bypassing Workflow 02's QC gate — no OpenAI cost) rather than
  running Workflow 02 live.
- Avatar Library also didn't exist before this build and started empty.
  First test run against it correctly produced `Needs Avatar Review` for
  both candidates and left the source rows untouched — proving Test 4's
  path before any real avatar data existed. Three real coach avatars were
  then added by resolving Avatar/Voice IDs against the live HeyGen API
  (`tools/heygen_lookup.py`, plus the `/v2/avatar_group.list` and
  `/v2/avatar_group/{id}/avatars` endpoints for custom photo avatars, which
  aren't returned by `/v2/avatars`) — see `tools/heygen_lookup.py`'s
  docstring. One gotcha hit during that lookup: a custom "photo avatar"
  group's **group ID** is not itself a usable Avatar ID — the actual
  avatar_id to use is the "look" nested inside that group
  (`/v2/avatar_group/{group_id}/avatars`). The Fitness Coach ID initially
  given was a group ID; the real look ID was substituted after catching
  this.
- Full test sequence run and verified 2026-08-08: Test 1 (2 approved rows →
  2 queue rows, scripts byte-for-byte preserved, Content Pipeline →
  `HeyGen Queued`), Test 2 (immediate re-run → 0 candidates, 0 duplicates,
  no-op), Test 3 (no-content run → exact fallback email, nothing changed),
  Test 4 (avatar-less run → both items `Needs Avatar Review`, source rows
  untouched). All passed against the live sheet, not fixtures.

## Final architecture

```
Workflow 01 — Script Factory
        ↓
Content Pipeline
        ↓
Workflow 02 — Quality Checker
        ↓
Approved + Ready for Video
        ↓
Workflow 03 — HeyGen Production Queue   (this workflow)
        ↓
HeyGen Queue
```

Stops there — no Workflow 04 (video generation/publishing) exists yet.
