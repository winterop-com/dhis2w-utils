"""Unit tests for `d2w metadata share` bulk-share verb + its service layer."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import respx
from dhis2w_core.v42.plugins.metadata import service


@pytest.fixture
def pat_profile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Profiles.toml with a Basic profile that the service can open_client on."""
    config_dir = tmp_path / ".config" / "dhis2"
    config_dir.mkdir(parents=True)
    (config_dir / "profiles.toml").write_text(
        """
default = "probe"

[profiles.probe]
base_url = "https://dhis2.example"
auth = "basic"
username = "admin"
password = "district"
"""
    )
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_dir.parent))
    monkeypatch.delenv("DHIS2_PROFILE", raising=False)
    monkeypatch.chdir(tmp_path)


def _mock_preamble() -> None:
    respx.get("https://dhis2.example/api/system/info").mock(
        return_value=httpx.Response(200, json={"version": "2.42.0"}),
    )


@respx.mock
async def test_bulk_share_applies_grants_to_every_uid(pat_profile: None) -> None:  # noqa: ARG001
    """Bulk share applies grants to every uid."""
    _mock_preamble()
    route = respx.post("https://dhis2.example/api/sharing").mock(return_value=httpx.Response(200, json={}))

    from dhis2w_core.profile import resolve_profile

    profile = resolve_profile("probe")
    result = await service.bulk_share_metadata(
        profile,
        "dataSet",
        ["DS_A", "DS_B"],
        public_access="r-------",
        user_group_access=["UG_PROG:rwrw----"],
    )
    assert route.call_count == 2
    assert result.matched == 2
    assert result.dry_run is False
    assert result.succeeded == 2
    assert result.failed == 0
    assert result.entries[0].user_group_grants == ["UG_PROG:rwrw----"]


@respx.mock
async def test_bulk_share_dry_run_does_not_post(pat_profile: None) -> None:  # noqa: ARG001
    """Bulk share dry run does not post."""
    _mock_preamble()
    route = respx.post("https://dhis2.example/api/sharing").mock(return_value=httpx.Response(200, json={}))

    from dhis2w_core.profile import resolve_profile

    profile = resolve_profile("probe")
    result = await service.bulk_share_metadata(
        profile,
        "dataSet",
        ["DS_A"],
        public_access="r-------",
        user_access=["U_ALICE:rw------"],
        dry_run=True,
    )
    assert not route.called
    assert result.dry_run is True
    assert result.matched == 1
    assert result.sharing_result is None
    assert result.entries[0].public_access == "r-------"
    assert result.entries[0].user_grants == ["U_ALICE:rw------"]


async def test_bulk_share_rejects_malformed_grant(pat_profile: None) -> None:  # noqa: ARG001
    """Service surfaces a typed ValueError on bad `UID:access` syntax — CLI converts to BadParameter."""
    from dhis2w_core.profile import resolve_profile

    profile = resolve_profile("probe")
    with pytest.raises(ValueError, match="--user-access"):
        await service.bulk_share_metadata(
            profile,
            "dataSet",
            ["DS_A"],
            user_access=["just-a-uid"],
            dry_run=True,
        )
