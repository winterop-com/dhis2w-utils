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
from dhis2w_fhir.attributes import AttributeCodeIndex
from dhis2w_fhir.resources.option_sets import option_set_identities
from dhis2w_fhir.resources.option_sets.schemas import OptionSetIdentityPlan, OptionSetIn
from dhis2w_fhir.resources.questionnaires import BOUNDS_BY_VALUE_TYPE, ITEM_TYPES_BY_VALUE_TYPE
from dhis2w_fhir.resources.questionnaires.schemas import (
    CategoryComboIn,
    CategoryOptionComboIn,
    QuestionnaireItemIn,
    QuestionnaireSectionIn,
    QuestionnaireSourceIn,
    TargetSelection,
)
from dhis2w_fhir.status import IgStatus
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

_SECOND_DATA_SET = {
    "id": "Ds2aaaaaaaa",
    "name": "Reproductive Health",
    "sections": [],
    "dataSetElements": [{"dataElement": {"id": "De5aaaaaaaa", "name": "ANC 1st visit", "valueType": "INTEGER"}}],
}

_TRACKER_PROGRAM = {
    "id": "IpHINAT79UW",
    "name": "Child Programme",
    "programType": "WITH_REGISTRATION",
    "programStages": [{"id": "A03MvHHogjR", "programStageDataElements": []}],
}

#: The whole instance as the all-mode sweep sees it: two data sets, an event program, and a tracker program.
_ALL_DATA_SETS_PAYLOAD = {"dataSets": [*_DATA_SETS_PAYLOAD["dataSets"], _SECOND_DATA_SET]}
_ALL_PROGRAMS_PAYLOAD = {"programs": [*_EVENT_PROGRAMS_PAYLOAD["programs"], _TRACKER_PROGRAM]}

#: The instance's option sets as the identity plan reads them - the one the fixture forms bind, and a peer.
_OPTION_SETS_PAYLOAD = {
    "optionSets": [
        {"id": "Os1aaaaaaaa", "name": "Gender"},
        {"id": "Os2aaaaaaaa", "name": "Severity"},
    ]
}


def _mock_option_sets() -> None:
    """Mock the option-set fetch every questionnaire run assigns its option-set names from."""
    respx.get(f"{_HOST}/api/optionSets").mock(return_value=httpx.Response(200, json=_OPTION_SETS_PAYLOAD))


_runner = CliRunner()


def _bound_plan(sources: list[QuestionnaireSourceIn], config: GenerateConfig) -> OptionSetIdentityPlan:
    """The identity plan the service hands the emitter: every option set these forms bind, named by its UID."""
    uids = sorted(
        {
            item.option_set_uid
            for source in sources
            for item in [*(item for section in source.sections for item in section.items), *source.flat_items]
            if item.option_set_uid
        }
    )
    return option_set_identities([OptionSetIn(uid=uid, name=uid) for uid in uids], config)


def _artifacts(
    sources: list[QuestionnaireSourceIn],
    config: GenerateConfig | None = None,
    *,
    ig_status: IgStatus = "draft",
    option_set_plan: OptionSetIdentityPlan | None = None,
    attribute_codes: AttributeCodeIndex | None = None,
) -> dict[str, str]:
    """Build the questionnaire artifacts and index them by relative path."""
    resolved = config or GenerateConfig()
    build = build_questionnaire_artifacts(
        sources,
        resolved,
        _CANONICAL,
        ig_status=ig_status,
        option_set_plan=option_set_plan or _bound_plan(sources, resolved),
        attribute_codes=attribute_codes or AttributeCodeIndex(),
    )
    return {artifact.relative_path: artifact.content for artifact in build.artifacts}


def test_questionnaire_artifacts_derive_their_publication_state_from_the_ig_status() -> None:
    """A draft IG publishes draft, experimental questionnaires and support terminology; an active IG neither."""
    draft = _artifacts([_DATA_SET])
    assert "* status = #draft" in draft["data-sets/BfMAe6Itzgt.fsh"]
    assert "* experimental = true" in draft["data-sets/BfMAe6Itzgt.fsh"]
    assert draft["data-dictionary/data-elements.fsh"].count("* ^status = #draft") == 2
    assert draft["data-dictionary/data-elements.fsh"].count("* ^experimental = true") == 2
    assert draft["data-dictionary/category-option-combos.fsh"].count("* ^status = #draft") == 2
    assert draft["data-dictionary/category-option-combos.fsh"].count("* ^experimental = true") == 2
    active = _artifacts([_DATA_SET], ig_status="active")
    assert "* status = #active" in active["data-sets/BfMAe6Itzgt.fsh"]
    assert "* experimental = false" in active["data-sets/BfMAe6Itzgt.fsh"]
    assert active["data-dictionary/data-elements.fsh"].count("* ^status = #active") == 2
    assert active["data-dictionary/data-elements.fsh"].count("* ^experimental = false") == 2
    assert active["data-dictionary/category-option-combos.fsh"].count("* ^status = #active") == 2
    assert active["data-dictionary/category-option-combos.fsh"].count("* ^experimental = false") == 2


def test_data_set_questionnaire_identity() -> None:
    """A data set becomes a definitional Questionnaire keyed by its bare UID, with both DHIS2 identifiers."""
    content = _artifacts([_DATA_SET])["data-sets/BfMAe6Itzgt.fsh"]
    assert "Instance: Questionnaire-BfMAe6Itzgt" in content
    assert "InstanceOf: Questionnaire" in content
    assert "Usage: #definition" in content
    assert '* id = "BfMAe6Itzgt"' in content
    assert '* url = "http://example.org/fhir/Questionnaire/BfMAe6Itzgt"' in content
    assert '* identifier[+].system = $DHIS2-DS\n* identifier[=].value = "BfMAe6Itzgt"' in content
    assert '* identifier[+].system = $DHIS2-DS-CODE\n* identifier[=].value = "DS_359711"' in content
    assert '* name = "D2DS_BfMAe6Itzgt"' in content
    assert '* title = "Child Health"' in content
    assert "* status = #draft" in content
    assert "* experimental = true" in content
    assert "* subjectType = #Location" in content


def test_event_program_questionnaire_identity() -> None:
    """An event program takes the program identifier systems and the PR naming token."""
    content = _artifacts([_EVENT_PROGRAM])["event-programs/VBqh0ynB2wv.fsh"]
    assert "Instance: Questionnaire-VBqh0ynB2wv" in content
    assert "* identifier[+].system = $DHIS2-PROGRAM" in content
    assert "* identifier[+].system = $DHIS2-PROGRAM-CODE" in content
    assert '* name = "D2PR_VBqh0ynB2wv"' in content
    assert '* identifier[=].value = "VBqh0ynB2wv"' in content


def test_form_type_is_carried_by_extension_and_code() -> None:
    """Both kinds state where they came from twice: the D2FormType extension and Questionnaire.code."""
    artifacts = _artifacts([_DATA_SET, _EVENT_PROGRAM])
    aggregate = artifacts["data-sets/BfMAe6Itzgt.fsh"]
    event = artifacts["event-programs/VBqh0ynB2wv.fsh"]
    assert "* extension[D2FormType].valueCode = #aggregate" in aggregate
    assert "* code = D2FormType_CS#aggregate" in aggregate
    assert "* extension[D2FormType].valueCode = #event" in event
    assert "* code = D2FormType_CS#event" in event


def test_sections_become_group_items_holding_their_data_elements() -> None:
    """Each section is a #group item whose children are the data elements it references."""
    content = _artifacts([_DATA_SET])["data-sets/BfMAe6Itzgt.fsh"]
    assert '* item[+].linkId = "Sec1aaaaaaa"' in content
    assert '* item[=].text = "Immunization"' in content
    assert "* item[=].type = #group" in content
    assert '* item[=].item[+].linkId = "De1aaaaaaaa"' in content
    assert '* item[=].item[=].code = D2DE_CS#De1aaaaaaaa "BCG doses given"' in content
    assert '* item[=].item[=].text = "BCG"' in content
    assert "* item[=].item[=].type = #integer" in content


def test_disaggregated_data_element_becomes_a_group_of_option_combos() -> None:
    """A non-default category combo turns the question into a group with one child per option combo."""
    content = _artifacts([_DATA_SET])["data-sets/BfMAe6Itzgt.fsh"]
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
    content = _artifacts([_DATA_SET])["data-sets/BfMAe6Itzgt.fsh"]
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
    content = _artifacts([_DATA_SET])["data-sets/BfMAe6Itzgt.fsh"]
    assert "* item[=].item[=].type = #choice" in content
    assert "* item[=].item[=].answerValueSet = Canonical(D2OS_Os1aaaaaaaa_VS)" in content


def test_compulsory_event_question_is_required() -> None:
    """A compulsory program-stage data element emits `required = true`; the form name is the item text."""
    content = _artifacts([_EVENT_PROGRAM])["event-programs/VBqh0ynB2wv.fsh"]
    assert '* item[+].linkId = "qrur9Dvnyt5"' in content
    assert '* item[=].text = "Age (years)"' in content
    assert "* item[=].required = true" in content


def _operand_payload(operands: list[dict[str, object]]) -> dict[str, object]:
    """One data set holding a plain and a disaggregated data element, plus the given compulsory operands."""
    return {
        "dataSets": [
            {
                "id": "BfMAe6Itzgt",
                "name": "Child Health",
                "sections": [],
                "compulsoryDataElementOperands": operands,
                "dataSetElements": [
                    {"dataElement": {"id": "De1aaaaaaaa", "name": "BCG doses given", "valueType": "INTEGER"}},
                    {
                        "dataElement": {
                            "id": "De2aaaaaaaa",
                            "name": "Measles doses given",
                            "valueType": "INTEGER",
                            "categoryCombo": {
                                "id": "CcAaBbCcDdE",
                                "name": "EPI/nutrition age",
                                "isDefault": False,
                                "categoryOptionCombos": [
                                    {"id": "Coc1aaaaaaa", "name": "<1y"},
                                    {"id": "Coc2aaaaaaa", "name": ">1y"},
                                ],
                            },
                        }
                    },
                ],
            }
        ]
    }


async def _generated_data_set(tmp_path: Path, operands: list[dict[str, object]]) -> str:
    """Generate the operand fixture's questionnaire and read the emitted FSH back."""
    await _scaffold_project(tmp_path, data_sets='"BfMAe6Itzgt"')
    respx.get(f"{_HOST}/api/dataSets").mock(return_value=httpx.Response(200, json=_operand_payload(operands)))
    respx.get(f"{_HOST}/api/programs").mock(return_value=httpx.Response(200, json={"programs": []}))
    _mock_option_sets()
    await service.generate_questionnaires(resolve_profile("probe"), load_project(tmp_path))
    return (tmp_path / "ig" / "input" / "fsh" / "data-sets" / "BfMAe6Itzgt.fsh").read_text(encoding="utf-8")


@respx.mock
async def test_the_data_set_fetch_asks_for_the_compulsory_operands(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    mock_attributes: Callable[..., None],
    tmp_path: Path,
) -> None:
    """Required flags come off `compulsoryDataElementOperands`, so the projection has to request it."""
    mock_system_info("v42")
    mock_attributes()
    await _scaffold_project(tmp_path, data_sets='"BfMAe6Itzgt"')
    data_sets = respx.get(f"{_HOST}/api/dataSets").mock(return_value=httpx.Response(200, json=_operand_payload([])))
    respx.get(f"{_HOST}/api/programs").mock(return_value=httpx.Response(200, json={"programs": []}))
    _mock_option_sets()

    await service.generate_questionnaires(resolve_profile("probe"), load_project(tmp_path))

    fields = data_sets.calls.last.request.url.params["fields"]
    assert "compulsoryDataElementOperands[dataElement[id],categoryOptionCombo[id]]" in fields


@respx.mock
async def test_an_operand_without_an_option_combo_requires_a_plain_question(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    mock_attributes: Callable[..., None],
    tmp_path: Path,
) -> None:
    """An operand naming a data element alone makes that whole question mandatory."""
    mock_system_info("v42")
    mock_attributes()

    content = await _generated_data_set(tmp_path, [{"dataElement": {"id": "De1aaaaaaaa"}}])

    plain = content.split('* item[+].linkId = "De2aaaaaaaa"')[0]
    disaggregated = content.split('* item[+].linkId = "De2aaaaaaaa"')[1]
    assert "* item[=].required = true" in plain
    assert "required" not in disaggregated


@respx.mock
async def test_an_operand_without_an_option_combo_requires_every_cell_of_a_disaggregated_question(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    mock_attributes: Callable[..., None],
    tmp_path: Path,
) -> None:
    """The same operand on a disaggregated element requires the group and every option combo under it."""
    mock_system_info("v42")
    mock_attributes()

    content = await _generated_data_set(tmp_path, [{"dataElement": {"id": "De2aaaaaaaa"}}])

    disaggregated = content.split('* item[+].linkId = "De2aaaaaaaa"')[1]
    assert "* item[=].required = true" in disaggregated
    assert disaggregated.count("* item[=].item[=].required = true") == 2


@respx.mock
async def test_an_operand_with_an_option_combo_requires_only_that_cell(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    mock_attributes: Callable[..., None],
    tmp_path: Path,
) -> None:
    """An operand naming a category option combo makes only that one child question mandatory."""
    mock_system_info("v42")
    mock_attributes()

    content = await _generated_data_set(
        tmp_path,
        [{"dataElement": {"id": "De2aaaaaaaa"}, "categoryOptionCombo": {"id": "Coc2aaaaaaa"}}],
    )

    disaggregated = content.split('* item[+].linkId = "De2aaaaaaaa"')[1]
    first_cell = disaggregated.split('* item[=].item[+].linkId = "De2aaaaaaaa.Coc2aaaaaaa"')[0]
    second_cell = disaggregated.split('* item[=].item[+].linkId = "De2aaaaaaaa.Coc2aaaaaaa"')[1]
    assert "required" not in first_cell
    assert "* item[=].item[=].required = true" in second_cell
    assert content.count("required = true") == 1


@pytest.mark.parametrize(
    ("value_type", "minimum", "maximum"),
    [
        ("INTEGER_POSITIVE", "valueInteger = 1", None),
        ("INTEGER_ZERO_OR_POSITIVE", "valueInteger = 0", None),
        ("INTEGER_NEGATIVE", None, "valueInteger = -1"),
        ("PERCENTAGE", "valueDecimal = 0", "valueDecimal = 100"),
        ("UNIT_INTERVAL", "valueDecimal = 0", "valueDecimal = 1"),
        ("INTEGER", None, None),
        ("NUMBER", None, None),
        ("TEXT", None, None),
    ],
)
def test_a_bounded_value_type_carries_its_range_as_min_and_max_extensions(
    value_type: str, minimum: str | None, maximum: str | None
) -> None:
    """A DHIS2 value type that *is* a constraint states that constraint on the item; the rest state none."""
    source = QuestionnaireSourceIn(
        uid="Ds1aaaaaaaa",
        name="Types",
        kind="aggregate",
        flat_items=[QuestionnaireItemIn(uid="De9aaaaaaaa", name="Value", value_type=value_type)],
    )
    content = _artifacts([source])["data-sets/Ds1aaaaaaaa.fsh"]
    for url, literal in (("minValue", minimum), ("maxValue", maximum)):
        declaration = f'* item[=].extension[+].url = "http://hl7.org/fhir/StructureDefinition/{url}"'
        if literal is None:
            assert url not in content
            continue
        assert declaration in content
        assert f"* item[=].extension[=].{literal}" in content


def test_a_category_option_combo_child_carries_its_parents_bounds() -> None:
    """A disaggregated cell shares its data element's value type, so it shares the value type's bounds."""
    source = QuestionnaireSourceIn(
        uid="Ds1aaaaaaaa",
        name="Types",
        kind="aggregate",
        flat_items=[
            QuestionnaireItemIn(uid="De9aaaaaaaa", name="Coverage", value_type="PERCENTAGE", category_combo=_AGE_COMBO)
        ],
    )
    content = _artifacts([source])["data-sets/Ds1aaaaaaaa.fsh"]
    assert content.count('* item[=].item[=].extension[+].url = "http://hl7.org/fhir/StructureDefinition/minValue"') == 2
    assert content.count("* item[=].item[=].extension[=].valueDecimal = 100") == 2
    group = content.split('* item[=].item[+].linkId = "De9aaaaaaaa.Coc1aaaaaaa"')[0]
    assert "minValue" not in group


def test_an_option_set_bound_question_takes_no_numeric_bounds() -> None:
    """A `#choice` item has no numeric element to constrain, so no bound is emitted on it."""
    source = QuestionnaireSourceIn(
        uid="Ds1aaaaaaaa",
        name="Types",
        kind="aggregate",
        flat_items=[
            QuestionnaireItemIn(uid="De9aaaaaaaa", name="Band", value_type="PERCENTAGE", option_set_uid="Os1aaaaaaaa")
        ],
    )
    content = _artifacts([source])["data-sets/Ds1aaaaaaaa.fsh"]
    assert "* item[=].type = #choice" in content
    assert "minValue" not in content


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
        ("LETTER", "string"),
        ("PHONE_NUMBER", "string"),
        ("EMAIL", "string"),
        ("USERNAME", "string"),
        ("AGE", "date"),
        ("URL", "url"),
        ("FILE_RESOURCE", "attachment"),
        ("IMAGE", "attachment"),
        ("GEOJSON", "text"),
        ("COORDINATE", "string"),
        ("REFERENCE", "string"),
        ("TRACKER_ASSOCIATE", "string"),
        ("A_VALUE_TYPE_FROM_THE_FUTURE", "string"),
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
    assert f"* item[=].type = #{item_type}" in _artifacts([source])["data-sets/Ds1aaaaaaaa.fsh"]


def test_data_element_support_terminology_lists_every_referenced_element() -> None:
    """The DE CodeSystem covers every data element in any questionnaire and points back at its ValueSet."""
    content = _artifacts([_DATA_SET, _EVENT_PROGRAM])["data-dictionary/data-elements.fsh"]
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
    content = _artifacts([_DATA_SET])["data-dictionary/category-option-combos.fsh"]
    assert "CodeSystem: D2COC_CS" in content
    assert "Id: d2-coc-cs" in content
    assert '* #Coc1aaaaaaa ^property[=].valueString = "U1"' in content
    assert '* #Coc2aaaaaaa ^property[=].valueString = "Coc2aaaaaaa"' in content
    assert "ValueSet: D2COC_VS" in content


def test_support_terminology_is_only_emitted_when_referenced() -> None:
    """A form with no disaggregation emits no option-combo pair; a form with no elements emits neither."""
    without_disaggregation = _artifacts([_EVENT_PROGRAM])
    assert "data-dictionary/data-elements.fsh" in without_disaggregation
    assert "data-dictionary/category-option-combos.fsh" not in without_disaggregation
    empty = _artifacts([QuestionnaireSourceIn(uid="Ds2aaaaaaaa", name="Empty", kind="aggregate")])
    assert set(empty) == {"data-sets/Ds2aaaaaaaa.fsh"}


def test_naming_tokens_flow_into_the_questionnaire_names() -> None:
    """Custom data_set / program / prefix tokens rename the questionnaires and their support terminology."""
    config = GenerateConfig(naming=NamingConfig(prefix="Dhis2", data_set="DataSet", program="Program"))
    artifacts = _artifacts([_DATA_SET, _EVENT_PROGRAM], config)
    assert '* name = "Dhis2DataSet_BfMAe6Itzgt"' in artifacts["data-sets/BfMAe6Itzgt.fsh"]
    assert '* name = "Dhis2Program_VBqh0ynB2wv"' in artifacts["event-programs/VBqh0ynB2wv.fsh"]
    assert "CodeSystem: Dhis2DE_CS" in artifacts["data-dictionary/data-elements.fsh"]
    assert "Id: dhis2-de-cs" in artifacts["data-dictionary/data-elements.fsh"]
    assert "Extension: Dhis2FormType" not in artifacts["data-sets/BfMAe6Itzgt.fsh"]
    assert "* extension[Dhis2FormType].valueCode = #aggregate" in artifacts["data-sets/BfMAe6Itzgt.fsh"]


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
    mock_attributes: Callable[..., None],
    tmp_path: Path,
) -> None:
    """The target fetches the configured data sets and event programs and syncs its three directories."""
    mock_system_info("v42")
    mock_attributes()
    await _scaffold_project(tmp_path, data_sets='"BfMAe6Itzgt"', event_programs='"VBqh0ynB2wv"')
    data_sets = respx.get(f"{_HOST}/api/dataSets").mock(return_value=httpx.Response(200, json=_DATA_SETS_PAYLOAD))
    programs = respx.get(f"{_HOST}/api/programs").mock(return_value=httpx.Response(200, json=_EVENT_PROGRAMS_PAYLOAD))
    _mock_option_sets()

    report = await service.generate_questionnaires(resolve_profile("probe"), load_project(tmp_path))

    assert data_sets.called
    assert programs.called
    assert data_sets.calls.last.request.url.params["filter"] == "id:in:[BfMAe6Itzgt]"
    assert report.questionnaire_count == 2
    assert report.written_files == [
        "data-sets/BfMAe6Itzgt.fsh",
        "event-programs/VBqh0ynB2wv.fsh",
        "data-dictionary/category-option-combos.fsh",
        "data-dictionary/data-elements.fsh",
    ]
    assert report.target_directory == "data-sets, event-programs, data-dictionary"
    fsh = tmp_path / "ig" / "input" / "fsh"
    assert not (fsh / "questionnaires").exists()
    assert (fsh / "event-programs" / "VBqh0ynB2wv.fsh").exists()
    assert (fsh / "data-dictionary" / "data-elements.fsh").exists()
    content = (fsh / "data-sets" / "BfMAe6Itzgt.fsh").read_text(encoding="utf-8")
    assert '* url = "http://example.org/fhir/Questionnaire/BfMAe6Itzgt"' in content
    assert '* item[+].linkId = "Sec1aaaaaaa"' in content
    assert '* item[=].item[+].linkId = "De1aaaaaaaa"' in content


@respx.mock
async def test_an_absent_selection_covers_the_whole_instance(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    mock_attributes: Callable[..., None],
    tmp_path: Path,
) -> None:
    """No selection tables means all: every data set plus the single-stage event programs, the rest noted."""
    mock_system_info("v42")
    mock_attributes()
    await _scaffold_project(tmp_path)
    data_sets = respx.get(f"{_HOST}/api/dataSets").mock(return_value=httpx.Response(200, json=_ALL_DATA_SETS_PAYLOAD))
    programs = respx.get(f"{_HOST}/api/programs").mock(return_value=httpx.Response(200, json=_ALL_PROGRAMS_PAYLOAD))
    _mock_option_sets()

    report = await service.generate_questionnaires(resolve_profile("probe"), load_project(tmp_path))

    assert "filter" not in data_sets.calls.last.request.url.params
    assert "filter" not in programs.calls.last.request.url.params
    assert report.questionnaire_count == 3
    assert report.written_files == [
        "data-sets/BfMAe6Itzgt.fsh",
        "data-sets/Ds2aaaaaaaa.fsh",
        "event-programs/VBqh0ynB2wv.fsh",
        "data-dictionary/category-option-combos.fsh",
        "data-dictionary/data-elements.fsh",
    ]
    assert [note for note in report.notes if "skipped" in note] == [
        "1 tracker programs skipped (tracker generation not implemented): Child Programme (IpHINAT79UW)",
    ]


@respx.mock
async def test_each_directory_is_swept_against_its_own_files(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    mock_attributes: Callable[..., None],
    tmp_path: Path,
) -> None:
    """Narrowing the selection deletes the questionnaires that left its own directory, and nothing else."""
    mock_system_info("v42")
    mock_attributes()
    await _scaffold_project(tmp_path)

    def _data_sets(request: httpx.Request) -> httpx.Response:
        """Answer the whole instance, or the one configured data set once the selection narrows."""
        narrowed = "filter" in request.url.params
        return httpx.Response(200, json=_DATA_SETS_PAYLOAD if narrowed else _ALL_DATA_SETS_PAYLOAD)

    respx.get(f"{_HOST}/api/dataSets").mock(side_effect=_data_sets)
    respx.get(f"{_HOST}/api/programs").mock(return_value=httpx.Response(200, json=_ALL_PROGRAMS_PAYLOAD))
    _mock_option_sets()
    await service.generate_questionnaires(resolve_profile("probe"), load_project(tmp_path))
    await _scaffold_project(tmp_path, data_sets='"BfMAe6Itzgt"')

    report = await service.generate_questionnaires(resolve_profile("probe"), load_project(tmp_path))

    fsh = tmp_path / "ig" / "input" / "fsh"
    assert report.deleted_files == ["Ds2aaaaaaaa.fsh"]
    assert not (fsh / "data-sets" / "Ds2aaaaaaaa.fsh").exists()
    assert (fsh / "data-sets" / "BfMAe6Itzgt.fsh").exists()
    assert (fsh / "event-programs" / "VBqh0ynB2wv.fsh").exists()
    assert (fsh / "data-dictionary" / "data-elements.fsh").exists()


@respx.mock
async def test_a_tracker_program_fails_loudly_by_name(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    tmp_path: Path,
) -> None:
    """A WITH_REGISTRATION program under [generate.event_programs] is refused, naming the program and its type."""
    mock_system_info("v42")
    await _scaffold_project(tmp_path, event_programs='"IpHINAT79UW"')
    respx.get(f"{_HOST}/api/dataSets").mock(return_value=httpx.Response(200, json={"dataSets": []}))
    respx.get(f"{_HOST}/api/programs").mock(return_value=httpx.Response(200, json={"programs": [_TRACKER_PROGRAM]}))

    with pytest.raises(UnsupportedProgramError) as raised:
        await service.generate_questionnaires(resolve_profile("probe"), load_project(tmp_path))

    assert "Child Programme" in str(raised.value)
    assert "IpHINAT79UW" in str(raised.value)
    assert "WITH_REGISTRATION" in str(raised.value)
    assert "tracker programs are not implemented yet" in str(raised.value)


@respx.mock
async def test_an_unmatched_target_uid_is_noted(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    mock_attributes: Callable[..., None],
    tmp_path: Path,
) -> None:
    """A configured UID the instance answers nothing for is reported as a note, never dropped silently."""
    mock_system_info("v42")
    mock_attributes()
    await _scaffold_project(tmp_path, data_sets='"BfMAe6Itzgt", "Missing1234"')
    respx.get(f"{_HOST}/api/dataSets").mock(return_value=httpx.Response(200, json=_DATA_SETS_PAYLOAD))
    respx.get(f"{_HOST}/api/programs").mock(return_value=httpx.Response(200, json={"programs": []}))
    _mock_option_sets()

    report = await service.generate_questionnaires(resolve_profile("probe"), load_project(tmp_path))

    assert report.questionnaire_count == 1
    assert any("Missing1234" in note and "matched no data set" in note for note in report.notes)


@respx.mock
async def test_a_form_mixing_sectioned_and_unsectioned_elements_is_noted(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    mock_attributes: Callable[..., None],
    tmp_path: Path,
) -> None:
    """Data elements no section references are emitted after the sections, with one note naming them."""
    mock_system_info("v42")
    mock_attributes()
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
    respx.get(f"{_HOST}/api/programs").mock(return_value=httpx.Response(200, json={"programs": []}))
    _mock_option_sets()

    report = await service.generate_questionnaires(resolve_profile("probe"), load_project(tmp_path))

    assert any("outside its sections" in note and "De4aaaaaaaa" in note for note in report.notes)
    content = (tmp_path / "ig" / "input" / "fsh" / "data-sets" / "BfMAe6Itzgt.fsh").read_text(encoding="utf-8")
    assert content.index('* item[+].linkId = "Sec1aaaaaaa"') < content.index('* item[+].linkId = "De4aaaaaaaa"')


@respx.mock
async def test_option_set_selection_unions_the_target_closure(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    mock_attributes: Callable[..., None],
    tmp_path: Path,
) -> None:
    """A narrowed option-set selection still emits the sets the configured targets bind their elements to."""
    mock_system_info("v42")
    mock_attributes()
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
    respx.get(f"{_HOST}/api/programs").mock(return_value=httpx.Response(200, json={"programs": []}))

    report = await service.generate_option_sets(resolve_profile("probe"), load_project(tmp_path))

    assert report.option_set_count == 2
    assert report.written_files == [
        "terminology/CodeSystem-d2-os-Os1aaaaaaaa-cs.json",
        "terminology/CodeSystem-d2-os-Os2aaaaaaaa-cs.json",
        "terminology/ValueSet-d2-os-Os1aaaaaaaa-vs.json",
        "terminology/ValueSet-d2-os-Os2aaaaaaaa-vs.json",
    ]
    assert any("closure" in note and "Os1aaaaaaaa" in note for note in report.notes)


@respx.mock
async def test_option_set_closure_is_a_no_op_when_every_set_is_already_included(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    mock_attributes: Callable[..., None],
    tmp_path: Path,
) -> None:
    """An empty include_ids already means all option sets, so the targets are not fetched a second time."""
    mock_system_info("v42")
    mock_attributes()
    await _scaffold_project(tmp_path, data_sets='"BfMAe6Itzgt"')
    respx.get(f"{_HOST}/api/optionSets").mock(
        return_value=httpx.Response(200, json={"optionSets": [{"id": "Os1aaaaaaaa", "name": "Gender"}]})
    )
    data_sets = respx.get(f"{_HOST}/api/dataSets").mock(return_value=httpx.Response(200, json=_DATA_SETS_PAYLOAD))

    report = await service.generate_option_sets(resolve_profile("probe"), load_project(tmp_path))

    assert report.option_set_count == 1
    assert not data_sets.called


@respx.mock
async def test_generate_all_without_selection_tables_still_emits_questionnaires(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    mock_attributes: Callable[..., None],
    tmp_path: Path,
) -> None:
    """`generate all` on a project with no selection tables generates for the whole instance."""
    mock_system_info("v42")
    mock_attributes()
    await _scaffold_project(tmp_path)
    _mock_option_sets()
    respx.get(f"{_HOST}/api/categories").mock(return_value=httpx.Response(200, json={"categories": []}))
    respx.get(f"{_HOST}/api/organisationUnits").mock(return_value=httpx.Response(200, json={"organisationUnits": []}))
    data_sets = respx.get(f"{_HOST}/api/dataSets").mock(return_value=httpx.Response(200, json=_ALL_DATA_SETS_PAYLOAD))
    programs = respx.get(f"{_HOST}/api/programs").mock(return_value=httpx.Response(200, json=_ALL_PROGRAMS_PAYLOAD))

    report = await service.generate_all(resolve_profile("probe"), load_project(tmp_path))

    assert data_sets.called
    assert programs.called
    assert report.questionnaires.questionnaire_count == 3
    assert "data-sets/BfMAe6Itzgt.fsh" in report.questionnaires.written_files


def test_target_selection_defaults_to_everything() -> None:
    """A data-definition target defaults to an empty include list, which selects the whole instance."""
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
        written_files=["data-sets/BfMAe6Itzgt.fsh"],
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


def test_page_titles_escape_markup_while_the_element_title_stays_raw() -> None:
    """A DHIS2 name holding `<` aborts the IG publisher's HTML parse, so only the page metadata escapes it."""
    source = _DATA_SET.model_copy(update={"name": "Mortality < 5 years by gender"})
    content = _artifacts([source])["data-sets/BfMAe6Itzgt.fsh"]
    assert 'Title: "Questionnaire - Mortality &lt; 5 years by gender"' in content
    assert "Mortality &lt; 5 years by gender (BfMAe6Itzgt)" in content
    assert '* title = "Mortality < 5 years by gender"' in content


@respx.mock
async def test_a_data_sets_unsectioned_elements_are_ordered_independently_of_the_wire(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    mock_attributes: Callable[..., None],
    tmp_path: Path,
) -> None:
    """DHIS2 shuffles `dataSetElements` per request (BUGS.md #63), so the emitter orders them itself."""
    mock_system_info("v42")
    mock_attributes()
    await _scaffold_project(tmp_path, data_sets='"Ds3aaaaaaaa"')
    elements = [
        {"dataElement": {"id": "Deczzzzzzzz", "name": "Zebra count", "valueType": "INTEGER"}},
        {"dataElement": {"id": "Debzzzzzzzz", "name": "Antelope count", "valueType": "INTEGER"}},
        {"dataElement": {"id": "Deazzzzzzzz", "name": "Marmot count", "valueType": "INTEGER"}},
    ]
    shuffled = {"dataSets": [{"id": "Ds3aaaaaaaa", "name": "Wildlife", "sections": [], "dataSetElements": elements}]}
    reversed_order = {
        "dataSets": [{"id": "Ds3aaaaaaaa", "name": "Wildlife", "sections": [], "dataSetElements": elements[::-1]}]
    }
    respx.get(f"{_HOST}/api/programs").mock(return_value=httpx.Response(200, json={"programs": []}))
    _mock_option_sets()
    respx.get(f"{_HOST}/api/dataSets").mock(return_value=httpx.Response(200, json=shuffled))
    await service.generate_questionnaires(resolve_profile("probe"), load_project(tmp_path))
    first = (tmp_path / "ig" / "input" / "fsh" / "data-sets" / "Ds3aaaaaaaa.fsh").read_text(encoding="utf-8")
    respx.get(f"{_HOST}/api/dataSets").mock(return_value=httpx.Response(200, json=reversed_order))

    report = await service.generate_questionnaires(resolve_profile("probe"), load_project(tmp_path))

    second = (tmp_path / "ig" / "input" / "fsh" / "data-sets" / "Ds3aaaaaaaa.fsh").read_text(encoding="utf-8")
    assert report.written_files == []
    assert first == second
    assert first.index("Debzzzzzzzz") < first.index("Deazzzzzzzz") < first.index("Deczzzzzzzz")


#: One category combo's option combos, deliberately not in (name, uid) order on the wire.
_SHUFFLED_OPTION_COMBOS = [
    {"id": "Cocczzzzzzz", "name": "Zebra"},
    {"id": "Cocazzzzzzz", "name": "Antelope", "code": "ANT"},
    {"id": "Cocbzzzzzzz", "name": "Marmot"},
]


def _disaggregated_payload(option_combos: list[dict[str, str]]) -> dict[str, object]:
    """One data set whose single data element disaggregates by the given option combos."""
    return {
        "dataSets": [
            {
                "id": "Ds3aaaaaaaa",
                "name": "Wildlife",
                "sections": [],
                "dataSetElements": [
                    {
                        "dataElement": {
                            "id": "Deazzzzzzzz",
                            "name": "Sightings",
                            "valueType": "INTEGER",
                            "categoryCombo": {
                                "id": "CcAaBbCcDdE",
                                "name": "Species",
                                "isDefault": False,
                                "categoryOptionCombos": option_combos,
                            },
                        }
                    }
                ],
            }
        ]
    }


@respx.mock
async def test_category_option_combos_are_ordered_independently_of_the_wire(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    mock_attributes: Callable[..., None],
    tmp_path: Path,
) -> None:
    """DHIS2 shuffles `categoryOptionCombos` per request (BUGS.md #64), so the emitter orders them itself."""
    mock_system_info("v42")
    mock_attributes()
    await _scaffold_project(tmp_path, data_sets='"Ds3aaaaaaaa"')
    respx.get(f"{_HOST}/api/programs").mock(return_value=httpx.Response(200, json={"programs": []}))
    _mock_option_sets()
    respx.get(f"{_HOST}/api/dataSets").mock(
        return_value=httpx.Response(200, json=_disaggregated_payload(_SHUFFLED_OPTION_COMBOS))
    )
    await service.generate_questionnaires(resolve_profile("probe"), load_project(tmp_path))
    fsh = tmp_path / "ig" / "input" / "fsh"
    first = (fsh / "data-sets" / "Ds3aaaaaaaa.fsh").read_text(encoding="utf-8")
    terminology = (fsh / "data-dictionary" / "category-option-combos.fsh").read_text(encoding="utf-8")
    respx.get(f"{_HOST}/api/dataSets").mock(
        return_value=httpx.Response(200, json=_disaggregated_payload(_SHUFFLED_OPTION_COMBOS[::-1]))
    )

    report = await service.generate_questionnaires(resolve_profile("probe"), load_project(tmp_path))

    second = (fsh / "data-sets" / "Ds3aaaaaaaa.fsh").read_text(encoding="utf-8")
    assert report.written_files == []
    assert first == second
    assert first.index("Cocazzzzzzz") < first.index("Cocbzzzzzzz") < first.index("Cocczzzzzzz")
    assert terminology.index("Cocazzzzzzz") < terminology.index("Cocbzzzzzzz") < terminology.index("Cocczzzzzzz")


def _generated_value_types(version: str) -> set[str]:
    """The members of one generated tree's ValueType enum, found by the two members every version holds."""
    import enum
    import importlib

    module = importlib.import_module(f"dhis2w_client.generated.{version}.enums")
    enums = [
        candidate
        for candidate in vars(module).values()
        if isinstance(candidate, type)
        and issubclass(candidate, enum.Enum)
        and {"TEXT", "TRUE_ONLY"} <= set(candidate.__members__)
    ]
    assert len(enums) == 1, f"expected exactly one ValueType enum in {version}, found {len(enums)}"
    return set(enums[0].__members__)


@pytest.mark.parametrize("version", ["v41", "v42", "v43"])
def test_every_generated_value_type_has_an_explicit_item_type(version: str) -> None:
    """A codegen refresh that adds a DHIS2 value type must be a mapping decision, not a silent string.

    `TRACKER_ASSOCIATE` is v41/v42 only - v43 dropped it - so the table is the union of the three.
    """
    unmapped = sorted(_generated_value_types(version) - set(ITEM_TYPES_BY_VALUE_TYPE))
    assert unmapped == [], f"{version} ValueType members with no entry in ITEM_TYPES_BY_VALUE_TYPE: {unmapped}"


def test_the_item_type_table_maps_nothing_dhis2_does_not_have() -> None:
    """The table is exactly the union of the three trees - a stale key would document a type that is gone."""
    known = set().union(*(_generated_value_types(version) for version in ("v41", "v42", "v43")))
    assert set(ITEM_TYPES_BY_VALUE_TYPE) == known


def test_every_bounded_value_type_is_a_value_type_dhis2_has() -> None:
    """A bound on a value type no generated tree knows would constrain a question that cannot exist."""
    known = set().union(*(_generated_value_types(version) for version in ("v41", "v42", "v43")))
    unknown = sorted(set(BOUNDS_BY_VALUE_TYPE) - known)
    assert unknown == [], f"BOUNDS_BY_VALUE_TYPE keys no generated ValueType enum holds: {unknown}"


def test_every_bounded_value_type_answers_as_a_number() -> None:
    """A bound is a numeric constraint, so a bounded value type has to answer as an integer or a decimal."""
    unnumbered = sorted(
        value_type
        for value_type in BOUNDS_BY_VALUE_TYPE
        if ITEM_TYPES_BY_VALUE_TYPE[value_type] not in {"integer", "decimal"}
    )
    assert unnumbered == [], f"BOUNDS_BY_VALUE_TYPE keys that do not answer as a number: {unnumbered}"


def test_multi_text_is_a_repeating_choice() -> None:
    """MULTI_TEXT *is* multiple selection, so its item repeats; a single-valued choice does not."""
    source = QuestionnaireSourceIn(
        uid="Ds4aaaaaaaa",
        name="Symptoms",
        kind="aggregate",
        flat_items=[
            QuestionnaireItemIn(
                uid="De6aaaaaaaa", name="Symptoms seen", value_type="MULTI_TEXT", option_set_uid="Os1aaaaaaaa"
            ),
            QuestionnaireItemIn(uid="De7aaaaaaaa", name="Sex", value_type="TEXT", option_set_uid="Os2aaaaaaaa"),
        ],
    )
    content = _artifacts([source])["data-sets/Ds4aaaaaaaa.fsh"]
    multi = content.split('* item[+].linkId = "De7aaaaaaaa"')[0]
    single = content.split('* item[+].linkId = "De7aaaaaaaa"')[1]
    assert "* item[=].type = #choice" in multi
    assert "* item[=].repeats = true" in multi
    assert "* item[=].type = #choice" in single
    assert "repeats" not in single


def test_a_multi_text_element_without_an_option_set_does_not_repeat() -> None:
    """MULTI_TEXT is option-set-bound by definition; one without a set is malformed and takes no repeats."""
    source = QuestionnaireSourceIn(
        uid="Ds5aaaaaaaa",
        name="Broken",
        kind="aggregate",
        flat_items=[QuestionnaireItemIn(uid="De8aaaaaaaa", name="Loose multi", value_type="MULTI_TEXT")],
    )
    assert "repeats" not in _artifacts([source])["data-sets/Ds5aaaaaaaa.fsh"]


def test_data_element_concepts_carry_their_dhis2_domain_type() -> None:
    """The DE CodeSystem declares a `domain` property and codes each concept aggregate or tracker."""
    aggregate = _BCG.model_copy(update={"domain_type": "AGGREGATE"})
    tracker = QuestionnaireItemIn(uid="De9aaaaaaaa", name="Tracker element", value_type="TEXT", domain_type="TRACKER")
    source = QuestionnaireSourceIn(uid="Ds6aaaaaaaa", name="Mixed", kind="aggregate", flat_items=[aggregate, tracker])
    content = _artifacts([source])["data-dictionary/data-elements.fsh"]
    assert "* ^property[+].code = #domain" in content
    assert '* ^property[=].uri = "http://dhis2.org/fhir/property/domain"' in content
    assert '* ^property[=].description = "DHIS2 data element domain type."' in content
    assert "* ^property[=].type = #code" in content
    assert "* #De1aaaaaaaa ^property[=].valueCode = #aggregate" in content
    assert "* #De9aaaaaaaa ^property[=].valueCode = #tracker" in content


def test_the_domain_property_is_absent_when_dhis2_sends_no_domain_type() -> None:
    """An instance answering no domainType leaves the property off the concepts and off the CodeSystem header."""
    content = _artifacts([_DATA_SET])["data-dictionary/data-elements.fsh"]
    assert "#domain" not in content


def test_a_disaggregated_option_bound_question_binds_every_cell_to_the_option_set() -> None:
    """A cell asks its data element's question one option combo at a time, so it keeps the choice binding."""
    source = QuestionnaireSourceIn(
        uid="Ds7aaaaaaaa",
        name="Coded grid",
        kind="aggregate",
        flat_items=[
            QuestionnaireItemIn(
                uid="De9aaaaaaaa",
                name="Outcome",
                value_type="PERCENTAGE",
                option_set_uid="Os1aaaaaaaa",
                category_combo=_AGE_COMBO,
            )
        ],
    )
    content = _artifacts([source])["data-sets/Ds7aaaaaaaa.fsh"]
    cells = content.split('* item[+].linkId = "De9aaaaaaaa"')[1]
    assert cells.count("* item[=].item[=].type = #choice") == 2
    assert cells.count("* item[=].item[=].answerValueSet = Canonical(D2OS_Os1aaaaaaaa_VS)") == 2
    assert '* item[=].item[+].linkId = "De9aaaaaaaa.Coc1aaaaaaa"' in cells
    assert "* item[=].type = #group" in cells
    assert "minValue" not in content
    assert "maxValue" not in content


def test_a_disaggregated_multi_text_question_repeats_on_every_cell() -> None:
    """MULTI_TEXT is multiple selection whatever the disaggregation, so each cell repeats like the plain item does."""
    source = QuestionnaireSourceIn(
        uid="Ds8aaaaaaaa",
        name="Symptom grid",
        kind="aggregate",
        flat_items=[
            QuestionnaireItemIn(
                uid="De9aaaaaaaa",
                name="Symptoms seen",
                value_type="MULTI_TEXT",
                option_set_uid="Os1aaaaaaaa",
                category_combo=_AGE_COMBO,
            )
        ],
    )
    content = _artifacts([source])["data-sets/Ds8aaaaaaaa.fsh"]
    assert content.count("* item[=].item[=].repeats = true") == 2
    assert content.count("* item[=].item[=].type = #choice") == 2
    assert "* item[=].repeats = true" not in content


def test_an_option_set_the_plan_omits_falls_back_to_the_uid_name_with_one_note() -> None:
    """The closure puts every bound set into the plan; a gap still emits a name, and the run says which."""
    build = build_questionnaire_artifacts(
        [_DATA_SET],
        GenerateConfig(),
        _CANONICAL,
        ig_status="draft",
        option_set_plan=OptionSetIdentityPlan(),
        attribute_codes=AttributeCodeIndex(),
    )
    content = next(
        artifact.content for artifact in build.artifacts if artifact.relative_path.endswith("BfMAe6Itzgt.fsh")
    )
    assert "* item[=].item[=].answerValueSet = Canonical(D2OS_Os1aaaaaaaa_VS)" in content
    assert build.notes == [
        "1 option sets a question binds are absent from the option-set selection; their answerValueSet "
        "names are derived from the UID: Os1aaaaaaaa"
    ]


@respx.mock
async def test_the_questionnaire_target_plans_option_set_names_over_the_whole_selection(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    mock_attributes: Callable[..., None],
    tmp_path: Path,
) -> None:
    """A slug is assigned against its peers, so the target reads every selected set, not just the bound ones."""
    mock_system_info("v42")
    mock_attributes()
    await _scaffold_project(tmp_path, data_sets='"BfMAe6Itzgt"')
    respx.get(f"{_HOST}/api/dataSets").mock(return_value=httpx.Response(200, json=_DATA_SETS_PAYLOAD))
    respx.get(f"{_HOST}/api/programs").mock(return_value=httpx.Response(200, json={"programs": []}))
    option_sets = respx.get(f"{_HOST}/api/optionSets").mock(return_value=httpx.Response(200, json=_OPTION_SETS_PAYLOAD))

    report = await service.generate_questionnaires(resolve_profile("probe"), load_project(tmp_path))

    assert option_sets.called
    assert option_sets.calls.last.request.url.params["fields"] == "id,name"
    assert report.notes == []
    content = (tmp_path / "ig" / "input" / "fsh" / "data-sets" / "BfMAe6Itzgt.fsh").read_text(encoding="utf-8")
    assert "* item[=].item[=].answerValueSet = Canonical(D2OS_Os1aaaaaaaa_VS)" in content
