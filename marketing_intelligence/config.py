"""Central configuration for the Marketing Intelligence Agent.

Two things live here, deliberately kept apart from the workbook:

  1. The WEEKLY SCHEDULE (frequency/day/time/timezone) — read by scheduler.py
     to (re)generate a single launchd job. Stored in JSON, not hardcoded,
     per workflow section 5, and mirrored (read-only) into the workbook's
     Config & Lists sheet so it's human-visible without opening a terminal.
  2. The PRODUCT REALITY list (section 18) — what Vital Sync can ACTUALLY do
     right now, classified LIVE / PARTIAL / COMING SOON / PLANNED. This
     starts EMPTY. campaign_engine.py refuses to build a campaign around any
     feature that isn't explicitly marked LIVE or PARTIAL here — an empty
     list means every campaign gets flagged NEEDS PRODUCT INPUT rather than
     inventing functionality.

Everything else (opportunity thresholds, workbook path) also lives here so
no module hardcodes a magic number that another module might disagree with.
"""

import json
import os
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
CONFIG_DIR = PACKAGE_DIR / "config"
STATE_DIR = PACKAGE_DIR / "state"
CONFIG_DIR.mkdir(exist_ok=True)
STATE_DIR.mkdir(exist_ok=True)

SCHEDULE_FILE = CONFIG_DIR / "schedule.json"

# Workbook location: the workbook lives outside the repo (in ~/Downloads),
# per the operating instructions ("use the existing Excel workbook").
# Overridable via .env so this still works if the file is moved.
DEFAULT_WORKBOOK_PATH = str(
    Path.home() / "Downloads" / "Vital_Sync_Marketing_Intelligence_Workflow.xlsx"
)

DEFAULT_SCHEDULE = {
    "frequency": "weekly",
    "day": "monday",
    "time": "08:00",
    "timezone": "Asia/Dubai",
}

DEFAULT_THRESHOLDS = {
    "opportunity_threshold": 8.0,  # BUILD NOW at/above this
    "test_threshold": 6.5,         # TEST at/above this, below opportunity_threshold
    "monitor_threshold": 5.0,      # MONITOR at/above this, below test_threshold — else IGNORE
}

PRODUCT_DEMAND_SIGNALS_SHEET = "Product Demand Signals"
PRODUCT_DEMAND_SIGNALS_HEADERS = [
    "Signal ID", "Date Found", "Feature Requested", "Audience", "Demand Evidence",
    "Competitor Evidence", "Frequency", "Potential Marketing Value",
    "Recommended Product Priority", "Status", "Notes",
]

REQUIRED_SHEETS = [
    "Overview",
    "Market Signals",
    "Competitor Intelligence",
    "Audience Problems",
    "Campaign Opportunities",
    "Active Campaigns",
    "Campaign Performance",
    "Marketing Learnings",
    "Automation Logs",
    "Config & Lists",
]


def workbook_path() -> str:
    return os.environ.get("VITAL_SYNC_MARKETING_WORKBOOK", DEFAULT_WORKBOOK_PATH)


def _load_json(path: Path, default: dict) -> dict:
    if not path.exists():
        return dict(default)
    try:
        with open(path) as f:
            data = json.load(f)
        merged = dict(default)
        merged.update(data)
        return merged
    except (json.JSONDecodeError, OSError):
        return dict(default)


def _save_json(path: Path, data: dict) -> None:
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with open(tmp_path, "w") as f:
        json.dump(data, f, indent=2, sort_keys=True)
    os.replace(tmp_path, path)


def load_schedule() -> dict:
    return _load_json(SCHEDULE_FILE, DEFAULT_SCHEDULE)


def save_schedule(schedule: dict) -> dict:
    current = load_schedule()
    current.update(schedule)
    _save_json(SCHEDULE_FILE, current)
    return current


def load_thresholds() -> dict:
    # Thresholds are authored in the workbook's Config & Lists sheet
    # ("Default Opportunity Threshold" / "Default Test Threshold"); this is
    # just the code-side default used until workbook.py syncs them in.
    return _load_json(CONFIG_DIR / "thresholds.json", DEFAULT_THRESHOLDS)


def save_thresholds(thresholds: dict) -> dict:
    current = load_thresholds()
    current.update(thresholds)
    _save_json(CONFIG_DIR / "thresholds.json", current)
    return current


# NOTE: the manual product_capabilities.json placeholder that used to live
# here (empty-by-default LIVE/PARTIAL/COMING SOON/PLANNED list a human had
# to hand-fill) is retired as of the Product Intelligence integration —
# product_intelligence.py now reads real, current product status straight
# from the latest Vital_Sync_Weekly_Intelligence_*.pdf report instead of
# waiting on manual input. See product_intelligence.resolve_feature().
