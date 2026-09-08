"""Product Intelligence bridge (new architecture, see workflow doc section
"Product Intelligence -> Marketing Intelligence"): locates the newest
Vital_Sync_Weekly_Intelligence_*.pdf, extracts its structured findings, and
turns them into a Product Reality Map that campaign_engine.py can query.

This is a REAL PDF text extraction (pypdf), not a hardcoded restatement of
today's findings — every future run re-parses whatever the latest report
actually says (section: "do not hardcode the report conclusions forever").
Extraction anchors on the report's section headers, which are fixed
literal strings in tools/generate_weekly_pdf.py's rendering code (verified
2026-08-19: "Vital Sync Current State", "Cross-System Audit", "Product
Opportunities", "Build Now"/"Improve Existing"/"Build Next"/"Experiment"/
"Monitor", "Biggest Competitor Threat" etc. are all literal Paragraph
strings, not LLM-improvised each week) — stable anchors across reports
produced by that script. If a future report doesn't use this template, the
relevant lists simply come back empty rather than fabricated, same honesty
rule as everywhere else in this codebase.
"""

import json
import re
from datetime import datetime
from pathlib import Path

import pypdf

from config import CONFIG_DIR

PRODUCT_REALITY_FILE = CONFIG_DIR / "product_reality.json"
STALE_DAYS = 10  # only used as a last-resort fallback — see determine_freshness()

REPO_ROOT = Path(__file__).resolve().parent.parent
FILENAME_RE = re.compile(r"Vital_Sync_Weekly_Intelligence_(\d{4}-\d{2}-\d{2})\.pdf$")

SEARCH_DIRS = [
    REPO_ROOT / "reports" / "vital_sync",  # canonical, recursive
    Path.home() / "Desktop",
    Path.home() / "Downloads",
]

# Priority-2 source in Workflow 02's source hierarchy (product-reality
# refresh spec, section 3): Workflow 01's own structured, lifecycle-aware
# state registry. Read directly rather than only text-scraping the PDF,
# because the PDF's new BROKEN/COMPLETE/MISSING/MISMATCH vocabulary (see
# STATUS_WORDS below) carries no lifecycle information the way this file
# does, and because this is exactly the file Workflow 01's own Product
# Freshness Gate writes its verified overall_freshness/overall_confidence
# conclusion to — re-deriving that from prose would be strictly worse.
PRODUCT_STATE_FILE = REPO_ROOT / "reports" / "vital_sync" / "vital_sync_product_state.json"

FRESHNESS_LABELS = ("CURRENT_VERIFIED", "LIKELY_CURRENT", "CONFLICTING", "STALE", "UNKNOWN")
FRESH_ENOUGH = {"CURRENT_VERIFIED", "LIKELY_CURRENT"}

# Workflow 01's report vocabulary grew (see workflow doc "Finding lifecycle")
# beyond the original LIVE/PARTIAL/PROTOTYPE/NOT FOUND four — BROKEN/
# COMPLETE/MISSING/MISMATCH are now real status words a table row can
# anchor on. Recognizing them here keeps the PDF-table fallback parser
# (parse_status_table) from silently dropping every row that uses one.
STATUS_WORDS = {"LIVE", "PARTIAL", "PROTOTYPE", "NOT FOUND", "BROKEN", "COMPLETE", "MISSING", "MISMATCH"}
NOISE_LINES = {"Area", "Status", "Evidence", "Vital Sync — Competition & Product Intelligence"}
PAGE_RE = re.compile(r"^Page \d+ of \d+$")

OPPORTUNITY_BUCKETS = ["Build Now", "Improve Existing", "Build Next", "Experiment", "Monitor"]

EXEC_FIELDS = {
    "Biggest Competitor Threat": "biggest_threat",
    "Biggest Open Market Gap": "biggest_gap",
    "Biggest Vital Sync Weakness": "biggest_weakness",
    "Biggest Vital Sync Advantage": "biggest_advantage",
    "One Thing To Ignore": "one_thing_to_ignore",
}


# --------------------------------------------------------------------------
# Locate + read
# --------------------------------------------------------------------------

def find_latest_report() -> tuple:
    """Returns (path, report_date) for the newest report BY REPORT DATE
    (parsed from the filename, per workflow section "never use the older
    report" / "use report date, not filesystem time") — or (None, None) if
    none found. Searches the repo's canonical archive first, then common
    Desktop/Downloads drop locations."""
    candidates = []
    seen_dates = {}
    for base in SEARCH_DIRS:
        if not base.exists():
            continue
        for path in base.rglob("Vital_Sync_Weekly_Intelligence_*.pdf"):
            match = FILENAME_RE.search(path.name)
            if not match:
                continue
            report_date = datetime.strptime(match.group(1), "%Y-%m-%d").date()
            # Prefer the repo's own archive copy if the same date shows up
            # in multiple locations (Desktop/Downloads are just convenience
            # copies of the same report).
            if report_date not in seen_dates or "reports/vital_sync" in str(path):
                seen_dates[report_date] = path
    if not seen_dates:
        return None, None
    latest_date = max(seen_dates)
    return seen_dates[latest_date], latest_date


def extract_text(path: Path) -> str:
    reader = pypdf.PdfReader(str(path))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


# --------------------------------------------------------------------------
# Product Freshness Gate (product-reality refresh spec, sections 3-5)
#
# "Latest available file" is NOT "current product state" — that was the
# exact bug this replaces. The old is_stale() only ever asked "is this PDF's
# report_date more than 10 days old?", a question with no connection to
# whether Workflow 01 itself verified the product as current. A same-day
# report built from a source Workflow 01's own gate had marked STALE would
# have sailed through that check with a cheerful "Stale Warning: No".
#
# Freshness now comes from Workflow 01's OWN verified classification —
# CURRENT_VERIFIED / LIKELY_CURRENT / STALE / UNKNOWN / CONFLICTING — read
# from whichever of these actually exists, in priority order:
#   1. vital_sync_product_state.json's overall_freshness (Priority 2 source,
#      structured, and normally written by the same run as the newest PDF).
#   2. The newest PDF's own "Product Source Freshness" section text
#      (Priority 1 source, parsed defensively since it's prose).
#   3. UNKNOWN, with a visible warning — never a silent "not stale".
# --------------------------------------------------------------------------

def load_product_state() -> dict:
    """Returns the parsed vital_sync_product_state.json, or None if it
    doesn't exist or doesn't parse — callers must degrade to the PDF-text
    fallback, never fabricate a freshness verdict to fill the gap."""
    if not PRODUCT_STATE_FILE.exists():
        return None
    try:
        with open(PRODUCT_STATE_FILE) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def _normalize_freshness_label(raw) -> str:
    raw_up = str(raw or "").upper()
    for label in FRESHNESS_LABELS:
        if label in raw_up:
            return label
    return "UNKNOWN"


def _freshness_from_pdf_text(text: str) -> dict:
    """Fallback when vital_sync_product_state.json isn't available: parse
    Workflow 01's "Product Source Freshness" section out of the report text
    itself. Best-effort and prose-based, so this is used only as a second
    choice, never preferred over the structured JSON."""
    section = _section(text, "Product Source Freshness", "This Week's Actions")
    if not section:
        return {
            "freshness": "UNKNOWN",
            "confidence": "UNKNOWN",
            "warning": (
                "No 'Product Source Freshness' section found in the latest Workflow 01 "
                "report and no vital_sync_product_state.json on file — freshness could not "
                "be determined. Treat all product-dependent claims as provisional."
            ),
            "source": None,
            "source_date": None,
        }
    freshness = _normalize_freshness_label(section)
    conf_match = re.search(r"Overall confidence:\s*([A-Za-z]+)", section)
    confidence = conf_match.group(1).upper() if conf_match else "UNKNOWN"
    warning = None
    if freshness not in FRESH_ENOUGH:
        warning = (
            f"Workflow 01's own Product Source Freshness section reports '{freshness}' — "
            "do not produce definitive marketing classifications from this run's product reality."
        )
    return {
        "freshness": freshness, "confidence": confidence, "warning": warning,
        "source": "Workflow 01 PDF text ('Product Source Freshness' section)", "source_date": None,
    }


def determine_freshness(report_date, freshness_section_text: str, state: dict) -> dict:
    """The real Product Freshness Gate. report_date/freshness_section_text
    come from the newest Workflow 01 PDF found; state is
    load_product_state()'s result. Returns
    {freshness, confidence, warning, source, source_date}."""
    if state:
        state_date = str(state.get("generated_at") or "")[:10]
        if not report_date or not state_date or state_date >= str(report_date):
            # The state file is at least as new as the newest report on
            # file — normally the same Workflow 01 run wrote both. Treat it
            # as authoritative rather than re-deriving from PDF prose.
            freshness = _normalize_freshness_label(state.get("overall_freshness"))
            warning = state.get("warning")
            if warning is None and freshness not in FRESH_ENOUGH:
                warning = (
                    f"vital_sync_product_state.json reports overall_freshness='{freshness}' — "
                    "do not produce definitive marketing classifications from this run's product reality."
                )
            return {
                "freshness": freshness,
                "confidence": str(state.get("overall_confidence") or "UNKNOWN"),
                "warning": warning,
                "source": str(PRODUCT_STATE_FILE.relative_to(REPO_ROOT)),
                "source_date": state_date or report_date,
            }
        # The state file is OLDER than the newest PDF on disk — the two
        # disagree about what "current" even means. Never silently pick one.
        return {
            "freshness": "CONFLICTING",
            "confidence": "LOW",
            "warning": (
                f"vital_sync_product_state.json is dated {state_date}, older than the newest "
                f"Workflow 01 report on file ({report_date}). Freshness could not be reconciled "
                "automatically — treat product-dependent claims as provisional."
            ),
            "source": str(PRODUCT_STATE_FILE.relative_to(REPO_ROOT)),
            "source_date": state_date,
        }
    return _freshness_from_pdf_text(freshness_section_text or "")


# vital_sync_product_state.json's area keys are snake_case and internal;
# these are the display names the PDF's own "Vital Sync Current State"
# table uses for the same areas, so FEATURE_TAXONOMY's substring matching
# (_match_area) keeps working unchanged whichever source actually supplied
# the entry. Kept as an explicit mapping (not inferred) so a mismatch is a
# visible KeyError-free no-op rather than a silent wrong match.
STATE_AREA_DISPLAY_NAMES = {
    "user_scoping": "Multi-User / Data Scoping",
    "squads_real_activity": "Squads — Real Activity",
    "squad_authorization": "Squads — Authorization / Privacy",
    "squad_invites": "Squads — Invites",
    "directive_engine": "Directive Engine",
    "directive_mission_connection": "Directive <-> Mission Connection",
    "alignment": "Cross-System Intelligence (Alignment)",
    "recovery": "Recovery",
    "training": "Training",
    "nutrition": "Nutrition",
    "ai_coach": "AI — chat coach",
    "analytics": "Analytics",
    "wearables": "Integrations (wearables)",
    "database_integrity": "Database Integrity",
    "monetization": "Monetization",
    "security": "Security",
    "mobile": "Mobile App",
    "marketing_product_alignment": "Marketing / Product Alignment",
}


def _areas_from_state(state: dict) -> dict:
    """Turns vital_sync_product_state.json's `areas` object into the same
    {display_name: {"status", "evidence", ...}} shape build_product_reality
    already produces from the PDF table — richer, since it also carries
    lifecycle/freshness/confidence per area, which the PDF-table parse has
    no way to express."""
    if not state:
        return {}
    out = {}
    for key, info in (state.get("areas") or {}).items():
        name = STATE_AREA_DISPLAY_NAMES.get(key)
        if not name or not isinstance(info, dict):
            continue
        out[name] = {
            "status": str(info.get("status", "UNKNOWN")).upper(),
            "evidence": info.get("evidence", ""),
            "lifecycle": info.get("lifecycle"),
            "freshness": info.get("freshness"),
            "confidence": info.get("confidence"),
            "source": info.get("source"),
        }
    return out


# --------------------------------------------------------------------------
# Section slicing
# --------------------------------------------------------------------------

def _section(text: str, start_header: str, end_header: str = None) -> str:
    start = text.find(start_header)
    if start == -1:
        return ""
    start += len(start_header)
    end = text.find(end_header, start) if end_header else -1
    if end == -1:
        end = len(text)
    return text[start:end]


def _clean_lines(section_text: str) -> list:
    lines = [l.strip() for l in section_text.split("\n")]
    return [l for l in lines if l and l not in NOISE_LINES and not PAGE_RE.match(l)]


def _name_span(lines: list, i: int) -> tuple:
    """For a status anchor at line index i, returns (name_start_idx, name)
    — grabbing a second line back ONLY when both lines look like a wrapped
    label fragment (short, no sentence-ending period) rather than the tail
    of the previous entry's evidence paragraph (long, ends in '.')."""
    name = lines[i - 1] if i - 1 >= 0 else ""
    start = i - 1
    if len(name) < 16 and not name.endswith(".") and i - 2 >= 0:
        prev = lines[i - 2]
        if len(prev) < 30 and not prev.endswith("."):
            name, start = f"{prev} {name}", i - 2
    return start, name.strip()


def parse_status_table(section_text: str) -> list:
    """Parses an "Area / Status / Evidence"-shaped table (also used for the
    Cross-System Audit's "Connection / Status / Finding" table — same
    shape) into [{"name", "status", "evidence"}]. See _name_span for the
    wrapped-name heuristic this depends on."""
    lines = _clean_lines(section_text)
    anchors = [i for i, l in enumerate(lines) if l in STATUS_WORDS]
    spans = [_name_span(lines, i) for i in anchors]

    entries = []
    for idx, i in enumerate(anchors):
        _, name = spans[idx]
        status = lines[i]
        evidence_end = spans[idx + 1][0] if idx + 1 < len(spans) else len(lines)
        evidence = " ".join(lines[i + 1:evidence_end])
        entries.append({"name": name, "status": status, "evidence": evidence.strip()})
    return entries


def parse_bullets(section_text: str) -> list:
    """Best-effort bullet split for narrative Strengths/Weaknesses-style
    sections (reportlab bullet indentation isn't preserved reliably in
    extracted text, so this groups lines into sentences ending in '.')."""
    lines = _clean_lines(section_text)
    bullets, current = [], []
    for line in lines:
        line = re.sub(r"^[\s•●▪\-*]+", "", line).strip()  # strip leading bullet glyphs
        if not line:
            continue
        current.append(line)
        if line.endswith(".") or line.endswith(".\""):
            bullets.append(" ".join(current))
            current = []
    if current:
        bullets.append(" ".join(current))
    return [b for b in bullets if len(b) > 8]


def parse_opportunity_buckets(text: str) -> dict:
    """Returns {"Build Now": [...], "Improve Existing": [...], ...} —
    titles only (see module docstring: multi-line-wrapped titles are
    best-effort truncated to their first line, acceptable for this
    secondary/contextual list)."""
    opp_section = _section(text, "Product Opportunities", "Opportunity Movement")
    buckets = {}
    for i, bucket in enumerate(OPPORTUNITY_BUCKETS):
        next_bucket = OPPORTUNITY_BUCKETS[i + 1] if i + 1 < len(OPPORTUNITY_BUCKETS) else None
        chunk = _section(opp_section, bucket, next_bucket)
        titles = re.findall(r"#(\d+)\s+([^\n]+)", chunk)
        buckets[bucket] = [f"#{num} {title.strip()}" for num, title in titles]
    return buckets


def parse_exec_fields(text: str) -> dict:
    results = {}
    headers = list(EXEC_FIELDS.keys())
    for i, header in enumerate(headers):
        next_header = headers[i + 1] if i + 1 < len(headers) else "Vital Sync Current State"
        chunk = _section(text, header, next_header)
        lines = _clean_lines(chunk)
        results[EXEC_FIELDS[header]] = " ".join(lines).strip()
    return results


# --------------------------------------------------------------------------
# Product Reality Map
# --------------------------------------------------------------------------

def build_product_reality(path: Path = None, report_date=None) -> dict:
    if path is None:
        path, report_date = find_latest_report()
    if path is None:
        return {
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "report_file": None, "report_date": None,
            "live": [], "partial": [], "missing": [], "prototype": [],
            "strengths": [], "weaknesses": [], "market_gaps": [],
            "build_now": [], "build_next": [], "monitor": [],
            "exec_fields": {}, "areas": {},
            "error": "No Vital_Sync_Weekly_Intelligence_*.pdf found — Product Intelligence unavailable.",
        }

    text = extract_text(path)

    current_state = parse_status_table(_section(text, "Vital Sync Current State", "Changes This Week"))
    cross_system = parse_status_table(_section(text, "Cross-System Audit", "Competitor Watch"))
    all_areas = current_state + cross_system

    areas = {e["name"]: {"status": e["status"], "evidence": e["evidence"]} for e in all_areas if e["name"]}

    # Overlay the structured, lifecycle-aware state registry (Priority-2
    # source) on top of the PDF-table parse. Where both cover the same area,
    # the state file wins — it's what Workflow 01's own reconciliation
    # actually verified, not a best-effort re-parse of its prose.
    state = load_product_state()
    areas.update(_areas_from_state(state))

    def names_with_status(status):
        # Sourced from the final merged `areas` (PDF table + state overlay),
        # not the raw PDF-only `all_areas` list, so areas the state registry
        # tracks but the PDF's own narrative table doesn't render as a row
        # (e.g. Squad Invites) still show up in the snapshot lists below.
        return [name for name, info in areas.items() if info.get("status") == status and name]

    strengths = parse_bullets(_section(text, "Strengths", "Weaknesses"))
    weaknesses = parse_bullets(_section(text, "Weaknesses", "Cross-System Audit"))
    exec_fields = parse_exec_fields(text)
    buckets = parse_opportunity_buckets(text)
    freshness_section_text = _section(text, "Product Source Freshness", "This Week's Actions")

    report_date_str = (report_date or datetime.now().date()).isoformat()
    freshness_info = determine_freshness(report_date_str, freshness_section_text, state)

    return {
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "report_file": str(path),
        "report_date": report_date_str,
        "live": names_with_status("LIVE") + names_with_status("COMPLETE"),
        "partial": names_with_status("PARTIAL"),
        "missing": names_with_status("NOT FOUND") + names_with_status("MISSING"),
        "prototype": names_with_status("PROTOTYPE"),
        # BROKEN is its own bucket, not folded into "missing" — a broken
        # security/integrity finding (e.g. Squad authorization) is a
        # materially different, higher-urgency fact than a feature that
        # simply doesn't exist yet (product-reality refresh spec, section 7).
        "broken": names_with_status("BROKEN") + names_with_status("MISMATCH"),
        "strengths": strengths,
        "weaknesses": weaknesses,
        "market_gaps": [exec_fields.get("biggest_gap", "")] if exec_fields.get("biggest_gap") else [],
        "build_now": buckets.get("Build Now", []) + buckets.get("Improve Existing", []),
        "build_next": buckets.get("Build Next", []) + buckets.get("Experiment", []),
        "monitor": buckets.get("Monitor", []),
        "exec_fields": exec_fields,
        "areas": areas,  # {area_name: {"status", "evidence", ...}} — used by the feature taxonomy below
        # Product Freshness Gate output (product-reality refresh spec,
        # section 4) — the ONLY thing that should ever answer "is this
        # current?". See determine_freshness()/is_stale().
        "freshness_info": freshness_info,
        "product_state_version": (state or {}).get("generated_at"),
    }


def load_or_refresh(max_age_days: int = 1) -> dict:
    """Loads the cached product_reality.json if it's still pointing at the
    newest available report; otherwise regenerates it. max_age_days isn't
    a staleness judgment (see is_stale() for that, against report_date) —
    it just avoids re-parsing the PDF on every single sub-run within the
    same day."""
    latest_path, latest_date = find_latest_report()
    cached = None
    if PRODUCT_REALITY_FILE.exists():
        try:
            with open(PRODUCT_REALITY_FILE) as f:
                cached = json.load(f)
        except (json.JSONDecodeError, OSError):
            cached = None

    needs_refresh = True
    if cached and latest_path:
        needs_refresh = cached.get("report_file") != str(latest_path)
    elif cached and not latest_path:
        needs_refresh = False  # nothing new to find; keep what we have

    if not needs_refresh:
        return cached

    reality = build_product_reality(latest_path, latest_date)
    tmp = PRODUCT_REALITY_FILE.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(reality, f, indent=2)
    import os
    os.replace(tmp, PRODUCT_REALITY_FILE)
    return reality


def is_stale(reality: dict, as_of=None) -> bool:
    """Section 4/5: freshness comes from the Product Freshness Gate
    (freshness_info, set by determine_freshness() in build_product_reality),
    never from calendar age alone. A same-day report Workflow 01 itself
    marked STALE/UNKNOWN/CONFLICTING must still trip this — "latest file"
    is not "current product"."""
    freshness_info = reality.get("freshness_info")
    if freshness_info is not None:
        return freshness_info.get("freshness") not in FRESH_ENOUGH
    # No freshness_info at all means this reality predates the freshness
    # gate (or was hand-built without it) — fall back to the old calendar
    # heuristic, but this path should not be reachable via build_product_reality.
    report_date = reality.get("report_date")
    if not report_date:
        return True
    as_of = as_of or datetime.now().date()
    age = (as_of - datetime.fromisoformat(report_date).date()).days
    return age > STALE_DAYS


# ==========================================================================
# Feature taxonomy — the actual "Product Reality Map" campaign_engine.py
# queries. Each entry maps a marketing-speakable feature concept to the
# Product Intelligence Area(s) it depends on, plus a claim SCOPE:
#   "tracking" — a claim that the raw capability exists/logs data.
#   "guidance"/"advanced" — a claim that Vital Sync actively analyzes/
#     adapts/coaches from that data. A LIVE area does NOT automatically
#     license this stronger claim (section 5: "function exists" vs
#     "function is deep enough to market strongly") — it's downgraded to
#     PARTIAL so the campaign gate narrows the language instead of
#     rubber-stamping it.
#   "core" — the capability itself IS the advanced claim (Alignment, AI
#     chat coach) — already validated deep by the report's own Strengths
#     section, no downgrade.
# "manual_status"/"force_status" bypass area lookup entirely for concepts
# the report doesn't track as a named Area (e.g. voice logging isn't a
# Vital Sync area at all — it's a gap) or where a blanket area status
# would be misleading (Squads specifically, see section 9).
# ==========================================================================

FEATURE_TAXONOMY = {
    "Nutrition Tracking": {"areas": ["Nutrition"], "scope": "tracking"},
    "Nutrition Guidance": {"areas": ["Nutrition"], "scope": "guidance"},
    "Training Tracking": {"areas": ["Training"], "scope": "tracking"},
    "Training Load Intelligence": {"areas": ["Training Load"], "scope": "advanced"},
    "Adaptive Workout Programming": {"areas": ["Progress <-> Program", "Program Adjustment"], "scope": "advanced"},
    "Recovery Tracking": {"areas": ["Recovery"], "scope": "tracking"},
    "Wearable-Based Readiness": {"areas": ["Integrations (wearables)"], "scope": "advanced"},
    "Alignment Engine": {"areas": ["Cross-System Intelligence", "Alignment"], "scope": "core"},
    "AI Chat Coach": {"areas": ["chat coach"], "scope": "core"},
    "Ambient AI Brief": {"areas": ["ambient brief"], "scope": "core"},
    "Gamification / Streaks": {"areas": ["Engagement / Gamification"], "scope": "tracking"},
    "Low-Friction Logging": {
        "areas": [], "scope": "advanced", "manual_status": "MISSING",
        "manual_evidence": "No voice/photo logging area found in Product Intelligence — "
                            "competitors (Vora, Cora) are ahead here per the latest report's Monitor bucket.",
    },
    # Squads (product-reality refresh spec, section 7): "real activity
    # exists" and "secure social system ready to market" are DIFFERENT
    # facts and must not share one taxonomy entry. Any marketing claim that
    # implies a real social/multiplayer experience is gated on the
    # authorization/privacy area, not the activity area — activity being
    # real doesn't make it safe to invite users into an unauthenticated,
    # unfiltered squad list. Each sub-concept below is independently
    # queryable (e.g. by the Opportunity Map) rather than folded into one
    # generic "Squads" verdict.
    "Real Multiplayer Squads": {
        "areas": ["Squads — Authorization / Privacy"], "scope": "squads",
    },
    "Squad Activity Tracking": {"areas": ["Squads — Real Activity"], "scope": "tracking"},
    "Squad Invites": {"areas": ["Squads — Invites"], "scope": "advanced"},
    # Section 14: an explicit opportunity category for the piece that
    # actually connects Alignment to a daily action — currently absent.
    "Directive / Daily Guidance": {"areas": ["Directive Engine"], "scope": "advanced"},
}

DIFFERENTIATOR_FEATURES = {"Alignment Engine", "AI Chat Coach"}


def _match_area(areas: dict, needles: list):
    """Exact name match first, THEN forward containment (needle inside the
    area name) — e.g. needle "Training Load" matches area "Training Load
    <-> Fatigue". Exact match has to come first: without it, the short
    needle "Training" would steal a match meant for the base "Training"
    area and instead resolve against a compound cross-system connector
    area like "Training <-> Recovery" (a different fact — how training
    and recovery interact — not "does Training itself work"). A reverse
    check (area name inside needle) was tried and dropped: it let the
    short area "Training" falsely match the needle "Training Load",
    stealing the match that should go to the actual "Training Load <->
    Fatigue" area."""
    for needle in needles:
        for name, info in areas.items():
            if name.lower() == needle.lower():
                return name, info
    for name, info in areas.items():
        name_lower = name.lower()
        for needle in needles:
            if needle.lower() in name_lower:
                return name, info
    return None, None


def _is_differentiator(reality: dict, feature_key: str, definition: dict) -> bool:
    if feature_key in DIFFERENTIATOR_FEATURES:
        return True
    text = " ".join(reality.get("strengths", [])).lower()
    keywords = [a.lower() for a in definition.get("areas", []) if len(a) > 4]
    return any(kw in text for kw in keywords)


def _claim_status(final_status: str) -> str:
    return {
        "LIVE": "SAFE TO MARKET",
        "COMPLETE": "SAFE TO MARKET",  # Workflow 01's "fully real, not simulated" vocabulary
        "PARTIAL": "MARKET WITH QUALIFIER",
    }.get(final_status, "DO NOT MARKET YET")  # PROTOTYPE / MISSING / BROKEN / MISMATCH / UNKNOWN


def _fit_score(final_status: str, is_differentiator: bool, scope: str) -> int:
    if final_status in ("LIVE", "COMPLETE"):
        return 10 if is_differentiator else 9
    if final_status == "PARTIAL":
        return 7 if scope == "tracking" else 6
    if final_status == "PROTOTYPE":
        return 3
    return 1  # MISSING / BROKEN / MISMATCH / UNKNOWN -> section 19: must not become BUILD NOW


def resolve_feature(reality: dict, feature_key: str) -> dict:
    """The Product Reality Map lookup campaign_engine.py calls for every
    candidate campaign. Returns product-fit score, claim classification,
    and the evidence backing it — never invented, always traced to a
    report Area or an explicit "not tracked" admission."""
    definition = FEATURE_TAXONOMY.get(feature_key)
    if definition is None:
        return {
            "feature": feature_key, "area_matched": None, "base_status": "UNKNOWN",
            "final_status": "UNKNOWN", "evidence": "No taxonomy entry for this feature.",
            "claim_status": "DO NOT MARKET YET", "product_fit": 1, "differentiator": False, "scope": "unknown",
        }

    area_matched = None
    if definition.get("force_status"):
        base_status, evidence = definition["force_status"], definition.get("force_evidence", "")
    elif definition.get("manual_status"):
        base_status, evidence = definition["manual_status"], definition.get("manual_evidence", "")
    else:
        area_matched, info = _match_area(reality.get("areas", {}), definition["areas"])
        if info is None:
            base_status, evidence = "UNKNOWN", "Feature not found in the latest Product Intelligence report."
        else:
            base_status, evidence = info["status"], info["evidence"]

    scope = definition.get("scope", "tracking")
    final_status = base_status
    if scope in ("guidance", "advanced") and base_status in ("LIVE", "COMPLETE"):
        final_status = "PARTIAL"  # exists != deep enough to market strongly (section 5)

    is_differentiator = _is_differentiator(reality, feature_key, definition)
    claim_status = definition.get("force_claim") or _claim_status(final_status)
    fit_score = _fit_score(final_status, is_differentiator, scope)

    return {
        "feature": feature_key, "area_matched": area_matched, "base_status": base_status,
        "final_status": final_status, "evidence": evidence, "claim_status": claim_status,
        "product_fit": fit_score, "differentiator": is_differentiator, "scope": scope,
    }


def dependency_label(fit_score: int, claim_status: str) -> str:
    """The 5-way label (section 33). Product Fit <= 2 is a hard override —
    no combination of other scores can promote a missing-feature campaign
    to BUILD NOW (section 19)."""
    if fit_score <= 2:
        return "BLOCKED BY PRODUCT"
    if claim_status == "MARKET WITH QUALIFIER":
        return "QUALIFIER REQUIRED"
    if fit_score >= 9:
        return "READY TO MARKET"
    if fit_score >= 6:
        return "SAFE TEST"
    return "FUTURE CAMPAIGN"


QUALIFIER_MESSAGES = {
    "Nutrition Guidance": "Keep protein, hydration and calories connected to your goal.",
    "Recovery Tracking": "Log your recovery and see how it connects to your training and nutrition.",
    "Low-Friction Logging": "One place for training, nutrition and recovery.",
    "Training Tracking": "Track your training.",
    # Section 8/12: the CURRENT claim (things line up in one view), never
    # the FUTURE/blocked one (Vital Sync tells you what to do today) —
    # that requires Directive Engine, confirmed absent.
    "Alignment Engine": "See how your training, nutrition and recovery line up in one place.",
    # Section 9: scoped to what the Coach actually has context on today
    # (profile/streak/mission) — not wearables, not full longitudinal
    # history, not adaptive program changes.
    "AI Chat Coach": "Chat with an AI coach that knows your profile, streaks and missions.",
}


def competitive_gap_score(feature_key: str, reality: dict) -> int:
    """Grounded in the report's own competitive framing, not a flat
    default: differentiators score high, areas the report's Biggest
    Competitor Threat explicitly calls out as a competitor lead score low."""
    if feature_key in DIFFERENTIATOR_FEATURES:
        return 8
    threat_text = reality.get("exec_fields", {}).get("biggest_threat", "").lower()
    if feature_key in ("Wearable-Based Readiness", "Training Load Intelligence") and (
        "wearable" in threat_text or "recovery" in threat_text
    ):
        return 3
    if feature_key == "Low-Friction Logging":
        return 3  # section 15: competitors (Vora/Cora) ahead on voice/photo logging
    return 6


# --------------------------------------------------------------------------
# Product Demand Signals (sections 21-22) — market demand that points at a
# MISSING feature becomes a demand signal INSTEAD OF a campaign.
# --------------------------------------------------------------------------

DEMAND_SIGNAL_KEYWORDS = {
    "Voice / Photo Logging": ["voice log", "photo log", "voice tracking", "snap a photo", "natural-language logging"],
    "Apple Health / Wearable Integration": ["apple health", "wearable", "garmin", "whoop", "oura", "fitbit"],
    "Training Load Intelligence": ["training load", "overtraining", "fatigue tracking"],
    "Adaptive Program Adjustment": ["adaptive program", "auto adjust workout", "program adjustment", "plateau"],
}


def _competitor_evidence_for(demand_name: str, reality: dict) -> str:
    haystack_items = reality.get("monitor", []) + reality.get("build_next", []) + reality.get("build_now", [])
    keywords = DEMAND_SIGNAL_KEYWORDS.get(demand_name, [])
    for item in haystack_items:
        item_lower = item.lower()
        if any(kw.split()[0] in item_lower for kw in keywords):
            return item
    threat = reality.get("exec_fields", {}).get("biggest_threat", "")
    return threat if any(kw.split()[0] in threat.lower() for kw in keywords) else ""


def generate_demand_signals(new_signals: list, reality: dict) -> list:
    """new_signals: this run's fresh Market Signals rows. Returns Product
    Demand Signal records (section 21 field set) for any MISSING-feature
    topic that showed up more than once this run — a single hit isn't
    "recurring demand"."""
    out = []
    for demand_name, keywords in DEMAND_SIGNAL_KEYWORDS.items():
        matches = [
            s for s in new_signals
            if any(kw in f"{s.get('Search / Social Query', '')} {s.get('Topic', '')}".lower() for kw in keywords)
        ]
        if len(matches) < 2:
            continue
        audiences = sorted({str(m.get("Audience Segment", "Unknown")) for m in matches})
        queries = sorted({str(m.get("Search / Social Query", "")) for m in matches})
        competitor_evidence = _competitor_evidence_for(demand_name, reality)
        out.append({
            "Feature Requested": demand_name,
            "Audience": ", ".join(audiences) if audiences else "Unknown",
            "Demand Evidence": "; ".join(queries)[:400],
            "Competitor Evidence": competitor_evidence or "None on file this run.",
            "Frequency": len(matches),
            "Potential Marketing Value": "High" if len(matches) >= 4 else "Medium",
            "Recommended Product Priority": "High" if competitor_evidence else "Medium",
            "Status": "New",
        })
    return out
