"""Verify `d2w security authorities` categorises /api/me/authorization output.

Parametrised over the three version trees: `DHIS2_VERSION` selects the
plugin tree `build_app()` mounts, and the matching tree's `open_client`
is patched, so each tree's CLI path is exercised end-to-end in-process.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from dhis2w_cli.main import build_app
from dhis2w_client.errors import Dhis2ClientError
from typer.testing import CliRunner

_AUTHORITIES = ["F_USER_ADD", "F_SQLVIEW_PUBLIC_ADD", "F_DATAVALUE_ADD"]

TREES = ("v41", "v42", "v43")


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Install a raw-env profile so the CLI resolves without touching TOML."""
    monkeypatch.delenv("DHIS2_PROFILE", raising=False)
    monkeypatch.setenv("DHIS2_URL", "http://mock.example")
    monkeypatch.setenv("DHIS2_PAT", "test-token")


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _invoke(
    runner: CliRunner,
    args: list[str],
    payload: Any,
    *,
    tree: str = "v42",
    monkeypatch: pytest.MonkeyPatch | None = None,
) -> Any:
    """Invoke `d2w security authorities ...` against `tree` with a fake client returning `payload`."""
    if monkeypatch is not None:
        monkeypatch.setenv("DHIS2_VERSION", tree)

    fake_client = MagicMock()
    fake_client.get_raw = AsyncMock(return_value=payload)

    ctx = AsyncMock()
    ctx.__aenter__.return_value = fake_client
    ctx.__aexit__.return_value = None

    with patch(f"dhis2w_core.{tree}.plugins.security.service.open_client", lambda _profile: ctx):
        return runner.invoke(build_app(), args)


@pytest.mark.parametrize("tree", TREES)
def test_authorities_json_emits_categorised_summary(
    runner: CliRunner, tree: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`--json security authorities` emits the sorted authorities plus category matches, on every tree."""
    result = _invoke(
        runner, ["--json", "security", "authorities"], {"data": _AUTHORITIES}, tree=tree, monkeypatch=monkeypatch
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["authorities"] == sorted(_AUTHORITIES)
    assert payload["is_superuser"] is False
    assert [match["key"] for match in payload["categories"]] == ["user_management", "sql_views"]
    assert payload["categories"][0]["matched"] == ["F_USER_ADD"]


def test_authorities_json_flags_superuser(runner: CliRunner) -> None:
    """An account holding ALL is reported as superuser."""
    result = _invoke(runner, ["--json", "security", "authorities"], {"data": ["ALL"]})
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["is_superuser"] is True
    assert [match["key"] for match in payload["categories"]] == ["superuser"]


def test_authorities_human_output(runner: CliRunner) -> None:
    """The table view shows the summary counts and the matched category labels."""
    result = _invoke(runner, ["security", "authorities"], {"data": _AUTHORITIES})
    assert result.exit_code == 0, result.output
    assert "security authorities" in result.output
    assert "User & role management" in result.output
    assert "SQL views" in result.output


def test_authorities_human_output_without_categories(runner: CliRunner) -> None:
    """An account with only harmless authorities renders the summary and no category table."""
    result = _invoke(runner, ["security", "authorities"], {"data": ["F_DATAVALUE_ADD"]})
    assert result.exit_code == 0, result.output
    assert "security authorities" in result.output
    assert "risk categories" in result.output
    assert "User & role management" not in result.output


@pytest.mark.parametrize("tree", TREES)
def test_authorities_unexpected_payload_shape_fails_loud(
    runner: CliRunner, tree: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A non-list payload raises instead of reporting a reassuring empty result."""
    result = _invoke(
        runner, ["--json", "security", "authorities"], {"unexpected": "shape"}, tree=tree, monkeypatch=monkeypatch
    )
    assert result.exit_code != 0
    assert isinstance(result.exception, Dhis2ClientError)
