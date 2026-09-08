"""Vital Sync — Marketing Intelligence Agent.

Modular WAT Layer-3 tooling that reads/writes the existing
Vital_Sync_Marketing_Intelligence_Workflow.xlsx workbook. See
workflows/vital_sync_marketing_intelligence.md for the SOP this package
implements, and CLAUDE.md for the framework this sits inside.

Scheduled and manual runs both go through runner.run(), so the two
execution paths can never diverge (see config.py / scheduler.py for the
configurable weekly schedule, workflow_lock.py for concurrency safety, and
workbook.py for crash-safe writes).
"""
