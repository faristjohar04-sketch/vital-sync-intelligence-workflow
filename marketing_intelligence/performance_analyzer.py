"""Performance analysis (workflow section 22): reads Active Campaigns +
Campaign Performance and judges each campaign against the metric that
matches ITS OWN objective — never by views alone.
"""

OBJECTIVE_METRIC = {
    "Awareness": ("Reach", "Watch Time"),
    "Traffic": ("CTR", "Landing Visits"),
    "Signup": ("Signup Rate",),
    "Activation": ("Activation Rate",),
    "Paid Conversion": ("CAC", "ROAS"),
}


def analyze(active_campaigns: list, performance_rows: list) -> list:
    """Returns a list of {campaign_id, objective, metric_used, value,
    verdict, evidence_points} — one per campaign that has both an Active
    Campaigns record and at least one Campaign Performance row.

    With an empty/template workbook (no campaigns launched yet) this
    correctly returns an empty list — there is nothing to analyze until a
    human approves and launches a campaign (section 21)."""
    perf_by_campaign = {}
    for row in performance_rows:
        cid = row.get("Campaign ID")
        if not cid:
            continue
        perf_by_campaign.setdefault(cid, []).append(row)

    results = []
    for campaign in active_campaigns:
        cid = campaign.get("Campaign ID")
        if not cid or cid not in perf_by_campaign:
            continue
        objective = campaign.get("Objective", "")
        metrics = OBJECTIVE_METRIC.get(objective, ("Signup Rate",))
        rows = perf_by_campaign[cid]

        values = {}
        for metric in metrics:
            observed = [r.get(metric) for r in rows if isinstance(r.get(metric), (int, float))]
            if observed:
                values[metric] = sum(observed) / len(observed)

        target = campaign.get("Target")
        current_result = campaign.get("Current Result")
        verdict = "Insufficient Data"
        if target not in (None, "") and current_result not in (None, ""):
            try:
                verdict = "On/Above Target" if float(current_result) >= float(target) else "Below Target"
            except (TypeError, ValueError):
                pass

        results.append({
            "campaign_id": cid,
            "objective": objective,
            "metrics": values,
            "evidence_points": len(rows),
            "verdict": verdict,
        })
    return results
