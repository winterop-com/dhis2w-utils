"""Unit tests for `d2w metadata rename` bulk-rename verb + its service layer."""

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
from dhis2w_core.v42.plugins.metadata.service import BulkRenameResult
from typer.testing import CliRunner


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


# ---- service.bulk_rename_metadata ------------------------------------------


@respx.mock
async def test_bulk_rename_prefixes_and_patches(pat_profile: None) -> None:  # noqa: ARG001
    """Bulk rename prefixes and patches."""
    _mock_preamble()
    respx.get("https://dhis2.example/api/dataElements").mock(
        return_value=httpx.Response(
            200,
            json={
                "dataElements": [
                    {"id": "DE_A", "name": "ANC visits", "shortName": "ANCv"},
                    {"id": "DE_B", "name": "BCG doses", "shortName": "BCGd"},
                ],
            },
        ),
    )
    patch_a = respx.patch("https://dhis2.example/api/dataElements/DE_A").mock(return_value=httpx.Response(200, json={}))
    patch_b = respx.patch("https://dhis2.example/api/dataElements/DE_B").mock(return_value=httpx.Response(200, json={}))

    from dhis2w_core.profile import resolve_profile

    profile = resolve_profile("probe")
    result = await service.bulk_rename_metadata(
        profile,
        "dataElements",
        filters=["name:like:visits"],
        name_prefix="[MoH] ",
    )
    assert result.matched == 2
    assert result.dry_run is False
    assert result.entries[0].name_after == "[MoH] ANC visits"
    assert result.entries[1].name_after == "[MoH] BCG doses"
    assert patch_a.called and patch_b.called
    assert result.patch_result is not None
    assert sorted(result.patch_result.successful_uids) == ["DE_A", "DE_B"]


@respx.mock
async def test_bulk_rename_dry_run_does_not_patch(pat_profile: None) -> None:  # noqa: ARG001
    """Bulk rename dry run does not patch."""
    _mock_preamble()
    respx.get("https://dhis2.example/api/dataElements").mock(
        return_value=httpx.Response(
            200,
            json={"dataElements": [{"id": "DE_A", "name": "ANC visits", "shortName": "ANCv"}]},
        ),
    )
    patch_route = respx.patch("https://dhis2.example/api/dataElements/DE_A").mock(
        return_value=httpx.Response(200, json={}),
    )
    from dhis2w_core.profile import resolve_profile

    profile = resolve_profile("probe")
    result = await service.bulk_rename_metadata(
        profile,
        "dataElements",
        name_prefix="[MoH] ",
        dry_run=True,
    )
    assert result.dry_run is True
    assert result.matched == 1
    assert result.patch_result is None
    assert patch_route.called is False


@respx.mock
async def test_bulk_rename_idempotent_prefix_skips_already_prefixed(pat_profile: None) -> None:  # noqa: ARG001
    """Bulk rename idempotent prefix skips already prefixed."""
    _mock_preamble()
    respx.get("https://dhis2.example/api/dataElements").mock(
        return_value=httpx.Response(
            200,
            json={
                "dataElements": [
                    {"id": "DE_A", "name": "[MoH] ANC visits"},
                    {"id": "DE_B", "name": "BCG doses"},
                ],
            },
        ),
    )
    patch_b = respx.patch("https://dhis2.example/api/dataElements/DE_B").mock(return_value=httpx.Response(200, json={}))
    patch_a = respx.patch("https://dhis2.example/api/dataElements/DE_A").mock(return_value=httpx.Response(200, json={}))

    from dhis2w_core.profile import resolve_profile

    profile = resolve_profile("probe")
    result = await service.bulk_rename_metadata(
        profile,
        "dataElements",
        name_prefix="[MoH] ",
        allow_all=True,
    )
    # Only DE_B changes; DE_A was already prefixed so no op is planned.
    assert result.matched == 1
    assert result.entries[0].uid == "DE_B"
    assert patch_a.called is False
    assert patch_b.called is True


@respx.mock
async def test_bulk_rename_forwards_filter_and_root_junction(pat_profile: None) -> None:  # noqa: ARG001
    """Bulk rename forwards filter and root junction."""
    _mock_preamble()
    route = respx.get("https://dhis2.example/api/dataElements").mock(
        return_value=httpx.Response(200, json={"dataElements": []}),
    )
    from dhis2w_core.profile import resolve_profile

    profile = resolve_profile("probe")
    await service.bulk_rename_metadata(
        profile,
        "dataElements",
        filters=["name:like:ANC", "code:eq:DE_X"],
        root_junction="OR",
        name_prefix="ignored",
    )
    params = route.calls.last.request.url.params
    assert params.get_list("filter") == ["name:like:ANC", "code:eq:DE_X"]
    assert params["rootJunction"] == "OR"


async def test_bulk_rename_requires_at_least_one_mutation() -> None:
    """Bulk rename requires at least one mutation."""
    with pytest.raises(ValueError, match="at least one of"):
        await service.bulk_rename_metadata(
            profile=None,  # type: ignore[arg-type]  # value is unused before the raise
            resource="dataElements",
        )


@respx.mock
async def test_bulk_rename_strip_prefix_removes_only_matching_rows(pat_profile: None) -> None:  # noqa: ARG001
    """Bulk rename strip prefix removes only matching rows."""
    _mock_preamble()
    respx.get("https://dhis2.example/api/dataElements").mock(
        return_value=httpx.Response(
            200,
            json={
                "dataElements": [
                    {"id": "DE_A", "name": "[MoH] ANC visits"},
                    {"id": "DE_B", "name": "BCG doses"},
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

    result = await service.bulk_rename_metadata(
        resolve_profile("probe"),
        "dataElements",
        name_strip_prefix="[MoH] ",
        allow_all=True,
    )
    assert result.matched == 1
    assert result.entries[0].uid == "DE_A"
    assert result.entries[0].name_before == "[MoH] ANC visits"
    assert result.entries[0].name_after == "ANC visits"
    assert patch_a.called
    assert patch_b.called is False


@respx.mock
async def test_bulk_rename_strip_then_add_rewrites_prefix(pat_profile: None) -> None:  # noqa: ARG001
    """Bulk rename strip then add rewrites prefix."""
    _mock_preamble()
    respx.get("https://dhis2.example/api/dataElements").mock(
        return_value=httpx.Response(
            200,
            json={"dataElements": [{"id": "DE_A", "name": "[old] ANC visits"}]},
        ),
    )
    route = respx.patch("https://dhis2.example/api/dataElements/DE_A").mock(
        return_value=httpx.Response(200, json={}),
    )
    from dhis2w_core.profile import resolve_profile

    result = await service.bulk_rename_metadata(
        resolve_profile("probe"),
        "dataElements",
        name_strip_prefix="[old] ",
        name_prefix="[new] ",
        allow_all=True,
    )
    import json as _json

    body: list[dict[str, Any]] = _json.loads(route.calls.last.request.read())
    assert body[0]["value"] == "[new] ANC visits"
    assert result.entries[0].name_after == "[new] ANC visits"


@respx.mock
async def test_bulk_rename_strip_suffix_idempotent_when_absent(pat_profile: None) -> None:  # noqa: ARG001
    """Bulk rename strip suffix idempotent when absent."""
    _mock_preamble()
    respx.get("https://dhis2.example/api/dataElements").mock(
        return_value=httpx.Response(
            200,
            json={"dataElements": [{"id": "DE_A", "name": "ANC visits"}]},
        ),
    )
    patch_a = respx.patch("https://dhis2.example/api/dataElements/DE_A").mock(
        return_value=httpx.Response(200, json={}),
    )
    from dhis2w_core.profile import resolve_profile

    result = await service.bulk_rename_metadata(
        resolve_profile("probe"),
        "dataElements",
        name_strip_suffix=" (retired)",
        allow_all=True,
    )
    # Nothing to strip; no patch called.
    assert result.matched == 0
    assert patch_a.called is False


def test_rename_cli_strip_prefix_forwards_flag(pat_profile: None) -> None:  # noqa: ARG001
    """Rename cli strip prefix forwards flag."""
    mock = AsyncMock(return_value=_fake_result())
    with patch("dhis2w_core.v42.plugins.metadata.service.bulk_rename_metadata", new=mock):
        result = CliRunner().invoke(
            build_app(),
            [
                "metadata",
                "rename",
                "dataElements",
                "--filter",
                "code:like:DE_",
                "--name-strip-prefix",
                "[old] ",
                "--name-prefix",
                "[new] ",
            ],
        )
    assert result.exit_code == 0, result.output
    assert mock.await_args is not None
    kwargs = mock.await_args.kwargs
    assert kwargs["name_strip_prefix"] == "[old] "
    assert kwargs["name_prefix"] == "[new] "


# ---- CLI surface -----------------------------------------------------------


def _fake_result() -> BulkRenameResult:
    return BulkRenameResult(
        resource="dataElements",
        dry_run=False,
        matched=2,
        entries=[
            service.BulkRenameEntry(
                uid="DE_A",
                name_before="ANC visits",
                name_after="[MoH] ANC visits",
                short_name_before="ANCv",
                short_name_after="ANCv",
            ),
            service.BulkRenameEntry(
                uid="DE_B",
                name_before="BCG doses",
                name_after="[MoH] BCG doses",
                short_name_before="BCGd",
                short_name_after="BCGd",
            ),
        ],
        patch_result=BulkPatchResult(successful_uids=["DE_A", "DE_B"], failures=[]),
    )


def test_rename_cli_rejects_empty_mutation(pat_profile: None) -> None:  # noqa: ARG001
    """Rename cli rejects empty mutation."""
    result = CliRunner().invoke(build_app(), ["metadata", "rename", "dataElements"])
    assert result.exit_code != 0
    assert "at least one of" in result.output


def test_rename_cli_renders_before_after_table(pat_profile: None) -> None:  # noqa: ARG001
    """Rename cli renders before after table."""
    mock = AsyncMock(return_value=_fake_result())
    with patch("dhis2w_core.v42.plugins.metadata.service.bulk_rename_metadata", new=mock):
        result = CliRunner().invoke(
            build_app(),
            [
                "metadata",
                "rename",
                "dataElements",
                "--filter",
                "code:like:DE_",
                "--name-prefix",
                "[MoH] ",
            ],
        )
    assert result.exit_code == 0, result.output
    assert "ANC visits" in result.output
    assert "[MoH] ANC visits" in result.output
    assert "applied 2 renames" in result.output
    assert mock.await_args is not None
    kwargs = mock.await_args.kwargs
    assert kwargs["filters"] == ["code:like:DE_"]
    assert kwargs["name_prefix"] == "[MoH] "
    assert kwargs["dry_run"] is False


def test_rename_cli_dry_run_prints_preview(pat_profile: None) -> None:  # noqa: ARG001
    """Rename cli dry run prints preview."""
    dry = _fake_result().model_copy(update={"dry_run": True, "patch_result": None})
    with patch("dhis2w_core.v42.plugins.metadata.service.bulk_rename_metadata", new=AsyncMock(return_value=dry)):
        result = CliRunner().invoke(
            build_app(),
            ["metadata", "rename", "dataElements", "--name-prefix", "[MoH] ", "--dry-run"],
        )
    assert result.exit_code == 0, result.output
    assert "dry-run" in result.output
    assert "drop --dry-run to apply" in result.output


def test_rename_cli_renders_no_match_message(pat_profile: None) -> None:  # noqa: ARG001
    """Rename cli renders no match message."""
    empty = BulkRenameResult(resource="dataElements", dry_run=False, matched=0, entries=[])
    with patch("dhis2w_core.v42.plugins.metadata.service.bulk_rename_metadata", new=AsyncMock(return_value=empty)):
        result = CliRunner().invoke(
            build_app(),
            ["metadata", "rename", "dataElements", "--filter", "code:like:DE_", "--name-prefix", "X"],
        )
    assert result.exit_code == 0, result.output
    assert "no dataElements matched" in result.output


def test_rename_cli_emits_json_when_requested(pat_profile: None) -> None:  # noqa: ARG001
    """Rename cli emits json when requested."""
    mock = AsyncMock(return_value=_fake_result())
    with patch("dhis2w_core.v42.plugins.metadata.service.bulk_rename_metadata", new=mock):
        result = CliRunner().invoke(
            build_app(),
            ["--json", "metadata", "rename", "dataElements", "--filter", "code:like:DE_", "--name-prefix", "[MoH] "],
        )
    assert result.exit_code == 0, result.output
    import json as _json

    payload: dict[str, Any] = _json.loads(result.output)
    assert payload["resource"] == "dataElements"
    assert payload["matched"] == 2
    assert len(payload["entries"]) == 2


def test_rename_cli_refuses_no_filter_without_all(pat_profile: None) -> None:  # noqa: ARG001
    """A no-filter live rename is refused unless --all opts in; the service is never called."""
    mock = AsyncMock(return_value=_fake_result())
    with patch("dhis2w_core.v42.plugins.metadata.service.bulk_rename_metadata", new=mock):
        result = CliRunner().invoke(build_app(), ["metadata", "rename", "dataElements", "--name-prefix", "[X] "])
    assert result.exit_code != 0
    assert "refusing to rename every dataElements" in result.output
    assert mock.await_count == 0


def test_rename_cli_all_yes_opts_into_catalog_wide(pat_profile: None) -> None:  # noqa: ARG001
    """--all --yes forwards allow_all=True and skips the confirmation prompt."""
    mock = AsyncMock(return_value=_fake_result())
    with patch("dhis2w_core.v42.plugins.metadata.service.bulk_rename_metadata", new=mock):
        result = CliRunner().invoke(
            build_app(),
            ["metadata", "rename", "dataElements", "--name-prefix", "[X] ", "--all", "--yes"],
        )
    assert result.exit_code == 0, result.output
    assert mock.await_args is not None
    assert mock.await_args.kwargs["allow_all"] is True


def test_rename_cli_all_without_yes_aborts_on_no(pat_profile: None) -> None:  # noqa: ARG001
    """--all without --yes prompts for confirmation; answering 'n' aborts without calling the service."""
    mock = AsyncMock(return_value=_fake_result())
    with patch("dhis2w_core.v42.plugins.metadata.service.bulk_rename_metadata", new=mock):
        result = CliRunner().invoke(
            build_app(),
            ["metadata", "rename", "dataElements", "--name-prefix", "[X] ", "--all"],
            input="n\n",
        )
    assert result.exit_code != 0
    assert mock.await_count == 0
