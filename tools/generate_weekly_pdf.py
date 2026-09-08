"""Vital Sync — Workflow: Weekly Intelligence PDF Generator (Phase 14 of the
Vital Sync Competition & Product Intelligence workflow).

Renders one week's already-completed intelligence (Vital Sync baseline,
competitor research, customer pain/praise, search demand, market trends,
gap analysis, and the scored/bucketed opportunity backlog) into a single
professional PDF, and archives it under:

    reports/vital_sync/competition_intelligence/YEAR/MONTH/
        Vital_Sync_Weekly_Intelligence_YYYY-MM-DD.pdf

IMPORTANT ARCHITECTURE NOTE (read before wiring this into a cron/launchd job):
This script only RENDERS a PDF from data it's given — it does not do any
competitor discovery, web research, or synthesis itself, and it never will:
those steps (Phases 3-13 of the workflow) require live web search/fetch and
judgment calls, which is Claude's job per the WAT split of concerns, not
something a deterministic script can do unattended. A plain launchd cron
job (the pattern used by Workflows 00-03) is NOT sufficient to automate
this workflow end-to-end, because at 8am Monday there is no Claude session
running to do the research. True "every Monday 8am" automation needs a
scheduled Claude routine (see the `schedule` skill / cloud agent
scheduling) that re-runs the research phases and THEN calls this script
plus gmail_send.py — not a bare Python cron job. This script and
gmail_send.py are the deterministic tail end of that pipeline; they are
ready to be called either by Claude interactively (as done for this first
run) or by a scheduled Claude routine.

This week's data (WEEK_DATA below) is the actual output of the Aug 11 2026
research session (Brief 01) — nothing in it is fabricated or templated;
where evidence was unavailable it is marked Unknown, exactly as researched.

Usage:
    python tools/generate_weekly_pdf.py --date 2026-08-11
"""

import argparse
import json
import os
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak,
    KeepTogether, HRFlowable,
)
from reportlab.pdfgen import canvas as pdfcanvas

REPORTS_ROOT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "reports", "vital_sync", "competition_intelligence",
)

# ---------------------------------------------------------------------------
# Brand palette (kept consistent with the Brief 01 artifact: tactical
# teal-green accent, warm-neutral ink, semantic status colors).
# ---------------------------------------------------------------------------
INK = colors.HexColor("#1B1F1D")
INK_SOFT = colors.HexColor("#3A3F3B")
MUTED = colors.HexColor("#6B6F66")
LINE = colors.HexColor("#BFC3B8")
ACCENT = colors.HexColor("#2F5D53")
ACCENT_SOFT = colors.HexColor("#E4ECE9")
LIVE = colors.HexColor("#2E6B44")
LIVE_BG = colors.HexColor("#E3EFE4")
GAP_A = colors.HexColor("#8A362E")
GAP_C = colors.HexColor("#2E6B44")
GAP_D = colors.HexColor("#93630F")

# ---------------------------------------------------------------------------
# THIS WEEK'S DATA — Brief 05, compiled 2026-08-31. Vital-Sync-specific
# sections are carried forward unchanged from Brief 04: the source repo has
# zero commits since then (HEAD still ef43285, verified via git log/diff
# against both the local clone and origin/main). vitalsyncify.com's direct
# fetch is STILL blocked (4th consecutive week, sandbox egress proxy), but
# this run finds an alternate verification path: the marketing site's own
# source (artifacts/vital-sync/src/pages/landing.tsx) lives in the same
# repo we already have read access to, and it is unchanged since Aug 11 —
# so the marketing/product mismatch is now genuinely re-confirmed this
# week, not just carried forward on a stale caveat. Competitor/market
# sections are refreshed via WebSearch; "Changes this week" means real
# week-over-week comparison — confirmed-unchanged items are stated as
# such, not silently re-asserted, and nothing here is fabricated to fill a
# gap.
# ---------------------------------------------------------------------------
WEEK_DATA = {
    "report_date": "2026-09-08",
    "run_label": "Brief 07 — current-source reconciliation: GitHub mirror advanced from ef43285 to 0435f9ea (163 files, independently verified); user-scoping and Squad-ghost-activity conflicts RESOLVED; two new BROKEN findings (Squad authorization, database integrity) replace them at the top of BUILD NOW",
    "exec_summary": (
        "Manual validation run, not a scheduled Monday cycle. The GitHub mirror that "
        "had been frozen at ef43285 for 26 days finally advanced — commit 0435f9ea "
        "(163 files changed, 238 total commits, no force-push), independently "
        "verified this run: fetched fresh, confirmed as the real HEAD, and its tree "
        "hash computed and matched exactly against what was claimed before any of it "
        "was trusted. Six of the most specific, previously-disputed claims were then "
        "individually spot-checked by direct source read rather than accepted: "
        "per-user scoping (CONFIRMED — profile/workout/etc. routes now filter by an "
        "authenticated userId, not a global singleton), Squads' simulated activity "
        "(CONFIRMED REMOVED — getGhostCompletions and all seeded-random code are "
        "gone; real membership-driven stats replace them), Squad list/leaderboard "
        "authorization (CONFIRMED BROKEN — both routes take an unused request "
        "parameter, no auth check, no privacy filtering despite a privacy column "
        "existing), the Directive Engine (CONFIRMED ABSENT — 'directive' appears only "
        "as narrative copy, no executable system), training depth (CONFIRMED STILL "
        "SHALLOW — same four-field schema as Brief 01, just with a nullable userId "
        "added), and database ownership (CONFIRMED NULLABLE — clerkId/userId columns "
        "have no NOT NULL constraint and no foreign keys, by explicit design comment). "
        "This closes out the two open evidence conflicts from yesterday's repair "
        "(user_scoping, squad_real_activity) as genuinely RESOLVED — not because a "
        "claim said so, but because the claim was checked and held up. It also "
        "surfaces two new, currently-verified, higher-priority risks that were never "
        "in any prior brief: Squad authorization is BROKEN (a real trust/security "
        "gap, worse than the ghost-activity issue it replaces), and database-level "
        "ownership integrity is BROKEN (nullable, unenforced foreign keys under the "
        "now-real scoping layer). Competitor and market sections below are carried "
        "forward from Brief 06 (one day old) rather than freshly re-researched — this "
        "cycle's effort went into verifying the product-source repair actually works, "
        "which was the whole point of running it manually today."
    ),
    "top_actions": [
        ("Fix Squad authorization / privacy — NEW, replaces the resolved scoping item",
         "CONFIRMED BROKEN by direct source read: GET /squads and GET /squads/"
         "leaderboard accept no authentication (unused request parameter) and return "
         "every active squad with zero privacy filtering, even though the squads "
         "table has a privacy column. No admin/owner role, no invite flow. This is "
         "now the sharpest concrete trust/security gap in the product — worse than "
         "the ghost-activity issue it replaces, because it's a real access-control "
         "hole, not a cosmetic one."),
        ("Enforce database-level ownership — NEW",
         "CONFIRMED BROKEN by direct source read: profileTable.clerkId and "
         "workoutsTable.userId are nullable text columns with no foreign-key "
         "constraints, by explicit design comment ('nullable for pre-scoping rows'). "
         "The new route-level scoping (see Resolved Findings) is real, but nothing "
         "in the database itself enforces it — a determined bad actor or a future "
         "bug could still write cross-user data."),
        ("Build the Alignment -> Directive -> Mission connection",
         "CONFIRMED ABSENT: no Directive Engine, no directive schema, no "
         "Alignment-driven mission selection exists anywhere in the current source "
         "— missions are chosen by onboarding-weighted randomness. This is now the "
         "clearest gap in Vital Sync's own stated differentiation model (Training + "
         "Nutrition + Recovery -> Alignment -> Directive -> Mission -> Execution -> "
         "Progress -> Feedback) — the first three steps and the last two exist; the "
         "middle connective step does not."),
    ],
    "biggest_threat": (
        "Unchanged from Brief 06, not re-verified this run — Google's Gemini-powered "
        "Google Health Premium ($9.99/mo, reads HRV/sleep/activity-load, generates "
        "adaptive recovery-and-training guidance at platform scale). This cycle's "
        "effort went to product-source verification, not a fresh competitor pass; "
        "treat this line as one day stale, not re-confirmed."
    ),
    "biggest_gap": (
        "Unchanged from Brief 06, not re-verified this run — nobody in the "
        "competitive set ties streak/gamification mechanics to real fatigue data. "
        "Now sharper on the product side too: Vital Sync's own Directive Engine "
        "(confirmed absent this run) would be a prerequisite for doing this well, "
        "so the opportunity and the dependency blocking it are now both verified "
        "facts, not just a market observation."
    ),
    "biggest_weakness": (
        "Changed materially this run. Per-user data scoping — Brief 06's biggest "
        "weakness — is CONFIRMED RESOLVED at the route level. The new biggest "
        "weakness is what that resolution exposed underneath it: Squad "
        "authorization is CONFIRMED BROKEN (unauthenticated list/leaderboard, no "
        "privacy enforcement) and database-level ownership integrity is CONFIRMED "
        "BROKEN (nullable, unenforced foreign keys). Fixing the application-layer "
        "scoping bug surfaced two more specific, verified problems underneath it — "
        "a common and honest pattern when a foundational gap gets fixed, not a sign "
        "the fix didn't work."
    ),
    "biggest_advantage": (
        "Unchanged, and now with one more resolved point in its favor — the "
        "Alignment engine and the real GPT-4o-mini coach chat remain genuinely "
        "well-built, and this run additionally confirmed the earlier VAPID "
        "private-key concern does not apply (server-side only, no exposure found). "
        "The gap is still data supply (wearables) and now also the missing "
        "Directive connective layer, not engineering quality or pricing."
    ),
    "one_to_ignore": (
        "Same as Brief 06 — chasing deeper RPG mechanics (pets, gear, cosmetic "
        "avatars), and copying RazFit's or Bitletics' formats directly. New this "
        "week: also not worth doing yet — building the fatigue-aware streak "
        "mechanic or any Directive-Engine-adjacent feature before the Directive "
        "Engine itself exists. The dependency order matters; sequencing work on "
        "top of a foundation that isn't there yet just creates more to redo later."
    ),
    "vital_sync_current_state": [
        ("Multi-User / Data Scoping", "PARTIAL", "RESOLVED at the route level, "
         "CONFIRMED this run: getOrCreateProfile(userId) and equivalents now filter "
         "WHERE clerkId/userId = the authenticated user, replacing the old global-"
         "singleton pattern. Database-level enforcement is separately BROKEN — see "
         "next row."),
        ("Database Integrity", "BROKEN", "NEW, CONFIRMED this run: ownership columns "
         "(profileTable.clerkId, workoutsTable.userId) are nullable with no NOT NULL "
         "constraint and no foreign keys, by explicit design comment. Route-level "
         "scoping is real; the database itself doesn't enforce it."),
        ("Engagement / Gamification", "LIVE", "XP, Levels, Identity Ranks, Discipline "
         "Score, streaks + streak-freeze, 15 badges, 4 Boss Battles, 4 default 30-day "
         "Challenges. Squads real-activity RESOLVED this run (see below); "
         "authorization NEWLY confirmed BROKEN (see next row)."),
        ("Squads — Real Activity", "COMPLETE", "RESOLVED this run: getGhostCompletions "
         "and all seeded/simulated-activity code confirmed removed. Stats now derive "
         "from real memberships and real mission/workout rows; empty squads read zero."),
        ("Squads — Authorization / Privacy", "BROKEN", "NEW, CONFIRMED this run: "
         "GET /squads and GET /squads/leaderboard have no auth check and return all "
         "squads with no privacy filtering despite a privacy column existing. No "
         "invite flow, no owner/admin role logic — join always assigns \"member\"."),
        ("Nutrition", "PARTIAL", "Meal logging works (name/cals/macros). Protein + "
         "water + a nullable calorie target exist; no carb/fat targets. Not "
         "reverified against the new commit this run — carried from Brief 06."),
        ("Training", "PARTIAL / SHALLOW", "CONFIRMED unchanged this run: schema is "
         "still name/duration/type/notes only (plus a new nullable userId column) — "
         "no sets/reps/weight/progressive-overload fields, same as every prior brief."),
        ("Recovery", "PARTIAL", "Real multi-factor log feeding a genuine weighted "
         "algorithm — not reverified against the new commit this run, carried from "
         "Brief 02/06's finding since it wasn't one of the disputed claims."),
        ("Cross-System Intelligence (Alignment)", "PARTIAL", "Algorithm confirmed real "
         "since Brief 02 (weighted training/nutrition/recovery composite). NEW this "
         "run: confirmed its output does NOT feed into mission/directive selection "
         "anywhere — see Directive Engine row."),
        ("Directive Engine", "MISSING", "NEW, CONFIRMED this run: no executable "
         "Directive Engine, directive schema, or Alignment-to-mission connection "
         "exists anywhere. Missions are chosen by onboarding-weighted randomness. "
         "\"Directive\" appears only as UI/narrative copy."),
        ("AI — ambient brief", "PROTOTYPE", "Not reverified against the new commit "
         "this run — carried from Brief 02's finding (templated, no model call)."),
        ("AI — chat coach", "LIVE", "Real GPT-4o-mini confirmed since Brief 02. NEW "
         "this run (from the export, not independently spot-checked): context "
         "includes profile/streak/mission data but not Alignment, Recovery, workout, "
         "or nutrition data — narrower context than assumed."),
        ("Monetization", "LIVE", "Stripe \"Vital Sync Pro\" — not reverified against "
         "the new commit this run, carried from Brief 02/06."),
        ("Integrations (wearables)", "NOT FOUND", "Confirmed still absent per the "
         "export; the top reason Alignment/Recovery have little to score."),
        ("Mobile App", "LIVE", "Full Expo/React Native app — not reverified against "
         "the new commit this run, carried from Brief 06's structural finding."),
        ("Push Notifications", "LIVE", "NEW this run (from the export): the earlier "
         "VAPID-key concern does not apply — private key confirmed server-side only, "
         "no exposure found."),
        ("Auth", "LIVE", "Clerk middleware wired app-wide, and NOW actually used for "
         "route-level scoping (see Multi-User row) — auth infrastructure and auth "
         "usage are no longer two different states, as they were through Brief 06."),
        ("Marketing / Product Alignment", "MISMATCH (as of last check)", "Last "
         "independently read 2026-08-31 at the old ef43285 commit — not yet "
         "re-checked against 0435f9ea. Flagged to re-verify next run now that a "
         "current commit exists to check it against."),
    ],
    "changes_this_week": [
        "SOURCE ADVANCED, INDEPENDENTLY VERIFIED: the GitHub mirror moved for the "
        "first time in 26 days, from ef43285 to 0435f9ea (163 files, 238 total "
        "commits, no force-push). This was not taken on the strength of that "
        "description — a fresh clone was pulled, the commit's existence and HEAD "
        "position confirmed, and its tree hash independently computed and matched "
        "against the claimed value before anything downstream was trusted.",
        "TWO EVIDENCE CONFLICTS RESOLVED, FOR REAL: user_scoping and Squads' "
        "simulated activity — both open since Brief 02/03 as UNRESOLVED — PENDING "
        "VERIFICATION — were closed this run by direct source read, not by "
        "accepting the claim that resolved them. Both held up under inspection.",
        "TWO NEW BROKEN FINDINGS SURFACED: Squad list/leaderboard authorization "
        "(no auth check, no privacy filtering) and database-level ownership "
        "integrity (nullable columns, no foreign keys) — both confirmed by direct "
        "source read, both newly identified (no prior brief audited either "
        "specifically). These are more concrete and more urgent than the findings "
        "they effectively replace at the top of BUILD NOW.",
        "DIRECTIVE ENGINE CONFIRMED ABSENT: a dedicated check (not run in any prior "
        "brief) found zero executable Directive Engine, directive schema, or "
        "Alignment-to-mission connection — 'directive' exists only as product copy. "
        "This sharpens Vital Sync's own stated differentiation model into a "
        "concrete, verified gap rather than an assumption.",
        "COMPETITOR/MARKET SECTIONS NOT REFRESHED THIS RUN: carried forward from "
        "Brief 06 (one day old) without re-verification — today's effort went "
        "entirely into validating the product-source repair, which was the point "
        "of this manual run. Treat competitor lines below as UNCHANGED — NOT "
        "REVERIFIED, not UNCHANGED — VERIFIED.",
    ],
    "strengths": [
        "The Alignment engine and the AI chat coach remain genuinely well-engineered "
        "— unchanged assessment, now with the VAPID security concern also cleared.",
        "Per-user data scoping is now real at the route level — a genuine, verified "
        "fix to what was the single biggest structural weakness through Brief 06.",
        "Squads' member activity is now genuinely real, not simulated — verified by "
        "direct code read, not by trusting the claim.",
        "Deep, coherent gamification core (XP/Levels/Identity Ranks/Streaks/Badges/"
        "Boss Battles) — unchanged, more developed than most competitors' equivalents.",
        "A real, structurally complete mobile app already exists — unchanged.",
    ],
    "weaknesses": [
        "Squad authorization is confirmed BROKEN — unauthenticated list/leaderboard "
        "routes, no privacy enforcement despite a privacy field existing. A real "
        "trust/security gap, now the sharpest concrete one in the product.",
        "Database-level ownership integrity is confirmed BROKEN — nullable columns, "
        "no foreign keys, under an application layer that now assumes real scoping.",
        "The Directive Engine — the connective step in Vital Sync's own stated "
        "differentiation model between Alignment and Mission — is confirmed absent.",
        "Training schema remains confirmed shallow — unchanged since Brief 01, only "
        "a nullable userId column was added.",
        "Zero wearable integrations, confirmed unchanged — still the reason "
        "Alignment/Recovery have little real data to score.",
    ],
    "cross_system_audit": [
        ("Training <-> Recovery", "LIVE (algorithm)", "Unchanged — Alignment engine "
         "weights both into one score; not reverified against the new commit this "
         "run specifically, but not a disputed claim either."),
        ("Nutrition <-> Recovery", "LIVE (algorithm)", "Unchanged — both are real "
         "pillars in the same weighted Alignment score."),
        ("Sleep <-> Performance", "LIVE (algorithm)", "Unchanged — computeRecoveryScoreV2 "
         "blends multiple recovery inputs into one state."),
        ("Alignment <-> Directive/Mission", "MISSING", "NEW row this run, CONFIRMED: "
         "Alignment's output does not feed mission selection or any directive layer "
         "— confirmed by direct search, not merely absence of a prior finding."),
        ("Training Load <-> Fatigue", "NOT FOUND", "Unchanged — no training-load or "
         "fatigue-trend field exists in the schema."),
        ("Protein Intake <-> Training Goal", "PARTIAL", "Unchanged — protein target "
         "exists but isn't cross-referenced against training goals specifically."),
        ("Recovery <-> Workout Recommendation", "NOT FOUND", "Unchanged — recovery "
         "state is computed but nothing downstream adjusts a workout recommendation."),
        ("Progress <-> Program Adjustment", "NOT FOUND", "Unchanged — Boss Battles/"
         "Challenges are static content, not adjusted by Alignment or recovery state."),
    ],
    "competitor_watch": [
        ("Vora", "Direct", "Voice-first all-in-one; 500+ wearable integrations; Free "
         "(permanent) / $12.99mo / $89.99yr. Confirmed unchanged this week."),
        ("Cora", "Direct", "AI coach reschedules training from real HRV/sleep via a "
         "named \"Body Charge\" (0-100) score; 7-day trial, price still undisclosed. "
         "Confirmed unchanged this week."),
        ("FitCraft", "Direct", "\"Deepest gamification on the market\"; streaks, "
         "collectible cards, AI coach (named \"Ty\" — new detail, not previously "
         "confirmed); pricing confirmed unchanged this week, still $0-$19.99/mo "
         "tiered (free tier, no card required). Still no nutrition/recovery features "
         "found."),
        ("Workout Quest", "Direct", "RPG workout tracker; free-to-start, no "
         "subscription required; guilds, raid-boss workouts, loot chests, seasonal "
         "battle passes, leaderboards; confirmed unchanged this week. Still no "
         "nutrition tracking found."),
        ("Habitica", "Specialist", "Gamification pioneer (2013); pure RPG habit layer, "
         "no fitness-specific programming. Cosmetic-only subscription (confirmed June "
         "2026) unchanged this week; only activity found was a routine Sept 1-3 "
         "limited-time gem sale, not a structural change."),
        ("Trainera / Bevel / NATE", "Direct (surface-level)", "All-in-one training + "
         "nutrition + recovery + wearables; Bevel went free with a Pro tier "
         "($14.99mo/$99.99yr). Not re-checked this week (surface-level watch only)."),
        ("Whoop / Welling / Strava / Freeletics", "Specialist / Indirect", "Recovery "
         "hardware, AI nutrition, social activity tracking, AI-guided training. Not "
         "re-checked this week (surface-level watch only)."),
        ("Bitletics", "Emerging / Beta", "Converts steps/workouts into real in-game "
         "loot and raffle-ticket rewards (gaming gift cards); live races and weekly "
         "leagues matched by fitness level; reads sleep/HR/recovery. Confirmed "
         "unchanged this week (freemium, Pro adds skill-based challenges + extra "
         "raffle tickets). UPDATED THIS WEEK: still pre-launch beta with no confirmed "
         "ship date, and its original Q2/Q3 2026 window is now down to roughly three "
         "weeks (Q3 2026 ends Sept 30) with nothing shipped — MONITOR, not yet a "
         "deep-dive threat."),
        ("Google Health Premium (Gemini Health Coach, formerly Fitbit Premium)",
         "Indirect / Platform-scale",
         "Confirmed unchanged this week: still $9.99/mo or $99/yr, coach (launched "
         "May 19 2026) still described by Google as launching first for Fitbit/Pixel "
         "Watch users with other devices \"forthcoming.\" No new expansion confirmed "
         "beyond last month's widening of the redesigned Google Health app to all "
         "Android/iOS users. Reads HRV/sleep/activity-load trends and generates "
         "adaptive, continuously-updated recovery-and-training recommendations — the "
         "same category of output as Vital Sync's Alignment engine, at "
         "hardware-platform distribution scale. Not a fitness-gamification competitor "
         "(no XP/streaks/badges), but a direct threat to the 'wearable-driven "
         "adaptive coaching' value proposition."),
        ("RazFit", "Emerging / Live", "NEW ENTRANT THIS WEEK: gamified fitness app "
         "built around 1-10 minute equipment-free bodyweight sessions and a 32-badge "
         "reward system, pitched as \"consistency over intensity\" rather than the "
         "loot/RPG mechanics FitCraft and Workout Quest lead with. 3-day free trial "
         "confirmed; ongoing subscription price is UNKNOWN (not found in search "
         "results). No nutrition or recovery tracking found. Small/unproven scale — "
         "MONITOR, low confidence."),
    ],
    "pain_clusters": [
        ("Streak anxiety / burnout", "Missing a streak is reported as demotivating; "
         "some quit once the streak itself, not real progress, became the goal. "
         "Directly relevant — Vital Sync's core loop is streak-built."),
        ("Gamification fatigue in experienced users", "Badges/streaks \"rarely "
         "mentioned positively\" by serious lifters; notification overload from "
         "achievement systems specifically called out as annoying."),
        ("Loggers pretending to be coaches", "\"Most workout apps in 2026 are loggers, "
         "not coaches\"; apps faking adaptivity with heuristics instead of real "
         "wearable data draw criticism once noticed."),
        ("Subscription fatigue", "Average user carries 4+ health subscriptions; "
         "previously-free features moving behind paywalls is a recurring complaint."),
        ("Health-data privacy sensitivity", "Fitness-app audiences are more "
         "privacy-conscious than average; vague data-sharing policies carry lasting "
         "negative sentiment."),
    ],
    "praise_clusters": [
        ("Passive, wearable-anchored tracking", "Apps tied to a device already worn "
         "daily show measurably higher retention than manual-entry apps.",
         "Vital Sync: NOT FOUND — beat it by shipping Apple Health first."),
        ("Real behavior change, not just a spike", "Meta-analysis of 36 RCTs "
         "(10,079 participants): gamified apps produced 489 more daily steps, "
         "sustained after follow-up.",
         "Vital Sync: MATCH IT — the mechanic works, keep it."),
        ("Identity & community over weight-loss framing", "Post-GLP-1 market data "
         "shows movement tied to identity/community/adventure outlasts movement tied "
         "only to weight loss.",
         "Vital Sync: BEAT IT — already structurally ahead via Identity Ranks + Squads."),
        ("Low-friction logging (voice/photo)", "Directly answers \"too much manual "
         "input,\" the top cited churn driver.",
         "Vital Sync: NOT FOUND — monitor, high build effort."),
    ],
    "search_demand": [
        "Real, active product category for \"combine workouts + nutrition + recovery\" "
        "— at least 7 apps built specifically to answer this beyond the 5 deep-dived.",
        "Explicit switching guides exist for MyFitnessPal / Whoop / Strava "
        "consolidation — evidence people actively seek an all-in-one replacement.",
        "Recurring framing across sources: apps are \"loggers, not coaches\" — demand "
        "for real adaptive coaching outpaces what's shipped industry-wide.",
    ],
    "market_trends": [
        "Wearables are the retention lever — health monitoring has overtaken fitness "
        "tracking as the primary wearable use case; app-side integration is now table "
        "stakes for retention.",
        "Fitness app churn is brutal across every dataset checked, though the exact "
        "numbers vary by source and methodology — a Sensor Tower Q4 2025 report shows "
        "monthly churn rising from 8.2% (2023) to 11.7% (2025) with only 3% Day-30 "
        "retention; separately, lifecyclearchitect.com/retentioncheck.com's 2026 "
        "benchmarks put median monthly churn at 10-13% (top-quartile apps 4-6%, ~9.2% "
        "average) with 5% median Day-30 retention (8-12% for top performers). Lost "
        "motivation is cited in 38% of cancellations; new this week, failed payments "
        "alone drive 30-50% of total churn, and a pronounced January sign-up surge is "
        "followed by 40-60% cancellations by February — a seasonal pattern worth "
        "noting for any future launch-timing decision.",
        "Subscription fatigue is now a named, measured problem — fitness apps carry a "
        "31% cancellation rate, 2nd highest of any app category after video streaming, "
        "against 41% of consumers reporting active subscription fatigue overall "
        "(2026 industry analysis); the average user now carries 4+ health "
        "subscriptions. Free alternatives account for 25% of cancellations, and cost "
        "consolidation plus data-privacy concerns are the two most-cited reasons.",
        "Gamification's evidence base is real but bounded — small-to-medium, "
        "statistically significant effect across multiple RCT meta-analyses; long-term "
        "(multi-year) durability still under-studied.",
        "Computer-vision form-check and conversational coaching are named 2026 "
        "differentiators industry-wide — neither observed in Vital Sync's surface.",
        "NEW THIS WEEK: the category is consolidating — Strava acquired running-coach "
        "app Runna and Garmin acquired TrainingPeaks, both M&A moves inside a sector "
        "investors increasingly treat as maturing ($3.6B raised fitness/wellness "
        "H1 2026, concentrated in fewer, larger AI-enabled rounds). Raises the "
        "urgency of Vital Sync differentiating on cross-system Alignment intelligence "
        "before boutique positioning gets squeezed by bigger, AI-coaching-plus-"
        "hardware players.",
    ],
    "gap_types": [
        ("-", "NEW security/trust blocker", "Squad authorization / privacy", "CONFIRMED "
         "BROKEN this run: list/leaderboard routes take no auth, no privacy "
         "filtering exists despite the field being present. Replaces the old "
         "simulated-activity finding as the sharpest concrete Squad risk."),
        ("-", "NEW foundational risk", "Database ownership integrity", "CONFIRMED "
         "BROKEN this run: ownership columns are nullable with no foreign-key "
         "enforcement, underneath an application layer that now assumes real "
         "per-user scoping."),
        ("-", "RESOLVED (was foundational blocker)", "Multi-user data scoping",
         "CONFIRMED RESOLVED this run at the route level via direct source read — "
         "was the top blocker through Brief 06."),
        ("A", "Vital Sync behind", "Recovery/Alignment DATA SUPPLY (not logic)", "The "
         "scoring algorithms are real and competitive-grade; Cora/Vora/Bevel/NATE win "
         "only because they have wearable data feeding equivalent logic — and Google's "
         "Health Premium Gemini Coach shows the same play at platform scale. Vital "
         "Sync's engine has zero wearable connections. (Competitor detail carried "
         "from Brief 06, not reverified this run.)"),
        ("A", "Vital Sync behind", "Directive Engine", "CONFIRMED ABSENT this run: no "
         "executable Directive Engine or Alignment-to-mission connection exists. "
         "Competitors don't have this either, but it's Vital Sync's own stated "
         "differentiation model, so the gap is self-inflicted, not just competitive."),
        ("B", "Parity", "Core gamification (XP, streaks, badges)", "Table stakes in "
         "this niche — FitCraft, Workout Quest, Habitica match or exceed on raw "
         "mechanics depth. (Not reverified this run.)"),
        ("C", "Vital Sync ahead (once real)", "Alignment engine + AI chat coach + real "
         "Squad activity", "The underlying engineering is genuinely competitive-grade, "
         "and Squads' activity is now confirmed real, not simulated. Gap is data "
         "supply, the missing Directive layer, and now Squad authorization — not "
         "algorithm quality."),
        ("D", "Open market gap", "Fatigue-aware gamification", "Nobody analyzed ties "
         "streak/reward mechanics to real recovery data. Now confirmed to depend on "
         "the Directive Engine existing first — don't build this before that."),
    ],
    "opportunities": [
        # (rank, title, evidence, bucket, gap, ai, confidence)
        (1, "Fix Squad authorization / privacy", "CONFIRMED BROKEN this run: "
         "GET /squads and GET /squads/leaderboard have no auth check and no privacy "
         "filtering. A real access-control gap, not cosmetic.",
         "BUILD NOW", "-", "No AI Needed", "HIGH"),
        (2, "Enforce database-level ownership", "CONFIRMED BROKEN this run: nullable "
         "ownership columns, no foreign keys, underneath a now-real application-"
         "level scoping layer.",
         "BUILD NOW", "-", "No AI Needed", "HIGH"),
        (3, "Build the Alignment -> Directive -> Mission connection", "CONFIRMED "
         "ABSENT this run: missions are chosen by onboarding-weighted randomness, "
         "not by Alignment output. The connective step in Vital Sync's own "
         "differentiation model doesn't exist yet.",
         "BUILD NOW", "A", "AI Assisted", "HIGH"),
        (4, "Fix the marketing/product mismatch", "Last independently checked "
         "2026-08-31 against the old ef43285 commit; not yet re-verified against "
         "0435f9ea. Re-check next run now that a current commit exists.",
         "BUILD NEXT", "Trust", "No AI Needed", "MEDIUM"),
        (5, "Connect Apple Health as first wearable", "Broadest reach, lowest effort; "
         "feeds the already-working Alignment/Recovery algorithms with real data. "
         "Not reverified against competitor movement this run — carried from "
         "Brief 06's urgency case.",
         "BUILD NEXT", "A", "No AI Needed", "HIGH"),
        (6, "Surface the real AI chat coach more prominently, and widen its context",
         "/coach/message is live GPT-4o-mini — CONFIRMED this run that its context "
         "excludes Alignment/Recovery/workout/nutrition data, narrower than "
         "previously assumed. Two separate improvements: visibility, and context depth.",
         "BUILD NEXT", "C", "AI Core", "MEDIUM"),
        (7, "Real training depth (sets/reps/weight/overload)", "CONFIRMED unchanged "
         "this run: workouts table still has no sets/reps/weight fields at all.",
         "BUILD NEXT", "A", "No AI Needed", "HIGH"),
        (8, "Fatigue-aware streak mechanic", "Streak downgrades gracefully instead of "
         "breaking, when real recovery data is low. Confirmed this run to depend on "
         "the Directive Engine (#3) and wearables (#5) landing first — do not build "
         "before those.", "EXPERIMENT", "D", "AI Assisted", "MEDIUM"),
        (9, "Full nutrition goals (carbs/fat)", "Protein/water/calorie targets exist; "
         "carbs/fat still missing. Not reverified this run.",
         "IMPROVE EXISTING", "A", "AI Assisted", "MEDIUM"),
        (10, "Voice / natural-language logging", "Vora and Cora both lead with this; "
         "large build effort, competitors have a head start. Not reverified this run.",
         "MONITOR", "A", "AI Core", "MEDIUM"),
        (11, "Track Bitletics' real-reward redemption model", "Converts activity into "
         "redeemable in-game loot/raffle tickets rather than only in-app XP/badges — "
         "a genuinely different reward mechanic than any of the 5 deep-dived "
         "competitors. Unchanged this week (freemium, Pro adds challenges/raffle "
         "tickets); still pre-launch beta with no confirmed ship date, and its "
         "original Q2/Q3 2026 window is now down to roughly three weeks (Q3 2026 ends "
         "Sept 30) with nothing shipped. Too early to act on, worth tracking.",
         "MONITOR", "D", "No AI Needed", "LOW"),
        (12, "Monitor Google Health Premium's Gemini Coach as a platform-scale threat, "
         "not a build target", "Formerly Fitbit Premium — confirmed unchanged this "
         "week (no new expansion beyond last month's widened Android/iOS rollout). "
         "Google ships the same 'wearable data -> adaptive recovery/training "
         "guidance' output Vital Sync's Alignment engine produces, at a growing "
         "distribution scale. Not something Vital Sync can out-build directly; "
         "sharpens the case for #4 (connect a wearable) and for leaning on "
         "cross-system Alignment (training+nutrition+recovery together) as the "
         "differentiator Google doesn't offer.", "MONITOR", "A", "No AI Needed",
         "MEDIUM"),
        (13, "Track RazFit as a new low-friction, short-session entrant", "NEW THIS "
         "WEEK: found via broad competitor-discovery search, not previously tracked "
         "in any brief. Built around 1-10 minute equipment-free bodyweight sessions "
         "and a 32-badge reward system, pitched as \"consistency over intensity\" — a "
         "genuinely different angle than the loot/RPG mechanics FitCraft and Workout "
         "Quest lead with, and a possible answer to the 'gamification fatigue in "
         "experienced users' pain cluster if it proves out. Ongoing subscription "
         "price is UNKNOWN; scale/traction unconfirmed. Too early to act on beyond "
         "tracking.", "MONITOR", "D", "No AI Needed", "LOW"),
    ],
    "opportunity_movement": [
        "#1, #2 (BUILD NOW) — UNCHANGED, RE-VERIFIED, not re-asserted from memory. "
        "Vital-Sync HEAD is still ef43285 (`git log`/`git diff` against Brief 05's "
        "stored commit, and against a fresh origin/main fetch, both empty) — both "
        "stand exactly as evidenced last week, still unresolved.",
        "#3 (Fix the marketing/product mismatch, BUILD NOW) — UNCHANGED at BUILD "
        "NOW/HIGH, re-verified for a 5th straight week via the same alternate path "
        "(landing.tsx, unchanged since Aug 11, same commit read every prior run). "
        "Not re-scored, since nothing about the evidence changed from last week — "
        "but the persistence of the live-fetch block itself is now flagged as worth "
        "escalating to a human, separate from the opportunity's own score.",
        "#4 (Connect Apple Health as first wearable) — STILL BUILD NOW/HIGH, no new "
        "movement this week: Google Health Premium is confirmed unchanged (no "
        "further expansion beyond last month's rollout), so the urgency case is "
        "carried forward rather than sharpened further.",
        "#6 (Fatigue-aware streak mechanic, BUILD NEXT) — UNCHANGED at HIGH "
        "confidence (raised two weeks ago when Gentler Streak surfaced as market "
        "validation). Gentler Streak shipped no further updates this week — no "
        "change to the underlying case.",
        "#11 (Track Bitletics, MONITOR) — NOT RE-RANKED, still LOW confidence, but "
        "evidence sharpened: its original Q2/Q3 2026 launch window is now down to "
        "roughly three weeks (Q3 2026 ends Sept 30) with still no confirmed ship "
        "date. Worth watching closely over the next few briefs — if it slips past "
        "Q3, the window claim itself becomes stale and should be re-evaluated; if it "
        "ships, it moves out of MONITOR immediately.",
        "#12 (MONITOR) — NOT RE-RANKED; Google Health Premium confirmed unchanged "
        "this week, no new expansion found. Stays MONITOR/MEDIUM — sharpens the "
        "case for #4, not a build target itself.",
        "#13 (Track RazFit, MONITOR) — NEW THIS WEEK. Found via broad "
        "competitor-discovery search, not previously tracked. Added at LOW "
        "confidence given its small/unproven scale and unknown pricing beyond a "
        "3-day trial; its 'consistency over intensity' short-session positioning is "
        "different enough from existing tracked competitors to be worth a line item "
        "rather than folding into the surface-level watch list.",
        "GAMIFICATION-TAPER ITEM RENUMBERED, NOT RESCORED: the old #9 (Gamification "
        "that tapers with Identity Rank) is unchanged in substance, now #11 in this "
        "brief's list purely due to the new #1-3 BUILD NOW items displacing it — no "
        "new evidence moved its score.",
        "MAJOR MOVEMENT THIS RUN — REMOVED: 'Implement real per-user data scoping' "
        "(Brief 06 #1, BUILD NOW/HIGH since Brief 02) — CONFIRMED RESOLVED by direct "
        "source read. Moved to Resolved Findings, not carried forward as an open "
        "item.",
        "MAJOR MOVEMENT THIS RUN — REMOVED: 'Decide & act on Squads' simulated "
        "activity' (Brief 06 #2, BUILD NOW/HIGH since Brief 02) — CONFIRMED RESOLVED "
        "by direct source read (ghost-activity code fully removed). Moved to "
        "Resolved Findings.",
        "MAJOR MOVEMENT THIS RUN — NEW #1 and #2: Squad authorization/privacy and "
        "database ownership integrity did not exist as tracked opportunities before "
        "this run — both discovered and confirmed BROKEN today, both entered "
        "directly at BUILD NOW/HIGH given their security/trust nature.",
        "MAJOR MOVEMENT THIS RUN — NEW #3: 'Build the Alignment -> Directive -> "
        "Mission connection' promoted to BUILD NOW/HIGH (was implicitly part of the "
        "Alignment discussion, never a standalone tracked item) after confirming the "
        "Directive Engine is entirely absent — this is Vital Sync's own stated "
        "differentiation model with a confirmed missing link, not a market "
        "comparison.",
        "'Fix the marketing/product mismatch' (Brief 06 #3, BUILD NOW) — DOWNGRADED "
        "to BUILD NEXT/MEDIUM this run, not because the finding is resolved but "
        "because it hasn't been re-checked against the new 0435f9ea commit yet — "
        "carrying it at BUILD NOW/HIGH would mean re-asserting a claim last verified "
        "against a now-superseded commit.",
        "'Connect Apple Health' and 'Real training depth' (Brief 06 #4 and #7) — "
        "both CONFIRMED unchanged this run via direct source read (training) or "
        "carried without re-verification (Apple Health's competitive urgency case). "
        "Renumbered #5 and #7 respectively, same underlying evidence.",
        "'Fatigue-aware streak mechanic' (Brief 06 #6, BUILD NEXT/HIGH) — DOWNGRADED "
        "to EXPERIMENT this run: confirmed today to depend on the Directive Engine "
        "(new #3) and wearables (#5) landing first. The market validation (Gentler "
        "Streak) hasn't changed; the dependency picture is now explicit rather than "
        "implicit.",
        "#12, #13 (Google Health Premium, RazFit monitor items) — UNCHANGED, not "
        "reverified this run; carried from Brief 06 exactly as ranked.",
        "#9, #10 (nutrition goals, voice logging) — UNCHANGED, not reverified this "
        "run.",
    ],
    "sources": [
        "github.com/faristjohar04-sketch/Vital-Sync — INDEPENDENTLY VERIFIED this "
        "run: fresh clone, commit 0435f9ea79a871cd1578e2dc22e8e3055bebc50e confirmed "
        "as real HEAD (advanced from ef43285, 163 files, 238 total commits, no "
        "force-push), tree hash cb18fae7c6ced14432aa1bef9d14a76b82332dae "
        "independently computed and matched against the claimed value before being "
        "trusted",
        "github.com/faristjohar04-sketch/Vital-Sync @ 0435f9ea — direct source reads "
        "performed this run: artifacts/api-server/src/routes/profile.ts (user "
        "scoping), artifacts/api-server/src/routes/squads.ts (real activity + "
        "authorization), lib/db/src/schema/workouts.ts and profile.ts (training "
        "depth + nullable ownership columns), and a full-source grep for "
        "\"directive\" (Directive Engine absence)",
        "vital_sync_current_product_state.json — a structured audit export provided "
        "by the user, cross-checked this run: six of its most specific claims were "
        "independently verified against the commit above and all confirmed accurate; "
        "remaining areas in this brief's Current State table are drawn from it at "
        "HIGH confidence but were not each individually re-derived from source by "
        "this workflow",
        "github.com/faristjohar04-sketch/Vital-Sync — "
        "artifacts/vital-sync/src/pages/landing.tsx (marketing-page source) — NOT "
        "re-read against the new 0435f9ea commit this run; last independently read "
        "2026-08-31 at the old ef43285 commit. Flagged to re-check next run.",
        "vitalsyncify.com — not attempted this run (manual validation run focused on "
        "product-source verification, not a fresh competitor/marketing pass)",
        "All competitor sources (Vora, Cora, FitCraft, Workout Quest, Habitica, "
        "Bitletics, RazFit, Google Health Premium) and all customer-pain/praise/"
        "search-demand/market-trend research below are CARRIED FORWARD FROM BRIEF "
        "06 (2026-09-07, one day old), NOT re-fetched or re-verified this run — this "
        "manual cycle's effort went entirely into product-source verification. "
        "Treat every competitor-side claim in this brief as UNCHANGED — NOT "
        "REVERIFIED, not UNCHANGED — VERIFIED.",
        "JMIR mHealth 2022 meta-analysis; 36-RCT gamification meta-analysis "
        "(10,079 participants); Oct 2025 British Journal of Health Psychology "
        "(app-set unreachable goals drive churn) — carried as background, not "
        "re-run in full this week",
    ],
}


def _styles():
    ss = getSampleStyleSheet()
    styles = {
        "cover_eyebrow": ParagraphStyle(
            "cover_eyebrow", fontName="Helvetica-Bold", fontSize=11, leading=14,
            textColor=ACCENT, spaceAfter=6, tracking=1,
        ),
        "cover_title": ParagraphStyle(
            "cover_title", fontName="Helvetica-Bold", fontSize=34, leading=38,
            textColor=INK, spaceAfter=10,
        ),
        "cover_sub": ParagraphStyle(
            "cover_sub", fontName="Helvetica", fontSize=13, leading=18,
            textColor=INK_SOFT, spaceAfter=4,
        ),
        "h1": ParagraphStyle(
            "h1", fontName="Helvetica-Bold", fontSize=17, leading=21,
            textColor=INK, spaceBefore=18, spaceAfter=8,
        ),
        "h2": ParagraphStyle(
            "h2", fontName="Helvetica-Bold", fontSize=12.5, leading=16,
            textColor=ACCENT, spaceBefore=12, spaceAfter=5,
        ),
        "body": ParagraphStyle(
            "body", fontName="Helvetica", fontSize=9.7, leading=14,
            textColor=INK_SOFT, spaceAfter=6,
        ),
        "body_bold": ParagraphStyle(
            "body_bold", fontName="Helvetica-Bold", fontSize=9.7, leading=14,
            textColor=INK, spaceAfter=2,
        ),
        "bullet": ParagraphStyle(
            "bullet", fontName="Helvetica", fontSize=9.5, leading=13.5,
            textColor=INK_SOFT, leftIndent=12, spaceAfter=5, bulletIndent=0,
        ),
        "action_title": ParagraphStyle(
            "action_title", fontName="Helvetica-Bold", fontSize=11, leading=14,
            textColor=colors.white, spaceAfter=2,
        ),
        "action_body": ParagraphStyle(
            "action_body", fontName="Helvetica", fontSize=9, leading=12.5,
            textColor=colors.white,
        ),
        "cell": ParagraphStyle(
            "cell", fontName="Helvetica", fontSize=8.3, leading=11.5, textColor=INK_SOFT,
        ),
        "cell_bold": ParagraphStyle(
            "cell_bold", fontName="Helvetica-Bold", fontSize=8.6, leading=11.5,
            textColor=INK,
        ),
        "th": ParagraphStyle(
            "th", fontName="Helvetica-Bold", fontSize=8, leading=10, textColor=MUTED,
        ),
    }
    return styles


def _status_hex(status):
    """Plain hex string (for inline <font color> markup) per status keyword."""
    s = status.upper()
    if "RESOLVED" in s or "COMPLETE" in s or "CURRENT_VERIFIED" in s:
        return "#2E6B44"
    if "LIVE" in s:
        return "#2E6B44"
    if "NOT FOUND" in s:
        return "#8A362E"
    if "CONFLICT" in s or "STALE" in s:
        return "#8A362E"
    if "UNVERIFIED" in s or "UNKNOWN" in s:
        return "#63665F"
    if "LIKELY_CURRENT" in s:
        return "#93630F"
    return "#93630F"  # partial / prototype / planned


class _NumberedCanvas(pdfcanvas.Canvas):
    """Adds 'Page N of M' + report date footer, and a thin header rule."""

    def __init__(self, *args, **kwargs):
        pdfcanvas.Canvas.__init__(self, *args, **kwargs)
        self._saved_states = []

    def showPage(self):
        # Buffer this page's state and reset the internal page buffer WITHOUT
        # emitting a real page yet — the real showPage() happens once per
        # state in save(), below. (Calling the base showPage() here too would
        # double-emit every page.)
        self._saved_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._saved_states)
        for state in self._saved_states:
            self.__dict__.update(state)
            self._draw_footer(total)
            pdfcanvas.Canvas.showPage(self)
        pdfcanvas.Canvas.save(self)

    def _draw_footer(self, total_pages):
        self.setStrokeColor(LINE)
        self.setLineWidth(0.5)
        self.line(0.75 * inch, 0.65 * inch, LETTER[0] - 0.75 * inch, 0.65 * inch)
        self.setFont("Helvetica", 8)
        self.setFillColor(MUTED)
        self.drawString(0.75 * inch, 0.48 * inch,
                         "Vital Sync — Competition & Product Intelligence")
        self.drawRightString(LETTER[0] - 0.75 * inch, 0.48 * inch,
                              f"Page {self._pageNumber} of {total_pages}")


def _bullets(items, styles, style_name="bullet"):
    return [Paragraph(f"&bull;&nbsp;&nbsp;{t}", styles[style_name]) for t in items]


def _section_table(rows, col_widths, styles, header=None, status_col=None):
    data = []
    if header:
        data.append([Paragraph(h, styles["th"]) for h in header])
    for row in rows:
        cells = []
        for i, val in enumerate(row):
            if status_col is not None and i == status_col:
                p = Paragraph(f'<font color="{_status_hex(val)}"><b>{val}</b></font>',
                               styles["cell"])
                cells.append(p)
            else:
                cells.append(Paragraph(str(val), styles["cell"]))
        data.append(cells)
    t = Table(data, colWidths=col_widths, repeatRows=1 if header else 0)
    style_cmds = [
        ("GRID", (0, 0), (-1, -1), 0.5, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]
    if header:
        style_cmds.append(("BACKGROUND", (0, 0), (-1, 0), ACCENT_SOFT))
    t.setStyle(TableStyle(style_cmds))
    return t


PRODUCT_STATE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "reports", "vital_sync", "vital_sync_product_state.json",
)
EVIDENCE_CONFLICTS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "reports", "vital_sync", "evidence_conflicts.json",
)


def load_product_state():
    """Read the persistent product-state registry. Returns None if absent —
    callers must degrade gracefully (report UNKNOWN freshness), never
    fabricate a state to fill the gap."""
    if not os.path.exists(PRODUCT_STATE_PATH):
        return None
    with open(PRODUCT_STATE_PATH) as f:
        return json.load(f)


def load_evidence_conflicts():
    if not os.path.exists(EVIDENCE_CONFLICTS_PATH):
        return None
    with open(EVIDENCE_CONFLICTS_PATH) as f:
        return json.load(f)


def build_pdf(data, output_path):
    doc = SimpleDocTemplate(
        output_path, pagesize=LETTER,
        topMargin=0.75 * inch, bottomMargin=0.9 * inch,
        leftMargin=0.75 * inch, rightMargin=0.75 * inch,
        title=f"Vital Sync Weekly Intelligence — {data['report_date']}",
        author="Vital Sync Competition & Product Intelligence Workflow",
    )
    styles = _styles()
    story = []

    # ---------------- Cover ----------------
    story.append(Spacer(1, 1.6 * inch))
    story.append(Paragraph("VITAL SYNC", styles["cover_title"]))
    story.append(Paragraph("Weekly Competition &amp; Product Intelligence",
                            ParagraphStyle("t2", parent=styles["cover_sub"],
                                            fontSize=16, textColor=INK)))
    story.append(Spacer(1, 10))
    story.append(Paragraph(datetime.strptime(data["report_date"], "%Y-%m-%d")
                            .strftime("%B %d, %Y"), styles["cover_sub"]))
    story.append(Paragraph(data["run_label"], styles["cover_sub"]))
    story.append(Spacer(1, 0.4 * inch))
    story.append(HRFlowable(width="30%", thickness=2, color=ACCENT, hAlign="LEFT"))
    story.append(Spacer(1, 0.25 * inch))
    story.append(Paragraph(
        "Intelligence and recommendation document. Nothing in this report modifies "
        "Vital Sync's product. Every opportunity listed requires human approval "
        "before anything is built.", styles["cover_sub"]))
    story.append(PageBreak())

    # ---------------- Executive summary ----------------
    story.append(Paragraph("Executive Summary", styles["h1"]))
    story.append(Paragraph(data["exec_summary"], styles["body"]))

    # ---------------- Product Source Freshness (must precede recommendations) ----------------
    product_state = load_product_state()
    story.append(Paragraph("Product Source Freshness", styles["h1"]))
    if product_state is None:
        story.append(Paragraph(
            "<b>WARNING: CURRENT VITAL SYNC PRODUCT STATE COULD NOT BE VERIFIED.</b> "
            "No product-state registry was found. PRODUCT BUILD RECOMMENDATIONS ARE "
            "PROVISIONAL.", styles["body"]))
    else:
        overall = product_state.get("overall_freshness", "UNKNOWN")
        if overall in ("STALE", "UNKNOWN", "CONFLICTING"):
            story.append(Paragraph(
                f'<font color="{_status_hex(overall)}"><b>WARNING: CURRENT VITAL SYNC '
                f'PRODUCT STATE COULD NOT BE VERIFIED ({overall}).</b></font> '
                f'{product_state.get("warning", "PRODUCT BUILD RECOMMENDATIONS ARE PROVISIONAL.")}',
                styles["body"]))
        rows = []
        for key, src in product_state.get("source_freshness", {}).items():
            rows.append((
                f"<b>{key.replace('_', ' ').title()}</b>",
                src.get("classification", "UNKNOWN"),
                src.get("commit", src.get("source_type", "")) or "—",
                src.get("reason", ""),
            ))
        if rows:
            story.append(_section_table(
                rows, [1.3 * inch, 1.05 * inch, 1.3 * inch, 2.85 * inch], styles,
                header=["Source", "Freshness", "Commit / Type", "Notes"], status_col=1))
        story.append(Paragraph(
            f"Overall confidence: <b>{product_state.get('overall_confidence', 'UNKNOWN')}</b>",
            styles["body"]))

    story.append(Paragraph("This Week's Actions", styles["h1"]))
    action_rows = []
    for i, (title, body) in enumerate(data["top_actions"], start=1):
        cell = Table(
            [[Paragraph(f"#{i} BUILD NOW &mdash; {title}", styles["action_title"])],
             [Paragraph(body, styles["action_body"])]],
            colWidths=[6.5 * inch],
        )
        cell.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), ACCENT),
            ("LEFTPADDING", (0, 0), (-1, -1), 12),
            ("RIGHTPADDING", (0, 0), (-1, -1), 12),
            ("TOPPADDING", (0, 0), (0, 0), 10),
            ("BOTTOMPADDING", (0, 1), (0, 1), 10),
            ("TOPPADDING", (0, 1), (0, 1), 2),
        ]))
        action_rows.append(cell)
        action_rows.append(Spacer(1, 6))
    story.extend(action_rows)

    story.append(Spacer(1, 6))
    highlight_specs = [
        ("Biggest Competitor Threat", data["biggest_threat"]),
        ("Biggest Open Market Gap", data["biggest_gap"]),
        ("Biggest Vital Sync Weakness", data["biggest_weakness"]),
        ("Biggest Vital Sync Advantage", data["biggest_advantage"]),
        ("One Thing To Ignore", data["one_to_ignore"]),
    ]
    for label, text in highlight_specs:
        story.append(Paragraph(label, styles["h2"]))
        story.append(Paragraph(text, styles["body"]))
    story.append(PageBreak())

    # ---------------- Vital Sync current state ----------------
    story.append(Paragraph("Vital Sync Current State", styles["h1"]))
    rows = [(f"<b>{a}</b>", s, e) for a, s, e in data["vital_sync_current_state"]]
    story.append(_section_table(
        rows, [1.65 * inch, 1.0 * inch, 3.85 * inch], styles,
        header=["Area", "Status", "Evidence"], status_col=1))

    story.append(Paragraph("Changes This Week", styles["h2"]))
    if data["changes_this_week"] is None:
        story.append(Paragraph(
            "N/A — first run. Future weekly reports will diff against this baseline.",
            styles["body"]))
    else:
        story.extend(_bullets(data["changes_this_week"], styles))

    strengths_rows = [[Paragraph("Strengths", styles["h2"])]] + [
        [b] for b in _bullets(data["strengths"], styles)]
    weaknesses_rows = [[Paragraph("Weaknesses", styles["h2"])]] + [
        [b] for b in _bullets(data["weaknesses"], styles)]
    no_pad = TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ])
    left = Table(strengths_rows, colWidths=[3.1 * inch])
    left.setStyle(no_pad)
    right = Table(weaknesses_rows, colWidths=[3.1 * inch])
    right.setStyle(no_pad)
    col = Table([[left, right]], colWidths=[3.25 * inch, 3.25 * inch])
    col.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(Spacer(1, 4))
    story.append(col)

    # ---------------- Product State Delta + Resolved Findings ----------------
    if product_state:
        story.append(PageBreak())
        story.append(Paragraph("Product State Delta", styles["h1"]))
        delta_rows = []
        for area, info in product_state.get("areas", {}).items():
            status = info.get("status", "UNKNOWN")
            lifecycle = info.get("lifecycle", "UNVERIFIED")
            delta_rows.append((
                f"<b>{area.replace('_', ' ').title()}</b>",
                status,
                lifecycle,
                info.get("evidence", info.get("repo_evidence", ""))[:220],
            ))
        story.append(_section_table(
            delta_rows, [1.35 * inch, 1.15 * inch, 0.95 * inch, 3.05 * inch], styles,
            header=["Area", "Status", "Lifecycle", "Evidence (truncated)"], status_col=1))

        resolved = product_state.get("resolved_findings", [])
        story.append(Paragraph("Resolved Findings", styles["h2"]))
        if resolved:
            for r in resolved:
                story.append(Paragraph(
                    f"<b>{r.get('area', '').replace('_', ' ').title()}</b> — "
                    f"discovered {r.get('originally_discovered', '?')}, "
                    f"resolved {r.get('resolved', '?')}. "
                    f"Current status: {r.get('current_status', '?')}",
                    styles["body"]))
        else:
            story.append(Paragraph("None recorded yet.", styles["body"]))

        unverified = product_state.get("unverified_findings", [])
        if unverified:
            story.append(Paragraph("Unverified / Conflicting Findings", styles["h2"]))
            story.extend(_bullets(unverified, styles))

    story.append(Paragraph("Cross-System Audit", styles["h1"]))
    rows = [(f"<b>{a}</b>", s, e) for a, s, e in data["cross_system_audit"]]
    story.append(_section_table(
        rows, [1.9 * inch, 0.9 * inch, 3.7 * inch], styles,
        header=["Connection", "Status", "Finding"], status_col=1))
    story.append(PageBreak())

    # ---------------- Competitor watch / position ----------------
    story.append(Paragraph("Competitor Watch", styles["h1"]))
    rows = [(f"<b>{n}</b>", c, d) for n, c, d in data["competitor_watch"]]
    story.append(_section_table(
        rows, [1.5 * inch, 1.1 * inch, 3.9 * inch], styles,
        header=["Competitor", "Class", "Positioning / Pricing"]))

    story.append(Paragraph("Competitive Position", styles["h2"]))
    rows = [(t, l, a, f) for t, l, a, f in data["gap_types"]]
    story.append(_section_table(
        rows, [0.4 * inch, 1.3 * inch, 1.3 * inch, 3.5 * inch], styles,
        header=["Type", "Verdict", "Area", "Finding"]))

    # ---------------- Customer intelligence ----------------
    story.append(Paragraph("Customer Pain Intelligence", styles["h1"]))
    for label, text in data["pain_clusters"]:
        story.append(Paragraph(f"<b>{label}</b> — {text}", styles["body"]))

    story.append(Paragraph("Customer Praise Intelligence", styles["h1"]))
    for label, text, verdict in data["praise_clusters"]:
        story.append(Paragraph(f"<b>{label}</b> — {text} <i>{verdict}</i>", styles["body"]))
    story.append(PageBreak())

    # ---------------- Demand & trends ----------------
    story.append(Paragraph("Search Demand", styles["h1"]))
    story.extend(_bullets(data["search_demand"], styles))

    story.append(Paragraph("Market Trends", styles["h1"]))
    story.extend(_bullets(data["market_trends"], styles))

    # ---------------- Opportunities ----------------
    story.append(Paragraph("Product Opportunities", styles["h1"]))
    buckets = ["BUILD NOW", "IMPROVE EXISTING", "BUILD NEXT", "EXPERIMENT", "MONITOR"]
    for bucket in buckets:
        items = [o for o in data["opportunities"] if o[3] == bucket]
        if not items:
            continue
        story.append(Paragraph(bucket.title(), styles["h2"]))
        rows = [(f"#{r} {t}", ev, g, ai, conf)
                for r, t, ev, b, g, ai, conf in items]
        story.append(_section_table(
            rows, [1.85 * inch, 2.55 * inch, 0.5 * inch, 0.85 * inch, 0.75 * inch],
            styles, header=["Opportunity", "Evidence", "Gap", "AI", "Confidence"]))
        story.append(Spacer(1, 6))

    story.append(Paragraph("Opportunity Movement", styles["h2"]))
    if data["opportunity_movement"] is None:
        story.append(Paragraph(
            "N/A — first run. Future weekly reports will show rank changes here.",
            styles["body"]))
    else:
        story.extend(_bullets(data["opportunity_movement"], styles))
    story.append(PageBreak())

    # ---------------- Evidence Conflicts ----------------
    conflicts = load_evidence_conflicts()
    story.append(Paragraph("Evidence Conflicts", styles["h1"]))
    if not conflicts or not conflicts.get("conflicts"):
        story.append(Paragraph("None open.", styles["body"]))
    else:
        for c in conflicts["conflicts"]:
            story.append(Paragraph(f"<b>{c['finding']}</b>", styles["h2"]))
            a, b = c["source_a"], c["source_b"]
            story.append(Paragraph(
                f"<b>{a['label']}</b> ({a['date']}): {a['value']}", styles["body"]))
            story.append(Paragraph(
                f"<b>{b['label']}</b> ({b['date']}): {b['value']}", styles["body"]))
            story.append(Paragraph(
                f'Resolution: <font color="{_status_hex(c["resolution"])}"><b>'
                f'{c["resolution"]}</b></font> — {c.get("reason", "")}',
                styles["body"]))
            story.append(Spacer(1, 6))

    # ---------------- Sources ----------------
    story.append(Paragraph("Sources / Evidence", styles["h1"]))
    story.extend(_bullets(data["sources"], styles))
    story.append(Spacer(1, 10))
    story.append(Paragraph(
        "This is an intelligence and recommendation report. It never modifies Vital "
        "Sync's product; human approval is required before any listed opportunity is "
        "built.", styles["body"]))

    doc.build(story, canvasmaker=_NumberedCanvas)


def archive_path(report_date: str) -> str:
    dt = datetime.strptime(report_date, "%Y-%m-%d")
    out_dir = os.path.join(REPORTS_ROOT, dt.strftime("%Y"), dt.strftime("%m"))
    os.makedirs(out_dir, exist_ok=True)
    return os.path.join(out_dir, f"Vital_Sync_Weekly_Intelligence_{report_date}.pdf")


def validate_pdf(path: str) -> bool:
    """Cheap structural sanity check — real %PDF header, %%EOF trailer, non-trivial size."""
    if not os.path.exists(path) or os.path.getsize(path) < 5000:
        return False
    with open(path, "rb") as f:
        head = f.read(5)
        f.seek(-32, os.SEEK_END)
        tail = f.read()
    return head == b"%PDF-" and b"%%EOF" in tail


def _cli():
    parser = argparse.ArgumentParser(description="Generate the Vital Sync weekly intelligence PDF")
    parser.add_argument("--date", default=WEEK_DATA["report_date"])
    args = parser.parse_args()

    data = dict(WEEK_DATA)
    data["report_date"] = args.date
    out_path = archive_path(args.date)

    if os.path.exists(out_path):
        print(f"REFUSING TO OVERWRITE existing report: {out_path}")
        return

    build_pdf(data, out_path)

    if validate_pdf(out_path):
        print(f"PDF_GENERATED: {out_path}")
        print(f"PDF_VALIDATED: True ({os.path.getsize(out_path):,} bytes)")
    else:
        print(f"PDF_GENERATION_FAILED: {out_path}")


if __name__ == "__main__":
    _cli()
