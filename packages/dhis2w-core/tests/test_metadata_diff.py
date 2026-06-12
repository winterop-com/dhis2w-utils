"""Tests for `service.diff_bundles` + `d2w metadata diff` CLI + `metadata_diff` MCP tool."""

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


def _bundle(raw: dict[str, Any]) -> MetadataBundle:
    """Shortcut: build a typed MetadataBundle from a literal raw-dict fixture."""
    return MetadataBundle.from_raw(raw)


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _de(uid: str, *, name: str, code: str | None = None, **extra: object) -> dict[str, object]:
    """Build a minimal data element dict; timestamps default to the 'noisy' values that must be ignored."""
    row: dict[str, object] = {
        "id": uid,
        "name": name,
        "lastUpdated": "2026-04-19T10:00:00Z",
        "createdBy": {"id": "someuser"},
    }
    if code is not None:
        row["code"] = code
    row.update(extra)
    return row


def test_diff_bundles_created_updated_deleted_and_unchanged() -> None:
    """The classifier puts each UID into exactly one bucket across a realistic mixed bundle."""
    left = {
        "date": "2026-04-18",
        "system": {"version": "2.42"},
        "dataElements": [
            _de("keepSame001", name="Stable"),
            _de("renameEnm1", name="Old name", code="CODE_A"),
            _de("deleteMe01", name="Going away"),
        ],
    }
    right = {
        "date": "2026-04-19",
        "dataElements": [
            _de("keepSame001", name="Stable"),
            _de("renameEnm1", name="New name", code="CODE_A"),
            _de("newOne00001", name="Fresh"),
        ],
    }
    diff = service.diff_bundles(_bundle(left), _bundle(right), left_label="baseline", right_label="candidate")
    assert [r.resource for r in diff.resources] == ["dataElements"]
    data_diff = diff.resources[0]
    assert [c.id for c in data_diff.created] == ["newOne00001"]
    assert [c.id for c in data_diff.deleted] == ["deleteMe01"]
    assert [c.id for c in data_diff.updated] == ["renameEnm1"]
    assert data_diff.updated[0].changed_fields == ["name"]
    assert data_diff.unchanged_count == 1
    assert diff.total_created == 1
    assert diff.total_updated == 1
    assert diff.total_deleted == 1
    assert diff.total_unchanged == 1
    assert diff.left_label == "baseline"
    assert diff.right_label == "candidate"


def test_diff_bundles_default_ignores_lastupdated_and_createdby() -> None:
    """Round-trip noise (timestamps, createdBy) is ignored by default — no false-positive 'updated'."""
    left = {"dataElements": [_de("sameAsAsame", name="Constant")]}
    right = {
        "dataElements": [
            {
                "id": "sameAsAsame",
                "name": "Constant",
                "lastUpdated": "2099-01-01T00:00:00Z",  # different timestamp
                "createdBy": {"id": "differentuser"},  # different creator
            }
        ],
    }
    diff = service.diff_bundles(_bundle(left), _bundle(right))
    assert diff.total_updated == 0
    assert diff.resources[0].unchanged_count == 1


def test_diff_bundles_custom_ignore_fields_extend_defaults() -> None:
    """Custom `ignored_fields` is the authoritative set — caller can drop defaults or extend."""
    left = {"dataElements": [_de("someUid0001", name="A", code="X")]}
    right = {"dataElements": [_de("someUid0001", name="A", code="Y")]}
    # Default: code is a real change.
    default_diff = service.diff_bundles(_bundle(left), _bundle(right))
    assert default_diff.total_updated == 1
    assert default_diff.resources[0].updated[0].changed_fields == ["code"]
    # Explicit ignore-code → unchanged.
    custom = frozenset({*service._DEFAULT_IGNORED_FIELDS, "code"})
    hidden_diff = service.diff_bundles(_bundle(left), _bundle(right), ignored_fields=custom)
    assert hidden_diff.total_updated == 0


def test_diff_bundles_handles_resources_only_on_one_side() -> None:
    """A resource type missing on left shows up entirely as 'created'; missing-on-right as 'deleted'."""
    left = {"dataElements": [_de("leftOnly001", name="L")]}
    right = {"indicators": [_de("rightOnly01", name="R")]}
    diff = service.diff_bundles(_bundle(left), _bundle(right))
    by_name = {r.resource: r for r in diff.resources}
    assert by_name["dataElements"].total_changed == 1
    assert len(by_name["dataElements"].deleted) == 1
    assert by_name["indicators"].total_changed == 1
    assert len(by_name["indicators"].created) == 1


def test_cli_diff_two_files_success(runner: CliRunner, tmp_path: Path) -> None:
    """CLI with two positional bundle files prints a table and exits 0."""
    left = tmp_path / "left.json"
    right = tmp_path / "right.json"
    left.write_text(json.dumps({"dataElements": [_de("u1", name="A")]}), encoding="utf-8")
    right.write_text(json.dumps({"dataElements": [_de("u1", name="B")]}), encoding="utf-8")
    result = runner.invoke(build_app(), ["metadata", "diff", str(left), str(right)])
    assert result.exit_code == 0, result.output
    assert "dataElements" in result.output
    assert "1 updated" in result.output or "~1 updated" in result.output


def test_cli_diff_json_output_is_parseable_metadatadiff(runner: CliRunner, tmp_path: Path) -> None:
    """`--json` must emit a valid `MetadataDiff` that round-trips through `model_validate`."""
    left = tmp_path / "a.json"
    right = tmp_path / "b.json"
    left.write_text(json.dumps({"dataElements": [_de("u1", name="A")]}), encoding="utf-8")
    right.write_text(json.dumps({"dataElements": [_de("u1", name="B")]}), encoding="utf-8")
    result = runner.invoke(build_app(), ["--json", "metadata", "diff", str(left), str(right)])
    assert result.exit_code == 0, result.output
    parsed = json.loads(result.output)
    reloaded = service.MetadataDiff.model_validate(parsed)
    assert reloaded.total_updated == 1
    assert reloaded.resources[0].updated[0].id == "u1"


def test_cli_diff_rejects_both_positional_right_and_live(runner: CliRunner, tmp_path: Path) -> None:
    """`--live` + a positional right bundle is an error — exactly one right-hand source."""
    left = tmp_path / "a.json"
    right = tmp_path / "b.json"
    left.write_text("{}", encoding="utf-8")
    right.write_text("{}", encoding="utf-8")
    result = runner.invoke(build_app(), ["metadata", "diff", str(left), str(right), "--live"])
    assert result.exit_code != 0
    assert "live" in result.output.lower() or "exactly one" in result.output.lower()


def test_cli_diff_live_flag_calls_instance_compare(
    runner: CliRunner,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`--live` routes through `diff_bundle_against_instance` with the parsed bundle."""
    monkeypatch.setenv("DHIS2_URL", "http://mock.example")
    monkeypatch.setenv("DHIS2_PAT", "test-token")
    monkeypatch.delenv("DHIS2_PROFILE", raising=False)
    left = tmp_path / "a.json"
    raw = {"dataElements": [_de("u1", name="A")]}
    left.write_text(json.dumps(raw), encoding="utf-8")
    fake_diff = service.MetadataDiff(left_label="instance:x", right_label=str(left))
    mock = AsyncMock(return_value=fake_diff)
    with patch("dhis2w_core.v42.plugins.metadata.service.diff_bundle_against_instance", mock):
        result = runner.invoke(build_app(), ["metadata", "diff", str(left), "--live"])
    assert result.exit_code == 0, result.output
    args, kwargs = mock.call_args
    # First positional is the profile; second is the parsed MetadataBundle.
    passed_bundle = args[1]
    assert isinstance(passed_bundle, MetadataBundle)
    assert passed_bundle.get_resource("dataElements")[0].id == "u1"
    assert kwargs["bundle_label"] == str(left)
