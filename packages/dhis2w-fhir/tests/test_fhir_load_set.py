"""Tests for the load-set target: a volume corpus of synthetic QuestionnaireResponse documents.

Where `generate examples` writes the one example per form an IG publishes, this writes as many as
a POST loop wants, straight to JSON, into a `load/` directory the target owns outright.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest
import respx
from dhis2w_core.profile import resolve_profile
from dhis2w_fhir import InitOptions, load_project, service

_HOST = "https://dhis2.example"
_CANONICAL = "http://example.org/fhir"
_ROOT_ORG_UNIT = "ImspTQPwCqd"

#: The two questionnaire targets every run here builds from: one data set, one event program.
_QUESTIONNAIRE_COUNT = 2

_DATA_SETS_PAYLOAD = {
    "dataSets": [
        {
            "id": "BfMAe6Itzgt",
            "name": "Child Health",
            "periodType": "Monthly",
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

_PROGRAMS_PAYLOAD = {
    "programs": [
        {
            "id": "VBqh0ynB2wv",
            "name": "Malaria case registration",
            "programType": "WITHOUT_REGISTRATION",
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

_ROOT_PAYLOAD = {"organisationUnits": [{"id": _ROOT_ORG_UNIT}]}


async def _scaffold_project(directory: Path) -> None:
    """Scaffold a project holding both questionnaire targets a load set is built from."""
    options = InitOptions(
        ig_id="dhis2.fhir.load",
        canonical=_CANONICAL,
        name="Dhis2FhirLoad",
        title="Load IG",
        publisher="Example Org",
        data_set_ids=["BfMAe6Itzgt"],
        event_program_ids=["VBqh0ynB2wv"],
    )
    await service.init_project(directory, options)


def _mock_metadata() -> None:
    """Mock every metadata endpoint one load-set run reads."""
    respx.get(f"{_HOST}/api/dataSets").mock(return_value=httpx.Response(200, json=_DATA_SETS_PAYLOAD))
    respx.get(f"{_HOST}/api/programs").mock(return_value=httpx.Response(200, json=_PROGRAMS_PAYLOAD))
    respx.get(f"{_HOST}/api/optionSets").mock(return_value=httpx.Response(200, json=_OPTION_SETS_PAYLOAD))
    respx.get(f"{_HOST}/api/organisationUnits").mock(return_value=httpx.Response(200, json=_ROOT_PAYLOAD))


async def _run(tmp_path: Path, per_target: int = 3) -> service.LoadSetReport:
    """Scaffold a project and generate one load set into it."""
    await _scaffold_project(tmp_path)
    return await service.generate_load_set(resolve_profile("probe"), load_project(tmp_path), per_target=per_target)


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
    assert "the instance has no level-1 organisation unit; no load set emitted" in report.notes
