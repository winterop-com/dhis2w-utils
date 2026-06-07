"""Clean-error rendering surfaces WebMessageResponse detail (conflicts, importCount)."""

from __future__ import annotations

import sys

import pytest
import typer
from dhis2w_client.errors import Dhis2ApiError
from dhis2w_core.cli_errors import run_app

_IMPORT_SUMMARY_409 = {
    "httpStatus": "Conflict",
    "httpStatusCode": 409,
    "status": "WARNING",
    "message": "One more conflicts encountered, please check import summary.",
    "response": {
        "status": "WARNING",
        "responseType": "ImportSummary",
        "importCount": {"imported": 0, "updated": 0, "ignored": 1, "deleted": 0},
        "conflicts": [
            {
                "object": "202604",
                "value": "Period: `202604` is after latest open future period: `202603`",
                "errorCode": "E7641",
                "property": "period",
                "indexes": [0],
            }
        ],
        "rejectedIndexes": [0],
    },
}


def _app_raising(exc: BaseException) -> typer.Typer:
    app = typer.Typer(pretty_exceptions_enable=False)

    @app.command()
    def boom() -> None:
        raise exc

    return app


def test_renders_conflicts_and_import_count_on_409(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A Dhis2ApiError carrying an ImportSummary body renders per-row rejection detail."""
    app = _app_raising(Dhis2ApiError(status_code=409, message="Conflict", body=_IMPORT_SUMMARY_409))
    monkeypatch.setattr(sys, "argv", ["dhis2"])
    with pytest.raises(SystemExit) as excinfo:
        run_app(app)
    assert excinfo.value.code == 1
    captured = capsys.readouterr()
    combined = captured.err + captured.out
    assert "DHIS2 API error (409)" in combined
    assert "One more conflicts encountered" in combined
    assert "import_count: imported=0 updated=0 ignored=1 deleted=0" in combined
    # New Rich-table layout: heading + row cells.
    assert "conflicts" in combined and "(1)" in combined
    assert "period" in combined
    assert "E7641" in combined
    assert "rejected_indexes: [0]" in combined


def test_renders_message_only_when_body_is_plain(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A Dhis2ApiError whose body isn't a WebMessage dict still renders cleanly (no extras)."""
    app = _app_raising(Dhis2ApiError(status_code=500, message="Server error", body="Tomcat HTML"))
    monkeypatch.setattr(sys, "argv", ["dhis2"])
    with pytest.raises(SystemExit) as excinfo:
        run_app(app)
    assert excinfo.value.code == 1
    captured = capsys.readouterr()
    combined = captured.err + captured.out
    assert "DHIS2 API error (500)" in combined
    assert "Server error" in combined
    assert "conflict" not in combined
    assert "import_count" not in combined


_METADATA_IMPORT_ERROR = {
    "httpStatus": "Conflict",
    "httpStatusCode": 409,
    "status": "ERROR",
    "message": "One or more objects did not validate.",
    "response": {
        "status": "ERROR",
        "responseType": "ImportReport",
        "stats": {"ignored": 2, "created": 0, "updated": 0, "deleted": 0, "total": 2},
        "typeReports": [
            {
                "klass": "org.hisp.dhis.dataelement.DataElement",
                "stats": {"ignored": 1, "total": 1},
                "objectReports": [
                    {
                        "klass": "org.hisp.dhis.dataelement.DataElement",
                        "uid": "deUidAAA0001",
                        "errorReports": [
                            {
                                "errorCode": "E4003",
                                "message": "Property `valueType` is required.",
                                "errorProperty": "valueType",
                            }
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
                        "errorReports": [
                            {
                                "errorCode": "E5002",
                                "message": "Parent org unit `xyz` does not exist.",
                                "errorProperty": "parent",
                                "errorProperties": ["xyz", "parent"],
                            }
                        ],
                    }
                ],
            },
        ],
    },
}


def test_renders_metadata_import_errors_as_conflict_table(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Metadata /api/metadata ImportReport errors flatten to the Rich conflict table.

    Unlike `/api/dataValueSets` rejections (flat `response.conflicts[]`),
    `/api/metadata` nests errors at
    `response.typeReports[*].objectReports[*].errorReports[*]`. The Rich
    conflict renderer normalises both shapes and shows a unified table.
    """
    app = _app_raising(Dhis2ApiError(status_code=409, message="Conflict", body=_METADATA_IMPORT_ERROR))
    monkeypatch.setattr(sys, "argv", ["dhis2"])
    with pytest.raises(SystemExit) as excinfo:
        run_app(app)
    assert excinfo.value.code == 1
    captured = capsys.readouterr()
    combined = captured.err + captured.out
    # Rich table carries both resources + both error codes + both properties.
    assert "DataElement" in combined
    assert "OrganisationUnit" in combined
    assert "E4003" in combined
    assert "E5002" in combined
    assert "valueType" in combined
    assert "parent" in combined
    # The "conflicts (N)" heading renders — N is the total across both resources.
    assert "(2)" in combined
