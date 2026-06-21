"""
Background scheduler: runs ETL jobs on their configured intervals.
Start with: python scheduler.py
Keep the window open (or run minimized).
"""
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).parent
PYTHON = sys.executable
LOG = BASE / "logs" / "scheduler.log"
LOG.parent.mkdir(exist_ok=True)


def log(msg: str):
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def run(label: str, *args: str):
    log(f"START {label}")
    result = subprocess.run(
        [PYTHON, "main.py", *args],
        cwd=BASE,
        capture_output=False,
    )
    status = "OK" if result.returncode == 0 else f"FAILED (exit {result.returncode})"
    log(f"END   {label} — {status}")


JOBS = [
    {
        "label": "accounts-insights",
        "args": ["accounts-insights", "--days-back", "7", "--to-bigquery"],
        "interval_hours": 2,
        "run_at_hours": None,  # every N hours from start
        "_next": 0.0,
    },
    {
        "label": "dims-refresh",
        "args": ["dims-refresh", "--to-bigquery"],
        "interval_hours": 24,
        "run_at_hours": 6,  # run at 06:00 daily
        "_next": 0.0,
    },
]


def next_run_at_hour(hour: int) -> float:
    from datetime import timedelta
    now = datetime.now()
    target = now.replace(hour=hour, minute=0, second=0, microsecond=0)
    if target.timestamp() <= time.time():
        target += timedelta(days=1)
    return target.timestamp()


def init_jobs():
    now = time.time()
    for job in JOBS:
        if job["run_at_hours"] is not None:
            job["_next"] = next_run_at_hour(job["run_at_hours"])
        else:
            job["_next"] = now  # run immediately on first tick
    return JOBS


def main():
    log("Scheduler started")
    init_jobs()
    for job in JOBS:
        log(f"  {job['label']}: next run at {datetime.fromtimestamp(job['_next']).strftime('%Y-%m-%d %H:%M:%S')}")

    while True:
        now = time.time()
        for job in JOBS:
            if now >= job["_next"]:
                run(job["label"], *job["args"])
                if job["run_at_hours"] is not None:
                    job["_next"] = next_run_at_hour(job["run_at_hours"])
                else:
                    job["_next"] = time.time() + job["interval_hours"] * 3600
                log(f"  {job['label']}: next run at {datetime.fromtimestamp(job['_next']).strftime('%Y-%m-%d %H:%M:%S')}")
        time.sleep(30)


if __name__ == "__main__":
    main()
