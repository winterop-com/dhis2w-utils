"""Service tests for `forward_responses` - the spool, the two endpoints, the dials, and the lifecycle.

The fixture is a whole small project on disk: a `fhir.toml`, the compiled Questionnaire / CodeSystem /
ValueSet documents a generate run plus SUSHI would leave in `ig/fsh-generated/resources`, the ConceptMaps
and Locations the predefined tree carries, and a capture spool holding the very example responses the
examples target publishes. That is exactly what a real run reads, so what these tests exercise is the
whole path from `.serve/responses/received/*.json` to the DHIS2 import - respx standing in for the
instance alone.
"""

from __future__ import annotations

import datetime
import fcntl
import json
import os
import time
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from dhis2w_core.profile import resolve
from dhis2w_fhir import (
    AttributeCodeIndex,
    CodedAnswerMode,
    ForwardCompletenessKind,
    ForwardOutcomeKind,
    GenerateConfig,
    OptionSetIn,
    QuestionnaireItemIn,
    QuestionnaireSourceIn,
    build_attribute_combo_artifacts,
    build_attribute_combo_concept_maps,
    build_example_documents,
    build_forwarded_cell_index,
    build_questionnaire_documents,
    build_synthetic_responses,
    load_project,
    option_set_identities,
    service,
)
from dhis2w_fhir.conversion import (
    CompiledArtifactReadError,
    CompiledIgMissingError,
    ConversionNaming,
    ConversionTargetKind,
    bound_question_uids,
    build_project_context,
    load_compiled_artifacts,
    receipt_event_uid,
)
from dhis2w_fhir.names import is_dhis2_uid
from dhis2w_fhir.r4 import Extension, Identifier, Location, QuestionnaireResponse
from dhis2w_fhir.resources.examples.schemas import ExampleAnswerIn, ExampleResponseIn
from dhis2w_fhir.resources.option_sets import build_option_set_artifacts, build_option_set_concept_maps
from dhis2w_fhir.resources.option_sets.schemas import OptionIn
from dhis2w_fhir.resources.questionnaires.schemas import (
    CategoryComboIn,
    CategoryOptionComboIn,
    ProgramContextIn,
    QuestionnaireSectionIn,
)
from dhis2w_fhir.spool import (
    DRAIN_LOCK_FILE_NAME,
    FORWARDED_RESPONSES_RELATIVE_PATH,
    IMPORT_REPORT_SUFFIX,
    MALFORMED_RESPONSES_RELATIVE_PATH,
    ORPHAN_TEMPORARY_FILE_AGE_SECONDS,
    RECEIVED_RESPONSES_RELATIVE_PATH,
    REFUSAL_RECORD_SUFFIX,
    REJECTED_RESPONSES_RELATIVE_PATH,
    SPOOL_RELATIVE_PATH,
    ForwardRefusalRecord,
    SpoolLockedError,
    SpoolReadError,
    SpoolState,
)
from pydantic import BaseModel, ConfigDict

_BASE_URL = "https://dhis2.example"
_CANONICAL = "http://example.org/fhir"
_ROOT_ORG_UNIT = "ImspTQPwCqd"
_REFERENCE_DATE = datetime.date(2026, 8, 8)

_GENDER_SET = OptionSetIn(
    uid="Os1aaaaaaaa",
    name="Gender",
    options=[
        OptionIn(uid="Op1aaaaaaaa", code="F", name="Female", sort_order=1),
        OptionIn(uid="Op2aaaaaaaa", code="M", name="Male", sort_order=2),
    ],
)
_OPTION_SETS = [_GENDER_SET]

_DATA_SET = QuestionnaireSourceIn(
    uid="BfMAe6Itzgt",
    name="Child Health",
    kind="aggregate",
    period_type="Monthly",
    sections=[
        QuestionnaireSectionIn(
            uid="Sec1aaaaaaa",
            name="Immunization",
            items=[
                QuestionnaireItemIn(uid="De2aaaaaaaa", name="Measles doses given", value_type="INTEGER"),
                QuestionnaireItemIn(uid="De3aaaaaaaa", name="Gender", value_type="TEXT", option_set_uid="Os1aaaaaaaa"),
            ],
        )
    ],
)

_EVENT_PROGRAM = QuestionnaireSourceIn(
    uid="VBqh0ynB2wv",
    name="Case surveillance",
    kind="event",
    flat_items=[
        QuestionnaireItemIn(uid="De4aaaaaaaa", name="Cases", value_type="INTEGER"),
        QuestionnaireItemIn(uid="De5aaaaaaaa", name="Confirmed", value_type="TRUE_ONLY"),
    ],
)

_SOURCES = [_DATA_SET, _EVENT_PROGRAM]

#: What the instance answers the value-type read with - the fact the compiled IG cannot carry.
_VALUE_TYPES = {
    "De2aaaaaaaa": "INTEGER",
    "De3aaaaaaaa": "TEXT",
    "De4aaaaaaaa": "INTEGER",
    "De5aaaaaaaa": "TRUE_ONLY",
}

_FHIR_TOML = """
[ig]
id = "dhis2.fhir.test"
canonical = "http://example.org/fhir"
name = "Dhis2FhirTest"
title = "DHIS2 FHIR Test IG"
publisher = "Test Organisation"

[serve]
strict_codes = {strict}
"""


def _documents(config: GenerateConfig) -> list[QuestionnaireResponse]:
    """The example responses one generate run publishes for the fixture forms."""
    plan = option_set_identities(_OPTION_SETS, config)
    captured = build_synthetic_responses(_SOURCES, _OPTION_SETS, 1, _ROOT_ORG_UNIT, _REFERENCE_DATE).responses
    return list(
        build_example_documents(_SOURCES, captured, _OPTION_SETS, config, _CANONICAL, option_set_plan=plan).responses
    )


def _write_project(root: Path, *, strict_codes: bool = False, compiled: bool = True) -> None:
    """Write a whole project: the config, the published guide, and nothing else a forward run reads."""
    (root / "fhir.toml").write_text(_FHIR_TOML.format(strict="true" if strict_codes else "false"), encoding="utf-8")
    compiled_directory = root / "ig" / "fsh-generated" / "resources"
    compiled_directory.mkdir(parents=True, exist_ok=True)
    predefined_directory = root / "ig" / "input" / "resources"
    predefined_directory.mkdir(parents=True, exist_ok=True)
    if not compiled:
        return
    config = GenerateConfig()
    plan = option_set_identities(_OPTION_SETS, config)
    build = build_questionnaire_documents(
        _SOURCES, config, _CANONICAL, ig_status="draft", option_set_plan=plan, attribute_codes=AttributeCodeIndex()
    )
    for questionnaire in build.questionnaires:
        _write_resource(compiled_directory / f"Questionnaire-{questionnaire.id}.json", questionnaire)
    terminology = build_option_set_artifacts(
        _OPTION_SETS, config, _CANONICAL, ig_status="draft", attribute_codes=AttributeCodeIndex()
    )
    for artifact in terminology.artifacts:
        (compiled_directory / artifact.relative_path.rsplit("/", 1)[-1]).write_text(artifact.content, encoding="utf-8")
    for concept_map in build_option_set_concept_maps(_OPTION_SETS, config, _CANONICAL, ig_status="draft"):
        _write_resource(predefined_directory / f"ConceptMap-{concept_map.id}.json", concept_map)
    naming = ConversionNaming.from_config(config, _CANONICAL)
    _write_resource(
        predefined_directory / f"Location-{_ROOT_ORG_UNIT}.json",
        Location(
            id=_ROOT_ORG_UNIT,
            identifier=[Identifier(system=naming.organisation_unit_system, value=_ROOT_ORG_UNIT)],
        ),
    )


def _write_resource(path: Path, resource: Any) -> None:
    """Write one published resource the way SUSHI and the JSON targets write theirs."""
    path.write_text(resource.model_dump_json(exclude_none=True, by_alias=True, indent=2), encoding="utf-8")


def _form_kind(document: QuestionnaireResponse) -> str:
    """The DHIS2 form kind one published response declares, which is what its receipt records."""
    naming = ConversionNaming.from_config(GenerateConfig(), _CANONICAL)
    for extension in document.extension or []:
        if extension.url == naming.form_type_url and extension.valueCode:
            return extension.valueCode
    return "event"


#: When the fixture's receipts were captured, which is what a later drain reads back off a sidecar.
_RECEIVED_AT = "2026-08-08T09:00:00Z"


def _fill_spool(root: Path, documents: list[QuestionnaireResponse], *, received_at: str = _RECEIVED_AT) -> None:
    """Write the receipt envelopes `d2w fhir serve` would have left for these responses."""
    for document in documents:
        _write_receipt(root, document, received_at=received_at)


def _write_receipt(root: Path, document: QuestionnaireResponse, *, received_at: str = _RECEIVED_AT) -> None:
    """Write one receipt envelope into the queue, arriving when the caller says it did."""
    directory = root / RECEIVED_RESPONSES_RELATIVE_PATH
    directory.mkdir(parents=True, exist_ok=True)
    envelope = {
        "response_id": document.id,
        "received_at": received_at,
        "form_kind": _form_kind(document),
        "questionnaire": document.questionnaire or "",
        "warnings": [],
        "response": json.loads(document.model_dump_json(exclude_none=True, by_alias=True)),
    }
    (directory / f"{document.id}.json").write_text(json.dumps(envelope, indent=2), encoding="utf-8")


#: Where the 409 bodies harvested off the live play instances are kept, one file per DHIS2 major.
_HARVESTED_409_DIRECTORY = Path(__file__).parent / "data" / "forward-409"

#: What `/api/system/info` called each instance the stored 409 bodies were harvested off.
_HARVESTED_INSTANCE_VERSIONS = {"v41": "2.41.10-SNAPSHOT", "v42": "2.42.6-SNAPSHOT", "v43": "2.43.2-SNAPSHOT"}

#: The build beside each version - the pair that names the one nightly a stored body came off.
_HARVESTED_INSTANCE_REVISIONS = {"v41": "c3a425c", "v42": "9595934", "v43": "7b4cd04"}


def _harvested_409(name: str, wire_version: str) -> httpx.Response:
    """Replay one stored 409 body as the answer the instance gave, field for field as DHIS2 wrote it."""
    body = json.loads((_HARVESTED_409_DIRECTORY / f"{name}-{wire_version}.json").read_text(encoding="utf-8"))
    return httpx.Response(409, json=body)


def _harvested_aggregate_value_type_409(wire_version: str) -> httpx.Response:
    """A wrapped `/api/dataValueSets` 409, verbatim off the 2026-08-11 play nightlies.

    Off 2.41.10-SNAPSHOT (c3a425c), 2.42.6-SNAPSHOT (9595934) and 2.43.2-SNAPSHOT (7b4cd04). Provoked by
    `POST /api/dataValueSets?dryRun=true` writing `not-a-number` into the NUMBER data element `DUSpd8Jq3M7`
    of data set `BfMAe6Itzgt`, period `202601`, organisation unit `DiszpKrYNg8`.
    """
    return _harvested_409("data-value-set-value-type", wire_version)


def _harvested_absent_enrollment_409(wire_version: str) -> httpx.Response:
    """The bare `/api/tracker` pair a stage event whose enrollment nobody has earns, verbatim off the nightlies.

    Off 2.41.10-SNAPSHOT (c3a425c), 2.42.6-SNAPSHOT (9595934) and 2.43.2-SNAPSHOT (7b4cd04) on 2026-08-11.
    Provoked by `POST /api/tracker?importStrategy=CREATE&async=false&importMode=VALIDATE` with event
    `EvAaBbCcDd1` of stage `A03MvHHogjR` naming enrollment `EnAaBbCcDd1`, which no instance holds.

    `E1313` states the enrollment references no tracked entity and `E1079` asserts a program mismatch
    against that same absent enrollment (BUGS.md 68). Under `importMode=VALIDATE` the pair is what every
    stage event of a registration validated in the same run earns, because a dry run creates no enrollment.
    """
    return _harvested_409("tracker-absent-enrollment", wire_version)


def _harvested_tracker_value_type_409(wire_version: str) -> httpx.Response:
    """A bare `/api/tracker` 409 over a value the data element's type refuses, verbatim off the nightlies.

    Off 2.41.10-SNAPSHOT (c3a425c), 2.42.6-SNAPSHOT (9595934) and 2.43.2-SNAPSHOT (7b4cd04) on 2026-08-11.
    Provoked by `POST /api/tracker?importStrategy=CREATE&async=false&importMode=VALIDATE` with event
    `EvBbCcDd002` of stage `pTo4uMt3xur` writing `not-a-coordinate` into the COORDINATE data element
    `F3ogKBuviRA`.
    """
    return _harvested_409("tracker-value-type", wire_version)


class _AggregateRejectionFacts(BaseModel):
    """What one major's harvested `/api/dataValueSets` 409 states, read off the stored body itself."""

    model_config = ConfigDict(frozen=True)

    status: str
    error_code: str
    subject: str | None
    message: str


class _TrackerRejectionFacts(BaseModel):
    """What one major's harvested `/api/tracker` 409 states, read off the stored body itself."""

    model_config = ConfigDict(frozen=True)

    error_codes: tuple[str, ...]
    subject: str
    messages: tuple[str, ...]


#: What each major answers the one refused data value with. 2.43 names another rule, drops the `object`
#: that named the data element, and calls an outright error what 2.41 and 2.42 call a warning - so the
#: only thing a reader of all three can count on is that a conflict arrived at all.
_AGGREGATE_VALUE_TYPE_FACTS = {
    "v41": _AggregateRejectionFacts(
        status="WARNING",
        error_code="E7619",
        subject="DUSpd8Jq3M7",
        message="Value must match value type of data element `DUSpd8Jq3M7`: `Data value is not numeric`",
    ),
    "v42": _AggregateRejectionFacts(
        status="WARNING",
        error_code="E7619",
        subject="DUSpd8Jq3M7",
        message="Value must match value type of data element `DUSpd8Jq3M7`: `Data value is not numeric`",
    ),
    "v43": _AggregateRejectionFacts(
        status="ERROR",
        error_code="E8122",
        subject=None,
        message="Value #0 value `not-a-number` is no valid NUMBER: value_not_numeric",
    ),
}

#: What each major answers the stage event naming an enrollment nobody has with. The two codes are the
#: same three times over and the two sentences are three different pairs of prose (BUGS.md 68).
_ABSENT_ENROLLMENT_FACTS = {
    "v41": _TrackerRejectionFacts(
        error_codes=("E1313", "E1079"),
        subject="EvAaBbCcDd1",
        messages=(
            "Event EvAaBbCcDd1 of an enrollment does not point to an existing tracked entity. "
            "The data in your system might be corrupted",
            "Event: `EvAaBbCcDd1`, program: `IpHINAT79UW` is different from program defined in "
            "enrollment `EnAaBbCcDd1`.",
        ),
    ),
    "v42": _TrackerRejectionFacts(
        error_codes=("E1313", "E1079"),
        subject="EvAaBbCcDd1",
        messages=(
            "Event `EvAaBbCcDd1` of an Enrollment does not reference a TrackedEntity.",
            "Event: `EvAaBbCcDd1`, program: `IpHINAT79UW` is different from program defined in "
            "enrollment `EnAaBbCcDd1`.",
        ),
    ),
    "v43": _TrackerRejectionFacts(
        error_codes=("E1313", "E1079"),
        subject="EvAaBbCcDd1",
        messages=(
            "Event `EvAaBbCcDd1` of an Enrollment does not reference a TrackedEntity.",
            "Event: `EvAaBbCcDd1` Program: `IpHINAT79UW` is different from Program defined in "
            "Enrollment `EnAaBbCcDd1`.",
        ),
    ),
}

#: What each major answers the coordinate that is not one with. `E1302` names the value type - or, on
#: 2.41, nothing at all - where the data element identifier belongs (BUGS.md 75).
_TRACKER_VALUE_TYPE_FACTS = {
    "v41": _TrackerRejectionFacts(
        error_codes=("E1302",),
        subject="EvBbCcDd002",
        messages=("DataElement `` is not valid: `Value type is COORDINATE but the value `not-a-coordinate` is not.`",),
    ),
    "v42": _TrackerRejectionFacts(
        error_codes=("E1302",),
        subject="EvBbCcDd002",
        messages=(
            "DataElement `COORDINATE` is not valid: `Value type is COORDINATE but the value "
            "`not-a-coordinate` is not.`.",
        ),
    ),
    "v43": _TrackerRejectionFacts(
        error_codes=("E1302",),
        subject="EvBbCcDd002",
        messages=(
            "DataElement `COORDINATE` is not valid: `Value type is COORDINATE but the value "
            "`not-a-coordinate` is not.`.",
        ),
    ),
}


def _mock_instance(
    *,
    wire_version: str = "v42",
    aggregate_response: httpx.Response | None = None,
    tracker_response: httpx.Response | None = None,
    completeness_response: httpx.Response | None = None,
) -> dict[str, respx.Route]:
    """Mock everything a forward run touches: the version probe, the value types, and the three writes."""
    version = _HARVESTED_INSTANCE_VERSIONS[wire_version]
    respx.get(f"{_BASE_URL}/api/system/info").mock(return_value=httpx.Response(200, json={"version": version}))
    value_types = respx.get(f"{_BASE_URL}/api/dataElements").mock(
        return_value=httpx.Response(
            200,
            json={"dataElements": [{"id": uid, "valueType": value} for uid, value in _VALUE_TYPES.items()]},
        )
    )
    aggregate = respx.post(f"{_BASE_URL}/api/dataValueSets").mock(
        return_value=aggregate_response or _accepted_aggregate()
    )
    tracker = respx.post(f"{_BASE_URL}/api/tracker").mock(return_value=tracker_response or _accepted_tracker())
    completeness = respx.post(f"{_BASE_URL}/api/completeDataSetRegistrations").mock(
        return_value=completeness_response or _accepted_completeness()
    )
    return {
        "value_types": value_types,
        "aggregate": aggregate,
        "tracker": tracker,
        "completeness": completeness,
    }


def _accepted_completeness() -> httpx.Response:
    """What `/api/completeDataSetRegistrations` answers when it registered the tuple, verbatim off 2.43.1.

    The envelope is `/api/dataValueSets`' own - a `WebMessage` wrapping an `ImportSummary` - which is why
    one projection reads both. A tuple registered for the first time counts `imported`; the same tuple
    registered again counts `updated`, and neither is a conflict.
    """
    return httpx.Response(
        200,
        json={
            "httpStatus": "OK",
            "httpStatusCode": 200,
            "status": "OK",
            "message": "Import was successful.",
            "response": {
                "responseType": "ImportSummary",
                "status": "SUCCESS",
                "description": "Import process complete.",
                "importCount": {"imported": 1, "updated": 0, "ignored": 0, "deleted": 0},
                "conflicts": [],
                "rejectedIndexes": [],
            },
        },
    )


def _refused_completeness() -> httpx.Response:
    """What `/api/completeDataSetRegistrations` answers a tuple it will not take, verbatim off 2.43.1."""
    return httpx.Response(
        409,
        json={
            "httpStatus": "Conflict",
            "httpStatusCode": 409,
            "status": "ERROR",
            "message": "An error occurred, please check import summary.",
            "response": {
                "responseType": "ImportSummary",
                "status": "ERROR",
                "description": "Import process complete.",
                "importCount": {"imported": 0, "updated": 0, "ignored": 1, "deleted": 0},
                "conflicts": [{"object": "NOSUCHDSXXX", "value": "Data set not found or not accessible"}],
                "rejectedIndexes": [],
            },
        },
    )


def _accepted_aggregate() -> httpx.Response:
    """What `/api/dataValueSets` answers when it took the envelope."""
    return httpx.Response(
        200,
        json={
            "httpStatus": "OK",
            "httpStatusCode": 200,
            "status": "OK",
            "message": "Import was successful.",
            "response": {
                "responseType": "ImportSummary",
                "status": "SUCCESS",
                "description": "Import process completed successfully",
                "importCount": {"imported": 2, "updated": 0, "ignored": 0, "deleted": 0},
            },
        },
    )


def _rejected_aggregate() -> httpx.Response:
    """A real `/api/dataValueSets` 409, verbatim off a live 2.42 instance.

    The report is **wrapped**: the body is a `WebMessage` whose `response` is the `ImportSummary`, and
    the summary carries an `importOptions` block the outcome has no interest in but has to survive.
    """
    return httpx.Response(
        409,
        json={
            "httpStatus": "Conflict",
            "httpStatusCode": 409,
            "status": "ERROR",
            "message": "An error occurred, please check import summary.",
            "response": {
                "responseType": "ImportSummary",
                "status": "ERROR",
                "importOptions": {
                    "idScheme": "UID",
                    "dataElementIdScheme": "UID",
                    "dryRun": True,
                    "async": False,
                    "importStrategy": "CREATE_AND_UPDATE",
                    "mergeMode": "REPLACE",
                    "reportMode": "FULL",
                    "skipExistingCheck": False,
                    "sharing": False,
                    "skipNotifications": False,
                    "skipAudit": False,
                },
                "description": "Data element not part of data set",
                "importCount": {"imported": 0, "updated": 0, "ignored": 2, "deleted": 0},
                "conflicts": [
                    {
                        "object": "De2aaaaaaaa",
                        "value": "Data element not part of data set",
                        "errorCode": "E7611",
                        "indexes": [0],
                    }
                ],
                "dataSetComplete": "false",
            },
        },
    )


def _accepted_tracker() -> httpx.Response:
    """What `/api/tracker` answers when it took the event."""
    return httpx.Response(
        200,
        json={
            "httpStatus": "OK",
            "httpStatusCode": 200,
            "status": "OK",
            "message": "Import was successful.",
            "response": {
                "status": "OK",
                "stats": {"created": 1, "updated": 0, "deleted": 0, "ignored": 0, "total": 1},
                "validationReport": {"errorReports": [], "warningReports": []},
            },
        },
    )


def _rejected_tracker() -> httpx.Response:
    """A real `/api/tracker` 409, verbatim off a live 2.42 instance.

    The report arrives **bare**. There is no `WebMessage` around it - no `httpStatus`, no `response` -
    so a reader that expects the envelope every other DHIS2 write answers with sees `response: None` and
    loses every error DHIS2 just took the trouble to name. Recognising the document by its own shape is
    the whole point of this fixture.
    """
    return httpx.Response(
        409,
        json={
            "status": "ERROR",
            "validationReport": {
                "errorReports": [
                    {
                        "message": "Event OrganisationUnit: `ImspTQPwCqd` and Program: `IpHINAT79UW`, do not match.",
                        "errorCode": "E1029",
                        "trackerType": "EVENT",
                        "uid": "Ev1aaaaaaaa",
                    }
                ],
                "warningReports": [],
            },
            "stats": {"created": 0, "updated": 0, "deleted": 0, "ignored": 1, "total": 1},
            "bundleReport": {"status": "OK", "typeReportMap": {}, "stats": {"created": 0, "ignored": 1, "total": 1}},
        },
    )


def _rejected_tracker_other_unit() -> httpx.Response:
    """The same broken rule against different objects - the case the reason rollup has to collapse."""
    return httpx.Response(
        409,
        json={
            "status": "ERROR",
            "validationReport": {
                "errorReports": [
                    {
                        "message": "Event OrganisationUnit: `DiszpKrYNg8` and Program: `WSGAb5XwJ3Y`, do not match.",
                        "errorCode": "E1029",
                        "trackerType": "EVENT",
                        "uid": "Ev2aaaaaaaa",
                    }
                ],
                "warningReports": [],
            },
            "stats": {"created": 0, "updated": 0, "deleted": 0, "ignored": 1, "total": 1},
        },
    )


def _two_event_spool() -> list[QuestionnaireResponse]:
    """The published example responses plus a second copy of the event one, so two payloads reach `/api/tracker`.

    A rollup collapses causes across responses, so proving it takes two responses that meet the same
    cause - and the forwarder posts one payload per receipt, so the second copy is the second post.
    """
    documents = _documents(GenerateConfig())
    event = next(document for document in documents if _form_kind(document) != "aggregate")
    return [*documents, event.model_copy(update={"id": f"{event.id}b"})]


def _write_probe_profile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Point profile resolution at a `probe` profile whose base url is the mocked instance."""
    config_dir = tmp_path / ".config" / "dhis2"
    config_dir.mkdir(parents=True)
    (config_dir / "profiles.toml").write_text(
        f"""
default = "probe"

[profiles.probe]
base_url = "{_BASE_URL}"
auth = "pat"
token = "d2p_test"
"""
    )
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_dir.parent))
    monkeypatch.delenv("DHIS2_PROFILE", raising=False)


@pytest.fixture
def forward_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A project with a compiled guide, a filled spool, and a `probe` profile pointing at the mock."""
    _write_probe_profile(tmp_path, monkeypatch)
    root = tmp_path / "project"
    root.mkdir()
    _write_project(root)
    _fill_spool(root, _documents(GenerateConfig()))
    monkeypatch.chdir(root)
    return root


async def _forward(root: Path, **keyword_arguments: Any) -> Any:
    """Run the forwarder against the fixture project with the resolved probe profile."""
    return await service.forward_responses(resolve(None).profile, load_project(root), **keyword_arguments)


@respx.mock
async def test_a_dry_run_posts_every_payload_under_the_endpoints_own_validate_only_mode(forward_project: Path) -> None:
    """The two families carry the two v42 spellings of validate-only, and nothing else changes."""
    routes = _mock_instance()
    report = await _forward(forward_project)
    assert report.dry_run is True
    assert dict(routes["aggregate"].calls.last.request.url.params) == {"dryRun": "true"}
    assert dict(routes["tracker"].calls.last.request.url.params) == {
        "importStrategy": "CREATE",
        "async": "false",
        "importMode": "VALIDATE",
    }


@respx.mock
async def test_an_import_run_drops_the_validate_only_parameters(forward_project: Path) -> None:
    """`--import` is the same two posts with the validate-only dial off, and nothing else added."""
    routes = _mock_instance()
    await _forward(forward_project, import_responses=True)
    assert dict(routes["aggregate"].calls.last.request.url.params) == {}
    assert dict(routes["tracker"].calls.last.request.url.params) == {"importStrategy": "CREATE", "async": "false"}


@respx.mock
async def test_each_payload_family_goes_to_the_endpoint_that_imports_it(forward_project: Path) -> None:
    """One data set and one event program: one aggregate envelope, one tracker event, one POST each."""
    routes = _mock_instance()
    report = await _forward(forward_project)
    assert report.spooled == 2
    assert routes["aggregate"].call_count == 1
    assert routes["tracker"].call_count == 1
    body = json.loads(routes["tracker"].calls.last.request.content)
    assert list(body) == ["events"]
    assert len(body["events"]) == 1
    assert json.loads(routes["aggregate"].calls.last.request.content)["dataSet"] == "BfMAe6Itzgt"


@respx.mock
async def test_the_value_types_are_read_id_only_for_the_data_elements_the_forms_bind(forward_project: Path) -> None:
    """One id-only read carries every bound data element, which is what disambiguates TRUE_ONLY."""
    routes = _mock_instance()
    await _forward(forward_project)
    params = dict(routes["value_types"].calls.last.request.url.params)
    assert params["fields"] == "id,valueType"
    assert params["filter"] == f"id:in:[{','.join(sorted(_VALUE_TYPES))}]"


@respx.mock
async def test_an_accepted_run_counts_and_files_every_response(forward_project: Path) -> None:
    """An import moves each accepted receipt out of the queue and says where it went."""
    _mock_instance()
    report = await _forward(forward_project, import_responses=True)
    assert (len(report.accepted), len(report.rejected), len(report.refused)) == (2, 0, 0)
    assert report.posted_count == 2
    assert not list((forward_project / RECEIVED_RESPONSES_RELATIVE_PATH).glob("*.json"))
    directory = forward_project / FORWARDED_RESPONSES_RELATIVE_PATH
    receipts = sorted(path.name for path in directory.glob("*.json") if not path.name.endswith(IMPORT_REPORT_SUFFIX))
    assert len(receipts) == 2
    assert all(outcome.spool_path.startswith(FORWARDED_RESPONSES_RELATIVE_PATH) for outcome in report.accepted)


@respx.mock
async def test_a_dry_run_moves_nothing(forward_project: Path) -> None:
    """The queue after a dry run is the queue before it, so the same run repeats as the import."""
    _mock_instance()
    report = await _forward(forward_project)
    assert len(list((forward_project / RECEIVED_RESPONSES_RELATIVE_PATH).glob("*.json"))) == 2
    assert not (forward_project / FORWARDED_RESPONSES_RELATIVE_PATH).exists()
    assert all(outcome.spool_path.startswith(RECEIVED_RESPONSES_RELATIVE_PATH) for outcome in report.outcomes)


@respx.mock
async def test_a_dhis2_rejection_is_recorded_rather_than_raised(forward_project: Path) -> None:
    """A 409 carries the same envelope a success does, so it is one response's outcome, not the run's."""
    _mock_instance(aggregate_response=_rejected_aggregate(), tracker_response=_rejected_tracker())
    report = await _forward(forward_project)
    assert len(report.rejected) == 2
    assert len(report.accepted) == 0
    rejected = {outcome.target_kind: outcome for outcome in report.rejected}

    aggregate = rejected["data-value-set"].import_outcome
    assert aggregate is not None
    assert aggregate.status == "ERROR"
    assert aggregate.message == "Data element not part of data set"
    assert (aggregate.created, aggregate.updated, aggregate.ignored) == (0, 0, 2)
    assert aggregate.data_value_summary is not None
    assert aggregate.data_value_summary.conflicts is not None
    assert [issue.error_code for issue in aggregate.issues] == ["E7611"]
    assert aggregate.issues[0].subject == "De2aaaaaaaa"
    assert aggregate.issues[0].message == "Data element not part of data set"

    event = rejected["event"].import_outcome
    assert event is not None
    assert event.status == "ERROR"
    assert (event.created, event.ignored) == (0, 1)
    assert event.tracker_report is not None
    assert event.tracker_report.validationReport is not None
    assert [issue.error_code for issue in event.issues] == ["E1029"]
    assert event.issues[0].subject == "Ev1aaaaaaaa"
    assert event.issues[0].message is not None
    assert "do not match" in event.issues[0].message
    assert "E1029 Ev1aaaaaaaa Event OrganisationUnit" in event.issues[0].line


@respx.mock
async def test_an_imported_rejection_moves_beside_a_report_that_says_why(forward_project: Path) -> None:
    """A rejected receipt lands in rejected/ with a sibling report, so the reason survives the run."""
    _mock_instance(aggregate_response=_rejected_aggregate(), tracker_response=_rejected_tracker())
    report = await _forward(forward_project, import_responses=True)
    directory = forward_project / REJECTED_RESPONSES_RELATIVE_PATH
    assert len(list(directory.glob("*.json"))) == 4
    for outcome in report.rejected:
        assert outcome.import_outcome is not None
        assert (directory / f"{outcome.response_id}.json").is_file()
        sidecar = directory / f"{outcome.response_id}{IMPORT_REPORT_SUFFIX}"
        written = json.loads(sidecar.read_text(encoding="utf-8"))
        assert written["status"] == outcome.import_outcome.status
        assert [issue["error_code"] for issue in written["issues"]] == [
            issue.error_code for issue in outcome.import_outcome.issues
        ]
        assert written["issues"][0]["message"]


@respx.mock
async def test_an_accepted_receipt_is_filed_beside_a_report_of_what_the_import_counted(
    forward_project: Path,
) -> None:
    """An acceptance takes its import report along, so what DHIS2 did with it survives the run."""
    _mock_instance()
    report = await _forward(forward_project, import_responses=True)
    directory = forward_project / FORWARDED_RESPONSES_RELATIVE_PATH
    assert len(report.accepted) == 2
    for outcome in report.accepted:
        assert outcome.import_outcome is not None
        sidecar = directory / f"{outcome.response_id}{IMPORT_REPORT_SUFFIX}"
        written = json.loads(sidecar.read_text(encoding="utf-8"))
        assert written["status"] == outcome.import_outcome.status
        assert written["created"] == outcome.import_outcome.created
        assert written["target_kind"] == outcome.target_kind
        # An acceptance names no rows against the payload, which is what separates the two sidecars.
        assert written.get("issues", []) == []


#: Three event responses go to one endpoint, so the posting order inside the drain is the spool order
#: and "the first was taken, the second met the failure, the third was never asked about" is expressible.
def _event_documents(count: int) -> list[QuestionnaireResponse]:
    """`count` published event responses, every one of which posts to `/api/tracker`."""
    config = GenerateConfig()
    plan = option_set_identities(_OPTION_SETS, config)
    captured = build_synthetic_responses(
        [_EVENT_PROGRAM], _OPTION_SETS, count, _ROOT_ORG_UNIT, _REFERENCE_DATE
    ).responses
    return list(
        build_example_documents(
            [_EVENT_PROGRAM], captured, _OPTION_SETS, config, _CANONICAL, option_set_plan=plan
        ).responses
    )


@pytest.fixture
def three_event_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A project whose spool holds three event receipts, drained one POST at a time in spool order."""
    _write_probe_profile(tmp_path, monkeypatch)
    root = tmp_path / "project"
    root.mkdir()
    _write_project(root)
    _fill_spool(root, _event_documents(3))
    monkeypatch.chdir(root)
    return root


def _server_error() -> httpx.Response:
    """A 500 carrying the `WebMessage` DHIS2 and the proxies in front of it answer a server error with.

    The body states `status: ERROR` exactly as a refused import does, which is the whole reason the
    status has to decide: read as a report, this is a rejection DHIS2 never made.
    """
    return httpx.Response(
        500,
        json={
            "httpStatus": "Internal Server Error",
            "httpStatusCode": 500,
            "status": "ERROR",
            "message": "PSQLException: connection pool exhausted",
        },
    )


@respx.mock
async def test_a_500_mid_drain_stops_and_moves_nothing_more(three_event_project: Path) -> None:
    """The instance failing part-way leaves the first import filed and everything behind it in the queue."""
    route = respx.post(f"{_BASE_URL}/api/tracker").mock(side_effect=[_accepted_tracker(), _server_error()])
    respx.get(f"{_BASE_URL}/api/system/info").mock(
        return_value=httpx.Response(200, json={"version": _HARVESTED_INSTANCE_VERSIONS["v42"]})
    )
    respx.get(f"{_BASE_URL}/api/dataElements").mock(
        return_value=httpx.Response(
            200, json={"dataElements": [{"id": uid, "valueType": value} for uid, value in _VALUE_TYPES.items()]}
        )
    )

    report = await _forward(three_event_project, import_responses=True)

    # The drain stopped at the failure rather than posting the third payload into an unwell instance.
    assert route.call_count == 2
    assert report.stopped is not None
    assert report.stopped.status_code == 500
    assert "500" in report.stopped.reason

    # The one DHIS2 took is filed; the one that met the 500 and the one behind it are untouched.
    kinds = {outcome.response_id: outcome.kind for outcome in report.outcomes}
    ordered = sorted(kinds)
    assert kinds[ordered[0]] == ForwardOutcomeKind.ACCEPTED
    assert kinds[ordered[1]] == ForwardOutcomeKind.NOT_POSTED
    assert kinds[ordered[2]] == ForwardOutcomeKind.NOT_POSTED

    received = sorted(path.name for path in (three_event_project / RECEIVED_RESPONSES_RELATIVE_PATH).glob("*.json"))
    assert received == [f"{ordered[1]}.json", f"{ordered[2]}.json"]
    forwarded = three_event_project / FORWARDED_RESPONSES_RELATIVE_PATH
    assert sorted(path.name for path in forwarded.glob("*.json")) == [
        f"{ordered[0]}.json",
        f"{ordered[0]}{IMPORT_REPORT_SUFFIX}",
    ]
    # A 500 is not DHIS2 refusing a payload, so nothing is filed as a rejection.
    assert not (three_event_project / REJECTED_RESPONSES_RELATIVE_PATH).exists()
    assert not report.rejected

    # The report says so rather than reading as a clean run that happened to be short.
    assert len(report.not_posted) == 2
    assert "2 not posted" in report.counts_line


@respx.mock
async def test_a_drain_that_cannot_reach_the_instance_stops_without_losing_what_it_posted(
    three_event_project: Path,
) -> None:
    """A connection that never completes stops the drain too, and the receipt it met stays put."""
    route = respx.post(f"{_BASE_URL}/api/tracker").mock(
        side_effect=[_accepted_tracker(), httpx.ConnectError("connection refused")]
    )
    respx.get(f"{_BASE_URL}/api/system/info").mock(
        return_value=httpx.Response(200, json={"version": _HARVESTED_INSTANCE_VERSIONS["v42"]})
    )
    respx.get(f"{_BASE_URL}/api/dataElements").mock(
        return_value=httpx.Response(
            200, json={"dataElements": [{"id": uid, "valueType": value} for uid, value in _VALUE_TYPES.items()]}
        )
    )

    report = await _forward(three_event_project, import_responses=True)

    assert route.call_count == 2
    assert report.stopped is not None
    assert report.stopped.status_code is None
    assert "could not be reached" in report.stopped.reason
    assert len(report.accepted) == 1
    assert len(report.not_posted) == 2
    assert len(list((three_event_project / RECEIVED_RESPONSES_RELATIVE_PATH).glob("*.json"))) == 2


@respx.mock
async def test_a_refused_response_never_reaches_dhis2_and_stays_in_the_queue(forward_project: Path) -> None:
    """A receipt the translator cannot read whole is not posted, is not moved, and is named in the report."""
    routes = _mock_instance()
    orphan = forward_project / RECEIVED_RESPONSES_RELATIVE_PATH / "orphan.json"
    orphan.write_text(
        json.dumps(
            {
                "response_id": "orphan",
                "received_at": "2026-08-08T09:00:00Z",
                "form_kind": "aggregate",
                "questionnaire": f"{_CANONICAL}/Questionnaire/nothing-published",
                "response": {
                    "resourceType": "QuestionnaireResponse",
                    "id": "orphan",
                    "questionnaire": f"{_CANONICAL}/Questionnaire/nothing-published",
                    "status": "completed",
                },
            }
        ),
        encoding="utf-8",
    )
    report = await _forward(forward_project, import_responses=True)
    assert report.spooled == 3
    assert routes["aggregate"].call_count + routes["tracker"].call_count == 2
    refused = report.refused
    assert [outcome.response_id for outcome in refused] == ["orphan"]
    assert refused[0].kind == ForwardOutcomeKind.REFUSED
    assert refused[0].refusals[0].category == "no-form-type"
    assert orphan.is_file()
    assert refused[0].spool_path == f"{RECEIVED_RESPONSES_RELATIVE_PATH}/orphan.json"


def _orphan_receipt(project_root: Path) -> Path:
    """One queued receipt naming a Questionnaire the compiled guide does not hold, which every drain refuses."""
    orphan = project_root / RECEIVED_RESPONSES_RELATIVE_PATH / "orphan.json"
    orphan.write_text(
        json.dumps(
            {
                "response_id": "orphan",
                "received_at": "2026-08-08T09:00:00Z",
                "form_kind": "aggregate",
                "questionnaire": f"{_CANONICAL}/Questionnaire/nothing-published",
                "response": {
                    "resourceType": "QuestionnaireResponse",
                    "id": "orphan",
                    "questionnaire": f"{_CANONICAL}/Questionnaire/nothing-published",
                    "status": "completed",
                },
            }
        ),
        encoding="utf-8",
    )
    return orphan


@respx.mock
async def test_a_committing_drain_writes_the_refusal_record_and_the_next_one_counts_up(
    forward_project: Path,
) -> None:
    """The queue keeps the drain's mark: when it refused, how often it has, and why - and a retry counts up."""
    _mock_instance()
    orphan = _orphan_receipt(forward_project)
    marker = orphan.with_name(f"orphan{REFUSAL_RECORD_SUFFIX}")

    await _forward(forward_project, import_responses=True)

    record = ForwardRefusalRecord.model_validate_json(marker.read_text(encoding="utf-8"))
    assert record.attempt_count == 1
    assert record.reasons[0].category == "no-form-type"
    assert record.refused_at.endswith("Z")

    await _forward(forward_project, import_responses=True)

    record = ForwardRefusalRecord.model_validate_json(marker.read_text(encoding="utf-8"))
    assert record.attempt_count == 2
    assert orphan.is_file()


@respx.mock
async def test_a_dry_run_writes_no_refusal_record(forward_project: Path) -> None:
    """A dry run files nothing and marks nothing, exactly as it moves nothing."""
    _mock_instance()
    orphan = _orphan_receipt(forward_project)

    await _forward(forward_project)

    assert not orphan.with_name(f"orphan{REFUSAL_RECORD_SUFFIX}").exists()


@respx.mock
async def test_the_coded_answer_dial_defaults_to_what_the_serve_table_says(forward_project: Path) -> None:
    """A project that captures strictly forwards strictly, without stating it twice."""
    _mock_instance()
    lenient = await _forward(forward_project)
    assert lenient.coded_answer_mode == CodedAnswerMode.LENIENT
    _write_project(forward_project, strict_codes=True)
    strict = await _forward(forward_project)
    assert strict.coded_answer_mode == CodedAnswerMode.STRICT
    overridden = await _forward(forward_project, coded_answer_mode=CodedAnswerMode.LENIENT)
    assert overridden.coded_answer_mode == CodedAnswerMode.LENIENT


@respx.mock
async def test_an_empty_spool_is_a_run_with_nothing_to_do(forward_project: Path) -> None:
    """No receipts is not an error - it is a project nothing has been captured into yet."""
    _mock_instance()
    for path in (forward_project / RECEIVED_RESPONSES_RELATIVE_PATH).glob("*.json"):
        path.unlink()
    report = await _forward(forward_project)
    assert (report.spooled, report.posted_count, report.outcomes) == (0, 0, ())


@respx.mock
async def test_an_empty_spool_reads_nothing_from_the_instance(forward_project: Path) -> None:
    """Zero receipts is answered off disk: no client opened, no metadata read, no request at all."""
    routes = _mock_instance()
    for path in (forward_project / RECEIVED_RESPONSES_RELATIVE_PATH).glob("*.json"):
        path.unlink()

    report = await _forward(forward_project)

    assert (report.spooled, report.posted_count, report.outcomes) == (0, 0, ())
    # The reads past the spool exist to translate receipts, so a run with none pays for none -
    # not even the version probe every opened client makes.
    assert list(respx.calls) == []
    assert [route.call_count for route in routes.values()] == [0] * len(routes)


@respx.mock
async def test_an_empty_spool_with_no_compiled_guide_never_builds_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The unbounded live build is what receipts pay for; none of them means it is never opened."""
    _write_probe_profile(tmp_path, monkeypatch)
    root = tmp_path / "uncompiled"
    root.mkdir()
    _write_project(root, compiled=False)
    routes = _mock_instance()

    report = await _forward(root)

    assert (report.spooled, report.outcomes) == (0, ())
    assert list(respx.calls) == []
    assert [route.call_count for route in routes.values()] == [0] * len(routes)


@respx.mock
async def test_an_unreadable_receipt_on_an_otherwise_empty_spool_is_quarantined_for_free(forward_project: Path) -> None:
    """The spool is read before the run short-circuits, so the quarantine is reported at zero request cost."""
    routes = _mock_instance()
    for path in (forward_project / RECEIVED_RESPONSES_RELATIVE_PATH).glob("*.json"):
        path.unlink()
    broken = forward_project / RECEIVED_RESPONSES_RELATIVE_PATH / "broken.json"
    broken.write_text("{not json", encoding="utf-8")

    report = await _forward(forward_project)

    assert (report.spooled, report.outcomes) == (0, ())
    assert [entry.file_name for entry in report.quarantined] == ["broken.json"]
    assert list(respx.calls) == []
    assert [route.call_count for route in routes.values()] == [0] * len(routes)


@respx.mock
async def test_an_unreadable_receipt_is_quarantined_and_the_drain_proceeds(forward_project: Path) -> None:
    """A receipt silently skipped would look to its sender exactly like one that never arrived - so it is named.

    Named rather than fatal: aborting the drain over one unreadable file would cost every other
    receipt its turn, which is the larger silence. The file moves to `malformed/` with its reason
    written beside it, the report says so, and everything else forwards.
    """
    _mock_instance()
    broken = forward_project / RECEIVED_RESPONSES_RELATIVE_PATH / "broken.json"
    broken.write_text("{not json", encoding="utf-8")

    report = await _forward(forward_project)

    assert [entry.file_name for entry in report.quarantined] == ["broken.json"]
    assert "not readable as JSON" in report.quarantined[0].reason
    assert report.spooled > 0
    assert not broken.exists()
    quarantined = forward_project / MALFORMED_RESPONSES_RELATIVE_PATH / "broken.json"
    assert quarantined.is_file()


@respx.mock
async def test_an_unreadable_spool_directory_fails_the_run(forward_project: Path) -> None:
    """One bad file is quarantined; a directory the process cannot read is a failure of the whole drain."""
    _mock_instance()
    received = forward_project / RECEIVED_RESPONSES_RELATIVE_PATH
    received.chmod(0o000)
    try:
        with pytest.raises(SpoolReadError, match="cannot be read"):
            await _forward(forward_project)
    finally:
        received.chmod(0o755)


def test_the_context_is_assembled_from_the_published_guide(forward_project: Path) -> None:
    """Both compiled trees are read: the forms from fsh-generated, the ConceptMaps and Locations from input."""
    project = load_project(forward_project)
    artifacts = load_compiled_artifacts(project)
    assert len(artifacts.questionnaires) == 2
    assert len(artifacts.code_systems) == 1
    assert len(artifacts.value_sets) == 1
    assert len(artifacts.concept_maps) == 1
    assert len(artifacts.locations) == 1
    context = build_project_context(project, artifacts, value_types_by_data_element=_VALUE_TYPES)
    assert sorted(form.form_kind for form in context.forms.values()) == ["aggregate", "event"]
    assert context.resolves_organisation_units is True


def test_an_unreadable_form_fails_the_load_and_an_unreadable_terminology_is_left_out(forward_project: Path) -> None:
    """A skipped form would refuse every response answering it; a skipped CodeSystem costs only its codes."""
    predefined = forward_project / "ig" / "input" / "resources"
    (predefined / "CodeSystem-handwritten.json").write_text(
        json.dumps({"resourceType": "CodeSystem", "id": "handwritten", "somethingThisPackageHasNoModelFor": True}),
        encoding="utf-8",
    )
    artifacts = load_compiled_artifacts(load_project(forward_project))
    assert len(artifacts.code_systems) == 1
    assert len(artifacts.unreadable_resources) == 1
    assert "CodeSystem-handwritten.json" in artifacts.unreadable_resources[0]

    (predefined / "Questionnaire-handwritten.json").write_text(
        json.dumps({"resourceType": "Questionnaire", "id": "handwritten", "notAQuestionnaireElement": True}),
        encoding="utf-8",
    )
    with pytest.raises(CompiledArtifactReadError, match="Questionnaire-handwritten.json"):
        load_compiled_artifacts(load_project(forward_project))


def test_a_project_with_no_compiled_ig_says_which_two_commands_fill_it(tmp_path: Path) -> None:
    """Forwarding reads what SUSHI wrote, so an uncompiled project is a one-line refusal, not a traceback."""
    root = tmp_path / "uncompiled"
    root.mkdir()
    _write_project(root, compiled=False)
    with pytest.raises(CompiledIgMissingError, match="make sushi"):
        load_compiled_artifacts(load_project(root))


def test_a_project_with_no_compiled_guide_builds_one_off_the_instance(tmp_path: Path) -> None:
    """A live capture UI needs no build step, so the drain that empties its spool needs none either."""
    root = tmp_path / "uncompiled"
    root.mkdir()
    _write_project(root, compiled=False)

    assert service._compiled_artifacts_or_none(load_project(root)) is None


def test_turning_the_live_build_off_restores_the_refusal_naming_the_two_commands(tmp_path: Path) -> None:
    """`[forward] live = false` is the posture for a deployment forwarding only a reviewed, published guide."""
    root = tmp_path / "uncompiled-strict"
    root.mkdir()
    _write_project(root, compiled=False)
    (root / "fhir.toml").write_text(
        f"{(root / 'fhir.toml').read_text(encoding='utf-8')}\n[forward]\nlive = false\n", encoding="utf-8"
    )

    with pytest.raises(CompiledIgMissingError, match="make sushi"):
        service._compiled_artifacts_or_none(load_project(root))


def test_a_compiled_guide_is_read_off_disk_rather_than_built(forward_project: Path) -> None:
    """The live build is what a project holding no guide falls to, never what one holding a guide pays for."""
    artifacts = service._compiled_artifacts_or_none(load_project(forward_project))

    assert artifacts is not None
    assert artifacts.questionnaires


def test_built_documents_are_collected_into_the_five_types_the_translator_reads() -> None:
    """One collection point serves both ways a guide reaches the translator, so neither can drift."""
    from dhis2w_fhir.conversion.artifacts import SourcedDocument, collect_artifacts

    collected = collect_artifacts(
        [
            SourcedDocument(source="built live", body={"resourceType": "Questionnaire", "url": f"{_CANONICAL}/Q/one"}),
            SourcedDocument(source="built live", body={"resourceType": "CodeSystem", "url": f"{_CANONICAL}/CS/one"}),
            SourcedDocument(source="built live", body={"resourceType": "ValueSet", "url": f"{_CANONICAL}/VS/one"}),
            SourcedDocument(source="built live", body={"resourceType": "ConceptMap", "url": f"{_CANONICAL}/CM/one"}),
            SourcedDocument(source="built live", body={"resourceType": "Location", "id": _ROOT_ORG_UNIT}),
            SourcedDocument(source="built live", body={"resourceType": "StructureDefinition", "id": "passed-over"}),
        ]
    )

    assert len(collected.questionnaires) == 1
    assert len(collected.code_systems) == 1
    assert len(collected.value_sets) == 1
    assert len(collected.concept_maps) == 1
    assert len(collected.locations) == 1
    assert collected.resource_count == 5


def test_the_bound_data_elements_are_read_through_the_link_id_grammar(forward_project: Path) -> None:
    """A disaggregated cell's `<dataElement>.<combo>` link id contributes its data element once."""
    project = load_project(forward_project)
    artifacts = load_compiled_artifacts(project)
    naming = ConversionNaming.from_config(project.config.generate, project.config.ig.canonical)
    bound = bound_question_uids(artifacts, naming)
    assert bound.data_element_uids == tuple(sorted(_VALUE_TYPES))
    assert bound.tracked_entity_attribute_uids == ()


@respx.mock
def test_the_command_drains_the_whole_spool_end_to_end(forward_project: Path) -> None:
    """No mock but the instance: `d2w fhir forward` off a real project, through the real service.

    Everything else in this file calls the service directly and everything in
    `test_fhir_forward_cli.py` mocks it, so this is the one case that proves the two halves meet -
    the dry run being the path a first run against a live instance always takes.
    """
    from dhis2w_cli.main import build_app
    from typer.testing import CliRunner

    routes = _mock_instance()
    result = CliRunner().invoke(build_app(), ["fhir", "forward", str(forward_project), "--no-progress"])
    assert result.exit_code == 0, result.output
    assert "DRY RUN" in result.output
    assert routes["aggregate"].call_count == 1
    assert routes["tracker"].call_count == 1
    assert len(list((forward_project / RECEIVED_RESPONSES_RELATIVE_PATH).glob("*.json"))) == 2
    assert (forward_project / "reports" / "fhir-forward-report.md").is_file()


@respx.mock
async def test_a_bare_tracker_report_is_read_even_though_no_envelope_wrapped_it(forward_project: Path) -> None:
    """`/api/tracker` answers a refusal with the report itself, and losing that loses every reason there is.

    The regression this guards is exact: read through `WebMessage`, the bare document parses with
    `response = None`, and the outcome comes out empty - `status: ERROR` and nothing a user can act on.
    """
    _mock_instance(tracker_response=_rejected_tracker())
    report = await _forward(forward_project)
    event = next(outcome for outcome in report.rejected if outcome.target_kind == "event").import_outcome
    assert event is not None
    assert event.tracker_report is not None
    assert event.issues
    assert event.issues[0].message is not None
    assert event.ignored == 1


@respx.mock
async def test_the_rejections_roll_up_by_cause_with_the_quoted_uids_generalised(forward_project: Path) -> None:
    """One broken rule against two different pairs of objects is one cause of the run, not two."""
    _mock_instance(
        aggregate_response=_rejected_aggregate(),
        tracker_response=_rejected_tracker(),
    )
    respx.post(f"{_BASE_URL}/api/tracker").mock(
        side_effect=[_rejected_tracker(), _rejected_tracker_other_unit()],
    )
    _fill_spool(forward_project, _two_event_spool())
    report = await _forward(forward_project)
    reasons = {reason.error_code: reason for reason in report.rejection_reasons}
    assert set(reasons) == {"E7611", "E1029"}
    assert reasons["E1029"].reason == "Event OrganisationUnit: `...` and Program: `...`, do not match."
    assert reasons["E1029"].responses == 2
    assert reasons["E7611"].responses == 1
    assert [reason.responses for reason in report.rejection_reasons] == sorted(
        (reason.responses for reason in report.rejection_reasons), reverse=True
    )


@respx.mock
async def test_one_rule_worded_two_ways_is_still_one_cause_of_the_run(forward_project: Path) -> None:
    """The rollup groups on the error code, so the sentence 2.42 and 2.43 word differently stays one row.

    The two bodies are the same provocation harvested off two majors, so the drift here is DHIS2's own -
    2.42 says "program defined in enrollment", 2.43 says "Program defined in Enrollment", one rule either way.
    """
    _mock_instance(aggregate_response=_rejected_aggregate(), tracker_response=_rejected_tracker())
    respx.post(f"{_BASE_URL}/api/tracker").mock(
        side_effect=[_harvested_absent_enrollment_409("v42"), _harvested_absent_enrollment_409("v43")],
    )
    _fill_spool(forward_project, _two_event_spool())
    report = await _forward(forward_project)
    reasons = {reason.error_code: reason for reason in report.rejection_reasons}
    assert set(reasons) == {"E7611", "E1313", "E1079"}
    assert reasons["E1079"].responses == 2
    # The sample shown is the first wording the run met, generalised - not a second row beside it.
    assert reasons["E1079"].reason == (
        "Event: `...`, program: `...` is different from program defined in enrollment `...`."
    )


#: The data set on a non-default attribute category combo, whose every value carries a third key.
_PROJECT_COMBO = CategoryComboIn(
    uid="idcDPkDtepR",
    name="Project",
    option_combos=[
        CategoryOptionComboIn(uid="Aoc1aaaaaaa", name="Clean water", code="PRJ_WATER"),
        CategoryOptionComboIn(uid="Aoc2aaaaaaa", name="Basic education", code="PRJ_SCHOOL"),
    ],
)

_PROJECT_DATA_SET = QuestionnaireSourceIn(
    uid="TuL8IOPzpHh",
    name="Project funding",
    kind="aggregate",
    period_type="Monthly",
    attribute_combo=_PROJECT_COMBO,
    sections=[
        QuestionnaireSectionIn(
            uid="Sec2aaaaaaa",
            name="Funding",
            items=[QuestionnaireItemIn(uid="Dea0aaaaaaa", name="Amount spent", value_type="INTEGER")],
        )
    ],
)

_PROJECT_COMBO_SYSTEM = f"{_CANONICAL}/CodeSystem/d2-aoc-idcDPkDtepR-cs"


def _write_combo_project(root: Path) -> None:
    """Write a project whose one data set rides a non-default combo, terminology and ConceptMap included."""
    (root / "fhir.toml").write_text(_FHIR_TOML.format(strict="false"), encoding="utf-8")
    compiled_directory = root / "ig" / "fsh-generated" / "resources"
    compiled_directory.mkdir(parents=True, exist_ok=True)
    predefined_directory = root / "ig" / "input" / "resources"
    predefined_directory.mkdir(parents=True, exist_ok=True)
    config = GenerateConfig()
    sources = [_PROJECT_DATA_SET]
    combos = build_attribute_combo_artifacts(sources, config, _CANONICAL, ig_status="draft")
    build = build_questionnaire_documents(
        sources,
        config,
        _CANONICAL,
        ig_status="draft",
        option_set_plan=option_set_identities([], config),
        attribute_codes=AttributeCodeIndex(),
        attribute_combos=combos.plan,
    )
    for questionnaire in build.questionnaires:
        _write_resource(compiled_directory / f"Questionnaire-{questionnaire.id}.json", questionnaire)
    for artifact in combos.artifacts:
        name = artifact.relative_path.rsplit("/", 1)[-1]
        (predefined_directory / name).write_text(artifact.content, encoding="utf-8")
    for concept_map in build_attribute_combo_concept_maps(sources, config, _CANONICAL, ig_status="draft"):
        _write_resource(predefined_directory / f"ConceptMap-{concept_map.id}.json", concept_map)
    naming = ConversionNaming.from_config(config, _CANONICAL)
    _write_resource(
        predefined_directory / f"Location-{_ROOT_ORG_UNIT}.json",
        Location(
            id=_ROOT_ORG_UNIT, identifier=[Identifier(system=naming.organisation_unit_system, value=_ROOT_ORG_UNIT)]
        ),
    )


def _combo_documents(config: GenerateConfig) -> list[QuestionnaireResponse]:
    """The one example response the non-default-combo data set publishes, keyed to a real combo."""
    sources = [_PROJECT_DATA_SET]
    captured = build_synthetic_responses(sources, [], 1, _ROOT_ORG_UNIT, _REFERENCE_DATE).responses
    return list(
        build_example_documents(
            sources,
            captured,
            [],
            config,
            _CANONICAL,
            option_set_plan=option_set_identities([], config),
            attribute_combos=build_attribute_combo_artifacts(sources, config, _CANONICAL, ig_status="draft").plan,
        ).responses
    )


@pytest.fixture
def combo_forward_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A project holding only the non-default-combo data set, its spool filled with that form's example."""
    config_dir = tmp_path / ".config" / "dhis2"
    config_dir.mkdir(parents=True)
    (config_dir / "profiles.toml").write_text(
        f"""
default = "probe"

[profiles.probe]
base_url = "{_BASE_URL}"
auth = "pat"
token = "d2p_test"
"""
    )
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_dir.parent))
    monkeypatch.delenv("DHIS2_PROFILE", raising=False)
    root = tmp_path / "combo-project"
    root.mkdir()
    _write_combo_project(root)
    _fill_spool(root, _combo_documents(GenerateConfig()))
    monkeypatch.chdir(root)
    return root


@respx.mock
async def test_a_non_default_data_set_posts_its_attribute_option_combo_on_the_wire(
    combo_forward_project: Path,
) -> None:
    """The third key rides the `/api/dataValueSets` envelope, resolved back to the DHIS2 UID it names."""
    routes = _mock_instance()

    report = await _forward(combo_forward_project)

    assert report.refused == ()
    assert routes["aggregate"].call_count == 1
    body = json.loads(routes["aggregate"].calls.last.request.content)
    assert body["dataSet"] == "TuL8IOPzpHh"
    assert body["attributeOptionCombo"] in {"Aoc1aaaaaaa", "Aoc2aaaaaaa"}


@respx.mock
async def test_a_response_naming_no_attribute_option_combo_is_refused_and_stays_in_the_queue(
    combo_forward_project: Path,
) -> None:
    """A payload DHIS2 would refuse with `E8023` never reaches it, and the refusal reads as one line."""
    routes = _mock_instance()
    naming = ConversionNaming.from_config(GenerateConfig(), _CANONICAL)
    for path in (combo_forward_project / RECEIVED_RESPONSES_RELATIVE_PATH).glob("*.json"):
        envelope = json.loads(path.read_text(encoding="utf-8"))
        envelope["response"]["extension"] = [
            extension
            for extension in envelope["response"]["extension"]
            if extension["url"] != naming.attribute_option_combo_url
        ]
        path.write_text(json.dumps(envelope, indent=2), encoding="utf-8")

    report = await _forward(combo_forward_project)

    assert routes["aggregate"].call_count == 0
    assert len(report.refused) == 1
    refusal = report.refused[0].refusals[0]
    assert refusal.category == "missing-attribute-option-combo"
    assert "E8023" in refusal.reason
    assert report.refused[0].spool_path.startswith(RECEIVED_RESPONSES_RELATIVE_PATH)


#: A tracker program and one of its stages, which the ordering case drains together. Their receipts
#: land in the spool the other way round - `A03MvHHogjR-...` sorts before `En1aaaaaaaa` - so a run
#: that posted in spool order would post the event first, which is exactly what `E1313` refuses.
_TRACKER_PROGRAM = QuestionnaireSourceIn(
    uid="IpHINAT79UW",
    name="Child Programme",
    kind="tracker",
    tracked_entity_type_uid="nEenWmSyUEp",
    flat_items=[
        QuestionnaireItemIn(
            uid="w75KJ2mc4zz", name="First name", value_type="TEXT", compulsory=True, entity_level=True
        ),
        QuestionnaireItemIn(uid="TeaHousehld", name="Household size", value_type="INTEGER", entity_level=False),
    ],
)

_BIRTH_STAGE = QuestionnaireSourceIn(
    uid="A03MvHHogjR",
    name="Birth",
    kind="tracker-event",
    program=ProgramContextIn(uid="IpHINAT79UW", name="Child Programme"),
    flat_items=[QuestionnaireItemIn(uid="a3kGcGDCuk6", name="Apgar Score", value_type="INTEGER")],
)

_TRACKER_SOURCES = [_TRACKER_PROGRAM, _BIRTH_STAGE]

#: The tracker identities the two receipts share, as one client capturing both in a sitting mints them.
_MINTED_TRACKED_ENTITY = "TeAaBbCcDd1"
_MINTED_ENROLLMENT = "EnAaBbCcDd1"


def _tracker_captures() -> list[ExampleResponseIn]:
    """One registration and one stage event of the same enrollment, as a client captured them."""
    return [
        ExampleResponseIn(
            instance_id="En1aaaaaaaa",
            target_uid=_TRACKER_PROGRAM.uid,
            kind="tracker",
            organisation_unit_uid=_ROOT_ORG_UNIT,
            status_code="completed",
            authored="2026-01-04T08:00:00Z",
            tracked_entity_uid=_MINTED_TRACKED_ENTITY,
            enrollment_uid=_MINTED_ENROLLMENT,
            enrolled_at="2026-01-04T08:00:00Z",
            answers=[
                ExampleAnswerIn(data_element_uid="w75KJ2mc4zz", value="Amara"),
                ExampleAnswerIn(data_element_uid="TeaHousehld", value="4"),
            ],
        ),
        ExampleResponseIn(
            instance_id="A03MvHHogjR-example-1",
            target_uid=_BIRTH_STAGE.uid,
            kind="tracker-event",
            organisation_unit_uid=_ROOT_ORG_UNIT,
            status_code="completed",
            authored="2026-01-05T09:30:00Z",
            tracked_entity_uid=_MINTED_TRACKED_ENTITY,
            enrollment_uid=_MINTED_ENROLLMENT,
            answers=[ExampleAnswerIn(data_element_uid="a3kGcGDCuk6", value="9")],
        ),
    ]


def _write_tracker_project(root: Path) -> None:
    """Write a project publishing one tracker program's whole capture surface, and nothing else."""
    (root / "fhir.toml").write_text(_FHIR_TOML.format(strict="false"), encoding="utf-8")
    compiled_directory = root / "ig" / "fsh-generated" / "resources"
    compiled_directory.mkdir(parents=True, exist_ok=True)
    predefined_directory = root / "ig" / "input" / "resources"
    predefined_directory.mkdir(parents=True, exist_ok=True)
    config = GenerateConfig()
    build = build_questionnaire_documents(
        _TRACKER_SOURCES,
        config,
        _CANONICAL,
        ig_status="draft",
        option_set_plan=option_set_identities([], config),
        attribute_codes=AttributeCodeIndex(),
    )
    for questionnaire in build.questionnaires:
        _write_resource(compiled_directory / f"Questionnaire-{questionnaire.id}.json", questionnaire)
    naming = ConversionNaming.from_config(config, _CANONICAL)
    _write_resource(
        predefined_directory / f"Location-{_ROOT_ORG_UNIT}.json",
        Location(
            id=_ROOT_ORG_UNIT, identifier=[Identifier(system=naming.organisation_unit_system, value=_ROOT_ORG_UNIT)]
        ),
    )
    documents = build_example_documents(
        _TRACKER_SOURCES,
        _tracker_captures(),
        [],
        config,
        _CANONICAL,
        option_set_plan=option_set_identities([], config),
    ).responses
    _fill_spool(root, list(documents))


def _mock_tracker_instance() -> respx.Route:
    """Mock the version probe, both value-type reads, and the one import endpoint a tracker drain posts to."""
    respx.get(f"{_BASE_URL}/api/system/info").mock(
        return_value=httpx.Response(200, json={"version": _HARVESTED_INSTANCE_VERSIONS["v42"]})
    )
    respx.get(f"{_BASE_URL}/api/dataElements").mock(
        return_value=httpx.Response(200, json={"dataElements": [{"id": "a3kGcGDCuk6", "valueType": "INTEGER"}]})
    )
    respx.get(f"{_BASE_URL}/api/trackedEntityAttributes").mock(
        return_value=httpx.Response(
            200,
            json={
                "trackedEntityAttributes": [
                    {"id": "w75KJ2mc4zz", "valueType": "TEXT"},
                    {"id": "TeaHousehld", "valueType": "INTEGER"},
                ]
            },
        )
    )
    return respx.post(f"{_BASE_URL}/api/tracker").mock(return_value=_accepted_tracker())


@pytest.fixture
def tracker_forward_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A project publishing one tracker program's whole surface, its spool holding a registration and a stage."""
    _write_probe_profile(tmp_path, monkeypatch)
    root = tmp_path / "project"
    root.mkdir()
    _write_tracker_project(root)
    monkeypatch.chdir(root)
    return root


@respx.mock
async def test_a_registration_posts_before_the_events_of_the_same_drain(tracker_forward_project: Path) -> None:
    """An event's enrollment may have been minted seconds earlier, so the registration goes to DHIS2 first."""
    tracker = _mock_tracker_instance()

    report = await _forward(tracker_forward_project, import_responses=True)

    posted = [json.loads(call.request.content) for call in tracker.calls]
    assert [sorted(body) for body in posted] == [["trackedEntities"], ["events"]]
    assert report.rejected == ()
    assert len(report.accepted) == 2


@respx.mock
async def test_a_posted_registration_carries_the_enrollment_its_stage_event_names(
    tracker_forward_project: Path,
) -> None:
    """The pair travels as minted, which is what makes a drain of both land rather than earn `E1313`."""
    tracker = _mock_tracker_instance()

    await _forward(tracker_forward_project, import_responses=True)

    registration, event = (json.loads(call.request.content) for call in tracker.calls)
    tracked_entity = registration["trackedEntities"][0]
    assert tracked_entity["trackedEntity"] == _MINTED_TRACKED_ENTITY
    assert tracked_entity["trackedEntityType"] == "nEenWmSyUEp"
    assert tracked_entity["enrollments"][0]["enrollment"] == _MINTED_ENROLLMENT
    assert tracked_entity["enrollments"][0]["status"] == "ACTIVE"
    assert event["events"][0]["enrollment"] == _MINTED_ENROLLMENT
    assert event["events"][0]["trackedEntity"] == _MINTED_TRACKED_ENTITY


@respx.mock
async def test_a_posted_registration_states_each_answer_at_the_dhis2_level_the_form_published(
    tracker_forward_project: Path,
) -> None:
    """An entity attribute is written on the person, a program-only attribute on the enrollment it creates."""
    tracker = _mock_tracker_instance()

    await _forward(tracker_forward_project, import_responses=True)

    registration = json.loads(tracker.calls[0].request.content)
    tracked_entity = registration["trackedEntities"][0]
    assert tracked_entity["attributes"] == [{"attribute": "w75KJ2mc4zz", "value": "Amara"}]
    assert tracked_entity["enrollments"][0]["attributes"] == [{"attribute": "TeaHousehld", "value": "4"}]


#: The UID of a person the instance already holds, which a linked registration enrols rather than creates.
_EXISTING_TRACKED_ENTITY = "TeZzYyXxWw9"


def _linked_tracker_captures() -> list[ExampleResponseIn]:
    """One registration of a person the instance already holds, and one stage event of its enrollment."""
    registration, stage = _tracker_captures()
    return [
        registration.model_copy(
            update={
                "tracked_entity_uid": _EXISTING_TRACKED_ENTITY,
                "answers": [ExampleAnswerIn(data_element_uid="TeaHousehld", value="4")],
            }
        ),
        stage.model_copy(update={"tracked_entity_uid": _EXISTING_TRACKED_ENTITY}),
    ]


def _write_linked_tracker_project(root: Path) -> None:
    """Write the tracker project with a spool whose registration names a person the instance already holds."""
    _write_tracker_project(root)
    naming = ConversionNaming.from_config(GenerateConfig(), _CANONICAL)
    documents = build_example_documents(
        _TRACKER_SOURCES,
        _linked_tracker_captures(),
        [],
        GenerateConfig(),
        _CANONICAL,
        option_set_plan=option_set_identities([], GenerateConfig()),
    ).responses
    marked = [
        document.model_copy(
            update={
                "extension": [
                    *(document.extension or []),
                    Extension(url=naming.subject_exists_url, valueBoolean=True),
                ]
            }
        )
        if document.id == "En1aaaaaaaa"
        else document
        for document in documents
    ]
    _fill_spool(root, marked)


@pytest.fixture
def linked_forward_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A tracker project whose spooled registration enrols a person the instance already holds."""
    _write_probe_profile(tmp_path, monkeypatch)
    root = tmp_path / "project"
    root.mkdir()
    _write_linked_tracker_project(root)
    monkeypatch.chdir(root)
    return root


@respx.mock
async def test_enrolling_a_person_the_instance_holds_posts_a_top_level_enrollments_array(
    linked_forward_project: Path,
) -> None:
    """The one wire shape that enrols without touching the person: no `trackedEntities` wrapper anywhere."""
    tracker = _mock_tracker_instance()

    report = await _forward(linked_forward_project, import_responses=True)

    posted = [json.loads(call.request.content) for call in tracker.calls]
    assert [sorted(body) for body in posted] == [["enrollments"], ["events"]]
    enrollment = posted[0]["enrollments"][0]
    assert enrollment["trackedEntity"] == _EXISTING_TRACKED_ENTITY
    assert enrollment["enrollment"] == _MINTED_ENROLLMENT
    assert enrollment["program"] == _TRACKER_PROGRAM.uid
    assert enrollment["orgUnit"] == _ROOT_ORG_UNIT
    assert enrollment["status"] == "ACTIVE"
    assert enrollment["attributes"] == [{"attribute": "TeaHousehld", "value": "4"}]
    assert report.rejected == ()
    assert len(report.accepted) == 2


@respx.mock
async def test_an_enrollment_only_import_goes_under_plain_create(linked_forward_project: Path) -> None:
    """`CREATE_AND_UPDATE` rewrites the person's owning organisation unit (BUGS.md 73), so CREATE it is."""
    tracker = _mock_tracker_instance()

    await _forward(linked_forward_project, import_responses=True)

    params = tracker.calls[0].request.url.params
    assert params["importStrategy"] == "CREATE"
    assert params["async"] == "false"
    assert "importMode" not in params


@respx.mock
async def test_a_linked_registration_reads_back_as_an_enrollment_only_import(
    linked_forward_project: Path,
) -> None:
    """An operator reading the report can tell a linked import from a create without opening the receipt."""
    _mock_tracker_instance()

    report = await _forward(linked_forward_project, import_responses=True)

    targets = {outcome.response_id: outcome.target_kind for outcome in report.outcomes}
    assert targets["En1aaaaaaaa"] == "tracker-enrollment"
    assert targets["A03MvHHogjR-example-1"] == "tracker-event"


@respx.mock
async def test_a_rejected_enrollment_only_import_names_its_payload_kind_in_the_sidecar(
    linked_forward_project: Path,
) -> None:
    """The sidecar beside a rejected receipt says which tracker shape DHIS2 turned down."""
    _mock_tracker_instance()
    respx.post(f"{_BASE_URL}/api/tracker").mock(return_value=_rejected_tracker())

    report = await _forward(linked_forward_project, import_responses=True)

    sidecar = linked_forward_project / REJECTED_RESPONSES_RELATIVE_PATH / f"En1aaaaaaaa{IMPORT_REPORT_SUFFIX}"
    written = json.loads(sidecar.read_text(encoding="utf-8"))
    assert written["target_kind"] == "tracker-enrollment"
    assert written["issues"]
    assert len(report.rejected) == 2


@respx.mock
async def test_the_report_reads_back_in_spool_order_whatever_the_posting_order_was(
    tracker_forward_project: Path,
) -> None:
    """Two orders, deliberately separate: the report is the spool it drained, the posting order is the run's."""
    _mock_tracker_instance()

    report = await _forward(tracker_forward_project, import_responses=True)

    assert [outcome.response_id for outcome in report.outcomes] == ["A03MvHHogjR-example-1", "En1aaaaaaaa"]


def test_one_receipt_always_names_the_same_event_uid() -> None:
    """A receipt-derived identity is a pure function of the receipt, so two translations agree on it."""
    assert receipt_event_uid("A03MvHHogjR-example-1") == receipt_event_uid("A03MvHHogjR-example-1")


def test_two_receipts_name_two_events() -> None:
    """Two visits captured against one form are two events, so their derived UIDs must not collide."""
    assert receipt_event_uid("A03MvHHogjR-example-1") != receipt_event_uid("A03MvHHogjR-example-2")


def test_a_derived_event_uid_is_shaped_the_way_dhis2_reads_one() -> None:
    """One ASCII letter and ten alphanumeric places, which is the only check a reader can make offline."""
    assert is_dhis2_uid(receipt_event_uid("A03MvHHogjR-example-1"))
    assert is_dhis2_uid(receipt_event_uid("En1aaaaaaaa"))


@respx.mock
async def test_a_posted_event_carries_the_uid_its_receipt_derives(forward_project: Path) -> None:
    """The client names the event, so the import report DHIS2 answers with is about a UID the run already knows."""
    routes = _mock_instance()

    report = await _forward(forward_project, import_responses=True)

    posted = json.loads(routes["tracker"].calls.last.request.content)["events"][0]
    event_outcomes = [outcome for outcome in report.outcomes if outcome.target_kind is not None]
    event_receipt = next(outcome.response_id for outcome in event_outcomes if outcome.target_kind.value == "event")
    assert posted["event"] == receipt_event_uid(event_receipt)


@respx.mock
async def test_a_dry_run_and_the_import_behind_it_name_the_same_event(forward_project: Path) -> None:
    """Dry-run diagnostics are readable against the objects the import creates because both name one UID."""
    dry_routes = _mock_instance()
    await _forward(forward_project)
    validated = json.loads(dry_routes["tracker"].calls.last.request.content)["events"][0]["event"]

    respx.reset()
    import_routes = _mock_instance()
    await _forward(forward_project, import_responses=True)
    imported = json.loads(import_routes["tracker"].calls.last.request.content)["events"][0]["event"]

    assert validated == imported


@respx.mock
async def test_forwarding_one_receipt_twice_asks_dhis2_to_create_the_same_event_twice(
    forward_project: Path,
) -> None:
    """A re-forward is a `CREATE` against a UID the instance already holds - a refusal, not a second visit."""
    routes = _mock_instance()

    await _forward(forward_project, import_responses=True)
    first = json.loads(routes["tracker"].calls.last.request.content)["events"][0]["event"]

    _fill_spool(forward_project, _documents(GenerateConfig()))
    await _forward(forward_project, import_responses=True)
    second = json.loads(routes["tracker"].calls.last.request.content)["events"][0]["event"]

    assert first == second
    assert dict(routes["tracker"].calls.last.request.url.params)["importStrategy"] == "CREATE"


@respx.mock
async def test_a_completed_report_is_registered_complete_for_the_tuple_its_values_landed_under(
    forward_project: Path,
) -> None:
    """The second write names the same four keys the data value set did, and claims the day authored."""
    routes = _mock_instance()
    report = await _forward(forward_project, import_responses=True)

    values = json.loads(routes["aggregate"].calls.last.request.content)
    registration = json.loads(routes["completeness"].calls.last.request.content)["completeDataSetRegistrations"][0]
    assert registration["dataSet"] == values["dataSet"]
    assert registration["period"] == values["period"]
    assert registration["organisationUnit"] == values["orgUnit"]
    assert registration["completed"] is True
    assert dict(routes["completeness"].calls.last.request.url.params) == {}
    assert "storedBy" not in registration

    outcomes = report.completeness_of(ForwardCompletenessKind.REGISTERED)
    assert len(outcomes) == 1
    assert outcomes[0].data_set == values["dataSet"]
    assert outcomes[0].period == values["period"]


@respx.mock
async def test_the_registration_claims_the_day_the_response_records_itself_authored(
    forward_project: Path,
) -> None:
    """`authored` is the only statement of when the report was finished a receipt carries."""
    _stamp_aggregate_receipts_authored(forward_project, "2026-02-03T08:00:00")
    routes = _mock_instance()
    await _forward(forward_project, import_responses=True)
    registration = json.loads(routes["completeness"].calls.last.request.content)["completeDataSetRegistrations"][0]
    assert registration["date"] == "2026-02-03"


@respx.mock
async def test_the_data_value_set_never_carries_a_complete_date(forward_project: Path) -> None:
    """`completeDate` registers completeness before DHIS2 has taken anything (BUGS.md 76, 77), so it is unsent."""
    routes = _mock_instance()
    await _forward(forward_project, import_responses=True)
    assert "completeDate" not in json.loads(routes["aggregate"].calls.last.request.content)


@respx.mock
async def test_completeness_is_registered_only_after_the_values_are_in(forward_project: Path) -> None:
    """A claim about data DHIS2 refused would be a lie, so a rejected import registers nothing."""
    routes = _mock_instance(aggregate_response=_rejected_aggregate())
    report = await _forward(forward_project, import_responses=True)

    assert routes["aggregate"].call_count == 1
    assert routes["completeness"].call_count == 0
    assert report.completeness_of(ForwardCompletenessKind.REGISTERED) == ()


@respx.mock
async def test_an_in_progress_report_imports_its_values_and_registers_nothing(forward_project: Path) -> None:
    """`in-progress` is the reporter saying they are not finished, and nothing may claim otherwise."""
    _mock_in_progress_spool(forward_project)
    routes = _mock_instance()
    report = await _forward(forward_project, import_responses=True)

    assert routes["aggregate"].call_count == 1
    assert routes["completeness"].call_count == 0
    assert len(report.completeness_of(ForwardCompletenessKind.NOT_CLAIMED)) == 1


@respx.mock
async def test_a_dry_run_states_what_it_would_register_and_posts_nothing(forward_project: Path) -> None:
    """A dry run wrote no values, so there is nothing for a completeness claim to be about."""
    routes = _mock_instance()
    report = await _forward(forward_project)

    assert routes["completeness"].call_count == 0
    would = report.completeness_of(ForwardCompletenessKind.WOULD_REGISTER)
    assert len(would) == 1
    assert would[0].data_set
    assert would[0].period
    assert report.completeness_dry_run_reason


@respx.mock
async def test_a_refused_registration_leaves_the_values_imported(forward_project: Path) -> None:
    """The values landed and stay landed; only the claim failed, and the run still counts the response accepted."""
    routes = _mock_instance(completeness_response=_refused_completeness())
    report = await _forward(forward_project, import_responses=True)

    assert routes["completeness"].call_count == 1
    aggregate = next(
        outcome for outcome in report.outcomes if outcome.target_kind == ConversionTargetKind.DATA_VALUE_SET
    )
    assert aggregate.kind == ForwardOutcomeKind.ACCEPTED
    assert aggregate.spool_path.startswith(FORWARDED_RESPONSES_RELATIVE_PATH)
    refused = report.completeness_of(ForwardCompletenessKind.REFUSED)
    assert len(refused) == 1
    assert "Data set not found or not accessible" in refused[0].reason


@respx.mock
async def test_the_registration_can_be_turned_off_for_a_whole_run(forward_project: Path) -> None:
    """`--no-register-completeness` imports the values and states that nothing was registered."""
    routes = _mock_instance()
    report = await _forward(forward_project, import_responses=True, register_completeness=False)

    assert routes["aggregate"].call_count == 1
    assert routes["completeness"].call_count == 0
    assert len(report.completeness_of(ForwardCompletenessKind.NOT_REGISTERED)) == 1


def _mock_in_progress_spool(root: Path) -> None:
    """Re-spool the fixture's aggregate response as one the reporter has not finished."""
    _rewrite_aggregate_receipts(root, "status", "in-progress")


def _stamp_aggregate_receipts_authored(root: Path, authored: str) -> None:
    """Give the fixture's aggregate response an `authored` instant, which is the day it claims complete."""
    _rewrite_aggregate_receipts(root, "authored", authored)


def _rewrite_aggregate_receipts(root: Path, field: str, value: str) -> None:
    """Set one field on every spooled aggregate receipt, so a test can state what the response said."""
    for path in (root / RECEIVED_RESPONSES_RELATIVE_PATH).glob("*.json"):
        envelope = json.loads(path.read_text(encoding="utf-8"))
        if envelope["form_kind"] != "aggregate":
            continue
        envelope["response"][field] = value
        path.write_text(json.dumps(envelope, indent=2), encoding="utf-8")


def _mock_tracker_instance_answering_the_stage_event(event_response: httpx.Response) -> respx.Route:
    """Mock a tracker drain whose registration DHIS2 takes and whose stage event it answers `event_response`."""
    tracker = _mock_tracker_instance()

    def _answer(request: httpx.Request) -> httpx.Response:
        return _accepted_tracker() if b'"trackedEntities"' in request.content else event_response

    tracker.mock(side_effect=_answer)
    return tracker


def _drop_the_registration_receipt(root: Path) -> None:
    """Leave the stage event alone in the spool, so the enrollment it names is one no receipt here mints."""
    (root / RECEIVED_RESPONSES_RELATIVE_PATH / "En1aaaaaaaa.json").unlink()


@respx.mock
async def test_a_dry_run_cannot_check_a_stage_event_against_an_enrollment_the_same_run_would_create(
    tracker_forward_project: Path,
) -> None:
    """The pair DHIS2 answers here is the dry run's own doing, so the event is unverifiable and not rejected."""
    _mock_tracker_instance_answering_the_stage_event(_harvested_absent_enrollment_409("v42"))

    report = await _forward(tracker_forward_project)

    assert report.rejected == ()
    assert len(report.unverifiable) == 1
    assert report.unverifiable[0].response_id == "A03MvHHogjR-example-1"
    assert report.unverifiable[0].kind == ForwardOutcomeKind.UNVERIFIABLE
    assert len(report.accepted) == 1
    assert report.posted_count == 2
    assert "2 posted (validate only)" in report.counts_line
    assert report.counts_line.endswith("0 rejected, 1 unverifiable")


@respx.mock
async def test_the_unverifiable_section_says_what_a_dry_run_cannot_check_without_naming_an_error_code(
    tracker_forward_project: Path,
) -> None:
    """A reader acts on this without knowing what `E1079` and `E1313` are, which is the whole point of it."""
    _mock_tracker_instance_answering_the_stage_event(_harvested_absent_enrollment_409("v42"))

    report = await _forward(tracker_forward_project)

    assert len(report.unverifiable_reasons) == 1
    reason = report.unverifiable_reasons[0]
    assert reason.responses == 1
    assert "created by a registration validated in the same run" in reason.reason
    assert "A dry run writes nothing to the instance" in reason.reason
    assert "E1079" not in reason.reason
    assert "E1313" not in reason.reason


@respx.mock
async def test_a_dry_run_stage_event_naming_an_enrollment_no_registration_of_the_run_mints_stays_rejected(
    tracker_forward_project: Path,
) -> None:
    """The orphan is the case that has to keep failing loudly - nothing in this run would ever create it."""
    _drop_the_registration_receipt(tracker_forward_project)
    _mock_tracker_instance_answering_the_stage_event(_harvested_absent_enrollment_409("v42"))

    report = await _forward(tracker_forward_project)

    assert report.unverifiable == ()
    assert len(report.rejected) == 1
    assert report.rejected[0].response_id == "A03MvHHogjR-example-1"
    assert [issue.error_code for issue in report.rejected[0].import_outcome.issues] == ["E1313", "E1079"]


@respx.mock
async def test_a_dry_run_rejection_outside_the_absent_enrollment_pair_stays_rejected(
    tracker_forward_project: Path,
) -> None:
    """A stage event of this run's own registration is still rejected for anything else DHIS2 names."""
    _mock_tracker_instance_answering_the_stage_event(_rejected_tracker())

    report = await _forward(tracker_forward_project)

    assert report.unverifiable == ()
    assert len(report.rejected) == 1
    assert [issue.error_code for issue in report.rejected[0].import_outcome.issues] == ["E1029"]


@respx.mock
async def test_an_import_run_reads_the_same_pair_as_a_rejection_and_files_it_as_one(
    tracker_forward_project: Path,
) -> None:
    """An import creates what it posts, so nothing it refuses went unchecked and nothing is reclassified."""
    _mock_tracker_instance_answering_the_stage_event(_harvested_absent_enrollment_409("v42"))

    report = await _forward(tracker_forward_project, import_responses=True)

    assert report.unverifiable == ()
    assert report.unverifiable_reasons == ()
    assert "dry run" not in report.counts_line
    assert "validate only" not in report.counts_line
    assert "unverifiable" not in report.counts_line
    assert len(report.rejected) == 1
    assert report.rejected[0].spool_path.startswith(REJECTED_RESPONSES_RELATIVE_PATH)
    assert (tracker_forward_project / REJECTED_RESPONSES_RELATIVE_PATH / "A03MvHHogjR-example-1.json").is_file()


@respx.mock
async def test_the_report_round_trips_the_unverifiable_outcome_through_json(
    tracker_forward_project: Path,
) -> None:
    """The kind is a field of the receipt, so a dumped report rebuilds the count and the section from it."""
    _mock_tracker_instance_answering_the_stage_event(_harvested_absent_enrollment_409("v42"))

    report = await _forward(tracker_forward_project)
    restored = service.ForwardReport.model_validate_json(report.model_dump_json())

    assert [outcome.kind for outcome in restored.outcomes] == [outcome.kind for outcome in report.outcomes]
    assert len(restored.unverifiable) == 1
    assert restored.unverifiable_reasons == report.unverifiable_reasons
    assert restored.counts_line == report.counts_line


@respx.mock
def test_a_dry_run_whose_only_failures_are_unverifiable_exits_zero(
    tracker_forward_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A dry run proved everything a dry run can prove, so it is a success and says what it could not check."""
    from dhis2w_cli.main import build_app
    from typer.testing import CliRunner

    monkeypatch.setenv("COLUMNS", "300")
    _mock_tracker_instance_answering_the_stage_event(_harvested_absent_enrollment_409("v42"))

    result = CliRunner().invoke(build_app(), ["fhir", "forward", str(tracker_forward_project), "--no-progress"])

    assert result.exit_code == 0, result.output
    assert "unverifiable" in result.output
    assert "DRY RUN (validate only)" in result.output
    assert "created by a registration validated in the same run" in result.output


@respx.mock
def test_a_dry_run_holding_an_orphan_stage_event_exits_one(tracker_forward_project: Path) -> None:
    """A rejection nothing in the run explains is a failure whatever the mode, and the exit code says so."""
    from dhis2w_cli.main import build_app
    from typer.testing import CliRunner

    _drop_the_registration_receipt(tracker_forward_project)
    _mock_tracker_instance_answering_the_stage_event(_harvested_absent_enrollment_409("v42"))

    result = CliRunner().invoke(build_app(), ["fhir", "forward", str(tracker_forward_project), "--no-progress"])

    assert result.exit_code == 1, result.output
    assert "1 response(s) rejected by DHIS2" in result.output


@respx.mock
async def test_every_majors_wrapped_data_value_set_409_reaches_the_outcome_whole(
    forward_project: Path, wire_version: str
) -> None:
    """The `WebMessage` is unwrapped and its `ImportSummary` read on all three majors, counts and conflict intact.

    The degrade this guards is silent: a summary the generated model cannot read leaves
    `data_value_summary` at None, and the rejection is then a status with no code, no count and no
    conflict - a run that says nothing about why two hundred responses were refused.
    """
    _mock_instance(wire_version=wire_version, aggregate_response=_harvested_aggregate_value_type_409(wire_version))
    facts = _AGGREGATE_VALUE_TYPE_FACTS[wire_version]

    report = await _forward(forward_project)

    outcome = next(outcome for outcome in report.rejected if outcome.target_kind == "data-value-set").import_outcome
    assert outcome is not None
    assert outcome.data_value_summary is not None
    assert outcome.status == facts.status
    assert (outcome.created, outcome.updated, outcome.ignored, outcome.deleted) == (0, 0, 1, 0)
    assert outcome.data_value_summary.importCount is not None
    assert outcome.data_value_summary.importCount.ignored == 1
    assert outcome.data_value_summary.conflicts is not None
    assert len(outcome.data_value_summary.conflicts) == 1
    assert [issue.error_code for issue in outcome.issues] == [facts.error_code]
    assert outcome.issues[0].subject == facts.subject
    assert outcome.issues[0].message == facts.message


@respx.mock
async def test_a_data_value_set_409_is_a_rejection_on_every_major_whatever_status_it_carries(
    forward_project: Path, wire_version: str
) -> None:
    """2.41 and 2.42 call the refused value a warning and 2.43 an error, and all three refused it.

    Reading the rejection off the status alone would take the 2.41 and 2.42 answers for successes, so
    what makes it a rejection is DHIS2 having named a conflict against the payload at all.
    """
    _mock_instance(wire_version=wire_version, aggregate_response=_harvested_aggregate_value_type_409(wire_version))

    report = await _forward(forward_project)

    outcome = next(outcome for outcome in report.rejected if outcome.target_kind == "data-value-set").import_outcome
    assert outcome is not None
    assert outcome.is_rejected is True
    assert len(report.accepted) == 1


@respx.mock
async def test_every_majors_bare_tracker_409_parses_with_its_codes_and_uids_intact(
    forward_project: Path, wire_version: str
) -> None:
    """No major wraps the tracker report, so each one is recognised by its own shape and read whole."""
    _mock_instance(wire_version=wire_version, tracker_response=_harvested_tracker_value_type_409(wire_version))
    facts = _TRACKER_VALUE_TYPE_FACTS[wire_version]

    report = await _forward(forward_project)

    outcome = next(outcome for outcome in report.rejected if outcome.target_kind == "event").import_outcome
    assert outcome is not None
    assert outcome.tracker_report is not None
    assert outcome.tracker_report.validationReport is not None
    assert outcome.status == "ERROR"
    assert (outcome.created, outcome.updated, outcome.ignored, outcome.deleted) == (0, 0, 1, 0)
    assert [issue.error_code for issue in outcome.issues] == list(facts.error_codes)
    assert [issue.subject for issue in outcome.issues] == [facts.subject]
    assert [issue.message for issue in outcome.issues] == list(facts.messages)


@respx.mock
async def test_every_majors_absent_enrollment_409_carries_both_codes_of_the_pair(
    forward_project: Path, wire_version: str
) -> None:
    """`E1313` and `E1079` arrive together on all three majors, in the order the instance listed them."""
    _mock_instance(wire_version=wire_version, tracker_response=_harvested_absent_enrollment_409(wire_version))
    facts = _ABSENT_ENROLLMENT_FACTS[wire_version]

    report = await _forward(forward_project)

    outcome = next(outcome for outcome in report.rejected if outcome.target_kind == "event").import_outcome
    assert outcome is not None
    assert outcome.tracker_report is not None
    assert [issue.error_code for issue in outcome.issues] == list(facts.error_codes)
    assert [issue.subject for issue in outcome.issues] == [facts.subject, facts.subject]
    assert [issue.message for issue in outcome.issues] == list(facts.messages)
    assert outcome.ignored == 1


@respx.mock
async def test_the_harvested_rejections_roll_up_under_the_codes_each_major_named(
    forward_project: Path, wire_version: str
) -> None:
    """Two endpoints refuse one response each, and the run reads as one row per rule on every major."""
    _mock_instance(
        wire_version=wire_version,
        aggregate_response=_harvested_aggregate_value_type_409(wire_version),
        tracker_response=_harvested_tracker_value_type_409(wire_version),
    )
    aggregate_code = _AGGREGATE_VALUE_TYPE_FACTS[wire_version].error_code

    report = await _forward(forward_project)

    assert len(report.rejected) == 2
    reasons = {reason.error_code: reason for reason in report.rejection_reasons}
    assert set(reasons) == {aggregate_code, "E1302"}
    assert reasons[aggregate_code].responses == 1
    assert reasons["E1302"].responses == 1
    # 2.41 leaves the identifier empty and 2.42 and 2.43 put the value type there, and generalising the
    # quoted parts away folds both into one sentence - which is what one row per rule has to survive.
    assert reasons["E1302"].reason.startswith("DataElement `...` is not valid:")


def test_the_majors_word_one_tracker_rule_three_ways_and_only_its_code_holds_still() -> None:
    """BUGS.md 68's drift, pinned against the wire: the sentences differ, the codes do not.

    Rolling rejections up on the sentence would report one rule as two causes of a run that met two
    majors, which is the reason `rejection_reasons` keys on the code and never on the prose.
    """
    codes = {version: facts.error_codes for version, facts in _ABSENT_ENROLLMENT_FACTS.items()}
    assert set(codes.values()) == {("E1313", "E1079")}

    absent_tracked_entity = {version: facts.messages[0] for version, facts in _ABSENT_ENROLLMENT_FACTS.items()}
    assert absent_tracked_entity["v41"] != absent_tracked_entity["v42"]
    assert absent_tracked_entity["v42"] == absent_tracked_entity["v43"]

    program_mismatch = {version: facts.messages[1] for version, facts in _ABSENT_ENROLLMENT_FACTS.items()}
    assert program_mismatch["v41"] == program_mismatch["v42"]
    assert program_mismatch["v42"] != program_mismatch["v43"]


def test_each_stored_409_body_names_the_instance_it_was_harvested_off(wire_version: str) -> None:
    """A fixture whose provenance nobody can check is a fixture somebody will one day invent."""
    assert _HARVESTED_INSTANCE_VERSIONS[wire_version].startswith(f"2.{wire_version[1:]}.")
    assert len(_HARVESTED_INSTANCE_REVISIONS[wire_version]) == 7
    for name in ("data-value-set-value-type", "tracker-absent-enrollment", "tracker-value-type"):
        assert (_HARVESTED_409_DIRECTORY / f"{name}-{wire_version}.json").is_file()


# --- Spool hardening: the lock, filing as the drain goes, quarantine, sweeping, and requeue. ---


@respx.mock
async def test_each_receipt_is_filed_before_the_next_one_is_posted(three_event_project: Path) -> None:
    """The disk agrees with DHIS2 at every point of the loop, not only once the loop has ended.

    Asserted from inside the mock: when the second POST arrives, the first receipt is already in
    `forwarded/` with its report beside it. That is the property a killed drain depends on - what was
    posted is filed, and what was not is untouched.
    """
    filed_when_the_second_post_arrived: list[list[str]] = []

    def _answer(request: httpx.Request) -> httpx.Response:
        forwarded = three_event_project / FORWARDED_RESPONSES_RELATIVE_PATH
        filed_when_the_second_post_arrived.append(sorted(path.name for path in forwarded.glob("*")))
        return _accepted_tracker()

    respx.get(f"{_BASE_URL}/api/system/info").mock(
        return_value=httpx.Response(200, json={"version": _HARVESTED_INSTANCE_VERSIONS["v42"]})
    )
    respx.get(f"{_BASE_URL}/api/dataElements").mock(
        return_value=httpx.Response(
            200, json={"dataElements": [{"id": uid, "valueType": value} for uid, value in _VALUE_TYPES.items()]}
        )
    )
    respx.post(f"{_BASE_URL}/api/tracker").mock(side_effect=_answer)

    report = await _forward(three_event_project, import_responses=True)

    ordered = sorted(outcome.response_id for outcome in report.outcomes)
    # Nothing was filed when the first payload was posted, and the first was filed with its report by
    # the time the second was.
    assert filed_when_the_second_post_arrived[0] == []
    assert filed_when_the_second_post_arrived[1] == [f"{ordered[0]}.json", f"{ordered[0]}{IMPORT_REPORT_SUFFIX}"]
    assert len(filed_when_the_second_post_arrived[2]) == 4


@respx.mock
async def test_a_dry_run_files_nothing_as_it_goes(three_event_project: Path) -> None:
    """Filing as the drain goes is a property of an import; a dry run wrote nothing to be filing about."""
    _mock_instance()

    await _forward(three_event_project)

    assert len(list((three_event_project / RECEIVED_RESPONSES_RELATIVE_PATH).glob("*.json"))) == 3
    assert not (three_event_project / FORWARDED_RESPONSES_RELATIVE_PATH).exists()


@respx.mock
async def test_a_receipt_whose_file_vanished_mid_drain_is_graded_rather_than_fatal(
    three_event_project: Path,
) -> None:
    """A rename that lost a race must not throw away DHIS2's answer or the receipts queued behind it."""
    received = three_event_project / RECEIVED_RESPONSES_RELATIVE_PATH
    posts = 0

    def _answer(request: httpx.Request) -> httpx.Response:
        nonlocal posts
        posts += 1
        if posts == 1:
            # Something else moves the receipt out from under the drain between the post and the file.
            for path in sorted(received.glob("*.json")):
                path.unlink()
                break
        return _accepted_tracker()

    respx.get(f"{_BASE_URL}/api/system/info").mock(
        return_value=httpx.Response(200, json={"version": _HARVESTED_INSTANCE_VERSIONS["v42"]})
    )
    respx.get(f"{_BASE_URL}/api/dataElements").mock(
        return_value=httpx.Response(
            200, json={"dataElements": [{"id": uid, "valueType": value} for uid, value in _VALUE_TYPES.items()]}
        )
    )
    respx.post(f"{_BASE_URL}/api/tracker").mock(side_effect=_answer)

    report = await _forward(three_event_project, import_responses=True)

    assert len(report.accepted) == 3
    assert len(report.filing_issues) == 1
    assert "was gone when the drain went to file it" in report.filing_issues[0].reason


@respx.mock
async def test_a_second_drain_is_refused_while_another_holds_the_lock(forward_project: Path) -> None:
    """Two drains over one spool would post every payload twice, so the second one fails at once."""
    _mock_instance()
    lock_path = forward_project / SPOOL_RELATIVE_PATH / DRAIN_LOCK_FILE_NAME
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o644)
    os.write(descriptor, b"424242\n")
    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        with pytest.raises(SpoolLockedError, match="process 424242"):
            await _forward(forward_project, import_responses=True)
    finally:
        os.close(descriptor)

    # Nothing was posted and nothing moved: the refusal is the whole of what the second run did.
    assert len(list((forward_project / RECEIVED_RESPONSES_RELATIVE_PATH).glob("*.json"))) == 2


@respx.mock
async def test_the_lock_is_released_however_the_drain_ends(forward_project: Path) -> None:
    """A drain that raised still leaves the spool drainable, or one bad run would wedge the project."""
    respx.get(f"{_BASE_URL}/api/system/info").mock(side_effect=httpx.ConnectError("connection refused"))
    with pytest.raises(httpx.ConnectError):
        await _forward(forward_project)

    _mock_instance()
    report = await _forward(forward_project)

    assert report.spooled == 2


@respx.mock
async def test_an_orphan_temporary_file_is_swept_at_drain_start_and_a_young_one_is_left(
    forward_project: Path,
) -> None:
    """An abandoned write is deleted; one young enough to still be in flight is left exactly alone."""
    _mock_instance()
    received = forward_project / RECEIVED_RESPONSES_RELATIVE_PATH
    abandoned = received / ".abandoned.json.tmp"
    abandoned.write_text("half a receipt", encoding="utf-8")
    in_flight = received / ".in-flight.json.tmp"
    in_flight.write_text("half a receipt", encoding="utf-8")
    stale = time.time() - 2 * ORPHAN_TEMPORARY_FILE_AGE_SECONDS
    os.utime(abandoned, (stale, stale))

    await _forward(forward_project)

    assert not abandoned.exists()
    assert in_flight.is_file()


@respx.mock
async def test_an_entered_in_error_receipt_is_filed_once_and_is_gone_from_the_next_drain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The one refusal nothing can fix is filed rather than retried by every drain for ever.

    Withdrawal is a deletion and this toolchain imports (docs/fhir/design/data-lifecycle.md), so no
    change to the guide and no change to the instance would make this receipt convert. It is filed to
    `rejected/` with a sidecar naming the doctrine, and the next drain never sees it again.
    """
    _write_probe_profile(tmp_path, monkeypatch)
    root = tmp_path / "project"
    root.mkdir()
    _write_project(root)
    withdrawn = _event_documents(1)[0].model_copy(update={"status": "entered-in-error"})
    _fill_spool(root, [withdrawn])
    monkeypatch.chdir(root)
    _mock_instance()

    first = await _forward(root, import_responses=True)

    assert [outcome.kind for outcome in first.outcomes] == [ForwardOutcomeKind.REFUSED]
    assert first.refused[0].refusals[0].category == "entered-in-error-is-a-deletion"
    assert first.refused[0].spool_path == f"{REJECTED_RESPONSES_RELATIVE_PATH}/{withdrawn.id}.json"
    sidecar = root / REJECTED_RESPONSES_RELATIVE_PATH / f"{withdrawn.id}{IMPORT_REPORT_SUFFIX}"
    assert "Withdrawing a submission is unbuilt" in sidecar.read_text(encoding="utf-8")

    second = await _forward(root, import_responses=True)

    assert second.spooled == 0


@respx.mock
async def test_every_other_refusal_still_stays_in_the_queue(forward_project: Path) -> None:
    """A refusal with a fix in the guide or in the data is retried by the next drain, as it always was."""
    _mock_instance()
    orphan = forward_project / RECEIVED_RESPONSES_RELATIVE_PATH / "orphan.json"
    orphan.write_text(
        json.dumps(
            {
                "response_id": "orphan",
                "received_at": "2026-08-08T09:00:00Z",
                "form_kind": "aggregate",
                "questionnaire": f"{_CANONICAL}/Questionnaire/nothing-published",
                "response": {
                    "resourceType": "QuestionnaireResponse",
                    "id": "orphan",
                    "questionnaire": f"{_CANONICAL}/Questionnaire/nothing-published",
                    "status": "completed",
                },
            }
        ),
        encoding="utf-8",
    )

    await _forward(forward_project, import_responses=True)

    assert orphan.is_file()


@respx.mock
async def test_a_requeued_receipt_is_posted_again_by_the_next_drain(three_event_project: Path) -> None:
    """The round trip: DHIS2 refuses a payload, an operator requeues it, and the next drain posts it."""
    respx.get(f"{_BASE_URL}/api/system/info").mock(
        return_value=httpx.Response(200, json={"version": _HARVESTED_INSTANCE_VERSIONS["v42"]})
    )
    respx.get(f"{_BASE_URL}/api/dataElements").mock(
        return_value=httpx.Response(
            200, json={"dataElements": [{"id": uid, "valueType": value} for uid, value in _VALUE_TYPES.items()]}
        )
    )
    respx.post(f"{_BASE_URL}/api/tracker").mock(return_value=_rejected_tracker())
    first = await _forward(three_event_project, import_responses=True)
    refused = sorted(outcome.response_id for outcome in first.rejected)
    assert len(refused) == 3

    project = load_project(three_event_project)
    requeued = service.requeue_rejected_responses(project, [refused[0]])

    assert [receipt.response_id for receipt in requeued.requeued] == [refused[0]]
    assert requeued.requeued[0].spool_path == f"{RECEIVED_RESPONSES_RELATIVE_PATH}/{refused[0]}.json"
    # The report stays behind in rejected/ as the record of what DHIS2 last answered about the payload.
    assert (three_event_project / REJECTED_RESPONSES_RELATIVE_PATH / f"{refused[0]}{IMPORT_REPORT_SUFFIX}").is_file()

    respx.post(f"{_BASE_URL}/api/tracker").mock(return_value=_accepted_tracker())
    second = await _forward(three_event_project, import_responses=True)

    assert [outcome.response_id for outcome in second.accepted] == [refused[0]]
    assert (three_event_project / FORWARDED_RESPONSES_RELATIVE_PATH / f"{refused[0]}.json").is_file()


@respx.mock
async def test_requeue_all_moves_every_refused_receipt(three_event_project: Path) -> None:
    """`--all-rejected` is the same move over everything DHIS2 refused, which is the usual case."""
    _mock_instance(tracker_response=_rejected_tracker())
    await _forward(three_event_project, import_responses=True)
    project = load_project(three_event_project)

    report = service.requeue_rejected_responses(project, all_rejected=True)

    assert len(report.requeued) == 3
    assert len(list((three_event_project / RECEIVED_RESPONSES_RELATIVE_PATH).glob("*.json"))) == 3
    assert list((three_event_project / REJECTED_RESPONSES_RELATIVE_PATH).glob("*[!t].json")) == []


def test_requeueing_an_id_that_is_not_rejected_refuses_before_anything_moves(forward_project: Path) -> None:
    """A command that reported success for a receipt it never found would be worse than a refusal."""
    project = load_project(forward_project)

    with pytest.raises(SpoolReadError, match="`nothing-here`"):
        service.requeue_rejected_responses(project, ["nothing-here"])


@respx.mock
async def test_the_spool_listing_reads_the_directory_and_nothing_else(three_event_project: Path) -> None:
    """`d2w fhir spool` answers while the instance is down, because every fact in it is on disk."""
    _mock_instance(tracker_response=_rejected_tracker())
    await _forward(three_event_project, import_responses=True)
    (three_event_project / RECEIVED_RESPONSES_RELATIVE_PATH / "broken.json").write_text("{not json", encoding="utf-8")

    report = service.read_spool_state(load_project(three_event_project))

    assert report.counts.rejected == 3
    assert report.counts.received == 0
    assert report.counts.malformed == 1
    assert [entry.file_name for entry in report.quarantined] == ["broken.json"]
    assert {row.state for row in report.receipts} == {SpoolState.REJECTED}
    # A rejected row states the short reason off the report the forwarder left beside it.
    assert all(row.reason for row in report.receipts)


#: The organisation unit a re-capture is moved to, so the cell it names is a different cell entirely.
_OTHER_ORG_UNIT = "DiszpKrYNg8"


def _aggregate_document() -> QuestionnaireResponse:
    """The published aggregate example response - the one receipt of the fixture that carries cells."""
    return next(document for document in _documents(GenerateConfig()) if _form_kind(document) == "aggregate")


def _recaptured(
    document: QuestionnaireResponse,
    response_id: str,
    *,
    period: str | None = None,
    organisation_unit: str | None = None,
    attribute_option_combo: str | None = None,
    keep_link_ids: set[str] | None = None,
) -> QuestionnaireResponse:
    """A second capture of one aggregate response, optionally moved off one of the keys naming its cells.

    A re-capture is a fresh submission of the same form, so it is the same document under a new
    receipt id - which is exactly what a person filling the form in again produces.
    """
    raw: dict[str, Any] = json.loads(document.model_dump_json(exclude_none=True, by_alias=True))
    raw["id"] = response_id
    for extension in raw["extension"]:
        for part in extension.get("extension", []):
            if part["url"] == "iso" and period is not None:
                part["valueString"] = period
        if attribute_option_combo is not None and extension["url"].endswith("d2-attribute-option-combo"):
            extension["valueCoding"]["code"] = attribute_option_combo
    if organisation_unit is not None:
        raw["subject"]["reference"] = f"Location/{organisation_unit}"
    if keep_link_ids is not None:
        for section in raw["item"]:
            section["item"] = [item for item in section["item"] if item["linkId"] in keep_link_ids]
    return QuestionnaireResponse.model_validate(raw)


def _publish_location(root: Path, organisation_unit: str) -> None:
    """Publish one more Location, so a re-capture can name an organisation unit the guide resolves."""
    naming = ConversionNaming.from_config(GenerateConfig(), _CANONICAL)
    _write_resource(
        root / "ig" / "input" / "resources" / f"Location-{organisation_unit}.json",
        Location(
            id=organisation_unit,
            identifier=[Identifier(system=naming.organisation_unit_system, value=organisation_unit)],
        ),
    )


def _sent_values(report: Any) -> set[tuple[str, str | None, str | None, str | None, str | None]]:
    """Every value one run reported as already sent, as the five keys that name each of them."""
    return {
        (
            value.cell.data_element,
            value.cell.category_option_combo,
            value.cell.period,
            value.cell.organisation_unit,
            value.cell.attribute_option_combo,
        )
        for overwrite in report.overwrites
        for value in overwrite.values
    }


@respx.mock
async def test_a_forwarded_receipt_records_the_values_its_payload_landed(forward_project: Path) -> None:
    """The sidecar is what makes `forwarded/` answerable later, so it names the cells and the arrival."""
    _mock_instance()
    report = await _forward(forward_project, import_responses=True)
    aggregate = next(outcome for outcome in report.accepted if outcome.target_kind == "data-value-set")

    sidecar = forward_project / FORWARDED_RESPONSES_RELATIVE_PATH / f"{aggregate.response_id}{IMPORT_REPORT_SUFFIX}"
    written = json.loads(sidecar.read_text(encoding="utf-8"))

    assert written["received_at"] == _RECEIVED_AT
    assert {cell["data_element"] for cell in written["cells"]} == {"De2aaaaaaaa", "De3aaaaaaaa"}
    assert {cell["period"] for cell in written["cells"]} == {"202607"}
    assert {cell["organisation_unit"] for cell in written["cells"]} == {_ROOT_ORG_UNIT}
    # A tracker payload lands on no cell, so its sidecar records none.
    event = next(outcome for outcome in report.accepted if outcome.target_kind == "event")
    event_sidecar = forward_project / FORWARDED_RESPONSES_RELATIVE_PATH / f"{event.response_id}{IMPORT_REPORT_SUFFIX}"
    assert json.loads(event_sidecar.read_text(encoding="utf-8"))["cells"] == []


@respx.mock
async def test_a_second_capture_of_one_value_names_the_receipt_that_sent_it_first(forward_project: Path) -> None:
    """DHIS2 replaces the value and says nothing about it, so the run names the value and the sender."""
    _mock_instance()
    first = await _forward(forward_project, import_responses=True)
    assert first.overwrites == ()
    original = _aggregate_document()
    _write_receipt(forward_project, _recaptured(original, "recapture1"), received_at="2026-08-09T10:00:00Z")

    report = await _forward(forward_project, import_responses=True)

    assert [overwrite.response_id for overwrite in report.overwrites] == ["recapture1"]
    values = report.overwrites[0].values
    assert {value.cell.data_element for value in values} == {"De2aaaaaaaa", "De3aaaaaaaa"}
    assert {value.previous_response_id for value in values} == {original.id}
    assert {value.previous_received_at for value in values} == {_RECEIVED_AT}
    assert {(value.cell.period, value.cell.organisation_unit) for value in values} == {("202607", _ROOT_ORG_UNIT)}
    assert report.overwritten_value_count == 2
    assert report.overwrite_line == "2 value(s) across 1 response(s)"
    assert report.forwarded_without_values == 0


@respx.mock
async def test_a_re_capture_for_another_period_is_another_value_entirely(forward_project: Path) -> None:
    """The period is one of the five keys DHIS2 stores a value under, so a new one collides with nothing."""
    _mock_instance()
    await _forward(forward_project, import_responses=True)
    _write_receipt(forward_project, _recaptured(_aggregate_document(), "recapture1", period="202608"))

    report = await _forward(forward_project, import_responses=True)

    assert report.overwrites == ()
    assert report.overwrite_line == ""


@respx.mock
async def test_a_re_capture_for_another_organisation_unit_is_another_value_entirely(forward_project: Path) -> None:
    """Two organisation units reporting the same form for the same month are two cells, not one."""
    _mock_instance()
    _publish_location(forward_project, _OTHER_ORG_UNIT)
    await _forward(forward_project, import_responses=True)
    _write_receipt(forward_project, _recaptured(_aggregate_document(), "recapture1", organisation_unit=_OTHER_ORG_UNIT))

    report = await _forward(forward_project, import_responses=True)

    assert report.overwrites == ()


@respx.mock
async def test_a_re_capture_under_another_attribute_option_combo_is_another_value_entirely(
    combo_forward_project: Path,
) -> None:
    """The attribute option combo is the third key of the envelope, so it separates two cells as surely."""
    _mock_instance()
    original = _combo_documents(GenerateConfig())[0]
    await _forward(combo_forward_project, import_responses=True)
    _write_receipt(combo_forward_project, _recaptured(original, "recapture1", attribute_option_combo="Aoc1aaaaaaa"))

    report = await _forward(combo_forward_project, import_responses=True)

    assert report.overwrites == ()

    _write_receipt(combo_forward_project, _recaptured(original, "recapture2"))
    same_combo = await _forward(combo_forward_project, import_responses=True)

    assert [overwrite.response_id for overwrite in same_combo.overwrites] == ["recapture2"]


@respx.mock
async def test_a_partial_re_capture_names_only_the_values_it_sends_again(forward_project: Path) -> None:
    """A response answering one of two questions replaces one of two values, and the run says which."""
    _mock_instance()
    await _forward(forward_project, import_responses=True)
    _write_receipt(forward_project, _recaptured(_aggregate_document(), "recapture1", keep_link_ids={"De2aaaaaaaa"}))

    report = await _forward(forward_project, import_responses=True)

    assert report.overwritten_value_count == 1
    assert _sent_values(report) == {("De2aaaaaaaa", None, "202607", _ROOT_ORG_UNIT, None)}


@respx.mock
async def test_two_captures_of_one_value_in_a_single_drain_replace_each_other(forward_project: Path) -> None:
    """A receipt filed mid-drain has landed its values, so the next one of the same run replaces them."""
    _mock_instance()
    original = _aggregate_document()
    # The queue is drained in file-name order, so `recapture1` is the second of the two to be posted.
    _write_receipt(forward_project, _recaptured(original, "recapture1"), received_at="2026-08-09T10:00:00Z")

    report = await _forward(forward_project, import_responses=True)

    assert [overwrite.response_id for overwrite in report.overwrites] == ["recapture1"]
    values = report.overwrites[0].values
    assert {value.previous_response_id for value in values} == {original.id}
    assert {value.previous_received_at for value in values} == {_RECEIVED_AT}


@respx.mock
async def test_a_dry_run_states_the_values_an_import_would_replace_and_moves_nothing(forward_project: Path) -> None:
    """The prediction is the most useful moment to say it, because there is still something to do about it."""
    _mock_instance()
    await _forward(forward_project, import_responses=True)
    _write_receipt(forward_project, _recaptured(_aggregate_document(), "recapture1"))

    report = await _forward(forward_project)

    assert report.dry_run is True
    assert [overwrite.response_id for overwrite in report.overwrites] == ["recapture1"]
    assert (forward_project / RECEIVED_RESPONSES_RELATIVE_PATH / "recapture1.json").is_file()
    assert not (forward_project / FORWARDED_RESPONSES_RELATIVE_PATH / "recapture1.json").exists()


@respx.mock
async def test_a_dry_run_predicts_two_captures_of_one_value_inside_itself(forward_project: Path) -> None:
    """A dry run files nothing, so the prediction has to be carried in the run rather than read off disk."""
    _mock_instance()
    original = _aggregate_document()
    # The queue is drained in file-name order, so `recapture1` is the second of the two to be posted.
    _write_receipt(forward_project, _recaptured(original, "recapture1"), received_at="2026-08-09T10:00:00Z")

    report = await _forward(forward_project)

    assert [overwrite.response_id for overwrite in report.overwrites] == ["recapture1"]


@respx.mock
async def test_a_receipt_dhis2_refused_sent_nothing_and_covers_nothing(forward_project: Path) -> None:
    """`rejected/` is a receipt that never landed, so a later capture of its values replaces nothing."""
    _mock_instance(aggregate_response=_rejected_aggregate())
    first = await _forward(forward_project, import_responses=True)
    assert [outcome.target_kind for outcome in first.rejected] == ["data-value-set"]
    _write_receipt(forward_project, _recaptured(_aggregate_document(), "recapture1"))

    _mock_instance()
    report = await _forward(forward_project, import_responses=True)

    assert report.overwrites == ()


@respx.mock
async def test_a_tracker_only_drain_reads_no_forwarded_receipt(
    three_event_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`forwarded/` is unbounded, and a drain that cannot land on an aggregate value has no cause to read it."""
    _mock_instance()
    await _forward(three_event_project, import_responses=True)
    layout = service.spool_layout(load_project(three_event_project))
    # The three receipts are there to be read, and a drain carrying an aggregate payload would read them.
    assert build_forwarded_cell_index(layout).receipts_read == 3

    reads: list[Path] = []

    def _record_and_refuse(read_layout: Any) -> None:
        reads.append(read_layout.root)
        raise AssertionError("a tracker-only drain must not read the forwarded receipts")

    monkeypatch.setattr(service, "build_forwarded_cell_index", _record_and_refuse)
    _fill_spool(three_event_project, _event_documents(1))

    report = await _forward(three_event_project, import_responses=True)

    assert reads == []
    assert report.overwrites == ()
    assert report.forwarded_without_values == 0


@respx.mock
async def test_a_forwarded_receipt_recording_no_values_is_counted_rather_than_ignored(
    forward_project: Path,
) -> None:
    """A receipt that landed values nothing wrote down is where an overwrite could hide, so the run says so."""
    _mock_instance()
    report = await _forward(forward_project, import_responses=True)
    aggregate = next(outcome for outcome in report.accepted if outcome.target_kind == "data-value-set")
    sidecar = forward_project / FORWARDED_RESPONSES_RELATIVE_PATH / f"{aggregate.response_id}{IMPORT_REPORT_SUFFIX}"
    written = json.loads(sidecar.read_text(encoding="utf-8"))
    written["cells"] = []
    sidecar.write_text(json.dumps(written, indent=2), encoding="utf-8")
    _write_receipt(forward_project, _recaptured(_aggregate_document(), "recapture1"))

    second = await _forward(forward_project, import_responses=True)

    assert second.overwrites == ()
    assert second.forwarded_without_values == 1


@respx.mock
async def test_the_run_names_the_last_receipt_to_have_sent_a_value(forward_project: Path) -> None:
    """Three captures of one value name the second, because the second is the number the instance holds."""
    _mock_instance()
    original = _aggregate_document()
    await _forward(forward_project, import_responses=True)
    _write_receipt(forward_project, _recaptured(original, "recapture1"), received_at="2026-08-09T10:00:00Z")
    await _forward(forward_project, import_responses=True)
    _write_receipt(forward_project, _recaptured(original, "recapture2"), received_at="2026-08-10T10:00:00Z")

    report = await _forward(forward_project, import_responses=True)

    assert {value.previous_response_id for value in report.overwrites[0].values} == {"recapture1"}
    assert {value.previous_received_at for value in report.overwrites[0].values} == {"2026-08-09T10:00:00Z"}
