"""Benchmark local models driving the full dhis2 surface through the ROUTER (search + dispatch).

The router exposes only two tools — `search_tools` + `call_tool` — so a small local model can drive the
full ~311-tool surface at a TINY context (default 16k), versus the ~49k-token full-MCP payload that
overflows small models. This is the local-model peer of `bench-mcp`: it measures whether the router gives
small models the lazy discovery cloud agents get from ToolSearch. The read round runs on `play42` with
the router in read-only mode, and reuses `bench-mcp`'s read tasks + scoring so the numbers are
directly comparable to the full-server and bridge lanes.

Usage:
    uv run python -m dhis2w_bench.router google/gemma-4-26b-a4b-qat
    BENCH_CONTEXT=8192 uv run python -m dhis2w_bench.router <model> ...
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time

import httpx
from dhis2w_mcp_router.core import Registry, UpstreamServer
from pydantic import BaseModel, ConfigDict

from dhis2w_bench.backend import get_backend
from dhis2w_bench.mcp import READ_TASKS, REPO, _score_read

BACKEND = get_backend()
LM = BACKEND.chat_url
#: Load context for the model (env `BENCH_CONTEXT`). Small on purpose — the router payload is 2 tools.
CONTEXT = int(os.environ.get("BENCH_CONTEXT") or 16384)
_READ_PROFILE = "play42"
_SYSTEM = (
    "You are a DHIS2 operator with two tools: search_tools (find a tool by keyword) and call_tool (run "
    "a tool by its exact name from search). To answer, first search_tools, then call_tool with the "
    "exact namespaced name it returns."
)

_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_tools",
            "description": "Search the DHIS2 tools by keyword; returns matching tool names + descriptions. Call FIRST.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}, "limit": {"type": "integer"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "call_tool",
            "description": "Call a DHIS2 tool by its exact namespaced name (from search_tools) with its arguments.",
            "parameters": {
                "type": "object",
                "properties": {"name": {"type": "string"}, "arguments": {"type": "object"}},
                "required": ["name", "arguments"],
            },
        },
    },
]


class TaskOutcome(BaseModel):
    """One read task driven through the router."""

    model_config = ConfigDict(frozen=True)

    key: str
    ok: bool
    turns: int
    seconds: float


class ModelReport(BaseModel):
    """A model's router read-suite results at a given load context."""

    model_config = ConfigDict(frozen=True)

    model: str
    context: int
    outcomes: list[TaskOutcome]

    @property
    def passed(self) -> int:
        """Read tasks the model got right via the router."""
        return sum(1 for outcome in self.outcomes if outcome.ok)


def _make_registry() -> Registry:
    """A read-only router fronting the full dhis2-mcp server on the public read profile."""
    server = UpstreamServer(
        name="dhis2",
        command="uv",
        args=["run", "--directory", REPO, "dhis2w-mcp"],
        env={"DHIS2_PROFILE": _READ_PROFILE},
        readonly=True,
    )
    return Registry([server], readonly=True)


async def _dispatch(registry: Registry, name: str, arguments: dict) -> str:
    """Run one router meta-tool: search_tools returns matches; call_tool dispatches to the upstream."""
    if name == "search_tools":
        hits = await registry.search(arguments.get("query", ""), arguments.get("limit", 5))
        return json.dumps([{"name": hit.name, "description": hit.description} for hit in hits])
    if name == "call_tool":
        try:
            return await registry.call(arguments.get("name", ""), arguments.get("arguments", {}))
        except Exception as exc:  # noqa: BLE001 — surface any upstream/tool error to the model as feedback, don't crash
            return f"error: {exc}"
    return f"unknown meta-tool {name!r}"


async def _agent(
    http: httpx.AsyncClient, model: str, registry: Registry, goal: str, max_steps: int = 8
) -> tuple[str, int]:
    """Drive `model` over the router's two tools toward `goal`; return (answer, turns)."""
    messages: list[dict] = [{"role": "system", "content": _SYSTEM}, {"role": "user", "content": goal}]
    for step in range(1, max_steps + 1):
        body = {"model": model, "messages": messages, "tools": _TOOLS, "temperature": 0.2}
        resp = await http.post(LM, json=body, timeout=300.0)
        message = resp.json()["choices"][0]["message"]
        calls = message.get("tool_calls") or []
        if not calls:
            return ((message.get("content") or "").strip(), step)
        messages.append({"role": "assistant", "content": message.get("content"), "tool_calls": calls})
        for call in calls:
            name = call["function"]["name"]
            arguments = json.loads(call["function"]["arguments"] or "{}")
            result = await _dispatch(registry, name, arguments)
            messages.append({"role": "tool", "tool_call_id": call.get("id", name), "content": result[:4000]})
    return ("", max_steps)


async def _benchmark_model(model: str) -> ModelReport:
    """Load `model` at the small router context, then run the shared read suite through the router."""
    print(f">>> {model} (loaded at {CONTEXT // 1024}K context — router payload is 2 tools)")
    BACKEND.load(model, CONTEXT)
    registry = _make_registry()
    await registry.ensure_built()
    print(f"  router fronts {registry.tool_count()} tools")
    outcomes: list[TaskOutcome] = []
    async with httpx.AsyncClient() as http:
        for key, goal in READ_TASKS:
            started = time.monotonic()
            answer, turns = await _agent(http, model, registry, goal)
            ok = _score_read(key, answer)
            outcomes.append(TaskOutcome(key=key, ok=ok, turns=turns, seconds=time.monotonic() - started))
            print(f"  {key}: {'PASS' if ok else 'FAIL'} {outcomes[-1].seconds:.1f}s ({turns} turns)")
    await registry.aclose()
    return ModelReport(model=model, context=CONTEXT, outcomes=outcomes)


def _markdown_table(reports: list[ModelReport]) -> str:
    """Render a model x read-task table with the load context (the headline: small context works)."""
    keys = [key for key, _ in READ_TASKS]
    header = "| model | context | " + " | ".join(keys) + " | passed |"
    divider = "| --- | --- | " + " | ".join("---" for _ in keys) + " | --- |"
    lines = [header, divider]
    for report in reports:
        by_key = {outcome.key: outcome for outcome in report.outcomes}
        cells = ["PASS" if by_key[key].ok else "FAIL" for key in keys]
        row = f"| `{report.model}` | {report.context // 1024}K | " + " | ".join(cells)
        lines.append(row + f" | {report.passed}/{len(keys)} |")
    return "\n".join(lines)


async def _run(models: list[str]) -> None:
    """Benchmark each model over the router read suite and print the table."""
    reports = [await _benchmark_model(model) for model in models]
    BACKEND.unload_all()
    print("\n" + _markdown_table(reports))


def main() -> None:
    """CLI entry: drive named local models over the router's two tools (read suite, play42)."""
    models = sys.argv[1:]
    if not models:
        installed = "\n  ".join(BACKEND.list_installed()) or "(none found)"
        print("usage: python -m dhis2w_bench.router <model-key> ...\ninstalled:\n  " + installed, file=sys.stderr)
        sys.exit(2)
    asyncio.run(_run(models))


if __name__ == "__main__":
    main()
