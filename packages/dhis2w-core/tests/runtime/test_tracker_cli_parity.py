"""Per-version CLI invocation parity for the `tracker` plugin — exercise cli.py command bodies on all trees.

The service parity tests cover the service layer; these invoke the CLI commands (via CliRunner against a
version-pinned `build_app()`) with the version's service mocked, so the v41/v43 cli.py command bodies
(arg parsing + result rendering) run, not just their import-time definitions.
"""

from __future__ import annotations

import json
from importlib import import_module
from pathlib import Path
from types import ModuleType
from unittest.mock import AsyncMock, patch

import pytest
from dhis2w_cli.main import build_app
from typer import Typer
from typer.testing import CliRunner


def _build_versioned_app(core_version: str, monkeypatch: pytest.MonkeyPatch) -> Typer:
    """Build the CLI app pinned to `core_version` (so it discovers that tree's plugins)."""
    monkeypatch.setenv("DHIS2_VERSION", core_version)
    return build_app()


def _tracker_module(core_version: str) -> ModuleType:
    """Import the generated tracker schemas (TrackerTrackedEntity, TrackerEnrollment, TrackerEvent)."""
    return import_module(f"dhis2w_client.generated.{core_version}.tracker")


def _write_result_classes(core_version: str) -> ModuleType:
    """Import the v-tree write-result models (RegisterResult, EnrollResult, EventResult, WebMessageResponse)."""
    return import_module(f"dhis2w_client.{core_version}")


def test_tracker_list_cli_parity(core_version: str, core_profile: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """`d2w data tracker list <type>` resolves the TET then renders entities on every version tree."""
    entity_cls = _tracker_module(core_version).TrackerTrackedEntity
    entity = entity_cls.model_validate({"trackedEntity": "teI01234567", "orgUnit": "ou012345678"})
    with (
        patch(
            f"dhis2w_core.{core_version}.plugins.tracker.service.resolve_tracked_entity_type",
            new=AsyncMock(return_value="tet01234567"),
        ),
        patch(
            f"dhis2w_core.{core_version}.plugins.tracker.service.list_tracked_entities",
            new=AsyncMock(return_value=[entity]),
        ),
    ):
        app = _build_versioned_app(core_version, monkeypatch)
        result = CliRunner().invoke(app, ["-p", "probe", "data", "tracker", "list", "Person"])
    assert result.exit_code == 0, result.output
    assert "teI01234567" in result.output


def test_tracker_get_cli_parity(core_version: str, core_profile: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """`d2w data tracker get <uid>` renders one tracked entity on every version tree."""
    entity_cls = _tracker_module(core_version).TrackerTrackedEntity
    entity = entity_cls.model_validate(
        {"trackedEntity": "teI01234567", "trackedEntityType": "tet01234567", "orgUnit": "ou012345678"}
    )
    with patch(
        f"dhis2w_core.{core_version}.plugins.tracker.service.get_tracked_entity",
        new=AsyncMock(return_value=entity),
    ):
        app = _build_versioned_app(core_version, monkeypatch)
        result = CliRunner().invoke(app, ["-p", "probe", "data", "tracker", "get", "teI01234567"])
    assert result.exit_code == 0, result.output
    assert "teI01234567" in result.output


def test_tracker_enrollment_list_cli_parity(
    core_version: str, core_profile: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`d2w data tracker enrollment list` renders enrollments on every version tree."""
    enrollment_cls = _tracker_module(core_version).TrackerEnrollment
    enrollment = enrollment_cls.model_validate(
        {"enrollment": "enr01234567", "program": "prg01234567", "orgUnit": "ou012345678", "status": "ACTIVE"}
    )
    with patch(
        f"dhis2w_core.{core_version}.plugins.tracker.service.list_enrollments",
        new=AsyncMock(return_value=[enrollment]),
    ):
        app = _build_versioned_app(core_version, monkeypatch)
        result = CliRunner().invoke(
            app, ["-p", "probe", "data", "tracker", "enrollment", "list", "--program", "prg01234567"]
        )
    assert result.exit_code == 0, result.output
    assert "enr01234567" in result.output


def test_tracker_event_list_cli_parity(core_version: str, core_profile: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """`d2w data tracker event list` renders events on every version tree."""
    event_cls = _tracker_module(core_version).TrackerEvent
    event = event_cls.model_validate(
        {"event": "evt01234567", "program": "prg01234567", "orgUnit": "ou012345678", "status": "ACTIVE"}
    )
    with patch(
        f"dhis2w_core.{core_version}.plugins.tracker.service.list_events",
        new=AsyncMock(return_value=[event]),
    ):
        app = _build_versioned_app(core_version, monkeypatch)
        result = CliRunner().invoke(
            app, ["-p", "probe", "data", "tracker", "event", "list", "--program", "prg01234567"]
        )
    assert result.exit_code == 0, result.output
    assert "evt01234567" in result.output


def test_tracker_register_cli_parity(core_version: str, core_profile: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """`d2w data tracker register` renders the new TE + enrollment UIDs on every version tree."""
    classes = _write_result_classes(core_version)
    response = classes.WebMessageResponse.model_validate({"status": "OK", "httpStatusCode": 200})
    result_obj = classes.RegisterResult.model_validate(
        {"tracked_entity": "teI01234567", "enrollment": "enr01234567", "response": response}
    )
    with patch(
        f"dhis2w_core.{core_version}.plugins.tracker.service.register_tracked_entity",
        new=AsyncMock(return_value=result_obj),
    ):
        app = _build_versioned_app(core_version, monkeypatch)
        result = CliRunner().invoke(
            app,
            [
                "-p",
                "probe",
                "data",
                "tracker",
                "register",
                "prg01234567",
                "--ou",
                "ou012345678",
                "--tet",
                "tet01234567",
                "--attr",
                "w75KJ2mc4zz=Jane",
            ],
        )
    assert result.exit_code == 0, result.output
    assert "teI01234567" in result.output


def test_tracker_enrollment_create_cli_parity(
    core_version: str, core_profile: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`d2w data tracker enrollment create` renders the new enrollment UID on every version tree."""
    classes = _write_result_classes(core_version)
    response = classes.WebMessageResponse.model_validate({"status": "OK", "httpStatusCode": 200})
    result_obj = classes.EnrollResult.model_validate({"enrollment": "enr01234567", "response": response})
    with patch(
        f"dhis2w_core.{core_version}.plugins.tracker.service.enroll_tracked_entity",
        new=AsyncMock(return_value=result_obj),
    ):
        app = _build_versioned_app(core_version, monkeypatch)
        result = CliRunner().invoke(
            app,
            [
                "-p",
                "probe",
                "data",
                "tracker",
                "enrollment",
                "create",
                "teI01234567",
                "prg01234567",
                "--at",
                "ou012345678",
            ],
        )
    assert result.exit_code == 0, result.output
    assert "enr01234567" in result.output


def test_tracker_event_create_cli_parity(
    core_version: str, core_profile: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`d2w data tracker event create` renders the new event UID on every version tree."""
    classes = _write_result_classes(core_version)
    response = classes.WebMessageResponse.model_validate({"status": "OK", "httpStatusCode": 200})
    result_obj = classes.EventResult.model_validate({"event": "evt01234567", "response": response})
    with patch(
        f"dhis2w_core.{core_version}.plugins.tracker.service.add_tracker_event",
        new=AsyncMock(return_value=result_obj),
    ):
        app = _build_versioned_app(core_version, monkeypatch)
        result = CliRunner().invoke(
            app,
            [
                "-p",
                "probe",
                "data",
                "tracker",
                "event",
                "create",
                "--program",
                "prg01234567",
                "--stage",
                "stg01234567",
                "--at",
                "ou012345678",
                "--enrollment",
                "enr01234567",
                "--dv",
                "fClA2Erf6IO=5",
            ],
        )
    assert result.exit_code == 0, result.output
    assert "evt01234567" in result.output


def test_tracker_push_cli_parity(
    core_version: str, core_profile: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`d2w data tracker push <file>` renders the import response on every version tree."""
    response = _write_result_classes(core_version).WebMessageResponse.model_validate(
        {"status": "OK", "httpStatusCode": 200}
    )
    bundle = tmp_path / "bundle.json"
    bundle.write_text(json.dumps({"events": [{"event": "evt01234567"}]}), encoding="utf-8")
    with patch(
        f"dhis2w_core.{core_version}.plugins.tracker.service.push_tracker",
        new=AsyncMock(return_value=response),
    ):
        app = _build_versioned_app(core_version, monkeypatch)
        result = CliRunner().invoke(app, ["-p", "probe", "data", "tracker", "push", str(bundle)])
    assert result.exit_code == 0, result.output
    assert "pushed" in result.output


def test_tracker_delete_cli_parity(core_version: str, core_profile: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """`d2w data tracker delete <uid>` renders the delete response on every version tree."""
    response = _write_result_classes(core_version).WebMessageResponse.model_validate(
        {"status": "OK", "httpStatusCode": 200}
    )
    with patch(
        f"dhis2w_core.{core_version}.plugins.tracker.service.delete_tracker_objects",
        new=AsyncMock(return_value=response),
    ):
        app = _build_versioned_app(core_version, monkeypatch)
        result = CliRunner().invoke(app, ["-p", "probe", "data", "tracker", "delete", "teI01234567", "--yes"])
    assert result.exit_code == 0, result.output
    assert "deleted" in result.output


def test_tracker_outstanding_cli_parity(core_version: str, core_profile: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """`d2w data tracker outstanding <program>` renders the due report on every version tree."""
    row_cls = _write_result_classes(core_version).OutstandingEnrollment
    row = row_cls.model_validate(
        {
            "enrollment": "enr01234567",
            "tracked_entity": "teI01234567",
            "program": "prg01234567",
            "org_unit": "ou012345678",
            "missing_stages": ["stg01234567"],
        }
    )
    with patch(
        f"dhis2w_core.{core_version}.plugins.tracker.service.outstanding_enrollments",
        new=AsyncMock(return_value=[row]),
    ):
        app = _build_versioned_app(core_version, monkeypatch)
        result = CliRunner().invoke(app, ["-p", "probe", "data", "tracker", "outstanding", "prg01234567"])
    assert result.exit_code == 0, result.output
    assert "enr01234567" in result.output
