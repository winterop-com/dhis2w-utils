"""Benchmark named local models driving the dhis2 bridge: read + write + perf.

The recurring model benchmark for `dhis2w-mcp-bridge`. For each model named on the command line it
loads the model, runs a fixed read round (play42, read-only) and a write round-trip (local_basic,
self-restoring), scores correctness, and records timing + token throughput. Prints a Markdown table
and appends per-model JSON to `RESULTS`. There is no hardcoded roster — name the model(s) explicitly;
set `BENCH_CHAMPION=<key>` to designate an oracle (SUSPECT-task check when it's in the run).

Prereqs: a running backend (LM Studio by default; `MODEL_BACKEND` to switch). The script
loads/unloads models itself. The write round needs `local_basic` up (`make dhis2-run`).

Usage:
    uv run python infra/scripts/bench_bridge_models.py google/gemma-4-12b-qat            # one model
    uv run python infra/scripts/bench_bridge_models.py gemma-4-12b-qat gemma-4-e4b        # several
    BENCH_CHAMPION=<key> uv run python infra/scripts/bench_bridge_models.py <model> ...   # with an oracle

Results worth keeping live in docs/notes/model-benchmark.md. Testing policy: reads -> play42,
writes -> local_basic (never the shared public demo).
"""

from __future__ import annotations

import asyncio
import json
import os
import shlex
import sys
import time
from collections.abc import Sequence
from pathlib import Path

import httpx
from fastmcp import Client
from pydantic import BaseModel, ConfigDict

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _model_backend import get_backend  # noqa: E402 — sibling import needs the path-prepend above

#: Optional oracle model key (env `BENCH_CHAMPION`). When set and present in a run, the harness asserts
#: it passed every task and flags SUSPECT tasks otherwise (an oracle failure means the TASK is suspect,
#: not the model). Unset -> no oracle check. There is no hardcoded roster: name the models explicitly.
CHAMPION = os.environ.get("BENCH_CHAMPION", "").strip()

#: Local-inference backend (LM Studio by default; override with MODEL_BACKEND).
BACKEND = get_backend()
LM = BACKEND.chat_url
REPO = "/Users/morteoh/dev/local/dhis2w-utils"
RESULTS = "/tmp/bench_bridge_results.jsonl"
SYSTEM_PROMPT = (
    "You are a DHIS2 operator with one tool, dhis2_cli, that runs the d2w CLI. Always use the "
    "tool to get real data; never answer from memory. When you have the answer, reply in plain "
    "text with no further tool calls."
)
READ_TASKS: tuple[tuple[str, str], ...] = (
    ("count", "How many data elements are there? Give just the number."),
    ("schema", "What fields does a data element have? List a few of them."),
    ("filter", "List indicators whose name contains 'ANC' (names only)."),
)
WRITE_TASK = (
    "Set the system setting minPasswordLength to 10 (a single system setting is written with "
    "'dev customize set <key> <value>'), then read the security settings and confirm it is now 10."
)


class _ToolCallFunction(BaseModel):
    """The function block of an OpenAI tool call.

    `name` is retained (not just `arguments`) because the call is echoed back inside the
    assistant message — dropping it degrades or breaks the model's next turn.
    """

    model_config = ConfigDict(extra="ignore")

    name: str = ""
    arguments: str = "{}"


class _ToolCall(BaseModel):
    """A model-requested tool call."""

    model_config = ConfigDict(extra="ignore")

    id: str
    type: str = "function"
    function: _ToolCallFunction


class _Message(BaseModel):
    """The assistant message of a chat-completion choice."""

    model_config = ConfigDict(extra="ignore")

    content: str | None = None
    tool_calls: list[_ToolCall] = []


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
    usage: _Usage = _Usage()


class TaskOutcome(BaseModel):
    """Scored outcome of one task: pass/fail, tool-call count, wall-clock, tokens."""

    model_config = ConfigDict(frozen=True)

    key: str
    ok: bool
    calls: int
    secs: float
    tokens: int


class ModelReport(BaseModel):
    """A model's full benchmark line: read outcomes + the write outcome."""

    model_config = ConfigDict(frozen=True)

    model: str
    read: list[TaskOutcome]
    write: TaskOutcome
    found_write_cmd: bool

    @property
    def all_passed(self) -> bool:
        """True when every read task and the write task passed (the oracle bar)."""
        return all(outcome.ok for outcome in self.read) and self.write.ok


class _Run(BaseModel):
    """Raw metrics from one agent loop, before scoring."""

    model_config = ConfigDict(frozen=True)

    calls: int
    secs: float
    tokens: int
    answer: str
    tool_args: list[list[str]]


def _normalize_args(arguments: object) -> list[str]:
    """Coerce a model's `args` to a token list — shlex-split a packed string so the call validates."""
    raw = arguments.get("args") if isinstance(arguments, dict) else None
    if isinstance(raw, str):
        try:
            return shlex.split(raw)
        except ValueError:
            return raw.split()
    if isinstance(raw, list):
        return [str(token) for token in raw]
    return []


def _bridge_config(profile: str, readonly: str) -> dict[str, object]:
    """Bridge client config (same shape as ~/.lmstudio/mcp.json)."""
    return {
        "mcpServers": {
            "dhis2": {
                "command": "uv",
                "args": ["run", "--directory", REPO, "dhis2w-mcp-bridge"],
                "env": {"DHIS2_PROFILE": profile, "DHIS2_MCP_READONLY": readonly},
            }
        }
    }


def _tools(mcp_tools: Sequence[object]) -> list[dict[str, object]]:
    """Convert FastMCP tools to OpenAI function-tool specs."""
    specs: list[dict[str, object]] = []
    for tool in mcp_tools:
        specs.append(
            {
                "type": "function",
                "function": {
                    "name": getattr(tool, "name", "dhis2_cli"),
                    "description": (getattr(tool, "description", "") or "")[:6000],
                    "parameters": getattr(tool, "inputSchema", {}),
                },
            }
        )
    return specs


async def _bridge_call(client: Client, args: list[str]) -> tuple[int, str]:
    """Invoke the bridge tool directly (baseline/restore); return (exit_code, stdout)."""
    data = (await client.call_tool("dhis2_cli", {"args": args})).data
    return int(data.exit_code), str(data.stdout)


async def _agent(
    client: Client, http: httpx.AsyncClient, tools: list[dict[str, object]], model: str, task: str, max_steps: int
) -> _Run:
    """Run one task through the model + bridge; capture calls, wall-clock, tokens, tool args."""
    messages: list[dict[str, object]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": task},
    ]
    calls = 0
    tokens = 0
    tool_args: list[list[str]] = []
    started = time.monotonic()
    for _ in range(max_steps):
        body = {"model": model, "messages": messages, "tools": tools, "temperature": 0.2}
        try:
            resp = await http.post(LM, json=body, timeout=300.0)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            return _Run(
                calls=calls,
                secs=round(time.monotonic() - started, 1),
                tokens=tokens,
                answer=f"[API error: {type(exc).__name__}]",
                tool_args=tool_args,
            )
        parsed = _ChatResponse.model_validate(resp.json())
        tokens += parsed.usage.completion_tokens
        message = parsed.choices[0].message
        if not message.tool_calls:
            return _Run(
                calls=calls,
                secs=round(time.monotonic() - started, 1),
                tokens=tokens,
                answer=(message.content or "").strip(),
                tool_args=tool_args,
            )
        messages.append(
            {
                "role": "assistant",
                "content": message.content or "",
                "tool_calls": [tc.model_dump() for tc in message.tool_calls],
            }
        )
        for call in message.tool_calls:
            calls += 1
            try:
                arguments = json.loads(call.function.arguments or "{}")
            except json.JSONDecodeError:
                arguments = {}
            cli_args = _normalize_args(arguments)
            tool_args.append(cli_args)
            try:
                data = (await client.call_tool("dhis2_cli", {"args": cli_args})).data
                text = str(data.stdout) if int(data.exit_code) == 0 else f"ERROR (exit {data.exit_code}): {data.stderr}"
            except Exception as exc:  # noqa: BLE001 - a malformed tool call shouldn't abort the round
                text = f"ERROR: invalid tool call ({type(exc).__name__})"
            messages.append({"role": "tool", "tool_call_id": call.id, "content": text[:8000]})
    return _Run(
        calls=calls,
        secs=round(time.monotonic() - started, 1),
        tokens=tokens,
        answer="[max steps reached]",
        tool_args=tool_args,
    )


def _used(tool_args: list[list[str]], prefix: list[str]) -> bool:
    """Did any tool call start with the given command-path prefix?"""
    return any(args[: len(prefix)] == prefix for args in tool_args)


def _score_read(key: str, run: _Run) -> bool:
    """Correctness heuristic per read task."""
    answer = run.answer.lower()
    if key == "count":
        return "1037" in run.answer
    if key == "schema":
        return _used(run.tool_args, ["schema"]) and any(
            field in answer for field in ("valuetype", "domaintype", "aggregation", "code")
        )
    return "anc" in answer  # filter


async def _benchmark_model(model: str) -> ModelReport:
    """Run the read round (play42) then the write round-trip (local_basic) for one model."""
    read_outcomes: list[TaskOutcome] = []
    async with Client(_bridge_config("play42", "1")) as client:
        tools = _tools(await client.list_tools())
        async with httpx.AsyncClient() as http:
            for key, task in READ_TASKS:
                run = await _agent(client, http, tools, model, task, max_steps=8)
                ok = _score_read(key, run)
                read_outcomes.append(TaskOutcome(key=key, ok=ok, calls=run.calls, secs=run.secs, tokens=run.tokens))
                print(f"  READ {key}: ok={ok} calls={run.calls} {run.secs}s {run.tokens}tok")

    async with Client(_bridge_config("local_basic", "0")) as client:
        _, base_out = await _bridge_call(client, ["security", "settings"])
        baseline = json.loads(base_out).get("minPasswordLength") if base_out.strip().startswith("{") else None
        async with httpx.AsyncClient() as http:
            run = await _agent(client, http, tools, model, WRITE_TASK, max_steps=10)
        found = _used(run.tool_args, ["dev", "customize", "set"])
        write = TaskOutcome(
            key="write", ok=found and "10" in run.answer, calls=run.calls, secs=run.secs, tokens=run.tokens
        )
        print(f"  WRITE: ok={write.ok} found_cmd={found} calls={run.calls} {run.secs}s")
        if baseline is not None:
            await _bridge_call(client, ["dev", "customize", "set", "minPasswordLength", str(baseline)])

    return ModelReport(model=model, read=read_outcomes, write=write, found_write_cmd=found)


def _load_model(model: str) -> None:
    """Unload everything, then load `model` (one instance — avoids ambiguous-id 400s)."""
    BACKEND.load(model)


def _markdown_table(reports: list[ModelReport]) -> str:
    """Render the roster results as a Markdown table."""
    lines = ["| model | count | schema | filter | write | read tok/s |", "| --- | --- | --- | --- | --- | --- |"]
    for report in reports:
        by_key = {outcome.key: outcome for outcome in report.read}
        total_tokens = sum(outcome.tokens for outcome in report.read)
        total_secs = sum(outcome.secs for outcome in report.read) or 1.0

        def cell(outcome: TaskOutcome) -> str:
            return f"{'PASS' if outcome.ok else 'FAIL'} {outcome.secs}s"

        write_note = (
            "PASS" if report.write.ok else ("found-cmd, no-confirm" if report.found_write_cmd else "cmd-not-found")
        )
        lines.append(
            f"| `{report.model}` | {cell(by_key['count'])} | {cell(by_key['schema'])} | {cell(by_key['filter'])} "
            f"| {write_note} {report.write.secs}s | ~{round(total_tokens / total_secs)} |"
        )
    return "\n".join(lines)


async def _local_infra_reachable() -> bool:
    """Return True if the local_basic write target answers a cheap read (probe is read-only)."""
    async with Client(_bridge_config("local_basic", "1")) as client:
        code, _ = await _bridge_call(client, ["system", "info"])
    return code == 0


def _installed_models(requested: list[str]) -> list[str]:
    """Filter `requested` to models the backend has installed; log (don't fail on) the rest."""
    installed = set(BACKEND.list_installed())
    if not installed:  # backend listing failed — don't silently skip everything
        return requested
    models: list[str] = []
    for model in requested:
        if model in installed:
            models.append(model)
        else:
            print(f"!!! skip {model}: not installed (run `lms get {model}` to add it)")
    return models


def _check_oracle(reports: list[ModelReport]) -> None:
    """If an oracle (`BENCH_CHAMPION`) is set and ran, assert it passed; a failure flags a suspect task."""
    if not CHAMPION:
        return
    champion = next((report for report in reports if report.model == CHAMPION), None)
    if champion is None:
        return  # the named oracle wasn't part of this run — nothing to check
    if champion.all_passed:
        print(f"\nOracle OK: {CHAMPION} passed every task.")
        return
    failed = [outcome.key for outcome in champion.read if not outcome.ok]
    if not champion.write.ok:
        failed.append("write")
    print(
        f"\n!!! SUSPECT TASK(S): oracle {CHAMPION} FAILED {failed}. The oracle is the should-pass "
        "bar — fix the task(s) before trusting the weaker-model columns above; an oracle failure "
        "usually means the task is mis-specified, not the model."
    )


def _require_models() -> list[str]:
    """Return the model keys to benchmark from argv; exit with the installed list when none given."""
    requested = sys.argv[1:]
    if not requested:
        installed = BACKEND.list_installed()
        listing = "\n  ".join(installed) if installed else "(none found)"
        print(
            "usage: bench_bridge_models.py <model-key> [<model-key> ...]\n"
            "no model defaults — name the model(s) explicitly. Installed:\n  " + listing,
            file=sys.stderr,
        )
        sys.exit(2)
    return requested


async def main() -> None:
    """Benchmark the models named on the command line and print the Markdown table."""
    models = _installed_models(_require_models())
    if not models:
        print("none of the requested models are installed", file=sys.stderr)
        return
    if not await _local_infra_reachable():
        print(
            "!!! local_basic is unreachable — the write round needs it up.\n"
            "    Start the local stack first:  make dhis2-run\n"
            "    (reads use play42 and would work, but this benchmark includes the write round.)",
            file=sys.stderr,
        )
        sys.exit(1)

    reports: list[ModelReport] = []
    for model in models:
        print(f">>> {model}")
        _load_model(model)
        reports.append(await _benchmark_model(model))

    with open(RESULTS, "a") as handle:
        for report in reports:
            handle.write(report.model_dump_json() + "\n")
    print("\n" + _markdown_table(reports))
    _check_oracle(reports)


if __name__ == "__main__":
    asyncio.run(main())
