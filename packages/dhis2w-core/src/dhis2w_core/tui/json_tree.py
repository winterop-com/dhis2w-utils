"""A Textual Tree that renders a d2ql result as a collapsible JSON tree (json and ndjson alike)."""

from __future__ import annotations

from typing import Any

from dhis2w_ql import to_jsonable
from rich.highlighter import ReprHighlighter
from rich.text import Text
from textual.widgets import Tree
from textual.widgets.tree import TreeNode

_highlighter = ReprHighlighter()


def _add_node(name: str, node: TreeNode[Any], data: Any) -> None:
    """Attach `data` under `node`: dicts label `{} name`, lists `[] name`, scalars `name=<repr>`."""
    if isinstance(data, dict):
        node.set_label(Text(f"{{}} {name}"))
        for key, value in data.items():
            _add_node(str(key), node.add(""), value)
    elif isinstance(data, list):
        node.set_label(Text(f"[] {name}"))
        for index, value in enumerate(data):
            _add_node(str(index), node.add(""), value)
    else:
        node.allow_expand = False
        if name:
            node.set_label(Text.assemble(Text.from_markup(f"[b]{name}[/b]="), _highlighter(repr(data))))
        else:
            node.set_label(Text(repr(data)))


class JSONTree(Tree[Any]):
    """A collapsible tree view of a d2ql result; `show(result)` rebuilds it from the result rows."""

    def show(self, result: Any) -> None:
        """Rebuild the tree from a QueryResult — a scalar value, or the list of object rows."""
        self.clear()
        if result.scalar:
            value: Any = to_jsonable(result.rows[0]) if result.rows else None
        else:
            value = [to_jsonable(row) for row in result.rows]
        _add_node("result", self.root, value)
        self.root.expand()
