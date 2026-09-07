# Workflow 01 — Vital Sync Product + Competition Intelligence

**Question this workflow answers:** "What should Vital Sync build or improve, given the current product and the current market?"

This is a **recommendation-only intelligence workflow**. It analyzes, researches, scores, and recommends. It never modifies Vital Sync's product code, never touches Replit, never implements a recommendation, and never approves its own recommendations — a human decides what gets built. See section "Boundaries" below for how this relates to Workflow 02 (Marketing Intelligence) and a future Workflow 03 (Analytics + Funnel Intelligence).

## Why this document exists

Built interactively across several sessions (2026-08-11 through 2026-09-07) without ever being written down as a Layer-1 SOP — a real gap against this repo's own WAT architecture (CLAUDE.md). Repaired 2026-09-07 after discovering the workflow had been silently treating "the GitHub mirror of Vital Sync hasn't changed" as "Vital Sync hasn't changed," which is a different, unverified claim. See `reports/vital_sync/vital_sync_product_state.json` and `evidence_conflicts.json` for the persistent state this repair introduced.

## Systems involved (don't confuse these)

- **This workflow** — product + competition intelligence about the real Vital Sync **fitness app** (vitalsyncify.com, source mirrored at github.com/faristjohar04-sketch/Vital-Sync). Runs weekly.
- **`tools/vital_sync_marketing.py` + `marketing_intelligence/`** — a separate system, Vital Sync's *marketing* intelligence (Workflow 02). Different question, different outputs. Don't merge them.
- **A future Workflow 03** (Analytics + Funnel Intelligence) does not exist yet. If it's built, this workflow may *reference* its validated findings but must not duplicate funnel/cohort/retention analysis itself.
- **The rest of this repo** (Workflows 00/01/02/03 numbered elsewhere, `weekly_cleanup.py`, etc.) is a *different, unrelated* content-creation pipeline for a "Vital Sync" branded YouTube/TikTok channel. Same brand name, completely different product. Don't conflate a "Vital Sync" email/log line from one system with the other.

## Automation

- **Cloud routine** (`trig_01EP8zU38BpzthxADMLWo93h`, "Vital Sync Weekly Intelligence"): fires Monday 8am Asia/Dubai. Does the research and PDF generation — the part that needs live reasoning and web access. Pushes to a `claude/*` branch (its GitHub App install opens a PR rather than pushing to main directly) and cannot send email (no secrets-injection mechanism exists for cloud routines in this product).
- **Local cron job** (`vitalsync-weeklyfinish`, Monday 9am Asia/Dubai, `tools/vital_sync_weekly_finish.py`): the deterministic tail end — merges the pending branch, sends the email via the local OAuth-based `tools/gmail_send.py`, records delivery. Never uses `git reset --hard`; fast-forwards or fails loudly.
- See `reports/vital_sync/automation_log.jsonl` for the run history of both.

## Source-of-truth hierarchy

For **current Vital Sync product state**, sources rank in this order — a higher-priority source always wins a conflict with a lower one, but "wins" requires the higher source to actually be *checkable*, not just asserted:

1. **Verified current Replit production/development source** — not currently accessible to this workflow. No login, API key, or export mechanism exists yet. This is the real fix needed; everything below is a workaround for its absence.
2. **A repository snapshot confirmed to correspond to the current deployed/developed product** — in practice, the GitHub mirror (`faristjohar04-sketch/Vital-Sync`), *if and only if* it can be shown to be current (recent commits, or explicit confirmation it's synced with Replit).
3. **A current-state audit/export generated from Replit** — e.g., if the user pastes a fresh export or grants a checkable access path.
4. **The previous verified `vital_sync_product_state.json`** — yesterday's best-known state, better than nothing but itself may be stale.
5. **Historical weekly PDF reports** — lowest priority. A historical report NEVER overrides newer verified evidence, and conversely a historical report is never itself proof that nothing has changed since.

**A claim is not evidence.** A statement (in chat, in a spec, anywhere) that something has changed is a *lead to verify*, not itself a Priority-1/2/3 source, unless it comes with something independently checkable (a commit hash, an export file, a screenshot with a timestamp, direct access). Record it, don't promote it.

## The core mistake this repair fixes

```
LOCAL REPOSITORY UNCHANGED  ≠  VITAL SYNC PRODUCT UNCHANGED
```

A `git log`/`git diff` against the GitHub mirror only tells you the **mirror** hasn't changed. It says nothing about whether the mirror is itself stale, disconnected, behind Replit, or behind deployment. As of 2026-09-07, direct verification shows the mirror **is** stale — frozen at commit `ef43285` since 2026-08-12, unchanged through 4+ weekly checks — while the user reports real product work has happened since. **Report repository state and product state as two separate facts, always.**

## Product Freshness Gate (run before any product-state analysis)

For each source checked, record: source name, source type, commit/version (if any), generated/last-modified timestamp, environment, branch, deployment identity (if available), verification method. Classify the source as one of:

- `CURRENT_VERIFIED` — a Priority-1/2/3 source, confirmed current by direct means (not just "no diff found").
- `LIKELY_CURRENT` — best available source, no positive evidence of staleness, but no independent confirmation of currentness either.
- `STALE` — confirmed unchanged over a period long enough, or by other means, to doubt it reflects the current product (e.g., the GitHub mirror today).
- `UNKNOWN` — couldn't be checked this run (source unreachable).
- `CONFLICTING` — two sources disagree and neither dominates by the hierarchy above.

**If the best available source is STALE, UNKNOWN, or CONFLICTING**, every report must open with this warning, before any recommendations:

> **WARNING: CURRENT VITAL SYNC PRODUCT STATE COULD NOT BE VERIFIED. PRODUCT BUILD RECOMMENDATIONS ARE PROVISIONAL.**

## Conflict resolution

When two sources disagree, record in `reports/vital_sync/evidence_conflicts.json`: finding, source A, source B, both dates, the conflict, the resolution, the winning source, and why. **Newer *verified* evidence wins — not newer *asserted* evidence.** If neither side is independently checkable, the conflict stays open (`UNRESOLVED — PENDING VERIFICATION`), not silently resolved toward whichever is more recent or more convenient.

## Finding lifecycle

Every product-area finding carries one of: `NEW`, `ACTIVE`, `IMPROVING`, `RESOLVED`, `REGRESSED`, `STALE`, `UNVERIFIED`. A `RESOLVED` finding moves out of "Build Now" — it doesn't linger as an open action item forever, but it also doesn't vanish from history (see Resolved Findings section below).

## Evidence model

Every product-state claim in `vital_sync_product_state.json` carries: status, evidence, source, source date, verification method, freshness, confidence. No claim without all six.

## Persistent state files

- `reports/vital_sync/vital_sync_product_state.json` — the registry: per-area status, evidence, freshness, confidence, lifecycle. Updated every run, never silently overwritten without checking for conflicts against the previous version first.
- `reports/vital_sync/evidence_conflicts.json` — open and resolved conflicts between disagreeing sources.
- `reports/vital_sync/automation_log.jsonl` — per-run operational log (already existed; unrelated to product-state content).

## Layers

- **Layer A — Product Intelligence**: "What is actually built?" Gated by the Product Freshness Gate above. Never skip straight to Layer C using stale Layer A data.
- **Layer B — Market + Competition Intelligence**: "What's changing outside Vital Sync?" Independent of Layer A's freshness — competitor research is unaffected by whether the Vital Sync source is current.
- **Layer C — Gap Analysis**: "Given what Vital Sync actually has *today*, what matters?" Requires Layer A to be at least `LIKELY_CURRENT`; if Layer A is `STALE`/`UNKNOWN`, Layer C recommendations are explicitly marked provisional.

## Competitors tracked (not exhaustive — keep discovering)

Vora, Cora, FitCraft, Workout Quest, Habitica, Bitletics, RazFit (new, MONITOR: short 1-10min bodyweight sessions, badge gamification, consistency-over-intensity, limited confirmed scale, pricing incompletely verified — don't copy, watch for traction), WHOOP, Strava, Gentler Streak, Google Health/Gemini (treat as a **platform-scale threat**, not a product to copy — the pressure is wearable data + passive context + adaptive guidance + distribution; Vital Sync's answer is training+nutrition+recovery+alignment+behavior-change+gamification+squads together, not any single feature).

Evaluate competitors on mechanism, not a feature checklist: training, nutrition, recovery, wearables, readiness, daily recommendation, adaptive training, AI coach, gamification, streaks, social accountability, challenges, low-friction logging, progression, cross-system intelligence.

## The Alignment → Directive loop

Don't describe Vital Sync's differentiation as merely "an Alignment score." The fuller model, and the one competitors should be evaluated against:

```
Training + Nutrition + Recovery → Alignment → Today's Directive → Mission → Execution → Progress → Feedback
```

Fatigue-aware gamification (streak mechanics that respond to real recovery data) is a real strategic opportunity, but it depends on Recovery + Alignment + a Directive layer + eventually wearable data being reliable first — track the evidence for those dependencies rather than recommending it just because competitors lack it.

## Before assigning a priority bucket

Before marking anything `BUILD NOW` / `BUILD NEXT` / `IMPROVE EXISTING` / `EXPERIMENT` / `MONITOR` / `IGNORE`, check: is the finding current (per the freshness gate)? Already implemented, in progress, or approved? Does another already-approved stage solve it? Does it strengthen the core Alignment→Directive model? Is there real evidence of value? What has to exist first? What would success look like? If something is already implemented/in-progress/approved/queued, classify it `IN PROGRESS`, `AWAITING VALIDATION`, or `IMPLEMENTED — MEASURE` instead of re-raising it as a new `BUILD NOW`.

**Implementation doesn't end the decision process**: `DISCOVER → RECOMMEND → APPROVE → BUILD → IMPLEMENTED → MEASURE → KEEP/IMPROVE/REVERT`.

## Marketing/product mismatch checks

If the live marketing site can't be reached (as has been the case for `vitalsyncify.com` from the cloud sandbox for 4+ consecutive weeks — a network egress restriction, not a real-world outage), distinguish **source marketing state** (what the repo's own landing-page source says, if readable) from **deployed marketing state — UNVERIFIED**. A failed fetch is a coverage gap, not evidence of "no change" — never write "no marketing changes this week" when the real fact is "couldn't check this week."

## Temporal reasoning in every report

Every claim of "unchanged" requires the underlying source to have actually been reverified that run. Otherwise use `UNCHANGED — NOT REVERIFIED`, not `UNCHANGED — VERIFIED`. Full vocabulary: `NEW THIS WEEK`, `CHANGED THIS WEEK`, `UNCHANGED — VERIFIED`, `UNCHANGED — NOT REVERIFIED`, `STALE`, `RESOLVED`, `UNKNOWN`.

## Report structure

1. Executive Summary
2. Product Source Freshness (the gate's output — must appear before any recommendation)
3. Product State Delta (what moved since last report, per area)
4. Current Vital Sync State
5. Resolved Findings
6. Remaining Weaknesses
7. Vital Sync Strengths
8. Cross-System Audit
9. Competitor Changes
10. New Entrants
11. Competitive Position
12. Customer Pain Intelligence
13. Customer Praise Intelligence
14. Search Demand
15. Market Trends
16. Product Opportunities
17-22. Build Now / Improve Existing / Build Next / Experiment / Monitor / Ignore
23. Opportunity Movement
24. Evidence Conflicts
25. Sources / Evidence

## No fabrication

Never fabricate competitor features, pricing, user counts, retention, revenue, launch dates, product functionality, or Vital Sync implementation status. Use `CONFIRMED` / `LIKELY` / `UNVERIFIED` / `UNKNOWN` — not silence, and not invented specificity.

## Known limitation (as of 2026-09-07)

**This workflow has no Priority-1 access to Vital Sync's real current state.** The GitHub mirror is the best available source and is currently confirmed stale. Until either the mirror is kept in sync with Replit, or some other checkable access path exists, every report's Product Source Freshness section will likely read `STALE`, and product-state build recommendations will carry the provisional warning. This is the honest state of things, not a bug to hide.
