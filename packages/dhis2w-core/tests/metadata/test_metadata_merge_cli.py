"""Tests for the `d2w metadata merge` CLI conflict-rendering path."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from dhis2w_cli.main import build_app
from dhis2w_client import WebMessageResponse
from dhis2w_core.v42.plugins.metadata import service
from typer.testing import CliRunner


@pytest.fixture
def profiles_toml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Write a profiles.toml with two PAT profiles so CliRunner has something to resolve."""
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
    return path


def _merge_result_with_conflicts() -> service.MergeResult:
    """Build a `MergeResult` whose import_report carries two metadata-shape conflicts."""
    envelope = WebMessageResponse.model_validate(
        {
            "status": "ERROR",
            "response": {
                "stats": {"ignored": 2, "created": 0, "updated": 0, "deleted": 0, "total": 2},
                "typeReports": [
                    {
                        "klass": "org.hisp.dhis.dataelement.DataElement",
                        "stats": {"ignored": 1, "total": 1},
                        "objectReports": [
                            {
                                "klass": "org.hisp.dhis.dataelement.DataElement",
                                "uid": "deUidAAA0001",
                                "index": 0,
                                "errorReports": [
                                    {
                                        "errorCode": "E4003",
                                        "message": "Property `valueType` is required",
                                        "errorProperty": "valueType",
                                    },
                                ],
                            }
                        ],
                    },
                    {
                        "klass": "org.hisp.dhis.organisationunit.OrganisationUnit",
                        "stats": {"ignored": 1, "total": 1},
                        "objectReports": [
                            {
                                "klass": "org.hisp.dhis.organisationunit.OrganisationUnit",
                                "uid": "ouUidAAA0001",
                                "index": 0,
                                "errorReports": [
                                    {
                                        "errorCode": "E5002",
                                        "message": "Parent org unit `xyz` does not exist",
                                        "errorProperty": "parent",
                                    },
                                ],
                            }
                        ],
                    },
                ],
            },
        },
    )
    return service.MergeResult(
        source_base_url="http://stage.example",
        target_base_url="http://prod.example",
        resources=["dataElements", "organisationUnits"],
        dry_run=True,
        export_counts={"dataElements": 1, "organisationUnits": 1},
        import_report=envelope,
    )


def test_cli_merge_dry_run_renders_conflict_table(profiles_toml: Path) -> None:
    """`--dry-run` with conflicts renders them through the shared Rich table.

    Before the fix: the handler just said `conflicts: N — re-run with --json`
    and dropped the detail. After: the shared `render_conflicts` renderer
    used by `metadata import` prints a per-row table with resource, UID,
    property, errorCode, and message.
    """
    mock = AsyncMock(return_value=_merge_result_with_conflicts())
    with patch("dhis2w_core.v42.plugins.metadata.service.merge_metadata", mock):
        result = CliRunner().invoke(
            build_app(),
            ["metadata", "merge", "stage", "prod", "-r", "dataElements", "--dry-run"],
        )

    assert result.exit_code == 0, result.output
    assert "DRY RUN" in result.output
    assert "conflicts: 2" in result.output
    # Renderer emits resource names (shortened from klass) + errorCodes +
    # truncated messages in a Rich table.
    assert "DataElement" in result.output
    assert "OrganisationUnit" in result.output
    assert "E4003" in result.output
    assert "E5002" in result.output


def test_cli_merge_clean_run_skips_conflict_table(profiles_toml: Path) -> None:
    """When the import_report carries no errors, no conflict block is rendered."""
    envelope = WebMessageResponse.model_validate(
        {
            "status": "OK",
            "response": {
                "stats": {"ignored": 0, "created": 3, "updated": 0, "deleted": 0, "total": 3},
            },
        },
    )
    clean = service.MergeResult(
        source_base_url="http://stage.example",
        target_base_url="http://prod.example",
        resources=["dataElements"],
        dry_run=False,
        export_counts={"dataElements": 3},
        import_report=envelope,
    )
    with patch("dhis2w_core.v42.plugins.metadata.service.merge_metadata", AsyncMock(return_value=clean)):
        result = CliRunner().invoke(
            build_app(),
            ["metadata", "merge", "stage", "prod", "-r", "dataElements"],
        )

    assert result.exit_code == 0, result.output
    assert "APPLIED" in result.output
    assert "conflicts" not in result.output
