"""Generate the synthetic access log deterministically.

Same seed, same log. The story baked into the data:

- `/api/export` is the slow endpoint (report exports: 2-6s per call)
- `/api/reports` throws a burst of 503s from 14:00 to 15:00 on day one
  (think retries piling onto an exhausted connection pool; durations
  cluster around a 30s timeout)
- everything else is boring: fast, mostly 200s, a background hum of 404s

Run:  uv run python gen_logs.py   (writes data/access_log.csv, ~4,000 rows)
"""

import csv
import random
from collections.abc import Iterator
from datetime import datetime, timedelta
from pathlib import Path

ROWS = 4000
START = datetime(2026, 11, 10, 6, 0, 0)
OUT = Path(__file__).parent / "data" / "access_log.csv"

ENDPOINTS = {
    "/api/auth": (60, 180, 0.005),        # (p50_ms, spread, error_rate)
    "/api/orders": (90, 250, 0.01),
    "/api/reports": (140, 400, 0.02),
    "/api/export": (2400, 3200, 0.03),    # the slow one
    "/api/health": (8, 30, 0.0),
}


def rows() -> Iterator[dict]:
    rng = random.Random(42)
    for _ in range(ROWS):
        ts = START + timedelta(seconds=rng.randint(0, 48 * 3600))
        # export is rare, auth/orders are common
        endpoint = rng.choices(
            list(ENDPOINTS), weights=[25, 30, 25, 5, 15], k=1
        )[0]
        p50, spread, err = ENDPOINTS[endpoint]
        duration = max(3, int(rng.gauss(p50, spread / 3)))

        status = 200
        if rng.random() < 0.04:
            status = 404  # background noise
        elif rng.random() < err:
            status = 500

        # the incident: /api/reports 503 storm 14:00-15:00 on day one
        if (
            endpoint == "/api/reports"
            and ts.day == 10
            and ts.hour == 14
            and rng.random() < 0.8
        ):
            status = 503
            duration = max(duration, int(rng.gauss(29000, 5000)))  # 30s timeout

        yield {
            "timestamp": ts.isoformat(timespec="seconds"),
            "endpoint": endpoint,
            "status_code": status,
            "duration_ms": duration,
        }


def main():
    OUT.parent.mkdir(exist_ok=True)
    with OUT.open("w", newline="") as f:
        w = csv.DictWriter(
            f, fieldnames=["timestamp", "endpoint", "status_code", "duration_ms"]
        )
        w.writeheader()
        w.writerows(rows())
    print(f"wrote {ROWS} rows to {OUT}")


if __name__ == "__main__":
    main()
