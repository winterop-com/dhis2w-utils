"""Tests for the names and codes a substitute-posture run publishes in place of what DHIS2 holds.

`test_fhir_build_aborting.py` covers the refusal - the run that writes nothing when a selected
name carries '<'. This covers the other answer: publishing the name in wording the publisher
survives and the code with its spaces hyphenated, leaving DHIS2 untouched. The load-bearing test is
the parity one, which generates a whole guide off an instance whose names carry '<' everywhere a
name can sit and then runs the `d2w fhir check-artifacts` scan over every file the run wrote,
asserting it finds nothing; the code half is guarded by the emission tests at the foot of the file,
which read the published concepts, ConceptMaps, and identifier CodeSystems back off the disk.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import httpx
import pytest
import respx
from dhis2w_core.profile import resolve_profile
from dhis2w_fhir import HostileNamePosture, InitOptions, OptionIn, OptionSetIn, load_project, service
from dhis2w_fhir.hostile_names import HostileNameGate, HostileRewrite
from dhis2w_fhir.i18n import TranslationIn
from dhis2w_fhir.notes import GenerateNote, GenerateNoteCategory
from dhis2w_fhir.validation import build_aborting_name
from dhis2w_fhir.validation.artifacts import check_publishable_artifacts
from dhis2w_fhir.validation.substitution import first_control_character, substitute_build_aborting_text

_HOST = "https://dhis2.example"

#: Names shaped like the ones a national instance really carries, each rewritten the same way twice.
#: The entity spellings are the DHIS2 play instance's own: a name typed into a rich-text field is
#: stored as `&lt;`/`&gt;`, and a run that rewrote only the character would publish those to a reader
#: as an entity reference.
_REWRITES: list[tuple[str, str]] = [
    ("5 to < 15 years, Female", "5 to under 15 years, Female"),
    ("Male, <15y", "Male, under 15y"),
    ("<15y", "under 15y"),
    ("ENTO - IRS < 6 Months", "ENTO - IRS under 6 Months"),
    ("Mortality < 5 years by gender", "Mortality under 5 years by gender"),
    ("Age <= 5", "Age at most 5"),
    ("Mortality &lt; 5 years", "Mortality under 5 years"),
    ("Fixed, &lt;1y", "Fixed, under 1y"),
    ("&lt;1km", "under 1km"),
    ("&gt;5km", "over 5km"),
    ("Mortality > 5 years", "Mortality over 5 years"),
    ("Age &gt;= 5", "Age at least 5"),
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


def test_a_name_carrying_no_comparison_and_no_control_character_is_returned_byte_true() -> None:
    """Only a comparison and a control character are rewritten - everything else is published as DHIS2 states it."""
    for name in ("R&D bednets", "Child Health, Female", "Bo District", "Fixed 1y", "Two  spaces"):
        assert substitute_build_aborting_text(name) == name


@pytest.mark.parametrize(
    ("name", "published"),
    [
        ("Malaria\tcases", "Malaria cases"),
        ("Under\n5 years", "Under 5 years"),
        ("Fixed\rrate", "Fixed rate"),
        ("Malaria\x01cases", "Malaria cases"),
        ("A\x0b\x0cB", "A B"),
        ("\x01Leading", "Leading"),
        ("Trailing\x01", "Trailing"),
        ("Under \x01 5", "Under 5"),
        ("5 to\t< 15 years", "5 to under 15 years"),
    ],
)
def test_a_control_character_reads_as_the_space_it_stood_in(name: str, published: str) -> None:
    """A control character stands for no words, so the rewrite collapses it rather than spelling it out."""
    assert substitute_build_aborting_text(name) == published


@pytest.mark.parametrize("code_point", range(0x20))
def test_the_rewrite_leaves_no_control_character_behind(code_point: int) -> None:
    """The postcondition for the other half of the gate: whatever goes in, no C0 control comes out."""
    published = substitute_build_aborting_text(f"Malaria{chr(code_point)}cases")
    assert published == "Malaria cases"
    assert first_control_character(published) is None


def test_a_control_carrying_name_is_rewritten_by_the_gate_and_noted_as_one() -> None:
    """The note says which of the two rewrites the name took, rather than claiming a comparison it has none of."""
    gate = HostileNameGate(HostileNamePosture.SUBSTITUTE)
    notes: list[GenerateNote] = []
    screened = gate.screen([OptionSetIn(uid="Os1aaaaaaaa", name="Malaria\x01cases", options=[])], notes)

    assert screened[0].name == "Malaria cases"
    assert len(notes) == 1
    assert notes[0].category is GenerateNoteCategory.NAME_SUBSTITUTION
    assert "carries a control character the published guide cannot carry as it stands" in notes[0].message
    assert "'Malaria\\x01cases'" in notes[0].message


@pytest.mark.parametrize(
    ("less", "greater"),
    [("<1km", ">5km"), ("&lt;1km", "&gt;5km"), ("Age <= 5", "Age >= 5"), ("Age &lt;= 5", "Age &gt;= 5")],
)
def test_the_two_comparisons_are_rewritten_symmetrically(less: str, greater: str) -> None:
    """A registry reading "under 1km" beside "&gt;5km" states one fact in two vocabularies, one of them markup."""
    rewritten_less = substitute_build_aborting_text(less)
    rewritten_greater = substitute_build_aborting_text(greater)

    assert rewritten_less != less
    assert rewritten_greater != greater
    assert "<" not in rewritten_greater
    assert ">" not in rewritten_greater
    assert "&lt;" not in rewritten_less
    assert "&gt;" not in rewritten_greater


def test_a_name_translation_is_rewritten_with_the_name_it_translates() -> None:
    """A resource whose `title` and whose `_title` disagreed would state two names for one object."""
    gate = HostileNameGate(HostileNamePosture.SUBSTITUTE)
    option_set = OptionSetIn(
        uid="Os1aaaaaaaa",
        name="Mortality &lt; 5 years",
        translations=[
            TranslationIn(locale="en_GB", property="NAME", value="Mortality &lt; 5 years"),
            TranslationIn(locale="fr", property="DESCRIPTION", value="Mortalité &lt; 5 ans"),
        ],
        options=[
            OptionIn(
                uid="Op1aaaaaaaa",
                name="&gt;5km",
                translations=[TranslationIn(locale="fr", property="NAME", value="&gt;5km")],
            )
        ],
    )

    screened = gate.screen([option_set], [])

    assert screened[0].name == "Mortality under 5 years"
    assert screened[0].translations[0].value == "Mortality under 5 years"
    assert screened[0].options[0].name == "over 5km"
    assert screened[0].options[0].translations[0].value == "over 5km"


def test_a_description_translation_is_left_as_dhis2_states_it() -> None:
    """A DESCRIPTION lands on a `description` element rather than on a name, so nothing rewrites it."""
    gate = HostileNameGate(HostileNamePosture.SUBSTITUTE)
    option_set = OptionSetIn(
        uid="Os1aaaaaaaa",
        name="Mortality < 5 years",
        translations=[TranslationIn(locale="fr", property="DESCRIPTION", value="Mortalité < 5 ans")],
    )

    screened = gate.screen([option_set], [])

    assert screened[0].translations[0].value == "Mortalité < 5 ans"


def test_a_rewritten_name_keeps_the_dhis2_spelling_recoverable() -> None:
    """The translation no longer carries the instance's spelling, so `original_name` does."""
    gate = HostileNameGate(HostileNamePosture.SUBSTITUTE)
    option_set = OptionSetIn(
        uid="Os1aaaaaaaa",
        name="Mortality &lt; 5 years",
        translations=[TranslationIn(locale="en_GB", property="NAME", value="Mortality &lt; 5 years")],
        options=[OptionIn(uid="Op1aaaaaaaa", name="&gt;5km")],
    )

    screened = gate.screen([option_set], [])

    assert screened[0].original_name == "Mortality &lt; 5 years"
    assert screened[0].dhis2_name == "Mortality &lt; 5 years"
    assert screened[0].options[0].original_name == "&gt;5km"


def test_a_name_published_byte_true_states_no_original() -> None:
    """Nothing was rewritten, so there is nothing to recover and no property claiming otherwise."""
    screened = HostileNameGate(HostileNamePosture.SUBSTITUTE).screen(
        [OptionSetIn(uid="Os1aaaaaaaa", name="Child Health")], []
    )

    assert screened[0].original_name is None
    assert screened[0].dhis2_name is None


def test_a_code_the_guide_carries_cleanly_is_published_byte_true() -> None:
    """Only a space is rewritten in a code: a `<` still refuses, and everything else is left alone."""
    gate = HostileNameGate(HostileNamePosture.SUBSTITUTE)
    option_set = OptionSetIn(uid="Os1aaaaaaaa", name="Age < 5", code="AGE<5")
    screened = gate.screen([option_set], [])

    assert screened[0].name == "Age under 5"
    assert screened[0].code == "AGE<5"
    assert screened[0].original_code is None
    assert screened[0].dhis2_code == "AGE<5"


def test_a_space_in_a_code_becomes_a_hyphen() -> None:
    """The published code is the DHIS2 code with every space hyphenated, and the original rides along."""
    gate = HostileNameGate(HostileNamePosture.SUBSTITUTE)
    option_set = OptionSetIn(
        uid="Os1aaaaaaaa",
        name="Conditions",
        code="Set one",
        options=[OptionIn(uid="Op1aaaaaaaa", name="Pre eclampsia", code="Pre eclampsia")],
    )

    screened = gate.screen([option_set], [])

    assert screened[0].code == "Set-one"
    assert screened[0].original_code == "Set one"
    assert screened[0].options[0].code == "Pre-eclampsia"
    assert screened[0].options[0].dhis2_code == "Pre eclampsia"


def test_a_rewrite_colliding_with_a_literal_code_takes_an_ordinal() -> None:
    """`Pre eclampsia` beside a literal `Pre-eclampsia` cannot publish one code, so the rewrite is suffixed."""
    gate = HostileNameGate(HostileNamePosture.SUBSTITUTE)
    option_set = OptionSetIn(
        uid="Os1aaaaaaaa",
        name="Conditions",
        options=[
            OptionIn(uid="Op1aaaaaaaa", name="Spaced", code="Pre eclampsia"),
            OptionIn(uid="Op2aaaaaaaa", name="Literal", code="Pre-eclampsia"),
        ],
    )

    screened = gate.screen([option_set], [])

    assert [option.code for option in screened[0].options] == ["Pre-eclampsia-2", "Pre-eclampsia"]
    assert [option.dhis2_code for option in screened[0].options] == ["Pre eclampsia", "Pre-eclampsia"]


def test_the_assignment_does_not_depend_on_the_order_the_projections_arrive_in() -> None:
    """Same selection, same published codes - the ordinal is assigned in sorted order, not encounter order."""
    options = [
        OptionIn(uid="Op1aaaaaaaa", name="A", code="Pre eclampsia"),
        OptionIn(uid="Op2aaaaaaaa", name="B", code="Pre-eclampsia"),
        OptionIn(uid="Op3aaaaaaaa", name="C", code="Pre  eclampsia"),
    ]
    forwards = HostileNameGate(HostileNamePosture.SUBSTITUTE).screen(
        [OptionSetIn(uid="Os1aaaaaaaa", name="Conditions", options=options)], []
    )
    backwards = HostileNameGate(HostileNamePosture.SUBSTITUTE).screen(
        [OptionSetIn(uid="Os1aaaaaaaa", name="Conditions", options=list(reversed(options)))], []
    )

    assert {option.uid: option.code for option in forwards[0].options} == {
        option.uid: option.code for option in backwards[0].options
    }


def test_the_refuse_posture_leaves_every_code_byte_true() -> None:
    """A space is legal FHIR, so refusing rewrites nothing about it - the guide states what DHIS2 states."""
    option_set = OptionSetIn(
        uid="Os1aaaaaaaa",
        name="Conditions",
        options=[OptionIn(uid="Op1aaaaaaaa", name="Pre eclampsia", code="Pre eclampsia")],
    )

    for gate in (HostileNameGate(HostileNamePosture.REFUSE), HostileNameGate()):
        screened = gate.screen([option_set], [])
        assert screened[0].options[0].code == "Pre eclampsia"
        assert screened[0].options[0].original_code is None


def test_one_note_is_raised_per_distinct_code() -> None:
    """A rewritten code is provenance the notes report carries, once per DHIS2 code however many carry it."""
    gate = HostileNameGate(HostileNamePosture.SUBSTITUTE)
    notes: list[Any] = []
    shared = [
        OptionSetIn(
            uid=f"Os{index}aaaaaaa",
            name="Conditions",
            options=[OptionIn(uid=f"Op{index}aaaaaaa", name="Pre eclampsia", code="Pre eclampsia")],
        )
        for index in range(3)
    ]

    gate.screen(shared, notes)

    coded = [note for note in notes if note.category == GenerateNoteCategory.CODE_SUBSTITUTION]
    assert len(coded) == 1
    assert "Pre eclampsia" in coded[0].message
    assert "Pre-eclampsia" in coded[0].message
    assert coded[0].echoes_validate is False


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

    def confirmation(rewrites: list[HostileRewrite]) -> bool:
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

    A category option combo's name is both a cell's label and a data dictionary concept display, and
    a category combo's own name is the disaggregation the pages narrate - neither is a name the
    refusals read. This is the surface a national instance carried 738 of, which generated
    successfully and then aborted the publisher; it is what makes the parity assertion above worth
    something. The form name is deliberately clean here: it is the question's label wherever DHIS2
    states one, so the question gate reads it and a hostile one never reaches this path.
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
                        "formName": "Weight (kg)",
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


def _spaced_code_instance() -> dict[str, list[dict[str, Any]]]:
    """An instance whose option codes carry a space, beside the literal code one of them collides with.

    This is BUGS.md 107 as an instance: `Pre eclampsia` and `Preeclampsia` are distinct DHIS2 codes
    that the IG publisher's anchor slug renders as one anchor id, and `Pre-eclampsia` is the literal
    a rewrite of the first one lands on.
    """
    return {
        "dataSets": [],
        "programs": [],
        "trackedEntityTypes": [],
        "optionSets": [
            {
                "id": "OsSpc000001",
                "name": "Conditions",
                "code": "CONDITIONS",
                "options": [
                    {"id": "OpSpc000001", "name": "Pre eclampsia", "code": "Pre eclampsia", "sortOrder": 1},
                    {"id": "OpSpc000002", "name": "Pre-eclampsia", "code": "Pre-eclampsia", "sortOrder": 2},
                    {"id": "OpSpc000003", "name": "Preeclampsia", "code": "Preeclampsia", "sortOrder": 3},
                ],
            }
        ],
        "categories": [],
        "organisationUnits": [
            {"id": "OuSpc000001", "name": "Sierra Leone", "code": "SL", "level": 1, "path": "/OuSpc000001"}
        ],
        "programRules": [],
        "attributes": [],
    }


def _whitespace_code_instance() -> dict[str, list[dict[str, Any]]]:
    """An instance whose option codes carry the whitespace a real registry types into them.

    A doubled space and a trailing space are both what the play 2.43 instance really holds -
    "SS-Suspicious  malignancy", "QA Offic2er " - and neither is a valid R4 `code`. The option-set
    code beside them is the one whose spelling an identifier has to substitute.
    """
    return {
        "dataSets": [],
        "programs": [],
        "trackedEntityTypes": [],
        "optionSets": [
            {
                "id": "OsWsp000001",
                "name": "Distance (in km)",
                "code": "Distance (in km)",
                "options": [
                    {
                        "id": "OpWsp000001",
                        "name": "Suspicious malignancy",
                        "code": "SS-Suspicious  malignancy",
                        "sortOrder": 1,
                    },
                    {"id": "OpWsp000002", "name": "Quality officer", "code": "QA Offic2er ", "sortOrder": 2},
                ],
            }
        ],
        "categories": [],
        "organisationUnits": [
            {"id": "OuWsp000001", "name": "Sierra Leone", "code": "SL", "level": 1, "path": "/OuWsp000001"}
        ],
        "programRules": [],
        "attributes": [],
    }


async def _generate_option_sets(
    tmp_path: Path, instance: dict[str, list[dict[str, Any]]], *, code_source: str, gate: HostileNameGate
) -> Path:
    """Generate the option-set family off one instance and answer with the resources directory."""
    await _scaffold_project(tmp_path)
    config_path = tmp_path / "fhir.toml"
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(
            "[generate]\n", f'[generate]\nconcept_code_source = "{code_source}"\n', 1
        ),
        encoding="utf-8",
    )
    _mock_instance(instance)
    project = load_project(tmp_path)
    await service.generate_option_sets(resolve_profile("probe"), project, gate=gate)
    return project.resources_directory


async def _generate_spaced_codes(tmp_path: Path, *, code_source: str, gate: HostileNameGate) -> Path:
    """Generate the option-set family off the spaced-code instance and answer with the resources directory."""
    return await _generate_option_sets(tmp_path, _spaced_code_instance(), code_source=code_source, gate=gate)


def _read(directory: Path, name: str) -> dict[str, Any]:
    """Read one emitted resource by file name, from anywhere under the resources directory."""
    matches = sorted(directory.rglob(name))
    assert matches, f"{name} was not written under {directory}"
    return cast("dict[str, Any]", json.loads(matches[0].read_text(encoding="utf-8")))


def _concepts_by_code(document: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """One document's concepts keyed by the code it publishes them under."""
    return {concept["code"]: concept for concept in document.get("concept", [])}


def _property_value(concept: dict[str, Any], code: str) -> str | None:
    """The string value one concept carries under a named property, or None when it carries none."""
    for entry in concept.get("property", []):
        if entry.get("code") == code:
            return cast("str | None", entry.get("valueString") or entry.get("valueCode"))
    return None


@respx.mock
async def test_a_code_mode_concept_publishes_the_hyphenated_code_and_states_the_dhis2_one(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    tmp_path: Path,
) -> None:
    """The published vocabulary carries no space, and every rewritten concept says what DHIS2 holds."""
    mock_system_info("v42")
    directory = await _generate_spaced_codes(tmp_path, code_source="code", gate=_substituting_gate())

    concepts = _concepts_by_code(_read(directory, "CodeSystem-d2-os-OsSpc000001-cs.json"))

    assert set(concepts) == {"Pre-eclampsia-2", "Pre-eclampsia", "Preeclampsia"}
    assert _property_value(concepts["Pre-eclampsia-2"], "dhis2-code") == "Pre eclampsia"
    assert _property_value(concepts["Pre-eclampsia-2"], "dhis2-id") == "OpSpc000001"
    assert _property_value(concepts["Pre-eclampsia"], "dhis2-code") is None


@respx.mock
async def test_the_concept_map_states_the_published_code_and_keeps_the_uid_side_untouched(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    tmp_path: Path,
) -> None:
    """A map's own vocabulary is the published one, so its code target is the code the CodeSystem holds."""
    mock_system_info("v42")
    directory = await _generate_spaced_codes(tmp_path, code_source="code", gate=_substituting_gate())

    groups = _read(directory, "ConceptMap-d2-os-OsSpc000001-cm.json")["group"]
    by_target = {group["target"]: group for group in groups}
    uid_rows = {
        row["code"]: row["target"][0]["code"] for row in by_target["http://dhis2.org/fhir/id/option"]["element"]
    }
    code_rows = {
        row["code"]: row["target"][0]["code"] for row in by_target["http://dhis2.org/fhir/id/option-code"]["element"]
    }

    assert uid_rows["Pre-eclampsia-2"] == "OpSpc000001"
    assert code_rows["Pre-eclampsia-2"] == "Pre-eclampsia-2"
    assert " " not in "".join(code_rows.values())


@respx.mock
async def test_the_identifier_code_system_enumerates_the_published_codes_with_the_dhis2_one_beside_them(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    tmp_path: Path,
) -> None:
    """`d2-option-code-id-cs` is the namespace BUGS.md 107 collides in, and it now carries no space."""
    mock_system_info("v42")
    directory = await _generate_spaced_codes(tmp_path, code_source="code", gate=_substituting_gate())

    document = _read(directory, "CodeSystem-d2-option-code-id-cs.json")
    concepts = _concepts_by_code(document)

    assert set(concepts) == {"Pre-eclampsia-2", "Pre-eclampsia", "Preeclampsia"}
    assert _property_value(concepts["Pre-eclampsia-2"], "dhis2-code") == "Pre eclampsia"
    assert [entry["code"] for entry in document["property"]] == ["dhis2-code"]


@respx.mock
async def test_an_id_mode_run_publishes_uids_and_still_hyphenates_the_code_namespace(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    tmp_path: Path,
) -> None:
    """Under `concept_code_source = "id"` the concept code is a UID, and only the code namespace is rewritten."""
    mock_system_info("v42")
    directory = await _generate_spaced_codes(tmp_path, code_source="id", gate=_substituting_gate())

    set_concepts = _concepts_by_code(_read(directory, "CodeSystem-d2-os-OsSpc000001-cs.json"))
    identifier_concepts = _concepts_by_code(_read(directory, "CodeSystem-d2-option-code-id-cs.json"))

    assert set(set_concepts) == {"OpSpc000001", "OpSpc000002", "OpSpc000003"}
    assert _property_value(set_concepts["OpSpc000001"], "dhis2-code") == "Pre eclampsia"
    assert set(identifier_concepts) == {"Pre-eclampsia-2", "Pre-eclampsia", "Preeclampsia"}
    assert _property_value(identifier_concepts["Pre-eclampsia-2"], "dhis2-code") == "Pre eclampsia"


@respx.mock
async def test_the_refuse_posture_publishes_the_space_carrying_code_byte_true(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    tmp_path: Path,
) -> None:
    """Nothing about a space is refused, so refusing publishes exactly what the instance holds."""
    mock_system_info("v42")
    directory = await _generate_spaced_codes(
        tmp_path, code_source="code", gate=HostileNameGate(HostileNamePosture.REFUSE)
    )

    concepts = _concepts_by_code(_read(directory, "CodeSystem-d2-os-OsSpc000001-cs.json"))

    assert set(concepts) == {"Pre eclampsia", "Pre-eclampsia", "Preeclampsia"}
    assert _property_value(concepts["Pre eclampsia"], "dhis2-code") is None


def _extension_value(document: dict[str, Any], url: str) -> str | None:
    """The `valueString` one resource carries under a named extension URL, or None when it carries none."""
    for entry in document.get("extension", []):
        if entry.get("url") == url:
            return cast("str | None", entry.get("valueString"))
    return None


@respx.mock
async def test_a_whitespace_carrying_code_reaches_the_dhis2_code_property_verbatim(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    tmp_path: Path,
) -> None:
    """`dhis2-code` is a property value, not an identifier - a doubled or trailing space is legal in it.

    The UID never stands in for a code the instance really holds: a reader searching DHIS2 for
    "SS-Suspicious  malignancy" needs that string, spaces and all, not the UID of the option that
    carries it.
    """
    mock_system_info("v42")
    directory = await _generate_option_sets(
        tmp_path, _whitespace_code_instance(), code_source="id", gate=_substituting_gate()
    )

    concepts = _concepts_by_code(_read(directory, "CodeSystem-d2-os-OsWsp000001-cs.json"))

    assert _property_value(concepts["OpWsp000001"], "dhis2-code") == "SS-Suspicious  malignancy"
    assert _property_value(concepts["OpWsp000002"], "dhis2-code") == "QA Offic2er "


@respx.mock
async def test_the_option_code_target_keeps_the_substituted_spelling_beside_the_verbatim_property(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    tmp_path: Path,
) -> None:
    """The documented pair: the property carries the instance's spelling, the map target the published one."""
    mock_system_info("v42")
    directory = await _generate_option_sets(
        tmp_path, _whitespace_code_instance(), code_source="id", gate=_substituting_gate()
    )

    concepts = _concepts_by_code(_read(directory, "CodeSystem-d2-os-OsWsp000001-cs.json"))
    groups = _read(directory, "ConceptMap-d2-os-OsWsp000001-cm.json")["group"]
    by_target = {group["target"]: group for group in groups}
    code_rows = {
        row["code"]: row["target"][0]["code"] for row in by_target["http://dhis2.org/fhir/id/option-code"]["element"]
    }

    assert code_rows["OpWsp000001"] == "SS-Suspicious--malignancy"
    assert code_rows["OpWsp000002"] == "QA-Offic2er-"
    assert _property_value(concepts["OpWsp000001"], "dhis2-code") == "SS-Suspicious  malignancy"


@respx.mock
async def test_an_option_with_no_dhis2_code_still_states_its_uid(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    tmp_path: Path,
) -> None:
    """The UID stands in only where DHIS2 holds no code at all - a fact about the object, not its spelling."""
    mock_system_info("v42")
    instance = _whitespace_code_instance()
    instance["optionSets"][0]["options"][0].pop("code")
    directory = await _generate_option_sets(tmp_path, instance, code_source="id", gate=_substituting_gate())

    concepts = _concepts_by_code(_read(directory, "CodeSystem-d2-os-OsWsp000001-cs.json"))

    assert _property_value(concepts["OpWsp000001"], "dhis2-code") == "OpWsp000001"


@respx.mock
async def test_the_option_set_code_identifier_states_the_dhis2_spelling_as_an_extension(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    tmp_path: Path,
) -> None:
    """The `option-set-code` identifier is substituted so the guide can resolve it; the original rides beside it."""
    mock_system_info("v42")
    directory = await _generate_option_sets(
        tmp_path, _whitespace_code_instance(), code_source="id", gate=_substituting_gate()
    )

    code_system = _read(directory, "CodeSystem-d2-os-OsWsp000001-cs.json")
    value_set = _read(directory, "ValueSet-d2-os-OsWsp000001-vs.json")
    identifiers = {entry["system"]: entry["value"] for entry in code_system["identifier"]}

    assert identifiers["http://dhis2.org/fhir/id/option-set-code"] == "Distance-(in-km)"
    assert _extension_value(code_system, "http://dhis2.org/fhir/property/dhis2-code") == "Distance (in km)"
    assert _extension_value(value_set, "http://dhis2.org/fhir/property/dhis2-code") == "Distance (in km)"


@respx.mock
async def test_a_rewritten_display_states_the_dhis2_name_as_a_concept_property(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    tmp_path: Path,
) -> None:
    """The twin of `dhis2-code`: what the concept displays is the rewrite, what DHIS2 holds is one property away."""
    mock_system_info("v42")
    instance = _whitespace_code_instance()
    instance["optionSets"][0]["name"] = "Distance &lt; 1km"
    instance["optionSets"][0]["options"][0]["name"] = "&gt;5km"
    directory = await _generate_option_sets(tmp_path, instance, code_source="id", gate=_substituting_gate())

    code_system = _read(directory, "CodeSystem-d2-os-OsWsp000001-cs.json")
    concepts = _concepts_by_code(code_system)

    assert code_system["title"] == "Distance under 1km"
    assert _extension_value(code_system, "http://dhis2.org/fhir/property/dhis2-name") == "Distance &lt; 1km"
    assert concepts["OpWsp000001"]["display"] == "over 5km"
    assert _property_value(concepts["OpWsp000001"], "dhis2-name") == "&gt;5km"
    assert {entry["code"] for entry in code_system["property"]} == {"dhis2-code", "dhis2-name"}
