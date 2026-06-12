"""CliRunner tests for `d2w datastore` (namespaces / keys / get / set / delete)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from dhis2w_cli.main import build_app
from typer.testing import CliRunner

_runner = CliRunner()


@pytest.fixture
def pat_profile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Write a global profiles.toml with one PAT profile and point resolution at it."""
    config_dir = tmp_path / ".config" / "dhis2"
    config_dir.mkdir(parents=True)
    (config_dir / "profiles.toml").write_text(
        """
default = "probe"

[profiles.probe]
base_url = "https://dhis2.example"
auth = "pat"
token = "d2p_test"
"""
    )
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_dir.parent))
    monkeypatch.delenv("DHIS2_PROFILE", raising=False)
    monkeypatch.chdir(tmp_path)


def test_namespaces_lists_one_per_line(pat_profile: None) -> None:  # noqa: ARG001
    """`d2w datastore namespaces` prints each namespace from the service."""
    mock = AsyncMock(return_value=["capture", "analytics"])
    with patch("dhis2w_core.v42.plugins.datastore.service.list_namespaces", new=mock):
        result = _runner.invoke(build_app(), ["datastore", "namespaces"])
    assert result.exit_code == 0, result.output
    assert "capture" in result.output
    assert "analytics" in result.output


def test_get_prints_json_value(pat_profile: None) -> None:  # noqa: ARG001
    """`d2w datastore get NS KEY` prints the value as JSON."""
    mock = AsyncMock(return_value={"dataItems": ["abc"], "enabled": True})
    with patch("dhis2w_core.v42.plugins.datastore.service.get_value", new=mock):
        result = _runner.invoke(build_app(), ["datastore", "get", "ORG_UNIT_PROFILE", "ORG_UNIT_PROFILE"])
    assert result.exit_code == 0, result.output
    assert '"dataItems"' in result.output
    assert "abc" in result.output


def test_set_parses_json_value(pat_profile: None) -> None:  # noqa: ARG001
    """`d2w datastore set NS KEY VALUE` parses VALUE as JSON before storing."""
    mock = AsyncMock(return_value=None)
    with patch("dhis2w_core.v42.plugins.datastore.service.set_value", new=mock):
        result = _runner.invoke(build_app(), ["datastore", "set", "ns", "k", '{"a": 1}'])
    assert result.exit_code == 0, result.output
    assert "set ns/k" in result.output
    assert mock.await_args is not None
    assert mock.await_args.args[3] == {"a": 1}


def test_set_falls_back_to_string(pat_profile: None) -> None:  # noqa: ARG001
    """A non-JSON VALUE is stored as a plain string."""
    mock = AsyncMock(return_value=None)
    with patch("dhis2w_core.v42.plugins.datastore.service.set_value", new=mock):
        result = _runner.invoke(build_app(), ["datastore", "set", "ns", "k", "hello"])
    assert result.exit_code == 0, result.output
    assert mock.await_args is not None
    assert mock.await_args.args[3] == "hello"


def test_delete_requires_confirmation(pat_profile: None) -> None:  # noqa: ARG001
    """`d2w datastore delete` aborts without --yes when the prompt is declined."""
    mock = AsyncMock(return_value=None)
    with patch("dhis2w_core.v42.plugins.datastore.service.delete_key", new=mock):
        result = _runner.invoke(build_app(), ["datastore", "delete", "ns", "k"], input="n\n")
    assert result.exit_code != 0
    assert not mock.await_args  # service never called


def test_delete_with_yes_calls_service(pat_profile: None) -> None:  # noqa: ARG001
    """`d2w datastore delete --yes` skips the prompt and deletes."""
    mock = AsyncMock(return_value=None)
    with patch("dhis2w_core.v42.plugins.datastore.service.delete_key", new=mock):
        result = _runner.invoke(build_app(), ["datastore", "delete", "ns", "k", "--yes"])
    assert result.exit_code == 0, result.output
    assert "deleted ns/k" in result.output
