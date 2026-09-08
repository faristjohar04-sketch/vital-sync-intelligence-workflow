"""Audience intelligence (workflow sections 16-17): identifies problems per
audience segment.

Honesty rule (section 16): this module has no access to real forum/review
text this run (Reddit is blocked — see market_research.py's documented
SOURCE UNAVAILABLE list; App Store/Play review scraping isn't implemented
yet). Every row it writes is therefore explicitly Source = "Derived
Audience Language" — a reasoned hypothesis about the segment, never
presented as a real quote. If a real-quote source is added later (e.g. a
working review-scraper), it should tag those rows "Real User Language" and
this module should leave them alone.

Frequency Signal is grounded, not guessed: it only goes above the floor
value for a problem cluster that this run's Market Signals harvest actually
touched (i.e. real autocomplete/derived queries this week matched that
cluster's topic) — otherwise it stays at the conservative floor.

Each catalog entry also carries a `product_feature` key — the real Vital
Sync capability (from product_intelligence.FEATURE_TAXONOMY) the resulting
campaign would be built around, replacing the old "Recommended Angle as a
stand-in feature key" simplification. `fallback_feature` is set only where
a BLOCKED primary claim has a genuine narrower reframe worth testing
instead (section 15's exact case: low-friction logging is blocked, but
"one place for training/nutrition/recovery" — the Alignment story — is
still real and marketable for the same audience/problem).
"""

SEGMENTS = [
    "Beginner",
    "Intermediate Gym User",
    "Athlete / Performance User",
    "Busy Professional",
    "Gamification-Driven User",
    "Data-Driven User",
]

# Section 16-17 catalog. Derived language is templated from the
# audience_problem, not a fabricated first-person quote.
PROBLEM_CATALOG = [
    {
        "segment": "Beginner", "pillar": "Fitness", "cluster": "Consistency",
        "problem": "Cannot maintain a repeatable workout routine.", "emotion": "Frustration",
        "angle": "Consistency without relying on motivation", "product_feature": "Gamification / Streaks",
    },
    {
        "segment": "Intermediate Gym User", "pillar": "Recovery", "cluster": "Recovery Confusion",
        "problem": "Cannot translate fatigue/recovery into a training decision.", "emotion": "Confusion",
        "angle": "Know when to push and when to recover", "product_feature": "Recovery Tracking",
    },
    {
        "segment": "Athlete / Performance User", "pillar": "Performance", "cluster": "Progress Confusion",
        "problem": "Cannot tell whether current training is producing real performance gains.",
        "emotion": "Uncertainty", "angle": "Turn training load into a clear performance signal",
        "product_feature": "Training Load Intelligence",
    },
    {
        "segment": "Busy Professional", "pillar": "Fitness", "cluster": "Logging Friction",
        "problem": "Tracking workouts and food takes too much time/effort to sustain.", "emotion": "Overwhelm",
        "angle": "Fast, low-friction tracking that fits a packed schedule",
        "product_feature": "Low-Friction Logging", "fallback_feature": "Alignment Engine",
    },
    {
        "segment": "Gamification-Driven User", "pillar": "Fitness", "cluster": "Motivation Dependence",
        "problem": "Loses motivation once novelty fades and progress feels invisible.", "emotion": "Boredom",
        "angle": "Turn consistency into a visible streak/achievement system",
        "product_feature": "Gamification / Streaks",
    },
    {
        "segment": "Data-Driven User", "pillar": "Cross-System", "cluster": "Tracking Fragmentation",
        "problem": "Training, nutrition and recovery data are spread across different tools.",
        "emotion": "Overwhelm", "angle": "Training. Nutrition. Recovery. One system.",
        "product_feature": "Alignment Engine",
    },
    {
        "segment": "Beginner", "pillar": "Nutrition", "cluster": "Nutrition Confusion",
        "problem": "Doesn't know what or how much to eat to support training goals.", "emotion": "Confusion",
        "angle": "Simple, goal-linked nutrition guidance", "product_feature": "Nutrition Guidance",
    },
    {
        "segment": "Intermediate Gym User", "pillar": "Fitness", "cluster": "Performance Plateaus",
        "problem": "Progress has stalled and it's unclear what to change.", "emotion": "Frustration",
        "angle": "Data-backed plateau-breaking recommendations",
        "product_feature": "Adaptive Workout Programming",
    },
    {
        "segment": "Data-Driven User", "pillar": "AI", "cluster": "Guidance Gap",
        "problem": "Logs data but doesn't get clear guidance from what it means.", "emotion": "Overwhelm",
        "angle": "Turn your fitness data into guidance", "product_feature": "AI Chat Coach",
    },
]


def score_frequency(cluster: str, touched_pillars: set) -> int:
    return 8 if cluster.lower() in touched_pillars or any(
        p.lower() in cluster.lower() for p in touched_pillars
    ) else 6


def harvest(existing_pool, market_signal_rows: list, stats, reality: dict = None) -> list:
    """market_signal_rows: this run's newly-found Market Signals (list of
    dicts) — used only to decide which problem clusters got real-world
    confirmation this week (see module docstring). reality: the Product
    Reality Map (product_intelligence.load_or_refresh()) — grounds this
    sheet's own Product Fit column in real product evidence instead of a
    flat guess, same as Campaign Opportunities now does."""
    import product_intelligence

    touched_pillars = {
        str(row.get("Primary Pillar", "")).lower() for row in market_signal_rows
    }
    segments_touched = set()
    new_rows = []

    for entry in PROBLEM_CATALOG:
        segment, cluster, problem = entry["segment"], entry["cluster"], entry["problem"]
        key = f"{segment} {cluster} {problem}"
        if existing_pool.find_duplicate(key):
            continue
        segments_touched.add(segment)
        frequency = score_frequency(cluster, touched_pillars)
        pain_severity = 8
        if reality is not None:
            resolved = product_intelligence.resolve_feature(reality, entry["product_feature"])
            product_fit = resolved["product_fit"]
        else:
            product_fit = 8
        content_potential = 8
        conversion_potential = 7

        row = {
            "Date Found": None,
            "Audience Segment": segment,
            "Primary Pillar": entry["pillar"],
            "Problem Cluster": cluster,
            "Audience Language": f"(Derived) \"{problem}\"",
            "Audience Problem": problem,
            "Emotional Driver": entry["emotion"],
            "Source": "Derived Audience Language",
            "Source Detail / URL": "Templated from audience segment catalog — not a real quote.",
            "Frequency Signal": frequency,
            "Pain Severity": pain_severity,
            "Product Fit": product_fit,
            "Content Potential": content_potential,
            "Conversion Potential": conversion_potential,
            "Priority": "High" if frequency >= 8 else "Medium",
            "Recommended Angle": entry["angle"],
            "Status": "New",
            "_product_feature": entry["product_feature"],       # not a sheet header — read by campaign_engine, dropped by workbook.write_row
            "_fallback_feature": entry.get("fallback_feature"),  # ditto
        }
        new_rows.append(row)
        existing_pool.add(key, row)

    stats.audience_segments = len(segments_touched) or stats.audience_segments
    return new_rows
