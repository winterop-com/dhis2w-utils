"""Drive a cloud Claude model over the single-tool dhis2_cli bridge via the Agent SDK.

Cloud peer of `bench-bridge` + `bench-composite`: where those drive LOCAL models over the bridge with a
hand-rolled OpenAI loop, this hands the single `dhis2_cli` tool to a cloud Claude model and lets the
Claude Agent SDK drive its own loop. Three rounds, reusing the existing tasks + scoring so local and
cloud are directly comparable:

- read      (play42, bridge readonly): the shared read tasks.
- write     (local_basic): the single system-setting round-trip, then restore the baseline.
- composite (local_basic): the HARD multi-object authoring scenarios — the real local/cloud
  discriminator (local 4B models score 0/3 on the dataset; the strong locals only ~2/3).

Auth is AMBIENT — the logged-in Claude Code subscription. No API key is read, passed, or stored. Writes
target `local_basic` ONLY; the bridge's host-guard refuses writes to public hosts regardless of this
harness. Each task costs real subscription budget.

Usage:
    uv run python -m dhis2w_bench.claude_bridge                 # session-default model, all rounds
    uv run python -m dhis2w_bench.claude_bridge opus sonnet     # compare models
    uv run python -m dhis2w_bench.claude_bridge --runs 3        # repeat the flaky composite round
"""

from __future__ import annotations

import argparse
import asyncio
import json
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

from dhis2w_bench.bridge import READ_TASKS, REPO, WRITE_TASK, _normalize_args, _score_read, _used
from dhis2w_bench.composite import SCENARIOS, _cleanup_model, _verify_model, run_cli, run_cli_json

#: The SDK's discovery tool and the bridge's single tool (server key "dhis2"); only these are permitted.
_TOOL_SEARCH = "ToolSearch"
_BRIDGE_TOOL = "mcp__dhis2__dhis2_cli"
#: Per-round turn caps — composite authoring needs many steps; reads are quick.
_TURNS_READ = 10
_TURNS_WRITE = 14
_TURNS_COMPOSITE = 36
_WRITE_PROFILE = "local_basic"
_READ_PROFILE = "play42"


class TaskOutcome(BaseModel):
    """One task's result across any round (read / write / composite)."""

    model_config = ConfigDict(frozen=True)

    round: str
    key: str
    ok: bool
    turns: int
    cost_usd: float
    seconds: float
    detail: str = ""


class ModelReport(BaseModel):
    """A model's results over the bridge across all three rounds."""

    model_config = ConfigDict(frozen=True)

    model: str
    outcomes: list[TaskOutcome]

    @property
    def cost_usd(self) -> float:
        """Total subscription cost across every round."""
        return sum(outcome.cost_usd for outcome in self.outcomes)

    def passed(self, round_name: str) -> tuple[int, int]:
        """(passes, total) for one round."""
        items = [outcome for outcome in self.outcomes if outcome.round == round_name]
        return sum(1 for outcome in items if outcome.ok), len(items)


class _Run(BaseModel):
    """Raw capture of one agent run: the final answer plus the dhis2_cli arg-lists it issued."""

    model_config = ConfigDict(frozen=True)

    answer: str
    tool_args: list[list[str]]
    turns: int
    cost_usd: float
    seconds: float


async def _bridge_gate(
    tool_name: str, _input: dict[str, Any], _context: ToolPermissionContext
) -> PermissionResultAllow | PermissionResultDeny:
    """Permit only tool discovery and the single dhis2_cli tool; deny built-ins (fail-closed)."""
    if tool_name in (_TOOL_SEARCH, _BRIDGE_TOOL):
        return PermissionResultAllow()
    return PermissionResultDeny(message="bridge benchmark: only the dhis2_cli tool is permitted")


def _options(profile: str, readonly: str, model: str | None, max_turns: int) -> ClaudeAgentOptions:
    """Agent options spawning the dhis2_cli bridge for `profile` (readonly "1"/"0"), gated to that one tool."""
    return ClaudeAgentOptions(
        mcp_servers={
            "dhis2": {
                "type": "stdio",
                "command": "uv",
                "args": ["run", "--directory", REPO, "dhis2w-mcp-bridge"],
                # The SDK REPLACES the child env; merge os.environ or the bridge dies with "Stream closed".
                "env": {**os.environ, "DHIS2_PROFILE": profile, "DHIS2_MCP_READONLY": readonly},
            }
        },
        strict_mcp_config=True,
        setting_sources=[],
        can_use_tool=_bridge_gate,
        permission_mode="default",
        max_turns=max_turns,
        model=model,
        stderr=lambda _line: None,
    )


async def _drive(goal: str, profile: str, readonly: str, model: str | None, max_turns: int) -> _Run:
    """Run one goal through Claude + the bridge; capture answer, every dhis2_cli arg-list, turns, cost, time."""
    tool_args: list[list[str]] = []
    answer = ""
    turns = 0
    cost_usd = 0.0
    started = time.monotonic()
    async with ClaudeSDKClient(options=_options(profile, readonly, model, max_turns)) as client:
        await client.query(goal)
        async for message in client.receive_response():
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, ToolUseBlock) and block.name == _BRIDGE_TOOL:
                        tool_args.append(_normalize_args(block.input))
                    elif isinstance(block, TextBlock) and block.text.strip():
                        answer = block.text.strip()
            elif isinstance(message, ResultMessage):
                turns = message.num_turns
                cost_usd = message.total_cost_usd or 0.0
                if message.result:
                    answer = message.result
    return _Run(answer=answer, tool_args=tool_args, turns=turns, cost_usd=cost_usd, seconds=time.monotonic() - started)


def _baseline_min_password() -> int:
    """Read local_basic's current minPasswordLength so the write round can restore it; default 8 on any miss."""
    out = run_cli_json(_WRITE_PROFILE, ["security", "settings"])
    try:
        value = json.loads(out).get("minPasswordLength")
        return int(value) if value is not None else 8
    except (json.JSONDecodeError, AttributeError, TypeError, ValueError):
        return 8


async def _read_round(model: str | None) -> list[TaskOutcome]:
    """The shared read tasks against play42 with the bridge in readonly mode."""
    outcomes: list[TaskOutcome] = []
    for key, task in READ_TASKS:
        run = await _drive(task, _READ_PROFILE, "1", model, _TURNS_READ)
        ok = _score_read(key, run.answer, run.tool_args)
        outcomes.append(
            TaskOutcome(round="read", key=key, ok=ok, turns=run.turns, cost_usd=run.cost_usd, seconds=run.seconds)
        )
        print(f"  read {key}: {'PASS' if ok else 'FAIL'} {run.seconds:.1f}s ${run.cost_usd:.3f}")
    return outcomes


async def _write_round(model: str | None) -> TaskOutcome:
    """The single system-setting round-trip on local_basic, restoring the baseline afterwards."""
    baseline = _baseline_min_password()
    try:
        run = await _drive(WRITE_TASK, _WRITE_PROFILE, "0", model, _TURNS_WRITE)
        ok = _used(run.tool_args, ["system", "settings", "set"]) and "10" in run.answer
        print(f"  write minPasswordLength: {'PASS' if ok else 'FAIL'} {run.seconds:.1f}s ${run.cost_usd:.3f}")
        return TaskOutcome(
            round="write", key="minPasswordLength", ok=ok, turns=run.turns, cost_usd=run.cost_usd, seconds=run.seconds
        )
    finally:
        run_cli(_WRITE_PROFILE, ["system", "settings", "set", "minPasswordLength", str(baseline)])


async def _composite_round(model: str | None, runs: int) -> list[TaskOutcome]:
    """The hard multi-object authoring scenarios on local_basic, each run `runs` times, verified + cleaned up."""
    outcomes: list[TaskOutcome] = []
    for scenario in SCENARIOS:
        passes = 0
        for run_index in range(1, runs + 1):
            try:
                run = await _drive(scenario.goal, _WRITE_PROFILE, "0", model, _TURNS_COMPOSITE)
                ok, detail = _verify_model(_WRITE_PROFILE, scenario.key)
                cost, secs, turns = run.cost_usd, run.seconds, run.turns
            except Exception as exc:  # noqa: BLE001 — isolate one run so the sweep continues
                ok, detail, cost, secs, turns = False, f"errored ({type(exc).__name__}: {exc})", 0.0, 0.0, 0
            finally:
                _cleanup_model(_WRITE_PROFILE, scenario.key)
            passes += int(ok)
            outcomes.append(
                TaskOutcome(
                    round="composite",
                    key=f"{scenario.key}#{run_index}",
                    ok=ok,
                    turns=turns,
                    cost_usd=cost,
                    seconds=secs,
                    detail=detail,
                )
            )
            print(f"  composite {scenario.key} run {run_index}: {'PASS' if ok else 'FAIL'} — {detail} ${cost:.3f}")
        print(f"  == composite {scenario.key}: {passes}/{runs}")
    return outcomes


async def _benchmark_model(model: str | None, runs: int) -> ModelReport:
    """Run all three rounds against one Claude model over the bridge."""
    label = model or "session-default"
    print(f">>> {label}")
    outcomes = await _read_round(model)
    outcomes.append(await _write_round(model))
    outcomes.extend(await _composite_round(model, runs))
    return ModelReport(model=label, outcomes=outcomes)


def _markdown_table(reports: list[ModelReport], runs: int) -> str:
    """Render a model x round summary: read/write pass counts, per-scenario composite pass-rate, total cost."""
    scenarios = [scenario.key for scenario in SCENARIOS]
    header = "| model | read | write | " + " | ".join(scenarios) + " | cost |"
    divider = "| --- | --- | --- | " + " | ".join("---" for _ in scenarios) + " | --- |"
    lines = [header, divider]
    for report in reports:
        read_pass, read_total = report.passed("read")
        write_pass, write_total = report.passed("write")
        cells = []
        for scenario_key in scenarios:
            wins = sum(1 for o in report.outcomes if o.round == "composite" and o.key.startswith(scenario_key) and o.ok)
            cells.append(f"{wins}/{runs}")
        lines.append(
            f"| `{report.model}` | {read_pass}/{read_total} | {write_pass}/{write_total} | "
            + " | ".join(cells)
            + f" | ${report.cost_usd:.2f} |"
        )
    return "\n".join(lines)


async def _run(models: list[str | None], runs: int) -> None:
    """Benchmark each model across all rounds and print the comparison table."""
    reports = [await _benchmark_model(model, runs) for model in models]
    print("\n" + _markdown_table(reports, runs))


def main() -> None:
    """CLI entry: drive named Claude models (or the session default) over the bridge across all rounds."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("models", nargs="*", help="Model ids/aliases (e.g. opus sonnet); empty = session default.")
    parser.add_argument("--runs", type=int, default=1, help="Composite runs per scenario (it is flaky; default 1).")
    args = parser.parse_args()
    models: list[str | None] = list(args.models) if args.models else [None]
    asyncio.run(_run(models, max(1, args.runs)))


if __name__ == "__main__":
    main()
