"""Run tracking: a RunStats accumulator, an Automation Logs sheet writer,
and a plain-text run log under tmp/ for debugging (disposable, per
CLAUDE.md's tmp/ convention — the Automation Logs sheet is the durable
record).
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import workbook

REPO_ROOT = Path(__file__).resolve().parent.parent
TMP_LOG = REPO_ROOT / "tmp" / "marketing_intelligence_run.log"


def new_run_id() -> str:
    return "MI-" + datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:4]


@dataclass
class RunStats:
    run_id: str
    workflow: str
    trigger: str  # "Manual" | "Scheduled"
    started_at: datetime = field(default_factory=datetime.now)
    sources_checked: int = 0
    sources_unavailable: int = 0
    competitors_analyzed: int = 0
    audience_segments: int = 0
    opportunities_generated: int = 0
    build_now: int = 0
    tests: int = 0
    monitors: int = 0
    rejected: int = 0
    report_file: str = ""
    errors: list = field(default_factory=list)
    success: bool = True

    def note_error(self, stage: str, reason: str):
        self.errors.append(f"[{stage}] {reason}")
        self.success = False
        log_line(f"ERROR run_id={self.run_id} stage={stage} reason={reason}")

    def duration_seconds(self) -> float:
        return round((datetime.now() - self.started_at).total_seconds(), 1)

    def as_row(self) -> dict:
        return {
            "Run ID": self.run_id,
            "Date": datetime.now(),
            "Workflow": self.workflow,
            "Trigger": self.trigger,
            "Success": "Yes" if self.success else "No",
            "Duration Seconds": self.duration_seconds(),
            "Sources Checked": self.sources_checked,
            "Sources Unavailable": self.sources_unavailable,
            "Competitors Analyzed": self.competitors_analyzed,
            "Audience Segments": self.audience_segments,
            "Opportunities Generated": self.opportunities_generated,
            "Build Now": self.build_now,
            "Tests": self.tests,
            "Monitors": self.monitors,
            "Rejected": self.rejected,
            "Report File": self.report_file,
            "Errors / Notes": "; ".join(self.errors) if self.errors else "",
        }


def log_line(message: str) -> None:
    TMP_LOG.parent.mkdir(exist_ok=True)
    with open(TMP_LOG, "a") as f:
        f.write(f"{datetime.now().isoformat(timespec='seconds')} {message}\n")


def write_automation_log(wb, stats: RunStats) -> None:
    """Appends one row to the already-open (edit-in-progress) workbook's
    Automation Logs sheet. Caller is responsible for the workbook.safe_write()
    context — this never opens/saves the file itself, so it composes cleanly
    with every other sheet write in the same run."""
    ws = wb["Automation Logs"]
    formula_cols = workbook.formula_columns(ws)
    row_idx = workbook.next_empty_row(ws, formula_cols)
    workbook.write_row(ws, row_idx, stats.as_row(), formula_cols)


def dry_run_log(stats: RunStats) -> None:
    log_line(f"DRY RUN — would append Automation Logs row: {stats.as_row()}")
