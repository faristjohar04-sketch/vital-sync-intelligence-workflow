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
# THIS WEEK'S DATA — Brief 09, compiled 2026-09-28, CORRECTED same-day after a
# repo-owner PR comment. Original mistake: this run initially reported "no
# automated run on 2026-09-21" and counted the GitHub mirror's unchanged
# streak as only 2 checks. Both were wrong. A run DID fire on 2026-09-21 and
# produced PR #2, independently reaching the same STALE conclusion a week
# earlier — it was just never merged into main (this repo's documented local
# `vitalsync-weeklyfinish` merge cron appears not to be running), so this run
# started from a main still on Brief 08 content and undercounted. Verified
# against PR #2 directly (timestamps, base commit, body) before accepting the
# correction, per this workflow's own "a claim is not evidence" standard. The
# correct count is 3 consecutive unchanged checks (2026-09-14, 2026-09-21,
# 2026-09-28) — still STALE, same conclusion, corrected reasoning. This
# correction also recovers a real finding from PR #2's independent research
# that would otherwise have been lost: Apple's 2026-09-09 Health app redesign
# (free Readiness score + AI Insights, no subscription), independently
# re-verified via WebSearch this run and folded in below.
# ---------------------------------------------------------------------------
WEEK_DATA = {
    "report_date": "2026-10-05",
    "run_label": "Brief 10 — GitHub mirror STILL STALE (4th consecutive unchanged check at 0435f9ea; no merge-backlog problem this time); the four BUILD NOW findings carried forward unchanged via a full-repo diff-empty check rather than a fresh file re-read; competitor refresh finds real changes at Vora, Workout Quest, RazFit, and Bitletics (launch window now confirmed LAPSED)",
    "exec_summary": (
        "PRODUCT SOURCE FRESHNESS REMAINS STALE THIS RUN — see the warning banner "
        "in the Product Source Freshness section below; all product-build "
        "recommendations in this report remain provisional. Repository state and "
        "product state continue to be reported as two separate facts, per the "
        "2026-09-07 repair. The GitHub mirror's HEAD commit (0435f9ea) has now "
        "been independently confirmed unchanged across 4 real runs (2026-09-14, "
        "2026-09-21 via PR #2, 2026-09-28, 2026-10-05) — `git log`/`git diff` "
        "against both the locally stored commit and a fresh `origin/main` fetch "
        "came back empty again this run. Unlike two runs ago, there was no "
        "merge-backlog problem this time: `main` already carried PR #3's merge "
        "before this run started, so no PR was stuck unmerged. Given 4 straight "
        "byte-identical confirmations at this exact commit, this run relied on a "
        "repo-wide `git diff --stat` (zero changed files across the entire tree) "
        "rather than re-reading squads.ts/profile.ts/workouts.ts/landing.tsx "
        "line-by-line again — every finding below is therefore carried forward as "
        "UNCHANGED — VERIFIED via that diff-empty confirmation, not re-derived "
        "from a fresh semantic read this run. Squad list/leaderboard "
        "authorization remains BROKEN, database-level ownership integrity remains "
        "BROKEN, the Directive Engine remains ABSENT, training depth remains "
        "SHALLOW, and the marketing/product mismatch remains unresolved — all "
        "four weeks old now. vitalsyncify.com itself remains unreachable from "
        "this sandbox for an 8th consecutive check (EGRESS_BLOCKED on both "
        "WebFetch and a direct curl attempt this run, logged as "
        "SOURCE_UNAVAILABLE). Competitor and market research, independent of "
        "Layer A freshness, found several real changes this run: Vora shipped a "
        "September 1 update adding direct Oura Cloud integration (bypassing "
        "Apple Health) plus Strong/Hevy/Fitbod lift-history import and a COROS "
        "connection — a genuine cross-system data-consolidation move this "
        "workflow had not previously surfaced; Workout Quest shipped a "
        "recovery-data-aware AI chat feature, moving toward the exact "
        "Recovery<->Workout-Recommendation territory Vital Sync's own Directive "
        "Engine gap sits in; RazFit shipped version 1.5.1 (redesigned onboarding "
        "and workout flow, built-in music player, better Apple Watch sync, now "
        "live in 6 languages); and WHOOP 5.0 launched in India (geographic "
        "expansion, not a mechanism change). Most notably, Bitletics' Q2/Q3 2026 "
        "launch window (Q3 ended 2026-09-30) has now LAPSED with still no "
        "evidence of an actual launch found — confirmed this run, not merely "
        "'about to expire' as flagged last week. Apple's free Health app "
        "redesign (announced 2026-09-09) remains the single biggest "
        "platform-scale threat found to date; no new Apple Health development "
        "surfaced this run. A new entrant feature worth watching: BodBot shipped "
        "a camera-based, computer-vision rep-counting/form-check mode — a "
        "concrete example of the computer-vision coaching trend already flagged "
        "in Market Trends as absent from Vital Sync's surface."
    ),
    "top_actions": [
        ("Fix Squad authorization / privacy — CONFIRMED UNCHANGED, unfixed for 4 weeks, PROVISIONAL",
         "CONFIRMED UNCHANGED this run via a repo-wide diff-empty check (not a "
         "fresh file re-read): GET /squads and GET /squads/leaderboard still "
         "accept no authentication (unused request parameter) and still return "
         "every active squad with zero privacy filtering, even though the squads "
         "table has a privacy column, per the 2026-09-28 direct read. No "
         "admin/owner role, no invite flow. Still the sharpest concrete trust/"
         "security gap in the product. Flagged PROVISIONAL this run only because "
         "the mirror itself is now STALE-classified (4 weeks frozen) — not because "
         "the finding is in doubt at this commit."),
        ("Enforce database-level ownership — CONFIRMED UNCHANGED, unfixed for 4 weeks, PROVISIONAL",
         "CONFIRMED UNCHANGED this run via a repo-wide diff-empty check: "
         "profileTable.clerkId and workoutsTable.userId are still nullable text "
         "columns with no foreign-key constraints, by explicit design comment "
         "('nullable for pre-scoping rows'), per the 2026-09-28 direct read. "
         "Route-level scoping remains real, but nothing in the database itself "
         "enforces it — a determined bad actor or a future bug could still write "
         "cross-user data."),
        ("Build the Alignment -> Directive -> Mission connection — CONFIRMED "
         "UNCHANGED, unfixed for 4 weeks, PROVISIONAL",
         "CONFIRMED ABSENT this run via a repo-wide diff-empty check: "
         "getTomorrowDirective() remains `TOMORROW_DIRECTIVE_POOL[seed % "
         "pool.length]` — a fixed pool lookup, not Alignment-driven selection, per "
         "the 2026-09-28 direct read. No Directive Engine, no directive schema "
         "exists anywhere in the mirror — missions are still chosen by onboarding-"
         "weighted randomness. Still the clearest gap in Vital Sync's own stated "
         "differentiation model (Training + Nutrition + Recovery -> Alignment -> "
         "Directive -> Mission -> Execution -> Progress -> Feedback). Externally, "
         "Workout Quest shipped a recovery-data-aware AI chat feature this run — "
         "a competitor edging into adjacent territory while this gap sits open."),
    ],
    "biggest_threat": (
        "UNCHANGED this week — no new Apple Health development surfaced in this "
        "run's searches. Apple's 2026-09-09 Health app redesign (a free "
        "Readiness score, 'Health Age' computation, and an AI Insights tab "
        "powered by Apple Intelligence, no subscription required, rolling out to "
        "every iPhone/Apple Watch user) remains the single biggest platform-"
        "scale threat found to date — the same category of output as Vital "
        "Sync's own Alignment engine, for free, at hardware-platform scale. A "
        "secondary movement found this run: Vora (a direct competitor) shipped a "
        "September 1 update adding a direct Oura Cloud integration (bypassing "
        "Apple Health entirely for Readiness/HRV/sleep-staging data) plus "
        "Strong/Hevy/Fitbod lift-history import and a COROS connection — a real "
        "cross-system data-consolidation move this workflow had not previously "
        "surfaced, closing Vora's data-supply gap from a different angle than "
        "Apple/Google's platform-level push. Separately (previously tracked, "
        "unchanged): Google Health Premium's Gemini coach; Strava's $2.2B "
        "funding round; WHOOP's $575M Series G — all reinforcing the same "
        "capital pattern favoring platform-scale wearable/AI-coaching plays over "
        "gamification-first apps like Vital Sync."
    ),
    "biggest_gap": (
        "Unchanged in kind, sharpened further this run — nobody in the "
        "competitive set ties streak/gamification mechanics to real fatigue "
        "data. New this run: Workout Quest shipped a recovery-data-aware AI "
        "chat feature (mid-workout questions like 'should I drop set this "
        "next set' answered against recovery context) — a competitor now "
        "edging toward the Recovery<->Workout-Recommendation connection Vital "
        "Sync's own cross-system audit still marks NOT FOUND, though still "
        "without any gamification layer fused to it. Gentler Streak remains the "
        "closest full precedent (fatigue-aware check-ins, no gamification). "
        "Separately, Vora's new Oura/COROS/lift-import consolidation (found "
        "this run) closes a second competitor's data-supply gap further. On "
        "the product side, Vital Sync's own Directive Engine (confirmed absent "
        "this run via diff check, PROVISIONAL per the STALE mirror) remains the "
        "prerequisite for doing any of this well."
    ),
    "biggest_weakness": (
        "Unchanged in substance, now 4 weeks old with no fix and PROVISIONAL "
        "pending fresher product-source access: Squad authorization is "
        "CONFIRMED UNCHANGED (unauthenticated list/leaderboard, no privacy "
        "enforcement) and database-level ownership integrity is CONFIRMED "
        "UNCHANGED (nullable, unenforced foreign keys) — both confirmed this run "
        "via a repo-wide diff-empty check against the same commit, not a fresh "
        "file read. Per-user scoping at the route level remains genuinely fixed "
        "underneath these two open gaps."
    ),
    "biggest_advantage": (
        "Unchanged — the Alignment engine and the real GPT-4o-mini coach chat "
        "remain genuinely well-built, and the VAPID private-key concern remains "
        "resolved (server-side only, no exposure found). Not reverified line-by-"
        "line this run; no evidence surfaced that would change this assessment. "
        "Worth watching: Workout Quest deepened its AI chat into recovery-aware "
        "territory this run — the 'AI coach' claim keeps converging toward "
        "parity industry-wide; depth of context is what would keep Vital Sync "
        "ahead, and that context depth is still the open gap (see ai_coach_context)."
    ),
    "one_to_ignore": (
        "Same guidance as prior briefs — chasing deeper RPG mechanics (pets, "
        "gear, cosmetic avatars), and copying RazFit's or Bitletics' formats "
        "directly (Bitletics' Q2/Q3 2026 launch window has now LAPSED with "
        "nothing shipped, confirmed this run — see Competitor Changes). Still "
        "not worth doing yet: building the fatigue-aware streak mechanic or any "
        "Directive-Engine-adjacent feature before the Directive Engine itself "
        "exists, confirmed absent again this run. The dependency order matters; "
        "sequencing work on top of a foundation that isn't there yet just "
        "creates more to redo later."
    ),
    "vital_sync_current_state": [
        ("Multi-User / Data Scoping", "PARTIAL", "CONFIRMED UNCHANGED this run via "
         "a repo-wide diff-empty check against the unchanged (now STALE-"
         "classified) commit: getOrCreateProfile(userId) and equivalents still "
         "filter WHERE clerkId/userId = the authenticated user, per the "
         "2026-09-28 direct read. Database-level enforcement is separately "
         "BROKEN — see next row."),
        ("Database Integrity", "BROKEN", "CONFIRMED UNCHANGED this run via a "
         "repo-wide diff-empty check, still unfixed for 4 weeks of calendar "
         "time: ownership columns (profileTable.clerkId, workoutsTable.userId) "
         "are nullable with no NOT NULL constraint and no foreign keys, by "
         "explicit design comment. Route-level scoping is real; the database "
         "itself still doesn't enforce it."),
        ("Engagement / Gamification", "LIVE", "XP, Levels, Identity Ranks, Discipline "
         "Score, streaks + streak-freeze, 15 badges, 4 Boss Battles, 4 default 30-day "
         "Challenges. Not reverified in detail this run beyond the Squads rows below."),
        ("Squads — Real Activity", "COMPLETE", "CONFIRMED UNCHANGED this run via a "
         "repo-wide diff-empty check — not re-grepped this run; the "
         "2026-09-28 full grep for getGhostCompletions/seededRand/ghost returned "
         "zero matches. Stats still derive from real memberships and real "
         "mission/workout rows."),
        ("Squads — Authorization / Privacy", "BROKEN", "CONFIRMED UNCHANGED this "
         "run via a repo-wide diff-empty check, still unfixed for 4 weeks of "
         "calendar time: GET /squads and GET /squads/leaderboard still have no "
         "auth check and return all squads with no privacy filtering despite a "
         "privacy column existing, per the 2026-09-28 direct read."),
        ("Nutrition", "PARTIAL", "Meal logging works (name/cals/macros). Protein + "
         "water + a nullable calorie target exist; no carb/fat targets. Not "
         "reverified against the current commit this run — carried from Brief 07."),
        ("Training", "PARTIAL / SHALLOW", "CONFIRMED UNCHANGED this run via a "
         "repo-wide diff-empty check: schema is still name/duration/type/notes "
         "only (plus the nullable userId column) — no sets/reps/weight/"
         "progressive-overload fields, unchanged since Brief 01. Gap remains "
         "wide open against Strava's strength-training push (new workout log, "
         "muscle maps, unchanged from last week, no further Strava change found "
         "this run)."),
        ("Recovery", "PARTIAL", "Real multi-factor log feeding a genuine weighted "
         "algorithm — not reverified against the current commit this run, carried "
         "from Brief 02/07's finding since it wasn't re-checked this cycle."),
        ("Cross-System Intelligence (Alignment)", "PARTIAL", "Algorithm confirmed real "
         "since Brief 02 (weighted training/nutrition/recovery composite). Its output "
         "still does NOT feed into mission/directive selection — see Directive "
         "Engine row, re-verified this run."),
        ("Directive Engine", "MISSING", "CONFIRMED UNCHANGED this run via a "
         "repo-wide diff-empty check: getTomorrowDirective() remains a fixed "
         "`pool[seed % length]` lookup, not Alignment-driven, per the 2026-09-28 "
         "direct read. No executable Directive Engine, directive schema, or "
         "Alignment-to-mission connection exists anywhere. Missions are still "
         "chosen by onboarding-weighted randomness. \"Directive\" appears only as "
         "UI/narrative copy."),
        ("AI — ambient brief", "PROTOTYPE", "Not reverified against the current "
         "commit this run — carried from Brief 02's finding (templated, no model "
         "call)."),
        ("AI — chat coach", "LIVE", "Real GPT-4o-mini confirmed since Brief 02. Not "
         "reverified this run — context still known (from Brief 07's export) to "
         "include profile/streak/mission data but not Alignment, Recovery, workout, "
         "or nutrition data. Competitive backdrop sharpened again: Workout Quest "
         "deepened its AI chat into recovery-aware territory this run (UNVERIFIED "
         "whether genuinely LLM-backed) — the 'has an AI coach' claim alone is no "
         "longer distinguishing; context depth would be."),
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
        ("Marketing / Product Alignment", "MISMATCH", "CONFIRMED UNCHANGED via a "
         "repo-wide diff-empty check against the same 0435f9ea commit for a "
         "fourth consecutive run: landing.tsx still shows two 'Coming Soon' "
         "badges and 'Pricing will be announced before launch,' per the "
         "2026-09-28 direct read. vitalsyncify.com itself remains unreachable "
         "(8th consecutive check, EGRESS_BLOCKED on both WebFetch and a direct "
         "curl attempt this run)."),
    ],
    "changes_this_week": [
        "REPOSITORY STATE REMAINS STALE, NOW 4 CONSECUTIVE CHECKS: the GitHub "
        "mirror's HEAD (0435f9ea) has still not moved — `git log`/`git diff` "
        "against both the stored commit and a fresh `origin/main` fetch both "
        "came back empty again. This is the 4th confirmed-unchanged check since "
        "the mirror's 09-07 advance (2026-09-14, 2026-09-21, 2026-09-28, "
        "2026-10-05). No merge-backlog problem this time — `main` already "
        "carried PR #3's merge before this run started, so last fortnight's "
        "unmerged-PR issue did not recur (one clean week; not yet proof the "
        "underlying `vitalsync-weeklyfinish` cron is fixed). Given 4 straight "
        "byte-identical confirmations, this run used a repo-wide `git diff "
        "--stat` (zero changed files across the entire tree) rather than "
        "re-reading the previously-disputed files line-by-line again — every "
        "product-state finding below is carried forward as UNCHANGED — VERIFIED "
        "via that diff-empty confirmation, not re-derived from a fresh read "
        "this run.",
        "ALL FOUR BUILD-NOW-TIER FINDINGS CONFIRMED UNCHANGED, STILL PROVISIONAL: "
        "Squad list/leaderboard authorization, database-level ownership "
        "integrity, the Directive Engine's absence, and the marketing/product "
        "mismatch all remain exactly as last verified on 2026-09-28, confirmed "
        "via the repo-wide diff-empty check above — unchanged in substance for a "
        "fourth consecutive run, still flagged PROVISIONAL given the mirror's "
        "STALE classification.",
        "COMPETITOR/MARKET RESEARCH REFRESHED, REAL CHANGES FOUND: Vora shipped "
        "a September 1 update (v3.3.11) adding a direct Oura Cloud API "
        "integration — bypassing Apple Health entirely for Readiness Score, "
        "body-temperature deviation, granular sleep staging, and real-time HRV "
        "— plus Strong/Hevy/Fitbod lift-history import and a direct COROS "
        "connection; this is a genuine cross-system data-consolidation move this "
        "workflow had not previously surfaced (last week's check called Vora "
        "'confirmed unchanged'). Workout Quest shipped a recovery-data-aware AI "
        "chat feature (answering mid-workout questions like whether to drop-set "
        "against the user's recovery context), deepening its already-tracked "
        "AI-Fitness Chat. RazFit shipped version 1.5.1 — redesigned onboarding/"
        "Today-plan/exercise-library/profile flow, a built-in music player, "
        "better Apple Watch sync, and expansion to 6 languages; pricing "
        "unchanged. WHOOP 5.0 launched in India (geographic expansion of an "
        "already-tracked device, not a mechanism change). A new-entrant "
        "discovery: BodBot shipped a camera-based computer-vision rep-counting/"
        "form-check mode — a concrete instance of the computer-vision-coaching "
        "trend already flagged in Market Trends. MOST SIGNIFICANT: Bitletics' "
        "Q2/Q3 2026 launch window (Q3 ended 2026-09-30) has now LAPSED with "
        "still no evidence of an actual launch found in this run's fresh "
        "searches — confirmed this run, sharpened from last week's 'about to "
        "expire' flag. No new Apple Health, Google Health, Cora, FitCraft, or "
        "Strava development surfaced this run beyond what was already captured "
        "last week.",
        "NO NEW OR RESOLVED EVIDENCE CONFLICTS THIS RUN: the conflicts closed in "
        "Brief 07 (user_scoping, squad_real_activity RESOLVED; squad_authorization "
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
        "Squad authorization is CONFIRMED UNCHANGED this run (via repo-wide "
        "diff-empty check) — unauthenticated list/leaderboard routes, no "
        "privacy enforcement despite a privacy field existing. A real trust/"
        "security gap, unresolved for 4 weeks of calendar time now, PROVISIONAL "
        "pending fresher product-source access.",
        "Database-level ownership integrity is CONFIRMED UNCHANGED this run — "
        "nullable columns, no foreign keys, under an application layer that assumes "
        "real scoping.",
        "The Directive Engine — the connective step in Vital Sync's own stated "
        "differentiation model between Alignment and Mission — is CONFIRMED "
        "absent this run (getTomorrowDirective() remains a fixed seed-indexed "
        "pool lookup, not Alignment-driven). Externally, Workout Quest shipped a "
        "recovery-aware AI chat this run, edging into adjacent territory.",
        "Training schema remains CONFIRMED shallow this run — unchanged since "
        "Brief 01 — against Strava's still-unmatched workout-log/muscle-map depth "
        "(no further Strava change found this run).",
        "The marketing/product mismatch (site says 'Coming Soon,' pricing "
        "undisclosed) is CONFIRMED UNCHANGED this run against the same commit — "
        "still unresolved, and the deployed site remains unreachable for an 8th "
        "consecutive check (both WebFetch and a direct curl attempt this run).",
        "Zero wearable integrations, per the last export — still the reason "
        "Alignment/Recovery have little real data to score; not independently "
        "re-grepped against the current commit this run. Competitive pressure on "
        "this gap keeps mounting: Vora added direct Oura/COROS/lift-import "
        "integrations this run.",
        "PRODUCT SOURCE ITSELF IS NOW STALE: the GitHub mirror has sat frozen for "
        "4 weeks across 4 confirmed check-ins (2026-09-14, 2026-09-21, "
        "2026-09-28, 2026-10-05), well past this workflow's threshold for "
        "downgrading confidence in it as a proxy for the real, possibly-"
        "Replit-only, current product state.",
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
        ("Recovery <-> Workout Recommendation", "NOT FOUND", "Unchanged in Vital "
         "Sync's own product — recovery state is computed but nothing "
         "downstream adjusts a workout recommendation. Externally notable this "
         "run: Workout Quest shipped an AI chat that answers mid-workout "
         "questions (e.g. whether to drop-set) against the user's recovery "
         "context — a competitor now shipping a version of exactly this "
         "connection, which Vital Sync's own product still lacks."),
        ("Progress <-> Program Adjustment", "NOT FOUND", "Unchanged — Boss Battles/"
         "Challenges are static content, not adjusted by Alignment or recovery state."),
    ],
    "competitor_watch": [
        ("Apple Health", "Indirect / Platform-scale", "NOT RE-CHECKED THIS WEEK — "
         "no new Apple Health development surfaced in this run's searches. "
         "Unchanged from last brief: a major Health app redesign announced "
         "2026-09-09 — a free Readiness score, a 'Health Age' computation, and "
         "a new AI Insights tab powered by Apple Intelligence delivering "
         "personalized, contextual wellness guidance from activity/sleep/other "
         "signals. No subscription required; ships to every iPhone/Apple Watch "
         "user later in 2026, starting in U.S. English. Still the single "
         "biggest platform-scale threat to Vital Sync's Recovery/Alignment "
         "value proposition found to date."),
        ("Vora", "Direct", "CHANGED THIS WEEK: a September 1, 2026 update "
         "(v3.3.11) added a direct Oura Cloud API integration — bypassing "
         "Apple Health entirely to pull Readiness Score, body-temperature "
         "deviation, granular sleep staging, and real-time HRV — plus "
         "Strong/Hevy/Fitbod lift-history import and a direct COROS connection, "
         "on top of its existing 500+ wearable integrations claim. This "
         "predates but was not caught in last week's check (which called Vora "
         "'confirmed unchanged'); it is a genuine cross-system data-"
         "consolidation move, closing Vora's data-supply gap further and ahead "
         "of Vital Sync on exactly the wearable-integration dimension Vital "
         "Sync still lacks entirely. Pricing unchanged ($12.99/mo, cross-page "
         "discrepancy with a lower-priced annual tier still UNVERIFIED-EXACT, "
         "as last brief)."),
        ("Cora", "Direct", "NOT RE-CHECKED THIS WEEK (surface-level watch only) "
         "— carried unchanged from last brief: strength + nutrition tracking, "
         "new widgets/Apple Watch complications, \"Body Charge\" HRV/sleep/"
         "training-load recovery score, wearable integrations (Apple Watch, "
         "Garmin, WHOOP, Oura)."),
        ("FitCraft", "Direct", "NOT RE-CHECKED THIS WEEK (surface-level watch "
         "only) — carried unchanged from last brief: multiple AI trainer "
         "personas, RPG-style progression (XP, leveling, collectible cards), "
         "diagnostic-assessment-driven programming. Still no nutrition/recovery "
         "features found."),
        ("Workout Quest", "Direct", "CHANGED THIS WEEK: a September 8, 2026 "
         "update added an 'AI-Powered Recovery Analysis' capability — the AI "
         "chat (previously just an 'AI-Fitness Chat' feature, tracked since "
         "Brief 09) can now answer mid-workout questions like 'should I drop "
         "set this next set' or 'incline or flat bench today' against the "
         "user's recovery context. This is a real mechanism deepening, not "
         "cosmetic — it moves toward the Recovery<->Workout-Recommendation "
         "connection Vital Sync's own cross-system audit still marks NOT FOUND. "
         "Whether the underlying model is genuinely LLM-backed is UNVERIFIED "
         "from search snippets alone. Still no nutrition tracking found."),
        ("Habitica", "Specialist", "RE-CHECKED this week: no mechanism change — "
         "only routine seasonal content (new Market items, October Subscriber "
         "Item) and a prior accessibility/UI update (Aug 17). Still pure RPG "
         "habit layer, cosmetic-only subscription, no fitness-specific "
         "programming."),
        ("Trainera / Bevel / NATE", "Direct (surface-level)", "Not re-checked this "
         "week (surface-level watch only) — carried unchanged from Brief 07."),
        ("WHOOP / Strava", "Specialist / Indirect", "MINOR CHANGE THIS WEEK: "
         "WHOOP 5.0 launched in India (~Oct 2, 2026, ₹21,990 with a 12-month "
         "membership) — a geographic expansion of an already-tracked device, "
         "not a new mechanism. No new Strava-specific change found this run; "
         "its $2.2B funding round and strength-training push (muscle maps, "
         "workout log, deepened WHOOP integration) remain unchanged from last "
         "brief."),
        ("Bitletics", "Emerging / Beta", "CHANGED THIS WEEK: its Q2/Q3 2026 "
         "launch window (Q3 ended 2026-09-30) has now LAPSED — this run's fresh "
         "searches found no evidence of an actual iOS/Android launch, only the "
         "same blog and comparison pages describing the pre-launch pitch (free "
         "at launch, no subscription, 30+ activity types, Apple Watch/heart-"
         "rate verified, weekly gift-card raffles). Sharpened from last week's "
         "'window about to lapse' flag to a confirmed miss — next brief should "
         "watch for either a real launch announcement or continued silence."),
        ("Google Health Premium (Gemini Health Coach, formerly Fitbit Premium)",
         "Indirect / Platform-scale",
         "NOT RE-CHECKED THIS WEEK beyond confirming the existing timeline: "
         "the Fitbit-to-Google-Health rebrand (May 19, 2026) and the Gemini "
         "Health Coach preview are unchanged from what this workflow has "
         "already tracked. No new expansion or feature found this run. Still a "
         "direct threat to the 'wearable-driven adaptive coaching' value "
         "proposition, not a gamification competitor."),
        ("RazFit", "Emerging / Live", "CHANGED THIS WEEK: shipped version 1.5.1 "
         "(~Oct 3, 2026) — a redesigned onboarding flow, refreshed Today plan, "
         "exercise library, profile, and every workout stage (prep/pause/"
         "complete/end), a new built-in music player (14 exclusive tracks, "
         "smart shuffle, Dynamic Island controls, floating mini-player), better "
         "Apple Watch sync and notifications, improved accessibility/Dynamic "
         "Type/iPad support, and expansion to 6 languages. Pricing unchanged "
         "(Weekly $2.99 / Annual $29.99). This is the third tracked update in "
         "under two months — a real, active development cadence, though scale/"
         "traction is still unconfirmed. Stays MONITOR/MEDIUM."),
        ("Gentler Streak", "Specialist / Indirect", "NOT RE-CHECKED THIS WEEK "
         "beyond a forward-looking note: per this run's searches, the team "
         "shipped a smaller technical/cosmetic update (map-style options, "
         "faster chart loading, a new app icon) and has signaled a deeper "
         "personalized-guidance layer — extending its 'how you feel' framing — "
         "is planned for 'towards the end of October' 2026. Not yet shipped; "
         "worth checking explicitly next run. Core positioning (fatigue-aware "
         "check-ins, no gamification) unchanged."),
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
        ("Weak first-week activation", "Not re-measured this week — carried "
         "forward unchanged: users who don't complete at least 3 workouts in "
         "their first week churn at 4-5x the rate of those who do (2026 "
         "fitness-app retention benchmarking)."),
        ("App fragmentation / 'too many apps'", "NEW THIS WEEK: users report "
         "juggling multiple separate apps when one doesn't sync with their "
         "wearable (Garmin/Fitbit/Strava), forcing manual re-entry — direct "
         "support for an all-in-one positioning like Vital Sync's, if the "
         "wearable gap (see opportunity #5) is closed. Separately, even "
         "Google's own Health rebrand (Fitbit -> Google Health) drew complaints "
         "about the new experience feeling 'clunky' — a reminder that "
         "platform-scale threats aren't automatically frictionless, which is a "
         "narrow opening, not a reason to relax on the gaps above."),
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
        "First-week activation is a named, measured lever — apps that get a user "
        "through 3 workouts in week one see 4-5x better retention than those that "
        "don't, per 2026 fitness-app benchmarking research. Not re-measured this "
        "week.",
        "NEW THIS WEEK: app-fragmentation complaints (not syncing with a user's "
        "existing wearable, forcing manual re-entry) surfaced directly in review "
        "search results — concrete evidence for the all-in-one pitch, contingent "
        "on closing the wearable-integration gap (opportunity #5).",
    ],
    "market_trends": [
        "Wearables are the retention lever — health monitoring has overtaken fitness "
        "tracking as the primary wearable use case; app-side integration is now table "
        "stakes for retention.",
        "Unchanged from last brief, not re-surfaced this week: Apple announced a "
        "free Health app redesign on 2026-09-09 (Readiness score, 'Health Age', "
        "Apple-Intelligence-powered AI Insights, no subscription), rolling out to "
        "every iPhone/Apple Watch user later in 2026, alongside reported Apple "
        "Fitness+ team layoffs (~2026-09-20/22) under new CEO John Ternus. Read "
        "together, this still looks like a platform giant shifting investment away "
        "from paid fitness subscription content and toward free, AI-driven health "
        "guidance baked into the OS — the exact category Vital Sync's Alignment "
        "engine competes in, now available free at platform scale.",
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
        "Consolidation and capital concentration continue — following the Strava/"
        "Runna, Garmin/TrainingPeaks, and MyFitnessPal/Cal AI moves already "
        "tracked, Strava itself raised new funding this run at a $2.2B valuation "
        "(Sequoia-led, with TCV, Jackson Square Ventures, and Go4it Capital), "
        "reinforcing that capital is concentrating in fewer, larger, AI-enabled "
        "players rather than spreading across boutique apps. Startup funding in "
        "fitness/wellness topped $3.6B in H1 2026 (on pace to run roughly a third "
        "higher than 2025) — WHOOP's $575M Series G (March 2026) and Strava's new "
        "round are the two largest single data points found across this and prior "
        "briefs. Raises the urgency of Vital Sync differentiating on cross-system "
        "Alignment intelligence before boutique positioning gets squeezed by "
        "bigger, AI-coaching-plus-hardware players — and that pressure is no "
        "longer purely hypothetical: Strava's own strength-training push (new "
        "workout log, muscle maps) and Cora's expansion into nutrition+strength "
        "logging (found this run) both move directly into territory Vital Sync "
        "claims as differentiating.",
        "Activation, not just retention, remains separately measured — users who "
        "don't complete 3 workouts in their first week churn 4-5x faster than those "
        "who do. Not re-measured this week.",
        "NEW THIS WEEK: multiple independent market-research sources describe "
        "continued double-digit growth for AI-driven fitness coaching specifically "
        "— figures range widely by source and methodology (e.g. one report puts "
        "the global fitness-app market at $17.71B in 2025 growing toward $22.36B "
        "in 2026; another projects the AI-fitness-app segment specifically reaching "
        "$26.67B by 2035 at a ~22.55% CAGR) — cited here as reported by third-party "
        "market-research publishers, UNVERIFIED/LIKELY rather than independently "
        "confirmed by this workflow, and not reconciled against each other given "
        "the methodology differences. Directionally consistent across every source "
        "checked: AI personalization is moving from differentiator to baseline "
        "expectation, and apps without it are increasingly described as legacy.",
        "NEW THIS WEEK: app-fragmentation (not syncing with a user's existing "
        "wearable) is a named complaint pattern, and even Google's own Health "
        "rebrand drew 'clunky' UX criticism — a reminder that platform-scale "
        "threats carry their own friction, a narrow opening rather than a reason "
        "to relax on Vital Sync's own open gaps.",
    ],
    "gap_types": [
        ("-", "Security/trust blocker, unresolved for 3 weeks, PROVISIONAL",
         "Squad authorization / privacy", "RE-CONFIRMED BROKEN this run: "
         "list/leaderboard routes still take no auth, no privacy filtering exists "
         "despite the field being present. Still the sharpest concrete Squad risk "
         "confirmed in the mirror, now aging without a fix."),
        ("-", "Foundational risk, unresolved for 3 weeks, PROVISIONAL", "Database "
         "ownership integrity", "RE-CONFIRMED BROKEN this run: ownership columns "
         "are still nullable with no foreign-key enforcement, underneath an "
         "application layer that assumes real per-user scoping."),
        ("-", "RESOLVED (was foundational blocker)", "Multi-user data scoping",
         "RE-CONFIRMED RESOLVED this run at the route level via fresh direct source "
         "read — was the top blocker through Brief 06."),
        ("A", "Vital Sync behind, gap widening further", "Recovery/Alignment DATA "
         "SUPPLY (not logic)", "The scoring algorithms are real and competitive-"
         "grade; Cora/Vora/Bevel/NATE win only because they have wearable data "
         "feeding equivalent logic. Unchanged from last brief at the platform "
         "level (Apple's free Health redesign, Google Health Premium). CHANGED "
         "THIS WEEK at the app level: Vora added a direct Oura Cloud integration "
         "plus Strong/Hevy/Fitbod lift import and a COROS connection, widening "
         "its own data-supply lead. Vital Sync's engine still has zero wearable "
         "connections — the gap keeps widening, not holding steady."),
        ("A", "Vital Sync behind, PROVISIONAL", "Directive Engine", "CONFIRMED "
         "ABSENT this run via a repo-wide diff-empty check (no fresh file read "
         "needed — getTomorrowDirective()'s seed-pool-lookup implementation was "
         "directly read on 2026-09-28 and the mirror has not moved since): no "
         "executable Directive Engine or Alignment-to-mission connection exists. "
         "Competitors don't have this either, but it's Vital Sync's own stated "
         "differentiation model, so the gap is self-inflicted, not just "
         "competitive. CHANGED THIS WEEK, externally: Workout Quest shipped a "
         "recovery-aware AI chat — a competitor now shipping a version of the "
         "Recovery<->Recommendation connection this gap depends on."),
        ("A", "Vital Sync behind, gap holding", "Training depth", "CONFIRMED "
         "still shallow this run via a repo-wide diff-empty check (four-field "
         "schema, no sets/reps/weight, last directly read 2026-09-28). No new "
         "Strava change found this week — the gap holds at last week's widened "
         "level rather than widening further."),
        ("B", "Parity, competitors converging faster", "Core gamification (XP, "
         "streaks, badges) + 'AI coach' claim", "Table stakes in this niche — "
         "FitCraft, Workout Quest, Habitica match or exceed on raw mechanics "
         "depth. CHANGED THIS WEEK: Workout Quest deepened its AI chat into "
         "recovery-aware territory — the 'has an AI coach' claim keeps "
         "converging toward parity industry-wide and is now starting to add "
         "real depth, not just a chat UI (genuineness of the underlying model "
         "still UNVERIFIED); Vital Sync's real GPT-4o-mini coach needs its "
         "context-depth advantage made visible, not just claimed."),
        ("C", "Vital Sync ahead (once real), PROVISIONAL", "Alignment engine + AI "
         "chat coach + real Squad activity", "The underlying engineering is "
         "genuinely competitive-grade, and Squads' activity remains confirmed "
         "real, not simulated. Gap is data supply, the missing Directive layer, "
         "and Squad authorization — not algorithm quality."),
        ("D", "Open market gap, edging narrower from the data side", "Fatigue-"
         "aware gamification", "Nobody in the tracked competitive set ties "
         "streak/reward mechanics to real recovery data. CHANGED THIS WEEK: "
         "Workout Quest's new recovery-aware AI chat is a small step toward "
         "fatigue-aware guidance, though still with no gamification layer "
         "fused to it; Gentler Streak remains the closest full precedent and "
         "has signaled a deeper 'how you feel' guidance layer for late October "
         "(not yet shipped). Still confirmed to depend on the Directive Engine "
         "existing first — don't build this before that."),
    ],
    "opportunities": [
        # (rank, title, evidence, bucket, gap, ai, confidence)
        (1, "Fix Squad authorization / privacy [PROVISIONAL — see Product Source "
         "Freshness]", "CONFIRMED UNCHANGED this run via a repo-wide diff-empty "
         "check (not a fresh file read): GET /squads and GET /squads/leaderboard "
         "have no auth check and no privacy filtering. A real access-control "
         "gap, not cosmetic, unresolved for 4 weeks of calendar time now. "
         "PROVISIONAL only because the GitHub mirror is now STALE-classified — "
         "the finding itself is unchanged.",
         "BUILD NOW", "-", "No AI Needed", "HIGH"),
        (2, "Enforce database-level ownership [PROVISIONAL — see Product Source "
         "Freshness]", "CONFIRMED UNCHANGED this run via a repo-wide diff-empty "
         "check: nullable ownership columns, no foreign keys, underneath a "
         "now-real application-level scoping layer, unresolved for 4 weeks of "
         "calendar time now.",
         "BUILD NOW", "-", "No AI Needed", "HIGH"),
        (3, "Build the Alignment -> Directive -> Mission connection [PROVISIONAL — "
         "see Product Source Freshness]", "CONFIRMED ABSENT this run via a "
         "repo-wide diff-empty check against the commit where "
         "getTomorrowDirective()'s implementation was last directly read "
         "(2026-09-28): a fixed `pool[seed % length]` lookup, not "
         "Alignment-driven, and missions are still chosen by onboarding-weighted "
         "randomness. The connective step in Vital Sync's own differentiation "
         "model still doesn't exist. Externally, Workout Quest shipped a "
         "recovery-aware AI chat this run — a reminder the market is starting "
         "to move into this exact territory.",
         "BUILD NOW", "A", "AI Assisted", "HIGH"),
        (4, "Fix the marketing/product mismatch [PROVISIONAL — see Product Source "
         "Freshness]", "CONFIRMED UNCHANGED via a repo-wide diff-empty check "
         "against the same 0435f9ea commit for a fourth consecutive run: "
         "landing.tsx still shows two 'Coming Soon' badges and 'Pricing will be "
         "announced before launch,' per the 2026-09-28 direct read. "
         "vitalsyncify.com itself remains unreachable (8th consecutive check, "
         "EGRESS_BLOCKED on both WebFetch and a direct curl attempt this run) — "
         "a human manually checking the live deployed site would close this gap "
         "fastest.",
         "BUILD NOW", "Trust", "No AI Needed", "HIGH"),
        (5, "Connect Apple Health as first wearable", "Broadest reach, lowest "
         "effort; feeds the already-working Alignment/Recovery algorithms with "
         "real data. Unchanged at BUILD NOW this run — no new Apple Health "
         "development surfaced, but the underlying case (Apple's free "
         "2026-09-09 Health redesign: Readiness score + AI Insights, no "
         "subscription, every iPhone/Watch user) stands as last week. New "
         "urgency this run from a different angle: Vora (a direct competitor) "
         "added a direct Oura Cloud integration plus lift-history import and a "
         "COROS connection, showing a competitor can move fast on wearable "
         "consolidation even without owning the OS layer. Not reverified "
         "against Vital Sync's own source this run beyond the repo-wide "
         "diff-empty check — wearables remain absent per the last export.",
         "BUILD NOW", "A", "No AI Needed", "HIGH"),
        (6, "Surface the real AI chat coach more prominently, and widen its context",
         "/coach/message is live GPT-4o-mini — its context excludes Alignment/"
         "Recovery/workout/nutrition data (confirmed Brief 07, not reverified this "
         "run). Newly urgent again: Workout Quest deepened its own AI chat into "
         "recovery-aware territory this run (genuineness UNVERIFIED), so the "
         "'has an AI coach' claim is converging toward parity and starting to "
         "gain real depth elsewhere — Vital Sync's real, already-working "
         "GPT-4o-mini integration needs its context-depth advantage made "
         "visible and real, not just claimed. Two separate improvements: "
         "visibility, and context depth.",
         "BUILD NEXT", "C", "AI Core", "MEDIUM"),
        (7, "Real training depth (sets/reps/weight/overload) [PROVISIONAL — see "
         "Product Source Freshness]", "CONFIRMED unchanged this run via a "
         "repo-wide diff-empty check: workouts table still has no sets/reps/"
         "weight fields at all, per the 2026-09-28 direct read. No new Strava "
         "change found this week — the competitive gap holds at last week's "
         "widened level.",
         "BUILD NEXT", "A", "No AI Needed", "HIGH"),
        (8, "Fatigue-aware streak mechanic", "Streak downgrades gracefully instead of "
         "breaking, when real recovery data is low. Still confirmed to depend on "
         "the Directive Engine (#3) and wearables (#5) landing first — do not build "
         "before those. Market validation extended this week: Workout Quest's new "
         "recovery-aware AI chat is a small step in this direction, and Gentler "
         "Streak has signaled a deeper 'how you feel' guidance layer planned for "
         "late October (not yet shipped) — still the closest real-world "
         "precedent found, but neither changes the internal dependency order.",
         "EXPERIMENT", "D", "AI Assisted", "MEDIUM"),
        (9, "Full nutrition goals (carbs/fat)", "Protein/water/calorie targets exist; "
         "carbs/fat still missing. Not reverified this run.",
         "IMPROVE EXISTING", "A", "AI Assisted", "MEDIUM"),
        (10, "Voice / natural-language logging", "Vora and Cora both lead with this; "
         "large build effort, competitors have a head start. Not reverified this run.",
         "MONITOR", "A", "AI Core", "MEDIUM"),
        (11, "Track Bitletics' real-reward redemption model", "Converts activity into "
         "redeemable in-game loot/raffle tickets rather than only in-app XP/badges — "
         "a genuinely different reward mechanic than any of the 5 deep-dived "
         "competitors. CHANGED THIS WEEK: its Q2/Q3 2026 window (Q3 ended "
         "Sept 30) has now LAPSED — fresh searches this run found no evidence "
         "of an actual launch, only the same pre-launch blog/comparison pages. "
         "Sharpened from 'about to lapse' to a confirmed miss. Next brief should "
         "watch for either a real launch announcement or continued silence.",
         "MONITOR", "D", "No AI Needed", "LOW"),
        (12, "Monitor Google Health Premium's Gemini Coach as a platform-scale threat, "
         "not a build target", "Formerly Fitbit Premium — NOT RE-CHECKED beyond "
         "confirming the existing timeline this run: no new expansion or feature "
         "found. Google ships the same 'wearable data -> adaptive recovery/"
         "training guidance' output Vital Sync's Alignment engine produces, at "
         "a growing distribution scale. Not something Vital Sync can out-build "
         "directly; sharpens the case for #5 (connect a wearable) and for "
         "leaning on cross-system Alignment (training+nutrition+recovery "
         "together) as the differentiator Google doesn't offer.",
         "MONITOR", "A", "No AI Needed", "MEDIUM"),
        (13, "Track RazFit as a low-friction, short-session entrant", "CHANGED THIS "
         "WEEK: shipped version 1.5.1 — redesigned onboarding/Today-plan/"
         "exercise-library/profile flow, a built-in music player, better Apple "
         "Watch sync, and expansion to 6 languages. Pricing unchanged (Weekly "
         "$2.99 / Annual $29.99). Third tracked update in under two months — a "
         "real, active development cadence. Still 1-10 minute equipment-free "
         "bodyweight sessions with a badge reward system, \"consistency over "
         "intensity\" positioning. Scale/traction still unconfirmed.",
         "MONITOR", "D", "No AI Needed", "MEDIUM"),
        (14, "Track Gentler Streak's fatigue-aware check-in mechanic", "NOT "
         "RE-CHECKED beyond a forward-looking note this week: a smaller "
         "technical/cosmetic update shipped (map styles, faster charts, new "
         "icon), and the team has signaled a deeper 'how you feel' guidance "
         "layer planned for late October 2026 (not yet shipped) — on top of "
         "its already-tracked 'Morning Check-In Notifications.' $8.99/mo or "
         "$39.99/yr, no gamification layer at all. Relevant to #8 as market "
         "validation, not as a feature to copy directly.",
         "MONITOR", "D", "No AI Needed", "MEDIUM"),
        (15, "Track BodBot's computer-vision rep-counting / form-check mode",
         "NEW THIS WEEK: BodBot shipped a camera-based 'Camera Workout Mode' "
         "(beta, Sept 9 2026) that counts reps, tracks sets, and coaches form "
         "in real time via the phone camera, then reports rep speed/range-of-"
         "motion/fatigue after each set. A concrete instance of the computer-"
         "vision-coaching trend already flagged in Market Trends as absent from "
         "Vital Sync's surface and from every other tracked competitor. Not a "
         "direct gamification competitor; worth watching as a possible future "
         "low-friction-logging angle, not an immediate build.",
         "MONITOR", "A", "AI Core", "LOW"),
    ],
    "opportunity_movement": [
        "#1, #2, #3, #4 (BUILD NOW) — UNCHANGED IN RANK, CONFIRMED UNCHANGED for "
        "a fourth consecutive run, still PROVISIONAL: the GitHub mirror "
        "(0435f9ea, still unmoved) is now 4 consecutive checks into its STALE "
        "classification (see Product Source Freshness). This run confirmed via "
        "a repo-wide `git diff --stat` (zero changed files across the entire "
        "tree) rather than re-reading squads.ts/profile.ts/schema files/"
        "landing.tsx line-by-line again — a stronger, full-repository guarantee "
        "of byte-identity, though not a fresh semantic read. The bucket "
        "assignment (BUILD NOW) doesn't change; the provisional caveat holds, "
        "now sharper after a 4th straight frozen week.",
        "#5 (Connect Apple Health as first wearable) — STAYS BUILD NOW/HIGH, no "
        "rank change. No new Apple Health development surfaced this run; the "
        "underlying case stands unchanged from last week. New, separate urgency "
        "found this run: Vora (a direct competitor) added a direct Oura Cloud "
        "integration plus lift-history import and a COROS connection — evidence "
        "that wearable-data consolidation is achievable without owning the OS "
        "layer, which is exactly what Vital Sync would need to do here. Vital "
        "Sync's own wearables status was not independently re-grepped this run "
        "— carried from the last export.",
        "#6 (Surface + widen AI coach context) — STILL BUILD NEXT/MEDIUM, evidence "
        "sharpened again: Workout Quest deepened its AI chat into recovery-aware "
        "territory this run (genuineness UNVERIFIED), meaning the bare claim of "
        "having an AI coach is not just converging toward parity but starting to "
        "gain real depth elsewhere — raises the value of proving out Vital "
        "Sync's real GPT-4o-mini integration's context depth.",
        "#7 (Real training depth) — UNCHANGED bucket, CONFIRMED unchanged again "
        "this run via the repo-wide diff check (still four fields, no sets/reps/"
        "weight), still PROVISIONAL for the same mirror-staleness reason as "
        "#1-4. No new Strava change found this week — competitive gap holds at "
        "last week's widened level rather than widening further.",
        "#8 (Fatigue-aware streak mechanic, EXPERIMENT) — UNCHANGED bucket, "
        "evidence extended in a new direction: Workout Quest's recovery-aware AI "
        "chat is a small step toward this mechanic from a different competitor "
        "than Gentler Streak, which has separately signaled a deeper 'how you "
        "feel' layer for late October (not yet shipped). Still gated on the "
        "Directive Engine (#3) and wearables (#5) landing first — new evidence "
        "strengthens the market case, not the internal readiness, so the bucket "
        "doesn't move.",
        "#11 (Track Bitletics, MONITOR) — NOT RE-RANKED, still LOW confidence, "
        "evidence sharpened: its Q2/Q3 2026 window (Q3 ended Sept 30) has now "
        "LAPSED — fresh searches this run found no evidence of an actual launch. "
        "Sharpened from last week's 'about to lapse' flag to a confirmed miss.",
        "#12 (Google Health Premium, MONITOR) — NOT RE-RANKED; no new expansion "
        "found this run beyond confirming the existing timeline. Stays "
        "MONITOR/MEDIUM — sharpens the case for #5, not a build target itself.",
        "#13 (Track RazFit, MONITOR) — NOT RE-RANKED, confidence holds at "
        "MEDIUM: shipped version 1.5.1 this run (redesigned onboarding/workout "
        "flow, music player, 6-language expansion) — its third tracked update "
        "in under two months, a real active-development signal, though scale/"
        "traction remains unconfirmed so confidence doesn't move further yet.",
        "#14 (Track Gentler Streak, MONITOR) — NOT RE-RANKED, evidence extended: "
        "a smaller update shipped this run (map styles, faster charts, new "
        "icon) and a deeper 'how you feel' guidance layer is signaled for late "
        "October (not yet shipped) — worth an explicit check next brief. Still "
        "MONITOR/MEDIUM — tracked as market validation for #8, not a threat in "
        "its own right.",
        "#9, #10 (nutrition goals, voice logging) — UNCHANGED, not reverified this "
        "run.",
        "NEW THIS RUN: #15 (Track BodBot's computer-vision rep-counting/form-"
        "check mode, MONITOR/LOW) added — a concrete instance of the computer-"
        "vision-coaching trend already flagged in Market Trends, not previously "
        "tracked as a named competitor feature.",
        "NO ITEMS RESOLVED, REMOVED, OR MOVED BUCKETS THIS RUN. What changed "
        "most this week is the competitor/market layer (Vora's wearable "
        "consolidation, Workout Quest's recovery-aware AI chat, RazFit's 1.5.1 "
        "update, Bitletics' window lapsing, BodBot's new-entrant discovery) "
        "rather than any change in Vital Sync's own product-state findings, "
        "which were all confirmed unchanged via the repo-wide diff check — "
        "every product-state-dependent item (#1-4, #7, #8, gap type A/C rows) "
        "still carries its provisional caveat, now one week older.",
    ],
    "sources": [
        "github.com/faristjohar04-sketch/Vital-Sync — RE-CHECKED this run via "
        "`git log`/`git diff` against both the locally stored commit "
        "(0435f9ea79a871cd1578e2dc22e8e3055bebc50e) and a fresh `origin/main` "
        "fetch — both empty. This is the 4th confirmed-unchanged check since "
        "Brief 07's 2026-09-07 advance (2026-09-14, 2026-09-21 via PR #2, "
        "2026-09-28, 2026-10-05). `main` already carried PR #3's merge before "
        "this run started, so no PR was found stuck unmerged this time.",
        "github.com/faristjohar04-sketch/Vital-Sync @ 0435f9ea — NOT "
        "independently re-read file-by-file this run. Given 4 straight "
        "byte-identical confirmations at this exact commit, this run instead "
        "ran a repo-wide `git diff --stat` against the 2026-09-28 commit (zero "
        "changed files across the entire tree) — a stronger, full-repository "
        "guarantee of identity than a selective re-read, but not a fresh "
        "semantic read of profile.ts/squads.ts/workouts.ts/landing.tsx/"
        "getTomorrowDirective(). Every area resting on those files is marked "
        "UNCHANGED — VERIFIED via this diff-empty method, with the 2026-09-28 "
        "direct read cited as the underlying evidence.",
        "vital_sync_current_product_state.json — a structured audit export "
        "provided by the user on 2026-09-07/08, cross-checked against the commit "
        "above in Brief 07's run. No newer export has been provided in the four "
        "runs since; areas resting solely on it are marked UNCHANGED — NOT "
        "REVERIFIED in this brief's Current State table, now four weeks old.",
        "https://vitalsyncify.com — attempted directly this run via both "
        "WebFetch and a direct curl through the sandbox network proxy: "
        "EGRESS_BLOCKED on both, the 8th consecutive check this has failed from "
        "this sandbox. Logged as SOURCE_UNAVAILABLE for the marketing-mismatch "
        "check, not treated as evidence of 'no marketing changes.'",
        "WebSearch (this run, competitor/market refresh): Vora's official blog "
        "(askvora.com) and Play Store listing (v3.3.11 update, Oura/COROS/"
        "Strong/Hevy/Fitbod integrations); Workout Quest's Google Play listing "
        "and blog (AI-Powered Recovery Analysis, Sept 8 2026); RazFit's App "
        "Store listing (version 1.5.1); WHOOP press materials and Indian tech "
        "press (telecomtalk.info) for the WHOOP 5.0 India launch; Bitletics' own "
        "blog and store pages (no launch evidence found); Habitica's release "
        "notes and blog (routine content only); Apple Newsroom/TechCrunch and "
        "Google/blog.google coverage of Google Health (re-confirmed unchanged "
        "timeline, no new development); Gentler Streak's App Store listing and "
        "coverage of its planned late-October update; BodBot's Google Play "
        "listing (Camera Workout Mode beta); general market-trend and "
        "fitness-app-complaint searches for the app-fragmentation finding and "
        "AI-fitness-market growth figures — direct WebFetch to competitor "
        "domains and most news domains remains EGRESS_BLOCKED in this sandbox "
        "(confirmed again this run against androidauthority.com, "
        "press.strava.com, and apple.com), so WebSearch snippets were used "
        "throughout, as in prior briefs.",
        "Cora, FitCraft, Strava, Apple Health, Google Health Premium — "
        "surface-level watch only this run (no new development found in quick "
        "checks); carried forward unchanged from Brief 09.",
        "Habitica, Trainera/Bevel/NATE — surface-level watch only, carried "
        "forward unchanged from Brief 07/09.",
        "Customer pain/praise clusters and churn/retention benchmarks were "
        "partially refreshed this run (app-fragmentation complaint pattern, "
        "AI-fitness-market growth figures) — the remaining clusters and figures "
        "from Brief 08 are carried forward unchanged, not re-derived from memory.",
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
