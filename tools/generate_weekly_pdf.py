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
    "report_date": "2026-09-21",
    "run_label": "Brief 09 — GitHub mirror CROSSES the 2+-consecutive-unchanged-runs "
    "threshold and is RECLASSIFIED STALE (first STALE classification since the "
    "09-07 repair) — still unchanged at 0435f9ea, but every finding was "
    "independently re-confirmed by fresh direct source read, not inferred from the "
    "clean diff; all four BUILD NOW findings (Squad authorization, database "
    "integrity, Directive Engine, marketing mismatch) RE-VERIFIED again, now "
    "unresolved for two full weeks; wearables integration MOVES UP to BUILD NOW as "
    "three platform-scale threats converge — WHOOP's funding, Google Health "
    "Premium, and NEW: Apple's Sept 9 Health app Readiness score + AI Insights, "
    "alongside Apple Fitness+ layoffs signaling a pivot toward AI-driven guidance",
    "exec_summary": (
        "Second scheduled Monday-cadence run since the 2026-09-07 repair. The "
        "single most important development this week is procedural, not "
        "product-specific: the GitHub mirror's HEAD commit (0435f9ea) has now been "
        "confirmed unchanged for 2 consecutive weekly checks (Brief 08 on 09-14, "
        "this run on 09-21) — `git log`/`git diff` against both the stored commit "
        "and a fresh `origin/main` fetch both came back empty again. That crosses "
        "this workflow's own gate threshold for reclassifying a frozen commit "
        "STALE, and it is reclassified accordingly for the first time since the "
        "2026-09-07 repair. This is a mechanical reclassification of the SOURCE, "
        "not a retraction of last week's findings: rather than stop at 'no diff,' "
        "the actual source was re-read again this run at the same commit, and every "
        "one of last week's findings holds exactly — Squad list/leaderboard "
        "authorization is still CONFIRMED BROKEN, database-level ownership "
        "integrity is still CONFIRMED BROKEN, the Directive Engine is still "
        "CONFIRMED ABSENT (mission selection re-confirmed as Math.random()-based, "
        "not Alignment-driven, by direct read of missions.ts), training depth is "
        "still CONFIRMED SHALLOW, and the marketing/product mismatch (landing.tsx's "
        "'Coming Soon' badges and undisclosed pricing) is still CONFIRMED PRESENT. "
        "All four BUILD NOW items are therefore unresolved for two full weeks now "
        "with no fix landed. Two additional areas were independently re-verified "
        "for the first time in several weeks rather than carried forward from the "
        "stale export: a full-source grep found zero wearable-integration code "
        "(HealthKit/Health Connect/Garmin/WHOOP/Oura/Fitbit/Strava), and a direct "
        "read of coach.ts confirmed the AI chat coach's context still queries only "
        "missionsTable, not Alignment/Recovery/workout/meal data. vitalsyncify.com "
        "itself remains unreachable from this sandbox for a 7th straight week "
        "(EGRESS_BLOCKED). On the market side, a major new signal emerged: Apple's "
        "September 9, 2026 event revamped the Health app with a 0-10 'Readiness' "
        "score (built from activity/training-load/sleep/vitals — functionally the "
        "same output as Vital Sync's own Alignment/Recovery engine) and "
        "Apple-Intelligence-powered Health Insights, rolling out free to every "
        "iPhone/Apple Watch user later this year — no subscription required, unlike "
        "Google Health Premium's $9.99/mo. A related signal reported this week "
        "(MacRumors/9to5Mac, 2026-09-20): Apple has begun layoffs on the Fitness+ "
        "team's human-coached audio content, with observers reading it as an early "
        "step toward folding Fitness+ into the AI-driven Health app. Together with "
        "WHOOP's continued capital scale and Google Health Premium's established "
        "position, this is now three independent platform-scale signals converging "
        "on exactly the data-supply gap (zero wearable integrations) Vital Sync has "
        "carried since Brief 01 — which is why 'Connect Apple Health as first "
        "wearable' moves up from BUILD NEXT to BUILD NOW this week (see Opportunity "
        "Movement for the full reasoning). Elsewhere, Gentler Streak shipped an "
        "iOS 27 update (9to5Mac, 2026-09-14) adding Siri App Intents and 'a fresh "
        "notification category to help you tune in to your body in the morning' — "
        "a direct extension of last week's fatigue-aware Morning Check-In finding, "
        "further sharpening (without closing) the open fatigue-aware-gamification "
        "market gap. Bitletics remains pre-launch in beta with its Q2/Q3 2026 "
        "window now roughly 9 days from expiring (Q3 ends Sept 30) and no ship date "
        "found. No new or resolved evidence conflicts this run."
    ),
    "top_actions": [
        ("Fix Squad authorization / privacy — RE-VERIFIED again, unfixed for two "
         "full weeks now",
         "RE-CONFIRMED BROKEN by fresh direct source read at the same commit: "
         "GET /squads and GET /squads/leaderboard still accept no authentication "
         "(unused request parameter) and still return every active squad with zero "
         "privacy filtering, even though the squads table has a privacy column. A "
         "repo-wide search for an invite flow this run also came up empty — no "
         "admin/owner role, no invite flow. Still the sharpest concrete trust/"
         "security gap in the product, and now two full weeks old with no fix "
         "landed."),
        ("Enforce database-level ownership — RE-VERIFIED again, unfixed for two "
         "full weeks now",
         "RE-CONFIRMED BROKEN by fresh direct source read: profileTable.clerkId and "
         "workoutsTable.userId are still nullable text columns with no foreign-key "
         "constraints, by explicit design comment ('nullable for pre-scoping rows'). "
         "Route-level scoping remains real, but nothing in the database itself "
         "enforces it — a determined bad actor or a future bug could still write "
         "cross-user data."),
        ("Build the Alignment -> Directive -> Mission connection — RE-VERIFIED "
         "again, unfixed for two full weeks now",
         "RE-CONFIRMED ABSENT by a fresh full-source grep and a direct read of "
         "missions.ts: no Directive Engine, no directive schema, no "
         "Alignment-driven mission selection exists anywhere in the current source "
         "— missions are still chosen by Math.random() against a weighted pool. "
         "Still the clearest gap in Vital Sync's own stated differentiation model "
         "(Training + Nutrition + Recovery -> Alignment -> Directive -> Mission -> "
         "Execution -> Progress -> Feedback) — the first three steps and the last "
         "two exist; the middle connective step does not."),
    ],
    "biggest_threat": (
        "CHANGED THIS WEEK — a new platform-scale entrant joins Google Health "
        "Premium: at its September 9, 2026 event, Apple revamped the Health app "
        "with a free 0-10 'Readiness' score (built from activity, training load, "
        "sleep, and vitals) and Apple-Intelligence-powered Health Insights "
        "(including a 'Health Age' computation), rolling out to every iPhone/Apple "
        "Watch user later this year at no additional subscription cost — a "
        "functionally identical output to Vital Sync's own Alignment/Recovery "
        "engine, distributed for free at OS scale. A related signal reported this "
        "week (MacRumors/9to5Mac, 2026-09-20): Apple has begun layoffs on the "
        "Fitness+ team's human-coached audio content, read by observers as an "
        "early step toward folding Fitness+ into the AI-driven Health app. Google "
        "Health Premium ($9.99/mo, Gemini-powered) is unchanged and remains a real "
        "threat in its own right, but Apple's version needs no subscription and "
        "ships to a vastly larger installed base — it is now the sharper of the "
        "two. WHOOP's $575M Series G (found last run) still underlines how much "
        "capital platform-scale wearable/AI-coaching plays command versus "
        "gamification-first apps like Vital Sync."
    ),
    "biggest_gap": (
        "Unchanged, and sharpened again this week — nobody in the competitive set "
        "ties streak/gamification mechanics to real fatigue data. Gentler Streak "
        "shipped an iOS 27 update this week (9to5Mac, 2026-09-14) adding Siri App "
        "Intents and 'a fresh notification category to help you tune in to your "
        "body in the morning' — a direct extension of last week's fatigue-aware "
        "Morning Check-In finding, closer to the fatigue-aware concept than "
        "anything else tracked, though Gentler Streak still has no XP/streak-"
        "reward gamification layer to fuse it with. On the product side, Vital "
        "Sync's own Directive Engine (re-confirmed absent this run) remains the "
        "prerequisite for doing this well — the gap, the market validation, and "
        "the internal dependency are all independently verified facts, not "
        "assumptions."
    ),
    "biggest_weakness": (
        "Unchanged from Brief 08 in substance, but now two full weeks old with no "
        "fix: Squad authorization is RE-CONFIRMED BROKEN (unauthenticated list/"
        "leaderboard, no privacy enforcement, no invite flow) and database-level "
        "ownership integrity is RE-CONFIRMED BROKEN (nullable, unenforced foreign "
        "keys) — both re-verified by fresh direct source read against the same "
        "commit, not re-asserted from last week's finding. Per-user scoping at the "
        "route level remains genuinely fixed underneath these two open gaps."
    ),
    "biggest_advantage": (
        "Unchanged — the Alignment engine and the real GPT-4o-mini coach chat "
        "remain genuinely well-built, and the VAPID private-key concern remains "
        "resolved (server-side only, no exposure found). The coach chat engine "
        "itself was not independently re-pinged this run; its context-depth gap "
        "was re-verified (see AI Coach row). The gap is still data supply "
        "(wearables) and the missing Directive connective layer, not engineering "
        "quality or pricing."
    ),
    "one_to_ignore": (
        "Same as Brief 08 — chasing deeper RPG mechanics (pets, gear, cosmetic "
        "avatars), and copying RazFit's or Bitletics' formats directly (Bitletics "
        "still hasn't shipped — see Competitor Changes, window now ~9 days from "
        "expiring). Still not worth doing yet: building the fatigue-aware streak "
        "mechanic or any Directive-Engine-adjacent feature before the Directive "
        "Engine itself exists, re-confirmed absent again this run. Also not worth "
        "doing: reacting to Apple's or Google's platform moves by trying to build a "
        "competing OS-level health-insights product — Vital Sync's answer is "
        "connecting to their data (see #5), not competing with their distribution. "
        "The dependency order matters; sequencing work on top of a foundation that "
        "isn't there yet just creates more to redo later."
    ),
    "vital_sync_current_state": [
        ("Multi-User / Data Scoping", "PARTIAL", "RE-VERIFIED this run (third "
         "consecutive direct read) by direct source read at the unchanged commit: "
         "getOrCreateProfile(userId) and equivalents still filter WHERE "
         "clerkId/userId = the authenticated user. Database-level enforcement is "
         "separately BROKEN — see next row."),
        ("Database Integrity", "BROKEN", "RE-VERIFIED this run, still unfixed for "
         "two full weeks: ownership columns (profileTable.clerkId, "
         "workoutsTable.userId) are nullable with no NOT NULL constraint and no "
         "foreign keys, by explicit design comment. Route-level scoping is real; "
         "the database itself still doesn't enforce it."),
        ("Engagement / Gamification", "LIVE", "XP, Levels, Identity Ranks, Discipline "
         "Score, streaks + streak-freeze, 15 badges, 4 Boss Battles, 4 default 30-day "
         "Challenges. Not reverified in detail this run beyond the Squads rows below."),
        ("Squads — Real Activity", "COMPLETE", "RE-VERIFIED this run (third "
         "consecutive direct read): getGhostCompletions and all seeded/"
         "simulated-activity code still confirmed removed. Stats still derive from "
         "real memberships and real mission/workout rows."),
        ("Squads — Authorization / Privacy", "BROKEN", "RE-VERIFIED this run, still "
         "unfixed for two full weeks: GET /squads and GET /squads/leaderboard still "
         "have no auth check and return all squads with no privacy filtering "
         "despite a privacy column existing. A repo-wide search for an invite flow "
         "this run again found none, no owner/admin role logic."),
        ("Nutrition", "PARTIAL", "Meal logging works (name/cals/macros). Protein + "
         "water + a nullable calorie target exist; no carb/fat targets. Not "
         "reverified against the current commit this run — carried from Brief 07."),
        ("Training", "PARTIAL / SHALLOW", "RE-VERIFIED this run (third consecutive "
         "direct read): schema is still name/duration/type/notes only (plus the "
         "nullable userId column) — no sets/reps/weight/progressive-overload "
         "fields, unchanged since Brief 01."),
        ("Recovery", "PARTIAL", "Real multi-factor log feeding a genuine weighted "
         "algorithm — not reverified against the current commit this run, carried "
         "from Brief 02/07's finding since it wasn't re-checked this cycle."),
        ("Cross-System Intelligence (Alignment)", "PARTIAL", "Algorithm confirmed real "
         "since Brief 02 (weighted training/nutrition/recovery composite). Its output "
         "still does NOT feed into mission/directive selection — see Directive "
         "Engine row, re-verified this run."),
        ("Directive Engine", "MISSING", "RE-VERIFIED this run by a fresh full-source "
         "grep AND a direct read of missions.ts: no executable Directive Engine, "
         "directive schema, or Alignment-to-mission connection exists anywhere. "
         "Missions are still chosen by Math.random() against a weighted pool. "
         "\"Directive\" appears only as UI/narrative copy."),
        ("AI — ambient brief", "PROTOTYPE", "Not reverified against the current "
         "commit this run — carried from Brief 02's finding (templated, no model "
         "call)."),
        ("AI — chat coach", "LIVE", "Real GPT-4o-mini confirmed since Brief 02 (chat "
         "engine itself not re-pinged this run). RE-VERIFIED this run by direct "
         "read of coach.ts: both context-building query sites still select only "
         "from missionsTable (title/completed/date) scoped by userId — no query "
         "touches Alignment, Recovery, workout, or meal data."),
        ("Monetization", "LIVE", "Stripe \"Vital Sync Pro\" — not reverified against "
         "the current commit this run, carried from Brief 02/07."),
        ("Integrations (wearables)", "NOT FOUND", "RE-VERIFIED this run by a fresh "
         "full-source, case-insensitive grep for HealthKit/Health Connect/Garmin/"
         "WHOOP/Oura/Fitbit/Apple Health/Strava: zero matches anywhere in the "
         "codebase. Still the top reason Alignment/Recovery have little real data "
         "to score, and now the sharpest data-supply gap given this week's "
         "platform-scale competitive moves (see Biggest Competitor Threat)."),
        ("Mobile App", "LIVE", "Full Expo/React Native app — not reverified against "
         "the current commit this run, carried from Brief 06's structural finding."),
        ("Push Notifications", "LIVE", "The VAPID-key concern remains resolved — "
         "private key confirmed server-side only, no exposure found. Not "
         "independently re-checked this run."),
        ("Auth", "LIVE", "Clerk middleware wired app-wide and RE-VERIFIED this run "
         "still actually used for route-level scoping (see Multi-User row)."),
        ("Marketing / Product Alignment", "MISMATCH", "RE-VERIFIED again this run "
         "at the same 0435f9ea commit, second consecutive week confirmed current: "
         "landing.tsx still shows two 'Coming Soon' badges and 'Pricing will be "
         "announced before launch.' Unresolved for two full weeks now with no fix "
         "landed."),
    ],
    "changes_this_week": [
        "REPOSITORY STATE RECLASSIFIED STALE — the biggest process development this "
        "run: the GitHub mirror's HEAD (0435f9ea) has still not moved — `git log`/"
        "`git diff` against both the stored commit and a fresh `origin/main` fetch "
        "both came back empty again. This is the 2nd consecutive confirmed-"
        "unchanged check since the mirror's 09-07 advance, crossing this workflow's "
        "own 2+-consecutive-runs threshold — the mirror is reclassified STALE, the "
        "first STALE classification since the 09-07 repair, and the PDF's Product "
        "Source Freshness warning banner now applies. This does NOT mean the "
        "findings below are less trustworthy: every one was independently "
        "re-confirmed this run by fresh direct source read, not inferred from the "
        "clean diff. It means the SOURCE itself (an unchanged mirror, no newer "
        "Replit export in 2 weeks) can no longer be treated as demonstrably current "
        "— repository state and product state remain two separate facts, per the "
        "repair.",
        "ALL FOUR BUILD NOW ITEMS RE-VERIFIED AGAIN, STILL OPEN FOR TWO FULL WEEKS: "
        "Squad list/leaderboard authorization, database-level ownership integrity, "
        "the Directive Engine's absence, and the marketing/product mismatch were "
        "each re-confirmed this run by fresh direct source read against the "
        "unchanged commit — not re-asserted from last week's finding. None has "
        "been fixed since Brief 07/08.",
        "TWO AREAS INDEPENDENTLY RE-VERIFIED FOR THE FIRST TIME IN WEEKS (no longer "
        "resting solely on the aging 2026-09-07 export): a full-source grep found "
        "zero wearable-integration code, and a direct read of coach.ts confirmed "
        "the AI chat coach's context still excludes Alignment/Recovery/workout/"
        "meal data. A repo-wide search for an invite flow also re-confirmed "
        "squad_invites is still MISSING.",
        "WEARABLES OPPORTUNITY MOVES UP TO BUILD NOW: three platform-scale signals "
        "now converge on Vital Sync's zero-wearable-integration gap — WHOOP's "
        "$575M Series G (found last run), Google Health Premium's established "
        "$9.99/mo position, and NEW this week, Apple's September 9, 2026 Health app "
        "redesign shipping a free 0-10 Readiness score plus AI-powered Health "
        "Insights to every iPhone/Apple Watch user later this year — no "
        "subscription required. A related signal (MacRumors/9to5Mac, 2026-09-20): "
        "Apple has begun layoffs on Fitness+'s human-coached audio content, read as "
        "an early step toward folding Fitness+ into the AI-driven Health app. See "
        "Opportunity Movement for the full reasoning.",
        "COMPETITOR/MARKET RESEARCH REFRESHED AGAIN: Vora, Cora, FitCraft, and "
        "RazFit re-checked directly this week (Workout Quest/Habitica remain "
        "surface-level watch only). No material pricing change found at any of "
        "them; a May 2026 Cora update (redesigned Habits tab, widgets, Apple Watch "
        "complications) was newly surfaced this run, refining last week's 'last "
        "updated 2026-04-02' note. Gentler Streak shipped an iOS 27 update "
        "(9to5Mac, 2026-09-14) extending its fatigue-aware positioning with Siri "
        "App Intents and a new morning notification category. Bitletics remains "
        "pre-launch beta with its Q2/Q3 2026 window now ~9 days from expiring "
        "(Q3 ends Sept 30) and no ship date found. Background context surfaced this "
        "run on Strava (a confidential Jan 2026 IPO filing, and its cycling-app "
        "acquisition of The Breakaway alongside the previously-noted Runna deal) is "
        "dated earlier in 2026, not new this week, but newly added to this brief's "
        "record.",
        "NO NEW OR RESOLVED EVIDENCE CONFLICTS THIS RUN: the three conflicts closed "
        "in Brief 07 (user_scoping, squad_real_activity RESOLVED; squad_authorization "
        "confirmed as a new finding, not a conflict) stand as they were — nothing "
        "new was claimed this run without independently checkable evidence.",
    ],
    "strengths": [
        "The Alignment engine and the AI chat coach remain genuinely well-engineered "
        "— unchanged assessment; the coach's narrow context scope was independently "
        "re-verified this run (see AI Coach row), not the overall assessment.",
        "Per-user data scoping remains real at the route level — RE-VERIFIED this "
        "run (third consecutive direct read) at the unchanged commit.",
        "Squads' member activity remains genuinely real, not simulated — "
        "RE-VERIFIED this run (third consecutive direct read), not by trusting "
        "last week's finding.",
        "Deep, coherent gamification core (XP/Levels/Identity Ranks/Streaks/Badges/"
        "Boss Battles) — unchanged, more developed than most competitors' equivalents.",
        "A real, structurally complete mobile app already exists — unchanged.",
    ],
    "weaknesses": [
        "Squad authorization is RE-CONFIRMED BROKEN this run — unauthenticated "
        "list/leaderboard routes, no privacy enforcement despite a privacy field "
        "existing, no invite flow found on a fresh repo-wide search. A real trust/"
        "security gap, unresolved for two full weeks now.",
        "Database-level ownership integrity is RE-CONFIRMED BROKEN this run — "
        "nullable columns, no foreign keys, under an application layer that assumes "
        "real scoping.",
        "The Directive Engine — the connective step in Vital Sync's own stated "
        "differentiation model between Alignment and Mission — is RE-CONFIRMED "
        "absent this run.",
        "Training schema remains RE-CONFIRMED shallow this run — unchanged since "
        "Brief 01, only a nullable userId column was ever added.",
        "The marketing/product mismatch (site says 'Coming Soon,' pricing "
        "undisclosed) is RE-CONFIRMED this run against the current commit for a "
        "second consecutive week — still unresolved.",
        "Zero wearable integrations — RE-CONFIRMED this run by a fresh full-source "
        "grep, no longer resting on the aging export alone. Now the sharpest "
        "data-supply gap given this week's platform-scale competitive signals "
        "(Apple Health Readiness score, Google Health Premium, WHOOP).",
    ],
    "cross_system_audit": [
        ("Training <-> Recovery", "LIVE (algorithm)", "Unchanged — Alignment engine "
         "weights both into one score; not reverified against the new commit this "
         "run specifically, but not a disputed claim either."),
        ("Nutrition <-> Recovery", "LIVE (algorithm)", "Unchanged — both are real "
         "pillars in the same weighted Alignment score."),
        ("Sleep <-> Performance", "LIVE (algorithm)", "Unchanged — computeRecoveryScoreV2 "
         "blends multiple recovery inputs into one state."),
        ("Alignment <-> Directive/Mission", "MISSING", "RE-VERIFIED this run by a "
         "fresh grep AND a direct read of missions.ts: Alignment's output still "
         "does not feed mission selection (which uses Math.random()) or any "
         "directive layer — confirmed by direct code read, not carried over "
         "unchecked."),
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
        ("Vora", "Direct", "RE-CHECKED this week: voice-first all-in-one, 500+ "
         "wearable integrations. Pricing discrepancy PERSISTS across the vendor's "
         "own pages — $12.99/mo or $89.99/yr on the official app-store listing, "
         "but as low as $7.50/mo (billed annually) on a separate Vora pricing page "
         "— still UNVERIFIED-EXACT rather than a single confirmed number, unchanged "
         "from last week. Core mechanism unchanged."),
        ("Cora", "Direct", "RE-CHECKED this week: still freemium with in-app "
         "purchases, still no disclosed tier pricing found in search results. NEW "
         "DETAIL THIS WEEK: a May 2026 update added a redesigned Habits tab "
         "(routines/journals), widgets, and Apple Watch complications for sleep/"
         "Body Charge/strain — this refines (not contradicts) last week's 'last "
         "updated 2026-04-02' note, which undercounted a subsequent release. "
         "\"Body Charge\" HRV/sleep-driven scheduling mechanism itself unchanged."),
        ("FitCraft", "Direct", "RE-CHECKED this week: pricing and core mechanism "
         "(streaks, collectible cards, AI coach, gamified rewards) unchanged. "
         "Marketing copy continues to emphasize cosmetic/UX polish (new visual "
         "effects, calendar/rewards gamification, workout variety) — not a new "
         "capability. Still no nutrition/recovery features found."),
        ("Workout Quest", "Direct", "Not re-checked this week (surface-level watch "
         "only) — carried unchanged from Brief 07: RPG workout tracker, free-to-"
         "start, guilds/raid-boss workouts/loot chests/battle passes. Still no "
         "nutrition tracking found as of last check."),
        ("Habitica", "Specialist", "Not re-checked this week (surface-level watch "
         "only) — carried unchanged from Brief 07: pure RPG habit layer, cosmetic-"
         "only subscription, no fitness-specific programming."),
        ("Trainera / Bevel / NATE", "Direct (surface-level)", "Not re-checked this "
         "week (surface-level watch only) — carried unchanged from Brief 07."),
        ("Whoop / Welling / Strava / Freeletics", "Specialist / Indirect", "RE-"
         "CHECKED partially this week: WHOOP's $575M Series G (March 2026, found "
         "last run) stands, no new funding activity found. NEW CONTEXT on Strava "
         "found this run, though dated earlier in 2026 rather than new this week: "
         "Strava confidentially filed for an IPO on 2026-01-08 (per The Information, "
         "as reported by Forge/QuantLogix), and its oft-cited $2.2B valuation "
         "traces to a May 2025 Series F extension, not a new 2026 round; separately, "
         "Strava acquired cycling-training app The Breakaway in addition to the "
         "previously-noted Runna deal. None of this changes Strava's product "
         "surface as tracked here — background/scale context, not a feature "
         "change."),
        ("Bitletics", "Emerging / Beta", "RE-CHECKED this week: still pre-launch "
         "per official channels — no credible source found confirming a public "
         "iOS/Android launch. Still described as launching free, no subscription "
         "required, 30+ activity types, Apple Watch/heart-rate verified. Its Q2/Q3 "
         "2026 launch window is now roughly 9 days from expiring (Q3 2026 ends "
         "Sept 30) with no ship date found — MONITOR, sharpening toward 'window "
         "missed.' Next run should explicitly check whether it shipped or the "
         "window lapsed."),
        ("Google Health Premium (Gemini Health Coach, formerly Fitbit Premium)",
         "Indirect / Platform-scale",
         "RE-CHECKED this week: confirmed unchanged — still $9.99/mo or $99/yr, "
         "coach (launched May 19 2026) still described as launching first for "
         "Fitbit/Pixel Watch users with other devices \"forthcoming.\" No new "
         "expansion found this week. Reads HRV/sleep/activity-load trends and "
         "generates adaptive, continuously-updated recovery-and-training "
         "recommendations — the same category of output as Vital Sync's Alignment "
         "engine, at hardware-platform distribution scale. Now joined by Apple "
         "Health as a platform-scale threat in the same category (see new row "
         "below) — Google's version requires a paid subscription, Apple's does not."),
        ("Apple Health (Readiness Score + AI Health Insights)", "Indirect / "
         "Platform-scale", "NEW ROW THIS WEEK: at its September 9, 2026 event, "
         "Apple revamped the Health app for iOS 27 with a free 0-10 'Readiness' "
         "score (combining activity, workout effort, Training Load, Vitals-app "
         "signals, and sleep history — developed with the Apple Heart and Movement "
         "Study and exercise scientists) and an Apple-Intelligence-powered Insights "
         "tab (heart, sleep, readiness, fitness, vitals, cycle tracking, plus a "
         "computed 'Health Age'), rolling out later this year starting in U.S. "
         "English. No subscription required — a materially bigger distribution "
         "threat than Google Health Premium's $9.99/mo tier for the same category "
         "of output Vital Sync's Alignment/Recovery engine produces. A related "
         "signal reported this week (MacRumors/9to5Mac, 2026-09-20): Apple has laid "
         "off part of the Fitness+ team's human-coached audio-content group (Time "
         "to Walk/Run), read by observers as an early step toward folding Fitness+ "
         "into the AI-driven Health app (more likely 2027 than sooner, per "
         "reporting). Sources: Apple Newsroom, TechCrunch, 9to5Mac, Beebom, "
         "MacRumors."),
        ("RazFit", "Emerging / Live", "RE-CHECKED this week: still built around "
         "1-10 minute equipment-free bodyweight sessions with a badge reward "
         "system, pitched as \"consistency over intensity.\" Still no confirmed "
         "ongoing subscription price beyond a 3-day free trial (not found in "
         "search results again this week). No nutrition or recovery tracking "
         "found. Small/unproven scale — MONITOR, low confidence, unchanged."),
        ("Gentler Streak", "Specialist / Indirect", "CHANGED THIS WEEK: shipped an "
         "iOS 27 update (9to5Mac, 2026-09-14, app version 5.13) adding Siri App "
         "Intents support (ask Siri for health/fitness info without opening the "
         "app) and On-Screen Awareness, plus 'a fresh notification category to "
         "help you tune in to your body in the morning' and new workout types — a "
         "direct extension of last week's fatigue-aware 'Morning Check-In "
         "Notifications' finding. Still $8.99/mo or $39.99/yr, still no XP/streak-"
         "reward gamification layer (its whole positioning is the opposite — "
         "'gentler' than streak-anxiety apps), so it doesn't compete with Vital "
         "Sync's core loop directly, but it remains the closest real-world "
         "validation found for tying recovery guidance to daily behavior — "
         "directly relevant to the fatigue-aware gamification opportunity this "
         "brief tracks (see Product Opportunities)."),
    ],
    "pain_clusters": [
        ("Streak anxiety / burnout", "Missing a streak is reported as demotivating; "
         "some quit once the streak itself, not real progress, became the goal. "
         "Directly relevant — Vital Sync's core loop is streak-built. Not "
         "re-checked this week — carried forward from Brief 08."),
        ("Gamification fatigue in experienced users", "Badges/streaks/leaderboards "
         "without real fitness outcomes are \"consistently mocked\" by "
         "serious-lifter communities as shallow when done badly; notification "
         "overload from achievement systems specifically called out as annoying. "
         "Not re-checked this week — carried forward from Brief 08."),
        ("Loggers pretending to be coaches", "\"Most workout apps in 2026 are loggers, "
         "not coaches\"; apps faking adaptivity with heuristics instead of real "
         "wearable data draw criticism once noticed. Not re-checked this week — "
         "now two consecutive weeks without a refresh."),
        ("Subscription fatigue", "Average user carries 4+ health subscriptions; "
         "previously-free features moving behind paywalls is a recurring complaint "
         "— MyFitnessPal's 2022 paywall change is still cited as the cautionary "
         "example. Not re-checked this week — carried forward from Brief 08."),
        ("Health-data privacy sensitivity", "Fitness-app audiences are more "
         "privacy-conscious than average; vague data-sharing policies, or a data "
         "breach, carry lasting negative sentiment. Not re-checked this week — "
         "carried forward from Brief 08."),
        ("Weak first-week activation", "Users who don't complete at least 3 "
         "workouts in their first week churn at 4-5x the rate of those who do "
         "(2026 fitness-app retention benchmarking, found Brief 08). Relevant to "
         "Vital Sync's onboarding-weighted mission selection — first-week "
         "engagement design matters disproportionately, independent of the "
         "Directive Engine question. Not re-measured this week."),
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
        "— at least 7 apps built specifically to answer this beyond the 5 deep-dived. "
        "Not re-measured this week.",
        "Explicit switching guides exist for MyFitnessPal / Whoop / Strava "
        "consolidation — evidence people actively seek an all-in-one replacement. "
        "Not re-measured this week.",
        "Recurring framing across sources: apps are \"loggers, not coaches\" — demand "
        "for real adaptive coaching outpaces what's shipped industry-wide. Not "
        "re-checked this week — carried forward from Brief 08.",
        "First-week activation is a named, measured lever — apps that get a user "
        "through 3 workouts in week one see 4-5x better retention than those that "
        "don't, per 2026 fitness-app benchmarking research (found Brief 08). Not "
        "re-measured this week.",
        "NEW THIS WEEK: Apple's and Google's platform-level moves into free/"
        "low-cost 'readiness' and AI health coaching (see Competitor Watch) are "
        "themselves a search-demand signal — the category they're answering "
        "(wearable data -> daily actionable guidance) is now validated at OS scale, "
        "not just by boutique apps.",
    ],
    "market_trends": [
        "Wearables are the retention lever — health monitoring has overtaken fitness "
        "tracking as the primary wearable use case; app-side integration is now table "
        "stakes for retention. Reinforced this week: 2026 industry commentary "
        "(webpronews.com, t3.com, feed.fm) describes a broad shift from passive "
        "tracking to active AI coaching, with wearables increasingly predicting "
        "fatigue/injury/sleep-debt trends rather than just recording history.",
        "NEW THIS WEEK — Apple enters the platform-scale 'AI health coaching' race "
        "for free: the Sept 9, 2026 Health app redesign (0-10 Readiness score + "
        "Apple-Intelligence Insights, rolling out later this year) plus reported "
        "Fitness+ layoffs (Bloomberg via MacRumors/9to5Mac, 2026-09-20) together "
        "read as a strategic pivot from human-coached content toward AI-driven, "
        "OS-level health guidance — the same pivot Google made with Health Premium, "
        "but Apple's version needs no subscription at all. This intensifies the "
        "competitive case for Vital Sync to connect to wearable data rather than "
        "compete with platform-level distribution (see Product Opportunities #5).",
        "Fitness app churn is brutal across every dataset checked (not re-checked "
        "this week — carried forward from Brief 08), though the exact numbers vary "
        "by source and methodology — a Sensor Tower Q4 2025 report shows "
        "monthly churn rising from 8.2% (2023) to 11.7% (2025) with only 3% Day-30 "
        "retention; separately, lifecyclearchitect.com/retentioncheck.com's 2026 "
        "benchmarks put median monthly churn at 10-13% (top-quartile apps 4-6%, ~9.2% "
        "average) with 5% median Day-30 retention (8-12% for top performers). Lost "
        "motivation is cited in 38% of cancellations; failed payments alone drive "
        "30-50% of total churn, and a pronounced January sign-up surge is followed "
        "by 40-60% cancellations by February — a seasonal pattern worth noting for "
        "any future launch-timing decision.",
        "Subscription fatigue is now a named, measured problem — fitness apps carry a "
        "31% cancellation rate, 2nd highest of any app category after video streaming, "
        "against 41% of consumers reporting active subscription fatigue overall "
        "(2026 industry analysis, carried from Brief 08); the average user now "
        "carries 4+ health subscriptions. Free alternatives account for 25% of "
        "cancellations, and cost consolidation plus data-privacy concerns are the "
        "two most-cited reasons — directly relevant given Apple's free (no "
        "subscription) entry into the same 'AI readiness coaching' category this "
        "week.",
        "Gamification's evidence base is real but bounded — small-to-medium, "
        "statistically significant effect across multiple RCT meta-analyses; long-term "
        "(multi-year) durability still under-studied. Not re-checked this week.",
        "Computer-vision form-check and conversational coaching are named 2026 "
        "differentiators industry-wide — neither observed in Vital Sync's surface. "
        "Not re-checked this week.",
        "Consolidation continues — following the Strava/Runna, Strava/The Breakaway "
        "(both surfaced this run, dated earlier in 2026), and Garmin/TrainingPeaks "
        "moves, MyFitnessPal's acquisition of nutrition-AI app Cal AI (found Brief "
        "08, a Forbes '30 Under 30'-built app reported at $40M in sales) remains "
        "the most relevant consolidation to Vital Sync's own nutrition module. "
        "Startup funding in fitness/wellness topped $3.6B in H1 2026 (on pace to run "
        "roughly a third higher than 2025), concentrated in fewer, larger AI-enabled "
        "rounds. Separately, Strava confidentially filed for an IPO on 2026-01-08 "
        "(The Information, found this run) — not new this week, but newly recorded "
        "here as further evidence of platform-scale capital concentrating around "
        "wearable-data fitness plays. Raises the urgency of Vital Sync "
        "differentiating on cross-system Alignment intelligence before boutique "
        "positioning gets squeezed by bigger, AI-coaching-plus-hardware players.",
        "Activation, not just retention, is a separately measured lever — users who "
        "don't complete 3 workouts in their first week churn 4-5x faster than those "
        "who do (found Brief 08, not re-measured this week). The global fitness-app "
        "market is estimated at $13.9B in 2026 (context figure, not independently "
        "cross-verified against a second source).",
    ],
    "gap_types": [
        ("-", "Security/trust blocker, unresolved a week later", "Squad authorization "
         "/ privacy", "RE-CONFIRMED BROKEN this run: list/leaderboard routes still "
         "take no auth, no privacy filtering exists despite the field being present. "
         "Still the sharpest concrete Squad risk, now aging without a fix."),
        ("-", "Foundational risk, unresolved a week later", "Database ownership "
         "integrity", "RE-CONFIRMED BROKEN this run: ownership columns are still "
         "nullable with no foreign-key enforcement, underneath an application layer "
         "that assumes real per-user scoping."),
        ("-", "RESOLVED (was foundational blocker)", "Multi-user data scoping",
         "RE-CONFIRMED RESOLVED this run at the route level via fresh direct source "
         "read — was the top blocker through Brief 06."),
        ("A", "Vital Sync behind", "Recovery/Alignment DATA SUPPLY (not logic)", "The "
         "scoring algorithms are real and competitive-grade; Cora/Vora/Bevel/NATE win "
         "only because they have wearable data feeding equivalent logic. SHARPENED "
         "THIS WEEK: Google's Health Premium Gemini Coach shows the same play at "
         "platform scale, and Apple's Sept 9, 2026 Health app Readiness score now "
         "ships the same output for free to every iPhone/Apple Watch user. Vital "
         "Sync's engine still has zero wearable connections (re-confirmed this run "
         "by a fresh full-source grep)."),
        ("A", "Vital Sync behind", "Directive Engine", "RE-CONFIRMED ABSENT this run: "
         "no executable Directive Engine or Alignment-to-mission connection exists. "
         "Competitors don't have this either, but it's Vital Sync's own stated "
         "differentiation model, so the gap is self-inflicted, not just competitive."),
        ("B", "Parity", "Core gamification (XP, streaks, badges)", "Table stakes in "
         "this niche — FitCraft, Workout Quest, Habitica match or exceed on raw "
         "mechanics depth. (RE-CHECKED this week for FitCraft: unchanged; Workout "
         "Quest/Habitica not re-checked.)"),
        ("C", "Vital Sync ahead (once real)", "Alignment engine + AI chat coach + real "
         "Squad activity", "The underlying engineering is genuinely competitive-grade, "
         "and Squads' activity remains confirmed real, not simulated. Gap is data "
         "supply, the missing Directive layer, and Squad authorization — not "
         "algorithm quality."),
        ("D", "Open market gap, newly sharpened", "Fatigue-aware gamification",
         "Nobody in the tracked competitive set ties streak/reward mechanics to real "
         "recovery data. NEW THIS WEEK: Gentler Streak's 'Morning Check-In' "
         "notifications are the closest market validation found yet (fatigue-aware "
         "guidance without a gamification layer to fuse it to). Still confirmed to "
         "depend on the Directive Engine existing first — don't build this before "
         "that."),
    ],
    "opportunities": [
        # (rank, title, evidence, bucket, gap, ai, confidence)
        (1, "Fix Squad authorization / privacy", "RE-CONFIRMED BROKEN this run: "
         "GET /squads and GET /squads/leaderboard have no auth check and no privacy "
         "filtering, and a fresh repo-wide search found no invite flow either. A "
         "real access-control gap, not cosmetic, unresolved for two full weeks now.",
         "BUILD NOW", "-", "No AI Needed", "HIGH"),
        (2, "Enforce database-level ownership", "RE-CONFIRMED BROKEN this run: "
         "nullable ownership columns, no foreign keys, underneath a now-real "
         "application-level scoping layer, unresolved for two full weeks now.",
         "BUILD NOW", "-", "No AI Needed", "HIGH"),
        (3, "Build the Alignment -> Directive -> Mission connection", "RE-CONFIRMED "
         "ABSENT this run by a fresh grep AND a direct read of missions.ts: "
         "missions are chosen by Math.random() against a weighted pool, not by "
         "Alignment output. The connective step in Vital Sync's own "
         "differentiation model still doesn't exist.",
         "BUILD NOW", "A", "AI Assisted", "HIGH"),
        (4, "Fix the marketing/product mismatch", "RE-VERIFIED again this run at "
         "the same 0435f9ea commit — landing.tsx still shows two 'Coming Soon' "
         "badges and 'Pricing will be announced before launch.' Confirmed current "
         "for a second consecutive week, unresolved for two full weeks with no fix "
         "landed.",
         "BUILD NOW", "Trust", "No AI Needed", "HIGH"),
        (5, "Connect Apple Health as first wearable", "MOVED UP TO BUILD NOW this "
         "week: three platform-scale signals now converge on this exact gap — "
         "WHOOP's $575M Series G (Brief 08), Google Health Premium's established "
         "$9.99/mo position, and NEW this week, Apple's Sept 9, 2026 Health app "
         "redesign shipping a FREE 0-10 Readiness score plus AI Health Insights to "
         "every iPhone/Apple Watch user later this year, alongside reported "
         "Fitness+ layoffs signaling a strategic pivot toward AI-driven guidance. "
         "Broadest reach, lowest build effort of any opportunity here (HealthKit "
         "read integration feeds the already-working Alignment/Recovery "
         "algorithms with real data); nothing blocks it except build time. "
         "Wearables' absence was independently re-confirmed this run by a fresh "
         "full-source grep, not carried from the aging export.",
         "BUILD NOW", "A", "No AI Needed", "HIGH"),
        (6, "Surface the real AI chat coach more prominently, and widen its context",
         "/coach/message is live GPT-4o-mini — RE-VERIFIED this run by direct read "
         "of coach.ts: its context still excludes Alignment/Recovery/workout/"
         "nutrition data, querying only missionsTable. Two separate improvements: "
         "visibility, and context depth.",
         "BUILD NEXT", "C", "AI Core", "MEDIUM"),
        (7, "Real training depth (sets/reps/weight/overload)", "RE-CONFIRMED "
         "unchanged this run (third consecutive direct read): workouts table "
         "still has no sets/reps/weight fields at all.",
         "BUILD NEXT", "A", "No AI Needed", "HIGH"),
        (8, "Fatigue-aware streak mechanic", "Streak downgrades gracefully instead of "
         "breaking, when real recovery data is low. Still confirmed to depend on "
         "the Directive Engine (#3) and wearables (#5) landing first — do not build "
         "before those. Market validation sharpened again this week: Gentler "
         "Streak shipped an iOS 27 update adding Siri App Intents and a new "
         "morning-focused notification category, extending its fatigue-aware "
         "positioning — the closest real-world precedent found yet, though this "
         "doesn't change the internal dependency order.", "EXPERIMENT", "D",
         "AI Assisted", "MEDIUM"),
        (9, "Full nutrition goals (carbs/fat)", "Protein/water/calorie targets exist; "
         "carbs/fat still missing. Not reverified this run.",
         "IMPROVE EXISTING", "A", "AI Assisted", "MEDIUM"),
        (10, "Voice / natural-language logging", "Vora and Cora both lead with this; "
         "large build effort, competitors have a head start. Not reverified this run.",
         "MONITOR", "A", "AI Core", "MEDIUM"),
        (11, "Track Bitletics' real-reward redemption model", "Converts activity into "
         "redeemable in-game loot/raffle tickets rather than only in-app XP/badges — "
         "a genuinely different reward mechanic than any of the 5 deep-dived "
         "competitors. RE-CHECKED this week: still pre-launch beta, free-at-launch, "
         "no subscription required at launch; its Q2/Q3 2026 window is now roughly "
         "9 days from expiring (Q3 2026 ends Sept 30) with no ship date found. Too "
         "early to act on — next run should explicitly check whether it shipped or "
         "the window lapsed.",
         "MONITOR", "D", "No AI Needed", "LOW"),
        (12, "Monitor Google Health Premium's Gemini Coach as a platform-scale threat, "
         "not a build target", "Formerly Fitbit Premium — RE-CHECKED this week: "
         "confirmed unchanged, no new expansion found. Google ships the same "
         "'wearable data -> adaptive recovery/training guidance' output Vital Sync's "
         "Alignment engine produces, at a growing distribution scale. Now joined by "
         "the sharper Apple Health threat (see #15) — sharpens the case for #5 "
         "(now BUILD NOW) and for leaning on cross-system Alignment "
         "(training+nutrition+recovery together) as the differentiator neither "
         "platform offers.", "MONITOR", "A", "No AI Needed", "MEDIUM"),
        (13, "Track RazFit as a low-friction, short-session entrant", "RE-CHECKED "
         "this week: still built around 1-10 minute equipment-free bodyweight "
         "sessions and a badge reward system, pitched as \"consistency over "
         "intensity.\" Ongoing subscription price still UNKNOWN; scale/traction "
         "still unconfirmed. No change from last week — still MONITOR only.",
         "MONITOR", "D", "No AI Needed", "LOW"),
        (14, "Track Gentler Streak's fatigue-aware check-in mechanic", "CHANGED "
         "THIS WEEK: shipped an iOS 27 update (Siri App Intents, a new "
         "morning-focused notification category) extending last week's 'Morning "
         "Check-In Notifications' finding. $8.99/mo or $39.99/yr, no gamification "
         "layer at all — not a direct competitor to Vital Sync's core loop, but "
         "the clearest real-world precedent yet for tying daily guidance to real "
         "recovery signals. Relevant to #8 as market validation, not as a feature "
         "to copy directly (Gentler Streak's whole brand is the anti-gamification, "
         "anti-streak-anxiety positioning).", "MONITOR", "D", "No AI Needed",
         "MEDIUM"),
        (15, "Monitor Apple Health's Readiness Score + AI Insights as a "
         "platform-scale threat, not a build target", "NEW THIS WEEK: Apple's "
         "Sept 9, 2026 Health app redesign ships a free 0-10 Readiness score "
         "(activity/training-load/sleep/vitals) and Apple-Intelligence Health "
         "Insights to every iPhone/Apple Watch user later this year — the same "
         "category of output as Vital Sync's Alignment/Recovery engine, at "
         "zero subscription cost and platform-OS distribution scale, reinforced "
         "by reported Fitness+ layoffs signaling Apple's pivot toward AI-driven "
         "guidance. Not something Vital Sync can out-build directly; this is the "
         "primary reason #5 (connect Apple Health) moved to BUILD NOW this week — "
         "the correct response is integrating with Apple's data, not competing "
         "with Apple's distribution.", "MONITOR", "A", "No AI Needed", "MEDIUM"),
    ],
    "opportunity_movement": [
        "PROCESS NOTE, applies to all items below: the GitHub mirror crossed this "
        "workflow's 2+-consecutive-unchanged-runs threshold this run and is now "
        "reclassified STALE (see Product Source Freshness). Every product-side "
        "finding below was nonetheless independently re-confirmed by fresh direct "
        "source read this run, not inferred from the clean diff — the bucket calls "
        "below rest on that direct evidence, not on the source's freshness "
        "classification.",
        "#1, #2, #3 (BUILD NOW) — UNCHANGED IN RANK, RE-VERIFIED again this run "
        "(third consecutive direct read for #1-#2's underlying code, and a fresh "
        "missions.ts read added for #3): all three findings hold exactly as "
        "before. All three are now unresolved for TWO full weeks with no fix "
        "landed; that aging is itself worth a human's attention even though the "
        "score is unchanged.",
        "#4 (Fix the marketing/product mismatch) — UNCHANGED IN RANK at BUILD "
        "NOW/HIGH, RE-VERIFIED again this run at the same commit for a second "
        "consecutive week. No longer a 'newly re-confirmed' finding as it was last "
        "week — it is now a persistent, two-week-old unfixed item.",
        "#5 (Connect Apple Health as first wearable) — MOVED UP: BUILD NEXT/HIGH "
        "-> BUILD NOW/HIGH. This is the most significant bucket change this run. "
        "Rationale: three independent platform-scale signals now converge on "
        "exactly this gap — WHOOP's $575M Series G (Brief 08), Google Health "
        "Premium's established $9.99/mo position (unchanged, re-checked this run), "
        "and NEW this week, Apple's Sept 9, 2026 Health app redesign shipping a "
        "FREE Readiness score + AI Insights to every iPhone/Apple Watch user, "
        "reinforced by reported Fitness+ layoffs suggesting Apple is doubling down "
        "on AI-driven guidance over human-coached content. Nothing about Vital "
        "Sync's own readiness to build this changed (it was already assessed as "
        "lowest-effort, broadest-reach); what changed is the cost of NOT doing it "
        "— a free OS-level substitute for exactly Vital Sync's Alignment/Recovery "
        "value proposition is now shipping to Apple's entire installed base. "
        "Wearables' continued absence was independently re-confirmed this run by "
        "a fresh full-source grep, not carried from the aging 2026-09-07 export.",
        "#6 (Widen AI chat coach context) — UNCHANGED bucket (BUILD NEXT), but "
        "RE-VERIFIED this run via direct read of coach.ts rather than carried "
        "forward from Brief 07's export-based finding — confirmed the context "
        "still queries only missionsTable.",
        "#7 (Real training depth) — UNCHANGED bucket, RE-VERIFIED this run (third "
        "consecutive direct schema read) — workouts table confirmed still four "
        "fields, no sets/reps/weight.",
        "#8 (Fatigue-aware streak mechanic, EXPERIMENT) — UNCHANGED bucket, "
        "evidence sharpened again: Gentler Streak shipped an iOS 27 update this "
        "week extending its fatigue-aware Morning Check-In mechanic with Siri App "
        "Intents and a new morning notification category. Still gated on the "
        "Directive Engine (#3) and wearables (#5) landing first — the new evidence "
        "strengthens the market case, not the internal readiness, so the bucket "
        "doesn't move.",
        "#11 (Track Bitletics, MONITOR) — NOT RE-RANKED, still LOW confidence. "
        "RE-CHECKED this week: still pre-launch, still free-at-launch/no-"
        "subscription-required as previously described, and its Q2/Q3 2026 window "
        "is now roughly 9 days from expiring (Q3 ends Sept 30) with no ship date "
        "found. Next run should explicitly check whether it shipped or the window "
        "lapsed.",
        "#12 (Google Health Premium, MONITOR) — NOT RE-RANKED; RE-CHECKED this "
        "week, confirmed unchanged, no new expansion found. Stays MONITOR/MEDIUM, "
        "now joined by the sharper Apple Health threat (#15) — together they "
        "sharpen the case for #5, not a build target themselves.",
        "#13 (Track RazFit, MONITOR) — NOT RE-RANKED. RE-CHECKED this week: no "
        "change found, pricing still UNKNOWN beyond the 3-day trial.",
        "#14 (Track Gentler Streak, MONITOR) — NOT RE-RANKED, evidence CHANGED "
        "THIS WEEK: shipped an iOS 27 update (Siri App Intents, new morning "
        "notification category) extending its fatigue-aware positioning found "
        "last week. Confidence stays MEDIUM.",
        "#15 (Monitor Apple Health's Readiness Score, MONITOR) — NEW THIS WEEK. "
        "Added at MEDIUM confidence following Apple's Sept 9, 2026 Health app "
        "announcement, corroborated across Apple Newsroom, TechCrunch, 9to5Mac, "
        "Beebom, and MacRumors. Tracked as a platform-scale threat (same treatment "
        "as #12/Google Health Premium), not a build target — its real effect on "
        "this backlog is pulling #5 up to BUILD NOW.",
        "#9, #10 (nutrition goals, voice logging) — UNCHANGED, not reverified this "
        "run.",
        "NO ITEMS RESOLVED OR REMOVED THIS RUN. One item (#5) moved bucket — the "
        "backlog's shape is otherwise stable; what changed is which items are "
        "freshly re-verified (#1-#4, #5's wearables-absence check, #6, #7) versus "
        "carried forward unchecked (#9, #10), and that distinction is what this "
        "brief's Product State Delta and this list are for.",
    ],
    "sources": [
        "github.com/faristjohar04-sketch/Vital-Sync — RE-CHECKED this run via "
        "`git log`/`git diff` against both the locally stored commit "
        "(0435f9ea79a871cd1578e2dc22e8e3055bebc50e) and a fresh `origin/main` "
        "fetch — both empty, commit confirmed unchanged since Brief 08 "
        "(2026-09-14) and since the 2026-09-07 advance. This is the 2nd "
        "confirmed-unchanged check since that advance, CROSSING the 2+-"
        "consecutive-runs threshold — the mirror is reclassified STALE this run "
        "(first STALE classification since the 09-07 repair).",
        "github.com/faristjohar04-sketch/Vital-Sync @ 0435f9ea — direct source "
        "RE-READS performed this run (same commit, fresh read, not assumed "
        "unchanged from Brief 08): artifacts/api-server/src/routes/profile.ts (user "
        "scoping), artifacts/api-server/src/routes/squads.ts (both route handlers "
        "+ getRealSquadStats — real activity + authorization), "
        "artifacts/api-server/src/routes/missions.ts (mission-selection "
        "randomness, directive/mission connection), "
        "artifacts/api-server/src/routes/coach.ts (chat context query scope), "
        "lib/db/src/schema/workouts.ts and profile.ts (training depth + nullable "
        "ownership columns), a full-source grep for \"directive\", a full-source "
        "grep for wearable-integration keywords (HealthKit/Health Connect/Garmin/"
        "WHOOP/Oura/Fitbit/Apple Health/Strava — zero matches), a repo-wide search "
        "for \"invite\" (zero matches beyond narrative UI copy), and "
        "artifacts/vital-sync/src/pages/landing.tsx (marketing/product mismatch)",
        "vital_sync_current_product_state.json — a structured audit export "
        "provided by the user on 2026-09-07/08, cross-checked against the commit "
        "above in Brief 07's run. Still no newer export has been provided (now 2 "
        "weeks old); areas resting solely on it are marked UNCHANGED — NOT "
        "REVERIFIED in this brief's Current State table, not re-asserted as "
        "freshly confirmed.",
        "https://vitalsyncify.com — attempted directly this run (direct HTTPS "
        "fetch): EGRESS_BLOCKED (CONNECT tunnel rejected, HTTP 403 from the egress "
        "proxy), the 7th consecutive week this has failed from this sandbox. "
        "Logged as SOURCE_UNAVAILABLE for the marketing-mismatch check, not "
        "treated as evidence of 'no marketing changes.'",
        "WebSearch (this run, competitor/market refresh): official/store pages "
        "and comparison content for Vora, Cora, FitCraft, RazFit; Bitletics' own "
        "blog and app-store listings; Apple Newsroom, TechCrunch, 9to5Mac, "
        "Beebom, MacRumors, and gadgetbond.com coverage of the Sept 9, 2026 Apple "
        "Health app redesign (Readiness score, AI Insights) and the Sept 20, 2026 "
        "Fitness+ layoffs reporting; 9to5Mac coverage of Gentler Streak's iOS 27 "
        "update; Crunchbase News, Dealroom, Forge, and QuantLogix coverage of "
        "Strava's funding/valuation/IPO-filing history; Athletech News "
        "(MyFitnessPal/Cal AI acquisition, carried from Brief 08); "
        "webpronews.com/t3.com/feed.fm 2026 wearable-AI-coaching trend pieces — "
        "direct WebFetch to competitor domains remains typically EGRESS_BLOCKED "
        "in this sandbox, so WebSearch snippets were used throughout, as in prior "
        "briefs. Customer pain/praise/search-demand items not independently "
        "re-searched this run are explicitly marked 'not re-checked this week' "
        "rather than re-asserted as freshly confirmed.",
        "Workout Quest, Habitica, Trainera/Bevel/NATE — surface-level watch only, "
        "NOT re-checked this run; carried forward unchanged from Brief 07/08.",
        "JMIR mHealth 2022 meta-analysis; 36-RCT gamification meta-analysis "
        "(10,079 participants); Oct 2025 British Journal of Health Psychology "
        "(app-set unreachable goals drive churn) — carried as background, not "
        "re-run this week",
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
