"""Drive `dhis2w-mcp-bridge` with a local LM Studio model — a repeatable test round.

This is the canonical rig for exercising the single-tool CLI bridge (`dhis2_cli`)
the way a small on-box model does: LM Studio supplies the brain over its
OpenAI-compatible API, and every tool call is routed through the REAL bridge
(spawned via FastMCP's client, same config shape as `~/.lmstudio/mcp.json`), so
read-only enforcement, `--json` injection, and arg tokenization are all live.

Why a host-loop and not `lms chat`: `lms chat` does NOT load the MCP servers from
`mcp.json` (only the LM Studio GUI does), so it cannot reach the bridge tool. This
script wires the two together itself.

## Prerequisites

1. LM Studio's local server is running: `lms server start` (default port 1234).
2. The model is available/loaded: `lms load <model> --gpu max --ttl 3600`.
   (The `make bench-round` target loads it for you.)

## Profiles and read-only mode (testing policy — do not deviate)

- READS run against `play42` (or `local_basic`) with `DHIS2_MCP_READONLY=1`.
- WRITES run ONLY against `local_basic` with `DHIS2_MCP_READONLY=0` — NEVER the
  shared public demo. The write round captures the affected setting first and
  restores it afterwards, so it is safe to re-run.

## Usage

    uv run python infra/scripts/bridge_round.py --round read   --profile play42
    uv run python infra/scripts/bridge_round.py --round write  --profile local_basic
    uv run python infra/scripts/bridge_round.py --round bench  --profile play42
    uv run python infra/scripts/bridge_round.py --model qwen/qwen3.5-4b --round read

`--readonly` defaults to 1 for read/bench and 0 for write; override with `--readonly 0|1`.
Results worth keeping go in `docs/notes/small-model-bridge.md` (the benchmark table + rounds).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any

import httpx
from fastmcp import Client
from pydantic import BaseModel, ConfigDict

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _model_backend import get_backend  # noqa: E402 — sibling import needs the path-prepend above

#: OpenAI-compatible chat-completions endpoint (LM Studio by default; override with MODEL_BACKEND).
LMSTUDIO_URL = get_backend().chat_url
#: Repo root used to spawn the bridge via `uv run --directory`.
REPO_DIR = "/Users/morteoh/dev/local/dhis2w-utils"

#: System prompt that frames the single-tool agent loop.
SYSTEM_PROMPT = (
    "You are a DHIS2 operator with one tool, dhis2_cli, that runs the d2w CLI. "
    "Always use the tool to get real data; never answer from memory. When you have "
    "the answer, reply in plain text with no further tool calls."
)

#: Read-round tasks (safe against any profile under DHIS2_MCP_READONLY=1).
READ_TASKS = (
    "How many dataElements are on this server? Give me the number.",
    "Show me the security settings for this server (run the security settings command).",
    "Find indicators whose name contains 'ANC'. List just their names.",
    "Who am I logged in as? Give my username and the server version.",
)

#: Write-round task (local_basic only). The runner snapshots minPasswordLength
#: before and restores it after, so this is a reversible round-trip.
WRITE_TASK = (
    "Set the system setting 'minPasswordLength' to 10 (a single system setting is written "
    "with 'dev customize set <key> <value>'). After setting it, read the server's security "
    "settings and confirm minPasswordLength is now 10. Report the final value."
)

#: Bench prompts mirroring the `docs/notes/small-model-bridge.md` table columns.
BENCH_TASKS = (
    ("primary", "Get id, code, name and description for all our data elements."),
    ("count", "How many data elements are there? Give just the number."),
    ("starts-with", "List data elements whose name starts with 'Malaria'. Names only."),
)


class CliResult(BaseModel):
    """The bridge's `dhis2_cli` return shape: process exit code and captured streams."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    exit_code: int
    stdout: str
    stderr: str


class _ToolCallFunction(BaseModel):
    """The `function` block of an OpenAI-style tool call (name + raw JSON arguments)."""

    model_config = ConfigDict(extra="ignore")

    name: str
    arguments: str = "{}"


class _ToolCall(BaseModel):
    """A single tool call requested by the model.

    `type` is retained (default "function") because the OpenAI schema requires it when
    the call is echoed back inside the assistant message — dropping it yields a 400
    "Invalid 'messages'".
    """

    model_config = ConfigDict(extra="ignore")

    id: str
    type: str = "function"
    function: _ToolCallFunction


class _Message(BaseModel):
    """The assistant message from a chat-completion choice."""

    model_config = ConfigDict(extra="ignore")

    content: str | None = None
    tool_calls: list[_ToolCall] = []


class _Choice(BaseModel):
    """One chat-completion choice."""

    model_config = ConfigDict(extra="ignore")

    message: _Message


class _ChatResponse(BaseModel):
    """The chat-completions response, narrowed to the fields this rig reads."""

    model_config = ConfigDict(extra="ignore")

    choices: list[_Choice]


def _bridge_config(profile: str, readonly: str) -> dict[str, Any]:
    """Build the FastMCP client config (same shape as `~/.lmstudio/mcp.json`)."""
    return {
        "mcpServers": {
            "dhis2": {
                "command": "uv",
                "args": ["run", "--directory", REPO_DIR, "dhis2w-mcp-bridge"],
                "env": {"DHIS2_PROFILE": profile, "DHIS2_MCP_READONLY": readonly},
            }
        }
    }


def _to_openai_tool(tool: Any) -> dict[str, Any]:
    """Convert a FastMCP tool into an OpenAI function-tool spec for the model."""
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": (tool.description or "")[:6000],
            "parameters": tool.inputSchema,
        },
    }


async def _call_bridge(client: Client, arguments: dict[str, Any]) -> CliResult:
    """Invoke the bridge's dhis2_cli tool and return its typed result."""
    raw = (await client.call_tool("dhis2_cli", arguments)).data
    return CliResult(exit_code=int(raw.exit_code), stdout=str(raw.stdout), stderr=str(raw.stderr))


async def _agent_loop(
    client: Client,
    http: httpx.AsyncClient,
    tools: list[dict[str, Any]],
    model: str,
    task: str,
    *,
    max_steps: int,
    verbose: bool,
) -> tuple[int, float, str]:
    """Run one task to a final answer; return (tool_calls, seconds, final_text)."""
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": task},
    ]
    calls = 0
    started = time.monotonic()

    for step in range(1, max_steps + 1):
        body = {"model": model, "messages": messages, "tools": tools, "temperature": 0.2}
        response = await http.post(LMSTUDIO_URL, json=body, timeout=300.0)
        response.raise_for_status()
        parsed = _ChatResponse.model_validate(response.json())
        message = parsed.choices[0].message

        if not message.tool_calls:
            return calls, round(time.monotonic() - started, 1), (message.content or "").strip()

        messages.append(
            {
                "role": "assistant",
                "content": message.content or "",
                "tool_calls": [tc.model_dump() for tc in message.tool_calls],
            }
        )
        for tool_call in message.tool_calls:
            calls += 1
            try:
                arguments = json.loads(tool_call.function.arguments or "{}")
            except json.JSONDecodeError:
                arguments = {}
            if verbose:
                print(f"[step {step}] -> dhis2_cli({json.dumps(arguments)})")
            result = await _call_bridge(client, arguments)
            payload = result.stdout if result.exit_code == 0 else f"ERROR (exit {result.exit_code}): {result.stderr}"
            if verbose:
                preview = payload if len(payload) <= 500 else payload[:500] + f"... (+{len(payload) - 500} chars)"
                print(f"   <- {preview}")
            messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": payload[:8000]})

    return calls, round(time.monotonic() - started, 1), "[no final answer within max steps]"


async def _read_round(client: Client, http: httpx.AsyncClient, tools: list[dict[str, Any]], model: str) -> None:
    """Drive every READ_TASK and print a transcript per task."""
    for task in READ_TASKS:
        print(f"\n{'=' * 78}\nTASK: {task}\n{'=' * 78}")
        calls, secs, answer = await _agent_loop(client, http, tools, model, task, max_steps=8, verbose=True)
        print(f"\nFINAL ({calls} calls, {secs}s): {answer}")


async def _write_round(client: Client, http: httpx.AsyncClient, tools: list[dict[str, Any]], model: str) -> None:
    """Snapshot minPasswordLength, drive the write task, then restore the baseline."""
    before = await _call_bridge(client, {"args": ["security", "settings"]})
    baseline = json.loads(before.stdout).get("minPasswordLength") if before.exit_code == 0 else None
    print(f"baseline minPasswordLength = {baseline}")

    print(f"\n{'=' * 78}\nTASK: {WRITE_TASK}\n{'=' * 78}")
    calls, secs, answer = await _agent_loop(client, http, tools, model, WRITE_TASK, max_steps=10, verbose=True)
    print(f"\nFINAL ({calls} calls, {secs}s): {answer}")

    if baseline is not None:
        restored = await _call_bridge(client, {"args": ["dev", "customize", "set", "minPasswordLength", str(baseline)]})
        print(f"\nrestore minPasswordLength -> {baseline}: exit {restored.exit_code}")


async def _bench_round(client: Client, http: httpx.AsyncClient, tools: list[dict[str, Any]], model: str) -> None:
    """Run the timed benchmark prompts and print one line per prompt."""
    print(f"model={model}")
    for label, task in BENCH_TASKS:
        calls, secs, answer = await _agent_loop(client, http, tools, model, task, max_steps=8, verbose=False)
        print(f"\n### {label}: calls={calls} secs={secs}\n{answer[:400]}")


async def _run(model: str, profile: str, readonly: str, round_name: str) -> int:
    """Wire the bridge + LM Studio and dispatch the selected round."""
    print(f"ROUND={round_name}  MODEL={model}  PROFILE={profile}  READONLY={readonly}")
    client = Client(_bridge_config(profile, readonly))
    async with client:
        tools = [_to_openai_tool(tool) for tool in await client.list_tools()]
        print(f"bridge tools: {[tool['function']['name'] for tool in tools]}")
        async with httpx.AsyncClient() as http:
            if round_name == "read":
                await _read_round(client, http, tools, model)
            elif round_name == "write":
                await _write_round(client, http, tools, model)
            else:
                await _bench_round(client, http, tools, model)
    return 0


def main() -> int:
    """Parse arguments and run a single bridge test round; return an exit code."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", required=True, help="Model key to drive (no default; see `make bench-list`).")
    parser.add_argument("--profile", default="play42", help="DHIS2 profile (writes: local_basic only).")
    parser.add_argument("--round", default="read", choices=("read", "write", "bench"), help="Which round to run.")
    parser.add_argument("--readonly", default=None, choices=("0", "1"), help="Override DHIS2_MCP_READONLY.")
    args = parser.parse_args()

    if args.round == "write" and args.profile != "local_basic":
        parser.error("the write round mutates settings — use --profile local_basic")

    readonly = args.readonly if args.readonly is not None else ("0" if args.round == "write" else "1")
    try:
        return asyncio.run(_run(args.model, args.profile, readonly, args.round))
    except httpx.HTTPStatusError as exc:
        body = exc.response.text[:500]
        print(f"!!! LM Studio returned {exc.response.status_code}: {body}", file=sys.stderr)
        print("    A 400 often means the model id is ambiguous — run `lms ps` and unload duplicates", file=sys.stderr)
        return 1
    except httpx.HTTPError as exc:
        print(f"!!! LM Studio request failed (is `lms server` up and the model loaded?): {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
