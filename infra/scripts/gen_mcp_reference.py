"""Introspect the dhis2 FastMCP server and write `docs/mcp-reference.md`.

Runs the in-process Client, lists every registered tool, and emits a
markdown reference grouping tools by their top-level prefix (`metadata_*`,
`analytics_*`, ...). Each tool gets a table of parameters (name, type,
required, description).

Usage:
    uv run python infra/scripts/gen_mcp_reference.py

Chained into `make docs-build` via the `docs-mcp` target, so the reference
never drifts from the actual server.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from dhis2w_mcp.server import build_server
from fastmcp import Client
from mcp.types import Tool

_OUTPUT_PATH = Path(__file__).resolve().parents[2] / "docs" / "mcp-reference.md"


def _plugin_key(tool_name: str) -> str:
    """Group by the first underscore segment — `metadata_list` -> `metadata`."""
    return tool_name.split("_", 1)[0]


def _type_label(schema: Any) -> str:
    """Render a JSON-schema property type as a short markdown string."""
    if not isinstance(schema, dict):
        return "-"
    any_of = schema.get("anyOf") or schema.get("oneOf")
    if isinstance(any_of, list):
        parts = [_type_label(branch) for branch in any_of]
        return " \\| ".join(p for p in parts if p != "null")
    if schema.get("type") == "array":
        items = schema.get("items") or {}
        return f"list[{_type_label(items)}]"
    if schema.get("type") == "object":
        return "object"
    t = schema.get("type")
    if isinstance(t, list):
        return " \\| ".join(x for x in t if x != "null")
    if isinstance(t, str):
        return t
    if "$ref" in schema:
        ref = schema["$ref"]
        if isinstance(ref, str):
            return ref.rsplit("/", 1)[-1]
    return "-"


def _render_tool(tool: Tool) -> str:
    """Render one tool as a markdown section — heading + description + parameter table."""
    input_schema = tool.input_schema or {}
    properties: dict[str, Any] = input_schema.get("properties") or {}
    required: set[str] = set(input_schema.get("required") or [])

    lines: list[str] = []
    lines.append(f"### `{tool.name}`")
    lines.append("")
    if tool.description:
        # Keep the first paragraph only; FastMCP tool descriptions can be long.
        first_block = tool.description.strip().split("\n\n", 1)[0]
        lines.append(first_block)
        lines.append("")
    if properties:
        lines.append("| Parameter | Type | Required | Description |")
        lines.append("| --- | --- | --- | --- |")
        for prop_name, prop_schema in properties.items():
            desc = (prop_schema.get("description") or "").replace("\n", " ").strip()
            desc = desc.replace("|", "\\|")
            desc = desc or "—"
            req = "yes" if prop_name in required else "no"
            type_label = _type_label(prop_schema)
            lines.append(f"| `{prop_name}` | `{type_label}` | {req} | {desc} |")
        lines.append("")
    else:
        lines.append("No parameters.")
        lines.append("")
    return "\n".join(lines)


async def main() -> None:
    """Connect to the in-process server, list tools, write the markdown file."""
    async with Client(build_server()) as client:
        tools = await client.list_tools()

    grouped: dict[str, list[Tool]] = {}
    for tool in tools:
        grouped.setdefault(_plugin_key(tool.name), []).append(tool)

    sections: list[str] = []
    sections.append("# MCP reference\n")
    sections.append(
        "Every tool exposed by the `dhis2` FastMCP server, grouped by plugin. "
        "Auto-generated from the in-process server — do not edit by hand. "
        "Rebuild via `make docs-mcp` (chained into `make docs-build`).\n"
    )
    sections.append(f"**Total tools**: {len(tools)} across {len(grouped)} plugin groups.\n")
    sections.append("## Plugins\n")
    for key in sorted(grouped):
        tool_count = len(grouped[key])
        anchor = key.lower()
        sections.append(f"- [`{key}_*`](#{anchor}) — {tool_count} tool{'s' if tool_count != 1 else ''}")
    sections.append("")

    for key in sorted(grouped):
        sections.append(f"## `{key}`\n")
        for tool in sorted(grouped[key], key=lambda t: t.name):
            sections.append(_render_tool(tool))

    _OUTPUT_PATH.write_text("\n".join(sections) + "\n", encoding="utf-8")
    print(f"wrote {_OUTPUT_PATH.relative_to(Path.cwd())} ({len(tools)} tools, {len(grouped)} groups)")


if __name__ == "__main__":
    asyncio.run(main())
