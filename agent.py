"""The agent. Needs a real model — see README for the env vars.

    uv run python agent.py

The task: "Which endpoint is the slowest, and in which hour did errors spike?"
A CodeAgent answers this by writing and running its own Python over the rows
returned by the access_log() tool.
"""

import os

from smolagents import CodeAgent, LiteLLMModel

from tools import access_log

# The executor already allows a small default set (math, statistics, collections,
# datetime, re, itertools, ...). This task needs nothing beyond it, so nothing is
# added. Anything else (csv, json, pandas, ...) must be listed here explicitly.
AUTHORIZED_IMPORTS: list[str] = []

QUESTION = (
    "Analyze the API access log and answer two questions:\n"
    "1. Which endpoint has the worst latency? Give its median and p95 in ms.\n"
    "2. In which hour (bucket of the timestamp, e.g. '2026-11-10 14') did 5xx\n"
    "   errors spike, which endpoint caused it, and what status code dominated?\n"
    "Call access_log() first to get the rows. Round the numbers.\n"
    "Answer in at most 6 sentences."
)


def build_model() -> LiteLLMModel:
    model_id = os.environ.get("AGENT_MODEL", "openai/gpt-4o-mini")
    kwargs = {}
    if base := os.environ.get("AGENT_MODEL_BASE"):  # e.g. http://localhost:11434 for Ollama
        kwargs["api_base"] = base
    if model_id.startswith("ollama"):
        # Ollama's default context window (2048 tokens) is too small for an agent
        # loop; smolagents' own docs pass num_ctx=8192. Raise it for bigger models.
        kwargs["num_ctx"] = int(os.environ.get("AGENT_NUM_CTX", "8192"))
    return LiteLLMModel(model_id=model_id, **kwargs)


def main():
    agent = CodeAgent(
        tools=[access_log],
        model=build_model(),
        additional_authorized_imports=AUTHORIZED_IMPORTS,
        max_print_outputs_length=4000,
    )

    result = agent.run(QUESTION)
    print("\n=== ANSWER ===")
    print(result)


if __name__ == "__main__":
    main()
