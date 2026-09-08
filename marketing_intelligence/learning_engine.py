"""Marketing Learnings (workflow sections 23-24): converts performance
analysis into durable, reusable lessons — but only when there's enough
evidence to trust it. A single data point never becomes a "learning";
MIN_EVIDENCE_POINTS mirrors the workflow's explicit instruction not to
generalize from one weak result.
"""

from datetime import datetime

MIN_EVIDENCE_POINTS = 3


def confidence_for(evidence_points: int) -> str:
    if evidence_points >= 8:
        return "High"
    if evidence_points >= 5:
        return "Medium"
    return "Low"


def derive_learnings(analysis_results: list, run_date=None) -> list:
    """analysis_results: output of performance_analyzer.analyze(). Returns
    new Marketing Learnings rows — empty when nothing yet clears the
    evidence bar (the honest, expected state on a fresh workbook)."""
    run_date = run_date or datetime.now()
    learnings = []
    for result in analysis_results:
        if result["evidence_points"] < MIN_EVIDENCE_POINTS:
            continue
        if result["verdict"] == "Insufficient Data":
            continue

        finding = (
            f"Campaign {result['campaign_id']} ({result['objective']}) is "
            f"{result['verdict'].lower()} based on {result['evidence_points']} "
            "performance data points."
        )
        action = (
            "Increase testing/spend on this angle." if result["verdict"] == "On/Above Target"
            else "Revisit or stop this angle; investigate root cause."
        )
        learnings.append({
            "Date": run_date,
            "Campaign ID": result["campaign_id"],
            "Finding": finding,
            "Evidence": f"{result['evidence_points']} Campaign Performance rows; metrics={result['metrics']}",
            "Confidence": confidence_for(result["evidence_points"]),
            "Action": action,
            "Status": "New",
        })
    return learnings
