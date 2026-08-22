"""Tests for rewriting the DHIS2 names the IG publisher's own build cannot survive.

`test_fhir_build_aborting.py` covers the refusal - the run that writes nothing when a selected
name carries '<'. This covers the other answer: publishing the name in wording the publisher
survives, leaving DHIS2 untouched. The load-bearing test is the parity one, which generates a whole
guide off an instance whose names carry '<' everywhere a name can sit and then runs the
`d2w fhir check-artifacts` scan over every file the run wrote, asserting it finds nothing.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from dhis2w_core.profile import resolve_profile
from dhis2w_fhir import HostileNamePosture, InitOptions, OptionSetIn, load_project, service
from dhis2w_fhir.hostile_names import HostileNameGate, HostileNameRewrite
from dhis2w_fhir.notes import GenerateNoteCategory
from dhis2w_fhir.validation import build_aborting_name
from dhis2w_fhir.validation.artifacts import check_publishable_artifacts
from dhis2w_fhir.validation.substitution import substitute_build_aborting_text

_HOST = "https://dhis2.example"

#: Names shaped like the ones a national instance really carries, each rewritten the same way twice.
_REWRITES: list[tuple[str, str]] = [
    ("5 to < 15 years, Female", "5 to under 15 years, Female"),
    ("Male, <15y", "Male, under 15y"),
    ("<15y", "under 15y"),
    ("ENTO - IRS < 6 Months", "ENTO - IRS under 6 Months"),
    ("Mortality < 5 years by gender", "Mortality under 5 years by gender"),
    ("Age <= 5", "Age at most 5"),
]


def test_the_rewrite_reads_as_the_words_the_character_stands_for() -> None:
    """A rewritten age band is a sentence, not an escape: "5 to < 15 years" becomes "5 to under 15 years"."""
    assert [substitute_build_aborting_text(original) for original, _ in _REWRITES] == [
        rewritten for _, rewritten in _REWRITES
    ]


@pytest.mark.parametrize(
    "name",
    [
        *(original for original, _ in _REWRITES),
        "<",
        "<<",
        "a<b<c",
        "Trailing <",
        " < ",
        "Mortality > 5 years",
        "R&D bednets",
        "Child Health",
        "",
    ],
)
def test_a_rewritten_name_always_passes_the_build_gate(name: str) -> None:
    """The postcondition the whole feature rests on: whatever goes in, no '<' comes out."""
    assert build_aborting_name(substitute_build_aborting_text(name)) is False


def test_a_name_the_build_survives_is_returned_byte_true() -> None:
    """Only a name the publisher aborts on is touched - everything else is published as DHIS2 states it."""
    for name in ("Mortality > 5 years", "R&D bednets", "Child Health, Female"):
        assert substitute_build_aborting_text(name) == name


def test_a_code_is_never_rewritten() -> None:
    """A DHIS2 code is an identifier a consumer joins on, so the gate reads names and nothing else."""
    gate = HostileNameGate(HostileNamePosture.SUBSTITUTE)
    option_set = OptionSetIn(uid="Os1aaaaaaaa", name="Age < 5", code="AGE<5")
    screened = gate.screen([option_set], [])

    assert screened[0].name == "Age under 5"
    assert screened[0].code == "AGE<5"


def test_a_run_with_no_answer_rewrites_nothing() -> None:
    """A gate nobody answered leaves every name as DHIS2 states it, which is what the refusal then acts on."""
    gate = HostileNameGate()
    option_set = OptionSetIn(uid="Os1aaaaaaaa", name="Age < 5")

    assert gate.screen([option_set], [])[0].name == "Age < 5"


def test_one_note_is_raised_per_distinct_name() -> None:
    """A name three objects share is one note, because the reader is being told about the name."""
    gate = HostileNameGate(HostileNamePosture.SUBSTITUTE)
    notes: list[Any] = []
    shared = [OptionSetIn(uid=f"Os{index}aaaaaaa", name="Age < 5") for index in range(3)]

    gate.screen(shared, notes)

    assert len(notes) == 1
    assert notes[0].category == GenerateNoteCategory.NAME_SUBSTITUTION
    assert "Age < 5" in notes[0].message
    assert "Age under 5" in notes[0].message


def test_the_answer_is_asked_once_for_the_whole_run() -> None:
    """A full generate screens six projections; a person answers one question, not six."""
    asked: list[int] = []

    def confirmation(rewrites: list[HostileNameRewrite]) -> bool:
        """Count the question and answer yes."""
        asked.append(len(rewrites))
        return True

    gate = HostileNameGate(None, confirmation=confirmation)
    for index in range(3):
        gate.screen([OptionSetIn(uid=f"Os{index}aaaaaaa", name=f"Age < {index}")], [])

    assert len(asked) == 1


async def _scaffold_project(directory: Path) -> None:
    """Scaffold a project that publishes every kind and reads no data values."""
    await service.init_project(
        directory,
        InitOptions(
            ig_id="dhis2.fhir.names",
            canonical="http://example.org/fhir",
            name="Dhis2FhirNames",
            title="Names IG",
            publisher="Names Org",
        ),
    )
    config_path = directory / "fhir.toml"
    config_path.write_text(
        f"{config_path.read_text(encoding='utf-8')}\n[generate.examples]\nper_target = 0\n",
        encoding="utf-8",
    )


#: The category option combo grid one disaggregated question splits into - the surface a national
#: instance carried 738 build-aborting strings on, because every cell name reaches both the
#: Questionnaire's child item text and the data dictionary concept's display.
def _category_combo() -> dict[str, Any]:
    """One DHIS2 category combo whose cells are named the way real age bands are named."""
    return {
        "id": "CcHos000001",
        "name": "Age < 5 and sex",
        "code": "AGE_SEX",
        "categories": [
            {"id": "CaHos000001", "categoryOptions": [{"id": "CoHos000001"}, {"id": "CoHos000002"}]},
        ],
        "categoryOptionCombos": [
            {
                "id": "CocHos00001",
                "name": "5 to < 15 years, Female",
                "code": "F_5_15",
                "categoryOptions": [{"id": "CoHos000001"}],
            },
            {
                "id": "CocHos00002",
                "name": "Male, <15y",
                "code": "M_15",
                "categoryOptions": [{"id": "CoHos000002"}],
            },
        ],
    }


def _hostile_instance() -> dict[str, list[dict[str, Any]]]:
    """One instance carrying a build-aborting name on every surface a generate run publishes.

    Object titles, question labels, form names, option displays, category members, the cells of a
    disaggregation, and an organisation unit - one of each, so a scan of the emitted guide covers
    every position the artifact check reads rather than only the ones a gate already refuses.
    """
    return {
        "dataSets": [
            {
                "id": "DsHos000001",
                "name": "Child care < 5",
                "code": "CHILD_CARE",
                "periodType": "Monthly",
                "dataSetElements": [
                    {
                        "dataElement": {
                            "id": "DeHos000001",
                            "name": "Weight < 5kg",
                            "formName": "Weight, <5kg",
                            "valueType": "NUMBER",
                            "categoryCombo": _category_combo(),
                        }
                    },
                    {
                        "dataElement": {
                            "id": "DeHos000002",
                            "name": "Bednet given",
                            "valueType": "TEXT",
                            "optionSet": {"id": "OsHos000001"},
                        }
                    },
                ],
            }
        ],
        "programs": [
            {
                "id": "PrHos000001",
                "name": "Supervision < monthly",
                "code": "SUPERVISION",
                "programType": "WITHOUT_REGISTRATION",
                "programStages": [
                    {
                        "id": "PsHos000001",
                        "name": "Visit < 1h",
                        "programStageDataElements": [
                            {"dataElement": {"id": "DeHos000003", "name": "Finding < 5", "valueType": "TEXT"}}
                        ],
                    }
                ],
            },
            {
                "id": "PrHos000002",
                "name": "Child programme < 5",
                "code": "CHILD_PROGRAMME",
                "programType": "WITH_REGISTRATION",
                "trackedEntityType": {"id": "TtHos000001"},
                "programTrackedEntityAttributes": [
                    {
                        "trackedEntityAttribute": {
                            "id": "TaHos000001",
                            "name": "Age < 5 at enrolment",
                            "valueType": "TEXT",
                        }
                    }
                ],
                "programStages": [
                    {
                        "id": "PsHos000002",
                        "name": "Birth < term",
                        "code": "BIRTH",
                        "programStageDataElements": [
                            {
                                "dataElement": {
                                    "id": "DeHos000004",
                                    "name": "Birth weight < 2.5kg",
                                    "valueType": "NUMBER",
                                }
                            }
                        ],
                    }
                ],
            },
        ],
        "trackedEntityTypes": [
            {
                "id": "TtHos000001",
                "name": "Person < 18",
                "code": "PERSON",
                "trackedEntityTypeAttributes": [
                    {"trackedEntityAttribute": {"id": "TaHos000002", "name": "Family name", "valueType": "TEXT"}}
                ],
            }
        ],
        "optionSets": [
            {
                "id": "OsHos000001",
                "name": "Bednet age < 5",
                "code": "BEDNETS",
                "options": [{"id": "OpHos000001", "name": "Any bednet, <15y", "code": "ANY"}],
            }
        ],
        "categories": [
            {
                "id": "CaHos000001",
                "name": "Age < 5 band",
                "code": "AGE_BAND",
                "categoryOptions": [
                    {"id": "CoHos000001", "name": "5 to < 15 years, Female", "code": "F_5_15"},
                    {"id": "CoHos000002", "name": "Male, <15y", "code": "M_15"},
                ],
            }
        ],
        "organisationUnits": [
            {"id": "OuHos000001", "name": "Sierra Leone < north", "code": "SL", "level": 1, "path": "/OuHos000001"}
        ],
        "programRules": [],
        "attributes": [],
    }


def _unrefused_instance() -> dict[str, list[dict[str, Any]]]:
    """An instance whose build-aborting names sit only where no emit-site gate reads them.

    A data element's DHIS2 form name is the question's label, and a category option combo's name is
    both a cell's label and a data dictionary concept display - and neither is a name the four
    refusals read. This is the surface a national instance carried 738 of, which generated
    successfully and then aborted the publisher; it is what makes the parity assertion above worth
    something.
    """
    instance = _hostile_instance()
    instance["dataSets"] = [
        {
            "id": "DsUnr000001",
            "name": "Child care",
            "code": "CHILD_CARE",
            "periodType": "Monthly",
            "dataSetElements": [
                {
                    "dataElement": {
                        "id": "DeUnr000001",
                        "name": "Weight",
                        "formName": "Weight, <5kg",
                        "valueType": "NUMBER",
                        "categoryCombo": _category_combo(),
                    }
                }
            ],
        }
    ]
    instance["programs"] = []
    instance["trackedEntityTypes"] = []
    instance["optionSets"] = []
    instance["categories"] = [
        {
            "id": "CaHos000001",
            "name": "Age band",
            "code": "AGE_BAND",
            "categoryOptions": [
                {"id": "CoHos000001", "code": "F_5_15", "name": "5 to 14 years, Female"},
                {"id": "CoHos000002", "code": "M_15", "name": "Male, under 15y"},
            ],
        }
    ]
    instance["organisationUnits"] = [
        {"id": "OuHos000001", "name": "Sierra Leone", "code": "SL", "level": 1, "path": "/OuHos000001"}
    ]
    return instance


def _mock_instance(instance: dict[str, list[dict[str, Any]]]) -> None:
    """Answer every metadata endpoint a generate run reads with the given instance."""
    for resource, items in instance.items():
        respx.get(f"{_HOST}/api/{resource}").mock(return_value=httpx.Response(200, json={resource: items}))


def _substituting_gate() -> HostileNameGate:
    """The gate `--substitute-hostile-names` builds: rewrite, and never ask."""
    return HostileNameGate(HostileNamePosture.SUBSTITUTE)


@respx.mock
async def test_a_substituted_run_publishes_nothing_the_artifact_check_refuses(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    tmp_path: Path,
) -> None:
    """The parity that matters: generate the whole guide, then scan every file it wrote.

    The scan is `d2w fhir check-artifacts` itself - the same predicates, over `ig/input/fsh`,
    `ig/input/resources`, and `ig/fsh-generated` - so a name that escaped the rewrite anywhere in
    the emission is a finding here, whichever target published it.
    """
    mock_system_info("v42")
    await _scaffold_project(tmp_path)
    _mock_instance(_hostile_instance())
    project = load_project(tmp_path)

    await service.generate_full(resolve_profile("probe"), project, gate=_substituting_gate())

    report = check_publishable_artifacts(project)
    assert report.file_count > 0
    assert report.findings == []


@respx.mock
async def test_the_rewritten_names_reach_the_published_files(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    tmp_path: Path,
) -> None:
    """The guide states the rewritten wording, so the check passing is not the run publishing nothing."""
    mock_system_info("v42")
    await _scaffold_project(tmp_path)
    _mock_instance(_hostile_instance())
    project = load_project(tmp_path)

    await service.generate_full(resolve_profile("probe"), project, gate=_substituting_gate())

    published = "\n".join(
        path.read_text(encoding="utf-8")
        for directory in (project.fsh_directory, project.resources_directory)
        for path in directory.rglob("*")
        if path.is_file()
    )
    assert "5 to under 15 years, Female" in published
    assert "Male, under 15y" in published
    assert "Weight, under 5kg" in published


@respx.mock
async def test_the_run_notes_every_name_the_guide_states_differently(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    tmp_path: Path,
) -> None:
    """A rewrite is provenance: the notes report says which DHIS2 name the guide does not repeat."""
    mock_system_info("v42")
    await _scaffold_project(tmp_path)
    _mock_instance(_hostile_instance())

    report = await service.generate_full(resolve_profile("probe"), load_project(tmp_path), gate=_substituting_gate())

    distinct = report.with_distinct_notes()
    notes = [
        note
        for field_name in type(distinct).model_fields
        for note in getattr(distinct, field_name).notes
        if note.category == GenerateNoteCategory.NAME_SUBSTITUTION
    ]
    assert notes
    assert any("5 to < 15 years, Female" in note.message for note in notes)
    assert all(note.echoes_validate is False for note in notes)


@respx.mock
async def test_the_same_instance_still_refuses_under_the_refuse_posture(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    tmp_path: Path,
) -> None:
    """Refusing is the other answer to the same question, and it is unchanged by this feature."""
    mock_system_info("v42")
    await _scaffold_project(tmp_path)
    _mock_instance(_hostile_instance())

    with pytest.raises(service.BuildAbortingNameError):
        await service.generate_full(
            resolve_profile("probe"), load_project(tmp_path), gate=HostileNameGate(HostileNamePosture.REFUSE)
        )

    assert not list((tmp_path / "ig" / "input" / "resources").rglob("*.json"))


@respx.mock
async def test_a_build_aborting_code_refuses_the_run_however_the_names_are_answered(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    tmp_path: Path,
) -> None:
    """A code is an identifier, so no answer about names lets one carrying '<' reach a guide."""
    mock_system_info("v42")
    await _scaffold_project(tmp_path)
    instance = _hostile_instance()
    instance["optionSets"][0]["code"] = "BEDNETS < 5"
    _mock_instance(instance)

    with pytest.raises(service.BuildAbortingCodeError) as raised:
        await service.generate_full(resolve_profile("probe"), load_project(tmp_path), gate=_substituting_gate())

    assert "BEDNETS < 5" in str(raised.value)


@respx.mock
async def test_the_names_no_gate_reads_reach_the_disk_when_nothing_is_rewritten(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    tmp_path: Path,
) -> None:
    """The hole this feature answers, stated as a test: a run that refuses nothing still writes them.

    A form name and a category option combo name carry '<' past every emit-site refusal, so the run
    succeeds and the guide it wrote is what the publisher dies on hours later.
    """
    mock_system_info("v42")
    await _scaffold_project(tmp_path)
    _mock_instance(_unrefused_instance())
    project = load_project(tmp_path)

    await service.generate_full(resolve_profile("probe"), project, gate=HostileNameGate())

    report = check_publishable_artifacts(project)
    assert report.findings
    assert {finding.kind for finding in report.findings} == {"name"}


@respx.mock
async def test_the_same_names_are_rewritten_when_the_run_is_answered_with_yes(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    tmp_path: Path,
) -> None:
    """The other half of the hole: substitution closes what no refusal ever reached."""
    mock_system_info("v42")
    await _scaffold_project(tmp_path)
    _mock_instance(_unrefused_instance())
    project = load_project(tmp_path)

    await service.generate_full(resolve_profile("probe"), project, gate=_substituting_gate())

    assert check_publishable_artifacts(project).findings == []


@respx.mock
async def test_a_named_target_rewrites_what_the_full_run_rewrites(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    tmp_path: Path,
) -> None:
    """One target alone reads the same gate, so `generate questionnaires` publishes what a full run does."""
    mock_system_info("v42")
    await _scaffold_project(tmp_path)
    _mock_instance(_hostile_instance())
    project = load_project(tmp_path)

    await service.generate_questionnaires(resolve_profile("probe"), project, gate=_substituting_gate())

    report = check_publishable_artifacts(project)
    assert report.findings == []
