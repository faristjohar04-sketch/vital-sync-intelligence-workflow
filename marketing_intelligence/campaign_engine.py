"""Campaign opportunity generation (workflow sections 18-21, and the
Product Intelligence integration sections 3-20).

Product Intelligence is now a MANDATORY input (new architecture: Product
Intelligence -> Product Reality Map -> Market/Audience/Competitor ->
Opportunity Engine -> Campaigns). Every candidate campaign is resolved
against product_intelligence.resolve_feature() before it's allowed into
Campaign Opportunities:

  - Product Fit (a raw input to the sheet's own Opportunity Score formula)
    comes from real report evidence, banded per section 19 (LIVE +
    differentiating = 10, LIVE not unique = 8-9, PARTIAL = 6-7, weak/
    prototype = 3-5, missing = 0-2).
  - Product Fit <= 2 is a HARD gate (section 19): the campaign is written
    as Status = "BLOCKED BY PRODUCT" and excluded from BUILD NOW/TEST/
    MONITOR counts and the "Recommended Campaigns" report section —
    tracked instead as a Future Product-Dependent Campaign, never silently
    dropped (section 20's dedup/traceability principle still applies).
  - A PARTIAL claim gets Status = "QUALIFIER REQUIRED" and its Core
    Message is narrowed to what the product can actually back today
    (section 12), not just flagged and left as-is.
  - Where a blocked claim has a genuine narrower reframe on file
    (`fallback_feature` in audience_research.PROBLEM_CATALOG — currently
    only "low-friction logging" -> "Alignment", per section 15), the
    campaign is rebuilt around that instead of dropped.

"NEEDS PRODUCT INPUT" no longer exists as an outcome — that was the old
placeholder from before this integration (see workflow doc "Known
constraints"). Every campaign now gets a real LIVE/PARTIAL/MISSING read.
"""

import audience_research
import product_intelligence

# angle text -> catalog entry, for rows read back from the sheet that don't
# carry the "_product_feature"/"_fallback_feature" Python-only metadata
# (that metadata only exists in-memory the same run audience_research
# generated the row; a CAMPAIGN-only run re-reading a "New"-status
# Audience Problems row from the sheet a week later has no such luck —
# "Recommended Angle" is the one thing guaranteed still on the row).
_ANGLE_TO_CATALOG_ENTRY = {entry["angle"]: entry for entry in audience_research.PROBLEM_CATALOG}

CTA_BY_OBJECTIVE = {
    "Signup": ("Start with Vital Sync", "See how it works"),
    "Activation": ("Start Your Check-In", "Learn More"),
    "App Download": ("Get Vital Sync", "See Vital Sync"),
}

PLATFORM_BY_SEGMENT = {
    "Beginner": "TikTok",
    "Intermediate Gym User": "Instagram Reels",
    "Athlete / Performance User": "YouTube Shorts",
    "Busy Professional": "YouTube Shorts",
    "Gamification-Driven User": "TikTok",
    "Data-Driven User": "YouTube",
}


def _objective_for(problem_row: dict) -> str:
    cluster = str(problem_row.get("Problem Cluster", "")).lower()
    if "consistency" in cluster or "motivation" in cluster:
        return "App Download"
    if "confusion" in cluster or "plateau" in cluster:
        return "Activation"
    return "Signup"


def _confidence(product_fit: int, search_demand: int, pain_severity: int, competitive_gap: int) -> str:
    """Section 20: confidence reflects real evidence across all four
    categories, not a blanket LOW just because a human didn't hand-type a
    Product Feature — that gap is exactly what this integration closes."""
    evidence_count = sum([
        product_fit >= 8, search_demand >= 7, pain_severity >= 8, competitive_gap >= 7,
    ])
    if evidence_count >= 3:
        return "High"
    if evidence_count == 2:
        return "Medium"
    return "Low"


def build_campaign(problem_row: dict, matching_signal: dict, run_date, reality: dict) -> dict:
    segment = problem_row.get("Audience Segment", "Unknown")
    catalog_entry = _ANGLE_TO_CATALOG_ENTRY.get(problem_row.get("Recommended Angle", ""))
    feature_key = (
        problem_row.get("_product_feature")
        or (catalog_entry["product_feature"] if catalog_entry else None)
        or problem_row.get("Recommended Angle", "")
    )
    fallback_key = problem_row.get("_fallback_feature") or (catalog_entry.get("fallback_feature") if catalog_entry else None)

    resolved = product_intelligence.resolve_feature(reality, feature_key)
    dependency = product_intelligence.dependency_label(resolved["product_fit"], resolved["claim_status"])
    core_message = problem_row.get("Recommended Angle", "")
    reframed = False

    if dependency == "BLOCKED BY PRODUCT" and fallback_key:
        fallback_resolved = product_intelligence.resolve_feature(reality, fallback_key)
        fallback_dependency = product_intelligence.dependency_label(
            fallback_resolved["product_fit"], fallback_resolved["claim_status"]
        )
        if fallback_dependency != "BLOCKED BY PRODUCT":
            reframed = True
            # Look up the reframe message by the ORIGINAL blocked feature
            # (e.g. "Low-Friction Logging" -> "One place for training,
            # nutrition and recovery.") — not by the fallback feature name,
            # which has no entry of its own in QUALIFIER_MESSAGES.
            core_message = product_intelligence.QUALIFIER_MESSAGES.get(feature_key, core_message)
            feature_key, resolved, dependency = fallback_key, fallback_resolved, fallback_dependency
    elif dependency == "QUALIFIER REQUIRED":
        core_message = product_intelligence.QUALIFIER_MESSAGES.get(feature_key, core_message)

    objective = _objective_for(problem_row)
    primary_cta, secondary_cta = CTA_BY_OBJECTIVE.get(objective, ("Start with Vital Sync", "Learn More"))
    platform = PLATFORM_BY_SEGMENT.get(segment, "Instagram Reels")

    pain_severity = int(problem_row.get("Pain Severity") or 5)
    content_potential = int(problem_row.get("Content Potential") or 5)
    conversion_potential = int(problem_row.get("Conversion Potential") or 5)
    search_demand = int(matching_signal.get("Demand Score") or 5) if matching_signal else 4
    competitive_gap = product_intelligence.competitive_gap_score(feature_key, reality)
    audience_relevance = int(problem_row.get("Frequency Signal") or 5)
    ease_of_execution = 8 if dependency in ("READY TO MARKET", "SAFE TEST") else (
        5 if dependency == "QUALIFIER REQUIRED" else 2
    )
    confidence = _confidence(resolved["product_fit"], search_demand, pain_severity, competitive_gap)

    campaign_name = core_message[:60] if core_message else f"{segment} Campaign"

    notes_parts = [
        f"Product status: {resolved['final_status']} "
        f"(area: {resolved['area_matched'] or 'not tracked'}). {resolved['evidence']}"[:280],
        f"Claim classification: {resolved['claim_status']}.",
    ]
    if reframed:
        notes_parts.insert(0, f"Reframed from '{problem_row.get('_product_feature')}' (blocked) to '{feature_key}'.")
    if dependency == "BLOCKED BY PRODUCT":
        notes_parts.append(f"BLOCKED BY PRODUCT — dependency: {feature_key} implementation. Do not market now.")

    return {
        "Date Created": run_date,
        "Campaign Name": campaign_name,
        "Objective": objective,
        "Audience Segment": segment,
        "Audience Problem": problem_row.get("Audience Problem", ""),
        "Core Insight": problem_row.get("Audience Problem", ""),
        "Core Message": core_message,
        "Marketing Angle": problem_row.get("Recommended Angle", ""),
        "Offer": "Start with Vital Sync",
        "Primary CTA": primary_cta,
        "Secondary CTA": secondary_cta,
        "Platform": platform,
        "Format": "UGC Short" if platform in ("TikTok", "Instagram Reels") else "Short-form",
        "Product Feature": f"{feature_key} ({resolved['final_status']})",
        "Evidence / Research Basis": (
            f"Audience Problem ({problem_row.get('Problem ID', '?')})"
            + (f" + Market Signal ({matching_signal.get('Signal ID', '?')})" if matching_signal else "")
            + f" + Product Intelligence ({reality.get('report_date', 'unknown date')})"
        ),
        "Confidence": confidence,
        "Status": dependency,
        "Test Hypothesis": (
            f"{segment} users shown this angle will show higher {objective.lower()} intent."
        ),
        "Success Metric": {
            "Signup": "Signup Rate", "Activation": "Activation Rate", "App Download": "App Download Rate",
        }.get(objective, "Signup Rate"),
        "Human Approval": "Pending",
        "Notes": " ".join(notes_parts),
        "Audience Relevance": audience_relevance,
        "Pain Severity": pain_severity,
        "Search Demand": search_demand,
        "Competitive Gap": competitive_gap,
        "Product Fit": resolved["product_fit"],
        "Content Potential": content_potential,
        "Conversion Potential": conversion_potential,
        "Ease of Execution": ease_of_execution,
        "_dependency_label": dependency,  # not a sheet header — read by runner/report_generator
    }


# Fields refreshed on an existing row when Product Intelligence reclassifies
# it (section 20: UPDATE/EVOLVE in place, never a silent duplicate) — kept
# narrow on purpose: only what Product Intelligence actually informs.
# Campaign identity (Name, Date Created, Audience, Platform, CTAs, ...) is
# left exactly as a human last saw it.
RECLASSIFY_FIELDS = [
    "Product Feature", "Status", "Confidence", "Core Message", "Notes",
    "Product Fit", "Competitive Gap", "Ease of Execution",
]


def _needs_reclassification(existing_row: dict, fresh_campaign: dict) -> bool:
    return any(
        str(existing_row.get(f, "")) != str(fresh_campaign.get(f, ""))
        for f in ("Status", "Product Feature", "Confidence")
    )


def generate(
    audience_problem_rows: list,
    market_signal_rows: list,
    existing_pool,
    run_date,
    stats,
    reality: dict,
    max_campaigns: int = 8,
) -> tuple:
    """Returns (new_campaigns, campaign_updates).

    new_campaigns: brand-new Campaign Opportunity rows (including BLOCKED
    BY PRODUCT ones — runner.py buckets those into the "Future Product-
    Dependent Campaigns" report section rather than dropping them).

    campaign_updates: [(row_idx, {field: value})] for EXISTING Campaign
    Opportunities rows whose concept already matches a fresh candidate —
    reclassified in place (Status/Confidence/Product Feature/Core Message)
    instead of being silently skipped as a duplicate. This is what actually
    fixes stale "NEEDS PRODUCT INPUT" rows left over from before this
    Product Intelligence integration existed (section 20's UPDATE/EVOLVE
    principle, section 12's "fix NEEDS PRODUCT INPUT" instruction).
    """
    import duplicate_detector

    signals_by_pillar = {}
    for sig in market_signal_rows:
        signals_by_pillar.setdefault(str(sig.get("Primary Pillar", "")), []).append(sig)

    ranked = sorted(
        audience_problem_rows,
        key=lambda r: (r.get("Priority") != "High", -(int(r.get("Pain Severity") or 0))),
    )

    new_campaigns, campaign_updates = [], []
    for problem_row in ranked:
        if len(new_campaigns) >= max_campaigns:
            break
        matching_signal = None
        candidates = signals_by_pillar.get(str(problem_row.get("Primary Pillar", "")))
        if candidates:
            matching_signal = candidates[0]

        campaign = build_campaign(problem_row, matching_signal, run_date, reality)
        key = duplicate_detector.campaign_key(campaign)
        existing_match = existing_pool.find_duplicate(key)
        if existing_match:
            stats.rejected += 1
            row_idx = existing_match.get("_row_idx")
            if (
                existing_match.get("_sheet") == "Campaign Opportunities"
                and row_idx
                and _needs_reclassification(existing_match, campaign)
            ):
                campaign_updates.append((row_idx, {f: campaign[f] for f in RECLASSIFY_FIELDS}))
            continue

        new_campaigns.append(campaign)
        existing_pool.add(key, campaign)
        stats.opportunities_generated += 1

    return new_campaigns, campaign_updates


def classify_after_write(opportunity_score) -> str:
    """Mirrors the workbook's own IF formula (BUILD NOW/TEST/MONITOR/
    IGNORE, driven purely by the score average) — used only for run-summary
    / PDF purposes, never written back over the real formula cell. This is
    a SEPARATE axis from the product-dependency label above: a campaign can
    score well on the formula's raw average and still be BLOCKED BY PRODUCT
    if Product Fit alone is <= 2 (see module docstring) — callers that need
    the authoritative "should this be treated as actionable" answer should
    use the Status field's dependency label, not this."""
    import config
    thresholds = config.load_thresholds()
    if opportunity_score is None or opportunity_score == "":
        return ""
    score = float(opportunity_score)
    if score >= thresholds["opportunity_threshold"]:
        return "BUILD NOW"
    if score >= thresholds["test_threshold"]:
        return "TEST"
    if score >= thresholds["monitor_threshold"]:
        return "MONITOR"
    return "IGNORE"
