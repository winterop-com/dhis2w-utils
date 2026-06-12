"""End-to-end tracker CLI tests against local DHIS2."""

from __future__ import annotations

import json

import pytest
from dhis2w_cli.main import build_app
from typer.testing import CliRunner

pytestmark = pytest.mark.slow


def _setup_env(monkeypatch: pytest.MonkeyPatch, local_url: str, local_pat: str | None) -> None:
    if not local_pat:
        pytest.skip("DHIS2_PAT not set — run `make dhis2-run` to populate")
    monkeypatch.setenv("DHIS2_URL", local_url)
    monkeypatch.setenv("DHIS2_PAT", local_pat)


def _first_tracker_program_uid(runner: CliRunner) -> str | None:
    result = runner.invoke(
        build_app(),
        [
            "--json",
            "metadata",
            "list",
            "programs",
            "--fields",
            "id,name,programType",
            "--page-size",
            "50",
        ],
    )
    assert result.exit_code == 0, result.output
    items = json.loads(result.output)
    for p in items:
        if p.get("programType") == "WITH_REGISTRATION":
            return str(p["id"])
    return None


def _first_event_program_uid(runner: CliRunner) -> str | None:
    result = runner.invoke(
        build_app(),
        [
            "--json",
            "metadata",
            "list",
            "programs",
            "--fields",
            "id,name,programType",
            "--page-size",
            "50",
        ],
    )
    assert result.exit_code == 0, result.output
    items = json.loads(result.output)
    for p in items:
        if p.get("programType") == "WITHOUT_REGISTRATION":
            return str(p["id"])
    return None


def _root_org_unit_uid(runner: CliRunner) -> str | None:
    result = runner.invoke(
        build_app(),
        [
            "--json",
            "metadata",
            "list",
            "organisationUnits",
            "--fields",
            "id,name,level",
            "--filter",
            "level:eq:2",
            "--page-size",
            "1",
        ],
    )
    assert result.exit_code == 0, result.output
    items = json.loads(result.output)
    return str(items[0]["id"]) if items else None


def test_list_events_works_with_event_program(
    local_url: str, local_pat: str | None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """List events works with event program."""
    _setup_env(monkeypatch, local_url, local_pat)
    runner = CliRunner()
    program = _first_event_program_uid(runner)
    org_unit = _root_org_unit_uid(runner)
    if not (program and org_unit):
        pytest.skip("instance missing an event program or root orgUnit")

    result = runner.invoke(
        build_app(),
        [
            "--json",
            "data",
            "tracker",
            "event",
            "list",
            "--program",
            program,
            "--org-unit",
            org_unit,
            "--page-size",
            "5",
        ],
    )
    assert result.exit_code == 0, result.output
    envelope = json.loads(result.output)
    # CLI returns a JSON array of event dicts; underlying DHIS2 API returns an envelope with "events"/"instances".
    if isinstance(envelope, list):
        assert all(isinstance(entry, dict) for entry in envelope)
    else:
        assert any(k in envelope for k in ("events", "instances", "page", "pager"))


def test_list_tracked_entities_skips_if_no_tracker_program(
    local_url: str, local_pat: str | None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """List tracked entities skips if no tracker program."""
    _setup_env(monkeypatch, local_url, local_pat)
    runner = CliRunner()
    program = _first_tracker_program_uid(runner)
    org_unit = _root_org_unit_uid(runner)
    if not (program and org_unit):
        pytest.skip("no tracker program on this instance — nothing to list")

    # d2w data tracker list now takes the TET UID as a positional.
    # Discover one from the instance — skip if none.
    types_result = runner.invoke(build_app(), ["--json", "data", "tracker", "type"])
    if types_result.exit_code != 0:
        pytest.skip(f"could not list TET types: {types_result.output}")
    types = json.loads(types_result.output)
    if not types:
        pytest.skip("no TET types on this instance — nothing to list")
    tet_uid = types[0]["id"]
    result = runner.invoke(
        build_app(),
        [
            "--json",
            "data",
            "tracker",
            "list",
            tet_uid,
            "--org-unit",
            org_unit,
            "--page-size",
            "5",
        ],
    )
    assert result.exit_code == 0, result.output
    envelope = json.loads(result.output)
    # CLI returns a JSON array of tracked-entity dicts, or a pager/envelope dict — accept both.
    if isinstance(envelope, list):
        assert all(isinstance(entry, dict) for entry in envelope)
    else:
        assert any(k in envelope for k in ("trackedEntities", "instances", "page", "pager"))
