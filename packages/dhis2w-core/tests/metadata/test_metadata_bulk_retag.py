"""Unit tests for `d2w metadata retag` bulk-retag verb + its service layer."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import respx
from dhis2w_cli.main import build_app
from dhis2w_client import BulkPatchResult
from dhis2w_core.v42.plugins.metadata import service
from dhis2w_core.v42.plugins.metadata.service import BulkRetagEntry, BulkRetagResult
from typer.testing import CliRunner


@pytest.fixture
def pat_profile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Profiles.toml with a Basic profile usable by the service."""
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


# ---- service.bulk_retag_metadata -------------------------------------------


@respx.mock
async def test_bulk_retag_replaces_category_combo(pat_profile: None) -> None:  # noqa: ARG001
    """Bulk retag replaces category combo."""
    _mock_preamble()
    respx.get("https://dhis2.example/api/dataElements").mock(
        return_value=httpx.Response(
            200,
            json={
                "dataElements": [
                    {"id": "DE_A", "categoryCombo": {"id": "ccOld00001"}},
                    {"id": "DE_B", "categoryCombo": {"id": "ccNew00001"}},
                ],
            },
        ),
    )
    patch_a = respx.patch("https://dhis2.example/api/dataElements/DE_A").mock(
        return_value=httpx.Response(200, json={}),
    )
    patch_b = respx.patch("https://dhis2.example/api/dataElements/DE_B").mock(
        return_value=httpx.Response(200, json={}),
    )
    from dhis2w_core.profile import resolve_profile

    result = await service.bulk_retag_metadata(
        resolve_profile("probe"),
        "dataElements",
        category_combo_uid="ccNew00001",
    )
    assert result.matched == 1
    assert result.entries[0].uid == "DE_A"
    assert result.entries[0].before["/categoryCombo"] == "ccOld00001"
    assert result.entries[0].after["/categoryCombo"] == "ccNew00001"
    assert patch_a.called
    assert patch_b.called is False


@respx.mock
async def test_bulk_retag_clear_option_set_emits_remove(pat_profile: None) -> None:  # noqa: ARG001
    """Bulk retag clear option set emits remove."""
    _mock_preamble()
    respx.get("https://dhis2.example/api/dataElements").mock(
        return_value=httpx.Response(
            200,
            json={
                "dataElements": [
                    {"id": "DE_A", "optionSet": {"id": "optSetOld"}},
                    {"id": "DE_B"},
                ],
            },
        ),
    )
    put = respx.patch("https://dhis2.example/api/dataElements/DE_A").mock(return_value=httpx.Response(200, json={}))
    from dhis2w_core.profile import resolve_profile

    result = await service.bulk_retag_metadata(
        resolve_profile("probe"),
        "dataElements",
        clear_option_set=True,
    )
    assert result.matched == 1
    import json as _json

    body: list[dict[str, Any]] = _json.loads(put.calls.last.request.read())
    assert body == [{"op": "remove", "path": "/optionSet"}]


@respx.mock
async def test_bulk_retag_replaces_legend_sets_as_full_list(pat_profile: None) -> None:  # noqa: ARG001
    """Bulk retag replaces legend sets as full list."""
    _mock_preamble()
    respx.get("https://dhis2.example/api/dataElements").mock(
        return_value=httpx.Response(
            200,
            json={"dataElements": [{"id": "DE_A", "legendSets": [{"id": "oldLs1"}]}]},
        ),
    )
    route = respx.patch("https://dhis2.example/api/dataElements/DE_A").mock(return_value=httpx.Response(200, json={}))
    from dhis2w_core.profile import resolve_profile

    await service.bulk_retag_metadata(
        resolve_profile("probe"),
        "dataElements",
        legend_set_uids=["newLs1", "newLs2"],
    )
    import json as _json

    body: list[dict[str, Any]] = _json.loads(route.calls.last.request.read())
    assert body == [
        {"op": "replace", "path": "/legendSets", "value": [{"id": "newLs1"}, {"id": "newLs2"}]},
    ]


@respx.mock
async def test_bulk_retag_dry_run_does_not_patch(pat_profile: None) -> None:  # noqa: ARG001
    """Bulk retag dry run does not patch."""
    _mock_preamble()
    respx.get("https://dhis2.example/api/dataElements").mock(
        return_value=httpx.Response(
            200,
            json={"dataElements": [{"id": "DE_A", "categoryCombo": {"id": "ccOld"}}]},
        ),
    )
    patch_route = respx.patch("https://dhis2.example/api/dataElements/DE_A").mock(
        return_value=httpx.Response(200, json={}),
    )
    from dhis2w_core.profile import resolve_profile

    result = await service.bulk_retag_metadata(
        resolve_profile("probe"),
        "dataElements",
        category_combo_uid="ccNew",
        dry_run=True,
    )
    assert result.dry_run is True
    assert result.patch_result is None
    assert patch_route.called is False


async def test_bulk_retag_requires_at_least_one_mutation() -> None:
    """Bulk retag requires at least one mutation."""
    with pytest.raises(ValueError, match="at least one of"):
        await service.bulk_retag_metadata(
            profile=None,  # type: ignore[arg-type]  # raise before use
            resource="dataElements",
        )


async def test_bulk_retag_conflicting_option_flags_raise() -> None:
    """Bulk retag conflicting option flags raise."""
    with pytest.raises(ValueError, match="option_set_uid / clear_option_set"):
        await service.bulk_retag_metadata(
            profile=None,  # type: ignore[arg-type]  # raise before use
            resource="dataElements",
            option_set_uid="x",
            clear_option_set=True,
        )


# ---- CLI surface -----------------------------------------------------------


def _fake_result() -> BulkRetagResult:
    return BulkRetagResult(
        resource="dataElements",
        dry_run=False,
        matched=1,
        entries=[
            BulkRetagEntry(
                uid="DE_A",
                before={"/categoryCombo": "ccOld"},
                after={"/categoryCombo": "ccNew"},
            ),
        ],
        patch_result=BulkPatchResult(successful_uids=["DE_A"], failures=[]),
    )


def test_retag_cli_rejects_empty_mutation(pat_profile: None) -> None:  # noqa: ARG001
    """Retag cli rejects empty mutation."""
    result = CliRunner().invoke(build_app(), ["metadata", "retag", "dataElements"])
    assert result.exit_code != 0
    assert "at least one of" in result.output


def test_retag_cli_renders_before_after_table(pat_profile: None) -> None:  # noqa: ARG001
    """Retag cli renders before after table."""
    mock = AsyncMock(return_value=_fake_result())
    with patch("dhis2w_core.v42.plugins.metadata.service.bulk_retag_metadata", new=mock):
        result = CliRunner().invoke(
            build_app(),
            ["metadata", "retag", "dataElements", "--category-combo", "ccNew"],
        )
    assert result.exit_code == 0, result.output
    assert "/categoryCombo" in result.output
    assert "ccOld" in result.output
    assert "ccNew" in result.output
    assert "applied 1 retag" in result.output
    assert mock.await_args is not None
    assert mock.await_args.kwargs["category_combo_uid"] == "ccNew"


def test_retag_cli_forwards_repeated_legend_set_flag(pat_profile: None) -> None:  # noqa: ARG001
    """Retag cli forwards repeated legend set flag."""
    mock = AsyncMock(return_value=_fake_result())
    with patch("dhis2w_core.v42.plugins.metadata.service.bulk_retag_metadata", new=mock):
        result = CliRunner().invoke(
            build_app(),
            [
                "metadata",
                "retag",
                "dataElements",
                "--legend-set",
                "LS1",
                "--legend-set",
                "LS2",
            ],
        )
    assert result.exit_code == 0, result.output
    assert mock.await_args is not None
    assert mock.await_args.kwargs["legend_set_uids"] == ["LS1", "LS2"]


def test_retag_cli_dry_run_banner(pat_profile: None) -> None:  # noqa: ARG001
    """Retag cli dry run banner."""
    dry = _fake_result().model_copy(update={"dry_run": True, "patch_result": None})
    with patch("dhis2w_core.v42.plugins.metadata.service.bulk_retag_metadata", new=AsyncMock(return_value=dry)):
        result = CliRunner().invoke(
            build_app(),
            ["metadata", "retag", "dataElements", "--category-combo", "cc", "--dry-run"],
        )
    assert result.exit_code == 0, result.output
    assert "dry-run" in result.output


def test_retag_cli_renders_no_match_message(pat_profile: None) -> None:  # noqa: ARG001
    """Retag cli renders no match message."""
    empty = BulkRetagResult(resource="dataElements", dry_run=False, matched=0, entries=[])
    with patch("dhis2w_core.v42.plugins.metadata.service.bulk_retag_metadata", new=AsyncMock(return_value=empty)):
        result = CliRunner().invoke(
            build_app(),
            ["metadata", "retag", "dataElements", "--category-combo", "cc"],
        )
    assert result.exit_code == 0, result.output
    assert "no dataElements matched" in result.output
