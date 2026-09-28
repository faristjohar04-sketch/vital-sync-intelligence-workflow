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
# THIS WEEK'S DATA — Brief 09, compiled 2026-09-28. IMPORTANT: there was no
# automated run on 2026-09-21 (a full weekly cycle was skipped; cause not
# investigated by this run — worth a human checking the trigger/scheduler
# config). The GitHub mirror has therefore sat frozen at 0435f9ea for 3
# calendar weeks but only 2 actual check-ins (2026-09-14, 2026-09-28) have
# observed it unchanged — which nonetheless meets this workflow's 2+-
# consecutive-runs threshold, so the mirror is reclassified STALE this run
# (see Product Source Freshness, auto-rendered from
# vital_sync_product_state.json). Per the freshness gate, every product-
# state-dependent recommendation below is explicitly PROVISIONAL this week
# — re-verified against the mirror, but the mirror's standing as a proxy for
# the real (possibly Replit-only) product state is unconfirmed. Competitor/
# market sections are refreshed via WebSearch and are NOT gated by Layer A
# freshness; several real competitor changes were found this run.
# ---------------------------------------------------------------------------
WEEK_DATA = {
    "report_date": "2026-09-28",
    "run_label": "Brief 09 — GitHub mirror RECLASSIFIED STALE (2nd consecutive unchanged check at 0435f9ea meets the 2+-run threshold; note a 2026-09-21 run was missed); all three top BUILD NOW findings (Squad authorization, database integrity, Directive Engine) RE-VERIFIED unfixed for 3 weeks of calendar time, now PROVISIONAL pending fresher product-source access; competitor refresh finds real changes at Cora, FitCraft, Workout Quest, Gentler Streak, RazFit, and Strava",
    "exec_summary": (
        "PRODUCT SOURCE FRESHNESS DOWNGRADED TO STALE THIS RUN — see the warning "
        "banner in the Product Source Freshness section below; all product-build "
        "recommendations in this report are provisional. Repository state and "
        "product state continue to be reported as two separate facts, per the "
        "2026-09-07 repair. Note first: no automated run fired on 2026-09-21, so "
        "this is a 2-calendar-week gap since Brief 08, not a normal weekly cycle "
        "(worth a human checking the trigger/scheduler configuration). The GitHub "
        "mirror's HEAD commit (0435f9ea) has still not moved — `git log`/`git diff` "
        "against both the locally stored commit and a fresh `origin/main` fetch both "
        "came back empty, a fresh clone confirmed the same HEAD and commit date. "
        "This is the 2nd confirmed-unchanged check since the mirror's 2026-09-07 "
        "advance, which meets this workflow's 2+-consecutive-runs threshold for "
        "reclassifying a frozen commit STALE — not because anything was read "
        "incorrectly, but because a mirror frozen for 3 weeks is no longer a "
        "confirmed-current proxy for a product the user has previously reported "
        "being worked on directly in Replit. Rather than stop at 'no diff,' the "
        "actual source was independently re-read a third time at this same commit: "
        "Squad list/leaderboard authorization is still CONFIRMED BROKEN in the "
        "mirror (GET /squads and GET /squads/leaderboard still take an unused "
        "request parameter, still no privacy filtering), database-level ownership "
        "integrity is still CONFIRMED BROKEN (clerkId/userId columns still "
        "nullable, no foreign keys), the Directive Engine is still CONFIRMED "
        "ABSENT (a fresh grep found 'directive' only as narrative/UI copy; this "
        "run additionally read getTomorrowDirective()'s actual implementation and "
        "confirmed it is a fixed seed-indexed pool lookup, not Alignment-driven "
        "selection), and training depth is still CONFIRMED SHALLOW (same four-"
        "field workouts schema). The marketing/product mismatch (landing.tsx still "
        "shows 'Coming Soon' and undisclosed pricing) is likewise reconfirmed "
        "unchanged in the mirror. All of these findings are therefore accurate "
        "descriptions of the mirror as of today, but — per the STALE "
        "reclassification — carry a live, acknowledged risk that the real product "
        "in Replit has since diverged further. vitalsyncify.com itself remains "
        "unreachable from this sandbox for a 7th consecutive check "
        "(EGRESS_BLOCKED, logged as SOURCE_UNAVAILABLE, not as 'no marketing "
        "changes'). Competitor and market research, independent of Layer A "
        "freshness, was refreshed this run and found several real changes: Cora "
        "expanded into strength and nutrition logging (closing distance toward a "
        "full training+nutrition+recovery loop, on top of its existing wearable "
        "integrations), FitCraft shipped multiple new AI trainer personas (beyond "
        "just 'Ty'), Workout Quest added an 'AI-Fitness Chat' feature, Gentler "
        "Streak shipped an iOS 27 update adding Siri App Intents and On-Screen "
        "Awareness support on top of its already-tracked fatigue-aware Morning "
        "Check-In notifications, RazFit's ongoing subscription price is now "
        "CONFIRMED ($2.99/week or $29.99/year, resolving a previously-UNKNOWN "
        "gap), and Strava raised new funding at a $2.2B valuation (Sequoia-led) "
        "while continuing to push into structured strength training (new workout "
        "log, muscle maps, expanded WHOOP integration). Bitletics remains "
        "pre-launch with no ship date found — its Q2/Q3 2026 window (Q3 ends "
        "2026-09-30) expires in 2 days as of this report, with nothing shipped."
    ),
    "top_actions": [
        ("Fix Squad authorization / privacy — RE-VERIFIED, unfixed for 3 weeks, PROVISIONAL",
         "RE-CONFIRMED BROKEN in the mirror by fresh direct source read: "
         "GET /squads and GET /squads/leaderboard still accept no authentication "
         "(unused request parameter) and still return every active squad with zero "
         "privacy filtering, even though the squads table has a privacy column. No "
         "admin/owner role, no invite flow. Still the sharpest concrete trust/"
         "security gap in the product. Flagged PROVISIONAL this run only because "
         "the mirror itself is now STALE-classified (3 weeks frozen) — not because "
         "the finding is in doubt at this commit."),
        ("Enforce database-level ownership — RE-VERIFIED, unfixed for 3 weeks, PROVISIONAL",
         "RE-CONFIRMED BROKEN by fresh direct source read: profileTable.clerkId and "
         "workoutsTable.userId are still nullable text columns with no foreign-key "
         "constraints, by explicit design comment ('nullable for pre-scoping rows'). "
         "Route-level scoping remains real, but nothing in the database itself "
         "enforces it — a determined bad actor or a future bug could still write "
         "cross-user data."),
        ("Build the Alignment -> Directive -> Mission connection — RE-VERIFIED, "
         "unfixed for 3 weeks, PROVISIONAL",
         "RE-CONFIRMED ABSENT by a fresh full-source grep, and this run additionally "
         "read getTomorrowDirective()'s actual implementation directly: it is "
         "`TOMORROW_DIRECTIVE_POOL[seed % pool.length]` — a fixed pool lookup, not "
         "Alignment-driven selection. No Directive Engine, no directive schema "
         "exists anywhere in the mirror — missions are still chosen by onboarding-"
         "weighted randomness. Still the clearest gap in Vital Sync's own stated "
         "differentiation model (Training + Nutrition + Recovery -> Alignment -> "
         "Directive -> Mission -> Execution -> Progress -> Feedback)."),
    ],
    "biggest_threat": (
        "Broadened this run beyond a single competitor — platform- and capital-"
        "scale pressure is compounding. Google's Gemini-powered Google Health "
        "Premium ($9.99/mo, reads HRV/sleep/activity-load, generates adaptive "
        "recovery-and-training guidance) is confirmed unchanged, no new expansion "
        "found. Separately, Strava raised new funding at a $2.2B valuation "
        "(Sequoia-led, found this run) while pushing further into structured "
        "strength training (new workout log, muscle maps, expanded WHOOP "
        "integration) — a direct incursion into the training-depth territory "
        "where Vital Sync is confirmed weakest. WHOOP's $575M Series G (March "
        "2026) reinforces the same pattern: capital keeps flowing to platform-"
        "scale wearable/AI-coaching plays, not gamification-first apps like "
        "Vital Sync."
    ),
    "biggest_gap": (
        "Unchanged in kind, sharpened further this run — nobody in the "
        "competitive set ties streak/gamification mechanics to real fatigue data. "
        "Gentler Streak shipped an iOS 27 update (Siri App Intents, On-Screen "
        "Awareness) on top of its already-tracked fatigue-aware Morning Check-In "
        "notifications — still the closest real-world precedent, still with no "
        "XP/streak-reward layer to fuse it to. Separately, Cora's expansion into "
        "strength + nutrition logging (found this run) means a second competitor "
        "is now closing in on Vital Sync's full training+nutrition+recovery loop "
        "claim, from the data-supply side rather than the gamification side. On "
        "the product side, Vital Sync's own Directive Engine (re-confirmed absent "
        "this run, PROVISIONAL per the STALE mirror) remains the prerequisite for "
        "doing any of this well."
    ),
    "biggest_weakness": (
        "Unchanged in substance, now 3 weeks old with no fix and PROVISIONAL "
        "pending fresher product-source access: Squad authorization is "
        "RE-CONFIRMED BROKEN (unauthenticated list/leaderboard, no privacy "
        "enforcement) and database-level ownership integrity is RE-CONFIRMED "
        "BROKEN (nullable, unenforced foreign keys) — both re-verified by fresh "
        "direct source read against the same commit. Per-user scoping at the "
        "route level remains genuinely fixed underneath these two open gaps."
    ),
    "biggest_advantage": (
        "Unchanged — the Alignment engine and the real GPT-4o-mini coach chat "
        "remain genuinely well-built, and the VAPID private-key concern remains "
        "resolved (server-side only, no exposure found). Not reverified line-by-"
        "line this run; no evidence surfaced that would change this assessment. "
        "Worth watching: Workout Quest added an 'AI-Fitness Chat' feature and "
        "FitCraft added multiple AI trainer personas this run — neither confirmed "
        "to be genuinely LLM-backed versus scripted (UNVERIFIED specificity), but "
        "the 'AI coach' claim is no longer differentiating on its own; depth of "
        "context is what would keep Vital Sync ahead, and that context depth is "
        "still the open gap (see ai_coach_context)."
    ),
    "one_to_ignore": (
        "Same guidance as prior briefs — chasing deeper RPG mechanics (pets, "
        "gear, cosmetic avatars), and copying RazFit's or Bitletics' formats "
        "directly (Bitletics still hasn't shipped, with its launch window now "
        "expiring within days — see Competitor Changes). Still not worth doing "
        "yet: building the fatigue-aware streak mechanic or any Directive-Engine-"
        "adjacent feature before the Directive Engine itself exists, re-confirmed "
        "absent again this run. The dependency order matters; sequencing work on "
        "top of a foundation that isn't there yet just creates more to redo later."
    ),
    "vital_sync_current_state": [
        ("Multi-User / Data Scoping", "PARTIAL", "RE-VERIFIED this run by direct "
         "source read at the unchanged (now STALE-classified) commit: "
         "getOrCreateProfile(userId) and equivalents still filter WHERE "
         "clerkId/userId = the authenticated user. Database-level enforcement is "
         "separately BROKEN — see next row."),
        ("Database Integrity", "BROKEN", "RE-VERIFIED this run, still unfixed for "
         "3 weeks of calendar time: ownership columns (profileTable.clerkId, "
         "workoutsTable.userId) are nullable with no NOT NULL constraint and no "
         "foreign keys, by explicit design comment. Route-level scoping is real; "
         "the database itself still doesn't enforce it."),
        ("Engagement / Gamification", "LIVE", "XP, Levels, Identity Ranks, Discipline "
         "Score, streaks + streak-freeze, 15 badges, 4 Boss Battles, 4 default 30-day "
         "Challenges. Not reverified in detail this run beyond the Squads rows below."),
        ("Squads — Real Activity", "COMPLETE", "RE-VERIFIED this run: a full grep "
         "for getGhostCompletions/seededRand/ghost across the api-server source "
         "returned zero matches. Stats still derive from real memberships and real "
         "mission/workout rows."),
        ("Squads — Authorization / Privacy", "BROKEN", "RE-VERIFIED this run, still "
         "unfixed for 3 weeks of calendar time: GET /squads and GET "
         "/squads/leaderboard still have no auth check and return all squads with "
         "no privacy filtering despite a privacy column existing. No invite flow, "
         "no owner/admin role logic."),
        ("Nutrition", "PARTIAL", "Meal logging works (name/cals/macros). Protein + "
         "water + a nullable calorie target exist; no carb/fat targets. Not "
         "reverified against the current commit this run — carried from Brief 07."),
        ("Training", "PARTIAL / SHALLOW", "RE-VERIFIED this run: schema is still "
         "name/duration/type/notes only (plus the nullable userId column) — no "
         "sets/reps/weight/progressive-overload fields, unchanged since Brief 01. "
         "Competitive gap widened this run: Strava's continued strength-training "
         "push (new workout log, muscle maps) is real depth Vital Sync's schema "
         "cannot currently express."),
        ("Recovery", "PARTIAL", "Real multi-factor log feeding a genuine weighted "
         "algorithm — not reverified against the current commit this run, carried "
         "from Brief 02/07's finding since it wasn't re-checked this cycle."),
        ("Cross-System Intelligence (Alignment)", "PARTIAL", "Algorithm confirmed real "
         "since Brief 02 (weighted training/nutrition/recovery composite). Its output "
         "still does NOT feed into mission/directive selection — see Directive "
         "Engine row, re-verified this run."),
        ("Directive Engine", "MISSING", "RE-VERIFIED this run by a fresh full-source "
         "grep, plus a direct read of getTomorrowDirective()'s implementation: it "
         "is a fixed `pool[seed % length]` lookup, not Alignment-driven. No "
         "executable Directive Engine, directive schema, or Alignment-to-mission "
         "connection exists anywhere. Missions are still chosen by onboarding-"
         "weighted randomness. \"Directive\" appears only as UI/narrative copy."),
        ("AI — ambient brief", "PROTOTYPE", "Not reverified against the current "
         "commit this run — carried from Brief 02's finding (templated, no model "
         "call)."),
        ("AI — chat coach", "LIVE", "Real GPT-4o-mini confirmed since Brief 02. Not "
         "reverified this run — context still known (from Brief 07's export) to "
         "include profile/streak/mission data but not Alignment, Recovery, workout, "
         "or nutrition data. Competitive backdrop: Workout Quest and FitCraft both "
         "added new AI-branded coach features this run (UNVERIFIED whether "
         "genuinely LLM-backed) — the 'has an AI coach' claim alone is no longer "
         "distinguishing; context depth would be."),
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
        ("Marketing / Product Alignment", "MISMATCH", "RE-VERIFIED at the same "
         "0435f9ea commit for a third consecutive run: landing.tsx still shows two "
         "'Coming Soon' badges and 'Pricing will be announced before launch.' "
         "vitalsyncify.com itself remains unreachable (7th consecutive check, "
         "EGRESS_BLOCKED)."),
    ],
    "changes_this_week": [
        "REPOSITORY STATE RECLASSIFIED STALE: the GitHub mirror's HEAD (0435f9ea) "
        "has still not moved — `git log`/`git diff` against both the stored commit "
        "and a fresh `origin/main` fetch both came back empty, and a fresh clone "
        "confirmed the same commit and commit date. This is the 2nd confirmed-"
        "unchanged check since the mirror's 09-07 advance, which meets this "
        "workflow's 2+-consecutive-runs threshold — the mirror moves from "
        "CURRENT_VERIFIED to STALE this run. NOTE: no run fired on 2026-09-21, so "
        "this reflects 3 calendar weeks of no movement observed across 2 actual "
        "check-ins, not a clean weekly cadence. Repository state and product state "
        "are reported separately, per the repair: STALE means the mirror can no "
        "longer be trusted as a current proxy for the real product, not that the "
        "code was read incorrectly.",
        "ALL FOUR BUILD-NOW-TIER FINDINGS RE-VERIFIED, NOW PROVISIONAL: Squad "
        "list/leaderboard authorization, database-level ownership integrity, the "
        "Directive Engine's absence (including a new direct read of "
        "getTomorrowDirective()'s seed-pool-lookup implementation), and the "
        "marketing/product mismatch were each re-confirmed this run by fresh "
        "direct source read against the same commit — unchanged in substance for "
        "a third consecutive run, but now flagged PROVISIONAL given the mirror's "
        "STALE reclassification above.",
        "COMPETITOR/MARKET RESEARCH REFRESHED, REAL CHANGES FOUND: Cora added "
        "strength + nutrition logging (closing toward a full training+nutrition+"
        "recovery loop on top of its existing wearable integrations and Body "
        "Charge recovery score) — a genuine mechanism expansion, not cosmetic. "
        "FitCraft shipped multiple new AI trainer personas (previously only "
        "'Ty' was named). Workout Quest added an 'AI-Fitness Chat' feature. "
        "Gentler Streak shipped an iOS 27 update (Siri App Intents, On-Screen "
        "Awareness) layered on its already-tracked Morning Check-In notifications. "
        "RazFit's ongoing subscription price is now CONFIRMED ($2.99/week or "
        "$29.99/year), resolving a previously-UNKNOWN gap. Strava raised new "
        "funding at a $2.2B valuation (Sequoia-led) and continues pushing into "
        "structured strength training (new workout log, muscle maps, expanded "
        "WHOOP integration) — direct competitive pressure on Vital Sync's "
        "confirmed-shallow training schema. Bitletics remains pre-launch with no "
        "ship date found; its Q2/Q3 2026 window expires within 2 days of this "
        "report with nothing shipped.",
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
        "Squad authorization is RE-CONFIRMED BROKEN this run — unauthenticated "
        "list/leaderboard routes, no privacy enforcement despite a privacy field "
        "existing. A real trust/security gap, unresolved for 3 weeks of calendar "
        "time now, PROVISIONAL pending fresher product-source access.",
        "Database-level ownership integrity is RE-CONFIRMED BROKEN this run — "
        "nullable columns, no foreign keys, under an application layer that assumes "
        "real scoping.",
        "The Directive Engine — the connective step in Vital Sync's own stated "
        "differentiation model between Alignment and Mission — is RE-CONFIRMED "
        "absent this run (getTomorrowDirective() confirmed to be a fixed "
        "seed-indexed pool lookup, not Alignment-driven).",
        "Training schema remains RE-CONFIRMED shallow this run — unchanged since "
        "Brief 01 — and the competitive gap is widening, not just holding steady: "
        "Strava shipped new workout-log/muscle-map depth this run in the same area.",
        "The marketing/product mismatch (site says 'Coming Soon,' pricing "
        "undisclosed) is RE-CONFIRMED this run against the same commit — still "
        "unresolved, and the deployed site remains unreachable for a 7th "
        "consecutive check.",
        "Zero wearable integrations, per the last export — still the reason "
        "Alignment/Recovery have little real data to score; not independently "
        "re-grepped against the current commit this run.",
        "PRODUCT SOURCE ITSELF IS NOW STALE: the GitHub mirror has sat frozen for "
        "3 weeks (2 confirmed check-ins), meeting this workflow's threshold for "
        "downgrading confidence in it as a proxy for the real, possibly-Replit-"
        "only, current product state.",
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
         "wearable integrations. Pricing confirmed unchanged — $12.99/mo or "
         "$89.99/yr on the official App/Play Store listings, though a separate "
         "Vora pricing page still shows Pro from as low as $7.50/mo (billed "
         "annually), the same cross-page discrepancy as last brief — still "
         "UNVERIFIED-EXACT rather than a single confirmed number. Core mechanism "
         "unchanged."),
        ("Cora", "Direct", "CHANGED THIS WEEK: Cora has added strength and "
         "nutrition tracking (\"log lifts and meals\") plus new widgets and Apple "
         "Watch complications for sleep/body-charge/strain, on top of its existing "
         "\"Body Charge\" HRV/sleep/training-load recovery score and wearable "
         "integrations (Apple Watch, Garmin, WHOOP, Oura). This is a genuine "
         "mechanism expansion, not cosmetic polish — Cora is now closer to "
         "covering training+nutrition+recovery together than any prior check "
         "found, narrowing the distance to Vital Sync's own full-loop claim from "
         "the data-supply side. Tier pricing still not found disclosed in search "
         "results."),
        ("FitCraft", "Direct", "CHANGED THIS WEEK: FitCraft shipped a major update "
         "introducing multiple new AI trainer personas (previously only \"Ty\" was "
         "named) with different coaching styles, on top of its existing RPG-style "
         "progression (XP, leveling, collectible cards) and diagnostic-assessment-"
         "driven programming. Pricing unchanged. Still no nutrition/recovery "
         "features found."),
        ("Workout Quest", "Direct", "CHANGED THIS WEEK (first re-check since Brief "
         "07): a July 17 2026 update added 'AI-Enhanced Workouts' and an "
         "'AI-Fitness Chat' feature alongside its existing RPG mechanics (XP, "
         "gold, levels) and 1,000+ movement library. Whether the chat is "
         "genuinely LLM-backed or scripted is UNVERIFIED from search snippets "
         "alone. Still no nutrition tracking found."),
        ("Habitica", "Specialist", "Not re-checked this week (surface-level watch "
         "only) — carried unchanged from Brief 07: pure RPG habit layer, cosmetic-"
         "only subscription, no fitness-specific programming."),
        ("Trainera / Bevel / NATE", "Direct (surface-level)", "Not re-checked this "
         "week (surface-level watch only) — carried unchanged from Brief 07."),
        ("WHOOP / Strava", "Specialist / Indirect", "CHANGED THIS WEEK: Strava "
         "raised new funding at a $2.2B valuation (Sequoia-led, joined by TCV, "
         "Jackson Square Ventures, Go4it Capital — found this run), and continues "
         "pushing into structured strength training with an overhauled workout "
         "log, muscle maps, an expanded partner ecosystem, and a deepened WHOOP "
         "integration (activities now flow both directions between the two "
         "apps). This is direct competitive movement into training-depth "
         "territory, where Vital Sync's own schema is confirmed shallow (see "
         "Current State). WHOOP's $575M Series G (March 2026) previously noted; "
         "no new WHOOP-specific product change found this week."),
        ("Bitletics", "Emerging / Beta", "RE-CHECKED this week: still described "
         "identically across its own blog and store pages as launching iOS and "
         "Android together in Q2/Q3 2026, free at launch, no subscription "
         "required, 30+ activity types, Apple Watch/heart-rate verified, weekly "
         "gift-card raffles (EUR 5-50) and fitness-matched leagues. No evidence "
         "of an actual launch found in this run's searches. Its Q2/Q3 2026 "
         "window (Q3 ends 2026-09-30) now expires within 2 days of this report "
         "with nothing shipped — sharpened to 'window about to lapse,' next "
         "brief should explicitly check whether it shipped or missed."),
        ("Google Health Premium (Gemini Health Coach, formerly Fitbit Premium)",
         "Indirect / Platform-scale",
         "RE-CHECKED this week: confirmed unchanged — still $9.99/mo, live in 37 "
         "countries per this run's sources (consistent with the prior full "
         "rollout, not a new expansion). Reads HRV/sleep/activity-load trends and "
         "generates adaptive, continuously-updated recovery-and-training "
         "recommendations — the same category of output as Vital Sync's Alignment "
         "engine, at hardware-platform distribution scale. Not a fitness-"
         "gamification competitor (no XP/streaks/badges), but a direct threat to "
         "the 'wearable-driven adaptive coaching' value proposition."),
        ("RazFit", "Emerging / Live", "CHANGED THIS WEEK: ongoing subscription "
         "pricing is now CONFIRMED — Weekly Premium $2.99, Annual Premium "
         "$29.99 (resolving the prior UNKNOWN) — still with a 3-day free trial. "
         "AI coaches are named Orion and Lyss (previously unnamed in this "
         "brief). Still built around 1-10 minute equipment-free bodyweight "
         "sessions with a badge reward system pitched as \"consistency over "
         "intensity.\" No nutrition or recovery tracking found. Small/unproven "
         "scale — stays MONITOR, confidence raised from LOW toward MEDIUM now "
         "that pricing is confirmed."),
        ("Gentler Streak", "Specialist / Indirect", "CHANGED THIS WEEK: shipped an "
         "iOS 27 update adding Siri integration — App Intents (health/fitness "
         "info without opening the app) and On-Screen Awareness (Siri "
         "contextualizing what's on screen) — plus new workout types and faster "
         "loading, on top of its already-tracked 'Morning Check-In "
         "Notifications' (gentle, data-driven flags for overreach/rest days, "
         "including cycle-aware timing for women). Still $8.99/mo or $39.99/yr, "
         "still no XP/streak-reward gamification layer at all (its whole "
         "positioning is the opposite of Vital Sync's core loop), but it keeps "
         "extending as the clearest real-world precedent for tying daily "
         "guidance to real recovery signals."),
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
        "NEW THIS WEEK: activation, not just retention, is now separately measured "
        "— users who don't complete 3 workouts in their first week churn 4-5x faster "
        "than those who do. The global fitness-app market is estimated at $13.9B in "
        "2026 (context figure, not independently cross-verified against a second "
        "source this run).",
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
        ("A", "Vital Sync behind, gap widening", "Recovery/Alignment DATA SUPPLY "
         "(not logic)", "The scoring algorithms are real and competitive-grade; "
         "Cora/Vora/Bevel/NATE win only because they have wearable data feeding "
         "equivalent logic — and Google's Health Premium Gemini Coach shows the "
         "same play at platform scale. Vital Sync's engine has zero wearable "
         "connections. CHANGED THIS WEEK: Cora also added strength+nutrition "
         "logging, meaning it now covers more of the full loop than a pure "
         "recovery-scheduling tool — the data-supply gap is widening, not just "
         "holding steady."),
        ("A", "Vital Sync behind, PROVISIONAL", "Directive Engine", "RE-CONFIRMED "
         "ABSENT this run (including a direct read of getTomorrowDirective()'s "
         "seed-pool-lookup implementation): no executable Directive Engine or "
         "Alignment-to-mission connection exists. Competitors don't have this "
         "either, but it's Vital Sync's own stated differentiation model, so the "
         "gap is self-inflicted, not just competitive."),
        ("A", "Vital Sync behind, gap widening", "Training depth", "RE-CONFIRMED "
         "still shallow this run (four-field schema, no sets/reps/weight). CHANGED "
         "THIS WEEK: Strava's continued strength-training push (new workout log, "
         "muscle maps, expanded partner ecosystem) is real, shipped competitive "
         "depth in exactly this area."),
        ("B", "Parity, competitors converging faster", "Core gamification (XP, "
         "streaks, badges) + 'AI coach' claim", "Table stakes in this niche — "
         "FitCraft, Workout Quest, Habitica match or exceed on raw mechanics "
         "depth. CHANGED THIS WEEK: FitCraft added multiple AI trainer personas "
         "and Workout Quest added an 'AI-Fitness Chat' feature — the 'has an AI "
         "coach' claim alone is converging toward parity industry-wide (depth/"
         "genuineness of each UNVERIFIED); Vital Sync's real GPT-4o-mini coach "
         "needs its context-depth advantage made visible, not just claimed."),
        ("C", "Vital Sync ahead (once real), PROVISIONAL", "Alignment engine + AI "
         "chat coach + real Squad activity", "The underlying engineering is "
         "genuinely competitive-grade, and Squads' activity remains confirmed "
         "real, not simulated. Gap is data supply, the missing Directive layer, "
         "and Squad authorization — not algorithm quality."),
        ("D", "Open market gap, newly sharpened", "Fatigue-aware gamification",
         "Nobody in the tracked competitive set ties streak/reward mechanics to real "
         "recovery data. Gentler Streak's iOS 27 update (Siri App Intents, On-"
         "Screen Awareness) extends its lead as the closest market validation "
         "found yet (fatigue-aware guidance without a gamification layer to fuse "
         "it to). Still confirmed to depend on the Directive Engine existing "
         "first — don't build this before that."),
    ],
    "opportunities": [
        # (rank, title, evidence, bucket, gap, ai, confidence)
        (1, "Fix Squad authorization / privacy [PROVISIONAL — see Product Source "
         "Freshness]", "RE-CONFIRMED BROKEN this run: GET /squads and GET "
         "/squads/leaderboard have no auth check and no privacy filtering. A real "
         "access-control gap, not cosmetic, unresolved for 3 weeks of calendar "
         "time now. PROVISIONAL only because the GitHub mirror is now STALE-"
         "classified — the finding itself is unchanged and re-verified.",
         "BUILD NOW", "-", "No AI Needed", "HIGH"),
        (2, "Enforce database-level ownership [PROVISIONAL — see Product Source "
         "Freshness]", "RE-CONFIRMED BROKEN this run: nullable ownership columns, "
         "no foreign keys, underneath a now-real application-level scoping layer, "
         "unresolved for 3 weeks of calendar time now.",
         "BUILD NOW", "-", "No AI Needed", "HIGH"),
        (3, "Build the Alignment -> Directive -> Mission connection [PROVISIONAL — "
         "see Product Source Freshness]", "RE-CONFIRMED ABSENT this run: missions "
         "are chosen by onboarding-weighted randomness, not by Alignment output. "
         "This run additionally read getTomorrowDirective()'s implementation "
         "directly — a fixed `pool[seed % length]` lookup, confirming it is not "
         "Alignment-driven. The connective step in Vital Sync's own "
         "differentiation model still doesn't exist.",
         "BUILD NOW", "A", "AI Assisted", "HIGH"),
        (4, "Fix the marketing/product mismatch [PROVISIONAL — see Product Source "
         "Freshness]", "RE-VERIFIED this run against the same 0435f9ea commit for "
         "a third consecutive run: landing.tsx still shows two 'Coming Soon' "
         "badges and 'Pricing will be announced before launch.' vitalsyncify.com "
         "itself remains unreachable (7th consecutive check, EGRESS_BLOCKED) — a "
         "human manually checking the live deployed site would close this gap "
         "fastest.",
         "BUILD NOW", "Trust", "No AI Needed", "HIGH"),
        (5, "Connect Apple Health as first wearable", "Broadest reach, lowest effort; "
         "feeds the already-working Alignment/Recovery algorithms with real data. "
         "Competitive urgency reinforced further this week: Cora added strength+"
         "nutrition logging on top of its wearable integrations, and Strava raised "
         "new funding at a $2.2B valuation while pushing into strength training — "
         "capital and feature depth both keep flowing to wearable-data-driven "
         "coaching. Not reverified against Vital Sync's source this run beyond "
         "confirming wearables remain absent per the last export.",
         "BUILD NEXT", "A", "No AI Needed", "HIGH"),
        (6, "Surface the real AI chat coach more prominently, and widen its context",
         "/coach/message is live GPT-4o-mini — its context excludes Alignment/"
         "Recovery/workout/nutrition data (confirmed Brief 07, not reverified this "
         "run). Newly urgent: Workout Quest and FitCraft both added their own "
         "'AI coach' features this run (genuineness UNVERIFIED), so simply having "
         "an AI coach is converging toward industry parity — Vital Sync's real, "
         "already-working GPT-4o-mini integration needs its context-depth "
         "advantage made visible and real, not just claimed. Two separate "
         "improvements: visibility, and context depth.",
         "BUILD NEXT", "C", "AI Core", "MEDIUM"),
        (7, "Real training depth (sets/reps/weight/overload) [PROVISIONAL — see "
         "Product Source Freshness]", "RE-CONFIRMED unchanged this run: workouts "
         "table still has no sets/reps/weight fields at all. Competitive gap "
         "widened this week: Strava shipped a new workout log and muscle-map "
         "feature set in exactly this territory.",
         "BUILD NEXT", "A", "No AI Needed", "HIGH"),
        (8, "Fatigue-aware streak mechanic", "Streak downgrades gracefully instead of "
         "breaking, when real recovery data is low. Still confirmed to depend on "
         "the Directive Engine (#3) and wearables (#5) landing first — do not build "
         "before those. Market validation extended this week: Gentler Streak's "
         "iOS 27 update (Siri App Intents, On-Screen Awareness) layers further "
         "onto its already-tracked fatigue/overreach-aware check-ins (without a "
         "gamification layer) — still the closest real-world precedent found, but "
         "this doesn't change the internal dependency order.",
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
         "competitors. RE-CHECKED this week: still pre-launch, still identical "
         "language across its own blog/store pages, no evidence of an actual "
         "launch found. Its Q2/Q3 2026 window (Q3 ends Sept 30) now expires "
         "within 2 days of this report with nothing shipped — sharpened to "
         "'window about to lapse.' Next brief should explicitly check whether it "
         "shipped or the window lapsed.",
         "MONITOR", "D", "No AI Needed", "LOW"),
        (12, "Monitor Google Health Premium's Gemini Coach as a platform-scale threat, "
         "not a build target", "Formerly Fitbit Premium — RE-CHECKED this week: "
         "confirmed unchanged, no new expansion found (live in 37 countries per "
         "this run's sources, consistent with the prior rollout). Google ships the "
         "same 'wearable data -> adaptive recovery/training guidance' output Vital "
         "Sync's Alignment engine produces, at a growing distribution scale. Not "
         "something Vital Sync can out-build directly; sharpens the case for #5 "
         "(connect a wearable) and for leaning on cross-system Alignment "
         "(training+nutrition+recovery together) as the differentiator Google "
         "doesn't offer.", "MONITOR", "A", "No AI Needed", "MEDIUM"),
        (13, "Track RazFit as a low-friction, short-session entrant", "CHANGED THIS "
         "WEEK: ongoing subscription pricing is now CONFIRMED — Weekly Premium "
         "$2.99, Annual Premium $29.99 (resolving last brief's UNKNOWN), still "
         "with a 3-day free trial. AI coaches named Orion and Lyss (previously "
         "unnamed). Still 1-10 minute equipment-free bodyweight sessions with a "
         "badge reward system, \"consistency over intensity\" positioning. Scale/"
         "traction still unconfirmed.",
         "MONITOR", "D", "No AI Needed", "MEDIUM"),
        (14, "Track Gentler Streak's fatigue-aware check-in mechanic", "CHANGED "
         "THIS WEEK: shipped an iOS 27 update adding Siri App Intents and "
         "On-Screen Awareness support, on top of its already-tracked 'Morning "
         "Check-In Notifications.' $8.99/mo or $39.99/yr, no gamification layer "
         "at all — not a direct competitor to Vital Sync's core loop, but the "
         "clearest real-world precedent yet for tying daily guidance to real "
         "recovery signals. Relevant to #8 as market validation, not as a feature "
         "to copy directly (Gentler Streak's whole brand is the anti-"
         "gamification, anti-streak-anxiety positioning).",
         "MONITOR", "D", "No AI Needed", "MEDIUM"),
    ],
    "opportunity_movement": [
        "#1, #2, #3, #4 (BUILD NOW) — UNCHANGED IN RANK, RE-VERIFIED for a third "
        "consecutive run, but NEWLY FLAGGED PROVISIONAL this week: the GitHub "
        "mirror (0435f9ea, still unmoved) crossed this workflow's 2+-consecutive-"
        "unchanged-runs threshold and is reclassified STALE this run (see Product "
        "Source Freshness). The actual squads.ts, profile.ts, schema files, a "
        "full-source 'directive' grep, and getTomorrowDirective()'s implementation "
        "were all freshly re-read this run — every finding holds exactly as "
        "before. The bucket assignment (BUILD NOW) doesn't change, but every one "
        "of these four now carries an explicit provisional caveat: the mirror's "
        "standing as a current proxy for the real product is unconfirmed after 3 "
        "weeks frozen (note: a run was skipped on 2026-09-21).",
        "#5 (Connect Apple Health as first wearable) — STILL BUILD NEXT/HIGH, no "
        "change in bucket. Competitive backdrop sharpened further this week: Cora "
        "added strength+nutrition logging on top of its wearables, and Strava "
        "raised new funding at a $2.2B valuation while pushing into strength "
        "training. Vital Sync's own wearables status was not independently "
        "re-grepped this run — carried from the last export.",
        "#6 (Surface + widen AI coach context) — STILL BUILD NEXT/MEDIUM, evidence "
        "sharpened: Workout Quest and FitCraft both shipped their own 'AI coach' "
        "features this run (genuineness UNVERIFIED), meaning the bare claim of "
        "having an AI coach is converging toward parity — raises the value of "
        "proving out Vital Sync's real GPT-4o-mini integration's context depth.",
        "#7 (Real training depth) — UNCHANGED bucket, RE-VERIFIED again this run "
        "via direct schema read (still four fields, no sets/reps/weight), and now "
        "PROVISIONAL for the same mirror-staleness reason as #1-4. Competitive gap "
        "widened, not just held steady: Strava shipped a new workout log and "
        "muscle-map feature this run in exactly this territory.",
        "#8 (Fatigue-aware streak mechanic, EXPERIMENT) — UNCHANGED bucket, "
        "evidence extended: Gentler Streak's iOS 27 update (Siri App Intents, "
        "On-Screen Awareness) layers onto its already-tracked Morning Check-In "
        "notifications, still the closest real-world precedent for this mechanic. "
        "Still gated on the Directive Engine (#3) and wearables (#5) landing "
        "first — new evidence strengthens the market case, not the internal "
        "readiness, so the bucket doesn't move.",
        "#11 (Track Bitletics, MONITOR) — NOT RE-RANKED, still LOW confidence. "
        "RE-CHECKED this week: still pre-launch, identical language across its own "
        "pages, no evidence of a launch. Its Q2/Q3 2026 window now expires within "
        "2 days of this report (Q3 ends Sept 30) with nothing shipped. Next run "
        "should explicitly check whether it shipped or the window lapsed.",
        "#12 (Google Health Premium, MONITOR) — NOT RE-RANKED; RE-CHECKED this "
        "week, confirmed unchanged, no new expansion found. Stays MONITOR/MEDIUM — "
        "sharpens the case for #5, not a build target itself.",
        "#13 (Track RazFit, MONITOR) — CONFIDENCE RAISED LOW -> MEDIUM: its "
        "ongoing subscription price is now CONFIRMED this run ($2.99/wk or "
        "$29.99/yr, resolving the prior UNKNOWN), and its two AI coach personas "
        "are now named (Orion, Lyss). Bucket unchanged (MONITOR) — scale/traction "
        "still unconfirmed.",
        "#14 (Track Gentler Streak, MONITOR) — NOT RE-RANKED, evidence extended: "
        "its iOS 27 Siri-integration update (found this run) builds on last "
        "brief's Morning Check-In finding. Still MONITOR/MEDIUM — tracked as "
        "market validation for #8, not a threat in its own right.",
        "#9, #10 (nutrition goals, voice logging) — UNCHANGED, not reverified this "
        "run.",
        "NO ITEMS RESOLVED OR REMOVED THIS RUN. The backlog's shape is stable; "
        "what changed most this week is the freshness classification itself "
        "(github_mirror: CURRENT_VERIFIED -> STALE) rather than any individual "
        "finding's substance — every product-state-dependent item (#1-4, #7, #8, "
        "gap type A/C rows) now explicitly carries that provisional caveat, which "
        "is new this run even though none of the underlying evidence changed.",
    ],
    "sources": [
        "github.com/faristjohar04-sketch/Vital-Sync — RE-CHECKED this run via "
        "`git log`/`git diff` against both the locally stored commit "
        "(0435f9ea79a871cd1578e2dc22e8e3055bebc50e) and a fresh `origin/main` "
        "fetch — both empty, and a fresh clone independently confirmed the same "
        "HEAD and commit date. This is the 2nd confirmed-unchanged check since "
        "Brief 07's 2026-09-07 advance, which meets the 2+-consecutive-runs "
        "threshold — the mirror is reclassified STALE this run. NOTE: no "
        "automated run fired on 2026-09-21, so 3 calendar weeks have passed "
        "across only 2 actual check-ins.",
        "github.com/faristjohar04-sketch/Vital-Sync @ 0435f9ea — direct source "
        "RE-READS performed this run (same commit, fresh read, not assumed "
        "unchanged from Brief 08): artifacts/api-server/src/routes/profile.ts (user "
        "scoping), artifacts/api-server/src/routes/squads.ts (real activity + "
        "authorization, including a full grep for getGhostCompletions/ghost/"
        "seededRand), lib/db/src/schema/workouts.ts and profile.ts (training "
        "depth + nullable ownership columns), a full-source grep for \"directive\" "
        "plus a direct read of getTomorrowDirective()'s implementation in both "
        "dashboard.tsx and the mobile app (Directive Engine absence), and "
        "artifacts/vital-sync/src/pages/landing.tsx (marketing/product mismatch)",
        "vital_sync_current_product_state.json — a structured audit export "
        "provided by the user on 2026-09-07/08, cross-checked against the commit "
        "above in Brief 07's run. No newer export has been provided in the three "
        "runs since; areas resting solely on it are marked UNCHANGED — NOT "
        "REVERIFIED in this brief's Current State table, now three weeks old.",
        "https://vitalsyncify.com — attempted directly this run (WebFetch): "
        "EGRESS_BLOCKED, the 7th consecutive check this has failed from this "
        "sandbox. Logged as SOURCE_UNAVAILABLE for the marketing-mismatch check, "
        "not treated as evidence of 'no marketing changes.'",
        "WebSearch (this run, competitor/market refresh): official/store pages "
        "and recent coverage for Vora, Cora (corahealth.app blog/research report), "
        "FitCraft, Workout Quest, Bitletics' own blog and app-store listings, "
        "RazFit's App Store listing and comparison pages; Google/9to5Google/"
        "MobiHealthNews/store.google.com coverage of Google Health Premium; "
        "Gentler Streak's App Store listing and a 9to5Mac 2026-09-14 iOS 27 "
        "update article; Crunchbase News H1-2026 fitness-funding sector snapshot "
        "and a Strava-specific Crunchbase News funding article (WHOOP Series G, "
        "Strava's $2.2B valuation round); Athletech News (MyFitnessPal/Cal AI "
        "acquisition, carried forward); WHOOP press-center and Inc. coverage of "
        "the Strava/WHOOP strength-training integration — direct WebFetch to "
        "competitor domains remains typically EGRESS_BLOCKED in this sandbox, so "
        "WebSearch snippets were used throughout, as in prior briefs.",
        "Habitica, Trainera/Bevel/NATE — surface-level watch only, NOT re-checked "
        "this run; carried forward unchanged from Brief 07.",
        "Customer pain/praise clusters and churn/retention benchmarks were NOT "
        "independently re-researched this run (effort focused on the freshness "
        "gate and the competitor feature refresh above) — the clusters and figures "
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
