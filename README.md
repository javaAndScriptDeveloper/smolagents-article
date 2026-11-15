# smolagents tutorial: a CodeAgent that reads your access logs

Companion code for **[smolagents, Explained for Backend Engineers](https://codewithkyryl.dev/2026/11/15/smolagents-code-agents/)** on codewithkyryl.dev.

The task: give an agent two days of API access logs and ask
*"which endpoint is the slowest, and in which hour did 5xx errors spike?"*
A `CodeAgent` answers by writing and running its own Python — no JSON tool-call
choreography. Python 3.11+.

## Quickstart

```bash
uv sync                        # installs smolagents (nothing else)
uv run python offline_check.py # everything below, no model, no network, no keys
```

To run the real agent you need any LiteLLM-supported model:

```bash
export AGENT_MODEL=openai/gpt-4o-mini        # or anthropic/claude-..., ollama_chat/qwen2.5-coder, ...
export OPENAI_API_KEY=sk-...                 # (or the matching provider key)
# local model instead of a cloud one:
#   export AGENT_MODEL=ollama_chat/qwen2.5-coder:7b
#   export AGENT_MODEL_BASE=http://localhost:11434

uv run python agent.py
```

The log file is synthetic (`data/access_log.csv`, 4,000 rows, seeded). The story
in it: `/api/export` is persistently slow, and `/api/reports` has a 503 retry
storm from 14:00 to 15:00 on day one. `uv run python gen_logs.py` regenerates it.

## What is real and what runs offline

- `agent.py` is the real thing: `CodeAgent` + `LiteLLMModel`, one custom `@tool`,
  `additional_authorized_imports` pinned to stdlib. Needs a model key.
- `offline_check.py` runs **without any model** and verifies the parts a model
  is not needed for:
  - the `@tool` contract (docstring + type hints) builds correctly;
  - the planted incident is actually in the data (the task is solvable);
  - `LocalPythonExecutor` — the same sandbox `CodeAgent` uses — evaluates a
    hand-written version of the analysis the agent should produce, calling the
    tool the way the agent would, and returns the expected answer;
  - the sandbox blocks `import os` and `open()` with `InterpreterError`.
- One design note baked into `tools.py`: the tool returns the parsed rows as a
  `list[dict]`, not a file path. The local executor blocks `open()` by design,
  so data reaches the agent through tool return values, passed into the sandbox
  as real Python objects.

## Files

```
agent.py         the CodeAgent (needs a model)
tools.py         the one @tool: access_log() -> list[dict]
gen_logs.py      deterministic synthetic log generator (seed 42)
offline_check.py offline verification: tool, data, executor, sandbox
data/            generated access_log.csv
```

## License

MIT
