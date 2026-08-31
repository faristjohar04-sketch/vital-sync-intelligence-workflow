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
    "report_date": "2026-08-31",
    "run_label": "Brief 05 — no Vital Sync product changes since Brief 04; marketing mismatch re-verified via repo source; Fitbit Premium rebranded Google Health Premium with wider app rollout",
    "exec_summary": (
        "Vital Sync's source repository shows zero commits since Brief 04 — HEAD is "
        "still ef43285, confirmed via `git log`/`git diff` against both the local "
        "clone and origin/main, not assumed. Nothing about the product itself has "
        "changed, so all four BUILD NOW items stand exactly as reported. This week's "
        "one genuine methodology win: vitalsyncify.com's direct fetch is STILL blocked "
        "by the sandbox's network egress proxy (4th consecutive week), but the "
        "marketing site's own source file (artifacts/vital-sync/src/pages/landing.tsx) "
        "lives in the same Vital-Sync repo already available to this workflow, and it "
        "was last touched Aug 11 — unchanged for the entire period HEAD has been "
        "frozen. Reading it directly re-confirms, from fresh evidence rather than a "
        "3-week-old caveat, that the marketing copy still labels the AI Coach "
        "\"Coming Soon\" / \"in active development\" and says \"Pricing will be "
        "announced before launch,\" while the real GPT-4o-mini chat coach and Stripe "
        "$9.99/mo billing are both live in the backend, and Squads is not mentioned "
        "anywhere on the page. This is a re-verification of the source that generates "
        "the page, not proof the deployed site hasn't been hand-edited outside "
        "version control, so the live-fetch block is still worth escalating if it "
        "persists — but it materially raises confidence that opportunity #3 is real "
        "and unresolved, not a stale finding. The five tracked competitors (Vora, "
        "Cora, FitCraft, Workout Quest, Habitica) are all confirmed stable on pricing "
        "and features again this week. The indirect-competitor picture sharpened: "
        "Google rebranded the Fitbit app and Fitbit Premium into the \"Google Health "
        "app\" and \"Google Health Premium\" (the Gemini-powered coach itself launched "
        "May 19, 2026), and this month widened the redesigned Google Health app to all "
        "Android/iOS users — the Gemini Coach itself stays Premium-gated at $9.99/mo, "
        "but the app's top-of-funnel reach is no longer limited to Fitbit/Pixel Watch "
        "owners. Bitletics remains pre-launch beta with no confirmed ship date beyond "
        "its already-announced Q2/Q3 2026 window, now closer to slipping. New market "
        "data this week: a 2026 industry analysis puts fitness apps at a 31% "
        "subscription-cancellation rate (2nd highest category after video streaming, "
        "with 41% of consumers reporting active subscription fatigue overall), and a "
        "Sensor Tower Q4 2025 report shows fitness-app monthly churn rising from 8.2% "
        "(2023) to 11.7% (2025) with only 3% Day-30 retention — directionally the same "
        "story as prior weeks' churn figures, worse in this newer dataset. Separately, "
        "Strava's acquisition of Runna and Garmin's acquisition of TrainingPeaks signal "
        "the category consolidating around AI-coaching-plus-hardware plays, adding "
        "urgency to Vital Sync differentiating on cross-system Alignment before that "
        "consolidation squeezes out boutique competitors."
    ),
    "top_actions": [
        ("Implement real per-user data scoping — still unresolved",
         "Confirmed unchanged this week (commit ef43285, identical to Brief 04). Every "
         "route (profile, workouts, meals, recovery, etc.) still queries a single "
         "global row with no userId filter anywhere. Still more foundational than any "
         "feature gap — nothing this week changes that."),
        ("Fix the marketing/product mismatch — now re-verified, not just carried forward",
         "vitalsyncify.com's live fetch is still blocked (4th consecutive week), but "
         "this week the workflow read the page's own source directly from the "
         "Vital-Sync repo (landing.tsx, unchanged since Aug 11): AI Coach is still "
         "labeled \"Coming Soon\" and pricing \"will be announced before launch\" while "
         "the real chat coach and $9.99/mo Stripe billing are both live, and Squads "
         "isn't mentioned at all. Confidence in this finding just went up, not down."),
        ("Connect a first wearable (Apple Health) — competitive backdrop keeps sharpening",
         "Confirmed unchanged in Vital Sync's source this week: zero wearable "
         "integrations. Google's Gemini-powered health coach (now rebranded Google "
         "Health Premium, $9.99/mo) delivers the same 'read HRV/sleep, tell you what "
         "to do' output Vital Sync's Alignment engine already computes, and this "
         "month widened its redesigned app to all Android/iOS users — broader "
         "top-of-funnel reach than a Fitbit/Pixel-Watch-only audience. The algorithm "
         "gap was already closed; the data-supply gap is now competing against a "
         "bigger, more widely distributed rival every week it stays unaddressed."),
    ],
    "biggest_threat": (
        "Unchanged in substance, sharper in distribution — Google's Gemini-powered "
        "health coach, now formally rebranded from \"Fitbit Premium\" to \"Google "
        "Health Premium\" as part of a broader Google Health app redesign ($9.99/mo or "
        "$99/yr, coach launched May 19 2026): reads HRV/sleep/activity-load trends and "
        "generates continuously-adapting recovery-and-training guidance. This month "
        "Google widened the redesigned Google Health app to all Android/iOS users, not "
        "just Fitbit/Pixel Watch owners — the Gemini Coach itself stays Premium-gated, "
        "but the app's top-of-funnel reach just got meaningfully bigger. Cora and Vora "
        "remain live and stable (both confirmed unchanged on pricing/features this "
        "week) and are still the sharper boutique threat on specificity — but Google's "
        "version of the same idea now has a wider on-ramp than any direct competitor, "
        "Vital Sync included, can match."
    ),
    "biggest_gap": (
        "Unchanged — nobody in the competitive set ties streak/gamification mechanics "
        "to real fatigue data, or eases gamification off for experienced users. "
        "Gentler Streak (last week's market-validation find) shipped only cosmetic "
        "updates this week (new app icon, morning check-in notifications, new workout "
        "types) — nothing that changes the underlying case. Vital Sync's backlogged "
        "fatigue-aware streak opportunity (#6) remains a proven, currently-unaddressed "
        "pattern that nobody in the direct fitness-gamification set (Vora, Cora, "
        "FitCraft, Workout Quest, Habitica, Bitletics) has shipped yet."
    ),
    "biggest_weakness": (
        "Unchanged and re-verified — there is still no per-user data scoping anywhere "
        "in the backend (commit ef43285, identical to Brief 04); every route reads/"
        "writes one single global profile row. Until this is built, Vital Sync "
        "structurally cannot serve more than one real user at a time, regardless of "
        "how good any individual feature is."
    ),
    "biggest_advantage": (
        "Unchanged — the Alignment engine (weighted training/nutrition/recovery "
        "composite, confidence-rated, gracefully degrades with missing data) and the "
        "real GPT-4o-mini coach chat are both genuinely well-built. Vital Sync's "
        "$9.99/mo Pro price sits almost exactly on the 2026 Health & Fitness app "
        "pricing median ($9.70 median / $9.99 most common price point) and now also "
        "matches Google Health Premium's own $9.99/mo entry point — the engineering "
        "quality and price are both right for the category; the gap is still data "
        "supply and surfacing, not engineering or pricing."
    ),
    "one_to_ignore": (
        "Still: chasing deeper RPG mechanics (pets, gear, cosmetic avatars) to match "
        "FitCraft, Habitica or Workout Quest — saturated ground, low differentiation, "
        "and it plays away from Vital Sync's real structural advantage. Also not worth "
        "chasing this week: Bitletics' real-reward redemption model — its pricing has "
        "been confirmed for two weeks now (freemium, Pro adds challenges/raffle "
        "tickets), but it is still pre-launch beta with no user base to validate "
        "demand against and no confirmed date beyond its original Q2/Q3 2026 window, "
        "and trying to out-reward Google's platform-scale coach on distribution is not "
        "a fight Vital Sync can win directly — better to compete on the cross-system "
        "Alignment intelligence Google doesn't build (nutrition/training/recovery tied "
        "together, not just recovery alone)."
    ),
    "vital_sync_current_state": [
        ("Engagement / Gamification", "LIVE", "XP, Levels, Identity Ranks, Discipline "
         "Score, streaks + streak-freeze, 15 badges, 4 Boss Battles, 4 default 30-day "
         "Challenges. Squads leaderboard is LIVE but member activity is simulated "
         "(seeded pseudo-random \"ghost\" completions) — see Biggest Weakness/Actions."),
        ("Nutrition", "PARTIAL", "Meal logging works (name/cals/macros). Protein + "
         "water + a new nullable calorie target (\"Stage 1\", added recently) exist; "
         "no carb/fat targets. Meal \"aligned\" field is modeled but usually null."),
        ("Training", "PARTIAL", "Confirmed in source: logging works (name/duration/"
         "type/notes, +50 XP per workout) but the schema has no sets/reps/weight/"
         "progressive-overload fields at all — shallow by design, not just untested."),
        ("Recovery", "PARTIAL", "Real multi-factor log (sleep, morning feel, energy, "
         "soreness, stress, mobility) feeding a genuine weighted recovery-state "
         "algorithm (READY/NORMAL/RECOVER/LOW_READINESS). Reads empty only when no "
         "daily log exists yet — algorithm confirmed real, input data is the gap."),
        ("Cross-System Intelligence (Alignment)", "LIVE", "Confirmed in source: a real "
         "weighted composite (training 30% / nutrition 35% / recovery 35%) with "
         "confidence rating and graceful weight-redistribution for missing pillars. "
         "Corrects Brief 01's \"unproven/empty\" verdict — the algorithm works, it was "
         "just scoring an account with no logged data."),
        ("AI — ambient brief", "PROTOTYPE", "/coach/brief is confirmed templated: "
         "deterministic string selection keyed on streak/mission state, no model call."),
        ("AI — chat coach", "LIVE", "Confirmed in source: /coach/message is real "
         "GPT-4o-mini with a well-written system prompt and live user-stat context. "
         "First-class tab in the mobile app. Corrects Brief 01, which had not tested "
         "this endpoint and classified all \"AI\" as templated."),
        ("Monetization", "LIVE", "Stripe \"Vital Sync Pro\": $9.99/mo or $69.99/yr, "
         "gating AI coaching / insights / plans / reports. Not mentioned on marketing "
         "site. Tested account is free tier."),
        ("Integrations (wearables)", "NOT FOUND", "No Apple Health / Garmin / Whoop / "
         "Oura / Fitbit / Strava references anywhere in source or API surface — this "
         "is the main reason Alignment/Recovery read empty, not an algorithm gap."),
        ("Mobile App", "LIVE", "New this brief: a full Expo/React Native app "
         "(vital-sync-mobile) — tabbed nav (Home/Train/Nutrition/Coach/Stats) plus "
         "onboarding, recovery, squad, challenges, badges, evidence, and auth screens. "
         "Not inspected in Brief 01 (marketing site only)."),
        ("Multi-User / Data Scoping", "NOT FOUND", "New finding: no route anywhere "
         "filters by userId. getOrCreateProfile() and equivalents literally SELECT the "
         "first row in the table. One global profile currently serves every request."),
        ("Push Notifications", "LIVE", "Web push infrastructure present (VAPID key, "
         "subscribe endpoint); actual notification content/cadence not observed."),
        ("Auth", "LIVE", "Clerk middleware is correctly wired app-wide (verified in "
         "source) but no route uses req.auth() to scope a query yet — see Multi-User "
         "row above. Auth infra and auth usage are two different states here."),
    ],
    "changes_this_week": [
        "NO PRODUCT CHANGES: Vital-Sync repo HEAD is unchanged at ef43285 — zero "
        "commits since Brief 04 (`git log ef43285..origin/main` and `git diff --stat` "
        "both empty, verified against both the local clone and a fresh origin/main "
        "fetch). Every finding in the Current State table below is carried forward "
        "as-is, not re-derived from memory.",
        "COVERAGE GAP PARTIALLY CLOSED: vitalsyncify.com's direct fetch is STILL "
        "blocked (4th consecutive week, same sandbox egress-proxy failure as Briefs "
        "02-04), but this run found and used an alternate verification path flagged "
        "in Brief 04's log: the marketing page's own source, "
        "artifacts/vital-sync/src/pages/landing.tsx, lives in the already-accessible "
        "Vital-Sync repo and was last modified Aug 11 (unchanged for the entire period "
        "HEAD has been frozen). Reading it directly confirms the AI Coach section "
        "still says \"Coming Soon\"/\"in active development\" and pricing \"will be "
        "announced before launch,\" and Squads is not mentioned anywhere on the page — "
        "while the real chat coach and $9.99/mo Stripe billing are both live in the "
        "backend. Opportunity #3 is now re-verified from this week's own evidence, not "
        "carried forward on a stale caveat (with the standing caveat that this checks "
        "the source, not a possible out-of-band edit to the deployed site — worth "
        "raising to a human if the live-fetch block doesn't clear soon).",
        "COMPETITOR REBRAND: Google renamed \"Fitbit Premium\" to \"Google Health "
        "Premium\" and the Fitbit app to the \"Google Health app\" as part of a wider "
        "redesign (the Gemini-powered coach itself launched May 19 2026 and is "
        "unchanged in function/price, $9.99/mo or $99/yr). This month Google expanded "
        "the redesigned app to all Android/iOS users — the Coach stays Premium-gated, "
        "but the app's distribution is no longer limited to Fitbit/Pixel Watch owners. "
        "Competitor Watch and Biggest Threat updated to reflect the rebrand and wider "
        "reach.",
        "CONFIRMED UNCHANGED: Vora, Cora, FitCraft, Workout Quest, and Habitica are all "
        "re-checked this week with no material change in pricing or features from "
        "Brief 04. Bitletics is also unchanged (still pre-launch beta) — its "
        "previously-announced Q2/Q3 2026 launch window is now closer to slipping, with "
        "no confirmed ship date found this week.",
        "MINOR UPDATE, NOT MARKET-MOVING: Gentler Streak (last week's fatigue-aware-"
        "streak market validation) shipped cosmetic updates this week — a new app "
        "icon, morning check-in notifications, and new workout types. Doesn't change "
        "the core validation for opportunity #6, so it isn't re-scored.",
        "MARKET CONTEXT: A 2026 industry analysis puts fitness apps at a 31% "
        "subscription-cancellation rate (2nd highest category after video streaming, "
        "against 41% of consumers reporting active subscription fatigue overall), and "
        "a Sensor Tower Q4 2025 report shows fitness-app monthly churn rising from "
        "8.2% (2023) to 11.7% (2025) with only 3% Day-30 retention — worse than the "
        "churn figures cited in earlier briefs, though from a different underlying "
        "dataset, so treated as a directional confirmation rather than a like-for-like "
        "trend line. Separately, Strava's acquisition of Runna and Garmin's "
        "acquisition of TrainingPeaks this year signal the category consolidating "
        "around AI-coaching-plus-hardware plays — added as new market-trend context, "
        "not tied to a specific opportunity.",
    ],
    "strengths": [
        "The Alignment engine and the AI chat coach are both genuinely well-engineered "
        "— closer to competitor-grade than Brief 01 credited.",
        "Deep, coherent gamification core (XP/Levels/Identity Ranks/Streaks/Badges/Boss "
        "Battles) — more developed than most competitors' equivalents.",
        "Identity-rank narrative aligns with the identity/community motivator trend "
        "research flags as the strongest driver of movement post-GLP-1.",
        "Monetization infrastructure (Stripe) is genuinely live, not just a plan.",
        "A real, structurally complete mobile app already exists (Expo/React Native).",
    ],
    "weaknesses": [
        "No per-user data scoping anywhere in the backend — structurally blocks a "
        "real multi-user launch regardless of feature quality (see Top Action #1).",
        "Squads leaderboard activity is simulated with no visible disclosure — a trust "
        "risk if discovered by users, and not a real competitive moat until it's real.",
        "Zero wearable integrations — the reason two well-built engines (Alignment, "
        "Recovery) read empty is missing data supply, not missing logic.",
        "Training schema has no sets/reps/weight — confirmed shallow, not just "
        "unused, in the one pillar most fitness-serious users will judge first.",
        "Marketing site materially understates the product — re-verified this week via "
        "the landing page's own source (vitalsyncify.com's live fetch is still "
        "blocked, 4th consecutive week, but the repo source it's built from is "
        "unchanged since Aug 11): Squads, billing, and the real AI chat coach aren't "
        "mentioned; the AI section is still labeled \"Coming Soon\" and pricing "
        "\"will be announced before launch\" despite both already shipping.",
    ],
    "cross_system_audit": [
        ("Training <-> Recovery", "LIVE (algorithm)", "Alignment engine weights both "
         "into one score — confirmed real logic; needs real workout/recovery data to "
         "demonstrate."),
        ("Nutrition <-> Recovery", "LIVE (algorithm)", "Both are real pillars in the "
         "same weighted Alignment score."),
        ("Sleep <-> Performance", "LIVE (algorithm)", "computeRecoveryScoreV2 blends "
         "sleep with energy/soreness/stress/morning-feel/mobility into one state."),
        ("Training Load <-> Fatigue", "NOT FOUND", "No training-load or fatigue-"
         "trend field exists in the schema."),
        ("Protein Intake <-> Training Goal", "PARTIAL", "Protein target exists but "
         "isn't cross-referenced against training goals specifically."),
        ("Recovery <-> Workout Recommendation", "NOT FOUND", "Recovery state (READY/"
         "RECOVER/etc.) is computed but nothing downstream adjusts a workout "
         "recommendation from it yet."),
        ("Progress <-> Program Adjustment", "NOT FOUND", "Boss Battles/Challenges are "
         "static content, not adjusted by Alignment or recovery state."),
    ],
    "competitor_watch": [
        ("Vora", "Direct", "Voice-first all-in-one; 500+ wearable integrations; Free "
         "(permanent) / $12.99mo / $89.99yr. Confirmed unchanged this week."),
        ("Cora", "Direct", "AI coach reschedules training from real HRV/sleep via a "
         "named \"Body Charge\" (0-100) score; 7-day trial, price still undisclosed. "
         "Confirmed unchanged this week."),
        ("FitCraft", "Direct", "\"Deepest gamification on the market\"; streaks, "
         "collectible cards, AI coach; pricing now confirmed $0-$19.99/mo tiered "
         "(free tier, no card required) — unlisted in Brief 02. Still no nutrition/"
         "recovery features found."),
        ("Workout Quest", "Direct", "RPG workout tracker; free-to-start, no "
         "subscription required; guilds, raid-boss workouts, loot chests, seasonal "
         "battle passes, leaderboards; still no nutrition tracking found."),
        ("Habitica", "Specialist", "Gamification pioneer (2013); pure RPG habit layer, "
         "no fitness-specific programming. NEW: confirmed (June 2026 update) that its "
         "subscription is purely cosmetic — every core habit-tracking feature, "
         "including gamification, is free."),
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
         "raffle tickets). Still pre-launch beta with no confirmed ship date beyond "
         "its original Q2/Q3 2026 window, which is now closer to slipping — MONITOR, "
         "not yet a deep-dive threat."),
        ("Google Health Premium (Gemini Health Coach, formerly Fitbit Premium)",
         "Indirect / Platform-scale",
         "UPDATED THIS WEEK: Google renamed Fitbit/Fitbit Premium to Google Health "
         "app/Google Health Premium as part of a wider redesign, and this month "
         "expanded that redesigned app to all Android/iOS users (previously "
         "Fitbit/Pixel-Watch-centric) — broader top-of-funnel reach, though the "
         "Gemini Coach itself stays Premium-gated at $9.99/mo or $99/yr. The coach "
         "(launched May 19 2026) reads HRV/sleep/activity-load trends and generates "
         "adaptive, continuously-updated recovery-and-training recommendations — the "
         "same category of output as Vital Sync's Alignment engine, at "
         "hardware-platform distribution scale. Not a fitness-gamification competitor "
         "(no XP/streaks/badges), but a direct threat to the 'wearable-driven "
         "adaptive coaching' value proposition."),
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
        "Fitness app churn is brutal and, per this week's data, getting worse — a "
        "Sensor Tower Q4 2025 report shows monthly churn rising from 8.2% (2023) to "
        "11.7% (2025) with only 3% Day-30 retention; lost motivation is still cited in "
        "38% of cancellations.",
        "Subscription fatigue is now a named, measured problem — fitness apps carry a "
        "31% cancellation rate, 2nd highest of any app category after video streaming, "
        "against 41% of consumers reporting active subscription fatigue overall "
        "(2026 industry analysis); the average user now carries 4+ health "
        "subscriptions.",
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
        ("-", "Foundational blocker", "Multi-user data scoping", "No route filters by "
         "userId anywhere in the backend — one global profile serves every request. "
         "Not a competitor comparison; a prerequisite for everything else to matter "
         "at real-user scale."),
        ("A", "Vital Sync behind", "Recovery/Alignment DATA SUPPLY (not logic)", "The "
         "scoring algorithms are real and competitive-grade; Cora/Vora/Bevel/NATE win "
         "only because they have wearable data feeding equivalent logic — and Google's "
         "Health Premium Gemini Coach (formerly Fitbit Premium, now on a wider "
         "Android/iOS rollout this month) shows the same play at platform scale. "
         "Vital Sync's engine has zero wearable connections."),
        ("A", "Vital Sync behind", "Logging friction", "Voice/photo logging proven "
         "(Vora, Cora); Vital Sync has manual form-entry only."),
        ("B", "Parity", "Core gamification (XP, streaks, badges)", "Table stakes in "
         "this niche — FitCraft, Workout Quest, Habitica match or exceed on raw "
         "mechanics depth."),
        ("C", "Vital Sync ahead (once real)", "Alignment engine + AI chat coach", "The "
         "underlying engineering is genuinely competitive-grade — closer to what "
         "Cora/Vora charge for than Brief 01 credited. Gap is data supply and "
         "surfacing, not algorithm quality."),
        ("D", "Open market gap", "Fatigue-aware gamification", "Nobody analyzed ties "
         "streak/reward mechanics to real recovery data, or eases intensity for "
         "experienced users. Proven pain points, no proven solution yet."),
        ("D", "Open market gap / trust risk", "Simulated social proof", "Squads shows "
         "seeded-random \"member activity\" with no real users behind it and no "
         "disclosure — a category-wide pattern (cold-start ghost data) but a real risk "
         "if discovered without being a deliberate, owned decision."),
    ],
    "opportunities": [
        # (rank, title, evidence, bucket, gap, ai, confidence)
        (1, "Implement real per-user data scoping", "Every route reads/writes one "
         "global profile row — confirmed in source across profile/workouts/meals/"
         "recovery/etc. Blocks real multi-user launch entirely.",
         "BUILD NOW", "Foundational", "No AI Needed", "HIGH"),
        (2, "Decide & act on Squads' simulated activity", "getGhostCompletions() "
         "generates fake member counts/completions via seeded randomness — confirmed "
         "in source, no real users behind the numbers shown.",
         "BUILD NOW", "D", "No AI Needed", "HIGH"),
        (3, "Fix the marketing/product mismatch", "RE-VERIFIED this week via an "
         "alternate path: vitalsyncify.com's live fetch is still blocked (4th "
         "consecutive week), but the page's own source (landing.tsx, unchanged since "
         "Aug 11) confirms AI Coach is still \"Coming Soon\"/\"in active development\" "
         "and pricing \"will be announced before launch,\" while the real chat coach "
         "and $9.99/mo Stripe billing are both live and Squads isn't mentioned at all.",
         "BUILD NOW", "Trust", "No AI Needed", "HIGH"),
        (4, "Connect Apple Health as first wearable", "Broadest reach, lowest effort; "
         "feeds the already-working Alignment/Recovery algorithms with real data "
         "instead of building new logic. Urgency reinforced this week: Google Health "
         "Premium's Gemini coach (formerly Fitbit Premium) ships the same 'wearable "
         "data -> adaptive guidance' output at platform scale, and this month widened "
         "its app to all Android/iOS users, not just Fitbit/Pixel Watch owners.",
         "BUILD NOW", "A", "No AI Needed", "HIGH"),
        (5, "Surface the real AI chat coach more prominently", "/coach/message is "
         "live GPT-4o-mini with good context — currently one tab among many, while "
         "the more visible ambient \"brief\" is templated. Consider unifying quality.",
         "BUILD NEXT", "C", "AI Core", "MEDIUM"),
        (6, "Fatigue-aware streak mechanic", "Streak downgrades gracefully instead of "
         "breaking, when real recovery data (once wearables land) is low. Confidence "
         "raised this week: Gentler Streak is a live app built entirely around this "
         "exact premise (ease the target to match daily capacity, don't punish a "
         "miss) — direct market validation, and nobody in the direct fitness-"
         "gamification set (Vora/Cora/FitCraft/Workout Quest/Habitica/Bitletics) ships "
         "it yet.", "BUILD NEXT", "D", "AI Assisted", "HIGH"),
        (7, "Real training depth (sets/reps/weight/overload)", "Confirmed in schema: "
         "workouts table has no sets/reps/weight fields at all — shallow by design.",
         "BUILD NEXT", "A", "No AI Needed", "HIGH"),
        (8, "Full nutrition goals (carbs/fat)", "Protein/water/calorie targets exist "
         "(calorie target added recently, \"Stage 1\"); carbs/fat still missing.",
         "IMPROVE EXISTING", "A", "AI Assisted", "HIGH"),
        (9, "Gamification that tapers with Identity Rank", "Quieter, data-forward view "
         "for veteran-rank users.", "EXPERIMENT", "D", "No AI Needed", "MEDIUM"),
        (10, "Voice / natural-language logging", "Vora and Cora both lead with this; "
         "large build effort, competitors have a head start.", "MONITOR", "A",
         "AI Core", "MEDIUM"),
        (11, "Track Bitletics' real-reward redemption model", "Converts activity into "
         "redeemable in-game loot/raffle tickets rather than only in-app XP/badges — "
         "a genuinely different reward mechanic than any of the 5 deep-dived "
         "competitors. Unchanged this week (freemium, Pro adds challenges/raffle "
         "tickets); still pre-launch beta with no confirmed ship date beyond its "
         "original Q2/Q3 2026 window, which is now closer to slipping. Too early to "
         "act on, worth tracking.", "MONITOR", "D", "No AI Needed", "LOW"),
        (12, "Monitor Google Health Premium's Gemini Coach as a platform-scale threat, "
         "not a build target", "Formerly Fitbit Premium — Google renamed it this year "
         "and this month widened the redesigned Google Health app to all Android/iOS "
         "users (the Coach itself stays Premium-gated). Google now ships the same "
         "'wearable data -> adaptive recovery/training guidance' output Vital Sync's "
         "Alignment engine produces, at a growing distribution scale. Not something "
         "Vital Sync can out-build directly; sharpens the case for #4 (connect a "
         "wearable) and for leaning on cross-system Alignment (training+nutrition+"
         "recovery together) as the differentiator Google doesn't offer.", "MONITOR",
         "A", "No AI Needed", "MEDIUM"),
    ],
    "opportunity_movement": [
        "#1, #2 (BUILD NOW) — UNCHANGED, RE-VERIFIED, not re-asserted from memory. "
        "Vital-Sync HEAD is still ef43285 (`git log`/`git diff` against Brief 04's "
        "stored commit, and against a fresh origin/main fetch, both empty) — both "
        "stand exactly as evidenced last week, still unresolved.",
        "#3 (Fix the marketing/product mismatch, BUILD NOW) — RE-VERIFIED THIS WEEK "
        "on fresh evidence, ending a four-week run of 'source unavailable.' "
        "vitalsyncify.com's live fetch is still blocked, but this run read the "
        "marketing page's own source directly from the Vital-Sync repo "
        "(landing.tsx, unchanged since Aug 11) and confirmed the mismatch stands: "
        "AI Coach still \"Coming Soon,\" pricing still \"will be announced before "
        "launch,\" Squads not mentioned. Stays at BUILD NOW/HIGH, now on this week's "
        "own evidence rather than a rolling caveat. Standing caveat: this verifies "
        "the source, not a possible out-of-band edit to the deployed site — worth "
        "escalating to a human if the direct-fetch block doesn't clear soon.",
        "#4 (Connect Apple Health as first wearable) — STILL BUILD NOW/HIGH, urgency "
        "reinforced further: Google's coach (renamed Google Health Premium this "
        "year) widened its app to all Android/iOS users this month, broadening the "
        "distribution gap Vital Sync is racing against.",
        "#6 (Fatigue-aware streak mechanic, BUILD NEXT) — UNCHANGED at HIGH "
        "confidence (raised last week when Gentler Streak surfaced as market "
        "validation). Gentler Streak's updates this week were cosmetic only "
        "(app icon, notifications, workout types) — no change to the underlying "
        "case, so not re-scored again.",
        "#12 (MONITOR) — RENAMED, not re-ranked: the competitor is the same entity "
        "as last week's 'Fitbit Premium Gemini Coach,' now reflecting Google's "
        "rebrand to Google Health Premium and this month's wider app rollout. Still "
        "MONITOR/MEDIUM — sharpens the case for #4, not a build target itself.",
        "#11 (Track Bitletics, MONITOR) — NOT RE-RANKED; confirmed unchanged this "
        "week, still pre-launch beta with its original Q2/Q3 2026 window now closer "
        "to slipping. Stays at LOW confidence.",
        "#9 (Gamification that tapers with Identity Rank, EXPERIMENT) — NOT "
        "RE-SCORED this week; no new evidence moved it.",
        "#5, #7, #8, #10 — UNCHANGED. No evidence this week (product-side or "
        "competitive) moved any of these; carried forward exactly as ranked in "
        "Brief 04.",
    ],
    "sources": [
        "github.com/faristjohar04-sketch/Vital-Sync (source code; re-verified via "
        "`git log`/`git diff` against both the local clone and a fresh origin/main "
        "fetch — HEAD unchanged at ef43285, zero commits since Brief 04)",
        "github.com/faristjohar04-sketch/Vital-Sync — "
        "artifacts/vital-sync/src/pages/landing.tsx (marketing-page source, read "
        "directly this week as an alternate verification path for opportunity #3; "
        "last modified Aug 11, unchanged for the entire period HEAD has been frozen)",
        "vitalsyncify.com — SOURCE UNAVAILABLE this run, 4th consecutive week "
        "(sandbox network egress proxy blocked it, EGRESS_BLOCKED on WebFetch); the "
        "repo-source check above is a partial substitute, not full re-verification "
        "of the deployed site",
        "askvora.com, corahealth.app, getfitcraft.com, workoutquestapp.com, "
        "habitica.com — direct fetch also SOURCE UNAVAILABLE this run (same egress "
        "block); competitor data instead drawn from WebSearch-indexed pages on each "
        "domain (see individual Competitor Watch entries for specifics)",
        "bitletics.com (via WebSearch-indexed pages) — reconfirmed unchanged, still "
        "pre-launch beta",
        "support.google.com/googlehealth, androidauthority.com, howtogeek.com, "
        "mobihealthnews.com, techcrunch.com, blog.google, gadgetbond.com (via "
        "WebSearch) — Fitbit Premium -> Google Health Premium rebrand, wider "
        "Android/iOS app rollout this month, Gemini Health Coach pricing/features",
        "WebSearch: new fitness gamification app launches (no new direct entrants "
        "found this week), Gentler Streak feature updates, fitness startup funding "
        "and M&A landscape (valueaddvc.com — Strava/Runna, Garmin/TrainingPeaks), "
        "subscription-fatigue and churn statistics (techrt.com, adapty.io — Sensor "
        "Tower Q4 2025 churn data)",
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
    if "LIVE" in s:
        return "#2E6B44"
    if "NOT FOUND" in s:
        return "#8A362E"
    if "UNKNOWN" in s:
        return "#63665F"
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
