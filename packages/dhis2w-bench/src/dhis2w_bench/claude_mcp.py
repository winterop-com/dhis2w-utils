"""Drive a cloud Claude model over the full dhis2-mcp server via the Agent SDK — the cloud peer of bench-mcp.

Where `bench-mcp` benchmarks LOCAL models over a hand-rolled OpenAI tool loop, this hands the whole
dhis2-mcp tool surface to a cloud Claude model and lets the Claude Agent SDK drive its own loop: the SDK
spawns dhis2-mcp, Claude discovers and calls tools, and a read-only permission gate keeps the public
`play42` round safe. It reuses bench-mcp's read tasks and scoring so the two are comparable.

Auth is AMBIENT — the logged-in Claude Code subscription. No API key is read, passed, or stored; if you
are logged in (`claude setup-token` or `/login`), this works. Each task costs real subscription budget.

The read round only (against `play42`, the public demo) is in scope here: the read-only gate denies
any non-read tool, so nothing mutates. Writes would need local infra and are a follow-up.

Usage:
    uv run python -m dhis2w_bench.claude_mcp                 # session-default model, read suite on play42
    uv run python -m dhis2w_bench.claude_mcp opus sonnet     # compare named models
"""

from __future__ import annotations

import argparse
import asyncio
import os
import time
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    PermissionResultAllow,
    PermissionResultDeny,
    ResultMessage,
    TextBlock,
    ToolPermissionContext,
    ToolUseBlock,
)
from pydantic import BaseModel, ConfigDict

from dhis2w_bench.mcp import READ_TASKS, REPO, _is_read_tool, _score_read

#: Discovery tool the SDK exposes to find deferred MCP tools; harmless and needed, so always allowed.
_TOOL_SEARCH = "ToolSearch"
#: Prefix the SDK gives dhis2-mcp tools (server key "dhis2").
_MCP_PREFIX = "mcp__dhis2__"
#: Cap on agent turns per task so a confused run can't bill indefinitely.
_MAX_TURNS = 16
#: Read profile — the public demo. Writes are out of scope (the gate denies them).
_READ_PROFILE = "play42"


class TaskOutcome(BaseModel):
    """One read task's result driving Claude over the full MCP server."""

    model_config = ConfigDict(frozen=True)

    key: str
    ok: bool
    turns: int
    cost_usd: float
    seconds: float
    tools: list[str]


class ModelReport(BaseModel):
    """A model's read-suite results over the full dhis2-mcp server."""

    model_config = ConfigDict(frozen=True)

    model: str
    outcomes: list[TaskOutcome]

    @property
    def passed(self) -> int:
        """Count of read tasks the model got right."""
        return sum(1 for outcome in self.outcomes if outcome.ok)

    @property
    def cost_usd(self) -> float:
        """Total subscription cost across the suite."""
        return sum(outcome.cost_usd for outcome in self.outcomes)


class _Run(BaseModel):
    """Raw capture of one agent run (answer + the metadata the table reports)."""

    model_config = ConfigDict(frozen=True)

    answer: str
    tool_names: list[str]
    turns: int
    cost_usd: float
    seconds: float


async def _read_only_gate(
    tool_name: str, _input: dict[str, Any], _context: ToolPermissionContext
) -> PermissionResultAllow | PermissionResultDeny:
    """Allow tool discovery and read-verb dhis2 tools only; deny writes and every built-in tool (fail-closed)."""
    if tool_name == _TOOL_SEARCH:
        return PermissionResultAllow()
    if tool_name.startswith(_MCP_PREFIX) and _is_read_tool(tool_name[len(_MCP_PREFIX) :]):
        return PermissionResultAllow()
    return PermissionResultDeny(message="read-only benchmark: only dhis2 read tools are permitted")


def _options(model: str | None) -> ClaudeAgentOptions:
    """Agent options: spawn dhis2-mcp on the read profile, gate to read-only, isolate from local settings."""
    return ClaudeAgentOptions(
        mcp_servers={
            "dhis2": {
                "type": "stdio",
                "command": "uv",
                "args": ["run", "--directory", REPO, "dhis2w-mcp"],
                # The SDK REPLACES the child env, so merge os.environ or the server dies with "Stream closed".
                "env": {**os.environ, "DHIS2_PROFILE": _READ_PROFILE},
            }
        },
        strict_mcp_config=True,
        setting_sources=[],
        can_use_tool=_read_only_gate,
        permission_mode="default",
        max_turns=_MAX_TURNS,
        model=model,
        stderr=lambda _line: None,
    )


async def _drive(goal: str, model: str | None) -> _Run:
    """Run one goal through Claude + the full MCP server; capture answer, tool names, turns, cost, time."""
    tool_names: list[str] = []
    answer = ""
    turns = 0
    cost_usd = 0.0
    started = time.monotonic()
    async with ClaudeSDKClient(options=_options(model)) as client:
        await client.query(goal)
        async for message in client.receive_response():
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, ToolUseBlock):
                        tool_names.append(block.name)
                    elif isinstance(block, TextBlock) and block.text.strip():
                        answer = block.text.strip()
            elif isinstance(message, ResultMessage):
                turns = message.num_turns
                cost_usd = message.total_cost_usd or 0.0
                if message.result:
                    answer = message.result
    elapsed = time.monotonic() - started
    return _Run(answer=answer, tool_names=tool_names, turns=turns, cost_usd=cost_usd, seconds=elapsed)


async def _benchmark_model(model: str | None) -> ModelReport:
    """Run the shared read suite against one Claude model over the full MCP server."""
    label = model or "session-default"
    print(f">>> {label}")
    outcomes: list[TaskOutcome] = []
    for key, goal in READ_TASKS:
        run = await _drive(goal, model)
        ok = _score_read(key, run.answer)
        outcomes.append(
            TaskOutcome(
                key=key, ok=ok, turns=run.turns, cost_usd=run.cost_usd, seconds=run.seconds, tools=run.tool_names
            )
        )
        print(f"  {key}: {'PASS' if ok else 'FAIL'} {run.seconds:.1f}s ${run.cost_usd:.3f} ({run.turns} turns)")
    return ModelReport(model=label, outcomes=outcomes)


def _markdown_table(reports: list[ModelReport]) -> str:
    """Render a model x read-task table with totals for passes and cost."""
    keys = [key for key, _ in READ_TASKS]
    header = "| model | " + " | ".join(keys) + " | passed | cost |"
    divider = "| --- | " + " | ".join("---" for _ in keys) + " | --- | --- |"
    lines = [header, divider]
    for report in reports:
        by_key = {outcome.key: outcome for outcome in report.outcomes}
        cells = ["PASS" if by_key[key].ok else "FAIL" for key in keys]
        lines.append(
            f"| `{report.model}` | " + " | ".join(cells) + f" | {report.passed}/{len(keys)} | ${report.cost_usd:.3f} |"
        )
    return "\n".join(lines)


async def _run(models: list[str | None]) -> None:
    """Benchmark each model over the read suite and print the comparison table."""
    reports = [await _benchmark_model(model) for model in models]
    print("\n" + _markdown_table(reports))


def main() -> None:
    """CLI entry: drive named Claude models (or the session default) over the full dhis2-mcp read suite."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("models", nargs="*", help="Model ids/aliases (e.g. opus sonnet); empty = session default.")
    args = parser.parse_args()
    models: list[str | None] = list(args.models) if args.models else [None]
    asyncio.run(_run(models))


if __name__ == "__main__":
    main()
