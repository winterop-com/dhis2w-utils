"""Unit tests for the DHIS2 WebMessageResponse / ObjectReport / ImportReport models."""

from __future__ import annotations

from dhis2w_client import Conflict, ImportCount, ObjectReport, WebMessageResponse
from dhis2w_client.errors import Dhis2ApiError


def test_object_report_response_parses_created_uid() -> None:
    """Typical `POST /api/routes` response envelope — created_uid pulls response.uid."""
    envelope = WebMessageResponse.model_validate(
        {
            "httpStatus": "Created",
            "httpStatusCode": 201,
            "status": "OK",
            "response": {
                "uid": "abc123uid12",
                "klass": "org.hisp.dhis.route.Route",
                "errorReports": [],
                "responseType": "ObjectReportWebMessageResponse",
            },
        }
    )
    assert envelope.httpStatus == "Created"
    assert envelope.httpStatusCode == 201
    assert envelope.status == "OK"
    assert envelope.created_uid == "abc123uid12"

    inner = envelope.object_report()
    assert inner is not None
    assert inner.uid == "abc123uid12"
    assert inner.klass == "org.hisp.dhis.route.Route"
    assert inner.errorReports == []


def test_error_envelope_preserves_error_reports() -> None:
    """Envelope with E4030 errorReports — callers can drill into per-object reasons."""
    envelope = WebMessageResponse.model_validate(
        {
            "httpStatus": "Conflict",
            "httpStatusCode": 409,
            "status": "WARNING",
            "message": "One or more errors occurred, please see full details in import report.",
            "response": {
                "uid": "badObject1",
                "klass": "org.hisp.dhis.dataelement.DataElement",
                "errorReports": [
                    {
                        "message": (
                            "Object could not be deleted because it is associated with another object: DataValue"
                        ),
                        "mainKlass": "org.hisp.dhis.dataelement.DataElement",
                        "errorCode": "E4030",
                        "errorProperties": [],
                    }
                ],
                "responseType": "ObjectReportWebMessageResponse",
            },
        }
    )
    inner = envelope.object_report()
    assert inner is not None
    assert inner.errorReports is not None
    assert len(inner.errorReports) == 1
    assert inner.errorReports[0].errorCode == "E4030"


def test_import_count_from_data_value_set_response() -> None:
    """Data-value-set POST returns response: {importCount: {...}} — import_count() parses it."""
    # Real DHIS2 dataValueSets response wraps importCount under `response.importCount`, not directly:
    # {..., "response": {"responseType": "ImportSummary", "importCount": {"imported": 1, ...}}}
    # Callers typically reach in manually, or pydantic-validate against ImportCount if flat.
    envelope = WebMessageResponse.model_validate(
        {
            "status": "OK",
            "response": {
                "imported": 5,
                "updated": 2,
                "ignored": 0,
                "deleted": 0,
            },
        }
    )
    counts = envelope.import_count()
    assert counts is not None
    assert counts.imported == 5
    assert counts.updated == 2
    assert counts.ignored == 0
    assert counts.deleted == 0


def test_created_uid_falls_back_to_id_when_no_uid() -> None:
    """Defensive lookup: BUGS.md #4f — some endpoints return `id` not `uid`."""
    envelope = WebMessageResponse.model_validate(
        {"status": "OK", "response": {"id": "fromIdField", "name": "something"}}
    )
    assert envelope.created_uid == "fromIdField"


def test_created_uid_none_when_response_missing() -> None:
    """Created uid none when response missing."""
    envelope = WebMessageResponse.model_validate({"status": "OK"})
    assert envelope.created_uid is None
    assert envelope.object_report() is None


def test_extra_fields_are_preserved() -> None:
    """DHIS2 adds fields over time; extra='allow' keeps them accessible for downstream callers."""
    envelope = WebMessageResponse.model_validate(
        {
            "status": "OK",
            "somethingNew": "future-field",
            "response": {"uid": "u", "klass": "X"},
        }
    )
    # Dumped dict preserves the extra field so downstream CLI/MCP JSON output keeps it.
    dumped = envelope.model_dump(exclude_none=True)
    assert dumped["somethingNew"] == "future-field"


def test_object_report_standalone_parse() -> None:
    """ObjectReport can be validated directly too (e.g. when DHIS2 returns it at top level)."""
    report = ObjectReport.model_validate(
        {
            "uid": "x",
            "klass": "org.hisp.dhis.dataelement.DataElement",
            "errorReports": [],
        }
    )
    assert report.uid == "x"
    assert report.errorReports == []


def test_import_count_standalone() -> None:
    """Import count standalone."""
    counts = ImportCount.model_validate({"imported": 1, "updated": 0, "ignored": 0, "deleted": 0})
    assert counts.imported == 1


_DATA_VALUE_SETS_409_BODY = {
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
                "objects": {"period": "202604", "dataElement": "DEancVisit1"},
                "value": "Period: `202604` is after latest open future period: `202603`",
                "errorCode": "E7641",
                "property": "period",
                "indexes": [0],
            }
        ],
        "rejectedIndexes": [0],
    },
}


def test_conflicts_parse_per_row_rejection() -> None:
    """conflicts() pulls the typed `Conflict` list out of a /api/dataValueSets 409 body."""
    envelope = WebMessageResponse.model_validate(_DATA_VALUE_SETS_409_BODY)
    conflicts = envelope.conflicts()
    assert len(conflicts) == 1
    assert conflicts[0].property == "period"
    assert conflicts[0].errorCode == "E7641"
    assert "202604" in (conflicts[0].value or "")
    assert conflicts[0].indexes == [0]


def test_rejected_indexes_returns_list_of_ints() -> None:
    """Rejected indexes returns list of ints."""
    envelope = WebMessageResponse.model_validate(_DATA_VALUE_SETS_409_BODY)
    assert envelope.rejected_indexes() == [0]


def test_conflicts_returns_empty_when_response_missing() -> None:
    """Conflicts returns empty when response missing."""
    envelope = WebMessageResponse.model_validate({"status": "OK"})
    assert envelope.conflicts() == []
    assert envelope.rejected_indexes() == []


def test_conflict_standalone_parse() -> None:
    """Conflict standalone parse."""
    conflict = Conflict.model_validate({"property": "value", "value": "oops", "errorCode": "E9999", "indexes": [3]})
    assert conflict.property == "value"
    assert conflict.errorCode == "E9999"


def test_dhis2_api_error_exposes_web_message_envelope() -> None:
    """Dhis2ApiError carries body through; `.web_message` lazily parses the envelope."""
    exc = Dhis2ApiError(status_code=409, message="Conflict", body=_DATA_VALUE_SETS_409_BODY)
    envelope = exc.web_message
    assert envelope is not None
    assert envelope.status == "WARNING"
    conflicts = envelope.conflicts()
    assert len(conflicts) == 1
    assert conflicts[0].errorCode == "E7641"


def test_dhis2_api_error_web_message_none_when_body_not_dict() -> None:
    """Dhis2 api error web message none when body not dict."""
    exc = Dhis2ApiError(status_code=500, message="Internal", body="Tomcat HTML page")
    assert exc.web_message is None


def test_task_ref_pulls_jobtype_and_id_from_job_envelope() -> None:
    """JobConfigurationWebMessageResponse → `(jobType, id)` tuple for watchers to feed `watch_task`."""
    envelope = WebMessageResponse.model_validate(
        {
            "httpStatus": "OK",
            "status": "OK",
            "message": "Initiated ANALYTICS_TABLE (...)",
            "response": {
                "id": "abc123",
                "jobType": "ANALYTICS_TABLE",
                "responseType": "JobConfigurationWebMessageResponse",
            },
        }
    )
    assert envelope.task_ref() == ("ANALYTICS_TABLE", "abc123")


def test_task_ref_none_for_non_job_envelope() -> None:
    """ObjectReport-shaped responses don't have a task ref."""
    envelope = WebMessageResponse.model_validate(
        {"status": "OK", "response": {"uid": "xyz", "klass": "org.hisp.dhis.route.Route"}}
    )
    assert envelope.task_ref() is None


def test_task_ref_none_when_response_missing() -> None:
    """Task ref none when response missing."""
    envelope = WebMessageResponse.model_validate({"status": "OK"})
    assert envelope.task_ref() is None


# ---- WebMessageResponse.conflict_rows — normalised conflict view ----------


def test_conflict_rows_flat_data_value_shape() -> None:
    """DataValueSets-style `response.conflicts[]` flattens into typed `ConflictRow`s."""
    envelope = WebMessageResponse.model_validate(
        {
            "status": "WARNING",
            "response": {
                "importCount": {"imported": 5, "updated": 0, "ignored": 2, "deleted": 0, "total": 7},
                "conflicts": [
                    {
                        "object": "org.hisp.dhis.dataelement.DataElement",
                        "property": "dataElement",
                        "value": "UID xyz999 is not a valid value type",
                        "errorCode": "E5003",
                        "indexes": [3, 5],
                    },
                    {
                        "object": "Value",
                        "property": "value",
                        "value": "Not a number",
                        "errorCode": "E7611",
                    },
                ],
            },
        }
    )
    rows = envelope.conflict_rows()
    assert len(rows) == 2
    first, second = rows
    assert first.resource == "DataElement"  # Jackson klass stripped
    assert first.property == "dataElement"
    assert first.value == "UID xyz999 is not a valid value type"
    assert first.error_code == "E5003"
    assert first.indexes == [3, 5]
    assert second.resource == "Value"  # Non-dotted klass passes through unchanged


def test_conflict_rows_metadata_import_walks_typereports() -> None:
    """Metadata /api/metadata error reports flatten with resource + uid + errorCode."""
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
                                        "errorProperties": ["xyz", "parent"],
                                    },
                                ],
                            }
                        ],
                    },
                ],
            },
        }
    )
    rows = envelope.conflict_rows()
    assert len(rows) == 2
    de_row, ou_row = rows
    assert de_row.resource == "DataElement"
    assert de_row.uid == "deUidAAA0001"
    assert de_row.property == "valueType"
    assert de_row.error_code == "E4003"
    assert de_row.message == "Property `valueType` is required"
    assert ou_row.resource == "OrganisationUnit"
    assert ou_row.value == "xyz"  # First errorProperties entry = offending value


def test_conflict_rows_empty_on_clean_response() -> None:
    """No `conflicts` or `typeReports` → empty list, not an error."""
    envelope = WebMessageResponse.model_validate(
        {"status": "OK", "response": {"importCount": {"imported": 3, "total": 3}}}
    )
    assert envelope.conflict_rows() == []


def test_conflict_rows_merges_both_shapes() -> None:
    """Pathological case: both `conflicts[]` AND `typeReports[]` populated — merged."""
    envelope = WebMessageResponse.model_validate(
        {
            "status": "ERROR",
            "response": {
                "conflicts": [
                    {"object": "row", "property": "value", "errorCode": "E7611", "value": "not a number"},
                ],
                "typeReports": [
                    {
                        "klass": "org.hisp.dhis.dataelement.DataElement",
                        "objectReports": [
                            {
                                "uid": "deUidAAA0001",
                                "errorReports": [{"errorCode": "E4003", "message": "missing valueType"}],
                            }
                        ],
                    }
                ],
            },
        }
    )
    rows = envelope.conflict_rows()
    assert len(rows) == 2
    # Flat conflicts come first, then metadata rows.
    assert rows[0].error_code == "E7611"
    assert rows[1].error_code == "E4003"
