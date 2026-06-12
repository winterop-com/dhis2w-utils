"""Regression tests for the bound-tree profile version guard.

The MCP server pins its plugin tree once at boot via `bind_version_tree()`.
After that, every `resolve()` / `resolve_profile()` call checks the resolved
profile's `version` field against the bound tree and raises
`ProfileVersionMismatchError` on mismatch — preventing the silent v42-parses-
v43-payload class of bug a misconfigured per-call profile would otherwise hit.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from dhis2w_client.generated import Dhis2
from dhis2w_core.profile import (
    Profile,
    ProfilesFile,
    ProfileVersionMismatchError,
    bind_version_tree,
    resolve,
    write_profiles_file,
)


@pytest.fixture(autouse=True)
def _reset_bound_tree() -> object:
    """Always clear the binding around each test so process-wide state can't leak."""
    bind_version_tree(None)
    yield None
    bind_version_tree(None)


def _write_profiles(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, profiles: dict[str, Profile]) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    for key in ("DHIS2_PROFILE", "DHIS2_URL", "DHIS2_PAT", "DHIS2_USERNAME", "DHIS2_PASSWORD", "DHIS2_VERSION"):
        monkeypatch.delenv(key, raising=False)
    write_profiles_file(
        tmp_path / "dhis2" / "profiles.toml",
        ProfilesFile(default=next(iter(profiles)), profiles=profiles),
    )


def test_resolve_passes_when_no_tree_is_bound(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Resolve passes when no tree is bound."""
    _write_profiles(
        tmp_path,
        monkeypatch,
        {"local": Profile(base_url="http://x", auth="pat", token="t", version=Dhis2.V43)},
    )
    # No bind_version_tree(...) call — the CLI's regular usage. resolve() returns cleanly.
    resolved = resolve("local")
    assert resolved.profile.version == Dhis2.V43


def test_resolve_passes_when_profile_matches_bound_tree(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Resolve passes when profile matches bound tree."""
    _write_profiles(
        tmp_path,
        monkeypatch,
        {"local": Profile(base_url="http://x", auth="pat", token="t", version=Dhis2.V43)},
    )
    bind_version_tree("v43")
    resolved = resolve("local")
    assert resolved.profile.version == Dhis2.V43


def test_resolve_passes_when_profile_has_no_version_pin(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Resolve passes when profile has no version pin."""
    _write_profiles(
        tmp_path,
        monkeypatch,
        {"local": Profile(base_url="http://x", auth="pat", token="t")},
    )
    # Bound tree is v42; profile has no version pin — fine, auto-detect will sort it out.
    bind_version_tree("v42")
    resolved = resolve("local")
    assert resolved.profile.version is None


def test_resolve_raises_when_profile_version_mismatches_bound_tree(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Resolve raises when profile version mismatches bound tree."""
    _write_profiles(
        tmp_path,
        monkeypatch,
        {"v43_prod": Profile(base_url="http://x", auth="pat", token="t", version=Dhis2.V43)},
    )
    bind_version_tree("v42")
    with pytest.raises(ProfileVersionMismatchError) as exc:
        resolve("v43_prod")
    msg = str(exc.value)
    assert "v43_prod" in msg
    assert "v42" in msg
    assert "v43" in msg
    # Restart hint surfaces in the message so the operator can act on it.
    assert "DHIS2_VERSION=43 dhis2w-mcp" in msg
