"""Guard: every command / tool an example invokes must exist.

Examples only execute live in the nightly e2e, so a renamed CLI command or a removed MCP tool
hides until then. This validates statically (no DHIS2 stack):

- CLI examples (*.sh): each `d2w <group> <subcommand> ...` path must resolve in the Typer tree.
  Leaf arguments are not flagged — only a command-like token under a *group* that has no such
  child counts as a broken reference.
- MCP examples (*.py): each `call_tool("name", ...)` name must be a registered tool.

Run via `make check-examples` alongside the per-version sync check.
"""

from __future__ import annotations

import asyncio
import re
import shlex
import sys
from pathlib import Path
from typing import Any

import click
import typer
from dhis2w_cli.main import build_app
from dhis2w_mcp.server import build_server

ROOT = Path(__file__).resolve().parents[2] / "examples"
_GLOBAL_OPTS_WITH_VALUE = {"-p", "--profile"}
_GLOBAL_FLAGS = {"--json", "-q", "--quiet", "-y", "--yes"}


def _command_tree() -> Any:
    """The root click group for the `d2w` CLI."""
    return typer.main.get_command(build_app())


def _strip_comments(text: str) -> str:
    """Drop the `#` comment portion of each line so prose isn't parsed as commands/calls."""
    return "\n".join(line.split("#", 1)[0] for line in text.splitlines())


def _bad_cli_refs(text: str, root: Any) -> set[str]:
    """Return `d2w <path>` invocations whose command path doesn't resolve."""
    bad: set[str] = set()
    for raw in re.findall(r"\bdhis2\s+([^\n|;&<>]+)", _strip_comments(text)):
        try:
            tokens = shlex.split(raw)
        except ValueError:
            continue  # unbalanced quotes from shell vars — skip
        index = 0
        while index < len(tokens) and (tokens[index] in _GLOBAL_FLAGS or tokens[index] in _GLOBAL_OPTS_WITH_VALUE):
            index += 1 if tokens[index] in _GLOBAL_FLAGS else 2
        node: Any = root
        path: list[str] = []
        for token in tokens[index:]:
            if not re.fullmatch(r"[a-z][a-z0-9-]*", token):
                break  # option / arg / variable — command path ended
            if not hasattr(node, "get_command"):
                break  # reached a leaf; remaining tokens are arguments
            child = node.get_command(click.Context(node), token)
            if child is None:
                bad.add(f"d2w {' '.join([*path, token])}")
                break
            path.append(token)
            node = child
    return bad


async def _live_tools() -> set[str]:
    """Every registered MCP tool name."""
    return {tool.name for tool in await build_server().list_tools()}


def main() -> int:
    """Validate every example's CLI commands + MCP tool calls; exit 1 on any broken reference."""
    root = _command_tree()
    tools = asyncio.run(_live_tools())
    problems: list[str] = []

    for path in sorted(ROOT.rglob("*.sh")):
        for ref in sorted(_bad_cli_refs(path.read_text(), root)):
            problems.append(f"{path.relative_to(ROOT.parent)}: unknown command `{ref}`")

    for path in sorted(ROOT.rglob("*.py")):
        for name in sorted(set(re.findall(r'call_tool\(\s*"([a-z0-9_]+)"', _strip_comments(path.read_text())))):
            if name not in tools:
                problems.append(f"{path.relative_to(ROOT.parent)}: unknown MCP tool `{name}`")

    if problems:
        print("Example references that don't resolve:")
        for line in problems:
            print(f"  - {line}")
        return 1
    print("all example CLI commands + MCP tool calls resolve")
    return 0


if __name__ == "__main__":
    sys.exit(main())
