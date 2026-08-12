# Workflow 00 — Vital Sync Search Intelligence Engine

## Objective

Discover real-world search demand around **Fitness / Nutrition / Recovery**
and turn it into scored, deduplicated opportunities appended to the
**existing** Search Bank tab. This workflow sits BEFORE Workflow 01 (Script
Factory) in the pipeline:

```
Workflow 00 (this) -> Search Bank -> Workflow 01 (Script Factory)
                                   -> Content Pipeline -> Workflow 02 (QC)
```

Research only. This workflow **never** generates scripts, captions, CTAs,
hashtags, or videos; never quality-checks or approves anything; never
writes to Content Pipeline; and never marks a row `Used` (that belongs to
Workflow 01). Its only output is unused rows in Search Bank with
`Status = Unused`.

## Trigger

Scheduled daily via `launchd` at **7:52 AM Asia/Dubai**, 8 minutes before
Workflow 01 (8:00 AM) — see "Scheduling" at the bottom. Also runnable
manually at any time. Makes **zero paid API calls** (no OpenAI), so it's
safe to re-run as often as needed.

## Source of truth

Same Google Sheet as Workflows 01/02/03: `GOOGLE_SHEET_ID` in `.env`. No new
tab is created. Tabs used:

- **Search Bank** — read fully (all statuses) for dedup context on every
  run, then appended to. Never cleared, never overwritten, statuses never
  reset. See "Column mapping" below for the schema this workflow added.
- **Content Pipeline** — read-only, lightly checked for dedup (`Topic` /
  `Search Query` columns) per spec section 19. Never written to.
- **Automation Logs** — appended to using the *existing* 5-column schema
  (`Date, Workflow, Success, Time, Errors`) — no new columns. Workflow name:
  `Vital Sync Search Intelligence Engine`.

## Column mapping (why nothing was renamed or duplicated)

The live Search Bank already had 10 columns before this workflow existed:
`Search Query, Topic, Category, Search Intent, Difficulty, Search Score,
Trend Score, Follower Potential, Product Opportunity, Status`. Workflow 01's
`generate_content.py` reads several of these directly, so instead of adding
a parallel "Primary Pillar" / "Opportunity Score" column next to each
existing one (which the brand spec explicitly warned against), existing
columns are reused wherever they already mean the same thing:

| Spec field | Resolution | Why |
|---|---|---|
| Search Query, Topic | reused as-is | already exactly this |
| Primary Pillar | **is** `Category` | `build_prompt()` in Workflow 01 reads `Category` directly — renaming it would silently break every future content brief. New rows are restricted to `Fitness` / `Nutrition` / `Recovery`. |
| Search Intent, Product Opportunity, Status | reused as-is | new rows use the new spec's vocabulary; historic rows are untouched |
| Search Score, Trend Score | **populated for every new row** | `select_topics()` in Workflow 01 ranks unused rows by `int(Search Score) + int(Trend Score)`. Leaving them blank would sink every new opportunity to the bottom forever. `Search Score = round(Opportunity Score × 10)` (rescales 1–10 onto the existing 0–100 scale). `Trend Score = round(Search Demand × 10)` — an explicit ranking proxy, never presented as a real trend %. |
| Difficulty, Follower Potential | kept, populated | not read by any script (confirmed via grep) but kept meaningful: `Difficulty` from the Competition band, `Follower Potential` from the Content Potential band. |

17 new columns were appended after the existing 10 via
`sheets_io.ensure_headers()` (additive only — reads current headers, appends
whatever's missing at the end, never touches an existing cell):
`Search ID, Date Found, Seed Topic, Audience Problem, Subcategory, Audience
Level, Source, Source Detail, Trend Signal, Search Demand, Audience
Relevance, Content Potential, Competition, Opportunity Score, Priority,
Date Used, Notes`. Final shape: **27 columns**, nothing deleted or reordered.

## Tool

`tools/research_vital_sync.py`. Mirrors the CLI shape of `generate_content.py`
/ `build_heygen_queue.py`:

```
python tools/research_vital_sync.py --dry-run --batch-size 30
python tools/research_vital_sync.py --live --batch-size 30 --no-email
python tools/research_vital_sync.py --live --trigger scheduled
```

`--dry-run` previews everything (research, scoring, dedup, top 10) with zero
Sheets writes. `--live` appends to Search Bank, writes one Automation Logs
entry, and emails a summary (unless `--no-email`) via the existing
`gmail_send.send_email()`. Default batch size comes from
`SEARCH_ENGINE_BATCH_SIZE` in `.env` (50); `--batch-size 30` splits evenly
across the 3 pillars (10/10/10).

## Research sources (section 6/7 — never fabricated)

| Source | Status | Notes |
|---|---|---|
| Google Autocomplete | **Real, implemented** | `suggestqueries.google.com`, no key needed. Queried with bare seed topics + a curated set of AnswerThePublic-style prefixes (why/how much/how often/should i/does/is/best/can i) and suffixes (vs/without/with/before/after training). |
| YouTube Suggest | **Real, implemented** | same host, `client=youtube`. Bare seed queries only. |
| Derived Search Intent | **Real, implemented (offline)** | deterministic template expansion grounded in the brand's own seed/example vocabulary (spec sections 8–10). Never claimed to come from a platform. |
| Reddit | Attempted, **unavailable** | public JSON search returns HTTP 403 from this environment. Code path exists and activates automatically if reachable elsewhere, but every run logs it honestly as unavailable rather than assuming it works. |
| Google Trends | **Not implemented** | no reliable key-free API in this environment; scraping was ruled out as fragile/ToS-risky. `Trend Signal` is `Unknown` for every row as a result — an honest gap, not a bug. |
| Google People Also Ask / Related Searches | **Not implemented** | same reasoning — would require scraping SERP HTML. |

Each run does one connectivity probe per source and reports availability in
its summary and Automation Logs entry — a source going down never silently
drops rows or fabricates replacement data (section 30).

## Scoring (section 15 — transparent, deterministic, no fabricated volume)

- **Search Demand (1–9)**: capped below 10 (no real volume data exists to
  justify a max score). Autocomplete/YouTube hits score 6–9 based on how
  many times a query surfaced and its best suggestion rank; Derived Search
  Intent items are fixed at 4 (no external evidence).
- **Audience Relevance (1–10)**: `5 + min(2, own-pillar term matches) +
  min(2, other-pillar term matches) + 1 if a core brand term is present`.
  The cross-pillar bonus rewards queries that connect training + nutrition +
  recovery — Vital Sync's actual positioning — rather than every on-topic
  query trivially maxing out at 10.
- **Content Potential (1–10)**: query-shape heuristic — question-form
  phrasing, a concrete number/timeframe, and a healthy word count each add
  points; very short fragments are penalized.
- **Competition (1–10, 10 = hardest)**: broad head-term seeds and short
  phrasings score higher; longer, more specific phrasings score lower.
- **Opportunity Score** = `0.35×Relevance + 0.30×ContentPotential +
  0.25×Demand + 0.10×(11-Competition)`, rounded to 1 decimal.
- **Priority** is assigned **by rank within the accepted batch** (top ~25%
  High, next ~45% Medium, remaining ~30% Low), not a fixed absolute cutoff.
  A fixed cutoff collapsed here in testing: harvesting already selects only
  the strongest scorers out of 2,000+ raw candidates per run, so every
  accepted item cleared a modest absolute bar and everything came out
  "High" — exactly what section 16 warns against. Worth revisiting once
  there's a larger historical Opportunity Score distribution to calibrate
  an absolute bar against.
- **Product Opportunity**: `Yes` only when the query's phrasing is
  How-To/Recommendation/Frequency AND touches a real Vital Sync capability
  keyword (tracking, programming, consistency, routine). Defaults to `No`.

## Deduplication (section 19)

- **Exact**: normalized (lowercased, punctuation/whitespace-collapsed)
  Search Query match against every existing Search Bank row (any status)
  plus everything already accepted earlier in the same run.
- **Semantic**: stopword-stripped token-set Jaccard similarity ≥ 0.6 against
  the same pool — catches "how much protein should I eat" vs "how much
  protein do I need" without an embeddings API.
- Candidates are scored and sorted *before* the dedup/accept pass, so when
  two near-duplicates both surface, the stronger-scoring wording wins the
  slot (section 19: "keep the strongest wording").
- A per-seed cap during acceptance (`ceil(target/seed_count) + 1`) keeps a
  couple of strong seeds (e.g. "Rest Days") from crowding out the rest of a
  pillar's seed library.

## Quality filter (section 23)

Rejects: too-short/meaningless queries, banned-topic patterns (medical
diagnosis, extreme diets, disease-specific/clinical-population content,
business/finance/relationship/career pollution), off-niche pop-culture
autocomplete noise (a real, recurring issue — "muscle growth" pulls in
anime/manga results; "exercise form" pulls in English-grammar worksheets),
and anything with zero token overlap with its pillar's own seed vocabulary.

**QA finding from the initial test run**: "why is meal timing important for
clients with diabetes" passed the original filter and was appended, then
caught during the Workflow 01 compatibility check (it would have been
selected next). Corrected post-hoc — the row's `Status` was set to
`Rejected` with a `Notes` explanation, and a disease/clinical-population
pattern was added to the banned list so this class of query is rejected at
harvest time going forward.

## Seed library (section 22)

Configurable in `research_vital_sync.py` (`SEED_TOPICS` dict) — 8 Fitness, 7
Nutrition, 7 Recovery seeds to start, matching section 22 exactly. Not a
hard limit; more seeds can be added to the dict at any time.

## Known constraints / learnings

- **Runtime**: a batch-size-30 run makes ~330 Google Autocomplete/YouTube
  requests (full WHY/HOW/WHAT-style expansion is always run, not just as an
  escalation fallback — an earlier version only expanded when the bare-seed
  pass came up short, which meant it almost never triggered and the
  accepted set was dominated by generic noun-phrase completions instead of
  real questions). Takes ~2 minutes end to end. Fine for manual/on-demand
  use; worth revisiting if this becomes a frequent scheduled job.
- **Overlap-lock**: implemented the same started/completed marker pattern
  as Workflows 01/02 (`check_overlap()` in `research_vital_sync.py`) before
  scheduling was enabled — a run whose "started" marker is younger than
  `STALE_RUN_TIMEOUT_MINUTES` (30) with no matching completed/skipped
  marker blocks a new run and logs `skipped` instead of racing it. Unlike
  Workflow 01 there's no "Processing" status to self-heal — this workflow
  only ever appends new rows, never reserves existing ones — so the lock
  alone is sufficient.
- **Trend Signal is always "Unknown"** in this build — there is no
  key-free, reliable trend-direction source available. This is intentional
  honesty per section 18/7, not a bug to silently patch with a guess.

## Failure handling (section 30)

- A failed source call is logged (`source_call_failures` counter) and
  skipped — remaining sources continue, no fabricated replacement data.
- A Search Bank write failure stops the run before claiming success; the
  Automation Logs `completed` entry records `accepted: 0` and the error,
  and the process exits non-zero.
- Any single candidate that fails the quality filter is skipped; it never
  aborts the run.

## Scheduling

**Enabled**, using the exact same mechanism as Workflows 01–03 — `launchd`,
one LaunchAgent per workflow, no second scheduler. Built and verified
manually first (per section 31/32: 30-row run + repeat-run, documented in
the initial delivery report), then wired up:

- **Label**: `com.vitalsync.msearchintel` — a fresh label, never reused
  from a retired one (per `project_launchd_spawn_block` memory: old dead
  labels must never be recreated).
- **Schedule**: 7:52 AM daily, Asia/Dubai. This runs *before* Workflow 01
  (8:00 AM) so freshly-discovered opportunities are available the same
  morning, with an 8-minute buffer (a normal run takes ~2–3.5 minutes).
- **Command**: fully inlined absolute-path `/bin/bash -c "..."` in
  `ProgramArguments` — pointing at a `.sh` file in this project directory
  was proven unreliable here (`com.apple.provenance` xattr issue, see
  memory) even though the identical command inlined works fine. A copy of
  the exact command lives in
  `tools/run_search_intelligence_scheduled.sh` for manual testing/reference
  only — **not** referenced by the plist itself.
- **`com.vitalsync.macstaywake` was retimed** to start at 7:50 AM instead of
  7:58 AM (caffeinate duration extended from 9000s to 9480s to preserve the
  same ~10:28 AM end-of-coverage) so the Mac stays awake through this new
  earlier job as well as the existing 8:00/9:00 AM ones.
- Runs with no `--batch-size` override (uses `SEARCH_ENGINE_BATCH_SIZE=50`
  from `.env`) and no `--no-email` (sends the daily summary, matching
  Workflows 01/02's precedent).
- **Verified via a real `launchctl kickstart`**, not just a direct terminal
  invocation — this project has a documented history of `launchd` jobs
  failing silently (deep `posix_spawn` errors, invisible to `launchctl
  print`) that only surface on an actual scheduled-path run. The kickstart
  completed cleanly: appended 50 rows, wrote a `completed` Automation Logs
  entry, and sent the summary email.

Useful commands (same pattern as Workflows 01/02):

```
launchctl print gui/$(id -u)/com.vitalsync.msearchintel
launchctl kickstart -p gui/$(id -u)/com.vitalsync.msearchintel   # force an immediate run
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.vitalsync.msearchintel.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.vitalsync.msearchintel.plist
```

Final daily schedule: `macstaywake` 7:50 → `msearchintel` 7:52 →
`mscriptfactory` 8:00 → `mqualitychecker` 9:00.
