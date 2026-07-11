"""Verify emits a truthful diagnosis when a known auth kind is missing its secret.

A profile whose auth kind the code supports but whose secret is absent (session
without cookie, pat without token, basic without username/password) must yield an
error that names the missing material and points at the remedy — never the false
"unsupported auth type" message, which an external consumer (the kodo Chrome
extension panel) machine-reads to route bound/expired/broken states.
"""

from __future__ import annotations

import importlib
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import httpx
import pytest
import respx

# One test tree, parametrised over the three version trees — the diagnosis is
# identical across them and must read the same regardless of active tree.
TREES = pytest.mark.parametrize("tree", ["v41", "v42", "v43"], ids=["v41", "v42", "v43"])

_HOST = "https://dhis2.example"
_WIRE_VERSIONS = {"v41": "2.41.8.1", "v42": "2.42.0", "v43": "2.43.0"}


def _service(tree: str) -> ModuleType:
    """Import a version tree's profile service module."""
    return importlib.import_module(f"dhis2w_core.{tree}.plugins.profile.service")


@pytest.fixture(autouse=True)
def _isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Pin config into tmp_path and strip every env var the resolver consults."""
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
    ):
        monkeypatch.delenv(key, raising=False)
    yield


def _write_profile(tmp_path: Path, name: str, body: str) -> None:
    """Write a single-profile global profiles.toml under the isolated XDG config."""
    toml_dir = tmp_path / "xdg" / "dhis2"
    toml_dir.mkdir(parents=True, exist_ok=True)
    (toml_dir / "profiles.toml").write_text(
        f'default = "{name}"\n\n[profiles.{name}]\n{body}',
        encoding="utf-8",
    )


@TREES
async def test_session_without_cookie_names_missing_cookie(tree: str, tmp_path: Path) -> None:
    """A session profile with no cookie diagnoses the missing cookie, not 'unsupported auth type'."""
    _write_profile(tmp_path, "browser", f'base_url = "{_HOST}"\nauth = "session"\n')
    service = _service(tree)

    result = await service.verify_profile("browser")

    assert result.ok is False
    assert result.error == (
        "profile has no cookie; re-run `d2w profile add browser --auth session` to bind a fresh session cookie"
    )
    assert "does not yet support" not in (result.error or "")


@TREES
async def test_pat_without_token_names_missing_token(tree: str, tmp_path: Path) -> None:
    """A pat profile with no token diagnoses the missing token, not 'unsupported auth type'."""
    _write_profile(tmp_path, "api", f'base_url = "{_HOST}"\nauth = "pat"\n')
    service = _service(tree)

    result = await service.verify_profile("api")

    assert result.ok is False
    assert result.error == (
        "profile has no token; re-run `d2w profile add api --auth pat` to bind a personal access token"
    )
    assert "does not yet support" not in (result.error or "")


@TREES
async def test_basic_without_credentials_names_missing_credentials(tree: str, tmp_path: Path) -> None:
    """A basic profile missing username/password diagnoses the missing credentials."""
    _write_profile(tmp_path, "creds", f'base_url = "{_HOST}"\nauth = "basic"\nusername = "admin"\n')
    service = _service(tree)

    result = await service.verify_profile("creds")

    assert result.ok is False
    assert result.error == (
        "profile has no username/password; re-run `d2w profile add creds --auth basic` to bind Basic credentials"
    )
    assert "does not yet support" not in (result.error or "")


@TREES
@respx.mock
async def test_complete_session_profile_probes(tree: str, tmp_path: Path) -> None:
    """A session profile that HAS a cookie gets probed — never the missing-material diagnosis."""
    _write_profile(
        tmp_path,
        "browser",
        f'base_url = "{_HOST}"\nauth = "session"\ncookie = "JSESSIONID=abc123"\nversion = "{tree}"\n',
    )
    respx.get(f"{_HOST}/api/system/info").mock(
        return_value=httpx.Response(200, json={"version": _WIRE_VERSIONS[tree]}),
    )
    respx.get(f"{_HOST}/").mock(return_value=httpx.Response(200, text="<html></html>"))
    respx.get(f"{_HOST}/api/me").mock(
        return_value=httpx.Response(200, json={"id": "usr01234567", "username": "admin"}),
    )
    service = _service(tree)

    result = await service.verify_profile("browser")

    assert "profile has no cookie" not in (result.error or "")
    assert result.ok, result.error
    assert result.username == "admin"
