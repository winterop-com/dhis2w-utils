"""Command x model matrix: how each LM Studio model handles every d2w CLI command.

Enumerates every leaf command in the CLI, derives a task from its help text, and drives each
model in the roster through the bridge to see whether it discovers and forms the right command.
Runs READ-ONLY against play42 (`DHIS2_MCP_READONLY=1`), so write commands are *formed* by the
model and refused before any mutation — the metric is "did the AI navigate to the right command
path", which is safe to measure for reads and writes alike.

Streaming + resumable: every (model, command) cell is appended to `--results` as it completes, and
a re-run skips cells already present. Renders a per-group Markdown matrix to `--out`.

Prereqs: `lms server` running. The script loads/unloads each model itself.

Usage:
    uv run python infra/scripts/cli_matrix.py --group metadata --models google/gemma-4-12b-qat
    uv run python infra/scripts/cli_matrix.py            # full grid (roster x all groups; long)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import shlex
import time
from pathlib import Path

import httpx
import typer.main
from dhis2w_cli.main import build_app
from fastmcp import Client
from pydantic import BaseModel, ConfigDict

from dhis2w_bench.backend import get_backend

#: Local-inference backend (LM Studio by default; override with MODEL_BACKEND).
BACKEND = get_backend()
LM = BACKEND.chat_url
REPO = str(Path(__file__).resolve().parents[4])
RESULTS = "/tmp/cli_matrix.jsonl"
OUT = "docs/notes/cli-matrix.md"
PROFILE = "play42"
MAX_STEPS = 4
SYSTEM_PROMPT = (
    "You are a DHIS2 operator with one tool, dhis2_cli, that runs the d2w CLI. Discover commands "
    "with --help when unsure, then run the one that fits the task. Never answer from memory. Reply "
    "in plain text when done."
)


class Leaf(BaseModel):
    """A CLI leaf command: its path and one-line help."""

    model_config = ConfigDict(frozen=True)

    path: tuple[str, ...]
    help: str


class Cell(BaseModel):
    """One (model, command) result: did the model form the target path, did a read execute, cost."""

    model_config = ConfigDict(frozen=True)

    model: str
    command: str
    hit: bool
    exec_ok: bool
    calls: int
    secs: float


class _Fn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str = ""
    arguments: str = "{}"


class _ToolCall(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    type: str = "function"
    function: _Fn


class _Msg(BaseModel):
    model_config = ConfigDict(extra="ignore")
    content: str | None = None
    tool_calls: list[_ToolCall] = []


class _Choice(BaseModel):
    model_config = ConfigDict(extra="ignore")
    message: _Msg


class _Chat(BaseModel):
    model_config = ConfigDict(extra="ignore")
    choices: list[_Choice]


def enumerate_leaves() -> list[Leaf]:
    """Walk the Typer/Click tree and return every leaf command path + its help text."""
    root = typer.main.get_command(build_app())
    leaves: list[Leaf] = []

    def walk(node: object, path: tuple[str, ...]) -> None:
        commands = getattr(node, "commands", None)
        if commands:
            for name, child in commands.items():
                walk(child, (*path, name))
        else:
            help_text = (getattr(node, "help", None) or getattr(node, "short_help", None) or "").strip().split("\n")[0]
            leaves.append(Leaf(path=path, help=help_text))

    walk(root, ())
    return leaves


def _task(leaf: Leaf) -> str:
    """Derive a natural task prompt from a command's help text."""
    goal = leaf.help or " ".join(leaf.path)
    return (
        f"Goal: {goal}. Find and run the single d2w command that does this "
        "(use dataElements as the resource if one is needed)."
    )


def _normalize_args(arguments: object) -> list[str]:
    """Coerce a model's `args` to a token list — shlex-split a packed string so the call is valid.

    FastMCP validates `args` against `list[str]` client-side, so a model that packs the whole
    command into one string (`"metadata list dataElements ..."`) would raise before the bridge can
    tokenize it. Split it here instead of crashing the sweep.
    """
    raw = arguments.get("args") if isinstance(arguments, dict) else None
    if isinstance(raw, str):
        try:
            return shlex.split(raw)
        except ValueError:
            return raw.split()
    if isinstance(raw, list):
        return [str(token) for token in raw]
    return []


def _bridge_config() -> dict[str, object]:
    """Read-only bridge config against the read profile."""
    return {
        "mcpServers": {
            "dhis2": {
                "command": "uv",
                "args": ["run", "--directory", REPO, "dhis2w-mcp-bridge"],
                "env": {"DHIS2_PROFILE": PROFILE, "DHIS2_MCP_READONLY": "1"},
            }
        }
    }


def _tool_specs(mcp_tools: object) -> list[dict[str, object]]:
    """Build the OpenAI tool spec list from the bridge's single tool."""
    specs: list[dict[str, object]] = []
    for tool in list(mcp_tools):  # type: ignore[call-overload]
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


async def _run_cell(
    client: Client, http: httpx.AsyncClient, tools: list[dict[str, object]], model: str, leaf: Leaf
) -> Cell:
    """Drive one model against one command; score whether it formed the target command path."""
    messages: list[dict[str, object]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": _task(leaf)},
    ]
    target = list(leaf.path)
    hit = False
    exec_ok = False
    calls = 0
    started = time.monotonic()
    for _ in range(MAX_STEPS):
        body = {"model": model, "messages": messages, "tools": tools, "temperature": 0.2}
        try:
            resp = await http.post(LM, json=body, timeout=300.0)
            resp.raise_for_status()
        except httpx.HTTPError:
            break
        message = _Chat.model_validate(resp.json()).choices[0].message
        if not message.tool_calls:
            break
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
            path = _normalize_args(arguments)
            if path[: len(target)] == target and "--help" not in path:
                hit = True
            try:
                data = (await client.call_tool("dhis2_cli", {"args": path})).data
                output = str(data.stdout) if int(data.exit_code) == 0 else f"ERROR: {data.stderr}"
                if hit and int(data.exit_code) == 0:
                    exec_ok = True
            except Exception as exc:  # noqa: BLE001 - a malformed tool call shouldn't abort the sweep
                output = f"ERROR: invalid tool call ({type(exc).__name__})"
            messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": output[:6000]})
        if hit:
            break
    return Cell(
        model=model,
        command=" ".join(leaf.path),
        hit=hit,
        exec_ok=exec_ok,
        calls=calls,
        secs=round(time.monotonic() - started, 1),
    )


def _load_model(model: str) -> None:
    """Load exactly one model instance."""
    BACKEND.load(model)


def _done(results_path: Path) -> set[tuple[str, str]]:
    """Return the (model, command) cells already recorded, for resume."""
    done: set[tuple[str, str]] = set()
    if results_path.exists():
        for line in results_path.read_text().splitlines():
            if line.strip():
                cell = Cell.model_validate_json(line)
                done.add((cell.model, cell.command))
    return done


def _render(results_path: Path, out_path: Path, models: list[str]) -> None:
    """Render the streamed cells into a per-group Markdown matrix."""
    cells = [Cell.model_validate_json(line) for line in results_path.read_text().splitlines() if line.strip()]
    by_cmd: dict[str, dict[str, Cell]] = {}
    for cell in cells:
        by_cmd.setdefault(cell.command, {})[cell.model] = cell
    lines = [
        "# CLI command x model matrix",
        "",
        "`HIT` = model formed the right command path; `RUN` = read executed (exit 0); `miss` = neither.",
        "",
        "> **Read `miss` with care.** Each task is auto-derived from a command's one-line help, then the",
        "> model must pick that exact command among ~200 metadata siblings. A `miss` is usually that",
        "> ambiguity — the model ran a plausible neighbour — not an inability to use the command. The",
        "> structural proof that every command works is the deterministic `--help` guard",
        "> (`test_every_command_renders_help`); this grid measures *discoverability under a vague goal*.",
        "",
    ]
    groups: dict[str, list[str]] = {}
    for command in sorted(by_cmd):
        groups.setdefault(command.split(" ")[0], []).append(command)
    short = [m.split("/")[-1] for m in models]
    for group in sorted(groups):
        lines.append(f"## {group}")
        lines.append("| command | " + " | ".join(short) + " |")
        lines.append("| --- | " + " | ".join("---" for _ in short) + " |")
        for command in groups[group]:
            row = [f"`{command}`"]
            for model in models:
                found = by_cmd[command].get(model)
                row.append("-" if found is None else ("RUN" if found.exec_ok else ("HIT" if found.hit else "miss")))
            lines.append("| " + " | ".join(row) + " |")
        lines.append("")
    out_path.write_text("\n".join(lines))


async def _benchmark(models: list[str], leaves: list[Leaf], results_path: Path) -> None:
    """Run each model across the given leaves, streaming each cell to disk; resume-aware."""
    done = _done(results_path)
    with results_path.open("a") as handle:
        for model in models:
            pending = [leaf for leaf in leaves if (model, " ".join(leaf.path)) not in done]
            if not pending:
                continue
            print(f">>> {model}: {len(pending)} commands")
            _load_model(model)
            async with Client(_bridge_config()) as client:
                tools = _tool_specs(await client.list_tools())
                async with httpx.AsyncClient() as http:
                    for index, leaf in enumerate(pending, 1):
                        cell = await _run_cell(client, http, tools, model, leaf)
                        handle.write(cell.model_dump_json() + "\n")
                        handle.flush()
                        if index % 10 == 0:
                            print(f"    {index}/{len(pending)}")


async def main() -> None:
    """Parse args, run the requested slice of the matrix, and re-render the Markdown."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--group", default=None, help="Limit to one top-level command group (e.g. metadata).")
    parser.add_argument("--models", nargs="+", required=True, help="Models to run (no default; see `make bench-list`).")
    parser.add_argument("--max", type=int, default=None, help="Cap the number of commands (for a quick batch).")
    parser.add_argument("--results", default=RESULTS)
    parser.add_argument("--out", default=OUT)
    args = parser.parse_args()

    leaves = enumerate_leaves()
    if args.group:
        leaves = [leaf for leaf in leaves if leaf.path[0] == args.group]
    if args.max:
        leaves = leaves[: args.max]
    results_path = Path(args.results)
    print(f"matrix: {len(leaves)} commands x {len(args.models)} models = {len(leaves) * len(args.models)} cells")
    await _benchmark(args.models, leaves, results_path)
    _render(results_path, Path(args.out), args.models)
    print(f"rendered {args.out}")


if __name__ == "__main__":
    asyncio.run(main())
