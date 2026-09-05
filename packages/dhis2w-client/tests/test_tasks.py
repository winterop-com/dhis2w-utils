"""Tests for `TaskModule.await_completion` + `iter_notifications` + `parse_task_ref`."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
import pytest
import respx
from dhis2w_client import BasicAuth, Dhis2Client, TaskTimeoutError, parse_task_ref
from dhis2w_client.v42.tasks import TaskCompletion


def test_parse_task_ref_tuple_passthrough() -> None:
    """Tuples return unchanged."""
    assert parse_task_ref(("ANALYTICS_TABLE", "xYz")) == ("ANALYTICS_TABLE", "xYz")


def test_parse_task_ref_string_splits_on_last_slash() -> None:
    """`JOB_TYPE/uid` strings split into a tuple."""
    assert parse_task_ref("METADATA_IMPORT/abc123") == ("METADATA_IMPORT", "abc123")
    # Extra slashes in a hypothetical jobType survive via rpartition.
    assert parse_task_ref("FOO/BAR/xyz") == ("FOO/BAR", "xyz")


def test_parse_task_ref_rejects_malformed() -> None:
    """Strings without a slash or empty halves are rejected."""
    with pytest.raises(ValueError, match="JOB_TYPE"):
        parse_task_ref("nosep")
    with pytest.raises(ValueError, match="JOB_TYPE"):
        parse_task_ref("/xyz")


def _mock_connect_preamble() -> None:
    """Stub the canonical-URL + /api/system/info probes `Dhis2Client.connect()` performs."""
    respx.get("https://dhis2.example/").mock(return_value=httpx.Response(200, text="ok"))
    respx.get("https://dhis2.example/api/system/info").mock(
        return_value=httpx.Response(200, json={"version": "2.42.4"}),
    )


def _notifications(entries: list[dict[str, Any]]) -> httpx.Response:
    """Build a `/api/system/tasks/...` response. DHIS2 returns newest-first."""
    return httpx.Response(200, json=list(reversed(entries)))


@respx.mock
async def test_await_completion_returns_final_notification(monkeypatch: pytest.MonkeyPatch) -> None:
    """First poll: two in-progress rows; second poll adds a completed row. Helper returns TaskCompletion."""

    async def _instant_sleep(_: float) -> None:
        return None

    monkeypatch.setattr("dhis2w_client.v42.tasks.asyncio.sleep", _instant_sleep)
    _mock_connect_preamble()

    route = respx.get("https://dhis2.example/api/system/tasks/ANALYTICS_TABLE/uid123").mock(
        side_effect=[
            _notifications(
                [
                    {
                        "uid": "n1",
                        "time": "2026-04-20T12:00:01",
                        "level": "INFO",
                        "message": "starting",
                        "completed": False,
                    },
                    {
                        "uid": "n2",
                        "time": "2026-04-20T12:00:02",
                        "level": "INFO",
                        "message": "halfway",
                        "completed": False,
                    },
                ]
            ),
            _notifications(
                [
                    {
                        "uid": "n1",
                        "time": "2026-04-20T12:00:01",
                        "level": "INFO",
                        "message": "starting",
                        "completed": False,
                    },
                    {
                        "uid": "n2",
                        "time": "2026-04-20T12:00:02",
                        "level": "INFO",
                        "message": "halfway",
                        "completed": False,
                    },
                    {
                        "uid": "n3",
                        "time": "2026-04-20T12:00:03",
                        "level": "INFO",
                        "message": "all done",
                        "completed": True,
                    },
                ]
            ),
        ]
    )

    client = Dhis2Client("https://dhis2.example", auth=BasicAuth(username="a", password="b"))
    try:
        await client.connect()
        completion = await client.tasks.await_completion(
            ("ANALYTICS_TABLE", "uid123"),
            poll_interval=0.0,
        )
    finally:
        await client.close()

    assert isinstance(completion, TaskCompletion)
    assert completion.job_type == "ANALYTICS_TABLE"
    assert completion.task_uid == "uid123"
    assert [n.uid for n in completion.notifications] == ["n1", "n2", "n3"]
    assert completion.final.completed is True
    assert completion.message == "all done"
    assert completion.level == "INFO"
    assert route.call_count == 2  # one in-progress poll, one that saw the completion


@respx.mock
async def test_await_completion_dedupes_notifications_across_polls(monkeypatch: pytest.MonkeyPatch) -> None:
    """The same notification UIDs showing up in every poll aren't yielded twice."""

    async def _instant_sleep(_: float) -> None:
        return None

    monkeypatch.setattr("dhis2w_client.v42.tasks.asyncio.sleep", _instant_sleep)
    _mock_connect_preamble()

    respx.get("https://dhis2.example/api/system/tasks/METADATA_IMPORT/xyz").mock(
        side_effect=[
            _notifications([{"uid": "n1", "level": "INFO", "message": "one", "completed": False}]),
            _notifications(
                [
                    {"uid": "n1", "level": "INFO", "message": "one", "completed": False},
                    {"uid": "n2", "level": "INFO", "message": "two", "completed": True},
                ]
            ),
        ]
    )

    client = Dhis2Client("https://dhis2.example", auth=BasicAuth(username="a", password="b"))
    try:
        await client.connect()
        completion = await client.tasks.await_completion("METADATA_IMPORT/xyz", poll_interval=0.0)
    finally:
        await client.close()

    # n1 appeared in both poll results but was only yielded once.
    assert [n.uid for n in completion.notifications] == ["n1", "n2"]


@respx.mock
async def test_await_completion_times_out(monkeypatch: pytest.MonkeyPatch) -> None:
    """When no completion arrives before `timeout`, raises `TaskTimeoutError`."""

    async def _instant_sleep(_: float) -> None:
        return None

    # Advance a monotonic clock so the deadline check actually fires.
    now = [0.0]

    def fake_time() -> float:
        now[0] += 0.5
        return now[0]

    class _FakeLoop:
        def time(self) -> float:
            return fake_time()

    monkeypatch.setattr("dhis2w_client.v42.tasks.asyncio.sleep", _instant_sleep)
    monkeypatch.setattr("dhis2w_client.v42.tasks.asyncio.get_event_loop", lambda: _FakeLoop())
    _mock_connect_preamble()

    respx.get("https://dhis2.example/api/system/tasks/ANALYTICS_TABLE/stuck").mock(
        return_value=_notifications([{"uid": "n1", "level": "INFO", "message": "running", "completed": False}]),
    )

    client = Dhis2Client("https://dhis2.example", auth=BasicAuth(username="a", password="b"))
    try:
        await client.connect()
        with pytest.raises(TaskTimeoutError, match="ANALYTICS_TABLE/stuck"):
            await client.tasks.await_completion(
                ("ANALYTICS_TABLE", "stuck"),
                timeout=1.0,
                poll_interval=0.0,
            )
    finally:
        await client.close()


@respx.mock
async def test_iter_notifications_yields_chronologically(monkeypatch: pytest.MonkeyPatch) -> None:
    """Raw iterator path — yields DHIS2's entries oldest-first and stops on completed."""

    async def _instant_sleep(_: float) -> None:
        return None

    monkeypatch.setattr("dhis2w_client.v42.tasks.asyncio.sleep", _instant_sleep)
    _mock_connect_preamble()

    respx.get("https://dhis2.example/api/system/tasks/FOO/bar").mock(
        return_value=_notifications(
            [
                {"uid": "old", "level": "INFO", "message": "earliest", "completed": False},
                {"uid": "mid", "level": "INFO", "message": "middle", "completed": False},
                {"uid": "new", "level": "INFO", "message": "done", "completed": True},
            ]
        ),
    )

    client = Dhis2Client("https://dhis2.example", auth=BasicAuth(username="a", password="b"))
    try:
        await client.connect()
        yielded: list[str] = []
        async for n in client.tasks.iter_notifications("FOO/bar", poll_interval=0.0):
            yielded.append(n.uid or "")
    finally:
        await client.close()

    assert yielded == ["old", "mid", "new"]  # chronological, stopped on completed=True


@respx.mock
async def test_await_completion_unwraps_get_raw_data_wrapper(monkeypatch: pytest.MonkeyPatch) -> None:
    """`get_raw` wraps top-level JSON arrays under `{"data": [...]}`; the awaiter must unwrap."""

    async def _instant_sleep(_: float) -> None:
        return None

    monkeypatch.setattr("dhis2w_client.v42.tasks.asyncio.sleep", _instant_sleep)
    _mock_connect_preamble()

    # DHIS2 returns a bare array at this endpoint — `_parse_json` will wrap it.
    respx.get("https://dhis2.example/api/system/tasks/FOO/unwrap").mock(
        return_value=httpx.Response(
            200,
            json=[{"uid": "only", "level": "INFO", "message": "done", "completed": True}],
        )
    )

    client = Dhis2Client("https://dhis2.example", auth=BasicAuth(username="a", password="b"))
    try:
        await client.connect()
        completion = await client.tasks.await_completion("FOO/unwrap", poll_interval=0.0)
    finally:
        await client.close()

    assert completion.final.uid == "only"
    assert completion.final.message == "done"


@respx.mock
async def test_poll_once_returns_only_rows_new_since_cursor(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """A second `poll_once`, passed the first poll's cursor, returns only rows added since."""
    mock_system_info(server_version)
    respx.get("https://dhis2.example/api/system/tasks/ANALYTICS_TABLE/uid1").mock(
        side_effect=[
            _notifications(
                [
                    {"uid": "n1", "level": "INFO", "message": "one", "completed": False},
                    {"uid": "n2", "level": "INFO", "message": "two", "completed": False},
                ]
            ),
            _notifications(
                [
                    {"uid": "n1", "level": "INFO", "message": "one", "completed": False},
                    {"uid": "n2", "level": "INFO", "message": "two", "completed": False},
                    {"uid": "n3", "level": "INFO", "message": "three", "completed": False},
                ]
            ),
        ]
    )

    client = Dhis2Client("https://dhis2.example", auth=BasicAuth(username="a", password="b"))
    try:
        await client.connect()
        first = await client.tasks.poll_once(("ANALYTICS_TABLE", "uid1"))
        second = await client.tasks.poll_once(("ANALYTICS_TABLE", "uid1"), cursor=first.cursor)
    finally:
        await client.close()

    assert [n.uid for n in first.new] == ["n1", "n2"]  # chronological, oldest-first
    assert first.completed is False
    assert first.cursor == frozenset({"n1", "n2"})
    assert [n.uid for n in second.new] == ["n3"]  # only the newly-arrived row
    assert second.completed is False
    assert second.cursor == frozenset({"n1", "n2", "n3"})
    assert second.relative_notifier_endpoint == "/api/system/tasks/ANALYTICS_TABLE/uid1"


@respx.mock
async def test_poll_once_detects_completion_and_truncates(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """A `completed=True` row sets `completed` and ends `new` — a single poll sees the terminal row."""
    mock_system_info(server_version)
    respx.get("https://dhis2.example/api/system/tasks/METADATA_IMPORT/done").mock(
        return_value=_notifications(
            [
                {"uid": "a", "level": "INFO", "message": "start", "completed": False},
                {"uid": "b", "level": "INFO", "message": "finished", "completed": True},
            ]
        ),
    )

    client = Dhis2Client("https://dhis2.example", auth=BasicAuth(username="a", password="b"))
    try:
        await client.connect()
        poll = await client.tasks.poll_once("METADATA_IMPORT/done")
    finally:
        await client.close()

    assert poll.completed is True
    assert [n.uid for n in poll.new] == ["a", "b"]
    assert poll.new[-1].completed is True


@respx.mock
async def test_poll_once_empty_feed_returns_nothing(server_version: str, mock_system_info: Callable[..., None]) -> None:
    """An empty notification feed yields no rows, no completion, and an empty cursor."""
    mock_system_info(server_version)
    respx.get("https://dhis2.example/api/system/tasks/ANALYTICS_TABLE/fresh").mock(
        return_value=httpx.Response(200, json=[]),
    )

    client = Dhis2Client("https://dhis2.example", auth=BasicAuth(username="a", password="b"))
    try:
        await client.connect()
        poll = await client.tasks.poll_once(("ANALYTICS_TABLE", "fresh"))
    finally:
        await client.close()

    assert poll.new == []
    assert poll.completed is False
    assert poll.cursor == frozenset()
