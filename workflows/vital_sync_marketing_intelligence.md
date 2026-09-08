# Vital Sync — Marketing Intelligence Agent

## Objective

The marketing intelligence brain for Vital Sync: continuously research
market demand, competitors, and audience problems; turn the strongest
findings into scored campaign opportunities; analyze performance of
campaigns that are actually running; and compound what's learned week over
week. **Not** a content-generation workflow — it never writes scripts. This
is a separate system from Workflows 00-04 (the script/content pipeline);
the two don't read or write each other's storage.

```
Research (Market / Competitor / Audience)
        -> Campaign Opportunities (scored, deduplicated, Pending approval)
        -> Human approves -> Active Campaigns (manual move, not automated)
        -> Campaign Performance (manual/analytics entry)
        -> Performance Analysis -> Marketing Learnings
        -> feeds next run's research priorities and scoring
```

## Source of truth

`Vital_Sync_Marketing_Intelligence_Workflow.xlsx` — an Excel workbook, **not**
the Google Sheet Workflows 00-04 use. Default location:
`~/Downloads/Vital_Sync_Marketing_Intelligence_Workflow.xlsx`, overridable via
`VITAL_SYNC_MARKETING_WORKBOOK` in `.env` if it moves. Every run reads it
fresh and writes back through `marketing_intelligence/workbook.py`'s
backup-validate-replace path (see "Failure safety" below) — never a
replacement file.

Sheets: Overview, Market Signals, Competitor Intelligence, Audience
Problems, Campaign Opportunities, Active Campaigns, Campaign Performance,
Marketing Learnings, Automation Logs, Config & Lists. Several sheets ship
with spreadsheet formulas pre-filled down every templated row (e.g. Market
Signals' Opportunity Score, Campaign Opportunities' Opportunity Score +
Priority). `workbook.py` auto-detects those columns per run and never
writes into them — only the raw scored inputs are set, exactly as if a
human typed them in and let Excel compute the rest.

## Commands

All commands go through `tools/vital_sync_marketing.py`, which does nothing
but parse the command and call `marketing_intelligence/runner.py`'s single
`run()` function — scheduled and manual execution are the same code path,
so they can never diverge.

```
python tools/vital_sync_marketing.py "RUN NOW"                          # full cycle, immediately
python tools/vital_sync_marketing.py "DRY RUN"                          # full cycle, writes nothing
python tools/vital_sync_marketing.py "STATUS"                           # read-only, no research
python tools/vital_sync_marketing.py "RUN MARKET RESEARCH"              # Market Signals only
python tools/vital_sync_marketing.py "RUN COMPETITOR INTELLIGENCE"      # Competitor Intelligence only
python tools/vital_sync_marketing.py "RUN AUDIENCE INTELLIGENCE"        # Audience Problems only
python tools/vital_sync_marketing.py "RUN CAMPAIGN INTELLIGENCE"        # Campaign Opportunities from EXISTING intel only
python tools/vital_sync_marketing.py "RUN PERFORMANCE ANALYSIS"         # Performance -> Marketing Learnings only
python tools/vital_sync_marketing.py "RUN WEEKLY MARKETING INTELLIGENCE" --trigger scheduled   # what the cron entry runs
python tools/vital_sync_marketing.py "RUN EVERY MONDAY AT 8 AM"         # updates schedule config (add --activate to also (re)install the cron entry)
python tools/vital_sync_marketing.py "ACTIVATE SCHEDULE"                # installs/updates the recurring cron entry
python tools/vital_sync_marketing.py "RUN TOMORROW" --activate          # one-off future run via a separate, self-removing cron entry
```

`RUN NOW` / `RUN TODAY` / `RUN WEEKLY MARKETING INTELLIGENCE` / `RUN FULL
MARKETING INTELLIGENCE` all execute the FULL execution order below and
generate a PDF. The specialized runs (`MARKET RESEARCH`, `COMPETITOR
INTELLIGENCE`, `AUDIENCE INTELLIGENCE`, `CAMPAIGN INTELLIGENCE`,
`PERFORMANCE ANALYSIS`) only touch their own sheet(s) and skip the PDF.

## Full execution order

1. Acquire the workflow lock (`workflow_lock.py`) — a second run started
   while one is active gets `WORKFLOW ALREADY RUNNING` and does nothing. A
   lock older than 30 minutes with a dead PID is treated as an abandoned
   run and reclaimed automatically.
2. Load the workbook and every sheet (pre-run check) before any new
   research — Market Signals, Competitor Intelligence, Audience Problems,
   Campaign Opportunities, Active Campaigns, Campaign Performance,
   Marketing Learnings, Automation Logs, Config & Lists.
3. Sync thresholds (`Default Opportunity Threshold` / `Default Test
   Threshold`) from Config & Lists into local config, so the sheet — not a
   hardcoded number — is the source of truth for scoring bands.
4. Seed duplicate-detection pools from existing Market Signals, Audience
   Problems, Campaign Opportunities, and Active Campaigns.
5. Research: Market Signals -> Audience Problems -> Competitor
   Intelligence, each checked against its pool so re-running doesn't
   restate what's already stored (`duplicate_detector.py`, token-Jaccard
   similarity, same approach already proven in
   `tools/research_vital_sync.py`).
6. Generate Campaign Opportunities from the strongest audience problems
   (paired with a matching market signal where one exists), subject to the
   product reality check below, then dedup against the seeded pool.
7. Analyze Active Campaigns + Campaign Performance against each campaign's
   OWN objective metric (never judged by views alone), and write Marketing
   Learnings only where there's enough evidence (>= 3 performance data
   points) — one weak data point never becomes a "learning."
8. Classify every new campaign opportunity as BUILD NOW / TEST / MONITOR /
   IGNORE from its scored inputs (mirrors the workbook's own formula, used
   for the run summary and PDF only — the real number always comes from
   the spreadsheet formula).
9. Write everything in one `workbook.safe_write()` transaction: edits a
   temp copy, validates it opens cleanly and every required sheet/header is
   intact, backs up the current workbook, then atomically replaces it. A
   crash or bad write mid-run leaves the previous good workbook in place.
10. Append one Automation Logs row (Run ID, trigger, duration, sources
    checked/unavailable, counts, report file, errors).
11. Generate the PDF (full/weekly runs only) and release the lock.

## Research sources & honesty rules

Zero paid API calls, matching the pattern already proven by Workflow 00:

- **Implemented, real:** Google Autocomplete and YouTube Suggest
  (key-free), competitor homepage fetch (title + meta description only —
  whatever a plain HTTP GET actually exposes), and an offline
  AnswerThePublic-style template expansion (WHO/WHAT/WHY/HOW/CAN/SHOULD/
  VS/ALTERNATIVE/... x seed topics) used as a **discovery input**, never
  presented as platform evidence unless confirmed by a real source.
- **Documented as SOURCE UNAVAILABLE, every run:** Reddit (403 from this
  environment), Google Trends / People Also Ask (no key-free API short of
  fragile SERP scraping), TikTok search, App Store / Google Play reviews —
  not fabricated, not silently skipped. Some competitor homepages also
  block plain HTTP GETs (bot protection) and land here per-run rather than
  being guessed at.
- Audience Problems rows are explicitly `Source = "Derived Audience
  Language"` — a reasoned hypothesis from a fixed segment/problem-cluster
  catalog, never presented as a real quote. If a real-quote source is
  added later, tag those rows `Real User Language` and leave this module's
  rows alone.

## Product reality check (now automatic — Product Intelligence integration, 2026-08-19)

`marketing_intelligence/product_intelligence.py` replaces the old empty-
by-default `product_capabilities.json` placeholder. Every FULL/WEEKLY/
AUDIENCE/CAMPAIGN run now loads a **Product Reality Map** first:

```
Product Intelligence (Vital_Sync_Weekly_Intelligence_*.pdf)
        -> Product Reality Map (LIVE / PARTIAL / MISSING / PROTOTYPE per area)
        -> Market Intelligence -> Audience Intelligence -> Competitor Intelligence
        -> Marketing Opportunity Engine -> Campaign Recommendations
```

**Locating the report**: `find_latest_report()` searches
`reports/vital_sync/` (recursive), `~/Desktop`, and `~/Downloads` for
`Vital_Sync_Weekly_Intelligence_*.pdf`, picks the newest by the DATE IN
THE FILENAME (never filesystem mtime), and caches the parsed result in
`marketing_intelligence/config/product_reality.json` — regenerated
automatically whenever a newer report shows up, never hand-edited.

**Extraction**: real `pypdf` text extraction anchored on that report's
fixed section headers ("Vital Sync Current State", "Cross-System Audit",
"Product Opportunities" -> Build Now/Improve Existing/Build Next/
Experiment/Monitor, "Biggest Competitor Threat", etc.) — these are literal
strings in `tools/generate_weekly_pdf.py`'s rendering code, not
LLM-improvised each week, so they're stable anchors across reports. If a
future report doesn't use this template, the affected lists just come
back empty (logged, never fabricated) rather than guessed at.

**Feature taxonomy** (`FEATURE_TAXONOMY` in product_intelligence.py): maps
marketing-speakable concepts (e.g. "Nutrition Guidance", "Training Load
Intelligence", "Alignment Engine") to the report Area(s) they depend on,
plus a claim SCOPE — "tracking" (the raw capability exists) vs "guidance"/
"advanced" (Vital Sync actively analyzes/adapts from it) vs "core" (the
capability itself IS the advanced claim, e.g. Alignment, AI chat coach).
A LIVE area does NOT automatically license a "guidance"/"advanced" claim —
it's downgraded to PARTIAL, so the campaign gate narrows the language
instead of rubber-stamping it (the "function exists" vs "function is deep
enough to market strongly" distinction).

**Scoring** (`resolve_feature()` / `dependency_label()`): Product Fit is
banded 10 (LIVE + differentiator) / 9 (LIVE, not unique) / 6-7 (PARTIAL) /
3 (PROTOTYPE) / 1 (MISSING) — differentiator status is detected from
whether the feature's keywords appear in the report's own Strengths
bullets, not hardcoded. Product Fit <= 2 is a HARD gate: `Status` is
written as `BLOCKED BY PRODUCT` regardless of how strong the other seven
score inputs are — no combination of market/audience/competitor evidence
can promote a missing-feature campaign to BUILD NOW. The five-way label
(`READY TO MARKET` / `SAFE TEST` / `QUALIFIER REQUIRED` / `BLOCKED BY
PRODUCT` / `FUTURE CAMPAIGN`) is written directly into the sheet's
`Status` column — this is the authoritative answer; the sheet's own
Opportunity Score formula is left untouched (never overwritten) but is
informational only, since a single very-low Product Fit input isn't
guaranteed to pull an 8-input average below the BUILD NOW threshold by
itself. `Notes` always cites the Area, evidence snippet, and report date
so a human can verify the claim without re-opening the PDF.

**Reframing** (section 15's case): where a blocked claim has a real
narrower alternative on file (`fallback_feature` in
`audience_research.PROBLEM_CATALOG` — currently only "Low-Friction
Logging" -> "Alignment Engine"), the campaign is rebuilt around that
instead of just dropped, with `Notes` documenting the reframe.

**Reclassifying existing rows**: this isn't just for new campaigns.
`campaign_engine.generate()` returns `(new_campaigns, campaign_updates)` —
when a freshly-scored candidate matches an EXISTING Campaign Opportunities
row (same audience+problem+angle+message+feature fingerprint) and its
Status/Confidence/Product Feature actually changed, that existing row is
updated in place (`Product Feature`, `Status`, `Confidence`, `Core
Message`, `Notes`, `Product Fit`, `Competitive Gap`, `Ease of Execution`
only — Campaign Name/Date Created/Audience/Platform/CTAs are left exactly
as a human last saw them). This is what actually clears stale "NEEDS
PRODUCT INPUT" rows left over from before this integration existed,
verified 2026-08-19 against all 5 of the original campaigns — see
`runner.reclassification_report()` for the read-only preview `DRY RUN`
prints, and the module docstrings in `campaign_engine.py` /
`product_intelligence.py` for the full reasoning.

**Staleness**: `is_stale()` flags the report >10 days old; the PDF then
opens with a `PRODUCT INTELLIGENCE MAY BE STALE` banner.

**Product Demand Signals**: when this run's Market Signals harvest hits
the same MISSING-feature keyword group (voice/photo logging, Apple
Health/wearables, training load, adaptive program adjustment) more than
once, a Product Demand Signal record is written to the new **Product
Demand Signals** tab (added non-destructively via `workbook.ensure_sheet`
— the only structural change to the workbook this integration made, since
it's a genuinely new kind of record the original 10-sheet template didn't
anticipate) instead of a marketing campaign — see section 21/22 of the
integration instructions for the full two-way-loop rationale.

## Human approval

Every new campaign is written `Status = "Draft"`, `Human Approval =
"Pending"`. Nothing in this codebase ever flips that to Approved, spends
money, publishes content, or launches anything — that's a human editing
the workbook, always.

## Duplicate protection

Before adding a Market Signal / Audience Problem / Campaign Opportunity,
its concept fingerprint (topic+query, or segment+problem+angle+message+
feature for campaigns) is compared via token-Jaccard similarity (>= 0.6)
against everything already in the relevant pool. A near-duplicate is
skipped, not re-added with different wording — "Stay Consistent" and
"Consistency Wins" collapse to the same fingerprint.

## Failure safety & concurrency

- `workbook.safe_write()`: temp copy -> edit -> validate -> backup original
  -> atomic replace. Last 10 backups kept in
  `marketing_intelligence/state/backups/`.
- `workflow_lock.py`: single lock file, PID + timestamp, 30-minute stale
  timeout with dead-PID detection.
- Both verified working (2026-08-16): a full write cycle run against an
  isolated copy of the workbook correctly appended rows, preserved every
  pre-filled formula, wrote an Automation Logs row, created a backup, and
  never touched the real workbook file. A second concurrent lock attempt
  was correctly rejected and the first release cleared the lock file.

## Scheduling

**Runs via `cron`, not `launchd`.** Originally activated as a `launchd`
LaunchAgent (`com.vitalsync.mmarketingintel`). On 2026-08-22, that plist —
along with this project's 5 other `launchd` LaunchAgents — was disabled
after a recurring `launchd` spawn-block issue (see
`project_launchd_spawn_block` memory) stopped clearing via reboot/Full
Disk Access/Directory Services fixes. The old plist is preserved, disabled,
in `~/Library/LaunchAgents/disabled_vitalsync_launchd_20260822/`.

`scheduler.py` was updated the same day to manage a `cron` entry instead of
a `launchd` plist — `ACTIVATE SCHEDULE` / `RUN EVERY <day> AT <time>
--activate` now render and upsert a single tagged line
(`# vitalsync-mmarketingintel`) into the shared user crontab (`crontab -l`)
rather than writing/bootstrapping a plist. `install_job()` only ever
touches its own tagged line — every other job in that crontab (the other
5 Vital Sync jobs, or anything else) is read back untouched, so a schedule
change updates the one entry in place rather than stacking a duplicate,
same guarantee as before. A one-off run (`RUN TOMORROW` / `RUN ON
<date>`) uses a separate tag (`# vitalsync-mmarketingintel-oneoff`) and, since
cron has no "year" field, self-removes its own crontab line right after it
fires so it can't silently recur the following year.

Config still lives in `marketing_intelligence/config/schedule.json`
(frequency / day / time / timezone), not hardcoded — default `weekly,
monday, 08:00, Asia/Dubai`. `RUN EVERY <day> AT <time>` / `RUN WEEKLY ON
<day>` update this config exactly as before; only the installation
mechanism underneath changed.

Unlike `tools/generate_weekly_pdf.py`'s older pipeline (which needs a live
Claude session at run time to do its research), every research/scoring/
report step here is deterministic Python — no LLM calls — so the weekly
job genuinely can run unattended via bare `cron`, the same way Workflow
00's job already does.

## Known constraints / gaps

- **(2026-09-07, FIXED same day)** Every scheduled firing since the
  2026-08-22 cron migration had actually been failing silently: `tools/
  vital_sync_marketing.py --trigger` required `{Manual, Scheduled}`
  (capitalized) while `scheduler.py`'s cron line — and every other tool in
  this repo — passes lowercase `scheduled`, so argparse rejected it before
  `runner.py` ever ran. Confirmed via `tmp/marketing_intelligence_launchd.log`:
  the Sep 7 08:00 firing died on this exact argparse error; the Aug 31
  08:00 firing died earlier still, on a `.venv/pyvenv.cfg` PermissionError
  (the Downloads-folder TCC issue from `project_launchd_spawn_block`) that
  did NOT recur Sep 7 — consistent with that block being session-scoped,
  not persistent. Net effect: **no scheduled run had ever reached the
  workbook** — Automation Logs held exactly one row (the 2026-08-19 manual
  run) until this was caught. Fixed by matching the rest of the repo's
  lowercase `--trigger` convention; verified against an isolated workbook
  copy with the literal cron invocation (`--trigger scheduled`) before
  trusting it live. If a Monday run is ever missing again, check
  `tmp/marketing_intelligence_launchd.log` first — a crash before
  `runner.py` starts won't produce an Automation Logs row at all.
- **(2026-08-16)** No email delivery of the weekly PDF is wired up yet
  (unlike the older Workflow 00-04 pipeline's `gmail_send.py` /
  `gmail_smtp_send.py`) — say the word if you want that added.
- **(2026-08-16)** Competitor homepage research is title/meta-description
  only — pricing, feature lists, and review sentiment still need manual
  research or a future scraper.
- **(2026-08-19)** `competitive_gap_score()` is grounded in the report's
  Biggest Competitor Threat text plus a small hardcoded differentiator/
  competitor-lead list (Alignment/AI coach score high; wearables/training
  load/low-friction logging score low because the report explicitly says
  competitors lead there) — not yet a fully general read of Competitor
  Intelligence per-feature.
- **(2026-08-19)** Strengths/Weaknesses bullet extraction from the PDF is
  best-effort sentence-grouping (reportlab bullet indentation isn't
  reliably preserved in extracted text) — reads correctly against the
  2026-08-17 report but hasn't been proven against a report with a
  differently-shaped narrative.
- **(2026-08-19)** `Build Now`/`Build Next`/`Monitor` opportunity titles
  from the Product Opportunities table are truncated to their first line
  where a title wraps across two lines in the PDF — fine for the
  secondary demand-signal cross-referencing they're used for, not meant
  to be quoted verbatim.
- **(2026-08-19)** A handful of pre-existing Audience Problems rows from
  before this integration (e.g. one stray "Less logging, more useful
  decisions" row) don't match any `PROBLEM_CATALOG` angle — they still get
  processed honestly (fall through to an UNKNOWN feature -> `BLOCKED BY
  PRODUCT`, never fabricated) but won't get a meaningful Product Feature
  until manually reconciled or archived.

## Files

```
marketing_intelligence/
    config.py                # schedule, thresholds, sheet header constants
    workbook.py               # safe read/write, formula protection, ensure_sheet, validation
    workflow_lock.py          # concurrency lock
    logger.py                  # RunStats + Automation Logs writer
    duplicate_detector.py      # token-Jaccard dedup
    product_intelligence.py    # NEW 2026-08-19: locates/parses Vital_Sync_Weekly_Intelligence_*.pdf,
                                # builds the Product Reality Map, feature taxonomy, dependency labels,
                                # demand-signal generation — see "Product reality check" above
    market_research.py         # Market Signals research
    competitor_research.py     # Competitor Intelligence research
    audience_research.py       # Audience Problems research (PROBLEM_CATALOG now carries product_feature)
    campaign_engine.py         # Campaign Opportunities generation + scoring + reclassify-in-place
    performance_analyzer.py    # Active Campaigns + Campaign Performance analysis
    learning_engine.py         # Marketing Learnings
    report_generator.py        # weekly PDF — 20-section structure, Paragraph-wrapped tables, landscape support
    scheduler.py                # schedule parsing + crontab entry management
    runner.py                    # orchestrator — the only entrypoint every mode calls
    config/                     # schedule.json, thresholds.json, product_reality.json (cache, auto-regenerated)
    state/                      # workflow.lock, backups/, competitor_snapshots.json, last_marketing_product_report.json
tools/vital_sync_marketing.py    # thin CLI entrypoint
reports/vital_sync_marketing/    # generated PDFs
reports/vital_sync/              # Product Intelligence PDFs this system reads (owned by the older Workflow 00-04 pipeline)
```
