"""Verify `d2w security authorities` categorises /api/me/authorization output."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from dhis2w_cli.main import build_app
from typer.testing import CliRunner

_AUTHORITIES = ["F_USER_ADD", "F_SQLVIEW_EXECUTE", "F_DATAVALUE_ADD"]


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Install a raw-env profile so the CLI resolves without touching TOML."""
    monkeypatch.delenv("DHIS2_PROFILE", raising=False)
    monkeypatch.setenv("DHIS2_URL", "http://mock.example")
    monkeypatch.setenv("DHIS2_PAT", "test-token")


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _invoke(runner: CliRunner, args: list[str], authorities: list[str]) -> Any:
    """Invoke `d2w security authorities ...` with a fake client returning `authorities`."""
    fake_client = MagicMock()
    fake_client.get_raw = AsyncMock(return_value={"data": authorities})

    ctx = AsyncMock()
    ctx.__aenter__.return_value = fake_client
    ctx.__aexit__.return_value = None

    with patch("dhis2w_core.v42.plugins.security.service.open_client", lambda _profile: ctx):
        return runner.invoke(build_app(), args)


def test_authorities_json_emits_categorised_summary(runner: CliRunner) -> None:
    """`--json security authorities` emits the sorted authorities plus category matches."""
    result = _invoke(runner, ["--json", "security", "authorities"], _AUTHORITIES)
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["authorities"] == sorted(_AUTHORITIES)
    assert payload["is_superuser"] is False
    assert [match["key"] for match in payload["categories"]] == ["user_management", "sql_views"]
    assert payload["categories"][0]["matched"] == ["F_USER_ADD"]


def test_authorities_json_flags_superuser(runner: CliRunner) -> None:
    """An account holding ALL is reported as superuser."""
    result = _invoke(runner, ["--json", "security", "authorities"], ["ALL"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["is_superuser"] is True
    assert [match["key"] for match in payload["categories"]] == ["superuser"]


def test_authorities_human_output(runner: CliRunner) -> None:
    """The table view shows the summary counts and the matched category labels."""
    result = _invoke(runner, ["security", "authorities"], _AUTHORITIES)
    assert result.exit_code == 0, result.output
    assert "security authorities" in result.output
    assert "User & role management" in result.output
    assert "SQL views" in result.output


def test_authorities_human_output_without_categories(runner: CliRunner) -> None:
    """An account with only harmless authorities renders the summary and no category table."""
    result = _invoke(runner, ["security", "authorities"], ["F_DATAVALUE_ADD"])
    assert result.exit_code == 0, result.output
    assert "security authorities" in result.output
    assert "risk categories" in result.output
    assert "User & role management" not in result.output
