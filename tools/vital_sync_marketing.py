#!/usr/bin/env python3
"""Vital Sync — Marketing Intelligence Agent CLI (Layer-3 entrypoint).

Every command below routes through marketing_intelligence/runner.py's
single run() function — see workflows/vital_sync_marketing_intelligence.md
for the full SOP this implements. This script is intentionally thin: all
real logic lives in the marketing_intelligence/ package.

Usage:
    python tools/vital_sync_marketing.py "RUN NOW"
    python tools/vital_sync_marketing.py "DRY RUN"
    python tools/vital_sync_marketing.py "RUN MARKET RESEARCH"
    python tools/vital_sync_marketing.py "RUN COMPETITOR INTELLIGENCE"
    python tools/vital_sync_marketing.py "RUN AUDIENCE INTELLIGENCE"
    python tools/vital_sync_marketing.py "RUN CAMPAIGN INTELLIGENCE"
    python tools/vital_sync_marketing.py "RUN PERFORMANCE ANALYSIS"
    python tools/vital_sync_marketing.py "RUN WEEKLY MARKETING INTELLIGENCE" --trigger scheduled
    python tools/vital_sync_marketing.py "STATUS"
    python tools/vital_sync_marketing.py "RUN EVERY MONDAY AT 8 AM"
    python tools/vital_sync_marketing.py "ACTIVATE SCHEDULE"
    python tools/vital_sync_marketing.py "RUN TOMORROW" --activate
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "marketing_intelligence"))

import runner  # noqa: E402
import scheduler  # noqa: E402

DIRECT_MODE_COMMANDS = {
    "RUN WEEKLY MARKETING INTELLIGENCE": "WEEKLY",
    "RUN FULL MARKETING INTELLIGENCE": "FULL",
    "RUN MARKET RESEARCH": "MARKET_RESEARCH",
    "RUN COMPETITOR INTELLIGENCE": "COMPETITOR",
    "RUN AUDIENCE INTELLIGENCE": "AUDIENCE",
    "RUN CAMPAIGN INTELLIGENCE": "CAMPAIGN",
    "RUN PERFORMANCE ANALYSIS": "PERFORMANCE",
}


def _print_result(result):
    print(f"Run complete. Success={result.stats.success} Duration={result.stats.duration_seconds()}s")
    for line in result.summary_lines:
        print(line)
    if result.report_path:
        print(f"Report: {result.report_path}")
    if result.stats.errors:
        print("Errors:")
        for e in result.stats.errors:
            print(f"  - {e}")


def _print_status(data):
    if "error" in data:
        print(f"ERROR: {data['error']}")
        return
    sched = data["schedule"]
    print("Workflow Status:", data["workflow_status"])
    print("Last Successful Run:", data["last_successful_run"])
    print(f"Schedule: {sched['frequency']} on {sched['day'].title()} at {sched['time']} ({sched['timezone']})")
    print("Next Scheduled Run:", scheduler.next_run(sched).strftime("%Y-%m-%d %H:%M") + f" {sched['timezone']}")
    print("Scheduled Job Installed:", scheduler.is_installed())
    print("Signals Stored:", data["signals_stored"])
    print("Competitors Tracked:", data["competitors_tracked"])
    print("Audience Problems Stored:", data["audience_problems_stored"])
    print("Campaign Opportunities:", data["campaign_opportunities"])
    print("BUILD NOW Count:", data["build_now_count"])
    print("TEST Count:", data["test_count"])
    print("Active Campaigns:", data["active_campaigns"])
    print("Marketing Learnings:", data["marketing_learnings"])
    print("Product Intelligence Report:", data["product_intelligence_report"])
    print("Product Intelligence Date:", data["product_intelligence_date"],
          "(STALE)" if data["product_intelligence_stale"] else "")
    print("Product Freshness Gate:", data.get("product_intelligence_freshness", "UNKNOWN"),
          f"(confidence {data.get('product_intelligence_confidence', 'UNKNOWN')})")
    print("Last Error:", data["last_error"])


def _print_reclassification(comparisons):
    if not comparisons:
        print("No existing Campaign Opportunities rows matched a known audience-problem angle to reclassify.")
        return
    print(f"\n=== Reclassification of {len(comparisons)} existing campaign(s) against current Product Intelligence ===\n")
    for c in comparisons:
        print(f"Campaign: {c['name']}")
        print(f"  Previous: Status={c['previous_status']!r}  Confidence={c['previous_confidence']!r}  Product Feature={c['previous_product_feature']!r}")
        print(f"  New:      Status={c['new_status']!r}  Confidence={c['new_confidence']!r}  Product Fit={c['new_product_fit']}  Product Feature={c['new_product_feature']!r}")
        print(f"  New Core Message: {c['new_core_message']}")
        print(f"  Reason: {c['reason']}")
        print()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", help="e.g. \"RUN NOW\", \"STATUS\", \"DRY RUN\", \"RUN EVERY MONDAY AT 8 AM\"")
    # Lowercase, matching the --trigger convention every other tool in this
    # repo uses (research_vital_sync.py, quality_check.py, weekly_cleanup.py)
    # and what scheduler.py's cron line actually passes (`--trigger
    # scheduled`). A prior capitalized-choices version of this flag silently
    # broke every scheduled run (argparse rejected "scheduled") until the
    # 2026-09-07 firing surfaced it — see workflow doc "Known constraints".
    parser.add_argument("--trigger", default="manual", choices=["manual", "scheduled"])
    parser.add_argument("--activate", action="store_true", help="Actually install/update the cron entry for schedule commands (otherwise preview only).")
    args = parser.parse_args()

    command = args.command.strip().upper()
    trigger = args.trigger.capitalize()  # "manual"/"scheduled" (CLI/cron convention) -> "Manual"/"Scheduled" (Automation Logs display convention)

    if command == "STATUS":
        _print_status(runner.status())
        return

    if command == "DRY RUN":
        result = runner.run("FULL", trigger=trigger, dry_run=True)
        _print_result(result)
        _print_reclassification(runner.reclassification_report())
        return

    if command in ("RUN NOW", "RUN TODAY"):
        result = runner.run("FULL", trigger=trigger, dry_run=False)
        _print_result(result)
        return

    if command in DIRECT_MODE_COMMANDS:
        result = runner.run(DIRECT_MODE_COMMANDS[command], trigger=trigger, dry_run=False)
        _print_result(result)
        return

    if command == "ACTIVATE SCHEDULE":
        line = scheduler.install_job()
        print(f"Installed/updated crontab entry:\n  {line}")
        print(f"Next scheduled run: {scheduler.next_run()}")
        return

    if command.startswith("RUN EVERY") or command.startswith("RUN WEEKLY ON"):
        new_schedule = scheduler.update_schedule(command)
        print(f"Schedule updated: {new_schedule}")
        print(f"Next scheduled run would be: {scheduler.next_run(new_schedule)}")
        if scheduler.is_installed():
            scheduler.install_job(new_schedule)
            print("Existing crontab entry updated in place (was already active).")
        elif args.activate:
            scheduler.install_job(new_schedule)
            print("Crontab entry installed and activated.")
        else:
            print("Job not yet active. Re-run with --activate, or use \"ACTIVATE SCHEDULE\", to make it live.")
        return

    if command == "RUN TOMORROW" or command.startswith("RUN ON "):
        when = scheduler.parse_oneoff_command(command)
        if args.activate:
            path = scheduler.install_oneoff_job(when)
            print(f"One-off run scheduled for {when} -> {path}")
        else:
            print(f"Would schedule a one-off run for {when}. Re-run with --activate to install it.")
        return

    print(f"Unrecognized command: {args.command!r}")
    print("See the docstring at the top of this file for supported commands.")
    sys.exit(1)


if __name__ == "__main__":
    main()
