"""Weekly PDF report (workflow sections 26-32 of the original workflow,
restructured per the Product Intelligence integration's section 30):
decision-focused, executive summary first, sections only rendered when
there's real content — a fresh or quiet week produces a short report
rather than padding to a page count.

Table formatting (integration section 32): every cell is wrapped in a
Paragraph with a wrap-friendly style instead of a raw string — a plain
string in a reportlab Table cell does NOT wrap, which is exactly what
caused the text collisions/overlapping columns in the previous version.
Wide tables (8+ columns) render on a landscape page.
"""

import os
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import LETTER, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable, NextPageTemplate, PageBreak, PageTemplate, Paragraph,
    SimpleDocTemplate, Spacer, Table, TableStyle, Frame,
)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPORTS_DIR = os.path.join(REPO_ROOT, "reports", "vital_sync_marketing")

INK = colors.HexColor("#1B1F1D")
MUTED = colors.HexColor("#6B6F66")
LINE = colors.HexColor("#BFC3B8")
ACCENT = colors.HexColor("#2F5D53")
ACCENT_SOFT = colors.HexColor("#E4ECE9")
WARN = colors.HexColor("#8A362E")
WARN_BG = colors.HexColor("#F3E3E1")

STYLES = getSampleStyleSheet()
H1 = ParagraphStyle("H1", parent=STYLES["Heading1"], textColor=ACCENT, spaceAfter=10)
H2 = ParagraphStyle("H2", parent=STYLES["Heading2"], textColor=INK, spaceBefore=14, spaceAfter=6)
BODY = ParagraphStyle("Body", parent=STYLES["BodyText"], textColor=INK, leading=14, alignment=TA_LEFT)
MUTED_STYLE = ParagraphStyle("Muted", parent=BODY, textColor=MUTED, fontSize=9)
CELL = ParagraphStyle("Cell", parent=BODY, fontSize=8.5, leading=11)
CELL_HEAD = ParagraphStyle("CellHead", parent=CELL, textColor=ACCENT, fontName="Helvetica-Bold")


def _p(text, style=CELL):
    return Paragraph(str(text if text not in (None, "") else "—").replace("\n", "<br/>"), style)


def _table(rows, headers, col_widths):
    """Every cell wrapped in a Paragraph (see module docstring) so long
    campaign names / audience segments / evidence text wrap within their
    column instead of overlapping the next one."""
    data = [[_p(h, CELL_HEAD) for h in headers]] + [[_p(v) for v in row] for row in rows]
    t = Table(data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), ACCENT_SOFT),
        ("GRID", (0, 0), (-1, -1), 0.5, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return t


def _section(title, body_flowables):
    flow = [Paragraph(title, H2), HRFlowable(width="100%", color=LINE, thickness=0.75), Spacer(1, 6)]
    flow.extend(body_flowables)
    return flow


def _empty(note="No meaningful new data this period."):
    return [Paragraph(note, MUTED_STYLE)]


def _landscape_table(title, rows, headers, col_widths):
    """Wide tables (Product x Market Opportunity Map, 8 columns) switch
    the page to landscape for this section only, then switch back."""
    return [
        NextPageTemplate("landscape"), PageBreak(),
        Paragraph(title, H2), HRFlowable(width="100%", color=LINE, thickness=0.75), Spacer(1, 6),
        _table(rows, headers, col_widths) if rows else _empty()[0],
        NextPageTemplate("portrait"), PageBreak(),
    ]


def build(context: dict, preview: bool = False) -> str:
    os.makedirs(REPORTS_DIR, exist_ok=True)
    run_date = context.get("run_date") or datetime.now()
    date_str = run_date.strftime("%Y-%m-%d")
    # DRY RUN previews get their own filename suffix — never collide with
    # (and silently overwrite) an official post-approval report for the
    # same date. Caught during this integration's own testing: an isolated
    # validation write clobbered a same-day real report before this fix.
    suffix = "_PREVIEW" if preview else ""
    filename = f"Vital_Sync_Marketing_Intelligence_{date_str}{suffix}.pdf"
    filepath = os.path.join(REPORTS_DIR, filename)

    doc = SimpleDocTemplate(
        filepath, pagesize=LETTER,
        leftMargin=0.6 * inch, rightMargin=0.6 * inch,
        topMargin=0.7 * inch, bottomMargin=0.7 * inch,
        title="Vital Sync Marketing Intelligence Report",
    )
    portrait_frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="portrait")
    landscape_size = landscape(LETTER)
    lw = landscape_size[0] - 1.2 * inch
    lh = landscape_size[1] - 1.4 * inch
    landscape_frame = Frame(0.6 * inch, 0.7 * inch, lw, lh, id="landscape")
    doc.addPageTemplates([
        PageTemplate(id="portrait", frames=[portrait_frame], pagesize=LETTER),
        PageTemplate(id="landscape", frames=[landscape_frame], pagesize=landscape_size),
    ])

    story = []
    reality = context.get("product_reality", {})
    stale = context.get("stale", False)

    # --- Title page / executive summary --------------------------------
    story.append(Paragraph("VITAL SYNC", H1))
    story.append(Paragraph("MARKETING INTELLIGENCE REPORT", STYLES["Title"]))
    story.append(Paragraph(f"{date_str} — {context.get('mode', 'Full Run')}", MUTED_STYLE))
    if preview:
        story.append(Spacer(1, 8))
        preview_table = Table(
            [[_p("DRY RUN PREVIEW — nothing on this page has been written to the workbook. "
                 "Re-run without DRY RUN to apply it.", BODY)]],
            colWidths=[6.5 * inch],
        )
        preview_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), ACCENT_SOFT), ("BOX", (0, 0), (-1, -1), 1, ACCENT),
            ("LEFTPADDING", (0, 0), (-1, -1), 8), ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(preview_table)
    # --- Product Intelligence Source (section 24: shown at the TOP, never
    # only at the end) --------------------------------------------------
    cite = context.get("report_cross_citation", {})
    freshness = cite.get("freshness", "UNKNOWN")
    source_rows = [
        ["Workflow 01 Report", cite.get("report_used") or "None found"],
        ["Product Snapshot Date", cite.get("product_state_date") or "Unknown"],
        ["Product Freshness", freshness],
        ["Product Confidence", cite.get("confidence", "UNKNOWN")],
        ["Freshness Source", cite.get("freshness_source") or "None (calendar-age fallback only)"],
        ["Marketing Research Date", cite.get("marketing_research_date") or date_str],
        ["Product Changes Since Previous Marketing Run", cite.get("product_changes_since_previous") or "—"],
    ]
    story.append(_table(source_rows, ["PRODUCT INTELLIGENCE SOURCE", "Value"], col_widths=[2.6 * inch, 3.9 * inch]))
    if stale:
        story.append(Spacer(1, 8))
        warning_text = cite.get("freshness_warning") or (
            f"PRODUCT INTELLIGENCE IS NOT CURRENT (freshness={freshness}). "
            "Product-dependent recommendations below carry reduced confidence — do not treat them as definitive."
        )
        warn_table = Table([[_p(warning_text, BODY)]], colWidths=[6.5 * inch])
        warn_table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), WARN_BG), ("BOX", (0, 0), (-1, -1), 1, WARN),
                                         ("LEFTPADDING", (0, 0), (-1, -1), 8), ("TOPPADDING", (0, 0), (-1, -1), 6),
                                         ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
        story.append(warn_table)
    story.append(Spacer(1, 14))

    summary = context.get("executive_summary", {})
    exec_rows = [
        ["Best Opportunity", summary.get("best_opportunity")],
        ["Best Audience", summary.get("best_audience")],
        ["Best Marketing Angle", summary.get("best_angle")],
        ["Best Organic Move", summary.get("best_organic")],
        ["Best Paid Test", summary.get("best_paid_test")],
        ["Biggest Product Constraint", summary.get("biggest_constraint")],
        ["Biggest Competitor Threat", summary.get("biggest_threat")],
        ["What To Stop", summary.get("what_to_stop")],
        ["What To Do This Week", summary.get("what_to_do")],
    ]
    story.append(_table(exec_rows, ["Executive Summary", "Decision"], col_widths=[1.9 * inch, 4.6 * inch]))
    story.append(PageBreak())

    # --- 01 Product Reality Snapshot ----------------------------------------
    live, partial, missing, prototype = reality.get("live", []), reality.get("partial", []), reality.get("missing", []), reality.get("prototype", [])
    broken = reality.get("broken", [])
    snapshot_rows = [
        ["LIVE", ", ".join(live) or "None on file"],
        ["PARTIAL", ", ".join(partial) or "None on file"],
        # BROKEN gets its own row — a confirmed security/integrity gap
        # (e.g. Squad authorization) is a different, more urgent fact than
        # a feature simply not existing yet (product-reality refresh spec,
        # section 7), and must not be silently folded into "missing".
        ["BROKEN", ", ".join(broken) or "None on file"],
        ["MISSING", ", ".join(missing) or "None on file"],
        ["PROTOTYPE", ", ".join(prototype) or "None on file"],
    ]
    body = [_table(snapshot_rows, ["Status", "Areas"], col_widths=[1.2 * inch, 5.3 * inch])]
    if reality.get("error"):
        body = [Paragraph(f"Product Intelligence unavailable: {reality['error']}", MUTED_STYLE)]
    story += _section("01 — Product Reality Snapshot", body)

    # --- 02 What changed --------------------------------------------------
    changes = context.get("what_changed", [])
    body = [Paragraph(c, BODY) for c in changes] if changes else _empty("No prior run to diff against, or no material change detected.")
    story += _section("02 — What Changed This Week", body)

    # --- 03 Market intelligence --------------------------------------------
    signals = context.get("market_signals", [])
    if signals:
        rows = [[s.get("Topic", ""), s.get("Search / Social Query", ""), s.get("Source", ""), s.get("Priority", "")] for s in signals[:20]]
        body = [_table(rows, ["Topic", "Query", "Source", "Priority"], col_widths=[1.3 * inch, 2.7 * inch, 1.5 * inch, 1 * inch])]
    else:
        body = _empty()
    noise = context.get("noise_removed", [])
    if noise:
        body = body + [Spacer(1, 6), Paragraph(
            f"{len(noise)} autocomplete/derived result(s) filtered out as noise this run "
            f"(location-name completions, off-topic categories, or content-free mechanical "
            f"expansions) — not counted as demand: "
            + "; ".join(f"\"{n['query']}\" ({n['reason']})" for n in noise[:8])
            + ("…" if len(noise) > 8 else ""), MUTED_STYLE,
        )]
    story += _section("03 — Market Intelligence", body)

    # --- 04 Audience intelligence -------------------------------------------
    problems = context.get("audience_problems", [])
    if problems:
        rows = [[p.get("Audience Segment", ""), p.get("Problem Cluster", ""), p.get("Audience Problem", ""), p.get("Source", "")] for p in problems[:20]]
        body = [_table(rows, ["Segment", "Cluster", "Problem", "Source"], col_widths=[1.3 * inch, 1.3 * inch, 2.7 * inch, 1.2 * inch])]
    else:
        body = _empty()
    story += _section("04 — Audience Intelligence", body)

    # --- 05 Competitive intelligence ----------------------------------------
    # Section 18: a homepage recheck with no real diff is NOT a competitor
    # change — shown separately, never mixed into "Meaningful Competitor
    # Changes" so a quiet week of checks doesn't read as an eventful one.
    material = context.get("material_competitor_updates") or [c for c in context.get("competitor_updates", []) if c.get("material")]
    checked_only = context.get("checked_no_change_competitors") or []
    if material:
        rows = [[c.get("name", ""), c.get("change", "—"), c.get("action", "MONITOR")] for c in material]
        body = [_table(rows, ["Competitor", "Material Change", "Action"], col_widths=[1.5 * inch, 3.7 * inch, 1.3 * inch])]
    else:
        body = _empty("No MATERIAL competitor changes detected this period.")
    if checked_only:
        body.append(Spacer(1, 6))
        body.append(Paragraph(
            f"{len(checked_only)} competitor(s) rechecked with no material change: "
            + ", ".join(c.get("name", "") for c in checked_only) + ".",
            MUTED_STYLE,
        ))
    story += _section("05 — Competitive Intelligence (Meaningful Changes Only)", body)
    story.append(PageBreak())

    # --- 06 Product x Market Opportunity Map (landscape, wide table) --------
    opp_map = context.get("opportunity_map", [])
    map_rows = [[
        o["opportunity"], o["market_demand"], o["audience_pain"], o["product_status"],
        o["competitive_gap"], o["marketing_potential"], o["product_dependency"], o["recommendation"],
    ] for o in opp_map]
    story += _landscape_table(
        "06 — Product × Market Opportunity Map", map_rows,
        ["Opportunity", "Market Demand", "Audience Pain", "Product Status", "Competitive Gap", "Marketing Potential", "Product Dependency", "Recommendation"],
        [1.3 * inch, 0.9 * inch, 0.9 * inch, 0.9 * inch, 0.9 * inch, 1.0 * inch, 1.1 * inch, 1.3 * inch],
    )

    # --- 07 Positioning -------------------------------------------------------
    exec_fields = reality.get("exec_fields", {})
    positioning_note = exec_fields.get("biggest_advantage") or "No positioning changes recorded this period."
    story += _section("07 — Vital Sync Positioning", [Paragraph(positioning_note, BODY)])

    # --- 08 Top opportunities / 09 Recommended campaigns --------------------
    campaigns = context.get("campaign_opportunities", [])
    if campaigns:
        rows = [[c.get("Campaign Name", ""), c.get("Audience Segment", ""), c.get("Status", ""), c.get("Confidence", ""), c.get("Product Feature", "")] for c in campaigns]
        body = [_table(rows, ["Campaign", "Segment", "Status", "Confidence", "Product Feature"], col_widths=[1.6 * inch, 1.3 * inch, 1.2 * inch, 0.9 * inch, 1.5 * inch])]
    else:
        body = _empty("No new campaign opportunities generated this period.")
    story += _section("08 — Top Marketing Opportunities", body)
    story += _section("09 — Recommended Campaigns (Pending Human Approval)", body)

    # --- 10 Future product-dependent campaigns -------------------------------
    future = context.get("future_campaigns", [])
    if future:
        rows = [[c.get("Campaign Name", ""), c.get("Product Feature", ""), c.get("Status", ""), c.get("Notes", "")[:180]] for c in future]
        body = [_table(rows, ["Campaign", "Product Feature", "Status", "Dependency"], col_widths=[1.6 * inch, 1.7 * inch, 1.3 * inch, 1.9 * inch])]
    else:
        body = _empty("No campaigns are currently blocked by product gaps.")
    story += _section("10 — Future Product-Dependent Campaigns", body)

    # --- 11/12 Organic / Paid direction --------------------------------------
    story += _section("11 — Organic Marketing Direction", context.get("organic_direction_flow") or _empty())
    story += _section("12 — Paid Marketing Direction", context.get("paid_direction_flow") or _empty())

    # --- 13 Performance intelligence ------------------------------------------
    perf = context.get("performance_analysis", [])
    if perf:
        rows = [[p["campaign_id"], p["objective"], p["verdict"], p["evidence_points"]] for p in perf]
        body = [_table(rows, ["Campaign", "Objective", "Verdict", "Data Points"], col_widths=[1.5 * inch, 1.5 * inch, 2 * inch, 1.5 * inch])]
    else:
        body = _empty("No active campaigns with performance data yet.")
    story += _section("13 — Performance Intelligence", body)

    # --- 14 Learnings -----------------------------------------------------
    learnings = context.get("learnings", [])
    if learnings:
        rows = [[l["Finding"], l["Confidence"], l["Action"]] for l in learnings]
        body = [_table(rows, ["Finding", "Confidence", "Action"], col_widths=[3.5 * inch, 1 * inch, 2 * inch])]
    else:
        body = _empty("No learnings met the evidence bar this period.")
    story += _section("14 — Marketing Learnings", body)

    # --- 15-18 Decisions ----------------------------------------------------
    decisions = context.get("decisions", {})
    for num, key, title in [
        ("15", "double_down", "Double Down"), ("16", "test", "Test"),
        ("17", "monitor", "Monitor"), ("18", "stop", "Stop"),
    ]:
        items = decisions.get(key, [])
        body = [Paragraph(f"• {i}", BODY) for i in items] if items else _empty("None this period.")
        story += _section(f"{num} — {title}", body)

    # --- 19 Product demand signals --------------------------------------------
    demand = context.get("demand_signals", [])
    if demand:
        rows = [[d["Feature Requested"], d["Audience"], d["Frequency"], d["Potential Marketing Value"], d["Recommended Product Priority"]] for d in demand]
        body = [_table(rows, ["Feature Requested", "Audience", "Frequency", "Marketing Value", "Product Priority"], col_widths=[1.8 * inch, 1.5 * inch, 0.9 * inch, 1.3 * inch, 1.3 * inch])]
    else:
        body = _empty("No recurring demand for a missing feature surfaced this period.")
    story += _section("19 — Product Demand Signals", body)

    # --- 20 This week's actions ----------------------------------------------
    actions = context.get("this_week_actions", [])
    body = [Paragraph(f"{i + 1}. {a}", BODY) for i, a in enumerate(actions)] if actions else _empty(
        "No specific actions — review Pending campaign opportunities in the workbook."
    )
    story += _section("20 — This Week's Actions", body)

    # --- Report cross-citation (closing reference — the authoritative copy
    # of this is the "PRODUCT INTELLIGENCE SOURCE" table at the TOP of this
    # report; repeated here only as a closing reference, never the only
    # place it appears — section 24) --------------------------------------
    cite_rows = [
        ["Report Used", cite.get("report_used") or "None found"],
        ["Product State Date", cite.get("product_state_date") or "Unknown"],
        ["Product Changes Since Previous Marketing Run", cite.get("product_changes_since_previous") or "—"],
        ["Product Freshness", cite.get("freshness", "UNKNOWN")],
        ["Stale Warning", (cite.get("freshness_warning") or "Treat product-dependent items with caution.") if cite.get("stale") else "No"],
    ]
    story += _section("Product Intelligence Input (see top of report for full detail)", [_table(cite_rows, ["Field", "Value"], col_widths=[2.4 * inch, 4.1 * inch])])

    doc.build(story)
    return filepath
