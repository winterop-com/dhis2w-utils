"""Tests for the load-set target: a volume corpus of synthetic QuestionnaireResponse documents.

Where `generate examples` writes the one example per form an IG publishes, this writes as many as
a POST loop wants, straight to JSON, into a `load/` directory the target owns outright.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from dhis2w_core.profile import resolve_profile
from dhis2w_fhir import InitOptions, load_project, service

_HOST = "https://dhis2.example"
_CANONICAL = "http://example.org/fhir"
_ROOT_ORG_UNIT = "ImspTQPwCqd"

#: The published unit both targets are assigned to - where an assignment-aware pick has to land.
_SHARED_UNIT = "DiszpKrYNg8"

#: A published unit only the event program is assigned to, so the two targets draw different sets.
_PROGRAM_UNIT = "g8upMTyEZGZ"

#: A unit the program is assigned to that the registry selection does not publish, so no reference
#: may name it however the assignment reads.
_UNPUBLISHED_UNIT = "Rp268JB6Ne4"

#: The two questionnaire targets every run here builds from: one data set, one event program.
_QUESTIONNAIRE_COUNT = 2

_DATA_SET_UID = "BfMAe6Itzgt"
_PROGRAM_UID = "VBqh0ynB2wv"

#: The non-default category combo a data set may ride: its option combos are the attribute option
#: combos every value it holds is keyed by, and a response has to name one of them or earn `E8023`.
_NON_DEFAULT_DATA_SET_COMBO: dict[str, object] = {
    "id": "AccAaBbCcDd",
    "name": "Project",
    "isDefault": False,
    "categoryOptionCombos": [
        {"id": "Aoc1aaaaaaa", "name": "Partner A", "code": "PA"},
        {"id": "Aoc2aaaaaaa", "name": "Partner B", "code": "PB"},
    ],
}
_DEFAULT_DATA_SET_COMBO: dict[str, object] = {"id": "bjDvmb4bfuf", "name": "default", "isDefault": True}

#: The attribute option combos the non-default combo publishes, which a drawn response must name one of.
_ATTRIBUTE_OPTION_COMBO_CODES = frozenset({"Aoc1aaaaaaa", "Aoc2aaaaaaa"})

#: Where a drawn attribute option combo is coded from - the pair the questionnaire target publishes.
_ATTRIBUTE_COMBO_CODE_SYSTEM = f"{_CANONICAL}/CodeSystem/d2-aoc-AccAaBbCcDd-cs"

#: The extension an aggregate response carries its attribute option combo on.
_ATTRIBUTE_OPTION_COMBO_EXTENSION = f"{_CANONICAL}/StructureDefinition/d2-attribute-option-combo"


def _data_sets_payload(
    *, organisation_units: tuple[str, ...] = (_SHARED_UNIT,), category_combo: dict[str, object] | None = None
) -> dict[str, object]:
    """The data set both reads answer with: the form projection, its assignment, and its category combo."""
    return {
        "dataSets": [
            {
                "id": _DATA_SET_UID,
                "name": "Child Health",
                "periodType": "Monthly",
                "organisationUnits": [{"id": uid} for uid in organisation_units],
                "categoryCombo": category_combo if category_combo is not None else _DEFAULT_DATA_SET_COMBO,
                "sections": [{"id": "Sec1aaaaaaa", "name": "Immunization", "dataElements": [{"id": "De1aaaaaaaa"}]}],
                "dataSetElements": [
                    {
                        "dataElement": {
                            "id": "De1aaaaaaaa",
                            "name": "BCG doses given",
                            "valueType": "INTEGER_ZERO_OR_POSITIVE",
                            "categoryCombo": {
                                "id": "CcAaBbCcDdE",
                                "name": "EPI/nutrition age",
                                "isDefault": False,
                                "categoryOptionCombos": [
                                    {"id": "Coc1aaaaaaa", "name": "<1y", "code": "U1"},
                                    {"id": "Coc2aaaaaaa", "name": ">1y"},
                                ],
                            },
                        }
                    },
                    {
                        "dataElement": {
                            "id": "De3aaaaaaaa",
                            "name": "Gender",
                            "valueType": "TEXT",
                            "optionSet": {"id": "Os1aaaaaaaa"},
                            "categoryCombo": {"id": "bjDvmb4bfuf", "name": "default", "isDefault": True},
                        }
                    },
                ],
            }
        ]
    }


def _programs_payload(
    *, organisation_units: tuple[str, ...] = (_SHARED_UNIT, _PROGRAM_UNIT, _UNPUBLISHED_UNIT)
) -> dict[str, object]:
    """The event program both reads answer with: the form projection plus the units it is assigned to."""
    return {
        "programs": [
            {
                "id": _PROGRAM_UID,
                "name": "Malaria case registration",
                "programType": "WITHOUT_REGISTRATION",
                "organisationUnits": [{"id": uid} for uid in organisation_units],
                "programStages": [
                    {
                        "id": "pTo4uMt3xur",
                        "programStageSections": [],
                        "programStageDataElements": [
                            {
                                "compulsory": True,
                                "dataElement": {"id": "qrur9Dvnyt5", "name": "Age in years", "valueType": "INTEGER"},
                            }
                        ],
                    }
                ],
            }
        ]
    }


_OPTION_SETS_PAYLOAD = {
    "optionSets": [
        {
            "id": "Os1aaaaaaaa",
            "name": "Gender",
            "options": [
                {"id": "Op1aaaaaaaa", "code": "F", "name": "Female"},
                {"id": "Op2aaaaaaaa", "code": "M", "name": "Male"},
            ],
        }
    ]
}

#: The registry selection: the level-1 root first, because that read takes the first unit it is answered.
_ORG_UNITS_PAYLOAD = {
    "organisationUnits": [
        {"id": _ROOT_ORG_UNIT, "name": "Sierra Leone"},
        {"id": _SHARED_UNIT, "name": "Ngelehun CHC"},
        {"id": _PROGRAM_UNIT, "name": "Njandama MCHP"},
    ]
}


async def _scaffold_project(directory: Path) -> None:
    """Scaffold a project holding both questionnaire targets a load set is built from."""
    options = InitOptions(
        ig_id="dhis2.fhir.load",
        canonical=_CANONICAL,
        name="Dhis2FhirLoad",
        title="Load IG",
        publisher="Example Org",
        data_set_ids=[_DATA_SET_UID],
        event_program_ids=[_PROGRAM_UID],
    )
    await service.init_project(directory, options)


def _mock_metadata() -> None:
    """Mock every metadata endpoint one load-set run reads."""
    respx.get(f"{_HOST}/api/dataSets").mock(return_value=httpx.Response(200, json=_data_sets_payload()))
    respx.get(f"{_HOST}/api/programs").mock(return_value=httpx.Response(200, json=_programs_payload()))
    respx.get(f"{_HOST}/api/optionSets").mock(return_value=httpx.Response(200, json=_OPTION_SETS_PAYLOAD))
    respx.get(f"{_HOST}/api/organisationUnits").mock(return_value=httpx.Response(200, json=_ORG_UNITS_PAYLOAD))


def _subjects(directory: Path, prefix: str) -> list[str]:
    """The Location every written document of one target is subject to, in file-name order."""
    documents = [
        json.loads(path.read_text(encoding="utf-8")) for path in sorted(directory.glob(f"{prefix}-example-*.json"))
    ]
    return [document["subject"]["reference"] for document in documents]


async def _run(tmp_path: Path, per_target: int = 3) -> service.LoadSetReport:
    """Scaffold a project and generate one load set into it."""
    await _scaffold_project(tmp_path)
    return await service.generate_load_set(resolve_profile("probe"), load_project(tmp_path), per_target=per_target)


def _load_files(tmp_path: Path, target_uid: str) -> list[Path]:
    """The corpus files one target contributed, in file-name order."""
    return sorted((tmp_path / "load").glob(f"{target_uid}-*.json"))


@respx.mock
async def test_a_load_set_writes_one_document_per_target_and_ordinal(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    wire_version: str,
    tmp_path: Path,
) -> None:
    """`per_target` documents per questionnaire target land in `load/`, one JSON file each."""
    mock_system_info(wire_version)
    _mock_metadata()
    report = await _run(tmp_path, per_target=3)
    assert report.response_count == 3 * _QUESTIONNAIRE_COUNT
    assert report.questionnaire_count == _QUESTIONNAIRE_COUNT
    assert len(report.written_files) == 3 * _QUESTIONNAIRE_COUNT
    assert sorted(path.name for path in (tmp_path / "load").glob("*.json")) == sorted(
        [
            "BfMAe6Itzgt-example-1.json",
            "BfMAe6Itzgt-example-2.json",
            "BfMAe6Itzgt-example-3.json",
            "VBqh0ynB2wv-example-1.json",
            "VBqh0ynB2wv-example-2.json",
            "VBqh0ynB2wv-example-3.json",
        ]
    )


@respx.mock
async def test_a_load_set_reports_its_target_directory_and_project_root(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    wire_version: str,
    tmp_path: Path,
) -> None:
    """The report names where the corpus was written, so a caller can point a POST loop at it."""
    mock_system_info(wire_version)
    _mock_metadata()
    report = await _run(tmp_path)
    assert report.target_directory == "load"
    assert report.project_root == tmp_path


@respx.mock
async def test_every_written_file_is_a_questionnaire_response_document(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    wire_version: str,
    tmp_path: Path,
) -> None:
    """Each file parses as JSON and carries the resource type a capture server accepts."""
    mock_system_info(wire_version)
    _mock_metadata()
    await _run(tmp_path)
    documents = [json.loads(path.read_text(encoding="utf-8")) for path in sorted((tmp_path / "load").glob("*.json"))]
    assert documents
    assert {document["resourceType"] for document in documents} == {"QuestionnaireResponse"}
    assert all(document["questionnaire"].startswith(f"{_CANONICAL}/Questionnaire/") for document in documents)


@respx.mock
async def test_a_document_ends_on_a_newline(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    wire_version: str,
    tmp_path: Path,
) -> None:
    """The files are text on disk, so each one closes with the newline a text file ends on."""
    mock_system_info(wire_version)
    _mock_metadata()
    await _run(tmp_path)
    body = (tmp_path / "load" / "BfMAe6Itzgt-example-1.json").read_text(encoding="utf-8")
    assert body.endswith("}\n")
    assert '\n  "id": "BfMAe6Itzgt-example-1",' in body


@respx.mock
async def test_a_rerun_over_unchanged_metadata_writes_nothing(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    wire_version: str,
    tmp_path: Path,
) -> None:
    """The generator is seeded, so a second run reports every file unchanged."""
    mock_system_info(wire_version)
    _mock_metadata()
    await _run(tmp_path)
    rerun = await service.generate_load_set(resolve_profile("probe"), load_project(tmp_path), per_target=3)
    assert rerun.written_files == []
    assert rerun.deleted_files == []
    assert rerun.unchanged_count == 3 * _QUESTIONNAIRE_COUNT


@respx.mock
async def test_a_smaller_rerun_sweeps_the_documents_it_no_longer_produces(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    wire_version: str,
    tmp_path: Path,
) -> None:
    """The target owns `load/` outright, so shrinking the count deletes the tail it no longer writes."""
    mock_system_info(wire_version)
    _mock_metadata()
    await _run(tmp_path, per_target=4)
    rerun = await service.generate_load_set(resolve_profile("probe"), load_project(tmp_path), per_target=2)
    assert rerun.response_count == 2 * _QUESTIONNAIRE_COUNT
    assert sorted(rerun.deleted_files) == [
        "BfMAe6Itzgt-example-3.json",
        "BfMAe6Itzgt-example-4.json",
        "VBqh0ynB2wv-example-3.json",
        "VBqh0ynB2wv-example-4.json",
    ]
    assert len(list((tmp_path / "load").glob("*.json"))) == 2 * _QUESTIONNAIRE_COUNT


@respx.mock
@pytest.mark.parametrize("per_target", [2, 25])
async def test_the_document_count_follows_the_requested_volume(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    wire_version: str,
    tmp_path: Path,
    per_target: int,
) -> None:
    """The load set is not bounded the way `[generate.examples]` is - the caller asks for the volume."""
    mock_system_info(wire_version)
    _mock_metadata()
    report = await _run(tmp_path, per_target=per_target)
    assert report.response_count == per_target * _QUESTIONNAIRE_COUNT
    assert len(list((tmp_path / "load").glob("*.json"))) == per_target * _QUESTIONNAIRE_COUNT


@respx.mock
async def test_an_output_directory_relocates_the_corpus_off_the_project_root(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    wire_version: str,
    tmp_path: Path,
) -> None:
    """A caller writing into a scratch directory gets `load/` there, and nothing in the project."""
    mock_system_info(wire_version)
    _mock_metadata()
    await _scaffold_project(tmp_path)
    elsewhere = tmp_path / "scratch"
    report = await service.generate_load_set(
        resolve_profile("probe"), load_project(tmp_path), per_target=2, output_directory=elsewhere
    )
    assert report.project_root == tmp_path
    assert len(list((elsewhere / "load").glob("*.json"))) == 2 * _QUESTIONNAIRE_COUNT
    assert not (tmp_path / "load").exists()


@respx.mock
async def test_an_instance_without_a_root_organisation_unit_writes_nothing_with_a_note(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    wire_version: str,
    tmp_path: Path,
) -> None:
    """Every example is subject to the root unit, so an instance without one yields a note rather than files."""
    mock_system_info(wire_version)
    _mock_metadata()
    respx.get(f"{_HOST}/api/organisationUnits").mock(return_value=httpx.Response(200, json={"organisationUnits": []}))
    report = await _run(tmp_path)
    assert report.response_count == 0
    assert report.written_files == []
    assert "the instance has no level-1 organisation unit; no load set emitted" in [
        note.message for note in report.notes
    ]


@respx.mock
async def test_every_response_is_captured_at_a_unit_its_target_is_assigned_to(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    wire_version: str,
    tmp_path: Path,
) -> None:
    """DHIS2 scopes each container to its own units, so the draw is the target's assignment, not the registry."""
    mock_system_info(wire_version)
    _mock_metadata()
    await _run(tmp_path, per_target=8)
    load = tmp_path / "load"
    assert set(_subjects(load, _DATA_SET_UID)) == {f"Location/{_SHARED_UNIT}"}
    assert set(_subjects(load, _PROGRAM_UID)) == {f"Location/{_SHARED_UNIT}", f"Location/{_PROGRAM_UNIT}"}


@respx.mock
async def test_an_assigned_unit_the_registry_does_not_publish_is_never_drawn(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    wire_version: str,
    tmp_path: Path,
) -> None:
    """The draw is an intersection: a unit the guide publishes no Location for stays out of it."""
    mock_system_info(wire_version)
    _mock_metadata()
    await _run(tmp_path, per_target=25)
    assert f"Location/{_UNPUBLISHED_UNIT}" not in _subjects(tmp_path / "load", _PROGRAM_UID)


@respx.mock
async def test_a_target_with_no_published_assigned_unit_is_skipped_with_a_note(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    wire_version: str,
    tmp_path: Path,
) -> None:
    """An empty intersection emits nothing for that target: a response DHIS2 refuses measures nothing."""
    mock_system_info(wire_version)
    _mock_metadata()
    respx.get(f"{_HOST}/api/dataSets").mock(
        return_value=httpx.Response(200, json=_data_sets_payload(organisation_units=(_UNPUBLISHED_UNIT,)))
    )
    report = await _run(tmp_path, per_target=3)
    assert report.questionnaire_count == 1
    assert report.response_count == 3
    assert list((tmp_path / "load").glob(f"{_DATA_SET_UID}-*.json")) == []
    assert any(
        note.message.startswith("1 questionnaire targets have no published organisation unit assigned to them")
        and f"Child Health ({_DATA_SET_UID})" in note.message
        for note in report.notes
    )


@respx.mock
async def test_a_target_assigned_to_nothing_is_skipped_with_the_same_note(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    wire_version: str,
    tmp_path: Path,
) -> None:
    """A container DHIS2 assigns no unit at all is the same case as one assigned only outside the registry."""
    mock_system_info(wire_version)
    _mock_metadata()
    respx.get(f"{_HOST}/api/programs").mock(
        return_value=httpx.Response(200, json=_programs_payload(organisation_units=()))
    )
    report = await _run(tmp_path, per_target=2)
    assert report.questionnaire_count == 1
    assert list((tmp_path / "load").glob(f"{_PROGRAM_UID}-*.json")) == []
    assert any(
        f"Malaria case registration ({_PROGRAM_UID})" in note.message
        and "no published organisation unit assigned" in note.message
        for note in report.notes
    )


@respx.mock
async def test_a_data_set_on_a_non_default_category_combo_carries_a_drawn_attribute_option_combo(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    wire_version: str,
    tmp_path: Path,
) -> None:
    """Every response names one of the combos the data set really holds, so DHIS2 has no `E8023` to raise."""
    mock_system_info(wire_version)
    _mock_metadata()
    respx.get(f"{_HOST}/api/dataSets").mock(
        return_value=httpx.Response(200, json=_data_sets_payload(category_combo=_NON_DEFAULT_DATA_SET_COMBO))
    )
    report = await _run(tmp_path, per_target=3)
    assert report.questionnaire_count == _QUESTIONNAIRE_COUNT
    documents = [json.loads(path.read_text(encoding="utf-8")) for path in _load_files(tmp_path, _DATA_SET_UID)]
    assert len(documents) == 3
    codings = [
        extension["valueCoding"]
        for document in documents
        for extension in document["extension"]
        if extension["url"] == _ATTRIBUTE_OPTION_COMBO_EXTENSION
    ]
    assert len(codings) == 3
    assert {coding["system"] for coding in codings} == {_ATTRIBUTE_COMBO_CODE_SYSTEM}
    assert {coding["code"] for coding in codings} <= _ATTRIBUTE_OPTION_COMBO_CODES
    assert not [note for note in report.notes if "category combo" in note.message]


@respx.mock
async def test_the_drawn_attribute_option_combo_is_reproducible(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    wire_version: str,
    tmp_path: Path,
) -> None:
    """Same instance state, same combo per response: the draw is seeded, not left to request order."""
    mock_system_info(wire_version)
    _mock_metadata()
    respx.get(f"{_HOST}/api/dataSets").mock(
        return_value=httpx.Response(200, json=_data_sets_payload(category_combo=_NON_DEFAULT_DATA_SET_COMBO))
    )
    await _run(tmp_path, per_target=3)
    first = {path.name: path.read_text(encoding="utf-8") for path in _load_files(tmp_path, _DATA_SET_UID)}
    report = await _run(tmp_path, per_target=3)
    second = {path.name: path.read_text(encoding="utf-8") for path in _load_files(tmp_path, _DATA_SET_UID)}
    assert first == second
    assert report.written_files == []


@respx.mock
async def test_a_data_set_on_the_default_category_combo_keeps_its_responses(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    wire_version: str,
    tmp_path: Path,
) -> None:
    """The default combo is the one a response already writes against, so nothing about it changes."""
    mock_system_info(wire_version)
    _mock_metadata()
    report = await _run(tmp_path, per_target=3)
    assert report.questionnaire_count == _QUESTIONNAIRE_COUNT
    assert len(list((tmp_path / "load").glob(f"{_DATA_SET_UID}-*.json"))) == 3
    assert not [note for note in report.notes if "category combo" in note.message]


@respx.mock
async def test_the_assignment_aware_pick_is_reproducible(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    wire_version: str,
    tmp_path: Path,
) -> None:
    """Same instance state, same corpus: the placement draws on a seed, not on the order DHIS2 answered in."""
    mock_system_info(wire_version)
    _mock_metadata()
    await _scaffold_project(tmp_path)
    first = tmp_path / "first"
    second = tmp_path / "second"
    for directory in (first, second):
        await service.generate_load_set(
            resolve_profile("probe"), load_project(tmp_path), per_target=12, output_directory=directory
        )
    respx.get(f"{_HOST}/api/programs").mock(
        return_value=httpx.Response(
            200, json=_programs_payload(organisation_units=(_UNPUBLISHED_UNIT, _PROGRAM_UNIT, _SHARED_UNIT))
        )
    )
    third = tmp_path / "third"
    await service.generate_load_set(
        resolve_profile("probe"), load_project(tmp_path), per_target=12, output_directory=third
    )
    picks = _subjects(first / "load", _PROGRAM_UID)
    assert picks == _subjects(second / "load", _PROGRAM_UID)
    assert picks == _subjects(third / "load", _PROGRAM_UID)


#: A tracker program whose whole capture surface the corpus covers: the registration form that mints
#: the enrollment identities, and the stage form whose events answer against those very identities.
_TRACKER_PROGRAM_UID = "IpHINAT79UW"
_TRACKER_STAGE_UID = "A03MvHHogjR"

_TRACKER_PROGRAMS_PAYLOAD: dict[str, object] = {
    "programs": [
        {
            "id": _TRACKER_PROGRAM_UID,
            "name": "Child Programme",
            "programType": "WITH_REGISTRATION",
            "trackedEntityType": {"id": "nEenWmSyUEp"},
            "organisationUnits": [{"id": _SHARED_UNIT}],
            "programTrackedEntityAttributes": [
                {
                    "mandatory": True,
                    "sortOrder": 1,
                    "trackedEntityAttribute": {"id": "Tea1aaaaaaa", "name": "First name", "valueType": "TEXT"},
                }
            ],
            "programStages": [
                {
                    "id": "A03MvHHogjR",
                    "programStageSections": [],
                    "programStageDataElements": [
                        {
                            "compulsory": True,
                            "dataElement": {"id": "a3kGcGDCuk6", "name": "Apgar Score", "valueType": "INTEGER"},
                        }
                    ],
                }
            ],
        }
    ]
}


async def _tracker_run(tmp_path: Path, per_target: int) -> service.LoadSetReport:
    """Scaffold a project holding one tracker program and generate a corpus over its whole surface."""
    respx.get(f"{_HOST}/api/dataSets").mock(return_value=httpx.Response(200, json={"dataSets": []}))
    respx.get(f"{_HOST}/api/programs").mock(return_value=httpx.Response(200, json=_TRACKER_PROGRAMS_PAYLOAD))
    respx.get(f"{_HOST}/api/optionSets").mock(return_value=httpx.Response(200, json=_OPTION_SETS_PAYLOAD))
    respx.get(f"{_HOST}/api/organisationUnits").mock(return_value=httpx.Response(200, json=_ORG_UNITS_PAYLOAD))
    options = InitOptions(
        ig_id="dhis2.fhir.load",
        canonical=_CANONICAL,
        name="Dhis2FhirLoad",
        title="Load IG",
        publisher="Example Org",
        tracker_program_ids=[_TRACKER_PROGRAM_UID],
    )
    await service.init_project(tmp_path, options)
    return await service.generate_load_set(resolve_profile("probe"), load_project(tmp_path), per_target=per_target)


def _documents(tmp_path: Path, target_uid: str) -> list[dict[str, Any]]:
    """One target's corpus documents, parsed, in file-name order."""
    return [json.loads(path.read_text(encoding="utf-8")) for path in _load_files(tmp_path, target_uid)]


def _minted_pair(document: dict[str, Any]) -> tuple[str, str]:
    """The tracked entity and enrollment UIDs one tracker response names."""
    enrollment = next(
        extension["valueIdentifier"]["value"]
        for extension in document["extension"]
        if extension["url"].endswith("d2-tracker-enrollment")
    )
    return (document["subject"]["identifier"]["value"], enrollment)


@respx.mock
async def test_a_tracker_program_contributes_registrations_and_stage_events(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    tmp_path: Path,
) -> None:
    """Every form kind is captured now, so a tracker program's whole surface lands in the corpus."""
    mock_system_info("v42")

    report = await _tracker_run(tmp_path, per_target=2)

    assert report.questionnaire_count == _QUESTIONNAIRE_COUNT
    assert len(_load_files(tmp_path, _TRACKER_PROGRAM_UID)) == 2
    assert len(_load_files(tmp_path, _TRACKER_STAGE_UID)) == 2
    assert not [note for note in report.notes if "no capture server accepts" in note.message]


@respx.mock
async def test_a_registration_response_states_the_enrollment_it_mints(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    tmp_path: Path,
) -> None:
    """A registration is the response that creates the enrollment, so it dates it and names the type."""
    mock_system_info("v42")

    await _tracker_run(tmp_path, per_target=1)

    registration = _documents(tmp_path, _TRACKER_PROGRAM_UID)[0]
    urls = [extension["url"] for extension in registration["extension"]]
    assert registration["meta"]["profile"] == [f"{_CANONICAL}/StructureDefinition/d2-tracker-registration-response"]
    assert f"{_CANONICAL}/StructureDefinition/d2-enrolled-at" in urls
    assert urls[-1] == f"{_CANONICAL}/StructureDefinition/d2-form-type"


@respx.mock
async def test_stage_events_answer_against_the_registrations_of_the_same_corpus(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    tmp_path: Path,
) -> None:
    """The corpus is internally consistent: every stage event names a pair a registration in it mints."""
    mock_system_info("v42")

    await _tracker_run(tmp_path, per_target=3)

    minted = {_minted_pair(document) for document in _documents(tmp_path, _TRACKER_PROGRAM_UID)}
    used = [_minted_pair(document) for document in _documents(tmp_path, _TRACKER_STAGE_UID)]
    assert len(minted) == 3
    assert set(used) == minted


@respx.mock
async def test_the_registration_identities_are_reproducible(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    tmp_path: Path,
) -> None:
    """Same instance state, same minted identities: the pair is seeded off the program and the ordinal."""
    mock_system_info("v42")

    await _tracker_run(tmp_path, per_target=2)
    first = _documents(tmp_path, _TRACKER_PROGRAM_UID)
    rerun = await service.generate_load_set(resolve_profile("probe"), load_project(tmp_path), per_target=2)
    second = _documents(tmp_path, _TRACKER_PROGRAM_UID)

    assert [_minted_pair(document) for document in first] == [_minted_pair(document) for document in second]
    assert rerun.written_files == []
