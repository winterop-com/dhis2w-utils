"""Verify `dhis2 metadata list --output` writes JSON to a file and prints a summary, not the rows."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from dhis2w_cli.main import build_app
from typer.testing import CliRunner

_GLOBAL_FLAGS = {"--json", "-j", "--debug", "-d"}


class _FakeAccessor:
    """Mock resource accessor whose list() yields models that dump to the given rows."""

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    async def list(self, **_kwargs: Any) -> list[Any]:
        models: list[Any] = []
        for row in self._rows:
            model = MagicMock()
            model.model_dump = MagicMock(return_value=row)
            models.append(model)
        return models


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Install a raw-env profile so the CLI resolves without touching TOML."""
    monkeypatch.delenv("DHIS2_PROFILE", raising=False)
    monkeypatch.setenv("DHIS2_URL", "http://mock.example")
    monkeypatch.setenv("DHIS2_PAT", "test-token")


def _invoke(accessor: _FakeAccessor, args: list[str]) -> Any:
    """Invoke `dhis2 metadata list dataElements ...` with the fake accessor injected."""
    fake_resources = MagicMock()
    fake_resources.data_elements = accessor
    ctx = AsyncMock()
    ctx.__aenter__.return_value = MagicMock(resources=fake_resources)
    ctx.__aexit__.return_value = None
    head = [a for a in args if a in _GLOBAL_FLAGS]
    tail = [a for a in args if a not in _GLOBAL_FLAGS]
    with patch("dhis2w_core.v42.plugins.metadata.service.open_client", lambda _profile: ctx):
        return CliRunner().invoke(build_app(), [*head, "metadata", "list", "dataElements", *tail])


def test_output_writes_file_and_human_summary(tmp_path: Path) -> None:
    """--output writes the rows to disk and prints a one-line summary instead of the rows."""
    out = tmp_path / "de.json"
    rows = [{"id": "a", "name": "A"}, {"id": "b", "name": "B"}]
    result = _invoke(_FakeAccessor(rows), ["--output", str(out)])
    assert result.exit_code == 0, result.output
    assert json.loads(out.read_text(encoding="utf-8")) == rows
    assert "wrote 2 dataElements" in result.output
    assert '"id"' not in result.output  # the rows themselves are not echoed


def test_output_json_summary(tmp_path: Path) -> None:
    """With --json, --output prints the {resource, written, path} summary."""
    out = tmp_path / "de.json"
    result = _invoke(_FakeAccessor([{"id": "a", "name": "A"}]), ["--json", "--output", str(out)])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["resource"] == "dataElements"
    assert payload["written"] == 1
    assert payload["path"].endswith("de.json")
