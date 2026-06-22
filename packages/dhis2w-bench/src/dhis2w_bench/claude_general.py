"""Cloud Claude on the coding suite (python + cli + tooling) — the cloud peer of bench-general.

Reuses `bench-general`'s tasks, executors, and scoring verbatim; only the driver changes. The python and
cli suites are one-shot text generation (Claude writes code → the existing extract/exec/assert
machinery scores it). The tooling suite is multi-turn agentic: the mock toolbox is exposed to Claude as
an in-process SDK MCP server, Claude calls the tools, and the same full-transcript checker scores the
calls. Directly comparable to the local `bench-general` table.

Auth is AMBIENT — the logged-in Claude Code subscription. No API key is read or stored. Costs budget.

Usage:
    uv run python -m dhis2w_bench.claude_general                 # session-default model
    uv run python -m dhis2w_bench.claude_general opus sonnet     # compare models
"""

from __future__ import annotations

import argparse
import asyncio
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
    create_sdk_mcp_server,
    tool,
)
from pydantic import BaseModel, ConfigDict

from dhis2w_bench.general import (
    CLI_SYSTEM,
    CLI_TASKS,
    PY_SYSTEM,
    PYTHON_TASKS,
    TOOL_SCENARIOS,
    TOOL_SYSTEM,
    ModelReport,
    TaskResult,
    ToolCall,
    ToolDef,
    ToolScenario,
    _run_cli,
    _run_python,
)

#: Prefix the SDK gives in-process mock tools (server key "tools").
_TOOLS_PREFIX = "mcp__tools__"


async def _deny_all_gate(
    _tool_name: str, _input: dict[str, Any], _context: ToolPermissionContext
) -> PermissionResultAllow | PermissionResultDeny:
    """Code-gen rounds use no tools — Claude must write the answer, not run anything."""
    return PermissionResultDeny(message="code-gen round: no tools")


async def _mock_only_gate(
    tool_name: str, _input: dict[str, Any], _context: ToolPermissionContext
) -> PermissionResultAllow | PermissionResultDeny:
    """The tooling round permits only discovery + the scenario's mock tools; deny every built-in tool."""
    if tool_name == "ToolSearch" or tool_name.startswith(_TOOLS_PREFIX):
        return PermissionResultAllow()
    return PermissionResultDeny(message="tooling bench: only the scenario tools are permitted")


def _options(
    system: str, gate: Any, max_turns: int, model: str | None, mcp_servers: dict[str, Any]
) -> ClaudeAgentOptions:
    """Shared options: a fixed system prompt, isolation from local settings, a gate, ambient auth."""
    return ClaudeAgentOptions(
        system_prompt=system,
        mcp_servers=mcp_servers,
        setting_sources=[],
        can_use_tool=gate,
        permission_mode="default",
        max_turns=max_turns,
        model=model,
        stderr=lambda _line: None,
    )


async def _claude_text(system: str, prompt: str, model: str | None) -> tuple[str, float]:
    """One-shot text generation (no tools). Returns (answer, cost_usd)."""
    answer = ""
    cost = 0.0
    async with ClaudeSDKClient(options=_options(system, _deny_all_gate, 2, model, {})) as client:
        await client.query(prompt)
        async for message in client.receive_response():
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock) and block.text.strip():
                        answer = block.text
            elif isinstance(message, ResultMessage):
                cost = message.total_cost_usd or 0.0
                if message.result:
                    answer = message.result
    return (answer, cost)


def _sdk_tools(tool_defs: list[ToolDef]) -> list[Any]:
    """Wrap each mock ToolDef as an in-process SDK tool whose handler returns the canned result."""

    def _wrap(definition: ToolDef) -> Any:
        async def _handler(args: dict[str, Any]) -> dict[str, Any]:
            return {"content": [{"type": "text", "text": definition.handler(args)}]}

        return tool(definition.name, definition.description, definition.parameters)(_handler)

    return [_wrap(definition) for definition in tool_defs]


async def _claude_tooling(scenario: ToolScenario, model: str | None) -> tuple[list[ToolCall], float]:
    """Drive Claude over the scenario's mock tools (in-process SDK server); capture the calls + cost."""
    server = create_sdk_mcp_server("tools", tools=_sdk_tools(scenario.tools))
    options = _options(TOOL_SYSTEM, _mock_only_gate, scenario.max_steps + 3, model, {"tools": server})
    calls: list[ToolCall] = []
    cost = 0.0
    async with ClaudeSDKClient(options=options) as client:
        await client.query(scenario.goal)
        async for message in client.receive_response():
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, ToolUseBlock) and block.name.startswith(_TOOLS_PREFIX):
                        calls.append(ToolCall(name=block.name[len(_TOOLS_PREFIX) :], arguments=block.input))
            elif isinstance(message, ResultMessage):
                cost = message.total_cost_usd or 0.0
    return (calls, cost)


class _ModelRun(BaseModel):
    """A model's report plus its total subscription cost."""

    model_config = ConfigDict(frozen=True)

    report: ModelReport
    cost_usd: float


async def _run_python_suite(model: str | None) -> tuple[list[TaskResult], float]:
    """The python code-gen suite via one-shot Claude text."""
    results: list[TaskResult] = []
    cost = 0.0
    for task in PYTHON_TASKS:
        started = time.monotonic()
        text, task_cost = await _claude_text(PY_SYSTEM, task.prompt, model)
        passed, total = _run_python(text, task)
        cost += task_cost
        results.append(
            TaskResult(
                suite="python", key=task.key, passed=passed, total=total, seconds=time.monotonic() - started, tokens=0
            )
        )
        print(f"  python {task.key}: {passed}/{total}")
    return (results, cost)


async def _run_cli_suite(model: str | None) -> tuple[list[TaskResult], float]:
    """The cli command-gen suite via one-shot Claude text, scored in the sandbox."""
    results: list[TaskResult] = []
    cost = 0.0
    for task in CLI_TASKS:
        started = time.monotonic()
        text, task_cost = await _claude_text(CLI_SYSTEM, task.goal, model)
        passed, total = _run_cli(text, task)
        cost += task_cost
        results.append(
            TaskResult(
                suite="cli", key=task.key, passed=passed, total=total, seconds=time.monotonic() - started, tokens=0
            )
        )
        print(f"  cli {task.key}: {passed}/{total}")
    return (results, cost)


async def _run_tooling_suite(model: str | None) -> tuple[list[TaskResult], float]:
    """The multi-turn agentic tooling suite via Claude's in-process mock tools."""
    results: list[TaskResult] = []
    cost = 0.0
    for scenario in TOOL_SCENARIOS:
        started = time.monotonic()
        calls, scenario_cost = await _claude_tooling(scenario, model)
        ok = scenario.check(calls)
        cost += scenario_cost
        results.append(
            TaskResult(
                suite="tooling", key=scenario.key, passed=int(ok), total=1, seconds=time.monotonic() - started, tokens=0
            )
        )
        print(f"  tooling {scenario.key}: {'PASS' if ok else 'FAIL'}")
    return (results, cost)


async def _benchmark_model(model: str | None) -> _ModelRun:
    """Run all three coding suites against one Claude model."""
    label = model or "session-default"
    print(f">>> {label}")
    py_results, py_cost = await _run_python_suite(model)
    cli_results, cli_cost = await _run_cli_suite(model)
    tool_results, tool_cost = await _run_tooling_suite(model)
    report = ModelReport(model=label, results=[*py_results, *cli_results, *tool_results])
    return _ModelRun(report=report, cost_usd=py_cost + cli_cost + tool_cost)


def _markdown_table(runs: list[_ModelRun]) -> str:
    """Render a model x suite table (python / cli / tooling / total / cost)."""
    lines = ["| model | python | cli | tooling | total | cost |", "| --- | --- | --- | --- | --- | --- |"]
    for run in runs:
        report = run.report
        passed = sum(result.passed for result in report.results)
        total = sum(result.total for result in report.results)
        lines.append(
            f"| `{report.model}` | {report.suite_score('python')} | {report.suite_score('cli')} "
            f"| {report.suite_score('tooling')} | **{passed}/{total}** | ${run.cost_usd:.2f} |"
        )
    return "\n".join(lines)


async def _run(models: list[str | None]) -> None:
    """Benchmark each model across the three suites and print the comparison table."""
    runs = [await _benchmark_model(model) for model in models]
    print("\n" + _markdown_table(runs))


def main() -> None:
    """CLI entry: drive named Claude models (or the session default) over the coding suite."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("models", nargs="*", help="Model ids/aliases (e.g. opus sonnet); empty = session default.")
    args = parser.parse_args()
    models: list[str | None] = list(args.models) if args.models else [None]
    asyncio.run(_run(models))


if __name__ == "__main__":
    main()
