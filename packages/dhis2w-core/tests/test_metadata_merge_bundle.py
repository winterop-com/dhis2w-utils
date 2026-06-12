"""Tests for `d2w metadata merge-bundle` — bundle-from-disk import path."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx
from dhis2w_core.v42.plugins.metadata import service


@pytest.fixture
def pat_profile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """profiles.toml with a Basic profile that the service can open_client on."""
    config_dir = tmp_path / ".config" / "dhis2"
    config_dir.mkdir(parents=True)
    (config_dir / "profiles.toml").write_text(
        """
default = "target"

[profiles.target]
base_url = "https://target.example"
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
    respx.get("https://target.example/api/system/info").mock(
        return_value=httpx.Response(200, json={"version": "2.42.0"}),
    )


def _bundle_with(items: dict[str, list[dict[str, str]]]) -> dict[str, object]:
    return {"system": {"id": "sys"}, **items}


@respx.mock
async def test_merge_bundle_imports_every_resource_section(tmp_path: Path, pat_profile: None) -> None:  # noqa: ARG001
    """Merge bundle imports every resource section."""
    _mock_preamble()
    bundle_path = tmp_path / "bundle.json"
    bundle_path.write_text(
        json.dumps(
            _bundle_with(
                {
                    "dataElements": [{"id": "DE_A", "name": "ANC visits"}],
                    "indicators": [{"id": "IND_A", "name": "ANC indicator"}],
                }
            )
        )
    )
    import_route = respx.post("https://target.example/api/metadata").mock(
        return_value=httpx.Response(
            200,
            json={
                "status": "OK",
                "httpStatusCode": 200,
                "response": {
                    "stats": {"created": 2, "updated": 0, "ignored": 0, "deleted": 0, "total": 2},
                    "typeReports": [],
                },
            },
        ),
    )

    from dhis2w_core.profile import resolve_profile

    target = resolve_profile("target")
    result = await service.merge_metadata_from_bundle(target, bundle_path)

    assert import_route.called
    assert result.dry_run is False
    assert result.target_base_url == "https://target.example"
    assert result.source_base_url.startswith("bundle:")
    assert sorted(result.export_counts) == ["dataElements", "indicators"]
    assert result.export_counts["dataElements"] == 1
    assert result.export_counts["indicators"] == 1


@respx.mock
async def test_merge_bundle_dry_run_uses_validate_mode(tmp_path: Path, pat_profile: None) -> None:  # noqa: ARG001
    """Merge bundle dry run uses validate mode."""
    _mock_preamble()
    bundle_path = tmp_path / "bundle.json"
    bundle_path.write_text(json.dumps(_bundle_with({"dataElements": [{"id": "DE_A"}]})))
    import_route = respx.post("https://target.example/api/metadata").mock(
        return_value=httpx.Response(
            200, json={"status": "OK", "httpStatusCode": 200, "response": {"stats": {"total": 0}}}
        ),
    )

    from dhis2w_core.profile import resolve_profile

    target = resolve_profile("target")
    result = await service.merge_metadata_from_bundle(target, bundle_path, dry_run=True)
    assert result.dry_run is True
    assert import_route.calls.last.request.url.params["importMode"] == "VALIDATE"


@respx.mock
async def test_merge_bundle_resource_filter_narrows_count_summary(tmp_path: Path, pat_profile: None) -> None:  # noqa: ARG001
    """Merge bundle resource filter narrows count summary."""
    _mock_preamble()
    bundle_path = tmp_path / "bundle.json"
    bundle_path.write_text(
        json.dumps(
            _bundle_with(
                {
                    "dataElements": [{"id": "DE_A"}, {"id": "DE_B"}],
                    "indicators": [{"id": "IND_A"}],
                }
            )
        )
    )
    respx.post("https://target.example/api/metadata").mock(
        return_value=httpx.Response(
            200, json={"status": "OK", "httpStatusCode": 200, "response": {"stats": {"total": 0}}}
        ),
    )

    from dhis2w_core.profile import resolve_profile

    target = resolve_profile("target")
    result = await service.merge_metadata_from_bundle(target, bundle_path, resources=["dataElements"])
    assert sorted(result.export_counts) == ["dataElements"]
    assert result.export_counts["dataElements"] == 2


async def test_merge_bundle_rejects_non_object_root(tmp_path: Path) -> None:
    """Merge bundle rejects non object root."""
    bundle_path = tmp_path / "bundle.json"
    bundle_path.write_text(json.dumps([{"id": "wrong"}]))

    from dhis2w_core.profile import Profile

    profile = Profile(base_url="https://example.invalid", auth="basic")
    with pytest.raises(ValueError, match="did not parse to an object"):
        await service.merge_metadata_from_bundle(profile, bundle_path)
