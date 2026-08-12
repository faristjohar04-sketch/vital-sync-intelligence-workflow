#!/bin/bash
# Invoked by launchd (com.vitalsync.qualitychecker) daily at 9:00 AM Asia/Dubai,
# one hour after com.vitalsync.scriptfactory (Workflow 01).
# Appends its own timestamped output to tmp/quality_check_scheduled.log.
cd "/Users/farisjohar/Downloads/First Workflow"
LOG="tmp/quality_check_scheduled.log"
{
  echo "=== Scheduled run at $(date) ==="
  .venv/bin/python -u tools/quality_check.py --live --trigger scheduled
  echo
} >> "$LOG" 2>&1
