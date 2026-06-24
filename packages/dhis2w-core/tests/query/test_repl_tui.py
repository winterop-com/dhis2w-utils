"""Textual REPL tests: Enter runs the program; Ctrl+J inserts a newline instead of submitting."""

from __future__ import annotations

import pytest

pytest.importorskip("textual")

from dhis2w_core.tui.repl import D2qlReplApp, _ProgramArea  # noqa: E402 — after importorskip
from dhis2w_ql import QueryResult  # noqa: E402


def _result(rows: list[dict[str, str]], format: str | None = None) -> QueryResult:
    return QueryResult(rows=rows, count=len(rows), scalar=False, format=format)


async def test_enter_runs_the_program() -> None:
    calls: list[str] = []

    async def fake(program: str) -> QueryResult:
        calls.append(program)
        return _result([{"id": "a1", "name": "ANC"}])

    app = D2qlReplApp(run_program=fake, title="test")
    async with app.run_test() as pilot:
        area = app.query_one("#program", _ProgramArea)
        area.text = "dataElements | limit 1"
        await pilot.press("enter")
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert area.text == ""  # editor cleared after submit
    assert calls == ["dataElements | limit 1"]


async def test_up_arrow_recalls_history_at_top_line() -> None:
    async def fake(program: str) -> QueryResult:
        return _result([])

    app = D2qlReplApp(run_program=fake, title="test")
    async with app.run_test() as pilot:
        area = app.query_one("#program", _ProgramArea)
        area.text = "dataElements | count"
        await pilot.press("enter")
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert area.text == ""  # cleared; cursor on the (only) line
        await pilot.press("up")  # at the top line → recall previous program
        await pilot.pause()
        assert area.text == "dataElements | count"


def test_explicit_sink_format_renders_as_text() -> None:
    # A result carrying a sink format (e.g. `>> ndjson`) renders serialized, not as a table.
    from dhis2w_core.tui.render import build_result_renderable
    from rich.text import Text

    renderable = build_result_renderable(_result([{"id": "a1"}, {"id": "b2"}], format="ndjson"))
    assert isinstance(renderable, Text)
    assert renderable.plain == '{"id": "a1"}\n{"id": "b2"}'


async def test_ctrl_f_cycles_the_default_output_format() -> None:
    async def fake(program: str) -> QueryResult:
        return _result([])

    app = D2qlReplApp(run_program=fake, title="test")
    async with app.run_test() as pilot:
        assert app._default_format is None
        await pilot.press("ctrl+f")
        await pilot.pause()
        assert app._default_format == "json"
        await pilot.press("ctrl+f")
        await pilot.pause()
        assert app._default_format == "ndjson"


async def test_ctrl_t_toggles_the_json_tree_view() -> None:
    from dhis2w_core.tui.json_tree import JSONTree
    from textual.widgets import RichLog

    async def fake(program: str) -> QueryResult:
        return _result([{"id": "a1", "name": "ANC"}, {"id": "b2", "name": "BCG"}])

    app = D2qlReplApp(run_program=fake, title="test")
    async with app.run_test() as pilot:
        app.query_one("#program", _ProgramArea).text = "dataElements | limit 2"
        await pilot.press("enter")
        await app.workers.wait_for_complete()
        await pilot.pause()
        tree = app.query_one("#tree", JSONTree)
        log = app.query_one("#results", RichLog)
        await pilot.press("ctrl+t")  # enter tree mode; the latest result populates the tree
        await pilot.pause()
        assert tree.display is True and log.display is False
        assert len(tree.root.children) == 2  # one node per result row
        assert app.focused is tree  # tree mode focuses the tree so you can navigate immediately
        await pilot.press("ctrl+t")  # back to the log
        await pilot.pause()
        assert tree.display is False and log.display is True
        assert app.focused is app.query_one("#program", _ProgramArea)  # focus returns to the editor


async def test_tree_mode_renders_new_results_into_the_tree() -> None:
    # In tree mode, running a query shows the result as a tree (no JSON in the log first).
    from dhis2w_core.tui.json_tree import JSONTree

    async def fake(program: str) -> QueryResult:
        return _result([{"id": "a1"}, {"id": "b2"}, {"id": "c3"}])

    app = D2qlReplApp(run_program=fake, title="test")
    async with app.run_test() as pilot:
        await pilot.press("ctrl+t")  # enter tree mode (focuses the tree)
        await pilot.pause()
        editor = app.query_one("#program", _ProgramArea)
        editor.focus()  # Tab back to the editor to run a query
        editor.text = "dataElements | limit 3"
        await pilot.press("enter")
        await app.workers.wait_for_complete()
        await pilot.pause()
        tree = app.query_one("#tree", JSONTree)
        assert tree.display is True
        assert len(tree.root.children) == 3


async def test_ctrl_j_inserts_newline_and_does_not_run() -> None:
    calls: list[str] = []

    async def fake(program: str) -> QueryResult:
        calls.append(program)
        return _result([])

    app = D2qlReplApp(run_program=fake, title="test")
    async with app.run_test() as pilot:
        area = app.query_one("#program", _ProgramArea)
        area.text = "dataElements"
        await pilot.press("ctrl+j")
        await pilot.pause()
        assert "\n" in area.text
    assert calls == []  # newline chord must not submit
