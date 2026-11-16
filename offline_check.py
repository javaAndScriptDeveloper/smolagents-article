"""Offline verification: no model, no network, no API keys.

    uv run python offline_check.py

What it checks:
1. The tool contract (@tool docstring/inputs) builds correctly.
2. The data contains the incident we planted (so the task is solvable), with a
   clear margin over the background noise.
3. LocalPythonExecutor, the same interpreter CodeAgent uses, evaluates a
   hand-written version of the analysis, calling the real tool object.
4. The sandbox blocks `import os` and `open()` (InterpreterError, exact reasons).
5. The real CodeAgent loop (prompting, code extraction, executor, final_answer,
   error feedback) runs end to end against a SCRIPTED model that returns canned
   code. This exercises smolagents' plumbing; it says nothing about how well
   any real LLM writes the code. That needs agent.py and a model.
"""

import statistics
from collections import Counter, defaultdict

from smolagents import ChatMessage, CodeAgent, Model
from smolagents.default_tools import FinalAnswerTool
from smolagents.local_python_executor import InterpreterError, LocalPythonExecutor

from agent import AUTHORIZED_IMPORTS
from gen_logs import main as gen
from tools import access_log

# The analysis the agent is expected to produce on its own.
# Note how it starts: call the tool, get real Python objects back.
AGENT_STYLE_CODE = """
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
"""

ANSWER_CODE = """
final_answer(
    f"slowest={worst},median={statistics.median(durations)},"
    f"p95={durations[int(len(durations) * 0.95)]},spike={spike_hour}"
)
"""

# imports the generated code needs; all are in the executor's default allow-list
IMPORTS = "import statistics\nfrom collections import defaultdict, Counter\n"

ESCAPE_OS = "import os\nfinal_answer(os.system('echo PWNED'))"
ESCAPE_OPEN = "final_answer(open('/etc/passwd').read())"


def analyze(rows):
    by_endpoint = defaultdict(list)
    fives_by_hour = Counter()
    for r in rows:
        by_endpoint[r["endpoint"]].append(r["duration_ms"])
        if r["status_code"] >= 500:
            fives_by_hour[r["timestamp"][:13].replace("T", " ")] += 1
    return by_endpoint, fives_by_hour


def test_tool_contract():
    assert access_log.name == "access_log"
    assert "access logs" in access_log.description
    assert access_log.inputs == {}
    rows = access_log()
    assert isinstance(rows, list) and isinstance(rows[0], dict)
    assert set(rows[0]) == {"timestamp", "endpoint", "status_code", "duration_ms"}
    print(f"OK  tool contract: @tool builds, returns list[dict] ({len(rows)} rows)")


def test_data_has_the_incident():
    by_endpoint, fives_by_hour = analyze(access_log())

    worst = max(by_endpoint, key=lambda e: statistics.median(by_endpoint[e]))
    assert worst == "/api/export", f"expected /api/export worst, got {worst}"

    (spike, count), (_, runner_up) = fives_by_hour.most_common(2)
    assert spike == "2026-11-10 14", f"expected spike at 14:00, got {(spike, count)}"
    assert count >= 1.5 * runner_up, f"spike {count} not clearly above noise {runner_up}"
    print(f"OK  data: slowest={worst}, 5xx spike at {spike} ({count} errors, next hour {runner_up})")


def test_executor_runs_the_analysis():
    executor = LocalPythonExecutor(AUTHORIZED_IMPORTS)
    # CodeAgent wires tools into the sandbox the same way: tool objects by name,
    # including a FinalAnswerTool.
    executor.send_tools({"access_log": access_log, "final_answer": FinalAnswerTool()})
    out = executor(IMPORTS + AGENT_STYLE_CODE + ANSWER_CODE)

    assert out.is_final_answer
    assert "slowest=/api/export" in out.output
    assert "spike=2026-11-10 14" in out.output
    print(f"OK  executor: agent-style code evaluates -> {out.output}")


def test_sandbox_blocks_escapes():
    executor = LocalPythonExecutor(AUTHORIZED_IMPORTS)
    executor.send_tools({"final_answer": FinalAnswerTool()})

    expected = [
        ("import os", ESCAPE_OS, "Import of os is not allowed"),
        ("open()", ESCAPE_OPEN, "'open' is not among the explicitly allowed tools"),
    ]
    for label, code, reason in expected:
        try:
            executor(code)
        except InterpreterError as e:
            assert reason in str(e), str(e)
            print(f"OK  sandbox: {label} blocked ({reason})")
        else:
            raise AssertionError(f"{label} executed: sandbox did NOT block")


class ScriptedModel(Model):
    """Returns canned replies in order. Stands in for the LLM, nothing more."""

    def __init__(self, replies):
        super().__init__(model_id="scripted")
        self.replies = list(replies)
        self.calls = 0

    def generate(self, messages, stop_sequences=None, response_format=None,
                 tools_to_call_from=None, **kwargs):
        reply = self.replies[self.calls]
        self.calls += 1
        return ChatMessage(role="assistant", content=reply)


def test_codeagent_loop_with_scripted_model():
    def turn(thought, code):
        return f"Thought: {thought}\n<code>\n{code}\n</code>"

    model = ScriptedModel([
        # 1: tries something the sandbox forbids -> error must come back as feedback
        turn("peek at the filesystem", "import os\nprint(os.listdir('.'))"),
        # 2: recovers, uses the tool; variables persist into the next step
        turn("analyze the log", IMPORTS + AGENT_STYLE_CODE
             + "print(worst, spike_hour)"),
        # 3: reuses state from step 2 and answers
        turn("answer", ANSWER_CODE),
    ])
    agent = CodeAgent(
        tools=[access_log],
        model=model,
        additional_authorized_imports=AUTHORIZED_IMPORTS,
        max_steps=5,
        verbosity_level=0,
    )
    result = agent.run("which endpoint is slowest, and when did 5xx spike?")

    assert model.calls == 3, model.calls
    assert "slowest=/api/export" in str(result) and "spike=2026-11-10 14" in str(result)
    steps = [s for s in agent.memory.steps if type(s).__name__ == "ActionStep"]
    assert steps[0].error is not None and "os" in str(steps[0].error), steps[0].error
    assert "/api/export" in steps[1].observations
    print(f"OK  CodeAgent loop (scripted model): blocked step -> recovery -> state reuse -> {result}")


if __name__ == "__main__":
    gen()
    test_tool_contract()
    test_data_has_the_incident()
    test_executor_runs_the_analysis()
    test_sandbox_blocks_escapes()
    test_codeagent_loop_with_scripted_model()
    print("\nAll offline checks passed. No LLM was involved; "
          "set AGENT_MODEL (+ key) and run agent.py to exercise a real model.")
