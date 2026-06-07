"""End-to-end metadata CLI tests against local DHIS2."""

from __future__ import annotations

import json

import pytest
from dhis2w_cli.main import build_app
from typer.testing import CliRunner

pytestmark = pytest.mark.slow


def test_metadata_types_lists_resources(local_url: str, local_pat: str | None, monkeypatch: pytest.MonkeyPatch) -> None:
    """Metadata types lists resources."""
    if not local_pat:
        pytest.skip("DHIS2_PAT not set — run `make dhis2-run` to populate")
    monkeypatch.setenv("DHIS2_URL", local_url)
    monkeypatch.setenv("DHIS2_PAT", local_pat)
    runner = CliRunner()
    result = runner.invoke(build_app(), ["metadata", "type", "list"])
    assert result.exit_code == 0, result.output
    assert "dataElements" in result.output
    assert "indicators" in result.output
    assert "DHIS2 metadata types" in result.output


def test_metadata_list_data_elements_json(
    local_url: str, local_pat: str | None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Metadata list data elements json."""
    if not local_pat:
        pytest.skip("DHIS2_PAT not set — run `make dhis2-run` to populate")
    monkeypatch.setenv("DHIS2_URL", local_url)
    monkeypatch.setenv("DHIS2_PAT", local_pat)
    runner = CliRunner()
    result = runner.invoke(
        build_app(),
        ["--json", "metadata", "list", "dataElements", "--fields", "id,name", "--page-size", "3"],
    )
    assert result.exit_code == 0, result.output
    items = json.loads(result.output)
    assert isinstance(items, list)
    assert len(items) <= 3
    if items:
        assert "id" in items[0]
