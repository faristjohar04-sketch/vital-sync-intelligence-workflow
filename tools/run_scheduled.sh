#!/bin/bash
# Invoked by launchd (com.vitalsync.scriptfactory) daily at 8:00 AM Asia/Dubai.
# Appends its own timestamped output to tmp/script_factory_scheduled.log.
cd "/Users/farisjohar/Downloads/First Workflow"
LOG="tmp/script_factory_scheduled.log"
{
  echo "=== Scheduled run at $(date) ==="
  .venv/bin/python -u tools/generate_content.py --live --trigger scheduled
  echo
} >> "$LOG" 2>&1
