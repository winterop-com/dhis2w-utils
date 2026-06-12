"""Tests for `metadata export` per-resource filters + dangling-reference probe."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import respx
from dhis2w_cli.main import build_app
from dhis2w_core.profile import Profile
from dhis2w_core.v42.plugins.metadata import service
from dhis2w_core.v42.plugins.metadata.models import MetadataBundle
from typer.testing import CliRunner


def _bundle(raw: dict[str, Any]) -> MetadataBundle:
    """Shortcut: build a typed MetadataBundle from a literal raw-dict fixture."""
    return MetadataBundle.from_raw(raw)


@pytest.fixture(autouse=True)
def _raw_env_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    """Isolate tests from any system `profiles.toml` — force raw-env resolution."""
    monkeypatch.delenv("DHIS2_PROFILE", raising=False)
    monkeypatch.setenv("DHIS2_URL", "http://mock.example")
    monkeypatch.setenv("DHIS2_PAT", "test-token")


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _mock_connect_preamble() -> None:
    """Mock the endpoints `Dhis2Client.connect()` hits before the per-test route."""
    respx.get("http://mock.example/").mock(return_value=httpx.Response(200, text="ok"))
    respx.get("http://mock.example/api/system/info").mock(
        return_value=httpx.Response(200, json={"version": "2.42.4"}),
    )


@respx.mock
async def test_export_per_resource_filter_hits_prefixed_wire_format() -> None:
    """Per-resource filters must arrive as `<resource>:filter=<expr>` repeated params."""
    _mock_connect_preamble()
    route = respx.get("http://mock.example/api/metadata").mock(
        return_value=httpx.Response(200, json={"dataElements": []}),
    )
    profile = Profile(base_url="http://mock.example", auth="pat", token="t")
    await service.export_metadata(
        profile,
        resources=["dataElements"],
        per_resource_filters={
            "dataElements": ["name:like:ANC", "valueType:eq:INTEGER_POSITIVE"],
        },
    )
    # httpx serialises list values as repeated params — .params is a MultiDict.
    params = route.calls.last.request.url.params
    filter_values = params.get_list("dataElements:filter")
    assert filter_values == ["name:like:ANC", "valueType:eq:INTEGER_POSITIVE"]


@respx.mock
async def test_export_per_resource_fields_overrides_global() -> None:
    """Per-resource fields selector lands as `<resource>:fields=<selector>`."""
    _mock_connect_preamble()
    route = respx.get("http://mock.example/api/metadata").mock(
        return_value=httpx.Response(200, json={"dataElements": []}),
    )
    profile = Profile(base_url="http://mock.example", auth="pat", token="t")
    await service.export_metadata(
        profile,
        resources=["dataElements"],
        fields=":owner",
        per_resource_fields={"dataElements": ":identifiable"},
    )
    params = route.calls.last.request.url.params
    # Global fields still present.
    assert params.get("fields") == ":owner"
    # Per-resource override present.
    assert params.get("dataElements:fields") == ":identifiable"


def test_bundle_dangling_references_finds_missing_nested_refs() -> None:
    """A dataElement whose categoryCombo UID isn't in the bundle surfaces as dangling."""
    bundle = {
        "dataElements": [
            {
                "id": "DE00000001",
                "name": "DE",
                "categoryCombo": {"id": "CCmissing01"},
                "optionSet": {"id": "OSmissing01"},
            }
        ],
    }
    refs = service.bundle_dangling_references(_bundle(bundle))
    by_field = {item.field_name: item for item in refs.items}
    assert set(by_field) == {"categoryCombo", "optionSet"}
    assert by_field["categoryCombo"].missing_uids == ["CCmissing01"]
    assert by_field["optionSet"].missing_uids == ["OSmissing01"]
    assert refs.total_missing == 2
    assert refs.bundle_uid_count == 1
    assert refs.is_clean is False


def test_bundle_dangling_references_ignores_uids_present_in_bundle() -> None:
    """References that resolve to UIDs in the bundle are not dangling."""
    bundle = {
        "dataElements": [
            {"id": "DE00000001", "categoryCombo": {"id": "CC00000001"}},
        ],
        "categoryCombos": [{"id": "CC00000001", "name": "default"}],
    }
    refs = service.bundle_dangling_references(_bundle(bundle))
    assert refs.is_clean is True
    assert refs.total_missing == 0
    assert refs.bundle_uid_count == 2


def test_bundle_dangling_references_skips_noisy_user_fields_by_default() -> None:
    """`createdBy` / `lastUpdatedBy` / user sharing blocks are expected to dangle — skipped by default."""
    bundle = {
        "dataElements": [
            {
                "id": "DE00000001",
                "createdBy": {"id": "userxxxxxx"},  # noisy — skipped
                "lastUpdatedBy": {"id": "userxxxxxx"},  # noisy — skipped
                "sharing": {"owner": "userxxxxxx"},  # noisy — skipped
                "categoryCombo": {"id": "CCrealmiss1"},  # NOT noisy
            }
        ],
    }
    refs = service.bundle_dangling_references(_bundle(bundle))
    assert [item.field_name for item in refs.items] == ["categoryCombo"]
    assert "createdBy" in refs.skipped_fields


def test_bundle_dangling_references_skip_override_checks_everything() -> None:
    """`skip_fields=frozenset()` exposes the user refs too — escape hatch for power users."""
    bundle = {
        "dataElements": [
            {"id": "DE00000001", "createdBy": {"id": "userxxxxxx"}},
        ],
    }
    refs = service.bundle_dangling_references(_bundle(bundle), skip_fields=frozenset())
    fields = {item.field_name for item in refs.items}
    assert "createdBy" in fields


def test_bundle_dangling_references_walks_lists_of_refs() -> None:
    """`legendSets: [{id: ...}, {id: ...}]` is a list of refs — each UID checked individually."""
    bundle = {
        "dataElements": [
            {
                "id": "DE00000001",
                "legendSets": [{"id": "LSpresent01"}, {"id": "LSmissing01"}],
            }
        ],
        "legendSets": [{"id": "LSpresent01"}],
    }
    refs = service.bundle_dangling_references(_bundle(bundle))
    assert [item.field_name for item in refs.items] == ["legendSets"]
    assert refs.items[0].missing_uids == ["LSmissing01"]


def test_cli_export_parses_prefixed_filter_flag(runner: CliRunner, tmp_path: Path) -> None:
    """`--filter dataElements:name:like:ANC` routes into per_resource_filters correctly."""
    out = tmp_path / "b.json"
    mock = AsyncMock(return_value=_bundle({"dataElements": []}))
    with patch("dhis2w_core.v42.plugins.metadata.service.export_metadata", mock):
        result = runner.invoke(
            build_app(),
            [
                "metadata",
                "export",
                "--resource",
                "dataElements",
                "--filter",
                "dataElements:name:like:ANC",
                "--filter",
                "dataElements:valueType:eq:INTEGER_POSITIVE",
                "--resource-fields",
                "dataElements::identifiable",
                "--no-check-references",
                "--output",
                str(out),
            ],
        )
    assert result.exit_code == 0, result.output
    _, kwargs = mock.call_args
    assert kwargs["per_resource_filters"] == {
        "dataElements": ["name:like:ANC", "valueType:eq:INTEGER_POSITIVE"],
    }
    assert kwargs["per_resource_fields"] == {"dataElements": ":identifiable"}


def test_cli_export_rejects_malformed_filter(runner: CliRunner) -> None:
    """A `--filter` value with no colon is malformed — Typer should surface a clear error."""
    result = runner.invoke(
        build_app(),
        ["metadata", "export", "--filter", "justaname", "--no-check-references"],
    )
    assert result.exit_code != 0
    assert "RESOURCE:expr" in result.output or "RESOURCE" in result.output


def test_cli_export_prints_dangling_reference_warning(runner: CliRunner, tmp_path: Path) -> None:
    """Default `--check-references` surfaces dangling UIDs in the CLI output."""
    out = tmp_path / "b.json"
    mock = AsyncMock(
        return_value=_bundle(
            {
                "dataElements": [
                    {"id": "DE00000001", "categoryCombo": {"id": "CCmissing01"}},
                ],
            }
        )
    )
    with patch("dhis2w_core.v42.plugins.metadata.service.export_metadata", mock):
        result = runner.invoke(
            build_app(),
            ["metadata", "export", "--resource", "dataElements", "--output", str(out)],
        )
    assert result.exit_code == 0, result.output
    # The warning goes to the Rich console which captures to stdout under CliRunner.
    combined = result.output
    assert "WARNING" in combined
    assert "categoryCombo" in combined
    assert "CCmissing01" in combined


def test_cli_export_no_check_references_silences_the_warning(runner: CliRunner, tmp_path: Path) -> None:
    """`--no-check-references` skips the walk entirely — nothing about references in output."""
    out = tmp_path / "b.json"
    mock = AsyncMock(
        return_value=_bundle(
            {
                "dataElements": [
                    {"id": "DE00000001", "categoryCombo": {"id": "CCmissing01"}},
                ],
            }
        )
    )
    with patch("dhis2w_core.v42.plugins.metadata.service.export_metadata", mock):
        result = runner.invoke(
            build_app(),
            ["metadata", "export", "--resource", "dataElements", "--no-check-references", "--output", str(out)],
        )
    assert result.exit_code == 0, result.output
    assert "WARNING" not in result.output
    assert "dangling" not in result.output.lower()


def test_cli_export_clean_bundle_says_no_dangling(runner: CliRunner, tmp_path: Path) -> None:
    """A bundle where every ref resolves in-bundle prints the reassuring clean message."""
    out = tmp_path / "b.json"
    mock = AsyncMock(
        return_value=_bundle(
            {
                "dataElements": [
                    {"id": "DE00000001", "categoryCombo": {"id": "CC00000001"}},
                ],
                "categoryCombos": [{"id": "CC00000001"}],
            }
        )
    )
    with patch("dhis2w_core.v42.plugins.metadata.service.export_metadata", mock):
        result = runner.invoke(
            build_app(),
            ["metadata", "export", "--resource", "dataElements", "--resource", "categoryCombos", "--output", str(out)],
        )
    assert result.exit_code == 0, result.output
    assert "no dangling references" in result.output.lower()
