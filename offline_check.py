"""Offline verification — no model, no network, no API keys.

    uv run python offline_check.py

What it checks:
1. The tool contract (@tool docstring/inputs) builds correctly.
2. The data contains the incident we planted (so the agent task is solvable).
3. LocalPythonExecutor — the same sandbox the CodeAgent runs its code in —
   evaluates a hand-written version of the analysis the agent is expected to
   write, calling the tool the same way the agent would, and gets the answer.
4. The sandbox actually blocks: os.system and open() both raise
   InterpreterError instead of executing.
"""

import statistics
from collections import Counter, defaultdict

from smolagents.local_python_executor import InterpreterError, LocalPythonExecutor

from gen_logs import main as gen
from tools import _load, access_log

# The analysis the agent is expected to produce on its own.
# Note how it starts: call the tool, get real Python objects back.
AGENT_STYLE_CODE = """
import statistics
from collections import defaultdict, Counter

rows = access_log()
by_endpoint = defaultdict(list)
fives_by_hour = Counter()
for r in rows:
    by_endpoint[r["endpoint"]].append(r["duration_ms"])
    if r["status_code"] >= 500:
        fives_by_hour[r["timestamp"][:13].replace("T", " ")] += 1

worst = max(by_endpoint, key=lambda e: statistics.median(by_endpoint[e]))
durations = sorted(by_endpoint[worst])
spike_hour = fives_by_hour.most_common(1)[0][0]

final_answer(
    f"slowest={worst},median={statistics.median(durations)},"
    f"p95={durations[int(len(durations) * 0.95)]},spike={spike_hour}"
)
"""

ESCAPE_OS = "import os\nfinal_answer(os.system('echo PWNED'))"
ESCAPE_OPEN = "final_answer(open('/etc/passwd').read())"


def test_tool_contract():
    assert access_log.name == "access_log"
    assert "access logs" in access_log.description
    assert access_log.inputs == {}
    rows = access_log()
    assert isinstance(rows, list) and isinstance(rows[0], dict)
    print(f"OK  tool contract: @tool builds, returns list[dict] ({len(rows)} rows)")


def test_data_has_the_incident():
    by_endpoint = defaultdict(list)
    fives_by_hour = Counter()
    for r in _load():
        by_endpoint[r["endpoint"]].append(r["duration_ms"])
        if r["status_code"] >= 500:
            fives_by_hour[r["timestamp"][:13].replace("T", " ")] += 1

    worst = max(by_endpoint, key=lambda e: statistics.median(by_endpoint[e]))
    assert worst == "/api/export", f"expected /api/export worst, got {worst}"

    spike, count = fives_by_hour.most_common(1)[0]
    assert spike == "2026-11-10 14", f"expected spike at 14:00, got {(spike, count)}"
    print(f"OK  data: slowest={worst}, 5xx spike at {spike} ({count} errors)")


def test_executor_runs_the_analysis():
    executor = LocalPythonExecutor(
        additional_authorized_imports=["csv", "statistics", "collections", "datetime"]
    )
    # the agent wires tools into the sandbox exactly like this
    executor.send_tools({"access_log": _load, "final_answer": lambda x: x})
    out = executor(AGENT_STYLE_CODE)

    assert out.is_final_answer
    assert "slowest=/api/export" in out.output
    assert "spike=2026-11-10 14" in out.output
    print(f"OK  executor: agent-style code evaluates -> {out.output}")


def test_sandbox_blocks_escapes():
    executor = LocalPythonExecutor(additional_authorized_imports=[])
    executor.send_tools({"final_answer": lambda x: x})

    for label, code in [("import os", ESCAPE_OS), ("open()", ESCAPE_OPEN)]:
        try:
            executor(code)
            raise AssertionError(f"{label} executed — sandbox did NOT block")
        except InterpreterError as e:
            assert "allowed" in str(e) or "Forbidden" in str(e), str(e)
            print(f"OK  sandbox: {label} blocked (InterpreterError)")


if __name__ == "__main__":
    gen()
    test_tool_contract()
    test_data_has_the_incident()
    test_executor_runs_the_analysis()
    test_sandbox_blocks_escapes()
    print("\nAll offline checks passed. Set AGENT_MODEL (+ key) and run agent.py for real.")
