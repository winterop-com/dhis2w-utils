"""Textual REPL tests: Enter runs the program; Ctrl+J inserts a newline instead of submitting."""

from __future__ import annotations

import pytest

pytest.importorskip("textual")

from dhis2w_core.tui.repl import D2qlReplApp, _ProgramArea  # noqa: E402 — after importorskip
from dhis2w_ql import QueryResult  # noqa: E402


def _result(rows: list[dict[str, str]]) -> QueryResult:
    return QueryResult(rows=rows, count=len(rows), scalar=False)


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
