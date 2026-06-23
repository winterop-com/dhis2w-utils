"""Rich renderables for d2ql query results, shared by the CLI table output and the Textual REPL."""

from __future__ import annotations

import json
from typing import Any

from dhis2w_ql import to_jsonable
from rich.console import RenderableType
from rich.table import Table
from rich.text import Text


def _cell(value: Any) -> str:
    """Format one table cell; nested objects/arrays become JSON text (CSV-style)."""
    if value is None:
        return "-"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def build_result_table(rows: list[dict[str, Any]]) -> Table:
    """Build a rich Table from object rows; columns are the union of keys in first-seen order."""
    columns: list[str] = []
    for row in rows:
        for key in row:
            if key not in columns:
                columns.append(key)
    table = Table(title=f"{len(rows)} row(s)", pad_edge=False)
    for column in columns:
        table.add_column(column, overflow="fold")
    for row in rows:
        table.add_row(*[_cell(row.get(column)) for column in columns])
    return table


def build_result_renderable(result: Any) -> RenderableType:
    """Render a `QueryResult` as a table (object rows), JSON (other rows), or a written-to note."""
    if result.written_to is not None:
        return Text(f"wrote {result.count} row(s) to {result.written_to}", style="green")
    if result.scalar:
        value = to_jsonable(result.rows[0]) if result.rows else None
        return Text(json.dumps(value, ensure_ascii=False))
    payload = [to_jsonable(row) for row in result.rows]
    if payload and all(isinstance(item, dict) for item in payload):
        return build_result_table(payload)
    return Text(json.dumps(payload, indent=2, ensure_ascii=False))
