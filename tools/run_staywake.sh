#!/bin/bash
# Invoked by launchd (com.vitalsync.macstaywake) daily at 7:58 AM Asia/Dubai,
# two minutes before Workflow 01's 8:00 AM job. Keeps the Mac awake through
# both Workflow 01 (8:00 AM) and Workflow 02 (9:00 AM) scheduled runs.
# Appends its own timestamped output to tmp/staywake_scheduled.log.
cd "/Users/farisjohar/Downloads/First Workflow"
LOG="tmp/staywake_scheduled.log"
{
  echo "=== Staywake triggered at $(date) ==="
  /usr/bin/caffeinate -s -t 9000
  echo "=== Staywake released at $(date) ==="
} >> "$LOG" 2>&1
