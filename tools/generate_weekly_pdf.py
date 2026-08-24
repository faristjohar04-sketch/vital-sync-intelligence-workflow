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
# THIS WEEK'S DATA — Brief 04, compiled 2026-08-24. Vital-Sync-specific
# sections are carried forward unchanged from Brief 03: the source repo has
# zero commits since then (HEAD still ef43285, verified via git log/diff
# against both the local clone and origin/main). vitalsyncify.com was
# unreachable this run for the THIRD consecutive week (sandbox egress
# block), so the marketing-mismatch opportunity remains un-re-verified.
# Competitor/market sections are refreshed via WebSearch (direct
# competitor-site WebFetch was also blocked this run); "Changes this week"
# means real week-over-week comparison — confirmed-unchanged items are
# stated as such, not silently re-asserted, and nothing here is fabricated
# to fill a gap.
# ---------------------------------------------------------------------------
WEEK_DATA = {
    "report_date": "2026-08-24",
    "run_label": "Brief 04 — no Vital Sync product changes since Brief 03; Fitbit Gemini Coach added as new platform-scale threat",
    "exec_summary": (
        "Vital Sync's source repository shows zero commits since Brief 03 — HEAD is "
        "still ef43285, confirmed via `git log`/`git diff` against both the local "
        "clone and origin/main, not assumed. Nothing about the product itself has "
        "changed, so all BUILD NOW items (per-user data scoping, Squads' simulated "
        "activity, the marketing/product mismatch, connecting a first wearable) stand "
        "exactly as reported and remain unresolved. vitalsyncify.com could not be "
        "reached again this run (sandbox network egress proxy blocked it, same as "
        "Briefs 02 and 03) — this is now the THIRD consecutive week the marketing site "
        "has been unreachable, so opportunity #3 stays un-re-verified rather than "
        "assumed fixed. The five tracked competitors (Vora, Cora, FitCraft, Workout "
        "Quest, Habitica) are all confirmed stable on pricing and features this week — "
        "no material change on any of them. The real news this week is on the "
        "indirect-competitor side: Google's Gemini-powered Fitbit Premium health coach "
        "(launched May 19, 2026; $9.99/mo or $99.99/yr) reads HRV/sleep/activity-load "
        "trends off hundreds of millions of existing Fitbit/Pixel Watch devices and "
        "generates the same category of adaptive recovery-and-training guidance Vital "
        "Sync's Alignment engine is built to produce — at platform scale, bundled with "
        "hardware most target users may already own. It is added to Competitor Watch "
        "this week as a new platform-scale indirect threat. Separately, Bitletics' "
        "pricing model is now confirmed (freemium at launch, Pro tier adds weekly "
        "skill-based challenges and extra raffle tickets) though it remains pre-launch "
        "beta, and a live competitor, Gentler Streak, was surfaced this week whose "
        "entire premise — a streak/activity tracker that eases to match daily capacity "
        "instead of punishing a miss — is direct market validation of Vital Sync's own "
        "backlogged fatigue-aware streak opportunity (#6)."
    ),
    "top_actions": [
        ("Implement real per-user data scoping — still unresolved",
         "Confirmed unchanged this week (commit ef43285, identical to Brief 03). Every "
         "route (profile, workouts, meals, recovery, etc.) still queries a single "
         "global row with no userId filter anywhere. Still more foundational than any "
         "feature gap — nothing this week changes that."),
        ("Decide what to do about Squads' simulated activity — still unresolved",
         "Confirmed unchanged this week. Member counts and daily completions are still "
         "generated by a seeded pseudo-random function (getGhostCompletions), not real "
         "users. No new disclosure incident found in the category this week, but the "
         "underlying trust risk (fake social-proof skepticism, faked leaderboard/"
         "activity data drawing backlash when discovered) is unchanged and unaddressed."),
        ("Connect a first wearable (Apple Health) — now more urgent, not less",
         "Confirmed unchanged in Vital Sync's source this week: zero wearable "
         "integrations. What changed is the competitive backdrop: Google's Gemini-"
         "powered Fitbit Premium coach ($9.99/mo, launched May 2026) now delivers the "
         "same 'read HRV/sleep, tell you what to do' output Vital Sync's Alignment "
         "engine already computes — at platform scale, on hardware many target users "
         "already wear. The algorithm gap was already closed (Alignment engine is "
         "genuinely competitive-grade); the data-supply gap is now competing against a "
         "much bigger, free-distribution rival, not just boutique apps."),
    ],
    "biggest_threat": (
        "NEW THIS WEEK, and arguably now bigger than Cora/Vora — Google's Gemini-"
        "powered Fitbit Premium health coach ($9.99/mo or $99.99/yr, launched May 19 "
        "2026): reads HRV/sleep/activity-load trends and generates personalized, "
        "continuously-adapting recovery-and-training recommendations, bundled free "
        "into Google AI Pro/Ultra subscriptions and running on an installed base of "
        "hundreds of millions of Fitbit/Pixel Watch devices. Cora and Vora remain live "
        "and stable (both confirmed unchanged on pricing/features this week) and are "
        "still the sharper boutique threat on specificity — but Fitbit's version of "
        "the same idea now ships at platform distribution scale most direct "
        "competitors, Vital Sync included, cannot match."
    ),
    "biggest_gap": (
        "Unchanged — nobody in the competitive set ties streak/gamification mechanics "
        "to real fatigue data, or eases gamification off for experienced users. This "
        "week strengthens the case that it's a solvable, proven-demand gap rather than "
        "an unproven idea: Gentler Streak, a live adjacent-category app, is built "
        "entirely around easing a streak/activity target to match daily capacity "
        "instead of punishing a miss — direct market validation for Vital Sync's "
        "backlogged fatigue-aware streak opportunity (#6), which nobody in the direct "
        "fitness-gamification set (Vora, Cora, FitCraft, Workout Quest, Habitica, "
        "Bitletics) has shipped yet."
    ),
    "biggest_weakness": (
        "Unchanged and re-verified — there is still no per-user data scoping anywhere "
        "in the backend (commit ef43285, identical to Brief 03); every route reads/"
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
        "matches Fitbit Premium's own $9.99/mo entry point — the engineering quality "
        "and price are both right for the category; the gap is still data supply and "
        "surfacing, not engineering or pricing."
    ),
    "one_to_ignore": (
        "Still: chasing deeper RPG mechanics (pets, gear, cosmetic avatars) to match "
        "FitCraft, Habitica or Workout Quest — saturated ground, low differentiation, "
        "and it plays away from Vital Sync's real structural advantage. Also not worth "
        "chasing this week: Bitletics' real-reward redemption model — its pricing is "
        "now confirmed (freemium, Pro adds challenges/raffle tickets), but it is still "
        "pre-launch beta with no user base to validate demand against, and trying to "
        "out-reward Google's platform-scale Fitbit Premium coach on distribution is "
        "not a fight Vital Sync can win directly — better to compete on the "
        "cross-system Alignment intelligence Fitbit doesn't build (nutrition/training/"
        "recovery tied together, not just recovery alone)."
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
        "commits since Brief 03 (`git log ef43285..origin/main` and `git diff --stat` "
        "both empty, verified against both the local clone and a fresh origin/main "
        "fetch). Every finding in the Current State table below is carried forward "
        "as-is, not re-derived from memory.",
        "SOURCE UNAVAILABLE (3rd consecutive week): vitalsyncify.com could not be "
        "reached this run — the sandbox's network egress proxy blocked it again "
        "(same failure mode as Briefs 02 and 03). Opportunity #3 (marketing/product "
        "mismatch) has now gone three weeks without independent re-verification; kept "
        "at BUILD NOW rather than downgraded, since absence of evidence isn't evidence "
        "of a fix, but this gap in coverage should be flagged to a human — consider an "
        "alternate verification path (e.g. a cached/indexed snapshot) if the direct "
        "egress block persists into next week.",
        "NEW INDIRECT COMPETITOR ADDED: Google's Gemini-powered Fitbit Premium health "
        "coach — $9.99/mo or $99.99/yr, launched May 19 2026, reads HRV/sleep/activity-"
        "load and generates adaptive recovery-and-training recommendations at platform "
        "scale (bundled into Google AI Pro/Ultra; runs on the existing Fitbit/Pixel "
        "Watch installed base). This was first surfaced as a market signal in the "
        "2026-08-12 verification-pass log entry and is now formally added to "
        "Competitor Watch and folded into Biggest Threat.",
        "COMPETITOR UPDATE: Bitletics' pricing model is now confirmed (was 'undisclosed' "
        "in Brief 03) — freemium, free at launch with no subscription required to earn "
        "rewards; a Pro tier adds weekly skill-based challenges and extra raffle "
        "tickets. Still pre-launch beta (iOS/Android launching together Q2/Q3 2026), "
        "so kept at MONITOR-tier, not elevated to a deep-dive threat.",
        "CONFIRMED UNCHANGED: Vora, Cora, FitCraft, Workout Quest, and Habitica are all "
        "re-checked this week with no material change in pricing or features from "
        "Brief 03.",
        "NEW MARKET SIGNAL: Gentler Streak — a live adjacent-category app whose entire "
        "premise is easing a streak/activity target to match daily capacity instead of "
        "punishing a miss — surfaced this week as direct market validation for Vital "
        "Sync's backlogged fatigue-aware streak opportunity (#6). No direct fitness-"
        "gamification competitor in the tracked set ships this yet.",
        "MARKET CONTEXT: New retention data this week quantifies the gamification "
        "thesis Vital Sync is betting on — apps with gamified loops see 15-20% higher "
        "30-day retention than static alternatives, and social/challenge/leaderboard "
        "features cut monthly churn 20-35% vs. solo-experience apps. Reinforces that "
        "Vital Sync's gamification core is a real retention lever, not just a "
        "differentiation play — separately, an Oct 2025 British Journal of Health "
        "Psychology finding (surfaced this week) shows app-set unreachable goals "
        "specifically drive churn, relevant context for how Boss Battles/Challenges "
        "difficulty is tuned.",
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
        "Marketing site materially understates the product (per Brief 02's check — "
        "vitalsyncify.com has now been unreachable for THREE consecutive weekly runs, "
        "network egress blocked in the sandbox each time, so this could not be "
        "re-verified either way again this week): Squads, billing, and the real AI "
        "chat coach weren't mentioned as of last check; \"Coming Soon\" AI partially "
        "already ships.",
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
         "leagues matched by fitness level; reads sleep/HR/recovery. Pricing now "
         "confirmed this week: free at launch (no subscription required to earn "
         "rewards), Pro tier adds weekly skill-based challenges + extra raffle "
         "tickets. Still pre-launch beta (iOS/Android launching together Q2/Q3 "
         "2026) — MONITOR, not yet a deep-dive threat."),
        ("Fitbit Premium (Gemini Health Coach)", "Indirect / Platform-scale",
         "NEW THIS WEEK: Google's Gemini-powered AI health coach, launched May 19 "
         "2026 — $9.99/mo or $99.99/yr, bundled free into Google AI Pro/Ultra. Reads "
         "HRV/sleep/activity-load trends from the existing Fitbit/Pixel Watch "
         "installed base and generates adaptive, continuously-updated recovery-and-"
         "training recommendations — the same category of output as Vital Sync's "
         "Alignment engine, at hardware-platform distribution scale. Not a "
         "fitness-gamification competitor (no XP/streaks/badges), but a direct "
         "threat to the 'wearable-driven adaptive coaching' value proposition."),
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
        "Fitness app churn is brutal — 9.2% monthly / 68% annual; 80% of users gone "
        "within 30 days; lost motivation cited in 38% of cancellations.",
        "Gamification's evidence base is real but bounded — small-to-medium, "
        "statistically significant effect across multiple RCT meta-analyses; long-term "
        "(multi-year) durability still under-studied.",
        "Computer-vision form-check and conversational coaching are named 2026 "
        "differentiators industry-wide — neither observed in Vital Sync's surface.",
    ],
    "gap_types": [
        ("-", "Foundational blocker", "Multi-user data scoping", "No route filters by "
         "userId anywhere in the backend — one global profile serves every request. "
         "Not a competitor comparison; a prerequisite for everything else to matter "
         "at real-user scale."),
        ("A", "Vital Sync behind", "Recovery/Alignment DATA SUPPLY (not logic)", "The "
         "scoring algorithms are real and competitive-grade; Cora/Vora/Bevel/NATE win "
         "only because they have wearable data feeding equivalent logic — and this "
         "week Google's Fitbit Premium Gemini Coach shows the same play at platform "
         "scale. Vital Sync's engine has zero wearable connections."),
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
        (3, "Fix the marketing/product mismatch", "Real AI chat coach and Stripe "
         "billing weren't mentioned on the site as of Brief 02; \"Coming Soon\" AI "
         "partially already ships. NOT RE-VERIFIED this week — vitalsyncify.com was "
         "unreachable (sandbox network egress blocked); kept at BUILD NOW rather than "
         "downgraded since absence of this week's evidence isn't evidence of a fix.",
         "BUILD NOW", "Trust", "No AI Needed", "HIGH"),
        (4, "Connect Apple Health as first wearable", "Broadest reach, lowest effort; "
         "feeds the already-working Alignment/Recovery algorithms with real data "
         "instead of building new logic. Urgency raised this week: Fitbit Premium's "
         "Gemini coach now ships the same 'wearable data -> adaptive guidance' output "
         "at platform scale, on hardware many target users already own.",
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
         "competitors. Pricing now confirmed (freemium, Pro adds challenges/raffle "
         "tickets) but still pre-launch beta with no user base yet; too early to act "
         "on, worth tracking.", "MONITOR", "D", "No AI Needed", "LOW"),
        (12, "Monitor Fitbit Premium's Gemini Coach as a platform-scale threat, not a "
         "build target", "Google now ships the same 'wearable data -> adaptive "
         "recovery/training guidance' output Vital Sync's Alignment engine produces, "
         "at hardware-platform distribution scale. Not something Vital Sync can "
         "out-build directly; sharpens the case for #4 (connect a wearable) and for "
         "leaning on cross-system Alignment (training+nutrition+recovery together) as "
         "the differentiator Fitbit doesn't offer.", "MONITOR", "A", "No AI Needed",
         "MEDIUM"),
    ],
    "opportunity_movement": [
        "#1, #2, #3 (BUILD NOW) — UNCHANGED, RE-VERIFIED, not re-asserted from "
        "memory. Vital-Sync HEAD is still ef43285 (`git log`/`git diff` against "
        "Brief 03's stored commit, and against a fresh origin/main fetch, both "
        "empty) — all three stand exactly as evidenced last week, still unresolved. "
        "#3 specifically stays CONFIDENCE CAVEATED for a third straight week: "
        "vitalsyncify.com was unreachable again this run (same sandbox egress "
        "block as Briefs 02 and 03), so the marketing mismatch could not be "
        "re-verified either way — kept at BUILD NOW rather than downgraded, since "
        "absence of evidence isn't evidence of a fix.",
        "#4 (Connect Apple Health as first wearable) — RE-RANKED IN URGENCY, not in "
        "position: still BUILD NOW/HIGH, but the evidence backing it got stronger. "
        "Google's Fitbit Premium Gemini Coach (new this week) proves the exact "
        "'wearable data -> adaptive guidance' output Vital Sync's Alignment engine "
        "already computes now ships at platform scale — the cost of staying "
        "unconnected to any wearable keeps rising.",
        "#6 (Fatigue-aware streak mechanic, BUILD NEXT) — CONFIDENCE RAISED "
        "MEDIUM -> HIGH. Gentler Streak, a live adjacent-category app surfaced this "
        "week, is built entirely around this exact mechanic (ease the target to "
        "match daily capacity, don't punish a miss) — this is no longer a "
        "theoretical opportunity, it's a proven, currently-unaddressed pattern in "
        "the direct fitness-gamification competitive set.",
        "NEW #12 (MONITOR) — Fitbit Premium's Gemini Coach didn't exist as a "
        "tracked competitor before this week (first flagged as a signal in the "
        "2026-08-12 verification-pass log, formally added now). Not a build target "
        "for Vital Sync — tracked as a platform-scale threat that sharpens the case "
        "for #4.",
        "#11 (Track Bitletics, MONITOR) — NOT RE-RANKED, evidence refined: pricing "
        "model is now confirmed (was undisclosed in Brief 03) but the app is still "
        "pre-launch beta, so it stays at LOW confidence.",
        "#9 (Gamification that tapers with Identity Rank, EXPERIMENT) — NOT "
        "RE-SCORED this week; no new evidence moved it beyond last week's Habitica-"
        "driven context.",
        "#5, #7, #8, #10 — UNCHANGED. No evidence this week (product-side or "
        "competitive) moved any of these; carried forward exactly as ranked in "
        "Brief 03.",
    ],
    "sources": [
        "github.com/faristjohar04-sketch/Vital-Sync (source code; re-verified via "
        "`git log`/`git diff` against both the local clone and a fresh origin/main "
        "fetch — HEAD unchanged at ef43285, zero commits since Brief 03)",
        "vitalsyncify.com — SOURCE UNAVAILABLE this run, 3rd consecutive week "
        "(sandbox network egress proxy blocked it, EGRESS_BLOCKED on WebFetch). Not "
        "re-verified this week; last confirmed state is Brief 02's.",
        "askvora.com, corahealth.app, getfitcraft.com, workoutquestapp.com, "
        "habitica.com — direct fetch also SOURCE UNAVAILABLE this run (same egress "
        "block); competitor data instead drawn from WebSearch-indexed pages on each "
        "domain (see individual Competitor Watch entries for specifics)",
        "bitletics.com (via WebSearch-indexed pages) — pricing model confirmation "
        "this week",
        "techcrunch.com, blog.google, mobihealthnews.com, store.google.com (via "
        "WebSearch) — Fitbit Premium / Gemini Health Coach launch details, pricing, "
        "and feature set; new competitor added this week",
        "WebSearch: new fitness gamification app launches Aug 2026, fitness app "
        "churn/retention benchmarks 2026 (retentioncheck.com, StriveCloud), streak-"
        "pressure/subscription-fatigue Reddit sentiment (SERP-indexed summaries — "
        "individual threads not independently verified this run), Gentler Streak "
        "app positioning, all-in-one fitness/nutrition/recovery app landscape scan "
        "(Hoola, Nutrola, and others — noted for future-week tracking, not deep-"
        "dived this run)",
        "JMIR mHealth 2022 meta-analysis; 36-RCT gamification meta-analysis "
        "(10,079 participants); Oct 2025 British Journal of Health Psychology "
        "(app-set unreachable goals drive churn) — carried/added as background, not "
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
