"""OAuth2 token-store keys bind to instance identity, and storage scope follows the profile's layer."""

from __future__ import annotations

from importlib import import_module
from pathlib import Path
from types import ModuleType

import pytest
from dhis2w_core.profile import Profile, resolve
from dhis2w_core.v42.client_context import scope_from_resolved

TREES = pytest.mark.parametrize("tree", ["v41", "v42", "v43"])


def _client_context(tree: str) -> ModuleType:
    """Import the version tree's `client_context` module."""
    return import_module(f"dhis2w_core.{tree}.client_context")


def _oauth2_profile(base_url: str, client_id: str = "app-one") -> Profile:
    """Build a minimal OAuth2 profile pointed at `base_url`."""
    return Profile(
        base_url=base_url,
        auth="oauth2",
        client_id=client_id,
        client_secret="s3cret",
        scope="ALL",
        redirect_uri="http://localhost:8099/callback",
    )


def _store_key(auth: object) -> str:
    """Read the token-store key the provider was constructed with."""
    key = getattr(auth, "_store_key", None)
    assert isinstance(key, str)
    return key


def _clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Drop every profile env var so resolution reads only the TOML files under test."""
    for key in ("DHIS2_PROFILE", "DHIS2_URL", "DHIS2_PAT", "DHIS2_USERNAME", "DHIS2_PASSWORD", "DHIS2_VERSION"):
        monkeypatch.delenv(key, raising=False)


def _write_profiles(path: Path, body: str) -> None:
    """Write a `profiles.toml` at `path`, creating the `.dhis2` directory."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


_OAUTH_TOML = """
default = "default"

[profiles.default]
base_url = "{base_url}"
auth = "oauth2"
client_id = "{client_id}"
client_secret = "s3cret"
scope = "ALL"
redirect_uri = "http://localhost:8099/callback"
"""


@TREES
def test_different_base_urls_never_share_a_store_key(tree: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Two profiles resolving to the same name but different instances get different keys."""
    _clear_env(monkeypatch)
    module = _client_context(tree)
    first = module.build_auth(_oauth2_profile("https://one.example.org"), profile_name="default")
    second = module.build_auth(_oauth2_profile("https://two.example.org"), profile_name="default")
    assert _store_key(first) == "profile:default:https://one.example.org:app-one"
    assert _store_key(second) == "profile:default:https://two.example.org:app-one"


@TREES
def test_different_client_ids_never_share_a_store_key(tree: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Two profiles on one instance with different OAuth clients get different keys."""
    _clear_env(monkeypatch)
    module = _client_context(tree)
    base_url = "https://one.example.org"
    first = module.build_auth(_oauth2_profile(base_url, client_id="app-one"), profile_name="default")
    second = module.build_auth(_oauth2_profile(base_url, client_id="app-two"), profile_name="default")
    assert _store_key(first) == "profile:default:https://one.example.org:app-one"
    assert _store_key(second) == "profile:default:https://one.example.org:app-two"


@TREES
def test_store_key_composes_name_base_url_and_client_id(tree: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """The key names the profile, the instance origin, and the OAuth client."""
    _clear_env(monkeypatch)
    module = _client_context(tree)
    auth = module.build_auth(_oauth2_profile("https://one.example.org", client_id="app-one"), profile_name="prod")
    assert _store_key(auth) == "profile:prod:https://one.example.org:app-one"


@TREES
def test_two_projects_with_one_profile_name_never_share_a_store_key(
    tree: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The same profile name in two project directories keys on each project's own instance."""
    _clear_env(monkeypatch)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    module = _client_context(tree)

    project_one = tmp_path / "one"
    project_two = tmp_path / "two"
    _write_profiles(
        project_one / ".dhis2" / "profiles.toml",
        _OAUTH_TOML.format(base_url="https://one.example.org", client_id="app-one"),
    )
    _write_profiles(
        project_two / ".dhis2" / "profiles.toml",
        _OAUTH_TOML.format(base_url="https://two.example.org", client_id="app-two"),
    )

    keys: list[str] = []
    for project in (project_one, project_two):
        resolved = resolve(start=project)
        auth = module.build_auth(
            resolved.profile,
            profile_name=resolved.name,
            scope=module.scope_from_resolved(resolved),
        )
        keys.append(_store_key(auth))

    assert keys[0] != keys[1]


@TREES
def test_project_profile_selected_by_name_stores_beside_the_project(
    tree: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An explicit `-p` selection of a project profile still uses project-scoped storage."""
    _clear_env(monkeypatch)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    module = _client_context(tree)
    project = tmp_path / "project"
    _write_profiles(
        project / ".dhis2" / "profiles.toml",
        _OAUTH_TOML.format(base_url="https://one.example.org", client_id="app-one"),
    )
    resolved = resolve("default", start=project)
    assert resolved.source == "arg"
    assert resolved.layer == "project-toml"
    assert module.scope_from_resolved(resolved) == "project"


@TREES
def test_defaulted_project_profile_stores_beside_the_project(
    tree: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A project profile reached through the default chain uses project-scoped storage."""
    _clear_env(monkeypatch)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    module = _client_context(tree)
    project = tmp_path / "project"
    _write_profiles(
        project / ".dhis2" / "profiles.toml",
        _OAUTH_TOML.format(base_url="https://one.example.org", client_id="app-one"),
    )
    resolved = resolve(start=project)
    assert resolved.layer == "project-toml"
    assert module.scope_from_resolved(resolved) == "project"


@TREES
def test_global_profile_stores_globally(
    tree: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A profile that lives only in the global TOML uses global-scoped storage."""
    _clear_env(monkeypatch)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    module = _client_context(tree)
    _write_profiles(
        tmp_path / "xdg" / "dhis2" / "profiles.toml",
        _OAUTH_TOML.format(base_url="https://one.example.org", client_id="app-one"),
    )
    empty_project = tmp_path / "empty"
    empty_project.mkdir()
    resolved = resolve("default", start=empty_project)
    assert resolved.layer == "global-toml"
    assert module.scope_from_resolved(resolved) == "global"


def test_raw_env_profile_layer_is_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A profile built from raw env vars reports the `env` layer and global storage."""
    _clear_env(monkeypatch)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.setenv("DHIS2_URL", "https://env.example.org")
    monkeypatch.setenv("DHIS2_PAT", "d2p_env")
    empty_project = tmp_path / "empty"
    empty_project.mkdir()
    resolved = resolve(start=empty_project)
    assert resolved.source == "env-raw"
    assert resolved.layer == "env"
    assert scope_from_resolved(resolved) == "global"
