"""Tests for `d2w profile login --no-browser` + DHIS2_OAUTH_NO_BROWSER env var."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from dhis2w_cli.main import build_app
from dhis2w_core.v42.plugins.profile import cli as profile_cli
from typer.testing import CliRunner


@pytest.fixture(autouse=True)
def _isolated_tomls(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Pin profile TOMLs into tmp_path so tests don't touch the user's real config."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.chdir(tmp_path)
    yield


def _write_oauth2_profile(tmp_path: Path, name: str = "example_oidc") -> None:
    """Drop a minimal oauth2 profile into the global TOML."""
    toml_dir = tmp_path / "xdg" / "dhis2"
    toml_dir.mkdir(parents=True, exist_ok=True)
    (toml_dir / "profiles.toml").write_text(
        'default = "'
        + name
        + '"\n\n'
        + f"[profiles.{name}]\n"
        + 'base_url = "https://dhis2.example"\n'
        + 'auth = "oauth2"\n'
        + 'client_id = "abc"\n'
        + 'client_secret = "xyz"\n'
        + 'scope = "ALL"\n'
        + 'redirect_uri = "http://localhost:8765"\n',
        encoding="utf-8",
    )


class _StubAuth:
    """Stand-in AuthProvider — refresh_if_needed is a no-op so no HTTP happens."""

    async def refresh_if_needed(self) -> None:
        return None


def _stub_build_auth_capture(calls: list[dict[str, Any]]) -> Any:
    """Return a `build_auth` stub that records kwargs and returns a no-op AuthProvider."""

    def _stub(profile: Any, **kwargs: Any) -> _StubAuth:
        calls.append(kwargs)
        return _StubAuth()

    return _stub


def test_login_no_browser_flag_flips_open_browser(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`d2w profile login --no-browser` calls build_auth with open_browser=False."""
    _write_oauth2_profile(tmp_path)
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(profile_cli, "build_auth", _stub_build_auth_capture(calls))
    # Skip preflight (we're not reaching a real DHIS2 here).
    monkeypatch.setattr(profile_cli, "check_oauth2_server", _stub_preflight_ok)
    # Skip the post-login verify round-trip.
    monkeypatch.setattr(profile_cli, "_run_verify", lambda _name: None)

    result = CliRunner().invoke(build_app(), ["profile", "login", "example_oidc", "--no-browser"])
    assert result.exit_code == 0, result.output
    assert len(calls) == 1
    assert calls[0]["open_browser"] is False


def test_login_env_var_flips_open_browser(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`DHIS2_OAUTH_NO_BROWSER=1` flips open_browser without a CLI flag."""
    _write_oauth2_profile(tmp_path)
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(profile_cli, "build_auth", _stub_build_auth_capture(calls))
    monkeypatch.setattr(profile_cli, "check_oauth2_server", _stub_preflight_ok)
    monkeypatch.setattr(profile_cli, "_run_verify", lambda _name: None)
    monkeypatch.setenv("DHIS2_OAUTH_NO_BROWSER", "1")

    result = CliRunner().invoke(build_app(), ["profile", "login", "example_oidc"])
    assert result.exit_code == 0, result.output
    assert calls[0]["open_browser"] is False


def test_login_default_opens_browser(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No flag, no env var → open_browser=True (the existing behaviour)."""
    _write_oauth2_profile(tmp_path)
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(profile_cli, "build_auth", _stub_build_auth_capture(calls))
    monkeypatch.setattr(profile_cli, "check_oauth2_server", _stub_preflight_ok)
    monkeypatch.setattr(profile_cli, "_run_verify", lambda _name: None)
    monkeypatch.delenv("DHIS2_OAUTH_NO_BROWSER", raising=False)

    result = CliRunner().invoke(build_app(), ["profile", "login", "example_oidc"])
    assert result.exit_code == 0, result.output
    assert calls[0]["open_browser"] is True


async def _stub_preflight_ok(_base_url: str) -> str | None:
    """Stand-in for `check_oauth2_server` — always succeeds."""
    return None
