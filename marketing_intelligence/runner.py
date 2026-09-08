"""The single Marketing Intelligence Runner (workflow section 7): every
mode — scheduled weekly, manual RUN NOW, or any specialized run — calls
run() below. There is no separate code path for scheduled vs. manual, so
the two can never produce different results.

New architecture (Product Intelligence integration): every FULL/WEEKLY/
AUDIENCE/CAMPAIGN run loads the Product Reality Map FIRST and threads it
through audience scoring and campaign generation —

    Product Intelligence -> Product Reality Map -> Market Intelligence
        -> Audience Intelligence -> Competitor Intelligence
        -> Marketing Opportunity Engine -> Campaign Recommendations

— so campaigns are gated by what Vital Sync can actually do before
anything else runs. See product_intelligence.py for the extraction/scoring
logic this depends on.
"""

import json
from datetime import datetime

import audience_research
import campaign_engine
import competitor_research
import config
import duplicate_detector
import learning_engine
import logger
import market_research
import performance_analyzer
import product_intelligence
import report_generator
import workbook
import workflow_lock
from config import STATE_DIR

MODES = {
    "FULL": "RUN FULL MARKETING INTELLIGENCE",
    "WEEKLY": "RUN WEEKLY MARKETING INTELLIGENCE",
    "MARKET_RESEARCH": "RUN MARKET RESEARCH",
    "COMPETITOR": "RUN COMPETITOR INTELLIGENCE",
    "AUDIENCE": "RUN AUDIENCE INTELLIGENCE",
    "CAMPAIGN": "RUN CAMPAIGN INTELLIGENCE",
    "PERFORMANCE": "RUN PERFORMANCE ANALYSIS",
}
FULL_MODES = {"FULL", "WEEKLY"}

LAST_PRODUCT_REPORT_FILE = STATE_DIR / "last_marketing_product_report.json"
BLOCKED_STATUSES = {"BLOCKED BY PRODUCT", "FUTURE CAMPAIGN"}


class RunResult:
    def __init__(self, stats, dry_run: bool):
        self.stats = stats
        self.dry_run = dry_run
        self.report_path = None
        self.summary_lines = []


def _read_all(wb) -> dict:
    """Pre-run check (section 8): reads every sheet the workflow needs
    before doing any new research."""
    data = {}
    for sheet in [
        "Market Signals", "Competitor Intelligence", "Audience Problems",
        "Campaign Opportunities", "Active Campaigns", "Campaign Performance",
        "Marketing Learnings", "Automation Logs",
    ]:
        ws = wb[sheet]
        fcols = workbook.formula_columns(ws)
        data[sheet] = list(workbook.iter_data_rows(ws, fcols))
    return data


def _sync_thresholds_from_config_sheet(wb) -> None:
    ws = wb["Config & Lists"]
    idx = workbook.header_index(ws)
    setting_col, value_col = idx.get("Setting"), idx.get("Value")
    if not setting_col or not value_col:
        return
    settings = {}
    for row in ws.iter_rows(min_row=4, max_row=ws.max_row):
        key = row[setting_col - 1].value
        val = row[value_col - 1].value
        if key:
            settings[key] = val
    updates = {}
    if "Default Opportunity Threshold" in settings:
        try:
            updates["opportunity_threshold"] = float(settings["Default Opportunity Threshold"])
        except (TypeError, ValueError):
            pass
    if "Default Test Threshold" in settings:
        try:
            updates["test_threshold"] = float(settings["Default Test Threshold"])
        except (TypeError, ValueError):
            pass
    if updates:
        config.save_thresholds(updates)


def _seed_pools(existing: dict) -> dict:
    signal_pool = duplicate_detector.DuplicatePool()
    for _, row in existing["Market Signals"]:
        signal_pool.add(duplicate_detector.signal_key(row), row)

    problem_pool = duplicate_detector.DuplicatePool()
    for _, row in existing["Audience Problems"]:
        problem_pool.add(duplicate_detector.audience_problem_key(row), row)

    campaign_pool = duplicate_detector.DuplicatePool()
    for sheet in ("Campaign Opportunities", "Active Campaigns"):
        for row_idx, row in existing[sheet]:
            key = duplicate_detector.campaign_key(row)
            if key.strip():
                enriched = dict(row)
                enriched["_row_idx"], enriched["_sheet"] = row_idx, sheet
                campaign_pool.add(key, enriched)

    competitor_existing = {}
    for row_idx, row in existing["Competitor Intelligence"]:
        name = row.get("Competitor")
        if name:
            competitor_existing[name] = (row_idx, row)

    return {
        "signals": signal_pool, "problems": problem_pool,
        "campaigns": campaign_pool, "competitors": competitor_existing,
    }


def _formula_classify(campaign: dict) -> str:
    """What the SHEET'S OWN Opportunity Score formula would show
    (BUILD NOW/TEST/MONITOR/IGNORE) — informational only. The authoritative
    "is this actionable" answer is the campaign's Status field (the
    product-dependency label from campaign_engine), not this."""
    inputs = [campaign.get(k) for k in (
        "Audience Relevance", "Pain Severity", "Search Demand", "Competitive Gap",
        "Product Fit", "Content Potential", "Conversion Potential", "Ease of Execution",
    )]
    inputs = [i for i in inputs if isinstance(i, (int, float))]
    if not inputs:
        return ""
    score = round(sum(inputs) / len(inputs), 1)
    return campaign_engine.classify_after_write(score)


def run(mode: str, trigger: str, dry_run: bool = False) -> RunResult:
    if mode not in MODES:
        raise ValueError(f"Unknown mode: {mode}")
    run_id = logger.new_run_id()
    stats = logger.RunStats(run_id=run_id, workflow=MODES[mode], trigger=trigger)
    logger.log_line(f"START run_id={run_id} mode={mode} trigger={trigger} dry_run={dry_run}")

    try:
        with workflow_lock.acquire(run_id, trigger):
            result = _run_locked(mode, dry_run, stats)
    except workflow_lock.WorkflowAlreadyRunning as exc:
        stats.success = False
        stats.errors.append(str(exc))
        logger.log_line(str(exc))
        result = RunResult(stats, dry_run)
        result.summary_lines.append(str(exc))
        return result
    except Exception as exc:  # noqa: BLE001
        stats.note_error("run", str(exc))
        logger.log_line(f"FAILED run_id={run_id}: {exc}")
        raise

    logger.log_line(f"END run_id={run_id} success={stats.success} duration={stats.duration_seconds()}s")
    return result


def _load_last_product_report() -> dict:
    if LAST_PRODUCT_REPORT_FILE.exists():
        try:
            with open(LAST_PRODUCT_REPORT_FILE) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_last_product_report(reality: dict) -> None:
    tmp = LAST_PRODUCT_REPORT_FILE.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump({
            "report_file": reality.get("report_file"),
            "report_date": reality.get("report_date"),
            "product_state_version": reality.get("product_state_version"),
            "freshness": (reality.get("freshness_info") or {}).get("freshness"),
        }, f)
    import os
    os.replace(tmp, LAST_PRODUCT_REPORT_FILE)


def _product_changes_since_previous(reality: dict) -> str:
    """Product-reality refresh spec, section 25: this is a PRODUCT-facing
    fact only ("did Workflow 01's verified product state move?"), never a
    file-identity fact ("did the PDF path change?"). Those used to be
    treated as the same question — exactly how a same-day, freshly
    reconciled Brief 07 could still get reported as "Unchanged — still
    reading [stale Brief 06]'s report" the one run that happened to fire
    before Brief 07 existed on disk."""
    previous = _load_last_product_report()
    prev_file = previous.get("report_file")
    freshness_now = (reality.get("freshness_info") or {}).get("freshness")
    if not prev_file:
        return "No prior marketing run on record — this is the first run using Product Intelligence."
    if prev_file == reality.get("report_file"):
        if freshness_now not in product_intelligence.FRESH_ENOUGH:
            return (
                f"Unchanged file ({reality.get('report_date', 'unknown date')}'s report) AND "
                f"Workflow 01 itself marks this product state '{freshness_now}' — do not read "
                "this as 'nothing has changed', only as 'nothing newer was available to this run'."
            )
        return f"Unchanged — still reading {reality.get('report_date', 'unknown date')}'s CURRENT_VERIFIED report (no newer one published)."
    if previous.get("product_state_version") and previous.get("product_state_version") == reality.get("product_state_version"):
        return (
            f"Report file advanced ({previous.get('report_date', 'unknown')} -> {reality.get('report_date', 'unknown')}) "
            "but the underlying verified product state did not — same product_state_version."
        )
    return (
        f"Product Intelligence advanced from {previous.get('report_date', 'unknown')} "
        f"(freshness was {previous.get('freshness', 'unknown')}) to {reality.get('report_date', 'unknown')} "
        f"(now {freshness_now}) since the last marketing run."
    )


def _run_locked(mode: str, dry_run: bool, stats) -> RunResult:
    run_date = datetime.now()
    result = RunResult(stats, dry_run)

    # --- Load + pre-run checks (section 8) ------------------------------
    workbook.locate()  # raises WorkbookNotFoundError early if missing
    read_wb = workbook.load(data_only=True)
    existing = _read_all(read_wb)
    _sync_thresholds_from_config_sheet(read_wb)
    pools = _seed_pools(existing)

    # --- Product Intelligence -> Product Reality Map (mandatory input) ----
    reality = product_intelligence.load_or_refresh()
    stale = product_intelligence.is_stale(reality, run_date.date())
    product_changes_note = _product_changes_since_previous(reality)
    if reality.get("error"):
        logger.log_line(f"PRODUCT INTELLIGENCE UNAVAILABLE: {reality['error']}")
    freshness_info = reality.get("freshness_info") or {}
    if stale:
        logger.log_line(
            f"PRODUCT INTELLIGENCE NOT CURRENT — Product Freshness Gate reports "
            f"'{freshness_info.get('freshness', 'UNKNOWN')}' ({freshness_info.get('warning', 'no warning text on file')})."
        )

    new_signals, new_problems, competitor_updates, new_competitors = [], [], [], []
    competitor_update_summaries = []
    new_campaigns, learnings, demand_signals = [], [], []
    perf_analysis = []

    noise_removed = []
    if mode in FULL_MODES or mode == "MARKET_RESEARCH":
        new_signals = market_research.harvest(pools["signals"], stats)
        noise_removed = list(market_research.last_noise_removed)
        for row in new_signals:
            row["Date Found"] = run_date
        demand_signals = product_intelligence.generate_demand_signals(new_signals, reality)
        for row in demand_signals:
            row["Date Found"] = run_date

    if mode in FULL_MODES or mode == "AUDIENCE":
        new_problems = audience_research.harvest(pools["problems"], new_signals, stats, reality)
        for row in new_problems:
            row["Date Found"] = run_date

    if mode in FULL_MODES or mode == "COMPETITOR":
        updates, new_competitors = competitor_research.research(pools["competitors"], stats)
        for _, upd in updates:
            upd["Date Checked"] = run_date
        for row in new_competitors:
            row["Date Checked"] = run_date
        competitor_updates = updates
        row_idx_to_name = {row_idx: name for name, (row_idx, _) in pools["competitors"].items()}
        # Section 18: a "Date Checked" refresh with no actual homepage diff
        # is NOT a competitor change — competitor_research.research() only
        # sets "Recent Change" when diff_snapshot() found a real title/
        # description difference, so its absence here means "checked, no
        # material change" specifically, not "unknown". Keep both kinds
        # visible, but only the material ones count as a change.
        competitor_update_summaries = [
            {
                "name": row_idx_to_name.get(row_idx, f"row {row_idx}"),
                "change": upd.get("Recent Change") or "CHECKED — NO MATERIAL CHANGE (Date Checked updated only).",
                "action": "MONITOR",
                "material": bool(upd.get("Recent Change")),
            }
            for row_idx, upd in updates
        ]

    campaign_updates = []
    if mode in FULL_MODES or mode == "CAMPAIGN":
        # CAMPAIGN-only uses EXISTING unprocessed intelligence, not a fresh
        # harvest (section 29) — falls back to this run's fresh rows first.
        signal_source = new_signals or [r for _, r in existing["Market Signals"] if r.get("Status") == "New"]
        # Concatenate, not "or": existing "New"-status Audience Problems
        # rows must be re-evaluated every run too (not only when nothing
        # fresh was found this run) — that's what lets a stale existing
        # Campaign Opportunities row actually get reclassified once its
        # underlying audience problem is fed through campaign_engine again.
        problem_source = new_problems + [r for _, r in existing["Audience Problems"] if r.get("Status") == "New"]
        new_campaigns, campaign_updates = campaign_engine.generate(
            problem_source, signal_source, pools["campaigns"], run_date, stats, reality,
        )

    if mode in FULL_MODES or mode == "PERFORMANCE":
        perf_analysis = performance_analyzer.analyze(
            [r for _, r in existing["Active Campaigns"]],
            [r for _, r in existing["Campaign Performance"]],
        )
        learnings = learning_engine.derive_learnings(perf_analysis, run_date)

    recommended_campaigns = [c for c in new_campaigns if c["Status"] not in BLOCKED_STATUSES]
    future_campaigns = [c for c in new_campaigns if c["Status"] in BLOCKED_STATUSES]
    stats.build_now = sum(1 for c in new_campaigns if c["Status"] == "READY TO MARKET")
    stats.tests = sum(1 for c in new_campaigns if c["Status"] in ("SAFE TEST", "QUALIFIER REQUIRED"))
    stats.monitors = sum(1 for c in new_campaigns if c["Status"] == "FUTURE CAMPAIGN")

    # --- Write phase ------------------------------------------------------
    if dry_run:
        logger.dry_run_log(stats)
        result.summary_lines = _dry_run_summary(
            new_signals, new_problems, new_competitors, competitor_updates,
            new_campaigns, campaign_updates, learnings, demand_signals, reality, stale,
        )
    else:
        with workbook.safe_write() as wb:
            _write_all(
                wb, new_signals, new_problems, new_competitors,
                competitor_updates, new_campaigns, campaign_updates, learnings, demand_signals,
            )
            logger.write_automation_log(wb, stats)
        if mode in FULL_MODES:
            _save_last_product_report(reality)

    # --- PDF report (full/weekly runs only) -------------------------------
    if mode in FULL_MODES:
        context = _build_report_context(
            mode, run_date, new_signals, new_problems, new_competitors,
            competitor_updates, competitor_update_summaries, recommended_campaigns,
            future_campaigns, campaign_updates, perf_analysis, learnings, demand_signals, reality,
            stale, product_changes_note, existing, noise_removed,
        )
        # A DRY RUN still renders a real PDF (marked PREVIEW, distinct
        # filename — see report_generator.build's preview arg) so a human
        # can actually look at the report before approving a real run.
        # Only the workbook write is skipped in dry-run mode.
        report_path = report_generator.build(context, preview=dry_run)
        result.report_path = report_path
        if not dry_run:
            stats.report_file = report_path
        else:
            result.summary_lines.append(f"[DRY RUN] Preview report generated (not an official run): {report_path}")

    return result


def _write_all(wb, new_signals, new_problems, new_competitors, competitor_updates, new_campaigns, campaign_updates, learnings, demand_signals):
    def append_all(sheet_name, rows):
        if not rows:
            return
        ws = wb[sheet_name]
        fcols = workbook.formula_columns(ws)
        for row in rows:
            row_idx = workbook.next_empty_row(ws, fcols)
            workbook.write_row(ws, row_idx, row, fcols)

    import uuid

    for row in new_signals:
        row.setdefault("Signal ID", f"MS-{uuid.uuid4().hex[:8].upper()}")
    for row in new_problems:
        row.setdefault("Problem ID", f"AP-{uuid.uuid4().hex[:8].upper()}")
    for row in new_competitors:
        row.setdefault("Competitor ID", f"COMP-{uuid.uuid4().hex[:8].upper()}")
    for row in new_campaigns:
        row.setdefault("Campaign ID", f"CAM-{uuid.uuid4().hex[:8].upper()}")
    for row in learnings:
        row.setdefault("Learning ID", f"LRN-{uuid.uuid4().hex[:8].upper()}")
    for row in demand_signals:
        row.setdefault("Signal ID", f"PDS-{uuid.uuid4().hex[:8].upper()}")

    append_all("Market Signals", new_signals)
    append_all("Audience Problems", new_problems)
    append_all("Competitor Intelligence", new_competitors)
    append_all("Campaign Opportunities", new_campaigns)
    append_all("Marketing Learnings", learnings)

    if demand_signals:
        ws = workbook.ensure_sheet(wb, config.PRODUCT_DEMAND_SIGNALS_SHEET, config.PRODUCT_DEMAND_SIGNALS_HEADERS)
        fcols = workbook.formula_columns(ws)
        for row in demand_signals:
            row_idx = workbook.next_empty_row(ws, fcols)
            workbook.write_row(ws, row_idx, row, fcols)

    if competitor_updates:
        ws = wb["Competitor Intelligence"]
        fcols = workbook.formula_columns(ws)
        for row_idx, updates in competitor_updates:
            workbook.write_row(ws, row_idx, updates, fcols)

    if campaign_updates:
        ws = wb["Campaign Opportunities"]
        fcols = workbook.formula_columns(ws)
        for row_idx, updates in campaign_updates:
            workbook.write_row(ws, row_idx, updates, fcols)


def _dry_run_summary(new_signals, new_problems, new_competitors, competitor_updates, new_campaigns, campaign_updates, learnings, demand_signals, reality, stale):
    freshness_info = reality.get("freshness_info") or {}
    lines = [
        f"Product Intelligence report: {reality.get('report_file') or 'NONE FOUND'} (dated {reality.get('report_date')})",
        f"Product Freshness Gate: {freshness_info.get('freshness', 'UNKNOWN')} "
        f"(confidence {freshness_info.get('confidence', 'UNKNOWN')}, source {freshness_info.get('source') or 'none'})"
        + (f"  *** {freshness_info.get('warning')} ***" if stale and freshness_info.get("warning") else ""),
        f"[DRY RUN] Would add {len(new_signals)} Market Signals rows.",
        f"[DRY RUN] Would add {len(new_problems)} Audience Problems rows.",
        f"[DRY RUN] Would add {len(new_competitors)} new Competitor Intelligence rows, "
        f"update {len(competitor_updates)} existing ones.",
        f"[DRY RUN] Would add {len(new_campaigns)} Campaign Opportunities rows, "
        f"reclassify {len(campaign_updates)} existing ones in place.",
        f"[DRY RUN] Would add {len(demand_signals)} Product Demand Signals rows.",
        f"[DRY RUN] Would add {len(learnings)} Marketing Learnings rows.",
        "[DRY RUN] Workbook was NOT modified.",
    ]
    for c in new_campaigns:
        lines.append(f"    - Candidate campaign: \"{c['Campaign Name']}\" -> {c['Status']} (Product Fit={c['Product Fit']}, Confidence={c['Confidence']})")
    for row_idx, updates in campaign_updates:
        lines.append(f"    - Would reclassify row {row_idx}: Status -> {updates['Status']}, Product Feature -> {updates['Product Feature']}")
    return lines


def _build_opportunity_map(reality: dict, market_signal_rows: list, audience_problem_rows: list) -> list:
    """Section 23: PRODUCT x MARKET OPPORTUNITY MAP — one row per taxonomy
    feature, combining live product status with real market/audience
    signal counts already gathered this run."""
    rows = []
    for feature_key in product_intelligence.FEATURE_TAXONOMY:
        resolved = product_intelligence.resolve_feature(reality, feature_key)
        dep = product_intelligence.dependency_label(resolved["product_fit"], resolved["claim_status"])

        tokens = feature_key.lower().split()
        market_hits = [
            s for s in market_signal_rows
            if any(t in f"{s.get('Topic', '')} {s.get('Search / Social Query', '')}".lower() for t in tokens if len(t) > 3)
        ]
        audience_hits = [
            a for a in audience_problem_rows
            if a.get("_product_feature") == feature_key or feature_key.lower() in str(a.get("Recommended Angle", "")).lower()
        ]
        market_demand = "High" if len(market_hits) >= 3 else ("Medium" if market_hits else "Low")
        audience_pain = "High" if any(int(a.get("Pain Severity") or 0) >= 8 for a in audience_hits) else (
            "Medium" if audience_hits else "Unknown"
        )

        recommendation = {
            "READY TO MARKET": "MARKET NOW",
            "SAFE TEST": "TEST",
            "QUALIFIER REQUIRED": "NARROW & TEST",
            "FUTURE CAMPAIGN": "MONITOR / PRODUCT OPPORTUNITY",
            "BLOCKED BY PRODUCT": "BUILD PRODUCT FIRST",
        }[dep]

        rows.append({
            "opportunity": feature_key,
            "market_demand": market_demand,
            "audience_pain": audience_pain,
            "product_status": resolved["final_status"],
            "competitive_gap": product_intelligence.competitive_gap_score(feature_key, reality),
            "marketing_potential": "High" if dep in ("READY TO MARKET", "SAFE TEST") else (
                "Medium" if dep == "QUALIFIER REQUIRED" else "Low"
            ),
            "product_dependency": dep,
            "recommendation": recommendation,
        })
    return rows


def _reclassify_existing_campaigns(existing_campaign_rows: list, reality: dict, run_date) -> list:
    """Section 38: for every existing Campaign Opportunities row whose
    Marketing Angle matches a known audience_research.PROBLEM_CATALOG
    entry, recompute it fresh against the current Product Reality Map and
    report Previous vs New classification side by side."""
    by_angle = {entry["angle"]: entry for entry in audience_research.PROBLEM_CATALOG}
    comparisons = []
    for row in existing_campaign_rows:
        angle = row.get("Marketing Angle")
        entry = by_angle.get(angle)
        if not entry:
            continue
        problem_row = {
            "Audience Segment": entry["segment"], "Problem Cluster": entry["cluster"],
            "Audience Problem": entry["problem"], "Recommended Angle": entry["angle"],
            "Pain Severity": 8, "Content Potential": 8, "Conversion Potential": 7,
            "Frequency Signal": 7, "Problem ID": row.get("Campaign ID", "?"),
            "_product_feature": entry["product_feature"], "_fallback_feature": entry.get("fallback_feature"),
        }
        new_campaign = campaign_engine.build_campaign(problem_row, None, run_date, reality)
        comparisons.append({
            "name": angle,
            "previous_status": row.get("Status", "Draft"),
            "previous_confidence": row.get("Confidence", "Low"),
            "previous_product_feature": row.get("Product Feature", "NEEDS PRODUCT INPUT"),
            "new_status": new_campaign["Status"],
            "new_confidence": new_campaign["Confidence"],
            "new_product_feature": new_campaign["Product Feature"],
            "new_product_fit": new_campaign["Product Fit"],
            "new_core_message": new_campaign["Core Message"],
            "reason": new_campaign["Notes"],
        })
    return comparisons


def _build_report_context(mode, run_date, new_signals, new_problems, new_competitors, competitor_updates, competitor_update_summaries, recommended_campaigns, future_campaigns, campaign_updates, perf_analysis, learnings, demand_signals, reality, stale, product_changes_note, existing, noise_removed=None):
    noise_removed = noise_removed or []
    ready = [c for c in recommended_campaigns if c["Status"] == "READY TO MARKET"]
    safe_test = [c for c in recommended_campaigns if c["Status"] == "SAFE TEST"]
    qualifier = [c for c in recommended_campaigns if c["Status"] == "QUALIFIER REQUIRED"]
    stop = [f"{p['campaign_id']}: {p['verdict']}" for p in perf_analysis if p["verdict"] == "Below Target"]

    all_new = recommended_campaigns + future_campaigns
    # Section 18/25: a homepage recheck that found no real diff is not a
    # "competitor change" — only count entries diff_snapshot() actually
    # flagged (competitor_update_summaries[i]["material"]).
    material_competitor_updates = [c for c in competitor_update_summaries if c.get("material")]
    checked_no_change = [c for c in competitor_update_summaries if not c.get("material")]

    # Section 25: PRODUCT / MARKET / COMPETITOR / MARKETING changes kept as
    # separate facts, not folded into one "what changed" blob.
    changes = []
    if new_signals:
        changes.append(f"MARKET: {len(new_signals)} new market signal(s) discovered.")
    if new_problems:
        changes.append(f"AUDIENCE: {len(new_problems)} new audience problem(s) identified.")
    if new_competitors:
        changes.append(f"COMPETITOR: {len(new_competitors)} new competitor(s) added to the watchlist.")
    if material_competitor_updates:
        changes.append(f"COMPETITOR: {len(material_competitor_updates)} MATERIAL competitor change(s) detected.")
    if checked_no_change:
        changes.append(f"COMPETITOR: {len(checked_no_change)} competitor(s) rechecked, no material change (Date Checked only).")
    if all_new:
        changes.append(f"MARKETING: {len(all_new)} new campaign opportunit(y/ies) generated ({len(future_campaigns)} blocked by product).")
    if campaign_updates:
        changes.append(f"MARKETING: {len(campaign_updates)} existing campaign(s) reclassified in place against current Product Intelligence.")
    if demand_signals:
        changes.append(f"MARKET: {len(demand_signals)} product demand signal(s) surfaced from market research.")
    if noise_removed:
        changes.append(f"MARKET: {len(noise_removed)} autocomplete/derived query result(s) filtered out as noise (not counted as demand).")
    changes.append(f"PRODUCT: {product_changes_note}")

    best_opportunity = ready[0]["Campaign Name"] if ready else (safe_test[0]["Campaign Name"] if safe_test else None)
    best_audience = ready[0]["Audience Segment"] if ready else (safe_test[0]["Audience Segment"] if safe_test else None)
    best_angle = ready[0]["Marketing Angle"] if ready else (safe_test[0]["Marketing Angle"] if safe_test else None)
    biggest_constraint = reality.get("exec_fields", {}).get("biggest_weakness", "")
    biggest_threat = reality.get("exec_fields", {}).get("biggest_threat", "")

    def _or_insufficient(value):
        return value if value else "INSUFFICIENT EVIDENCE"

    return {
        "run_date": run_date,
        "mode": mode,
        "what_changed": changes,
        "product_reality": reality,
        "stale": stale,
        "opportunity_map": _build_opportunity_map(reality, new_signals or [r for _, r in existing["Market Signals"]], new_problems or [r for _, r in existing["Audience Problems"]]),
        "market_signals": new_signals,
        "noise_removed": noise_removed,
        "audience_problems": new_problems,
        "competitor_updates": (
            [
                {"name": r.get("Competitor", ""), "change": "New watchlist addition", "action": r.get("Action", "MONITOR"), "material": True}
                for r in new_competitors
            ]
            + competitor_update_summaries
        ),
        "material_competitor_updates": material_competitor_updates,
        "checked_no_change_competitors": checked_no_change,
        "campaign_opportunities": recommended_campaigns,
        "future_campaigns": future_campaigns,
        "demand_signals": demand_signals,
        "performance_analysis": perf_analysis,
        "learnings": learnings,
        "decisions": {
            "double_down": [], "build_now": [c["Campaign Name"] for c in ready],
            "test": [c["Campaign Name"] for c in safe_test + qualifier], "monitor": [c["Campaign Name"] for c in future_campaigns],
            "stop": stop,
        },
        "this_week_actions": (
            [f"Review and approve/reject: {c['Campaign Name']}" for c in ready]
            or ["Review Campaign Opportunities in the workbook — nothing cleared READY TO MARKET this run."]
        ),
        "executive_summary": {
            "best_opportunity": _or_insufficient(best_opportunity),
            "best_audience": _or_insufficient(best_audience),
            "best_angle": _or_insufficient(best_angle),
            "best_organic": _or_insufficient(f"{ready[0]['Platform']}: {ready[0]['Core Message']}" if ready else None),
            "best_paid_test": _or_insufficient(f"{safe_test[0]['Platform']}: {safe_test[0]['Core Message']}" if safe_test else None),
            "biggest_constraint": _or_insufficient(biggest_constraint),
            "biggest_threat": _or_insufficient(biggest_threat),
            "what_to_stop": _or_insufficient("; ".join(stop) if stop else None),
            "what_to_do": _or_insufficient(
                f"Approve or reject {len(ready)} READY TO MARKET candidate(s) in Campaign Opportunities."
                if ready else (f"Review {len(qualifier)} QUALIFIER REQUIRED candidate(s)." if qualifier else None)
            ),
        },
        # Section 24: "never hide product-source age at the end of the
        # report only" — report_generator renders this block at the TOP,
        # right after the title, not appended after everything else.
        "report_cross_citation": {
            "report_used": reality.get("report_file"),
            "product_state_date": reality.get("report_date"),
            "product_changes_since_previous": product_changes_note,
            "stale": stale,
            "freshness": (reality.get("freshness_info") or {}).get("freshness", "UNKNOWN"),
            "confidence": (reality.get("freshness_info") or {}).get("confidence", "UNKNOWN"),
            "freshness_source": (reality.get("freshness_info") or {}).get("source"),
            "freshness_warning": (reality.get("freshness_info") or {}).get("warning"),
            "marketing_research_date": run_date.strftime("%Y-%m-%d"),
        },
    }


def reclassification_report() -> list:
    """Public entrypoint for section 38's DRY RUN deliverable: re-scores
    every EXISTING Campaign Opportunities row that matches a known
    audience_research.PROBLEM_CATALOG angle against the current Product
    Reality Map, without writing anything. Read-only, no lock needed."""
    wb = workbook.load(data_only=True)
    ws = wb["Campaign Opportunities"]
    fcols = workbook.formula_columns(ws)
    existing_campaigns = [r for _, r in workbook.iter_data_rows(ws, fcols)]
    reality = product_intelligence.load_or_refresh()
    return _reclassify_existing_campaigns(existing_campaigns, reality, datetime.now())


def status() -> dict:
    """STATUS command (section 34) — read-only, no research, no lock."""
    try:
        wb = workbook.load(data_only=True)
    except workbook.WorkbookNotFoundError as exc:
        return {"error": str(exc)}

    existing = _read_all(wb)
    campaigns = [r for _, r in existing["Campaign Opportunities"]]
    build_now = sum(1 for c in campaigns if c.get("Status") == "READY TO MARKET")
    tests = sum(1 for c in campaigns if c.get("Status") in ("SAFE TEST", "QUALIFIER REQUIRED"))

    logs = [r for _, r in existing["Automation Logs"]]
    last_success = next((r for r in reversed(logs) if r.get("Success") == "Yes"), None)
    last_error = next((r for r in reversed(logs) if r.get("Success") == "No"), None)

    lock = workflow_lock.is_locked()
    schedule = config.load_schedule()
    reality = product_intelligence.load_or_refresh()

    return {
        "workflow_status": "RUNNING" if lock else "Idle",
        "last_successful_run": last_success.get("Date") if last_success else "No runs yet",
        "schedule": schedule,
        "product_intelligence_report": reality.get("report_file"),
        "product_intelligence_date": reality.get("report_date"),
        "product_intelligence_stale": product_intelligence.is_stale(reality),
        "product_intelligence_freshness": (reality.get("freshness_info") or {}).get("freshness", "UNKNOWN"),
        "product_intelligence_confidence": (reality.get("freshness_info") or {}).get("confidence", "UNKNOWN"),
        "signals_stored": len(existing["Market Signals"]),
        "competitors_tracked": len(existing["Competitor Intelligence"]),
        "audience_problems_stored": len(existing["Audience Problems"]),
        "campaign_opportunities": len(campaigns),
        "build_now_count": build_now,
        "test_count": tests,
        "active_campaigns": len(existing["Active Campaigns"]),
        "marketing_learnings": len(existing["Marketing Learnings"]),
        "last_error": last_error.get("Errors / Notes") if last_error else "None",
    }
