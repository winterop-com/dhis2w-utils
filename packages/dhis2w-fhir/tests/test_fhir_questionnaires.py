"""Tests for the questionnaire target: FSH emission, support terminology, and the service safeguards."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import httpx
import pytest
import respx
from dhis2w_cli.main import build_app
from dhis2w_core.profile import resolve_profile
from dhis2w_fhir import (
    GenerateConfig,
    InitOptions,
    NamingConfig,
    UnsupportedProgramError,
    build_questionnaire_artifacts,
    load_project,
    service,
)
from dhis2w_fhir.resources.questionnaires.schemas import (
    CategoryComboIn,
    CategoryOptionComboIn,
    QuestionnaireItemIn,
    QuestionnaireSectionIn,
    QuestionnaireSourceIn,
    TargetSelection,
)
from typer.testing import CliRunner

_HOST = "https://dhis2.example"
_CANONICAL = "http://example.org/fhir"

_DEFAULT_COMBO = CategoryComboIn(uid="bjDvmb4bfuf", name="default", is_default=True)
_AGE_COMBO = CategoryComboIn(
    uid="CcAaBbCcDdE",
    name="EPI/nutrition age",
    is_default=False,
    option_combos=[
        CategoryOptionComboIn(uid="Coc1aaaaaaa", name="<1y", code="U1"),
        CategoryOptionComboIn(uid="Coc2aaaaaaa", name=">1y"),
    ],
)

_BCG = QuestionnaireItemIn(
    uid="De1aaaaaaaa",
    name="BCG doses given",
    form_name="BCG",
    value_type="INTEGER_ZERO_OR_POSITIVE",
    category_combo=_DEFAULT_COMBO,
)
_MEASLES = QuestionnaireItemIn(
    uid="De2aaaaaaaa",
    name="Measles doses given",
    value_type="INTEGER",
    category_combo=_AGE_COMBO,
)
_GENDER = QuestionnaireItemIn(uid="De3aaaaaaaa", name="Gender", value_type="TEXT", option_set_uid="Os1aaaaaaaa")

_DATA_SET = QuestionnaireSourceIn(
    uid="BfMAe6Itzgt",
    name="Child Health",
    code="DS_359711",
    kind="aggregate",
    sections=[
        QuestionnaireSectionIn(uid="Sec1aaaaaaa", name="Immunization", items=[_BCG, _MEASLES]),
        QuestionnaireSectionIn(uid="Sec2aaaaaaa", name="Demographics", items=[_GENDER]),
    ],
)

_EVENT_PROGRAM = QuestionnaireSourceIn(
    uid="VBqh0ynB2wv",
    name="Malaria case registration",
    kind="event",
    flat_items=[
        QuestionnaireItemIn(
            uid="qrur9Dvnyt5",
            name="Age in years",
            form_name="Age (years)",
            value_type="INTEGER",
            compulsory=True,
            category_combo=_DEFAULT_COMBO,
        )
    ],
)

_DATA_SETS_PAYLOAD = {
    "dataSets": [
        {
            "id": "BfMAe6Itzgt",
            "name": "Child Health",
            "code": "DS_359711",
            "sections": [
                {"id": "Sec1aaaaaaa", "name": "Immunization", "dataElements": [{"id": "De1aaaaaaaa"}]},
                {"id": "Sec2aaaaaaa", "name": "Demographics", "dataElements": [{"id": "De3aaaaaaaa"}]},
            ],
            "dataSetElements": [
                {
                    "dataElement": {
                        "id": "De1aaaaaaaa",
                        "name": "BCG doses given",
                        "formName": "BCG",
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

_EVENT_PROGRAMS_PAYLOAD = {
    "programs": [
        {
            "id": "VBqh0ynB2wv",
            "name": "Malaria case registration",
            "programType": "WITHOUT_REGISTRATION",
            "programStages": [
                {
                    "id": "pTo4uMt3xur",
                    "name": "Malaria case registration",
                    "programStageSections": [],
                    "programStageDataElements": [
                        {
                            "compulsory": True,
                            "dataElement": {
                                "id": "qrur9Dvnyt5",
                                "name": "Age in years",
                                "formName": "Age (years)",
                                "valueType": "INTEGER",
                                "categoryCombo": {"id": "bjDvmb4bfuf", "name": "default", "isDefault": True},
                            },
                        }
                    ],
                }
            ],
        }
    ]
}

_runner = CliRunner()


def _artifacts(
    sources: list[QuestionnaireSourceIn], config: GenerateConfig | None = None, *, experimental: bool = True
) -> dict[str, str]:
    """Build the questionnaire artifacts and index them by relative path."""
    build = build_questionnaire_artifacts(sources, config or GenerateConfig(), _CANONICAL, experimental=experimental)
    return {artifact.relative_path: artifact.content for artifact in build.artifacts}


def test_questionnaire_artifacts_derive_experimental_from_the_ig_status() -> None:
    """An active IG publishes its questionnaires and their support terminology as non-experimental."""
    active = _artifacts([_DATA_SET], experimental=False)
    assert "* experimental = false" in active["questionnaires/BfMAe6Itzgt.fsh"]
    assert active["questionnaires/data-elements.fsh"].count("* ^experimental = false") == 2
    assert active["questionnaires/category-option-combos.fsh"].count("* ^experimental = false") == 2


def test_data_set_questionnaire_identity() -> None:
    """A data set becomes a definitional Questionnaire keyed by its bare UID, with both DHIS2 identifiers."""
    content = _artifacts([_DATA_SET])["questionnaires/BfMAe6Itzgt.fsh"]
    assert "Instance: Questionnaire-BfMAe6Itzgt" in content
    assert "InstanceOf: Questionnaire" in content
    assert "Usage: #definition" in content
    assert '* id = "BfMAe6Itzgt"' in content
    assert '* url = "http://example.org/fhir/Questionnaire/BfMAe6Itzgt"' in content
    assert '* identifier[+].system = $DHIS2-DS\n* identifier[=].value = "BfMAe6Itzgt"' in content
    assert '* identifier[+].system = $DHIS2-DS-CODE\n* identifier[=].value = "DS_359711"' in content
    assert '* name = "D2DS_BfMAe6Itzgt"' in content
    assert '* title = "Child Health"' in content
    assert "* status = #active" in content
    assert "* experimental = true" in content
    assert "* subjectType = #Location" in content


def test_event_program_questionnaire_identity() -> None:
    """An event program takes the program identifier systems and the PR naming token."""
    content = _artifacts([_EVENT_PROGRAM])["questionnaires/VBqh0ynB2wv.fsh"]
    assert "Instance: Questionnaire-VBqh0ynB2wv" in content
    assert "* identifier[+].system = $DHIS2-PROGRAM" in content
    assert "* identifier[+].system = $DHIS2-PROGRAM-CODE" in content
    assert '* name = "D2PR_VBqh0ynB2wv"' in content
    assert '* identifier[=].value = "VBqh0ynB2wv"' in content


def test_form_type_is_carried_by_extension_and_code() -> None:
    """Both kinds state where they came from twice: the D2FormType extension and Questionnaire.code."""
    artifacts = _artifacts([_DATA_SET, _EVENT_PROGRAM])
    aggregate = artifacts["questionnaires/BfMAe6Itzgt.fsh"]
    event = artifacts["questionnaires/VBqh0ynB2wv.fsh"]
    assert "* extension[D2FormType].valueCode = #aggregate" in aggregate
    assert "* code = D2FormType_CS#aggregate" in aggregate
    assert "* extension[D2FormType].valueCode = #event" in event
    assert "* code = D2FormType_CS#event" in event


def test_sections_become_group_items_holding_their_data_elements() -> None:
    """Each section is a #group item whose children are the data elements it references."""
    content = _artifacts([_DATA_SET])["questionnaires/BfMAe6Itzgt.fsh"]
    assert '* item[+].linkId = "Sec1aaaaaaa"' in content
    assert '* item[=].text = "Immunization"' in content
    assert "* item[=].type = #group" in content
    assert '* item[=].item[+].linkId = "De1aaaaaaaa"' in content
    assert '* item[=].item[=].code = D2DE_CS#De1aaaaaaaa "BCG doses given"' in content
    assert '* item[=].item[=].text = "BCG"' in content
    assert "* item[=].item[=].type = #integer" in content


def test_disaggregated_data_element_becomes_a_group_of_option_combos() -> None:
    """A non-default category combo turns the question into a group with one child per option combo."""
    content = _artifacts([_DATA_SET])["questionnaires/BfMAe6Itzgt.fsh"]
    assert '* item[=].item[+].linkId = "De2aaaaaaaa"' in content
    assert '* item[=].item[=].code = D2DE_CS#De2aaaaaaaa "Measles doses given"' in content
    assert "* item[=].item[=].type = #group" in content
    assert '* item[=].item[=].item[+].linkId = "De2aaaaaaaa.Coc1aaaaaaa"' in content
    assert '* item[=].item[=].item[=].code = D2COC_CS#Coc1aaaaaaa "<1y"' in content
    assert '* item[=].item[=].item[=].text = "<1y"' in content
    assert "* item[=].item[=].item[=].type = #integer" in content
    assert '* item[=].item[=].item[+].linkId = "De2aaaaaaaa.Coc2aaaaaaa"' in content


def test_a_section_with_a_disaggregated_element_renders_as_a_gtable() -> None:
    """Only the section carrying a disaggregated data element gets the itemControl gtable extension."""
    content = _artifacts([_DATA_SET])["questionnaires/BfMAe6Itzgt.fsh"]
    assert (
        content.count(
            '* item[=].extension[+].url = "http://hl7.org/fhir/StructureDefinition/questionnaire-itemControl"'
        )
        == 1
    )
    assert (
        "* item[=].extension[=].valueCodeableConcept = http://hl7.org/fhir/questionnaire-item-control#gtable" in content
    )
    demographics = content.split('* item[+].linkId = "Sec2aaaaaaa"')[1]
    assert "itemControl" not in demographics


def test_option_set_bound_question_is_a_choice_answered_from_the_option_set_value_set() -> None:
    """An optionSet on the data element makes the item a #choice bound to that set's generated ValueSet."""
    content = _artifacts([_DATA_SET])["questionnaires/BfMAe6Itzgt.fsh"]
    assert "* item[=].item[=].type = #choice" in content
    assert "* item[=].item[=].answerValueSet = Canonical(D2OS_Os1aaaaaaaa_VS)" in content


def test_compulsory_event_question_is_required() -> None:
    """A compulsory program-stage data element emits `required = true`; the form name is the item text."""
    content = _artifacts([_EVENT_PROGRAM])["questionnaires/VBqh0ynB2wv.fsh"]
    assert '* item[+].linkId = "qrur9Dvnyt5"' in content
    assert '* item[=].text = "Age (years)"' in content
    assert "* item[=].required = true" in content


@pytest.mark.parametrize(
    ("value_type", "item_type"),
    [
        ("TEXT", "string"),
        ("LONG_TEXT", "text"),
        ("NUMBER", "decimal"),
        ("INTEGER", "integer"),
        ("INTEGER_POSITIVE", "integer"),
        ("INTEGER_NEGATIVE", "integer"),
        ("INTEGER_ZERO_OR_POSITIVE", "integer"),
        ("BOOLEAN", "boolean"),
        ("TRUE_ONLY", "boolean"),
        ("DATE", "date"),
        ("DATETIME", "dateTime"),
        ("TIME", "time"),
        ("PERCENTAGE", "decimal"),
        ("UNIT_INTERVAL", "decimal"),
        ("ORGANISATION_UNIT", "reference"),
        ("FILE_RESOURCE", "string"),
        ("COORDINATE", "string"),
    ],
)
def test_value_type_maps_onto_the_item_type(value_type: str, item_type: str) -> None:
    """Every DHIS2 value type answers as its mapped FHIR item type; anything unmapped answers as a string."""
    source = QuestionnaireSourceIn(
        uid="Ds1aaaaaaaa",
        name="Types",
        kind="aggregate",
        flat_items=[QuestionnaireItemIn(uid="De9aaaaaaaa", name="Value", value_type=value_type)],
    )
    assert f"* item[=].type = #{item_type}" in _artifacts([source])["questionnaires/Ds1aaaaaaaa.fsh"]


def test_data_element_support_terminology_lists_every_referenced_element() -> None:
    """The DE CodeSystem covers every data element in any questionnaire and points back at its ValueSet."""
    content = _artifacts([_DATA_SET, _EVENT_PROGRAM])["questionnaires/data-elements.fsh"]
    assert "CodeSystem: D2DE_CS" in content
    assert "Id: d2-de-cs" in content
    assert "* ^experimental = true" in content
    assert "* ^valueSet = Canonical(D2DE_VS)" in content
    assert '* ^property[=].uri = "http://dhis2.org/fhir/property/dhis2-code"' in content
    assert '* #De1aaaaaaaa "BCG doses given"' in content
    assert '* #De1aaaaaaaa ^property[=].valueString = "De1aaaaaaaa"' in content
    assert '* #qrur9Dvnyt5 "Age in years"' in content
    assert "ValueSet: D2DE_VS" in content
    assert "Id: d2-de-vs" in content
    assert "* include codes from system D2DE_CS" in content


def test_category_option_combo_support_terminology_falls_back_to_the_uid() -> None:
    """The COC CodeSystem carries each combo's DHIS2 code, repeating the UID when there is none."""
    content = _artifacts([_DATA_SET])["questionnaires/category-option-combos.fsh"]
    assert "CodeSystem: D2COC_CS" in content
    assert "Id: d2-coc-cs" in content
    assert '* #Coc1aaaaaaa ^property[=].valueString = "U1"' in content
    assert '* #Coc2aaaaaaa ^property[=].valueString = "Coc2aaaaaaa"' in content
    assert "ValueSet: D2COC_VS" in content


def test_support_terminology_is_only_emitted_when_referenced() -> None:
    """A form with no disaggregation emits no option-combo pair; a form with no elements emits neither."""
    without_disaggregation = _artifacts([_EVENT_PROGRAM])
    assert "questionnaires/data-elements.fsh" in without_disaggregation
    assert "questionnaires/category-option-combos.fsh" not in without_disaggregation
    empty = _artifacts([QuestionnaireSourceIn(uid="Ds2aaaaaaaa", name="Empty", kind="aggregate")])
    assert set(empty) == {"questionnaires/Ds2aaaaaaaa.fsh"}


def test_naming_tokens_flow_into_the_questionnaire_names() -> None:
    """Custom data_set / program / prefix tokens rename the questionnaires and their support terminology."""
    config = GenerateConfig(naming=NamingConfig(prefix="Dhis2", data_set="DataSet", program="Program"))
    artifacts = _artifacts([_DATA_SET, _EVENT_PROGRAM], config)
    assert '* name = "Dhis2DataSet_BfMAe6Itzgt"' in artifacts["questionnaires/BfMAe6Itzgt.fsh"]
    assert '* name = "Dhis2Program_VBqh0ynB2wv"' in artifacts["questionnaires/VBqh0ynB2wv.fsh"]
    assert "CodeSystem: Dhis2DE_CS" in artifacts["questionnaires/data-elements.fsh"]
    assert "Id: dhis2-de-cs" in artifacts["questionnaires/data-elements.fsh"]
    assert "Extension: Dhis2FormType" not in artifacts["questionnaires/BfMAe6Itzgt.fsh"]
    assert "* extension[Dhis2FormType].valueCode = #aggregate" in artifacts["questionnaires/BfMAe6Itzgt.fsh"]


async def _scaffold_project(directory: Path, **generate_lines: str) -> None:
    """Scaffold a project and append generate tables to its fhir.toml."""
    options = InitOptions(
        ig_id="dhis2.fhir.questionnaires",
        canonical=_CANONICAL,
        name="Dhis2FhirQuestionnaires",
        title="Questionnaire IG",
        publisher="Questionnaire Org",
    )
    await service.init_project(directory, options)
    config_path = directory / "fhir.toml"
    body = config_path.read_text(encoding="utf-8")
    for table, entries in generate_lines.items():
        body += f"\n[generate.{table}]\ninclude_ids = [{entries}]\n"
    config_path.write_text(body, encoding="utf-8")


@respx.mock
async def test_generate_questionnaires_writes_the_target_directory(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    tmp_path: Path,
) -> None:
    """The target fetches the configured data sets and event programs and syncs `questionnaires/`."""
    mock_system_info("v42")
    await _scaffold_project(tmp_path, data_sets='"BfMAe6Itzgt"', event_programs='"VBqh0ynB2wv"')
    data_sets = respx.get(f"{_HOST}/api/dataSets").mock(return_value=httpx.Response(200, json=_DATA_SETS_PAYLOAD))
    programs = respx.get(f"{_HOST}/api/programs").mock(return_value=httpx.Response(200, json=_EVENT_PROGRAMS_PAYLOAD))

    report = await service.generate_questionnaires(resolve_profile("probe"), load_project(tmp_path))

    assert data_sets.called
    assert programs.called
    assert data_sets.calls.last.request.url.params["filter"] == "id:in:[BfMAe6Itzgt]"
    assert report.questionnaire_count == 2
    assert report.written_files == [
        "questionnaires/BfMAe6Itzgt.fsh",
        "questionnaires/VBqh0ynB2wv.fsh",
        "questionnaires/category-option-combos.fsh",
        "questionnaires/data-elements.fsh",
    ]
    content = (tmp_path / "ig" / "input" / "fsh" / "questionnaires" / "BfMAe6Itzgt.fsh").read_text(encoding="utf-8")
    assert '* url = "http://example.org/fhir/Questionnaire/BfMAe6Itzgt"' in content
    assert '* item[+].linkId = "Sec1aaaaaaa"' in content
    assert '* item[=].item[+].linkId = "De1aaaaaaaa"' in content


@respx.mock
async def test_generate_questionnaires_without_targets_touches_nothing(
    probe_profile: None,  # noqa: ARG001
    tmp_path: Path,
) -> None:
    """With no data sets and no event programs configured, the target writes nothing and opens no client."""
    await _scaffold_project(tmp_path)

    report = await service.generate_questionnaires(resolve_profile("probe"), load_project(tmp_path))

    assert report.questionnaire_count == 0
    assert report.written_files == []
    assert not (tmp_path / "ig" / "input" / "fsh" / "questionnaires").exists()
    assert respx.calls.call_count == 0


@respx.mock
async def test_a_tracker_program_fails_loudly_by_name(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    tmp_path: Path,
) -> None:
    """A WITH_REGISTRATION program under [generate.event_programs] is refused, naming the program and its type."""
    mock_system_info("v42")
    await _scaffold_project(tmp_path, event_programs='"IpHINAT79UW"')
    respx.get(f"{_HOST}/api/programs").mock(
        return_value=httpx.Response(
            200,
            json={
                "programs": [
                    {
                        "id": "IpHINAT79UW",
                        "name": "Child Programme",
                        "programType": "WITH_REGISTRATION",
                        "programStages": [{"id": "A03MvHHogjR", "programStageDataElements": []}],
                    }
                ]
            },
        )
    )

    with pytest.raises(UnsupportedProgramError) as raised:
        await service.generate_questionnaires(resolve_profile("probe"), load_project(tmp_path))

    assert "Child Programme" in str(raised.value)
    assert "IpHINAT79UW" in str(raised.value)
    assert "WITH_REGISTRATION" in str(raised.value)
    assert "tracker programs are not implemented yet" in str(raised.value)


@respx.mock
async def test_a_multi_stage_event_program_fails_loudly_by_name(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    tmp_path: Path,
) -> None:
    """An event program with more than one stage is refused rather than silently losing a stage."""
    mock_system_info("v42")
    await _scaffold_project(tmp_path, event_programs='"Pr2aaaaaaaa"')
    respx.get(f"{_HOST}/api/programs").mock(
        return_value=httpx.Response(
            200,
            json={
                "programs": [
                    {
                        "id": "Pr2aaaaaaaa",
                        "name": "Two stage event",
                        "programType": "WITHOUT_REGISTRATION",
                        "programStages": [
                            {"id": "Ps1aaaaaaaa", "programStageDataElements": []},
                            {"id": "Ps2aaaaaaaa", "programStageDataElements": []},
                        ],
                    }
                ]
            },
        )
    )

    with pytest.raises(UnsupportedProgramError) as raised:
        await service.generate_questionnaires(resolve_profile("probe"), load_project(tmp_path))

    assert "Two stage event" in str(raised.value)
    assert "2 program stages" in str(raised.value)


@respx.mock
async def test_an_unmatched_target_uid_is_noted(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    tmp_path: Path,
) -> None:
    """A configured UID the instance answers nothing for is reported as a note, never dropped silently."""
    mock_system_info("v42")
    await _scaffold_project(tmp_path, data_sets='"BfMAe6Itzgt", "Missing1234"')
    respx.get(f"{_HOST}/api/dataSets").mock(return_value=httpx.Response(200, json=_DATA_SETS_PAYLOAD))

    report = await service.generate_questionnaires(resolve_profile("probe"), load_project(tmp_path))

    assert report.questionnaire_count == 1
    assert any("Missing1234" in note and "matched no data set" in note for note in report.notes)


@respx.mock
async def test_a_form_mixing_sectioned_and_unsectioned_elements_is_noted(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    tmp_path: Path,
) -> None:
    """Data elements no section references are emitted after the sections, with one note naming them."""
    mock_system_info("v42")
    await _scaffold_project(tmp_path, data_sets='"BfMAe6Itzgt"')
    payload = {
        "dataSets": [
            {
                "id": "BfMAe6Itzgt",
                "name": "Child Health",
                "sections": [{"id": "Sec1aaaaaaa", "name": "Immunization", "dataElements": [{"id": "De1aaaaaaaa"}]}],
                "dataSetElements": [
                    {"dataElement": {"id": "De1aaaaaaaa", "name": "BCG doses given", "valueType": "INTEGER"}},
                    {"dataElement": {"id": "De4aaaaaaaa", "name": "Loose element", "valueType": "TEXT"}},
                ],
            }
        ]
    }
    respx.get(f"{_HOST}/api/dataSets").mock(return_value=httpx.Response(200, json=payload))

    report = await service.generate_questionnaires(resolve_profile("probe"), load_project(tmp_path))

    assert any("outside its sections" in note and "De4aaaaaaaa" in note for note in report.notes)
    content = (tmp_path / "ig" / "input" / "fsh" / "questionnaires" / "BfMAe6Itzgt.fsh").read_text(encoding="utf-8")
    assert content.index('* item[+].linkId = "Sec1aaaaaaa"') < content.index('* item[+].linkId = "De4aaaaaaaa"')


@respx.mock
async def test_option_set_selection_unions_the_target_closure(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    tmp_path: Path,
) -> None:
    """A narrowed option-set selection still emits the sets the configured targets bind their elements to."""
    mock_system_info("v42")
    await _scaffold_project(tmp_path, option_sets='"Os2aaaaaaaa"', data_sets='"BfMAe6Itzgt"')
    option_sets_payload = {
        "optionSets": [
            {"id": "Os1aaaaaaaa", "name": "Gender", "options": [{"id": "Op1aaaaaaaa", "name": "Female"}]},
            {"id": "Os2aaaaaaaa", "name": "Selected", "options": [{"id": "Op2aaaaaaaa", "name": "Yes"}]},
            {"id": "Os3aaaaaaaa", "name": "Unrelated", "options": [{"id": "Op3aaaaaaaa", "name": "No"}]},
        ]
    }
    respx.get(f"{_HOST}/api/optionSets").mock(return_value=httpx.Response(200, json=option_sets_payload))
    respx.get(f"{_HOST}/api/dataSets").mock(return_value=httpx.Response(200, json=_DATA_SETS_PAYLOAD))

    report = await service.generate_option_sets(resolve_profile("probe"), load_project(tmp_path))

    assert report.option_set_count == 2
    assert report.written_files == ["terminology/Os1aaaaaaaa.fsh", "terminology/Os2aaaaaaaa.fsh"]
    assert any("closure" in note and "Os1aaaaaaaa" in note for note in report.notes)


@respx.mock
async def test_option_set_closure_is_a_no_op_when_every_set_is_already_included(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    tmp_path: Path,
) -> None:
    """An empty include_ids already means all option sets, so the targets are not fetched a second time."""
    mock_system_info("v42")
    await _scaffold_project(tmp_path, data_sets='"BfMAe6Itzgt"')
    respx.get(f"{_HOST}/api/optionSets").mock(
        return_value=httpx.Response(200, json={"optionSets": [{"id": "Os1aaaaaaaa", "name": "Gender"}]})
    )
    data_sets = respx.get(f"{_HOST}/api/dataSets").mock(return_value=httpx.Response(200, json=_DATA_SETS_PAYLOAD))

    report = await service.generate_option_sets(resolve_profile("probe"), load_project(tmp_path))

    assert report.option_set_count == 1
    assert not data_sets.called


def test_target_selection_defaults_to_nothing() -> None:
    """A data-definition target is explicit opt-in: the default selection is empty."""
    assert TargetSelection().include_ids == []
    assert GenerateConfig().data_sets.include_ids == []
    assert GenerateConfig().event_programs.include_ids == []


def test_generate_questionnaires_cli_renders_the_count(fhir_questionnaire_project: Path) -> None:  # noqa: ARG001
    """`d2w fhir generate questionnaires` renders the questionnaire count from the service report."""
    from unittest.mock import AsyncMock, patch

    from dhis2w_fhir import GenerateReport

    report = GenerateReport(
        project_root=Path("/project"),
        target_directory="questionnaires",
        written_files=["questionnaires/BfMAe6Itzgt.fsh"],
        questionnaire_count=2,
    )
    with patch("dhis2w_fhir.service.generate_questionnaires", new=AsyncMock(return_value=report)):
        result = _runner.invoke(build_app(), ["fhir", "generate", "questionnaires"])

    assert result.exit_code == 0, result.output
    assert "questionnaires" in result.output
    assert "2" in result.output


@pytest.fixture
def fhir_questionnaire_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A working directory holding a fhir.toml and a default profile for CLI tests."""
    config_dir = tmp_path / ".config" / "dhis2"
    config_dir.mkdir(parents=True)
    (config_dir / "profiles.toml").write_text(
        '\ndefault = "probe"\n\n[profiles.probe]\n'
        'base_url = "https://dhis2.example"\nauth = "pat"\ntoken = "d2p_test"\n'
    )
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_dir.parent))
    monkeypatch.delenv("DHIS2_PROFILE", raising=False)
    (tmp_path / "fhir.toml").write_text(
        '[ig]\nid = "dhis2.fhir.test"\ncanonical = "http://example.org/fhir"\nname = "Dhis2FhirTest"\n'
        'title = "DHIS2 FHIR Test IG"\npublisher = "Test Organisation"\n',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    return tmp_path
