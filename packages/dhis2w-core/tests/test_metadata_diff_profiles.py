"""Tests for `service.diff_profiles` + `d2w metadata diff-profiles` CLI."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from dhis2w_cli.main import build_app
from dhis2w_core.v42.plugins.metadata import service
from dhis2w_core.v42.plugins.metadata.models import MetadataBundle
from typer.testing import CliRunner


def _de(uid: str, *, name: str, **extra: Any) -> dict[str, Any]:
    """Build a minimal data element dict with the noisy fields pre-filled."""
    row: dict[str, Any] = {
        "id": uid,
        "name": name,
        "lastUpdated": "2026-01-01T00:00:00.000",  # noise — ignored by default
        "createdBy": {"id": "noisy", "name": "noisy"},  # noise
    }
    row.update(extra)
    return row


def _bundle(raw: dict[str, Any]) -> MetadataBundle:
    """Shortcut: typed MetadataBundle from a raw-dict fixture."""
    return MetadataBundle.from_raw(raw)


@pytest.fixture
def profiles_toml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Write a global profiles.toml with two PAT profiles and point resolution at it."""
    config_dir = tmp_path / ".config" / "dhis2"
    config_dir.mkdir(parents=True)
    path = config_dir / "profiles.toml"
    path.write_text(
        "[profiles.stage]\n"
        'base_url = "http://stage.example"\n'
        'auth = "pat"\n'
        'token = "stage-token"\n'
        "\n"
        "[profiles.prod]\n"
        'base_url = "http://prod.example"\n'
        'auth = "pat"\n'
        'token = "prod-token"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / ".config"))
    monkeypatch.delenv("DHIS2_PROFILE", raising=False)
    monkeypatch.delenv("DHIS2_URL", raising=False)
    monkeypatch.delenv("DHIS2_PAT", raising=False)
    # Chdir into tmp_path so the profile resolver's project-local walk-up
    # (`.dhis2/profiles.toml` searched from CWD upward, per CLAUDE.md #1)
    # finds nothing and falls through to the global stub we just wrote.
    # Otherwise a `<repo>/.dhis2/profiles.toml` left behind by `make
    # dhis2-run` shadows the fixture.
    monkeypatch.chdir(tmp_path)
    return path


# ---- service layer -------------------------------------------------


async def test_service_diff_profiles_runs_exports_concurrently_and_diffs() -> None:
    """`diff_profiles` fans out two `export_metadata` calls and returns a typed `MetadataDiff`."""
    bundle_a = _bundle({"dataElements": [_de("u1", name="A"), _de("u2", name="Same")]})
    bundle_b = _bundle({"dataElements": [_de("u1", name="B"), _de("u2", name="Same")]})
    exports: list[dict[str, Any]] = []

    async def fake_export(
        profile: Any,
        *,
        resources: list[str] | None = None,
        fields: str | None = None,
        per_resource_filters: Any = None,
        **_: Any,
    ) -> MetadataBundle:
        exports.append(
            {
                "base_url": profile.base_url,
                "resources": resources,
                "fields": fields,
                "filters": per_resource_filters,
            }
        )
        return bundle_a if profile.base_url == "http://stage.example" else bundle_b

    from dhis2w_core.profile import Profile

    profile_a = Profile(base_url="http://stage.example", auth="pat", token="t")
    profile_b = Profile(base_url="http://prod.example", auth="pat", token="t")

    with patch("dhis2w_core.v42.plugins.metadata.service.export_metadata", fake_export):
        diff = await service.diff_profiles(
            profile_a,
            profile_b,
            resources=["dataElements"],
            per_resource_filters={"dataElements": ["name:like:A"]},
        )

    assert len(exports) == 2
    # Both sides saw the same filter — comparison is apples-to-apples.
    assert all(export["filters"] == {"dataElements": ["name:like:A"]} for export in exports)
    assert {export["base_url"] for export in exports} == {"http://stage.example", "http://prod.example"}
    # The bundles differ only on u1's name — noise on u2 ignored.
    assert diff.total_updated == 1
    assert diff.resources[0].updated[0].id == "u1"


async def test_service_diff_profiles_requires_resources_list() -> None:
    """Empty `resources` raises — there's no sensible default for a cross-instance diff."""
    from dhis2w_core.profile import Profile

    profile = Profile(base_url="http://x.example", auth="pat", token="t")
    with pytest.raises(ValueError, match="at least one resource"):
        await service.diff_profiles(profile, profile, resources=[])


# ---- CLI parsing ---------------------------------------------------


def test_cli_diff_profiles_rejects_missing_resources(profiles_toml: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Running without `-r` is a BadParameter (no whole-instance diff)."""
    result = CliRunner().invoke(build_app(), ["metadata", "diff-profiles", "stage", "prod"])
    assert result.exit_code != 0
    assert "resource" in result.output.lower()


def test_cli_diff_profiles_unknown_profile_surfaces_clean_error(
    profiles_toml: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Unknown profile names produce a BadParameter, not a traceback."""
    result = CliRunner().invoke(
        build_app(),
        ["metadata", "diff-profiles", "stage", "missing-profile", "-r", "dataElements"],
    )
    assert result.exit_code != 0
    assert "missing-profile" in result.output or "unknown" in result.output.lower()


def test_cli_diff_profiles_happy_path_renders_table(profiles_toml: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Resolves both profiles, calls `diff_profiles`, renders a table."""
    fake_diff = service.MetadataDiff(
        left_label="stage",
        right_label="prod",
        resources=[
            service.ResourceDiff(
                resource="dataElements",
                created=[service.ObjectChange(id="new-de", name="new")],
                updated=[],
                deleted=[],
                unchanged_count=2,
            )
        ],
        ignored_fields=["lastUpdated"],
    )
    mock = AsyncMock(return_value=fake_diff)
    with patch("dhis2w_core.v42.plugins.metadata.service.diff_profiles", mock):
        result = CliRunner().invoke(
            build_app(),
            ["metadata", "diff-profiles", "stage", "prod", "-r", "dataElements"],
        )
    assert result.exit_code == 0, result.output
    assert "dataElements" in result.output
    # Per-resource filter was empty -> passed through as {}
    _, kwargs = mock.call_args
    assert kwargs["per_resource_filters"] == {}
    assert kwargs["resources"] == ["dataElements"]
    assert kwargs["left_label"] == "stage"
    assert kwargs["right_label"] == "prod"


def test_cli_diff_profiles_parses_per_resource_filter(profiles_toml: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`--filter resource:prop:op:val` lands in `per_resource_filters`."""
    mock = AsyncMock(return_value=service.MetadataDiff(left_label="stage", right_label="prod"))
    with patch("dhis2w_core.v42.plugins.metadata.service.diff_profiles", mock):
        result = CliRunner().invoke(
            build_app(),
            [
                "metadata",
                "diff-profiles",
                "stage",
                "prod",
                "-r",
                "dataElements",
                "-r",
                "indicators",
                "--filter",
                "dataElements:name:like:ANC",
                "--filter",
                "dataElements:code:eq:X",
                "--filter",
                "indicators:name:like:ANC",
            ],
        )
    assert result.exit_code == 0, result.output
    _, kwargs = mock.call_args
    assert kwargs["per_resource_filters"] == {
        "dataElements": ["name:like:ANC", "code:eq:X"],
        "indicators": ["name:like:ANC"],
    }


def test_cli_diff_profiles_rejects_malformed_filter(profiles_toml: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A `--filter` without the resource prefix errors out before any network call."""
    result = CliRunner().invoke(
        build_app(),
        [
            "metadata",
            "diff-profiles",
            "stage",
            "prod",
            "-r",
            "dataElements",
            "--filter",
            "bogus",
        ],
    )
    assert result.exit_code != 0
    assert "filter" in result.output.lower()


def test_cli_diff_profiles_exit_on_drift_flags_nonzero(profiles_toml: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`--exit-on-drift` turns a non-empty diff into exit 1."""
    drifted = service.MetadataDiff(
        left_label="stage",
        right_label="prod",
        resources=[
            service.ResourceDiff(
                resource="dataElements",
                created=[service.ObjectChange(id="new", name="new")],
            )
        ],
    )
    mock = AsyncMock(return_value=drifted)
    with patch("dhis2w_core.v42.plugins.metadata.service.diff_profiles", mock):
        result = CliRunner().invoke(
            build_app(),
            ["metadata", "diff-profiles", "stage", "prod", "-r", "dataElements", "--exit-on-drift"],
        )
    assert result.exit_code == 1, result.output


def test_cli_diff_profiles_exit_on_drift_no_diff_exits_zero(
    profiles_toml: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Clean diff + `--exit-on-drift` still exits 0."""
    clean = service.MetadataDiff(left_label="stage", right_label="prod")
    mock = AsyncMock(return_value=clean)
    with patch("dhis2w_core.v42.plugins.metadata.service.diff_profiles", mock):
        result = CliRunner().invoke(
            build_app(),
            ["metadata", "diff-profiles", "stage", "prod", "-r", "dataElements", "--exit-on-drift"],
        )
    assert result.exit_code == 0, result.output


def test_cli_diff_profiles_json_output_is_parseable(profiles_toml: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`--json` emits a valid MetadataDiff; no Rich table on stdout."""
    diff = service.MetadataDiff(
        left_label="stage",
        right_label="prod",
        resources=[service.ResourceDiff(resource="dataElements", created=[service.ObjectChange(id="u1", name="x")])],
    )
    mock = AsyncMock(return_value=diff)
    with patch("dhis2w_core.v42.plugins.metadata.service.diff_profiles", mock):
        result = CliRunner().invoke(
            build_app(),
            ["--json", "metadata", "diff-profiles", "stage", "prod", "-r", "dataElements"],
        )
    assert result.exit_code == 0, result.output
    # CliRunner merges stderr into result.output by default. Split at the first `{`
    # to skip the stderr progress line and parse the JSON body.
    json_body = result.output[result.output.index("{") :]
    reloaded = service.MetadataDiff.model_validate(json.loads(json_body))
    assert reloaded.total_created == 1
