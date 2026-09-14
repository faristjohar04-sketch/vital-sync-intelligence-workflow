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
    "report_date": "2026-09-14",
    "run_label": "Brief 08 — first scheduled weekly run since the repair: GitHub mirror CONFIRMED UNCHANGED at 0435f9ea (1st unchanged check since the 09-07 advance, not yet STALE); all three top BUILD NOW findings (Squad authorization, database integrity, Directive Engine) RE-VERIFIED by fresh direct source read, still unfixed a full week later; marketing/product mismatch RE-VERIFIED against the current commit and promoted back to BUILD NOW; competitor/market research refreshed for the first time in two cycles",
    "exec_summary": (
        "First scheduled Monday-cadence run since the 2026-09-07 source-of-truth "
        "repair and the 2026-09-08 manual validation of it. Repository state and "
        "product state are reported as two separate facts, per that repair: the "
        "GitHub mirror's HEAD commit (0435f9ea) has not moved since last run — "
        "`git log`/`git diff` against both the locally stored commit and a fresh "
        "`origin/main` fetch both came back empty. That is the 1st confirmed-"
        "unchanged check since the mirror advanced out of its prior 26-day freeze; "
        "this workflow's own gate requires 2+ consecutive unchanged runs before "
        "reclassifying a commit STALE, so it stays CURRENT_VERIFIED this week, not "
        "downgraded. Rather than stop at 'no diff,' the actual source was re-read at "
        "this same commit: Squad list/leaderboard authorization is still CONFIRMED "
        "BROKEN (GET /squads and GET /squads/leaderboard still take an unused "
        "request parameter, still no privacy filtering), database-level ownership "
        "integrity is still CONFIRMED BROKEN (clerkId/userId columns still nullable, "
        "no foreign keys), the Directive Engine is still CONFIRMED ABSENT (a fresh "
        "grep found 'directive' only as narrative/UI copy, no executable system), and "
        "training depth is still CONFIRMED SHALLOW (same four-field workouts schema). "
        "All three BUILD NOW items from Brief 07 are therefore unresolved for a full "
        "week now — this is not new information, but it is newly reconfirmed rather "
        "than merely carried forward. One real change this run: the marketing/"
        "product mismatch flagged last week as 'needs re-check against 0435f9ea' was "
        "re-checked — landing.tsx at the current commit still shows two 'Coming "
        "Soon' badges and 'Pricing will be announced before launch,' so the finding "
        "is now verified against current product source rather than a superseded "
        "commit, and moves back to BUILD NOW from last week's provisional BUILD "
        "NEXT downgrade. vitalsyncify.com itself remains unreachable from this "
        "sandbox for a 6th straight week (EGRESS_BLOCKED, logged as SOURCE_UNAVAILABLE, "
        "not as 'no marketing changes'). Competitor and market research, skipped "
        "entirely in Brief 07's manual validation run, was refreshed this week: no "
        "material pricing or positioning changes among the five deep-dived direct "
        "competitors, Bitletics remains pre-launch with its Q2/Q3 2026 window now "
        "roughly two weeks from expiring with nothing shipped, and two new market "
        "signals surfaced — MyFitnessPal's acquisition of nutrition-AI app Cal AI "
        "(further sector consolidation) and Gentler Streak shipping fatigue-aware "
        "'Morning Check-In' notifications that flag overreaching/rest days from real "
        "data, which sharpens (without yet closing) the open 'fatigue-aware "
        "gamification' market gap this brief already tracks."
    ),
    "top_actions": [
        ("Fix Squad authorization / privacy — RE-VERIFIED, still unfixed a week later",
         "RE-CONFIRMED BROKEN by fresh direct source read at the same commit: "
         "GET /squads and GET /squads/leaderboard still accept no authentication "
         "(unused request parameter) and still return every active squad with zero "
         "privacy filtering, even though the squads table has a privacy column. No "
         "admin/owner role, no invite flow. Still the sharpest concrete trust/"
         "security gap in the product, and now a week old with no fix landed."),
        ("Enforce database-level ownership — RE-VERIFIED, still unfixed a week later",
         "RE-CONFIRMED BROKEN by fresh direct source read: profileTable.clerkId and "
         "workoutsTable.userId are still nullable text columns with no foreign-key "
         "constraints, by explicit design comment ('nullable for pre-scoping rows'). "
         "Route-level scoping remains real, but nothing in the database itself "
         "enforces it — a determined bad actor or a future bug could still write "
         "cross-user data."),
        ("Build the Alignment -> Directive -> Mission connection — RE-VERIFIED, "
         "still unfixed a week later",
         "RE-CONFIRMED ABSENT by a fresh full-source grep: no Directive Engine, no "
         "directive schema, no Alignment-driven mission selection exists anywhere in "
         "the current source — missions are still chosen by onboarding-weighted "
         "randomness. Still the clearest gap in Vital Sync's own stated "
         "differentiation model (Training + Nutrition + Recovery -> Alignment -> "
         "Directive -> Mission -> Execution -> Progress -> Feedback) — the first "
         "three steps and the last two exist; the middle connective step does not."),
    ],
    "biggest_threat": (
        "Unchanged, and re-verified this run via WebSearch — Google's Gemini-"
        "powered Google Health Premium ($9.99/mo, reads HRV/sleep/activity-load, "
        "generates adaptive recovery-and-training guidance at platform scale). No "
        "expansion beyond May 2026's Fitbit/Pixel-first launch was found this week. "
        "Separately, WHOOP's $575M Series G (March 2026, found this run) reinforces "
        "how much capital platform-scale wearable/AI-coaching plays command versus "
        "gamification-first apps like Vital Sync — a funding-market data point, not "
        "a feature change."
    ),
    "biggest_gap": (
        "Unchanged, but sharpened by a new market signal this run — nobody in the "
        "competitive set ties streak/gamification mechanics to real fatigue data. "
        "Gentler Streak (found this run) now ships 'Morning Check-In Notifications' "
        "that flag overreaching or rest days from real workout/health data — closer "
        "to the fatigue-aware concept than anything previously tracked, though "
        "Gentler Streak has no XP/streak-reward gamification layer to fuse it with. "
        "On the product side, Vital Sync's own Directive Engine (re-confirmed "
        "absent this run) remains the prerequisite for doing this well — the gap, "
        "the market validation, and the internal dependency are now all "
        "independently verified facts, not assumptions."
    ),
    "biggest_weakness": (
        "Unchanged from Brief 07 in substance, but now a week older with no fix: "
        "Squad authorization is RE-CONFIRMED BROKEN (unauthenticated list/"
        "leaderboard, no privacy enforcement) and database-level ownership "
        "integrity is RE-CONFIRMED BROKEN (nullable, unenforced foreign keys) — "
        "both re-verified by fresh direct source read against the same commit, not "
        "re-asserted from last week's finding. Per-user scoping at the route level "
        "remains genuinely fixed underneath these two open gaps."
    ),
    "biggest_advantage": (
        "Unchanged — the Alignment engine and the real GPT-4o-mini coach chat "
        "remain genuinely well-built, and the VAPID private-key concern remains "
        "resolved (server-side only, no exposure found). Not reverified line-by-"
        "line this run; no evidence surfaced that would change this assessment. "
        "The gap is still data supply (wearables) and the missing Directive "
        "connective layer, not engineering quality or pricing."
    ),
    "one_to_ignore": (
        "Same as Brief 07 — chasing deeper RPG mechanics (pets, gear, cosmetic "
        "avatars), and copying RazFit's or Bitletics' formats directly (Bitletics "
        "still hasn't shipped — see Competitor Changes). Still not worth doing yet: "
        "building the fatigue-aware streak mechanic or any Directive-Engine-"
        "adjacent feature before the Directive Engine itself exists, re-confirmed "
        "absent again this run. The dependency order matters; sequencing work on "
        "top of a foundation that isn't there yet just creates more to redo later."
    ),
    "vital_sync_current_state": [
        ("Multi-User / Data Scoping", "PARTIAL", "RE-VERIFIED this run by direct "
         "source read at the unchanged commit: getOrCreateProfile(userId) and "
         "equivalents still filter WHERE clerkId/userId = the authenticated user. "
         "Database-level enforcement is separately BROKEN — see next row."),
        ("Database Integrity", "BROKEN", "RE-VERIFIED this run, still unfixed: "
         "ownership columns (profileTable.clerkId, workoutsTable.userId) are "
         "nullable with no NOT NULL constraint and no foreign keys, by explicit "
         "design comment. Route-level scoping is real; the database itself still "
         "doesn't enforce it."),
        ("Engagement / Gamification", "LIVE", "XP, Levels, Identity Ranks, Discipline "
         "Score, streaks + streak-freeze, 15 badges, 4 Boss Battles, 4 default 30-day "
         "Challenges. Not reverified in detail this run beyond the Squads rows below."),
        ("Squads — Real Activity", "COMPLETE", "RE-VERIFIED this run: "
         "getGhostCompletions and all seeded/simulated-activity code still confirmed "
         "removed. Stats still derive from real memberships and real mission/workout "
         "rows."),
        ("Squads — Authorization / Privacy", "BROKEN", "RE-VERIFIED this run, still "
         "unfixed a week later: GET /squads and GET /squads/leaderboard still have "
         "no auth check and return all squads with no privacy filtering despite a "
         "privacy column existing. No invite flow, no owner/admin role logic."),
        ("Nutrition", "PARTIAL", "Meal logging works (name/cals/macros). Protein + "
         "water + a nullable calorie target exist; no carb/fat targets. Not "
         "reverified against the current commit this run — carried from Brief 07."),
        ("Training", "PARTIAL / SHALLOW", "RE-VERIFIED this run: schema is still "
         "name/duration/type/notes only (plus the nullable userId column) — no "
         "sets/reps/weight/progressive-overload fields, unchanged since Brief 01."),
        ("Recovery", "PARTIAL", "Real multi-factor log feeding a genuine weighted "
         "algorithm — not reverified against the current commit this run, carried "
         "from Brief 02/07's finding since it wasn't re-checked this cycle."),
        ("Cross-System Intelligence (Alignment)", "PARTIAL", "Algorithm confirmed real "
         "since Brief 02 (weighted training/nutrition/recovery composite). Its output "
         "still does NOT feed into mission/directive selection — see Directive "
         "Engine row, re-verified this run."),
        ("Directive Engine", "MISSING", "RE-VERIFIED this run by a fresh full-source "
         "grep: no executable Directive Engine, directive schema, or "
         "Alignment-to-mission connection exists anywhere. Missions are still chosen "
         "by onboarding-weighted randomness. \"Directive\" appears only as UI/"
         "narrative copy."),
        ("AI — ambient brief", "PROTOTYPE", "Not reverified against the current "
         "commit this run — carried from Brief 02's finding (templated, no model "
         "call)."),
        ("AI — chat coach", "LIVE", "Real GPT-4o-mini confirmed since Brief 02. Not "
         "reverified this run — context still known (from Brief 07's export) to "
         "include profile/streak/mission data but not Alignment, Recovery, workout, "
         "or nutrition data."),
        ("Monetization", "LIVE", "Stripe \"Vital Sync Pro\" — not reverified against "
         "the current commit this run, carried from Brief 02/07."),
        ("Integrations (wearables)", "NOT FOUND", "Still absent per the last export; "
         "not independently re-grepped against the current commit this run — the "
         "top reason Alignment/Recovery have little to score."),
        ("Mobile App", "LIVE", "Full Expo/React Native app — not reverified against "
         "the current commit this run, carried from Brief 06's structural finding."),
        ("Push Notifications", "LIVE", "The VAPID-key concern remains resolved — "
         "private key confirmed server-side only, no exposure found. Not "
         "independently re-checked this run."),
        ("Auth", "LIVE", "Clerk middleware wired app-wide and RE-VERIFIED this run "
         "still actually used for route-level scoping (see Multi-User row)."),
        ("Marketing / Product Alignment", "MISMATCH", "CHANGED THIS WEEK — RE-"
         "VERIFIED at the current 0435f9ea commit (last week's flagged re-check): "
         "landing.tsx still shows two 'Coming Soon' badges and 'Pricing will be "
         "announced before launch.' The mismatch itself is unchanged in substance, "
         "but is now confirmed against current source, not a superseded commit."),
    ],
    "changes_this_week": [
        "REPOSITORY STATE, RE-VERIFIED: the GitHub mirror's HEAD (0435f9ea) has not "
        "moved since last run — `git log`/`git diff` against both the stored commit "
        "and a fresh `origin/main` fetch both came back empty. This is the 1st "
        "confirmed-unchanged check since the mirror's 09-07 advance, not yet the "
        "2+-consecutive-runs threshold this workflow requires before calling a "
        "commit STALE — so it stays CURRENT_VERIFIED, not downgraded, this week. "
        "Repository state and product state are reported separately, per the repair: "
        "an unchanged mirror is not itself proof the real product is unchanged, it "
        "is only proof the mirror hasn't moved.",
        "ALL THREE TOP BUILD NOW ITEMS RE-VERIFIED, STILL OPEN A FULL WEEK LATER: "
        "Squad list/leaderboard authorization, database-level ownership integrity, "
        "and the Directive Engine's absence were each re-confirmed this run by "
        "fresh direct source read against the unchanged commit — not re-asserted "
        "from last week's finding. None has been fixed since Brief 07.",
        "MARKETING/PRODUCT MISMATCH RE-VERIFIED AT THE CURRENT COMMIT: last week's "
        "flagged re-check (the finding rested on a now-superseded ef43285 read) was "
        "completed this run — landing.tsx at 0435f9ea still shows 'Coming Soon' and "
        "undisclosed pricing. Moves back to BUILD NOW/HIGH from last week's "
        "provisional BUILD NEXT/MEDIUM downgrade, since it's no longer resting on "
        "stale evidence.",
        "COMPETITOR/MARKET RESEARCH REFRESHED for the first time in two cycles "
        "(skipped entirely in Brief 07's manual validation run). No material "
        "pricing or feature change found among the five deep-dived direct "
        "competitors (Vora, Cora, FitCraft, Workout Quest, Habitica); Bitletics "
        "remains pre-launch with its Q2/Q3 2026 window now roughly two weeks from "
        "expiring with nothing shipped; Google Health Premium unchanged since its "
        "May 2026 launch. Two new market signals: MyFitnessPal acquired "
        "nutrition-AI app Cal AI (further sector consolidation, following the "
        "Strava/Runna and Garmin/TrainingPeaks moves noted last month), and Gentler "
        "Streak shipped fatigue-aware 'Morning Check-In' notifications — the "
        "closest market validation yet found for the 'fatigue-aware gamification' "
        "opportunity this brief tracks, though it isn't fused with any XP/streak-"
        "reward layer.",
        "NO NEW OR RESOLVED EVIDENCE CONFLICTS THIS RUN: the three conflicts closed "
        "in Brief 07 (user_scoping, squad_real_activity RESOLVED; squad_authorization "
        "confirmed as a new finding, not a conflict) stand as they were — nothing "
        "new was claimed this run without independently checkable evidence.",
    ],
    "strengths": [
        "The Alignment engine and the AI chat coach remain genuinely well-engineered "
        "— unchanged assessment; not reverified line-by-line this run.",
        "Per-user data scoping remains real at the route level — RE-VERIFIED this "
        "run by direct source read at the unchanged commit.",
        "Squads' member activity remains genuinely real, not simulated — "
        "RE-VERIFIED this run by direct code read, not by trusting last week's "
        "finding.",
        "Deep, coherent gamification core (XP/Levels/Identity Ranks/Streaks/Badges/"
        "Boss Battles) — unchanged, more developed than most competitors' equivalents.",
        "A real, structurally complete mobile app already exists — unchanged.",
    ],
    "weaknesses": [
        "Squad authorization is RE-CONFIRMED BROKEN this run — unauthenticated "
        "list/leaderboard routes, no privacy enforcement despite a privacy field "
        "existing. A real trust/security gap, unresolved for a full week now.",
        "Database-level ownership integrity is RE-CONFIRMED BROKEN this run — "
        "nullable columns, no foreign keys, under an application layer that assumes "
        "real scoping.",
        "The Directive Engine — the connective step in Vital Sync's own stated "
        "differentiation model between Alignment and Mission — is RE-CONFIRMED "
        "absent this run.",
        "Training schema remains RE-CONFIRMED shallow this run — unchanged since "
        "Brief 01, only a nullable userId column was ever added.",
        "The marketing/product mismatch (site says 'Coming Soon,' pricing "
        "undisclosed) is RE-CONFIRMED this run against the current commit — no "
        "longer resting on stale evidence, and still unresolved.",
        "Zero wearable integrations, per the last export — still the reason "
        "Alignment/Recovery have little real data to score; not independently "
        "re-grepped against the current commit this run.",
    ],
    "cross_system_audit": [
        ("Training <-> Recovery", "LIVE (algorithm)", "Unchanged — Alignment engine "
         "weights both into one score; not reverified against the new commit this "
         "run specifically, but not a disputed claim either."),
        ("Nutrition <-> Recovery", "LIVE (algorithm)", "Unchanged — both are real "
         "pillars in the same weighted Alignment score."),
        ("Sleep <-> Performance", "LIVE (algorithm)", "Unchanged — computeRecoveryScoreV2 "
         "blends multiple recovery inputs into one state."),
        ("Alignment <-> Directive/Mission", "MISSING", "RE-VERIFIED this run: "
         "Alignment's output still does not feed mission selection or any directive "
         "layer — confirmed by a fresh direct search, not carried over unchecked."),
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
         "wearable integrations. Pricing confirmed as free-forever core tier plus a "
         "Pro tier — the official site states $12.99/mo or $89.99/yr, though a "
         "separate Vora pricing page shows Pro from as low as $7.50/mo (billed "
         "annually), a discrepancy across the vendor's own pages worth treating as "
         "UNVERIFIED-EXACT rather than a single confirmed number. Core mechanism "
         "unchanged."),
        ("Cora", "Direct", "RE-CHECKED this week: still freemium with in-app "
         "purchases, still no disclosed tier pricing found in search results. App "
         "last updated 2026-04-02 per store listings — no evidence of a recent "
         "relaunch or price change. \"Body Charge\" HRV/sleep-driven scheduling "
         "mechanism unchanged."),
        ("FitCraft", "Direct", "RE-CHECKED this week: pricing and core mechanism "
         "(streaks, collectible cards, AI coach, gamified rewards) unchanged. Recent "
         "product updates found are cosmetic/UX (new visual effects, calendar and "
         "rewards-gamification polish) — not a new capability. Still no nutrition/"
         "recovery features found."),
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
         "CHECKED partially this week: WHOOP raised a $575M Series G in March 2026 "
         "(per a Crunchbase News H1-2026 fitness-funding sector snapshot found this "
         "run) — a scale/capital data point, not a product change. Search results "
         "on Strava's Runna acquisition date were inconsistent across sources this "
         "run (2025 vs. 2026); not re-asserting a specific date pending a cleaner "
         "source. No other changes found."),
        ("Bitletics", "Emerging / Beta", "RE-CHECKED this week: still pre-launch, "
         "still described as launching iOS and Android together, free at launch, no "
         "subscription required, 30+ activity types, Apple Watch/heart-rate "
         "verified. Its Q2/Q3 2026 launch window is now roughly two weeks from "
         "expiring (Q3 2026 ends Sept 30) with no ship date found — MONITOR, "
         "sharpening toward 'window missed' if nothing lands by month end."),
        ("Google Health Premium (Gemini Health Coach, formerly Fitbit Premium)",
         "Indirect / Platform-scale",
         "RE-CHECKED this week: confirmed unchanged — still $9.99/mo or $99/yr, "
         "coach (launched May 19 2026) still described as launching first for "
         "Fitbit/Pixel Watch users with other devices \"forthcoming.\" No new "
         "expansion found this week. Reads HRV/sleep/activity-load trends and "
         "generates adaptive, continuously-updated recovery-and-training "
         "recommendations — the same category of output as Vital Sync's Alignment "
         "engine, at hardware-platform distribution scale. Not a fitness-"
         "gamification competitor (no XP/streaks/badges), but a direct threat to "
         "the 'wearable-driven adaptive coaching' value proposition."),
        ("RazFit", "Emerging / Live", "RE-CHECKED this week: still built around "
         "1-10 minute equipment-free bodyweight sessions with a badge reward "
         "system, pitched as \"consistency over intensity.\" Still no confirmed "
         "ongoing subscription price beyond a 3-day free trial (not found in "
         "search results again this week). No nutrition or recovery tracking "
         "found. Small/unproven scale — MONITOR, low confidence, unchanged."),
        ("Gentler Streak", "Specialist / Indirect", "NEW ROW THIS WEEK (previously "
         "referenced only in passing, not tracked as its own line): a wellbeing-"
         "first workout tracker, $8.99/mo or $39.99/yr. Recently shipped 'Morning "
         "Check-In Notifications' — a gentle, data-driven flag when yesterday's "
         "session was an overreach or today should be a rest day, including "
         "cycle-aware timing for women. No XP/streak-reward gamification layer at "
         "all (its whole positioning is the opposite — 'gentler' than streak-"
         "anxiety apps), so it doesn't compete with Vital Sync's core loop, but it "
         "is the closest real-world validation yet found for tying recovery "
         "guidance to daily behavior — directly relevant to the fatigue-aware "
         "gamification opportunity this brief tracks (see Product Opportunities)."),
    ],
    "pain_clusters": [
        ("Streak anxiety / burnout", "Missing a streak is reported as demotivating; "
         "some quit once the streak itself, not real progress, became the goal. "
         "Directly relevant — Vital Sync's core loop is streak-built. RE-CHECKED "
         "this week, unchanged."),
        ("Gamification fatigue in experienced users", "RE-CHECKED this week and "
         "unchanged: badges/streaks/leaderboards without real fitness outcomes are "
         "\"consistently mocked\" by serious-lifter communities as shallow when done "
         "badly; notification overload from achievement systems specifically called "
         "out as annoying."),
        ("Loggers pretending to be coaches", "\"Most workout apps in 2026 are loggers, "
         "not coaches\"; apps faking adaptivity with heuristics instead of real "
         "wearable data draw criticism once noticed. Not re-checked this week."),
        ("Subscription fatigue", "Average user carries 4+ health subscriptions; "
         "previously-free features moving behind paywalls is a recurring complaint "
         "— MyFitnessPal's 2022 paywall change is still cited as the cautionary "
         "example as of searches run this week."),
        ("Health-data privacy sensitivity", "Fitness-app audiences are more "
         "privacy-conscious than average; vague data-sharing policies, or a data "
         "breach, carry lasting negative sentiment. RE-CHECKED this week, unchanged."),
        ("Weak first-week activation", "NEW THIS WEEK: users who don't complete at "
         "least 3 workouts in their first week churn at 4-5x the rate of those who "
         "do (2026 fitness-app retention benchmarking). Relevant to Vital Sync's "
         "onboarding-weighted mission selection — first-week engagement design "
         "matters disproportionately, independent of the Directive Engine question."),
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
        "for real adaptive coaching outpaces what's shipped industry-wide. RE-"
        "CHECKED this week, still the dominant framing in search results.",
        "NEW THIS WEEK: first-week activation is a named, measured lever — apps that "
        "get a user through 3 workouts in week one see 4-5x better retention than "
        "those that don't, per 2026 fitness-app benchmarking research.",
    ],
    "market_trends": [
        "Wearables are the retention lever — health monitoring has overtaken fitness "
        "tracking as the primary wearable use case; app-side integration is now table "
        "stakes for retention.",
        "Fitness app churn is brutal across every dataset checked (RE-CHECKED this "
        "week, figures consistent with prior briefs), though the exact numbers vary "
        "by source and methodology — a Sensor Tower Q4 2025 report shows "
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
        "Consolidation continues — following last month's Strava/Runna and Garmin/"
        "TrainingPeaks moves, MyFitnessPal acquired nutrition-AI app Cal AI this "
        "period (a Forbes '30 Under 30'-built app reported at $40M in sales) — "
        "notable because it's consolidation specifically in the nutrition-AI layer "
        "adjacent to Vital Sync's own nutrition module, not just training/recovery. "
        "Startup funding in fitness/wellness topped $3.6B in H1 2026 (on pace to run "
        "roughly a third higher than 2025), concentrated in fewer, larger AI-enabled "
        "rounds — WHOOP's $575M Series G (March 2026) is the largest single data "
        "point found this week. Raises the urgency of Vital Sync differentiating on "
        "cross-system Alignment intelligence before boutique positioning gets "
        "squeezed by bigger, AI-coaching-plus-hardware players.",
        "NEW THIS WEEK: activation, not just retention, is now separately measured "
        "— users who don't complete 3 workouts in their first week churn 4-5x faster "
        "than those who do. The global fitness-app market is estimated at $13.9B in "
        "2026 (context figure, not independently cross-verified against a second "
        "source this run).",
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
         "only because they have wearable data feeding equivalent logic — and Google's "
         "Health Premium Gemini Coach shows the same play at platform scale. Vital "
         "Sync's engine has zero wearable connections. (Competitor detail RE-CHECKED "
         "this week: unchanged.)"),
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
         "filtering. A real access-control gap, not cosmetic, unresolved for a "
         "full week now.",
         "BUILD NOW", "-", "No AI Needed", "HIGH"),
        (2, "Enforce database-level ownership", "RE-CONFIRMED BROKEN this run: "
         "nullable ownership columns, no foreign keys, underneath a now-real "
         "application-level scoping layer, unresolved for a full week now.",
         "BUILD NOW", "-", "No AI Needed", "HIGH"),
        (3, "Build the Alignment -> Directive -> Mission connection", "RE-CONFIRMED "
         "ABSENT this run: missions are chosen by onboarding-weighted randomness, "
         "not by Alignment output. The connective step in Vital Sync's own "
         "differentiation model still doesn't exist.",
         "BUILD NOW", "A", "AI Assisted", "HIGH"),
        (4, "Fix the marketing/product mismatch", "RE-VERIFIED this run against the "
         "CURRENT commit (0435f9ea) — last week's flagged re-check is done: "
         "landing.tsx still shows two 'Coming Soon' badges and 'Pricing will be "
         "announced before launch.' No longer resting on a superseded commit, so "
         "promoted back to BUILD NOW/HIGH from last week's provisional downgrade.",
         "BUILD NOW", "Trust", "No AI Needed", "HIGH"),
        (5, "Connect Apple Health as first wearable", "Broadest reach, lowest effort; "
         "feeds the already-working Alignment/Recovery algorithms with real data. "
         "Competitive urgency reinforced this week by WHOOP's $575M Series G and "
         "Google Health Premium's continued stability — capital keeps flowing to "
         "wearable-data-driven coaching. Not reverified against Vital Sync's source "
         "this run beyond confirming wearables remain absent per the last export.",
         "BUILD NEXT", "A", "No AI Needed", "HIGH"),
        (6, "Surface the real AI chat coach more prominently, and widen its context",
         "/coach/message is live GPT-4o-mini — its context excludes Alignment/"
         "Recovery/workout/nutrition data (confirmed Brief 07, not reverified this "
         "run). Two separate improvements: visibility, and context depth.",
         "BUILD NEXT", "C", "AI Core", "MEDIUM"),
        (7, "Real training depth (sets/reps/weight/overload)", "RE-CONFIRMED "
         "unchanged this run: workouts table still has no sets/reps/weight fields "
         "at all.",
         "BUILD NEXT", "A", "No AI Needed", "HIGH"),
        (8, "Fatigue-aware streak mechanic", "Streak downgrades gracefully instead of "
         "breaking, when real recovery data is low. Still confirmed to depend on "
         "the Directive Engine (#3) and wearables (#5) landing first — do not build "
         "before those. Market validation sharpened this week: Gentler Streak now "
         "ships fatigue/overreach-aware check-ins (without a gamification layer), "
         "the closest real-world precedent found yet, though this doesn't change "
         "the internal dependency order.", "EXPERIMENT", "D", "AI Assisted", "MEDIUM"),
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
         "two weeks from expiring (Q3 2026 ends Sept 30) with no ship date found. "
         "Too early to act on, worth tracking closely over the next brief or two.",
         "MONITOR", "D", "No AI Needed", "LOW"),
        (12, "Monitor Google Health Premium's Gemini Coach as a platform-scale threat, "
         "not a build target", "Formerly Fitbit Premium — RE-CHECKED this week: "
         "confirmed unchanged, no new expansion found. Google ships the same "
         "'wearable data -> adaptive recovery/training guidance' output Vital Sync's "
         "Alignment engine produces, at a growing distribution scale. Not something "
         "Vital Sync can out-build directly; sharpens the case for #5 (connect a "
         "wearable) and for leaning on cross-system Alignment (training+nutrition+"
         "recovery together) as the differentiator Google doesn't offer.", "MONITOR",
         "A", "No AI Needed", "MEDIUM"),
        (13, "Track RazFit as a low-friction, short-session entrant", "RE-CHECKED "
         "this week: still built around 1-10 minute equipment-free bodyweight "
         "sessions and a badge reward system, pitched as \"consistency over "
         "intensity.\" Ongoing subscription price still UNKNOWN; scale/traction "
         "still unconfirmed. No change from last week — still MONITOR only.",
         "MONITOR", "D", "No AI Needed", "LOW"),
        (14, "Track Gentler Streak's fatigue-aware check-in mechanic", "NEW THIS "
         "WEEK: added as its own tracked line after its 'Morning Check-In "
         "Notifications' feature surfaced during this run's competitor refresh. "
         "$8.99/mo or $39.99/yr, no gamification layer at all — not a direct "
         "competitor to Vital Sync's core loop, but the clearest real-world "
         "precedent yet for tying daily guidance to real recovery signals. Relevant "
         "to #8 as market validation, not as a feature to copy directly (Gentler "
         "Streak's whole brand is the anti-gamification, anti-streak-anxiety "
         "positioning).", "MONITOR", "D", "No AI Needed", "MEDIUM"),
    ],
    "opportunity_movement": [
        "#1, #2, #3 (BUILD NOW) — UNCHANGED IN RANK, but RE-VERIFIED rather than "
        "carried forward from memory: Vital-Sync HEAD is confirmed unchanged at "
        "0435f9ea (`git log`/`git diff` against Brief 07's stored commit, and "
        "against a fresh origin/main fetch, both empty), and the actual squads.ts, "
        "profile.ts, schema files, and a full-source 'directive' grep were freshly "
        "read this run — all three findings hold exactly as before. All three are "
        "now a full week old with no fix landed; that aging is itself worth a "
        "human's attention even though the score is unchanged.",
        "#4 (Fix the marketing/product mismatch) — MOVED UP: BUILD NEXT/MEDIUM -> "
        "BUILD NOW/HIGH. Brief 07 downgraded this pending re-check against the new "
        "0435f9ea commit (its evidence rested on a superseded ef43285 read). That "
        "re-check happened this run — landing.tsx at 0435f9ea still shows 'Coming "
        "Soon' and undisclosed pricing — so the finding is now maximally current "
        "and returns to BUILD NOW rather than sitting provisionally downgraded.",
        "#5 (Connect Apple Health as first wearable, renumbered from #5) — STILL "
        "BUILD NEXT/HIGH, no change in bucket. Competitive backdrop reinforced, not "
        "newly urgent: WHOOP's $575M Series G and continued capital flow into "
        "wearable-data coaching plays (found this run) sit alongside Google Health "
        "Premium's confirmed-unchanged status. Vital Sync's own wearables status "
        "was not independently re-grepped this run — carried from the last export.",
        "#7 (Real training depth, renumbered from #7) — UNCHANGED bucket, but "
        "RE-VERIFIED this run via direct schema read rather than carried forward — "
        "workouts table confirmed still four fields, no sets/reps/weight.",
        "#8 (Fatigue-aware streak mechanic, EXPERIMENT) — UNCHANGED bucket, "
        "evidence sharpened: Gentler Streak (found this run) now ships fatigue/"
        "overreach-aware Morning Check-In notifications, the closest real-world "
        "precedent found yet for this mechanic. Still gated on the Directive Engine "
        "(#3) and wearables (#5) landing first — the new evidence strengthens the "
        "market case, not the internal readiness, so the bucket doesn't move.",
        "#11 (Track Bitletics, MONITOR) — NOT RE-RANKED, still LOW confidence. "
        "RE-CHECKED this week: still pre-launch, still free-at-launch/no-"
        "subscription-required as previously described, and its Q2/Q3 2026 window "
        "is now roughly two weeks from expiring (Q3 ends Sept 30) with no ship date "
        "found. Next run should explicitly check whether it shipped or the window "
        "lapsed.",
        "#12 (Google Health Premium, MONITOR) — NOT RE-RANKED; RE-CHECKED this "
        "week, confirmed unchanged, no new expansion found. Stays MONITOR/MEDIUM — "
        "sharpens the case for #5, not a build target itself.",
        "#13 (Track RazFit, MONITOR) — NOT RE-RANKED. RE-CHECKED this week: no "
        "change found, pricing still UNKNOWN beyond the 3-day trial.",
        "#14 (Track Gentler Streak, MONITOR) — NEW THIS WEEK. Found via this run's "
        "competitor refresh (previously mentioned only in passing under #8, never "
        "its own tracked line). Added at MEDIUM confidence — its pricing and "
        "feature set are well-documented, but it isn't a gamification competitor to "
        "Vital Sync, so it's tracked as market validation for #8, not a threat in "
        "its own right.",
        "#9, #10 (nutrition goals, voice logging) — UNCHANGED, not reverified this "
        "run.",
        "NO ITEMS RESOLVED OR REMOVED THIS RUN — a quieter week than Brief 07's "
        "major reconciliation. The backlog's shape is stable; what changed is which "
        "items are freshly re-verified (#1-3, #4, #7) versus carried forward "
        "unchecked (#6, #9, #10), and that distinction is what this brief's "
        "Product State Delta and this list are for.",
    ],
    "sources": [
        "github.com/faristjohar04-sketch/Vital-Sync — RE-CHECKED this run via "
        "`git log`/`git diff` against both the locally stored commit "
        "(0435f9ea79a871cd1578e2dc22e8e3055bebc50e) and a fresh `origin/main` "
        "fetch — both empty, commit confirmed unchanged since Brief 07 "
        "(2026-09-07). This is the 1st confirmed-unchanged check since that "
        "advance, not yet the 2+-consecutive-runs threshold for reclassifying the "
        "mirror STALE.",
        "github.com/faristjohar04-sketch/Vital-Sync @ 0435f9ea — direct source "
        "RE-READS performed this run (same commit, fresh read, not assumed "
        "unchanged from Brief 07): artifacts/api-server/src/routes/profile.ts (user "
        "scoping), artifacts/api-server/src/routes/squads.ts (real activity + "
        "authorization), lib/db/src/schema/workouts.ts and profile.ts (training "
        "depth + nullable ownership columns), a full-source grep for \"directive\" "
        "(Directive Engine absence), and artifacts/vital-sync/src/pages/landing.tsx "
        "(marketing/product mismatch — the re-check flagged last week, now done)",
        "vital_sync_current_product_state.json — a structured audit export "
        "provided by the user on 2026-09-07/08, cross-checked against the commit "
        "above in Brief 07's run. No newer export was provided this run; areas "
        "resting solely on it are marked UNCHANGED — NOT REVERIFIED in this brief's "
        "Current State table, not re-asserted as freshly confirmed.",
        "https://vitalsyncify.com — attempted directly this run (WebFetch): "
        "EGRESS_BLOCKED, the 6th consecutive week this has failed from this "
        "sandbox. Logged as SOURCE_UNAVAILABLE for the marketing-mismatch check, "
        "not treated as evidence of 'no marketing changes.'",
        "WebSearch (this run, competitor/market refresh — first refresh in two "
        "cycles): official/store pages for Vora, Cora, FitCraft; Bitletics' own "
        "blog and app-store listings; RazFit's own comparison pages; Google/"
        "TechCrunch/9to5Google/MobiHealthNews coverage of Google Health Premium; "
        "Gentler Streak's App Store listing, review site, and blog; Crunchbase News "
        "H1-2026 fitness-funding sector snapshot (WHOOP Series G, sector totals); "
        "Athletech News (MyFitnessPal/Cal AI acquisition); Lifecycle Architect, "
        "RetentionCheck, and a Fitness Refined 2026 churn/retention report set "
        "(activation, Day-30 retention, churn-rate benchmarks); Reddit-sentiment "
        "sourced via search (gamification fatigue, subscription-paywall complaints) "
        "— direct WebFetch to competitor domains remains typically EGRESS_BLOCKED "
        "in this sandbox, so WebSearch snippets were used throughout, as in prior "
        "briefs.",
        "Workout Quest, Habitica, Trainera/Bevel/NATE — surface-level watch only, "
        "NOT re-checked this run; carried forward unchanged from Brief 07.",
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
