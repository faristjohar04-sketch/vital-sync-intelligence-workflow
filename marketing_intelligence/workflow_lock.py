"""Workflow lock (section 32): stops a scheduled and a manual run — or two
manual runs — from writing to the workbook at the same time.

A single lock file at marketing_intelligence/state/workflow.lock holds the
active run's PID, start time and trigger. A lock older than STALE_MINUTES
with no matching release is treated as an abandoned run (crash, killed
process) rather than a live one, and is reclaimed automatically — mirroring
the stale-run handling already used by research_vital_sync.py.
"""

import json
import os
import time
from contextlib import contextmanager
from datetime import datetime, timedelta

from config import STATE_DIR

LOCK_FILE = STATE_DIR / "workflow.lock"
STALE_MINUTES = 30


class WorkflowAlreadyRunning(Exception):
    pass


def _read_lock():
    if not LOCK_FILE.exists():
        return None
    try:
        with open(LOCK_FILE) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def _is_stale(lock: dict) -> bool:
    try:
        started = datetime.fromisoformat(lock["started_at"])
    except (KeyError, ValueError):
        return True
    if datetime.now() - started > timedelta(minutes=STALE_MINUTES):
        return True
    # PID no longer alive -> definitely stale.
    pid = lock.get("pid")
    if pid:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        except PermissionError:
            pass  # process exists, just owned by someone else
    return False


def is_locked() -> dict:
    """Returns the active lock dict if genuinely held, else None (clearing
    any stale lock file it finds along the way)."""
    lock = _read_lock()
    if lock is None:
        return None
    if _is_stale(lock):
        LOCK_FILE.unlink(missing_ok=True)
        return None
    return lock


@contextmanager
def acquire(run_id: str, trigger: str):
    existing = is_locked()
    if existing:
        raise WorkflowAlreadyRunning(
            f"WORKFLOW ALREADY RUNNING (run_id={existing.get('run_id')}, "
            f"trigger={existing.get('trigger')}, started_at={existing.get('started_at')})"
        )
    lock = {
        "run_id": run_id,
        "trigger": trigger,
        "pid": os.getpid(),
        "started_at": datetime.now().isoformat(timespec="seconds"),
    }
    with open(LOCK_FILE, "w") as f:
        json.dump(lock, f)
    try:
        yield
    finally:
        LOCK_FILE.unlink(missing_ok=True)
