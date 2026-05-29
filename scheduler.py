"""Run the collector immediately, then every hour, until stopped (Ctrl+C).

    python scheduler.py

Keep this running in its own terminal alongside the dashboard. The dashboard
auto-refreshes and will show new data as each hourly pass writes snapshots.
"""
from __future__ import annotations

from apscheduler.schedulers.blocking import BlockingScheduler

from collect import run_once

if __name__ == "__main__":
    print("Running initial collection...")
    run_once()

    sched = BlockingScheduler(timezone="UTC")
    sched.add_job(run_once, "interval", hours=1, id="hourly_collect",
                  max_instances=1, coalesce=True)
    print("Scheduled hourly collection. Press Ctrl+C to stop.")
    try:
        sched.start()
    except (KeyboardInterrupt, SystemExit):
        print("\nStopped.")
