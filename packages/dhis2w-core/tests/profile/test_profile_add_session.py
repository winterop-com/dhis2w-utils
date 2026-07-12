"""Tests for `d2w profile add --auth session` — the Chrome-extension cookie fallback."""

from __future__ import annotations

import importlib
from collections.abc import Iterator
from pathlib import Path

import pytest
from dhis2w_core.profile import load_profiles_file
from dhis2w_core.v41.plugins.profile.cli import app as app_v41
from dhis2w_core.v42.plugins.profile.cli import app as app_v42
from dhis2w_core.v43.plugins.profile.cli import app as app_v43
from typer import Typer
from typer.testing import CliRunner

# One test tree, parametrised over the three version trees — the command is
# identical across them and must behave the same regardless of active tree.
TREES = pytest.mark.parametrize("app", [app_v41, app_v42, app_v43], ids=["v41", "v42", "v43"])


@pytest.fixture(autouse=True)
def _isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Pin TOMLs into tmp_path and strip every env var the resolver + add path consult."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.chdir(tmp_path)
    for key in (
        "DHIS2_PROFILE",
        "DHIS2_URL",
        "DHIS2_PAT",
        "DHIS2_USERNAME",
        "DHIS2_PASSWORD",
        "DHIS2_VERSION",
        "DHIS2_SESSION_COOKIE",
        "DHIS2_SESSION_XSRF",
    ):
        monkeypatch.delenv(key, raising=False)
    yield


@TREES
def test_add_session_reads_cookie_from_env(app: Typer, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`profile add --auth session` takes the cookie from DHIS2_SESSION_COOKIE (never argv)."""
    monkeypatch.setenv("DHIS2_SESSION_COOKIE", "JSESSIONID=abc123")
    result = CliRunner().invoke(
        app,
        ["add", "browser", "--url", "https://play.dhis2.org", "--auth", "session", "--local"],
    )
    assert result.exit_code == 0, result.output
    loaded = load_profiles_file(tmp_path / ".dhis2" / "profiles.toml")
    assert loaded.profiles["browser"].auth == "session"
    cookie = loaded.profiles["browser"].cookie
    assert cookie is not None and cookie == "JSESSIONID=abc123"


@TREES
def test_add_session_strips_cookie_whitespace(app: Typer, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A cookie captured with a trailing newline (echo / clipboard artifact) is stored stripped."""
    monkeypatch.setenv("DHIS2_SESSION_COOKIE", "  JSESSIONID=abc123\n")
    result = CliRunner().invoke(
        app,
        ["add", "browser", "--url", "https://play.dhis2.org", "--auth", "session", "--local"],
    )
    assert result.exit_code == 0, result.output
    loaded = load_profiles_file(tmp_path / ".dhis2" / "profiles.toml")
    cookie = loaded.profiles["browser"].cookie
    assert cookie is not None and cookie == "JSESSIONID=abc123"


@TREES
def test_add_session_reads_xsrf_from_env(app: Typer, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`profile add --auth session` takes the CSRF token from DHIS2_SESSION_XSRF and stores it."""
    monkeypatch.setenv("DHIS2_SESSION_COOKIE", "JSESSIONID=abc123")
    monkeypatch.setenv("DHIS2_SESSION_XSRF", "xsrf-tok-9")
    result = CliRunner().invoke(
        app,
        ["add", "browser", "--url", "https://play.dhis2.org", "--auth", "session", "--local"],
    )
    assert result.exit_code == 0, result.output
    loaded = load_profiles_file(tmp_path / ".dhis2" / "profiles.toml")
    assert loaded.profiles["browser"].xsrf_token == "xsrf-tok-9"


@TREES
def test_add_session_without_xsrf_is_none(app: Typer, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A session profile added without DHIS2_SESSION_XSRF leaves xsrf_token unset (None)."""
    monkeypatch.setenv("DHIS2_SESSION_COOKIE", "JSESSIONID=abc123")
    result = CliRunner().invoke(
        app,
        ["add", "browser", "--url", "https://play.dhis2.org", "--auth", "session", "--local"],
    )
    assert result.exit_code == 0, result.output
    loaded = load_profiles_file(tmp_path / ".dhis2" / "profiles.toml")
    assert loaded.profiles["browser"].xsrf_token is None


@TREES
def test_add_session_empty_xsrf_env_is_none(app: Typer, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`DHIS2_SESSION_XSRF=""` (set but empty) is inert — the stored profile's xsrf_token is None, not "" ."""
    monkeypatch.setenv("DHIS2_SESSION_COOKIE", "JSESSIONID=abc123")
    monkeypatch.setenv("DHIS2_SESSION_XSRF", "")
    result = CliRunner().invoke(
        app,
        ["add", "browser", "--url", "https://play.dhis2.org", "--auth", "session", "--local"],
    )
    assert result.exit_code == 0, result.output
    loaded = load_profiles_file(tmp_path / ".dhis2" / "profiles.toml")
    assert loaded.profiles["browser"].xsrf_token is None


@TREES
def test_add_session_strips_xsrf_whitespace(app: Typer, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """An xsrf token captured with a trailing newline (echo / clipboard artifact) is stored stripped."""
    monkeypatch.setenv("DHIS2_SESSION_COOKIE", "JSESSIONID=abc123")
    monkeypatch.setenv("DHIS2_SESSION_XSRF", "  xsrf-tok-9\n")
    result = CliRunner().invoke(
        app,
        ["add", "browser", "--url", "https://play.dhis2.org", "--auth", "session", "--local"],
    )
    assert result.exit_code == 0, result.output
    loaded = load_profiles_file(tmp_path / ".dhis2" / "profiles.toml")
    assert loaded.profiles["browser"].xsrf_token == "xsrf-tok-9"


@TREES
def test_env_emits_session_cookie_export(app: Typer, tmp_path: Path) -> None:
    """`profile env` on a session profile emits the DHIS2_SESSION_COOKIE export, ready for `eval`."""
    toml_dir = tmp_path / "xdg" / "dhis2"
    toml_dir.mkdir(parents=True, exist_ok=True)
    (toml_dir / "profiles.toml").write_text(
        'default = "browser"\n\n'
        "[profiles.browser]\n"
        'base_url = "https://play.dhis2.org"\n'
        'auth = "session"\n'
        'cookie = "JSESSIONID=abc123"\n'
        'version = "v42"\n',
        encoding="utf-8",
    )
    result = CliRunner().invoke(app, ["env"])
    assert result.exit_code == 0, result.output
    assert "export DHIS2_SESSION_COOKIE=JSESSIONID=abc123" in result.output


@TREES
def test_env_session_prints_no_raw_path_caveat(app: Typer, tmp_path: Path) -> None:
    """`profile env` on a session profile warns that DHIS2_SESSION_COOKIE has no raw-env path."""
    toml_dir = tmp_path / "xdg" / "dhis2"
    toml_dir.mkdir(parents=True, exist_ok=True)
    (toml_dir / "profiles.toml").write_text(
        'default = "browser"\n\n'
        "[profiles.browser]\n"
        'base_url = "https://play.dhis2.org"\n'
        'auth = "session"\n'
        'cookie = "JSESSIONID=abc123"\n'
        'version = "v42"\n',
        encoding="utf-8",
    )
    result = CliRunner().invoke(app, ["env"])
    assert result.exit_code == 0, result.output
    assert "DHIS2_SESSION_COOKIE has no raw-env path" in result.output


@TREES
def test_env_emits_session_xsrf_export(app: Typer, tmp_path: Path) -> None:
    """`profile env` on a session profile with an xsrf_token emits the DHIS2_SESSION_XSRF export."""
    toml_dir = tmp_path / "xdg" / "dhis2"
    toml_dir.mkdir(parents=True, exist_ok=True)
    (toml_dir / "profiles.toml").write_text(
        'default = "browser"\n\n'
        "[profiles.browser]\n"
        'base_url = "https://play.dhis2.org"\n'
        'auth = "session"\n'
        'cookie = "JSESSIONID=abc123"\n'
        'xsrf_token = "xsrf-tok-9"\n'
        'version = "v42"\n',
        encoding="utf-8",
    )
    result = CliRunner().invoke(app, ["env"])
    assert result.exit_code == 0, result.output
    assert "export DHIS2_SESSION_XSRF=xsrf-tok-9" in result.output


@TREES
def test_env_omits_session_xsrf_when_absent(app: Typer, tmp_path: Path) -> None:
    """`profile env` on a session profile without an xsrf_token emits no DHIS2_SESSION_XSRF line."""
    toml_dir = tmp_path / "xdg" / "dhis2"
    toml_dir.mkdir(parents=True, exist_ok=True)
    (toml_dir / "profiles.toml").write_text(
        'default = "browser"\n\n'
        "[profiles.browser]\n"
        'base_url = "https://play.dhis2.org"\n'
        'auth = "session"\n'
        'cookie = "JSESSIONID=abc123"\n'
        'version = "v42"\n',
        encoding="utf-8",
    )
    result = CliRunner().invoke(app, ["env"])
    assert result.exit_code == 0, result.output
    assert "DHIS2_SESSION_XSRF" not in result.output


@pytest.mark.parametrize("tree", ["v41", "v42", "v43"])
def test_probe_auth_threads_xsrf_token(tree: str, tmp_path: Path) -> None:
    """`_build_probe_auth` threads the profile's xsrf_token into the SessionCookieAuth it builds."""
    service = importlib.import_module(f"dhis2w_core.{tree}.plugins.profile.service")
    toml_dir = tmp_path / "xdg" / "dhis2"
    toml_dir.mkdir(parents=True, exist_ok=True)
    (toml_dir / "profiles.toml").write_text(
        'default = "browser"\n\n'
        "[profiles.browser]\n"
        'base_url = "https://play.dhis2.org"\n'
        'auth = "session"\n'
        'cookie = "JSESSIONID=abc123"\n'
        'xsrf_token = "xsrf-tok-9"\n',
        encoding="utf-8",
    )
    from dhis2w_core.profile import resolve

    resolved = resolve("browser", start=tmp_path)
    auth = service._build_probe_auth(resolved.profile, profile_name="browser", scope="global")
    assert auth is not None
    assert auth.cookie == "JSESSIONID=abc123"
    assert auth.xsrf_token == "xsrf-tok-9"


@pytest.mark.parametrize("tree", ["v41", "v42", "v43"])
def test_show_profile_masks_cookie(tree: str, tmp_path: Path) -> None:
    """`show_profile` masks the session cookie like every other secret unless include_secrets=True."""
    service = importlib.import_module(f"dhis2w_core.{tree}.plugins.profile.service")
    toml_dir = tmp_path / "xdg" / "dhis2"
    toml_dir.mkdir(parents=True, exist_ok=True)
    (toml_dir / "profiles.toml").write_text(
        'default = "browser"\n\n'
        "[profiles.browser]\n"
        'base_url = "https://play.dhis2.org"\n'
        'auth = "session"\n'
        'cookie = "JSESSIONID=abc123"\n',
        encoding="utf-8",
    )
    redacted = service.show_profile("browser", start=tmp_path)
    assert redacted.cookie == "***"
    revealed = service.show_profile("browser", include_secrets=True, start=tmp_path)
    assert revealed.cookie == "JSESSIONID=abc123"


@pytest.mark.parametrize("tree", ["v41", "v42", "v43"])
def test_revealed_view_cookie_is_plain_string(tree: str, tmp_path: Path) -> None:
    """`show_profile(include_secrets=True)` yields the real cookie value when include_secrets is set."""
    service = importlib.import_module(f"dhis2w_core.{tree}.plugins.profile.service")
    toml_dir = tmp_path / "xdg" / "dhis2"
    toml_dir.mkdir(parents=True, exist_ok=True)
    (toml_dir / "profiles.toml").write_text(
        'default = "browser"\n\n'
        "[profiles.browser]\n"
        'base_url = "https://play.dhis2.org"\n'
        'auth = "session"\n'
        'cookie = "JSESSIONID=abc123"\n',
        encoding="utf-8",
    )
    revealed = service.show_profile("browser", include_secrets=True, start=tmp_path)
    # ProfileView holds plain strings, so JSON/model_dump renders the real value.
    assert revealed.model_dump()["cookie"] == "JSESSIONID=abc123"
    # And the default (redacted) view never carries the raw secret.
    redacted = service.show_profile("browser", start=tmp_path)
    assert "abc123" not in str(redacted.model_dump())


@pytest.mark.parametrize("tree", ["v41", "v42", "v43"])
def test_show_profile_masks_xsrf_token(tree: str, tmp_path: Path) -> None:
    """`show_profile` masks the CSRF token like every other secret unless include_secrets=True."""
    service = importlib.import_module(f"dhis2w_core.{tree}.plugins.profile.service")
    toml_dir = tmp_path / "xdg" / "dhis2"
    toml_dir.mkdir(parents=True, exist_ok=True)
    (toml_dir / "profiles.toml").write_text(
        'default = "browser"\n\n'
        "[profiles.browser]\n"
        'base_url = "https://play.dhis2.org"\n'
        'auth = "session"\n'
        'cookie = "JSESSIONID=abc123"\n'
        'xsrf_token = "xsrf-tok-9"\n',
        encoding="utf-8",
    )
    redacted = service.show_profile("browser", start=tmp_path)
    assert redacted.xsrf_token == "***"
    assert "xsrf-tok-9" not in str(redacted.model_dump())
    revealed = service.show_profile("browser", include_secrets=True, start=tmp_path)
    assert revealed.xsrf_token == "xsrf-tok-9"
