"""Weekly schedule management (workflow sections 5-6): parses natural
schedule commands, updates the single JSON config (config.py), and
regenerates a single crontab entry — never a duplicate one.

Manages `cron`, not `launchd`. This module originally rendered/installed a
`launchd` plist (see git history), matching the mechanism every other
Vital Sync scheduled job used at the time. On 2026-08-22 this project
abandoned `launchd` entirely after a spawn-block bug (`xpcproxy` dying
mid identity-resolution, `EX_CONFIG`/exit 78 on every job, surviving a
reboot, a Full Disk Access re-check, and a Directory Services cache flush)
— see `project_launchd_spawn_block` memory / `workflows/00_search_intelligence.md`
"Scheduling" section for the full incident. All scheduled jobs, including
this one, now run via a single shared user crontab (`crontab -l`).

This module owns exactly the crontab line(s) tagged with CRON_MARKER /
CRON_ONEOFF_MARKER below — it reads the whole crontab, replaces only its
own tagged line(s), and writes the rest back untouched, so it can safely
share one crontab with the other 5 Vital Sync jobs (and anything else the
user adds) without ever clobbering them.

IMPORTANT: install_job() actually writes the crontab (makes the schedule
live/unattended). This module deliberately separates "compute what the
schedule/cron line would be" (render_cron_line, next_run) from "make it
live" (install_job) — the runner build stops short of calling install_job()
until a human approves going live, per workflow section 40.
"""

import re
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

import config

CRON_MARKER = "vitalsync-mmarketingintel"
CRON_ONEOFF_MARKER = "vitalsync-mmarketingintel-oneoff"

REPO_ROOT = Path(__file__).resolve().parent.parent
PYTHON_BIN = REPO_ROOT / ".venv" / "bin" / "python"
CLI_SCRIPT = REPO_ROOT / "tools" / "vital_sync_marketing.py"
LOG_FILE = REPO_ROOT / "tmp" / "marketing_intelligence_launchd.log"
# ^ filename kept as-is (not renamed to "_cron_") purely to avoid orphaning
# whatever log-rotation/tailing habits already point at this path.

DAY_TO_WEEKDAY = {
    "sunday": 0, "monday": 1, "tuesday": 2, "wednesday": 3,
    "thursday": 4, "friday": 5, "saturday": 6,
}
# cron's day-of-week field: 0 = Sunday ... 6 = Saturday — conveniently the
# same indexing this dict already used for launchd's StartCalendarInterval
# Weekday, so it's reused as-is for cron fields too.

TIME_RE = re.compile(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", re.IGNORECASE)


def parse_time(text: str) -> str:
    """'8 am' / '08:00' / '10:30pm' -> 'HH:MM' (24h). Raises ValueError."""
    match = TIME_RE.search(text.strip())
    if not match:
        raise ValueError(f"Could not parse a time from: {text!r}")
    hour, minute, meridiem = match.groups()
    hour, minute = int(hour), int(minute or 0)
    if meridiem:
        meridiem = meridiem.lower()
        if meridiem == "pm" and hour != 12:
            hour += 12
        if meridiem == "am" and hour == 12:
            hour = 0
    return f"{hour:02d}:{minute:02d}"


def parse_schedule_command(text: str) -> dict:
    """Parses commands like:
      "RUN EVERY MONDAY AT 8 AM"
      "RUN EVERY FRIDAY AT 10 AM"
      "RUN WEEKLY ON SUNDAY"
    Returns a schedule dict (frequency/day/time/timezone) to pass to
    config.save_schedule(). Raises ValueError if unparseable.
    """
    t = text.strip().lower()
    day_match = re.search(r"\b(sunday|monday|tuesday|wednesday|thursday|friday|saturday)\b", t)
    if not day_match:
        raise ValueError(f"No weekday found in: {text!r}")
    day = day_match.group(1)

    updates = {"frequency": "weekly", "day": day}
    time_match = re.search(r"\bat\s+(.+)$", t)
    if time_match:
        updates["time"] = parse_time(time_match.group(1))
    return updates


def _read_crontab_lines() -> list:
    """Returns the current user's crontab as a list of lines. An empty/
    nonexistent crontab (the common "no crontab for user" case) is treated
    as an empty list, not an error."""
    result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    if result.returncode != 0:
        return []
    return [line for line in result.stdout.splitlines() if line.strip()]


def _write_crontab_lines(lines: list) -> None:
    body = "\n".join(lines) + "\n" if lines else ""
    result = subprocess.run(["crontab", "-"], input=body, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"crontab install failed: {result.stderr.strip()}")


def _upsert_marked_line(marker: str, new_line: str) -> None:
    """Replaces any existing crontab line tagged with `marker` with
    `new_line`, leaving every other line (this project's other 5 scheduled
    jobs, or anything the user added by hand) untouched."""
    lines = [line for line in _read_crontab_lines() if marker not in line]
    lines.append(new_line)
    _write_crontab_lines(lines)


def _remove_marked_line(marker: str) -> None:
    lines = [line for line in _read_crontab_lines() if marker not in line]
    _write_crontab_lines(lines)


def render_cron_line(schedule: dict = None) -> str:
    schedule = schedule or config.load_schedule()
    weekday = DAY_TO_WEEKDAY[schedule["day"].lower()]
    hour, minute = (int(x) for x in schedule["time"].split(":"))
    command = (
        f'/bin/bash -c \'cd "{REPO_ROOT}" && {{ echo "=== Scheduled run at $(date) ==="; '
        f'"{PYTHON_BIN}" -u "{CLI_SCRIPT}" "RUN WEEKLY MARKETING INTELLIGENCE" '
        f'--trigger scheduled; echo; }} >> "{LOG_FILE}" 2>&1\''
    )
    return f"{minute} {hour} * * {weekday} {command} # {CRON_MARKER}"


def next_run(schedule: dict = None) -> datetime:
    schedule = schedule or config.load_schedule()
    weekday = DAY_TO_WEEKDAY[schedule["day"].lower()]  # 0=Sunday
    hour, minute = (int(x) for x in schedule["time"].split(":"))
    now = datetime.now()
    python_weekday = (weekday - 1) % 7  # datetime.weekday(): 0=Monday
    days_ahead = (python_weekday - now.weekday()) % 7
    candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0) + timedelta(days=days_ahead)
    if candidate <= now:
        candidate += timedelta(days=7)
    return candidate


def is_installed() -> bool:
    return any(CRON_MARKER in line for line in _read_crontab_lines())


def install_job(schedule: dict = None) -> str:
    """Renders this job's crontab line and upserts it into the shared user
    crontab — replaces the existing line under CRON_MARKER if present
    (so a schedule change UPDATES the one entry rather than stacking a
    duplicate, section 6), leaves every other crontab line untouched."""
    schedule = schedule or config.load_schedule()
    LOG_FILE.parent.mkdir(exist_ok=True)
    line = render_cron_line(schedule)
    _upsert_marked_line(CRON_MARKER, line)
    return line


def update_schedule(text: str) -> dict:
    updates = parse_schedule_command(text)
    return config.save_schedule(updates)


def parse_oneoff_command(text: str) -> datetime:
    """"RUN TODAY" / "RUN TOMORROW" / "RUN ON 2026-08-20" -> datetime (at
    the configured default schedule time)."""
    t = text.strip().lower()
    schedule = config.load_schedule()
    hour, minute = (int(x) for x in schedule["time"].split(":"))
    now = datetime.now()
    if "today" in t or t.strip() == "run now":
        return now
    if "tomorrow" in t:
        return (now + timedelta(days=1)).replace(hour=hour, minute=minute, second=0, microsecond=0)
    date_match = re.search(r"(\d{4}-\d{2}-\d{2})", t)
    if date_match:
        return datetime.strptime(date_match.group(1), "%Y-%m-%d").replace(hour=hour, minute=minute)
    raise ValueError(f"Could not parse a one-off run date from: {text!r}")


def render_oneoff_cron_line(when: datetime) -> str:
    """cron has no "year" field, so a plain day/month/hour/minute line
    would silently recur every year on that date. Self-removing instead:
    the command runs, then strips its own tagged line back out of the
    crontab — a true one-shot regardless of year."""
    command = (
        f'/bin/bash -c \'cd "{REPO_ROOT}" && {{ echo "=== One-off run at $(date) ==="; '
        f'"{PYTHON_BIN}" -u "{CLI_SCRIPT}" "RUN WEEKLY MARKETING INTELLIGENCE" '
        f'--trigger scheduled; echo; }} >> "{LOG_FILE}" 2>&1; '
        f'(crontab -l 2>/dev/null | grep -v "{CRON_ONEOFF_MARKER}" | crontab -) || true\''
    )
    return f"{when.minute} {when.hour} {when.day} {when.month} * {command} # {CRON_ONEOFF_MARKER}"


def install_oneoff_job(when: datetime) -> str:
    LOG_FILE.parent.mkdir(exist_ok=True)
    line = render_oneoff_cron_line(when)
    _upsert_marked_line(CRON_ONEOFF_MARKER, line)
    return line
