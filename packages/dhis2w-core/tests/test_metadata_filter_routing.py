"""Verify `d2w metadata list` flags reach `accessor.list()` with the right kwargs."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from dhis2w_cli.main import build_app
from typer.testing import CliRunner


class _FakeAccessor:
    """Recording mock of a generated resource accessor."""

    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self._rows = rows or [{"id": "x", "name": "X"}]

    async def list(self, **kwargs: Any) -> list[Any]:
        self.calls.append(kwargs)
        dumped_models = [MagicMock(**row) for row in self._rows]
        # Each mock .model_dump returns the dict, mimicking pydantic.
        for model, row in zip(dumped_models, self._rows, strict=True):
            model.model_dump = MagicMock(return_value=row)
        return dumped_models


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Install a raw-env profile so `profile_from_env()` resolves without touching TOML."""
    monkeypatch.delenv("DHIS2_PROFILE", raising=False)
    monkeypatch.setenv("DHIS2_URL", "http://mock.example")
    monkeypatch.setenv("DHIS2_PAT", "test-token")


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


_GLOBAL_FLAGS = {"--json", "-j", "--debug", "-d"}


def _invoke(
    runner: CliRunner,
    accessor: _FakeAccessor,
    args: list[str],
) -> Any:
    """Invoke `d2w metadata list ...` with the fake accessor injected.

    Pulls any global flags (`--json`, `--debug`) out of `args` and prepends
    them — Typer requires root-callback options before the subcommand chain.
    """
    fake_resources = MagicMock()
    fake_resources.data_elements = accessor
    fake_client = MagicMock(resources=fake_resources)

    ctx = AsyncMock()
    ctx.__aenter__.return_value = fake_client
    ctx.__aexit__.return_value = None

    def _open_client(_profile: Any) -> Any:
        return ctx

    head = [a for a in args if a in _GLOBAL_FLAGS]
    tail = [a for a in args if a not in _GLOBAL_FLAGS]
    with patch("dhis2w_core.v42.plugins.metadata.service.open_client", _open_client):
        return runner.invoke(build_app(), [*head, "metadata", "list", "dataElements", *tail])


def test_single_filter_forwards_as_list(runner: CliRunner) -> None:
    """Single filter forwards as list."""
    accessor = _FakeAccessor()
    result = _invoke(runner, accessor, ["--filter", "name:like:Malaria", "--fields", "id,name"])
    assert result.exit_code == 0, result.output
    call = accessor.calls[-1]
    assert call["filters"] == ["name:like:Malaria"]
    # rootJunction omitted when there's only one filter (DHIS2 default = AND).
    assert call["root_junction"] is None


def test_multi_filter_routes_root_junction_or(runner: CliRunner) -> None:
    """Multi filter routes root junction or."""
    accessor = _FakeAccessor()
    result = _invoke(
        runner,
        accessor,
        [
            "--filter",
            "name:like:ANC",
            "--filter",
            "code:eq:DEancVisit1",
            "--root-junction",
            "OR",
        ],
    )
    assert result.exit_code == 0, result.output
    call = accessor.calls[-1]
    assert call["filters"] == ["name:like:ANC", "code:eq:DEancVisit1"]
    assert call["root_junction"] == "OR"


def test_order_repeatable(runner: CliRunner) -> None:
    """Order repeatable."""
    accessor = _FakeAccessor()
    result = _invoke(runner, accessor, ["--order", "level:asc", "--order", "name:asc"])
    assert result.exit_code == 0, result.output
    assert accessor.calls[-1]["order"] == ["level:asc", "name:asc"]


def test_page_and_page_size(runner: CliRunner) -> None:
    """Page and page size."""
    accessor = _FakeAccessor()
    result = _invoke(runner, accessor, ["--page", "2", "--page-size", "10"])
    assert result.exit_code == 0, result.output
    call = accessor.calls[-1]
    assert call["page"] == 2
    assert call["page_size"] == 10


def test_translate_and_locale(runner: CliRunner) -> None:
    """Translate and locale."""
    accessor = _FakeAccessor()
    result = _invoke(runner, accessor, ["--translate", "--locale", "fr"])
    assert result.exit_code == 0, result.output
    call = accessor.calls[-1]
    assert call["translate"] is True
    assert call["locale"] == "fr"


def test_all_flag_streams_pages(runner: CliRunner) -> None:
    """--all should walk pages server-side via iter_metadata (paging=True + page=N)."""
    # Serve three pages: 500 rows, 500 rows, 3 rows (less than page_size -> stop).
    pages = [
        [{"id": f"p1-{i}", "name": f"r{i}"} for i in range(500)],
        [{"id": f"p2-{i}", "name": f"r{i}"} for i in range(500)],
        [{"id": "p3-a", "name": "tail"}],
    ]
    accessor = _FakeAccessor()

    call_index = 0

    async def _paged_list(**kwargs: Any) -> list[Any]:
        nonlocal call_index
        accessor.calls.append(kwargs)
        rows = pages[call_index] if call_index < len(pages) else []
        call_index += 1
        models = [MagicMock() for _ in rows]
        for model, row in zip(models, rows, strict=True):
            model.model_dump = MagicMock(return_value=row)
        return models

    accessor.list = _paged_list  # type: ignore[method-assign]

    result = _invoke(runner, accessor, ["--json", "--all"])
    assert result.exit_code == 0, result.output
    # Three list() calls -> page=1, page=2, page=3. All with paging=True.
    assert len(accessor.calls) == 3
    assert [c["page"] for c in accessor.calls] == [1, 2, 3]
    assert all(c["paging"] is True for c in accessor.calls)


def test_defaults_when_no_flags(runner: CliRunner) -> None:
    """With no filter/order/paging flags, the accessor call has them all None."""
    accessor = _FakeAccessor()
    result = _invoke(runner, accessor, [])
    assert result.exit_code == 0, result.output
    call = accessor.calls[-1]
    assert call["filters"] is None
    assert call["root_junction"] is None
    assert call["order"] is None
    assert call["page"] is None
    assert call["page_size"] is None
    assert call["paging"] is None
