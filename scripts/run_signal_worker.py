from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from signals.worker import run_signal_worker_once


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run signal async worker.")
    parser.add_argument("--worker-id", default="signal-worker-local", help="Worker id label.")
    parser.add_argument("--max-jobs", type=int, default=1, help="Maximum jobs to process in this run.")
    parser.add_argument("--poll-interval", type=float, default=5.0, help="Polling interval seconds for loop mode.")
    parser.add_argument("--stale-lock-timeout", type=float, default=1800.0, help="Seconds before a RUNNING job lock is requeued.")
    parser.add_argument("--loop", action="store_true", help="Keep polling until interrupted.")
    return parser.parse_args()


def _run_once(worker_id: str, max_jobs: int, stale_lock_timeout: float) -> list[dict]:
    return run_signal_worker_once(
        worker_id=worker_id,
        max_jobs=max_jobs,
        stale_lock_timeout_seconds=stale_lock_timeout,
    )


def main() -> None:
    args = _parse_args()
    if args.loop:
        while True:
            items = _run_once(
                worker_id=args.worker_id,
                max_jobs=args.max_jobs,
                stale_lock_timeout=args.stale_lock_timeout,
            )
            print(json.dumps({"worker_id": args.worker_id, "processed": len(items), "items": items}, ensure_ascii=False))
            time.sleep(max(args.poll_interval, 0.2))
    else:
        items = _run_once(
            worker_id=args.worker_id,
            max_jobs=args.max_jobs,
            stale_lock_timeout=args.stale_lock_timeout,
        )
        print(json.dumps({"worker_id": args.worker_id, "processed": len(items), "items": items}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
