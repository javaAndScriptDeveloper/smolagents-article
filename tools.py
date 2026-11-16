"""The one tool our agent gets: the access log itself.

The docstring IS the tool description the model sees. No JSON schema file, no
register step — type hints plus this docstring are the whole contract.

Note the return type: a list of dicts, not a file path. The LocalPythonExecutor
sandbox blocks open() by design — data reaches the agent through tool return
values, which are passed into the sandbox as real Python objects (no
serialization round-trip, and the rows themselves never enter the prompt;
only what the generated code prints does).
"""

import csv
from pathlib import Path

from smolagents import tool

LOG_PATH = Path(__file__).parent / "data" / "access_log.csv"


def _load():
    with open(LOG_PATH, newline="") as f:
        return [
            {
                "timestamp": r["timestamp"],
                "endpoint": r["endpoint"],
                "status_code": int(r["status_code"]),
                "duration_ms": int(r["duration_ms"]),
            }
            for r in csv.DictReader(f)
        ]


@tool
def access_log() -> list[dict]:
    """Returns two days of API access logs as a list of dicts, newest first.

    Each row has:
    - timestamp: ISO-8601 string, e.g. '2026-11-10T14:23:01'
    - endpoint: one of /api/auth, /api/orders, /api/reports, /api/export, /api/health
    - status_code: int (200, 404, 500, 503)
    - duration_ms: int, request duration in milliseconds

    Group with collections.defaultdict; compute medians with statistics.
    """
    return _load()
