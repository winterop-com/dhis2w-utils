"""Tests for the generate-time refusal of DHIS2 codes and names the IG publisher's own build cannot survive.

A DHIS2 code becomes an identifier value, which the publisher writes into a table cell unescaped;
a DHIS2 name stays byte-true on the emitted resource's title, which the publisher writes into
pages it strict-parses after writing. `d2w fhir validate` already reports a `<` on either as an
error; these cover the gate that stops `d2w fhir generate` from writing an hour of build input
the publisher will abort on.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from dhis2w_core.profile import resolve_profile
from dhis2w_fhir import InitOptions, load_project, service
from dhis2w_fhir.config import HostileNamePosture
from dhis2w_fhir.hostile_names import HostileNameGate
from dhis2w_fhir.validation import build_aborting_code, build_aborting_name

_HOST = "https://dhis2.example"

#: The finding category both parity walks read, one for the error grade and one for the note.
_NAME_CATEGORY = "template-hostile-name"

#: The code that aborted a 55-minute build on a real instance: the '<' opens a tag in the cell.
_ABORTING_CODE = "ENTO - IRS < 6 Months"

#: A name the publisher's template cannot survive, shaped like the ones real instances carry.
_ABORTING_NAME = "Mortality < 5 years by gender"

#: A form name the publisher's template cannot survive, shaped like the ones real instances carry.
_HOSTILE_FORM_NAME = "Weight < 5kg"


async def _scaffold_project(directory: Path) -> None:
    """Scaffold a minimal project so the generate targets have a fhir.toml and an ig tree."""
    await service.init_project(
        directory,
        InitOptions(
            ig_id="dhis2.fhir.codes",
            canonical="http://example.org/fhir",
            name="Dhis2FhirCodes",
            title="Codes IG",
            publisher="Codes Org",
        ),
    )


def _mock_empty_metadata() -> None:
    """Answer every metadata endpoint with nothing, so a test only populates the one it is about."""
    for resource in ("optionSets", "categories", "organisationUnits", "dataSets", "programs", "programRules"):
        respx.get(f"{_HOST}/api/{resource}").mock(return_value=httpx.Response(200, json={resource: []}))
    respx.get(f"{_HOST}/api/attributes").mock(return_value=httpx.Response(200, json={"attributes": []}))


def _mock(resource: str, *items: dict[str, Any]) -> None:
    """Answer one metadata endpoint with the given objects."""
    respx.get(f"{_HOST}/api/{resource}").mock(return_value=httpx.Response(200, json={resource: list(items)}))


def _option_set(code: str = "BEDNETS", name: str = "Bednet distribution") -> dict[str, Any]:
    """One DHIS2 option set carrying the given code and name."""
    return {"id": "Os1aaaaaaaa", "name": name, "code": code, "options": []}


def _category(code: str = "SEX", name: str = "Sex") -> dict[str, Any]:
    """One DHIS2 category carrying the given code and name."""
    return {"id": "Ca1aaaaaaaa", "name": name, "code": code, "categoryOptions": []}


def _organisation_unit(code: str = "SL", name: str = "Sierra Leone") -> dict[str, Any]:
    """One DHIS2 organisation unit carrying the given code and name."""
    return {"id": "Ou1aaaaaaaa", "name": name, "code": code, "level": 1, "path": "/Ou1aaaaaaaa"}


def _data_set(code: str = "CH", name: str = "Child Health") -> dict[str, Any]:
    """One DHIS2 data set carrying the given code and name."""
    return {"id": "Ds1aaaaaaaa", "name": name, "code": code, "periodType": "Monthly"}


def _event_program(code: str = "MCR", name: str = "Malaria case registration") -> dict[str, Any]:
    """One DHIS2 event program carrying the given code and name."""
    return {
        "id": "Pr1aaaaaaaa",
        "name": name,
        "code": code,
        "programType": "WITHOUT_REGISTRATION",
        "programStages": [{"id": "Ps1aaaaaaaa", "name": "Stage", "programStageDataElements": []}],
    }


def test_the_predicate_names_only_the_character_seen_to_abort_a_build() -> None:
    """'<' opens a tag in the cell the publisher strict-parses; '>' and '&' render badly and build fine."""
    assert build_aborting_code(_ABORTING_CODE) is True
    assert build_aborting_code("A > B") is False
    assert build_aborting_code("R&D") is False
    assert build_aborting_code("ENTO_IRS_6M") is False
    assert build_aborting_code(None) is False


@respx.mock
@pytest.mark.parametrize(
    ("target", "resource", "payload", "expected_uid"),
    [
        ("option_sets", "optionSets", _option_set, "Os1aaaaaaaa"),
        ("categories", "categories", _category, "Ca1aaaaaaaa"),
        ("organisation_units", "organisationUnits", _organisation_unit, "Ou1aaaaaaaa"),
        ("questionnaires", "dataSets", _data_set, "Ds1aaaaaaaa"),
        ("questionnaires", "programs", _event_program, "Pr1aaaaaaaa"),
    ],
)
async def test_generate_refuses_a_code_that_aborts_the_publisher(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    tmp_path: Path,
    target: str,
    resource: str,
    payload: Callable[[str], dict[str, Any]],
    expected_uid: str,
) -> None:
    """Every surface whose DHIS2 code becomes an identifier value refuses the run before writing a file."""
    mock_system_info("v42")
    await _scaffold_project(tmp_path)
    _mock_empty_metadata()
    _mock(resource, payload(_ABORTING_CODE))
    generate = {
        "option_sets": service.generate_option_sets,
        "categories": service.generate_categories,
        "organisation_units": service.generate_organisation_units,
        "questionnaires": service.generate_questionnaires,
    }[target]

    with pytest.raises(service.BuildAbortingCodeError) as raised:
        await generate(resolve_profile("probe"), load_project(tmp_path))

    message = str(raised.value)
    assert resource in message
    assert expected_uid in message
    assert _ABORTING_CODE in message
    assert "Unable to Parse HTML" in message
    assert "d2w fhir validate" in message
    assert "Change the code in DHIS2" in message


@respx.mock
async def test_a_program_stage_code_is_gated_like_its_program(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    tmp_path: Path,
) -> None:
    """A tracker stage's own code rides its Questionnaire's identifier list, so it aborts the same build."""
    mock_system_info("v42")
    await _scaffold_project(tmp_path)
    _mock_empty_metadata()
    _mock(
        "programs",
        {
            "id": "Pr2aaaaaaaa",
            "name": "Child Programme",
            "programType": "WITH_REGISTRATION",
            "programStages": [
                {"id": "Ps2aaaaaaaa", "name": "Birth", "code": _ABORTING_CODE, "programStageDataElements": []}
            ],
        },
    )

    with pytest.raises(service.BuildAbortingCodeError) as raised:
        await service.generate_questionnaires(resolve_profile("probe"), load_project(tmp_path))

    assert "programStages" in str(raised.value)
    assert "Ps2aaaaaaaa" in str(raised.value)


@respx.mock
@pytest.mark.parametrize("code", ["ENTO - IRS > 6 Months", "R&D bednets"])
async def test_the_other_hostile_characters_still_generate(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    tmp_path: Path,
    code: str,
) -> None:
    """'>' and '&' cost a malformed page rather than an aborted build, so they stay validate warnings."""
    mock_system_info("v42")
    await _scaffold_project(tmp_path)
    _mock_empty_metadata()
    _mock("optionSets", _option_set(code))

    report = await service.generate_option_sets(resolve_profile("probe"), load_project(tmp_path))

    assert report.option_set_count == 1


@respx.mock
async def test_a_full_run_refuses_before_it_writes_anything(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    tmp_path: Path,
) -> None:
    """The whole run is refused rather than the object skipped - a skipped set dangles every binding to it."""
    mock_system_info("v42")
    await _scaffold_project(tmp_path)
    _mock_empty_metadata()
    _mock("optionSets", _option_set(_ABORTING_CODE))

    with pytest.raises(service.BuildAbortingCodeError):
        await service.generate_full(resolve_profile("probe"), load_project(tmp_path))

    assert not list((tmp_path / "ig" / "input" / "resources").rglob("*.json"))


@respx.mock
async def test_an_unselected_object_never_refuses_the_run(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    tmp_path: Path,
) -> None:
    """The gate reads the selection, not the instance: a set this project does not publish cannot abort it."""
    mock_system_info("v42")
    await _scaffold_project(tmp_path)
    config_path = tmp_path / "fhir.toml"
    config_path.write_text(
        f'{config_path.read_text(encoding="utf-8")}\n[generate.option_sets]\ninclude_ids = ["Os2aaaaaaaa"]\n',
        encoding="utf-8",
    )
    _mock_empty_metadata()
    _mock(
        "optionSets",
        _option_set(_ABORTING_CODE),
        {"id": "Os2aaaaaaaa", "name": "Birth type", "code": "BIRTH_TYPE", "options": []},
    )

    report = await service.generate_option_sets(resolve_profile("probe"), load_project(tmp_path))

    assert report.option_set_count == 1


@respx.mock
async def test_a_code_the_uid_stands_in_for_never_reaches_the_page(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    tmp_path: Path,
) -> None:
    """A code too malformed to be an R4 code is replaced by the UID, so its '<' is never emitted at all."""
    mock_system_info("v42")
    await _scaffold_project(tmp_path)
    _mock_empty_metadata()
    _mock("optionSets", _option_set("  ENTO < 6  Months  "))

    report = await service.generate_option_sets(resolve_profile("probe"), load_project(tmp_path))

    assert report.option_set_count == 1
    written = (tmp_path / "ig" / "input" / "resources" / "terminology").rglob("*.json")
    assert not any("<" in path.read_text(encoding="utf-8") for path in written)


def test_the_name_predicate_names_only_the_character_seen_to_abort_a_build() -> None:
    """A name's '<' aborts the publisher's re-parse of its own pages; '>' and '&' render badly and build fine."""
    assert build_aborting_name(_ABORTING_NAME) is True
    assert build_aborting_name("Mortality > 5 years") is False
    assert build_aborting_name("R&D bednets") is False
    assert build_aborting_name("Child Health") is False
    assert build_aborting_name(None) is False


@respx.mock
@pytest.mark.parametrize(
    ("target", "resource", "payload", "expected_uid"),
    [
        ("option_sets", "optionSets", _option_set, "Os1aaaaaaaa"),
        ("categories", "categories", _category, "Ca1aaaaaaaa"),
        ("organisation_units", "organisationUnits", _organisation_unit, "Ou1aaaaaaaa"),
        ("questionnaires", "dataSets", _data_set, "Ds1aaaaaaaa"),
        ("questionnaires", "programs", _event_program, "Pr1aaaaaaaa"),
    ],
)
async def test_generate_refuses_a_name_that_aborts_the_publisher(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    tmp_path: Path,
    target: str,
    resource: str,
    payload: Callable[..., dict[str, Any]],
    expected_uid: str,
) -> None:
    """Every surface whose DHIS2 name becomes a resource title refuses the run before writing a file."""
    mock_system_info("v42")
    await _scaffold_project(tmp_path)
    _mock_empty_metadata()
    _mock(resource, payload(name=_ABORTING_NAME))
    generate = {
        "option_sets": service.generate_option_sets,
        "categories": service.generate_categories,
        "organisation_units": service.generate_organisation_units,
        "questionnaires": service.generate_questionnaires,
    }[target]

    with pytest.raises(service.BuildAbortingNameError) as raised:
        await generate(resolve_profile("probe"), load_project(tmp_path))

    message = str(raised.value)
    assert resource in message
    assert expected_uid in message
    assert _ABORTING_NAME in message
    assert "d2w fhir validate" in message
    assert "Change the name in DHIS2" in message


@respx.mock
@pytest.mark.parametrize(
    ("resource", "payload", "member_key", "member_label"),
    [
        ("optionSets", _option_set, "options", "option"),
        ("categories", _category, "categoryOptions", "category option"),
    ],
)
async def test_generate_refuses_a_member_name_that_aborts_the_publisher(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    tmp_path: Path,
    resource: str,
    payload: Callable[..., dict[str, Any]],
    member_key: str,
    member_label: str,
) -> None:
    """An option's name lands in page tables the instance sweep cannot see, so the gate reads it too."""
    mock_system_info("v42")
    await _scaffold_project(tmp_path)
    _mock_empty_metadata()
    source = payload()
    source[member_key] = [{"id": "Op1aaaaaaaa", "code": "LT6M", "name": "Age < 6 months"}]
    _mock(resource, source)
    generate = service.generate_option_sets if resource == "optionSets" else service.generate_categories

    with pytest.raises(service.BuildAbortingNameError) as raised:
        await generate(resolve_profile("probe"), load_project(tmp_path))

    message = str(raised.value)
    assert member_label in message
    assert "Op1aaaaaaaa" in message
    assert "Age < 6 months" in message


@respx.mock
@pytest.mark.parametrize("name", ["Mortality > 5 years", "R&D bednets"])
async def test_the_other_hostile_name_characters_still_generate(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    tmp_path: Path,
    name: str,
) -> None:
    """'>' and '&' in a name cost a malformed page rather than an aborted build, so they stay warnings."""
    mock_system_info("v42")
    await _scaffold_project(tmp_path)
    _mock_empty_metadata()
    _mock("optionSets", _option_set(name=name))

    report = await service.generate_option_sets(resolve_profile("probe"), load_project(tmp_path))

    assert report.option_set_count == 1


@respx.mock
async def test_a_full_run_refuses_a_hostile_name_before_it_writes_anything(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    tmp_path: Path,
) -> None:
    """The name gate holds on the full pipeline exactly as the code gate does."""
    mock_system_info("v42")
    await _scaffold_project(tmp_path)
    _mock_empty_metadata()
    _mock("dataSets", _data_set(name=_ABORTING_NAME))

    with pytest.raises(service.BuildAbortingNameError):
        await service.generate_full(resolve_profile("probe"), load_project(tmp_path))

    assert not list((tmp_path / "ig" / "input" / "resources").rglob("*.json"))


#: One tiny instance holding exactly one object of every kind a selection can put on the build path.
#:
#: The parity walk poisons one name at a time and asks both commands about the same instance, so the
#: payload has to carry every kind at once: a data set with a question, an event program with a
#: stage question, a tracker program with a registration attribute and a stage of its own, the
#: tracked entity type that program enrols into with a question of its own, an option set with an
#: option, a category with a category option, and one organisation unit.
def _parity_instance() -> dict[str, list[dict[str, Any]]]:
    """The whole parity instance as one collection-per-endpoint mapping, freshly built each call."""
    return {
        "dataSets": [
            {
                "id": "DsPar000001",
                "name": "Child care",
                "code": "CHILD_CARE",
                "periodType": "Monthly",
                "dataSetElements": [{"dataElement": {"id": "DePar000001", "name": "Weight", "valueType": "NUMBER"}}],
            }
        ],
        "programs": [
            {
                "id": "PrEvt000001",
                "name": "Supervision visit",
                "code": "SUPERVISION",
                "programType": "WITHOUT_REGISTRATION",
                "programStages": [
                    {
                        "id": "PsEvt000001",
                        "name": "Visit",
                        "programStageDataElements": [
                            {"dataElement": {"id": "DeEvt000001", "name": "Visit finding", "valueType": "TEXT"}}
                        ],
                    }
                ],
            },
            {
                "id": "PrTrk000001",
                "name": "Child programme",
                "code": "CHILD_PROGRAMME",
                "programType": "WITH_REGISTRATION",
                "trackedEntityType": {"id": "TeTyp000001"},
                "programTrackedEntityAttributes": [
                    {"trackedEntityAttribute": {"id": "TeAtt000001", "name": "Given name", "valueType": "TEXT"}}
                ],
                "programStages": [
                    {
                        "id": "PsTrk000001",
                        "name": "Birth",
                        "code": "BIRTH",
                        "programStageDataElements": [
                            {"dataElement": {"id": "DeStg000001", "name": "Birth weight", "valueType": "NUMBER"}}
                        ],
                    }
                ],
            },
        ],
        "trackedEntityTypes": [
            {
                "id": "TeTyp000001",
                "name": "Person",
                "code": "PERSON",
                "trackedEntityTypeAttributes": [
                    {"trackedEntityAttribute": {"id": "TeAtt000002", "name": "Family name", "valueType": "TEXT"}}
                ],
            }
        ],
        "optionSets": [
            {
                "id": "OsPar000001",
                "name": "Bednet distribution",
                "code": "BEDNETS",
                "options": [{"id": "OpPar000001", "name": "Any bednet", "code": "ANY"}],
            }
        ],
        "categories": [
            {
                "id": "CaPar000001",
                "name": "Sex",
                "code": "SEX",
                "categoryOptions": [{"id": "CoPar000001", "name": "Female", "code": "F"}],
            }
        ],
        "organisationUnits": [
            {"id": "OuPar000001", "name": "Sierra Leone", "code": "SL", "level": 1, "path": "/OuPar000001"}
        ],
        "programRules": [],
        "attributes": [],
    }


def _poison(instance: dict[str, list[dict[str, Any]]], uid: str) -> None:
    """Give the named object a name the publisher's build cannot survive, wherever in the instance it sits."""
    found = any(_poison_object(entry, uid) for collection in instance.values() for entry in collection)
    assert found, f"the parity instance holds no object {uid}"


def _set_form_name(instance: dict[str, list[dict[str, Any]]], uid: str, form_name: str) -> None:
    """Give the named question object a DHIS2 form name, wherever in the instance it sits."""
    found = any(
        _set_object_form_name(entry, uid, form_name) for collection in instance.values() for entry in collection
    )
    assert found, f"the parity instance holds no object {uid}"


def _set_object_form_name(entry: dict[str, Any], uid: str, form_name: str) -> bool:
    """Write a form name onto one wire object, or any object nested inside it."""
    found = entry.get("id") == uid
    if found:
        entry["formName"] = form_name
    for value in entry.values():
        if isinstance(value, dict):
            found = _set_object_form_name(value, uid, form_name) or found
        for nested in value if isinstance(value, list) else []:
            if isinstance(nested, dict):
                found = _set_object_form_name(nested, uid, form_name) or found
    return found


def _poison_object(entry: dict[str, Any], uid: str) -> bool:
    """Rename one wire object, or any object nested inside it, walking the lists DHIS2 nests them in."""
    found = entry.get("id") == uid and "name" in entry
    if found:
        entry["name"] = f"{entry['name']} < 5y"
    for value in entry.values():
        if isinstance(value, dict):
            found = _poison_object(value, uid) or found
        for nested in value if isinstance(value, list) else []:
            if isinstance(nested, dict):
                found = _poison_object(nested, uid) or found
    return found


def _mock_parity_instance(instance: dict[str, list[dict[str, Any]]]) -> None:
    """Answer every endpoint both commands read with the parity instance, the validate sweep included."""
    for resource, items in instance.items():
        respx.get(f"{_HOST}/api/{resource}").mock(return_value=httpx.Response(200, json={resource: items}))
    respx.get(f"{_HOST}/api/metadata").mock(return_value=httpx.Response(200, json=_sweep_body(instance)))


def _sweep_body(instance: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    """The `/api/metadata?fields=id,name,code` body this instance answers with.

    The sweep is a flat `collection -> [{id, name, code}]` map over every object DHIS2 holds, so the
    questions, the stages, and the category options the parity instance nests inside their parents
    are swept as the top-level collections they really are. Options are the one exclusion the sweep
    itself states, because validate reads them through its own per-set pass instead.
    """
    body: dict[str, list[dict[str, Any]]] = {
        resource: [_swept(item) for item in items] for resource, items in instance.items()
    }
    body["programStages"] = [
        _swept(stage) for program in instance["programs"] for stage in program.get("programStages", [])
    ]
    body["dataElements"] = [
        _swept(entry["dataElement"])
        for data_set in instance["dataSets"]
        for entry in data_set.get("dataSetElements", [])
    ] + [
        _swept(entry["dataElement"])
        for program in instance["programs"]
        for stage in program.get("programStages", [])
        for entry in stage.get("programStageDataElements", [])
    ]
    body["trackedEntityAttributes"] = [
        _swept(entry["trackedEntityAttribute"])
        for program in instance["programs"]
        for entry in program.get("programTrackedEntityAttributes", [])
    ] + [
        _swept(entry["trackedEntityAttribute"])
        for tracked_entity_type in instance["trackedEntityTypes"]
        for entry in tracked_entity_type.get("trackedEntityTypeAttributes", [])
    ]
    body["categoryOptions"] = [
        _swept(option) for category in instance["categories"] for option in category.get("categoryOptions", [])
    ]
    return body


def _swept(item: dict[str, Any]) -> dict[str, Any]:
    """One object as the sweep projects it: its id, its two names, and its code and nothing else.

    DHIS2 answers the sweep without `formName` on every collection that has no such field, which is
    every collection but the two a form asks its questions from - so the key is written only where
    the fixture states one.
    """
    swept = {"id": item["id"], "name": item["name"], "code": item.get("code")}
    if "formName" in item:
        swept["formName"] = item["formName"]
    return swept


#: Every object kind a `fhir.toml` selection can put on the build path, with the sweep collection
#: `d2w fhir validate` grades it under. The parity walk poisons each in turn and asserts the two
#: commands agree: a selection-scoped `template-hostile-name` error is a generate refusal, and a
#: generate refusal is a selection-scoped error. An event program's stage is deliberately absent -
#: it publishes no form of its own, so neither command reads its name.
_SELECTABLE_OBJECT_KINDS: list[tuple[str, str]] = [
    ("OsPar000001", "optionSets"),
    ("OpPar000001", "options"),
    ("CaPar000001", "categories"),
    ("CoPar000001", "categoryOptions"),
    ("OuPar000001", "organisationUnits"),
    ("DsPar000001", "dataSets"),
    ("PrEvt000001", "programs"),
    ("PrTrk000001", "programs"),
    ("PsTrk000001", "programStages"),
    ("TeTyp000001", "trackedEntityTypes"),
    ("DePar000001", "dataElements"),
    ("DeEvt000001", "dataElements"),
    ("DeStg000001", "dataElements"),
    ("TeAtt000001", "trackedEntityAttributes"),
    ("TeAtt000002", "trackedEntityAttributes"),
]


async def _parity_project(directory: Path, posture: str = "refuse") -> None:
    """Scaffold the parity project: every kind selected, and no examples, so nothing reads data values.

    The posture is written explicitly because it is half of what the parity means. `refuse` is the
    reading the two-way walk asserts - a validate error is a generate refusal - and `substitute` is
    the reading where neither happens, so a test that wants one has to say which.
    """
    await _scaffold_project(directory)
    config_path = directory / "fhir.toml"
    scaffolded = config_path.read_text(encoding="utf-8").replace(
        'hostile_names = "substitute"', f'hostile_names = "{posture}"'
    )
    config_path.write_text(f"{scaffolded}\n[generate.examples]\nper_target = 0\n", encoding="utf-8")


@respx.mock
@pytest.mark.parametrize(
    ("uid", "collection"), _SELECTABLE_OBJECT_KINDS, ids=[uid for uid, _ in _SELECTABLE_OBJECT_KINDS]
)
async def test_a_name_validate_grades_an_error_is_a_name_generate_refuses(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    tmp_path: Path,
    uid: str,
    collection: str,
) -> None:
    """Parity, both ways, over every object kind a selection can publish.

    One object is renamed at a time and both commands are asked about the same instance: the finding
    validate raises must be a selection-scoped `template-hostile-name` error on that object, and
    generate must refuse the run naming it. Neither command may be the only one that notices.
    """
    mock_system_info("v42")
    await _parity_project(tmp_path)
    instance = _parity_instance()
    _poison(instance, uid)
    _mock_parity_instance(instance)
    project = load_project(tmp_path)

    report = await service.validate_codes(resolve_profile("probe"), project.config.generate)
    graded = [
        finding
        for finding in report.findings
        if finding.uid == uid and finding.category == "template-hostile-name" and finding.scope == "selection"
    ]
    assert graded, f"validate raised no selection-scoped name error on {uid}"
    assert graded[0].severity == "error"
    assert graded[0].resource_type == collection

    with pytest.raises(service.BuildAbortingNameError) as raised:
        await service.generate_full(resolve_profile("probe"), project)

    assert uid in str(raised.value)


@respx.mock
@pytest.mark.parametrize(
    ("uid", "collection"), _SELECTABLE_OBJECT_KINDS, ids=[uid for uid, _ in _SELECTABLE_OBJECT_KINDS]
)
async def test_under_substitute_the_same_name_is_a_note_and_the_run_completes(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    tmp_path: Path,
    uid: str,
    collection: str,
) -> None:
    """The other posture, both ways: the guide rewrites the name, so validate notes it and generate writes it.

    Same instance, same object, same walk - only the project's `hostile_names` differs. Every
    finding the refusing walk grades an error is graded info here, and the generate run that
    refuses there completes here, which is the parity `make refresh` depends on.
    """
    mock_system_info("v42")
    await _parity_project(tmp_path, posture="substitute")
    instance = _parity_instance()
    _poison(instance, uid)
    _mock_parity_instance(instance)
    project = load_project(tmp_path)

    report = await service.validate_codes(resolve_profile("probe"), project.config.generate)
    graded = [finding for finding in report.findings if finding.uid == uid and finding.category == _NAME_CATEGORY]
    assert graded, f"validate raised no name finding on {uid}"
    assert graded[0].severity == "info"
    assert graded[0].resource_type == collection
    assert "rewritten for publication" in graded[0].message
    assert report.error_count == 0

    generated = await service.generate_full(
        resolve_profile("probe"), project, gate=HostileNameGate(HostileNamePosture.SUBSTITUTE)
    )
    assert generated.questionnaires.questionnaire_count > 0


@respx.mock
async def test_a_clean_instance_is_neither_an_error_nor_a_refusal(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    tmp_path: Path,
) -> None:
    """The other half of the parity: nothing hostile means no error and no refusal, so the walk means something."""
    mock_system_info("v42")
    await _parity_project(tmp_path)
    _mock_parity_instance(_parity_instance())
    project = load_project(tmp_path)

    report = await service.validate_codes(resolve_profile("probe"), project.config.generate)
    assert [finding.uid for finding in report.findings if finding.severity == "error"] == []

    generated = await service.generate_full(resolve_profile("probe"), project)
    assert generated.questionnaires.questionnaire_count > 0


@respx.mock
@pytest.mark.parametrize(
    ("uid", "collection", "asked_by"),
    [
        ("DePar000001", "dataElements", "dataSets"),
        ("DeEvt000001", "dataElements", "programs"),
        ("DeStg000001", "dataElements", "programStages"),
        ("TeAtt000001", "trackedEntityAttributes", "programs"),
        ("TeAtt000002", "trackedEntityAttributes", "trackedEntityTypes"),
    ],
)
async def test_generate_refuses_a_question_name_that_aborts_the_publisher(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    tmp_path: Path,
    uid: str,
    collection: str,
    asked_by: str,
) -> None:
    """A question's name is its label and its dictionary concept display, so the gate reads it too."""
    mock_system_info("v42")
    await _parity_project(tmp_path)
    instance = _parity_instance()
    _poison(instance, uid)
    _mock_parity_instance(instance)

    with pytest.raises(service.BuildAbortingNameError) as raised:
        await service.generate_questionnaires(resolve_profile("probe"), load_project(tmp_path))

    message = str(raised.value)
    assert collection in message
    assert uid in message
    assert asked_by in message
    assert "Change the name in DHIS2" in message


@respx.mock
@pytest.mark.parametrize(
    ("uid", "collection"),
    [("DePar000001", "dataElements"), ("TeAtt000001", "trackedEntityAttributes")],
)
async def test_generate_refuses_a_question_form_name_that_aborts_the_publisher(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    tmp_path: Path,
    uid: str,
    collection: str,
) -> None:
    """A form name is the question's label wherever DHIS2 states one, so the gate reads it beside the name."""
    mock_system_info("v42")
    await _parity_project(tmp_path)
    instance = _parity_instance()
    _set_form_name(instance, uid, _HOSTILE_FORM_NAME)
    _mock_parity_instance(instance)

    with pytest.raises(service.BuildAbortingNameError) as raised:
        await service.generate_questionnaires(resolve_profile("probe"), load_project(tmp_path))

    message = str(raised.value)
    assert collection in message
    assert uid in message
    assert "has a form name carrying" in message
    assert "Change the form name in DHIS2" in message


@respx.mock
@pytest.mark.parametrize(
    ("uid", "collection"),
    [("DePar000001", "dataElements"), ("TeAtt000001", "trackedEntityAttributes")],
)
async def test_validate_grades_a_hostile_form_name_the_way_it_grades_a_name(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    tmp_path: Path,
    uid: str,
    collection: str,
) -> None:
    """The parity holds on the form name too: what generate refuses, validate calls a selection error."""
    mock_system_info("v42")
    await _parity_project(tmp_path)
    instance = _parity_instance()
    _set_form_name(instance, uid, _HOSTILE_FORM_NAME)
    _mock_parity_instance(instance)
    project = load_project(tmp_path)

    report = await service.validate_codes(resolve_profile("probe"), project.config.generate)

    graded = [finding for finding in report.findings if finding.uid == uid and finding.category == _NAME_CATEGORY]
    assert graded, f"validate raised no name finding on {uid}"
    assert graded[0].severity == "error"
    assert graded[0].scope == "selection"
    assert graded[0].resource_type == collection
    assert "form name" in graded[0].message


@respx.mock
async def test_a_clean_form_name_is_neither_an_error_nor_a_refusal(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    tmp_path: Path,
) -> None:
    """A form name DHIS2 states cleanly is published as the question's label and graded by nobody."""
    mock_system_info("v42")
    await _parity_project(tmp_path)
    instance = _parity_instance()
    _set_form_name(instance, "DePar000001", "Weight in kilograms")
    _mock_parity_instance(instance)
    project = load_project(tmp_path)

    report = await service.validate_codes(resolve_profile("probe"), project.config.generate)
    assert [finding.uid for finding in report.findings if finding.severity == "error"] == []

    generated = await service.generate_full(resolve_profile("probe"), project)
    assert generated.questionnaires.questionnaire_count > 0


@respx.mock
async def test_a_question_code_carrying_the_character_still_generates(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    tmp_path: Path,
) -> None:
    """A question's DHIS2 code is a concept property the publisher escapes, so only its name is gated."""
    mock_system_info("v42")
    await _parity_project(tmp_path)
    instance = _parity_instance()
    instance["dataSets"][0]["dataSetElements"][0]["dataElement"]["code"] = "DE < 5"
    _mock_parity_instance(instance)

    report = await service.generate_questionnaires(resolve_profile("probe"), load_project(tmp_path))

    assert report.questionnaire_count > 0


@respx.mock
@pytest.mark.parametrize("target", ["questionnaires", "examples", "pages"])
async def test_every_target_that_writes_a_form_name_refuses_the_same_name(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    tmp_path: Path,
    target: str,
) -> None:
    """The catalog and the examples name the same forms the questionnaires do, so all three read one gate."""
    mock_system_info("v42")
    await _scaffold_project(tmp_path)
    instance = _parity_instance()
    _poison(instance, "DePar000001")
    _mock_parity_instance(instance)
    generate = {
        "questionnaires": service.generate_questionnaires,
        "examples": service.generate_examples,
        "pages": service.generate_pages,
    }[target]

    with pytest.raises(service.BuildAbortingNameError) as raised:
        await generate(resolve_profile("probe"), load_project(tmp_path))

    assert "DePar000001" in str(raised.value)
