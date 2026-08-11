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
import json
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from dhis2w_core.profile import resolve
from dhis2w_fhir import (
    AttributeCodeIndex,
    CodedAnswerMode,
    ForwardOutcomeKind,
    GenerateConfig,
    OptionSetIn,
    QuestionnaireItemIn,
    QuestionnaireSourceIn,
    build_attribute_combo_artifacts,
    build_attribute_combo_concept_maps,
    build_example_documents,
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
    bound_question_uids,
    build_project_context,
    load_compiled_artifacts,
)
from dhis2w_fhir.r4 import Identifier, Location, QuestionnaireResponse
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
    FORWARDED_RESPONSES_RELATIVE_PATH,
    RECEIVED_RESPONSES_RELATIVE_PATH,
    REJECTED_RESPONSES_RELATIVE_PATH,
    REJECTION_REPORT_SUFFIX,
    SpoolReadError,
)

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


def _fill_spool(root: Path, documents: list[QuestionnaireResponse]) -> None:
    """Write the receipt envelopes `d2w fhir serve` would have left for these responses."""
    directory = root / RECEIVED_RESPONSES_RELATIVE_PATH
    directory.mkdir(parents=True, exist_ok=True)
    for document in documents:
        envelope = {
            "response_id": document.id,
            "received_at": "2026-08-08T09:00:00Z",
            "form_kind": _form_kind(document),
            "questionnaire": document.questionnaire or "",
            "warnings": [],
            "response": json.loads(document.model_dump_json(exclude_none=True, by_alias=True)),
        }
        (directory / f"{document.id}.json").write_text(json.dumps(envelope, indent=2), encoding="utf-8")


def _mock_instance(
    *,
    aggregate_response: httpx.Response | None = None,
    tracker_response: httpx.Response | None = None,
) -> dict[str, respx.Route]:
    """Mock everything a forward run touches: the version probe, the value types, and the two imports."""
    respx.get(f"{_BASE_URL}/api/system/info").mock(return_value=httpx.Response(200, json={"version": "2.42.0"}))
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
    return {"value_types": value_types, "aggregate": aggregate, "tracker": tracker}


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


def _rejected_tracker_reworded() -> httpx.Response:
    """The same broken rule worded the way another DHIS2 major words it, which no generalisation reconciles.

    `E1029` names one rule; the sentence DHIS2 wraps it in is prose and differs between majors
    (BUGS.md #68 shows the same drift on `E1079`). Grouping on the sentence would report one rule as
    two causes of the run against an instance that words it either way.
    """
    return httpx.Response(
        409,
        json={
            "status": "ERROR",
            "validationReport": {
                "errorReports": [
                    {
                        "message": "Event `Ev3aaaaaaaa` organisation unit does not belong to program `IpHINAT79UW`.",
                        "errorCode": "E1029",
                        "trackerType": "EVENT",
                        "uid": "Ev3aaaaaaaa",
                    }
                ],
                "warningReports": [],
            },
            "stats": {"created": 0, "updated": 0, "deleted": 0, "ignored": 1, "total": 1},
        },
    )


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
    forwarded = sorted(path.name for path in (forward_project / FORWARDED_RESPONSES_RELATIVE_PATH).glob("*.json"))
    assert len(forwarded) == 2
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
        sidecar = directory / f"{outcome.response_id}{REJECTION_REPORT_SUFFIX}"
        written = json.loads(sidecar.read_text(encoding="utf-8"))
        assert written["status"] == outcome.import_outcome.status
        assert [issue["error_code"] for issue in written["issues"]] == [
            issue.error_code for issue in outcome.import_outcome.issues
        ]
        assert written["issues"][0]["message"]


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
async def test_an_unreadable_receipt_fails_the_run_naming_the_file(forward_project: Path) -> None:
    """A receipt silently skipped would look to its sender exactly like one that never arrived."""
    _mock_instance()
    broken = forward_project / RECEIVED_RESPONSES_RELATIVE_PATH / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    with pytest.raises(SpoolReadError, match="broken.json"):
        await _forward(forward_project)


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
    """The rollup groups on the error code, so a message DHIS2 rewords between majors stays one row."""
    _mock_instance(aggregate_response=_rejected_aggregate(), tracker_response=_rejected_tracker())
    respx.post(f"{_BASE_URL}/api/tracker").mock(
        side_effect=[_rejected_tracker(), _rejected_tracker_reworded()],
    )
    _fill_spool(forward_project, _two_event_spool())
    report = await _forward(forward_project)
    reasons = {reason.error_code: reason for reason in report.rejection_reasons}
    assert set(reasons) == {"E7611", "E1029"}
    assert reasons["E1029"].responses == 2
    # The sample shown is the first wording the run met, generalised - not a second row beside it.
    assert reasons["E1029"].reason == "Event OrganisationUnit: `...` and Program: `...`, do not match."


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
    respx.get(f"{_BASE_URL}/api/system/info").mock(return_value=httpx.Response(200, json={"version": "2.42.0"}))
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


@respx.mock
async def test_the_report_reads_back_in_spool_order_whatever_the_posting_order_was(
    tracker_forward_project: Path,
) -> None:
    """Two orders, deliberately separate: the report is the spool it drained, the posting order is the run's."""
    _mock_tracker_instance()

    report = await _forward(tracker_forward_project, import_responses=True)

    assert [outcome.response_id for outcome in report.outcomes] == ["A03MvHHogjR-example-1", "En1aaaaaaaa"]
