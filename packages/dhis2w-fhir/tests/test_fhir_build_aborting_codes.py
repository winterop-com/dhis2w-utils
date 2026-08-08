"""Tests for the generate-time refusal of DHIS2 codes the IG publisher's own build cannot survive.

A DHIS2 code becomes an identifier value on the emitted resources, and the publisher writes an
identifier value into a table cell unescaped before strict-parsing the page. `d2w fhir validate`
already reports a `<` there as an error; these cover the gate that stops `d2w fhir generate` from
writing an hour of build input the publisher will abort on.
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
from dhis2w_fhir.validation import build_aborting_code

_HOST = "https://dhis2.example"

#: The code that aborted a 55-minute build on a real instance: the '<' opens a tag in the cell.
_ABORTING_CODE = "ENTO - IRS < 6 Months"


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
    for resource in ("optionSets", "categories", "organisationUnits", "dataSets", "programs"):
        respx.get(f"{_HOST}/api/{resource}").mock(return_value=httpx.Response(200, json={resource: []}))
    respx.get(f"{_HOST}/api/attributes").mock(return_value=httpx.Response(200, json={"attributes": []}))


def _mock(resource: str, *items: dict[str, Any]) -> None:
    """Answer one metadata endpoint with the given objects."""
    respx.get(f"{_HOST}/api/{resource}").mock(return_value=httpx.Response(200, json={resource: list(items)}))


def _option_set(code: str) -> dict[str, Any]:
    """One DHIS2 option set carrying the given code."""
    return {"id": "Os1aaaaaaaa", "name": "Bednet distribution", "code": code, "options": []}


def _category(code: str) -> dict[str, Any]:
    """One DHIS2 category carrying the given code."""
    return {"id": "Ca1aaaaaaaa", "name": "Sex", "code": code, "categoryOptions": []}


def _organisation_unit(code: str) -> dict[str, Any]:
    """One DHIS2 organisation unit carrying the given code."""
    return {"id": "Ou1aaaaaaaa", "name": "Sierra Leone", "code": code, "level": 1, "path": "/Ou1aaaaaaaa"}


def _data_set(code: str) -> dict[str, Any]:
    """One DHIS2 data set carrying the given code."""
    return {"id": "Ds1aaaaaaaa", "name": "Child Health", "code": code, "periodType": "Monthly"}


def _event_program(code: str) -> dict[str, Any]:
    """One DHIS2 event program carrying the given code."""
    return {
        "id": "Pr1aaaaaaaa",
        "name": "Malaria case registration",
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
