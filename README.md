# smolagents tutorial: a CodeAgent that reads your access logs

Companion code for **[smolagents: Agents That Write Python Instead of JSON](https://codewithkyryl.dev/2026/11/15/smolagents-code-agents/)** on codewithkyryl.dev.

The task: give an agent two days of API access logs and ask
*"which endpoint is the slowest, and in which hour did 5xx errors spike?"*
A `CodeAgent` answers by writing and running its own Python, with no JSON
tool-call choreography. Python 3.11+, smolagents 1.26.

## Quickstart

```bash
uv sync                        # smolagents + the litellm extra (LiteLLMModel needs it)
uv run python offline_check.py # everything below, no model, no network, no keys
```

To run the real agent you need any LiteLLM-supported model:

```bash
export AGENT_MODEL=openai/gpt-4o-mini        # or anthropic/claude-..., ollama_chat/qwen2.5-coder, ...
export OPENAI_API_KEY=sk-...                 # (or the matching provider key)
# local model instead of a cloud one:
#   export AGENT_MODEL=ollama_chat/qwen2.5-coder:7b
#   export AGENT_MODEL_BASE=http://localhost:11434
#   export AGENT_NUM_CTX=8192                # optional, this is the default

uv run python agent.py
```

For `ollama*` model ids `agent.py` passes `num_ctx` (default 8192) to
`LiteLLMModel`: Ollama's default context window of 2048 tokens is too small for an
agent loop (smolagents' own docs say so and use 8192).

## Status of this code

`agent.py` has **not been run against a real LLM** by the author of this repo
(no API key or local model was available when it was written). Everything
below that runs offline is verified; the quality of the code a given model
writes for this task is not.

The log file is synthetic (`data/access_log.csv`, 4,000 rows, seeded). The story
in it: `/api/export` is persistently slow, and `/api/reports` has a 503 retry
storm from 14:00 to 15:00 on day one. `uv run python gen_logs.py` regenerates it.

## What runs offline (`offline_check.py`)

- the `@tool` contract (docstring + type hints) builds correctly;
- the planted incident is in the data, with a margin over background noise
  (the task is solvable);
- `LocalPythonExecutor`, the interpreter `CodeAgent` uses, evaluates a
  hand-written version of the analysis against the real tool object;
- the sandbox blocks `import os` and `open()` with `InterpreterError`, and the
  test asserts the exact reasons;
- the real `CodeAgent` loop runs end to end against a **scripted model** that
  returns canned code: a blocked step whose error is fed back, a recovery step
  that calls the tool, and a final step that reuses variables from the previous
  one. This verifies smolagents' plumbing and this repo's wiring, not any LLM.

Design note in `tools.py`: the tool returns parsed rows as a `list[dict]`, not a
file path. The local executor blocks `open()`, so data reaches the agent through
tool return values, which enter the sandbox as real Python objects.

`LocalPythonExecutor` is **not a security boundary** (the smolagents README says
so). For untrusted input use a remote executor (`executor_type="docker"`,
`"e2b"`, `"modal"` or `"blaxel"`).

## Files

```
agent.py         the CodeAgent (needs a model)
tools.py         the one @tool: access_log() -> list[dict]
gen_logs.py      deterministic synthetic log generator (seed 42)
offline_check.py offline verification: tool, data, executor, sandbox, scripted agent loop
data/            generated access_log.csv
```

## License

MIT
