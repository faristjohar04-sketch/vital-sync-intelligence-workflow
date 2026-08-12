#!/bin/bash
# Reference/manual-testing copy of the command launchd actually runs.
# NOT referenced by the launchd plist itself — pointing ProgramArguments at
# a script file in this project directory was found to be unreliable (see
# project_launchd_spawn_block memory / workflows/01_script_factory.md
# "Known constraints"); the plist inlines this same command directly with
# absolute paths instead.
#
# Invoked manually to reproduce exactly what com.vitalsync.msearchintel runs
# at 7:52 AM daily (before Workflow 01 at 8:00 AM).
# Appends its own timestamped output to tmp/search_intelligence_scheduled.log.
cd "/Users/farisjohar/Downloads/First Workflow"
LOG="tmp/search_intelligence_scheduled.log"
{
  echo "=== Scheduled run at $(date) ==="
  .venv/bin/python -u tools/research_vital_sync.py --live --trigger scheduled
  echo
} >> "$LOG" 2>&1
