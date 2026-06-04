"""Verify `dhis2 metadata list --count` returns the DHIS2 pager total via accessor.list_raw()."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from dhis2w_cli.main import build_app
from typer.testing import CliRunner


class _CountingAccessor:
    """Recording mock whose list_raw() returns a DHIS2 response with a pager block."""

    def __init__(self, total: int = 220) -> None:
        self.calls: list[dict[str, Any]] = []
        self._total = total

    async def list_raw(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        return {"pager": {"page": 1, "pageSize": 1, "total": self._total}, "dataElements": [{"id": "x"}]}


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Install a raw-env profile so the CLI resolves without touching TOML."""
    monkeypatch.delenv("DHIS2_PROFILE", raising=False)
    monkeypatch.setenv("DHIS2_URL", "http://mock.example")
    monkeypatch.setenv("DHIS2_PAT", "test-token")


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


_GLOBAL_FLAGS = {"--json", "-j", "--debug", "-d"}


def _invoke(runner: CliRunner, accessor: _CountingAccessor, args: list[str]) -> Any:
    """Invoke `dhis2 metadata list dataElements ...` with the fake accessor injected."""
    fake_resources = MagicMock()
    fake_resources.data_elements = accessor
    fake_client = MagicMock(resources=fake_resources)

    ctx = AsyncMock()
    ctx.__aenter__.return_value = fake_client
    ctx.__aexit__.return_value = None

    head = [a for a in args if a in _GLOBAL_FLAGS]
    tail = [a for a in args if a not in _GLOBAL_FLAGS]
    with patch("dhis2w_core.v42.plugins.metadata.service.open_client", lambda _profile: ctx):
        return runner.invoke(build_app(), [*head, "metadata", "list", "dataElements", *tail])


def test_count_json_returns_pager_total(runner: CliRunner) -> None:
    """--count --json emits {resource, total} and queries a single id-only page."""
    accessor = _CountingAccessor(total=220)
    result = _invoke(runner, accessor, ["--json", "--count"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == {"resource": "dataElements", "total": 220}
    call = accessor.calls[-1]
    assert call["page_size"] == 1
    assert call["paging"] is True
    assert call["fields"] == "id"


def test_count_human_output(runner: CliRunner) -> None:
    """--count without --json prints a one-line `<resource>: <total>`."""
    accessor = _CountingAccessor(total=7)
    result = _invoke(runner, accessor, ["--count"])
    assert result.exit_code == 0, result.output
    assert "dataElements: 7" in result.output


def test_count_forwards_filters(runner: CliRunner) -> None:
    """--count narrows the total via --filter, same as a listing."""
    accessor = _CountingAccessor()
    result = _invoke(runner, accessor, ["--json", "--count", "--filter", "domainType:eq:AGGREGATE"])
    assert result.exit_code == 0, result.output
    assert accessor.calls[-1]["filters"] == ["domainType:eq:AGGREGATE"]
