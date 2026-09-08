"""Competitor intelligence (workflow sections 14-15): fetches each
watchlist competitor's public homepage (real HTTP request, no key needed),
extracts what a page actually exposes (title, meta description), and
diffs it against the last snapshot to detect real change — never invents
pricing, features, or praise/complaints that aren't on the page.

Anything the homepage doesn't expose (pricing tables behind JS, App Store
review text, etc.) is left blank and — where a fetch fails outright —
marked SOURCE UNAVAILABLE rather than guessed at.

Snapshots persist locally (state/competitor_snapshots.json) purely to
compute "what changed since last time"; the workbook itself remains the
system of record — this file is disposable/regenerable, consistent with
CLAUDE.md's tmp-vs-durable split.
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from config import STATE_DIR
import logger

SNAPSHOT_FILE = STATE_DIR / "competitor_snapshots.json"
USER_AGENT = "Mozilla/5.0 (compatible; VitalSyncMarketingIntel/1.0)"

# Section 14 core watchlist. Websites are the competitor's own marketing
# homepage — the only page we attempt to fetch. "Bevel" has no confirmed
# public domain at time of writing; left None so it's honestly logged as
# SOURCE UNAVAILABLE instead of guessed.
WATCHLIST = {
    "MyFitnessPal": {"website": "https://www.myfitnesspal.com", "class": "Indirect"},
    "WHOOP": {"website": "https://www.whoop.com", "class": "Indirect"},
    "Strava": {"website": "https://www.strava.com", "class": "Indirect"},
    "Hevy": {"website": "https://www.hevyapp.com", "class": "Direct"},
    "Fitbod": {"website": "https://www.fitbod.me", "class": "Direct"},
    "MacroFactor": {"website": "https://www.macrofactorapp.com", "class": "Indirect"},
    "Oura": {"website": "https://ouraring.com", "class": "Indirect"},
    "Garmin": {"website": "https://www.garmin.com", "class": "Indirect"},
    "Freeletics": {"website": "https://www.freeletics.com", "class": "Direct"},
    "Bevel": {"website": None, "class": "Direct"},
}


def _load_snapshots() -> dict:
    if not SNAPSHOT_FILE.exists():
        return {}
    try:
        with open(SNAPSHOT_FILE) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save_snapshots(snapshots: dict) -> None:
    tmp = SNAPSHOT_FILE.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(snapshots, f, indent=2)
    import os
    os.replace(tmp, SNAPSHOT_FILE)


def fetch_homepage(url: str, timeout: float = 8.0):
    """Returns {"title", "description"} or None on failure."""
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        title = soup.title.string.strip() if soup.title and soup.title.string else ""
        desc_tag = soup.find("meta", attrs={"name": "description"}) or soup.find(
            "meta", attrs={"property": "og:description"}
        )
        description = desc_tag.get("content", "").strip() if desc_tag else ""
        return {"title": title, "description": description}
    except (requests.RequestException, Exception):  # noqa: BLE001
        return None


def diff_snapshot(name: str, current: dict, snapshots: dict) -> str:
    previous = snapshots.get(name)
    snapshots[name] = current
    if previous is None:
        return ""  # first time seeing this competitor, nothing to diff
    changes = []
    if previous.get("title") != current.get("title"):
        changes.append(f"Title changed: \"{previous.get('title')}\" -> \"{current.get('title')}\"")
    if previous.get("description") != current.get("description"):
        changes.append("Meta description changed.")
    return " ".join(changes)


def research(existing_rows: dict, stats) -> tuple:
    """existing_rows: {competitor_name: (row_idx, record)} from the current
    Competitor Intelligence sheet (built by campaign_engine/runner via
    workbook.iter_data_rows).

    Returns (updates, new_rows):
      updates  -> [(row_idx, {header: value})] for competitors already in
                  the sheet (update in place, section 15).
      new_rows -> [dict] for newly-discovered competitors not yet tracked.
    """
    snapshots = _load_snapshots()
    updates, new_rows = [], []

    for name, meta in WATCHLIST.items():
        stats.competitors_analyzed += 1
        website = meta["website"]
        fetched = None
        if website:
            stats.sources_checked += 1
            fetched = fetch_homepage(website)
            if fetched is None:
                stats.sources_unavailable += 1
                logger.log_line(f"SOURCE UNAVAILABLE: {name} homepage fetch failed ({website}).")
        else:
            stats.sources_unavailable += 1
            logger.log_line(f"SOURCE UNAVAILABLE: {name} has no confirmed public domain on file.")

        recent_change = ""
        positioning, core_promise = None, None
        if fetched:
            recent_change = diff_snapshot(name, fetched, snapshots)
            positioning = fetched.get("title") or None
            core_promise = fetched.get("description") or None

        if name in existing_rows:
            row_idx, record = existing_rows[name]
            update = {"Date Checked": None}  # caller fills real datetime
            if positioning:
                update["Positioning"] = positioning
            if core_promise:
                update["Core Promise"] = core_promise
            if recent_change:
                update["Recent Change"] = recent_change
                update["Evidence / Notes"] = f"Homepage change detected: {recent_change}"
            updates.append((row_idx, update))
        else:
            new_rows.append({
                "Date Checked": None,
                "Competitor": name,
                "Class": meta["class"],
                "Website / Source": website or "SOURCE UNAVAILABLE — no confirmed domain",
                "Positioning": positioning,
                "Core Promise": core_promise,
                "Threat Level": "Unknown",
                "Action": "MONITOR",
                "Evidence / Notes": (
                    "Newly discovered competitor — homepage-only research; "
                    "pricing/features/reviews need manual follow-up."
                    if fetched else "SOURCE UNAVAILABLE — homepage fetch failed, needs manual research."
                ),
            })

    _save_snapshots(snapshots)
    return updates, new_rows
