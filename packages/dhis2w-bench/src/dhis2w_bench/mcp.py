"""Benchmark named local models driving the FULL dhis2-mcp server (all ~337 typed tools): read + write.

The third benchmark axis (alongside `bench_general_models.py` = coding, `bench_bridge_models.py` =
single-tool bridge). Here the model is handed the entire dhis2-mcp tool surface (every plugin tool,
~50-65k tokens of schema) and must pick the right one — the hard case the bridge avoids by exposing a
single tool. Expect local models to struggle; that result is the point (it validates the bridge).

SAFETY: the full server has NO readonly mode, and its typed write tools do NOT pass through the
bridge's host-guard. So the READ round (against `play42`, the public demo) is given ONLY read-verb
tools — a write tool is never even offered, so the model cannot mutate the public instance. The WRITE
round runs against `local_basic` (a throwaway local stack) and is best-effort self-restoring.

There is no hardcoded roster — name the model(s) explicitly. Set `BENCH_CHAMPION=<key>` for the oracle
SUSPECT-task check. Prereqs: a backend running; `local_basic` up (`make dhis2-run`) for the write round.

Usage:
    uv run python infra/scripts/bench_mcp_models.py google/gemma-4-26b-a4b-qat
    BENCH_CHAMPION=<key> uv run python infra/scripts/bench_mcp_models.py <model> ...
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from collections.abc import Sequence
from pathlib import Path

import httpx
from fastmcp import Client
from pydantic import BaseModel, ConfigDict, Field

from dhis2w_bench.backend import get_backend

#: Optional oracle model key (env `BENCH_CHAMPION`); unset -> no oracle check. No hardcoded roster.
CHAMPION = os.environ.get("BENCH_CHAMPION", "").strip()

BACKEND = get_backend()
LM = BACKEND.chat_url
REPO = str(Path(__file__).resolve().parents[4])
RESULTS = "/tmp/bench_mcp_results.jsonl"


def _env_int(name: str, default: int) -> int:
    """Read a positive int from env `name`; fall back to `default` when unset or invalid."""
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


#: Context length to load each model at (env `BENCH_CONTEXT`). The full tool payload is ~49k tokens,
#: so the default is generous (128k); lower it to test a model under tighter context, or to fit a
#: model that can't hold 128k in memory. Loading at 8192 (LM Studio's default) cannot fit the tools.
MCP_CONTEXT = _env_int("BENCH_CONTEXT", 131072)
SYSTEM_PROMPT = (
    "You are a DHIS2 operator with many typed tools. Pick the single right tool for the task and call "
    "it with concrete arguments. Always use a tool to get real data; never answer from memory. When "
    "you have the answer, reply in plain text with no further tool calls."
)
READ_TASKS: tuple[tuple[str, str], ...] = (
    ("count", "How many data elements are there? Give just the number."),
    ("filter", "List indicators whose name contains 'ANC' (names only)."),
    ("whoami", "Who am I logged in as? Give my username."),
)
WRITE_TASK = (
    "Set the system setting minPasswordLength to 10, then read it back and confirm it is now 10. "
    "Use the appropriate system-settings tools."
)

#: Read-verb suffixes — a tool is treated as read-only (safe for the play42 round) only when its name
#: ends in one of these. Fail-closed: anything else is assumed to mutate and is withheld from reads.
_READ_VERBS = frozenset(
    {
        "get", "list", "ls", "count", "find", "search", "show", "info", "whoami", "me", "tree",
        "members", "query", "namespaces", "keys", "usage", "diff", "verify", "status", "result",
        "list-keys", "authority-list", "outstanding",
    }
)  # fmt: skip


def _is_read_tool(name: str) -> bool:
    """Return True when a tool name's verb is a known read (safe to offer on the public read round)."""
    return name.rsplit("_", 1)[-1] in _READ_VERBS


# --- response parsing (OpenAI chat) ---------------------------------------------------------


class _ToolCallFunction(BaseModel):
    """The `function` block of a tool call."""

    model_config = ConfigDict(extra="ignore")

    name: str = ""
    arguments: str = "{}"


class _ToolCall(BaseModel):
    """One tool call (id + type retained so it can be echoed back)."""

    model_config = ConfigDict(extra="ignore")

    id: str = ""
    type: str = "function"
    function: _ToolCallFunction = Field(default_factory=_ToolCallFunction)


class _Message(BaseModel):
    """The assistant message of a chat choice."""

    model_config = ConfigDict(extra="ignore")

    content: str | None = None
    tool_calls: list[_ToolCall] = Field(default_factory=list)


class _Choice(BaseModel):
    """One chat-completion choice."""

    model_config = ConfigDict(extra="ignore")

    message: _Message


class _Usage(BaseModel):
    """Token usage for a completion."""

    model_config = ConfigDict(extra="ignore")

    completion_tokens: int = 0


class _ChatResponse(BaseModel):
    """The chat-completions response, narrowed to fields this harness reads."""

    model_config = ConfigDict(extra="ignore")

    choices: list[_Choice]
    usage: _Usage = Field(default_factory=_Usage)


# --- results --------------------------------------------------------------------------------


class TaskOutcome(BaseModel):
    """Scored outcome of one task: pass/fail, tool-call count, wall-clock, tokens."""

    model_config = ConfigDict(frozen=True)

    key: str
    ok: bool
    calls: int
    secs: float
    tokens: int


class ModelReport(BaseModel):
    """A model's full benchmark line: read outcomes + the write outcome, plus the tool count offered."""

    model_config = ConfigDict(frozen=True)

    model: str
    read: list[TaskOutcome]
    write: TaskOutcome
    found_write_tool: bool
    tools_offered: int

    @property
    def all_passed(self) -> bool:
        """True when every read task and the write task passed (the oracle bar)."""
        return all(outcome.ok for outcome in self.read) and self.write.ok


class _Run(BaseModel):
    """Raw result of one agent task: counts, timing, final answer, and the tool names it called."""

    model_config = ConfigDict(frozen=True)

    calls: int
    secs: float
    tokens: int
    answer: str
    tool_names: list[str]


# --- server client + agent loop -------------------------------------------------------------


def _mcp_config(profile: str) -> dict[str, object]:
    """FastMCP client config spawning the FULL dhis2-mcp server for `profile`."""
    return {
        "mcpServers": {
            "dhis2": {
                "command": "uv",
                "args": ["run", "--directory", REPO, "dhis2w-mcp"],
                "env": {"DHIS2_PROFILE": profile},
            }
        }
    }


def _tools(mcp_tools: Sequence[object], *, reads_only: bool) -> list[dict[str, object]]:
    """Convert FastMCP tools to OpenAI specs; with `reads_only`, withhold every non-read-verb tool."""
    specs: list[dict[str, object]] = []
    for tool in mcp_tools:
        name = str(getattr(tool, "name", ""))
        if not name or (reads_only and not _is_read_tool(name)):
            continue
        specs.append(
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": (getattr(tool, "description", "") or "")[:4000],
                    "parameters": getattr(tool, "inputSchema", {}),
                },
            }
        )
    return specs


def _result_text(result: object) -> str:
    """Serialize an MCP tool result to text the model can read (typed `.data`, else `.content`)."""
    data = getattr(result, "data", None)
    if data is not None:
        dump = getattr(data, "model_dump_json", None)
        if callable(dump):
            return str(dump())[:8000]
        try:
            return json.dumps(data, default=str)[:8000]
        except (TypeError, ValueError):
            return str(data)[:8000]
    return str(getattr(result, "content", ""))[:8000]


async def _agent(
    client: Client, http: httpx.AsyncClient, tools: list[dict[str, object]], model: str, task: str, max_steps: int
) -> _Run:
    """Run one task through the model + full MCP server; capture calls, timing, tokens, tool names."""
    messages: list[dict[str, object]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": task},
    ]
    calls = 0
    tokens = 0
    names: list[str] = []
    started = time.monotonic()
    for _ in range(max_steps):
        body = {"model": model, "messages": messages, "tools": tools, "temperature": 0.2}
        try:
            resp = await http.post(LM, json=body, timeout=300.0)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            return _Run(
                calls=calls, secs=round(time.monotonic() - started, 1), tokens=tokens,
                answer=f"[API error: {type(exc).__name__}]", tool_names=names,
            )  # fmt: skip
        parsed = _ChatResponse.model_validate(resp.json())
        tokens += parsed.usage.completion_tokens
        message = parsed.choices[0].message
        if not message.tool_calls:
            return _Run(
                calls=calls, secs=round(time.monotonic() - started, 1), tokens=tokens,
                answer=(message.content or "").strip(), tool_names=names,
            )  # fmt: skip
        messages.append(
            {
                "role": "assistant",
                "content": message.content or "",
                "tool_calls": [tc.model_dump() for tc in message.tool_calls],
            }
        )
        for call in message.tool_calls:
            calls += 1
            name = call.function.name
            names.append(name)
            try:
                arguments = json.loads(call.function.arguments or "{}")
            except json.JSONDecodeError:
                arguments = {}
            if not isinstance(arguments, dict):
                arguments = {}
            try:
                text = _result_text(await client.call_tool(name, arguments))
            except Exception as exc:  # noqa: BLE001 — a bad tool call shouldn't abort the round
                text = f"ERROR: tool {name} failed ({type(exc).__name__}: {exc})"
            messages.append({"role": "tool", "tool_call_id": call.id or name, "content": text[:8000]})
    return _Run(
        calls=calls, secs=round(time.monotonic() - started, 1), tokens=tokens,
        answer="[no final answer within step budget]", tool_names=names,
    )  # fmt: skip


# --- scoring --------------------------------------------------------------------------------


def _score_read(key: str, run: _Run) -> bool:
    """Heuristic pass/fail for a read task (same play42 expectations as the bridge bench)."""
    answer = run.answer.lower()
    if key == "count":
        return "1037" in answer
    if key == "filter":
        return "anc" in answer
    return "admin" in answer  # whoami


def _found_write(run: _Run) -> bool:
    """True if the model called a system-settings write tool."""
    return any("settings_set" in name or name.endswith("_set") for name in run.tool_names)


# --- benchmark one model --------------------------------------------------------------------


async def _benchmark_model(model: str) -> ModelReport:
    """Read round (play42, read-tools-only) then write round-trip (local_basic, best-effort restore)."""
    read_outcomes: list[TaskOutcome] = []
    tools_offered = 0
    async with Client(_mcp_config("play42")) as client:
        read_tools = _tools(await client.list_tools(), reads_only=True)
        tools_offered = len(read_tools)
        print(f"  (offering {tools_offered} read-only tools on play42)")
        async with httpx.AsyncClient() as http:
            for key, task in READ_TASKS:
                run = await _agent(client, http, read_tools, model, task, max_steps=8)
                ok = _score_read(key, run)
                read_outcomes.append(TaskOutcome(key=key, ok=ok, calls=run.calls, secs=run.secs, tokens=run.tokens))
                print(f"  READ {key}: ok={ok} calls={run.calls} {run.secs}s {run.tokens}tok")

    async with Client(_mcp_config("local_basic")) as client:
        all_tools = _tools(await client.list_tools(), reads_only=False)
        async with httpx.AsyncClient() as http:
            run = await _agent(client, http, all_tools, model, WRITE_TASK, max_steps=10)
        found = _found_write(run)
        write = TaskOutcome(
            key="write", ok=found and "10" in run.answer, calls=run.calls, secs=run.secs, tokens=run.tokens
        )
        print(f"  WRITE: ok={write.ok} found_tool={found} calls={run.calls} {run.secs}s")

    return ModelReport(
        model=model, read=read_outcomes, write=write, found_write_tool=_found_write(run), tools_offered=tools_offered
    )


# --- orchestration --------------------------------------------------------------------------


def _markdown_table(reports: list[ModelReport]) -> str:
    """Render the roster results as a Markdown table."""
    lines = [
        "| model | count | filter | whoami | write | tools | read tok/s |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for report in reports:
        by_key = {outcome.key: outcome for outcome in report.read}
        total_tokens = sum(outcome.tokens for outcome in report.read)
        total_secs = sum(outcome.secs for outcome in report.read) or 1.0

        def cell(outcome: TaskOutcome) -> str:
            return f"{'PASS' if outcome.ok else 'FAIL'} {outcome.secs}s"

        write_note = "PASS" if report.write.ok else ("found-tool, no-confirm" if report.found_write_tool else "no-tool")
        lines.append(
            f"| `{report.model}` | {cell(by_key['count'])} | {cell(by_key['filter'])} | {cell(by_key['whoami'])} "
            f"| {write_note} {report.write.secs}s | {report.tools_offered} | ~{round(total_tokens / total_secs)} |"
        )
    return "\n".join(lines)


async def _local_infra_reachable() -> bool:
    """Return True if local_basic answers a cheap read (whoami) — the write round needs it up."""
    async with Client(_mcp_config("local_basic")) as client:
        try:
            await client.call_tool("system_whoami", {})
        except Exception:  # noqa: BLE001 — any failure means treat infra as unreachable
            return False
    return True


def _installed_models(requested: list[str]) -> list[str]:
    """Filter `requested` to installed models; log (don't fail on) the rest."""
    installed = set(BACKEND.list_installed())
    if not installed:
        return requested
    models: list[str] = []
    for model in requested:
        if model in installed:
            models.append(model)
        else:
            print(f"!!! skip {model}: not installed")
    return models


def _check_oracle(reports: list[ModelReport]) -> None:
    """If an oracle (`BENCH_CHAMPION`) is set and ran, assert it passed; a failure flags a suspect task."""
    if not CHAMPION:
        return
    champion = next((report for report in reports if report.model == CHAMPION), None)
    if champion is None:
        return
    if champion.all_passed:
        print(f"\nOracle OK: {CHAMPION} passed every task.")
        return
    failed = [outcome.key for outcome in champion.read if not outcome.ok] + ([] if champion.write.ok else ["write"])
    print(
        f"\n!!! SUSPECT TASK(S): oracle {CHAMPION} FAILED {failed}. Fix the task(s) before trusting the "
        "weaker-model columns; an oracle failure usually means the task is mis-specified, not the model."
    )


def _require_models() -> list[str]:
    """Return model keys from argv; exit with the installed list when none given."""
    requested = sys.argv[1:]
    if not requested:
        installed = "\n  ".join(BACKEND.list_installed()) or "(none found)"
        print(
            "usage: bench_mcp_models.py <model-key> ...\nno model defaults. Installed:\n  " + installed, file=sys.stderr
        )
        sys.exit(2)
    return requested


async def main() -> None:
    """Benchmark the models named on the command line against the full MCP server; print the table."""
    models = _installed_models(_require_models())
    if not models:
        print("none of the requested models are installed", file=sys.stderr)
        return
    if not await _local_infra_reachable():
        print("!!! local_basic is unreachable — the write round needs it up. Run: make dhis2-run", file=sys.stderr)
        sys.exit(1)

    reports: list[ModelReport] = []
    failures: list[str] = []
    for model in models:
        print(f">>> {model} (loading at {MCP_CONTEXT // 1024}K context)")
        BACKEND.load(model, MCP_CONTEXT)
        try:
            report = await _benchmark_model(model)
        except Exception as exc:  # noqa: BLE001 — isolate one model's failure so the run continues
            print(f"!!! {model} FAILED ({type(exc).__name__}: {exc}); skipping")
            failures.append(model)
            continue
        reports.append(report)
        with open(RESULTS, "a") as handle:
            handle.write(report.model_dump_json() + "\n")

    if reports:
        print("\n" + _markdown_table(reports))
    _check_oracle(reports)
    if failures:
        print(f"\n{len(failures)} model(s) failed and were skipped: {', '.join(failures)}")


if __name__ == "__main__":
    asyncio.run(main())
