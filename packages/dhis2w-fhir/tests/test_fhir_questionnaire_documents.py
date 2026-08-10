"""Unit tests for the Questionnaire document builder: the element-by-element JSON twin of the FSH target.

The compiled goldens in `test_fhir_questionnaire_parity.py` pin the shapes the local DHIS2 stack
actually produces. These tests pin the shapes it does not - a decimal bound, a repeating
`MULTI_TEXT` question, a form name holding markup, an option set the identity plan omits.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from dhis2w_fhir import (
    FORM_KIND_PROFILES,
    ITEM_TYPES_BY_VALUE_TYPE,
    PROGRAM_IDENTIFIER_SEGMENT,
    AttributeCodeIndex,
    AttributeValueIn,
    CategoryComboIn,
    CategoryOptionComboIn,
    GenerateConfig,
    NamingConfig,
    OptionSetIdentityPlan,
    OptionSetIn,
    ProgramContextIn,
    QuestionnaireItemIn,
    QuestionnaireSectionIn,
    QuestionnaireSourceIn,
    build_data_dictionary_documents,
    build_foundation_artifacts,
    build_questionnaire_documents,
    option_set_identities,
)
from dhis2w_fhir.r4 import FhirBase, Questionnaire, QuestionnaireItem
from dhis2w_fhir.status import IgStatus

_CANONICAL = "http://example.org/fhir"
_IDENTIFIER_BASE = "http://dhis2.org/fhir/id"

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

#: A data element DHIS2 codes, beside `_GENDER` which it does not - the pair the data dictionary's
#: `dhis2-code` property is written for and left off for.
_BCG = QuestionnaireItemIn(
    uid="De1aaaaaaaa",
    name="BCG doses given",
    code="DE_BCG_DOSES",
    form_name="BCG",
    value_type="INTEGER_ZERO_OR_POSITIVE",
    domain_type="AGGREGATE",
    category_combo=_DEFAULT_COMBO,
)
_MEASLES = QuestionnaireItemIn(
    uid="De2aaaaaaaa",
    name="Measles doses given",
    value_type="INTEGER",
    domain_type="AGGREGATE",
    required_option_combo_uids=["Coc1aaaaaaa"],
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
    flat_items=[_MEASLES],
)

_CHILD_PROGRAMME = ProgramContextIn(uid="IpHINAT79UW", name="Child Programme")

_STAGE = QuestionnaireSourceIn(
    uid="A03MvHHogjR",
    name="Birth",
    code="PS_BIRTH",
    kind="tracker-event",
    program=_CHILD_PROGRAMME,
    flat_items=[_GENDER],
)


def _build(
    sources: list[QuestionnaireSourceIn],
    config: GenerateConfig | None = None,
    *,
    ig_status: IgStatus = "draft",
    option_set_plan: OptionSetIdentityPlan | None = None,
    attribute_codes: AttributeCodeIndex | None = None,
) -> tuple[dict[str, Questionnaire], list[str]]:
    """Build the documents for the given forms and index them by resource id, with the notes raised."""
    resolved = config or GenerateConfig()
    build = build_questionnaire_documents(
        sources,
        resolved,
        _CANONICAL,
        ig_status=ig_status,
        option_set_plan=option_set_plan or _bound_plan(sources, resolved),
        attribute_codes=attribute_codes or AttributeCodeIndex(),
    )
    return {str(questionnaire.id): questionnaire for questionnaire in build.questionnaires}, [
        note.message for note in build.notes
    ]


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


def _one(source: QuestionnaireSourceIn, **kwargs: Any) -> Questionnaire:
    """Build one form's Questionnaire."""
    return _build([source], **kwargs)[0][source.uid]


def _emitted(resource: FhirBase) -> Any:
    """One built resource as the JSON document it is served as."""
    return json.loads(resource.model_dump_json(exclude_none=True, by_alias=True))


def _items(questionnaire: Questionnaire) -> list[QuestionnaireItem]:
    """The form's top-level items, refusing a form the builder left empty."""
    assert questionnaire.item is not None
    return questionnaire.item


def _children(item: QuestionnaireItem) -> list[QuestionnaireItem]:
    """One group item's children, refusing a group the builder left empty."""
    assert item.item is not None
    return item.item


def test_a_data_set_carries_its_uid_and_its_code_under_the_data_set_identifier_systems() -> None:
    """An aggregate form is identified as a DHIS2 data set, by UID and by code."""
    identifiers = _emitted(_one(_DATA_SET))["identifier"]
    assert identifiers == [
        {"system": f"{_IDENTIFIER_BASE}/data-set", "value": "BfMAe6Itzgt"},
        {"system": f"{_IDENTIFIER_BASE}/data-set-code", "value": "DS_359711"},
    ]


def test_an_event_program_carries_the_program_identifier_systems() -> None:
    """An event form is identified as a DHIS2 program, its code slot repeating the UID when DHIS2 sent none."""
    identifiers = _emitted(_one(_EVENT_PROGRAM))["identifier"]
    assert identifiers == [
        {"system": f"{_IDENTIFIER_BASE}/program", "value": "VBqh0ynB2wv"},
        {"system": f"{_IDENTIFIER_BASE}/program-code", "value": "VBqh0ynB2wv"},
    ]


def test_a_tracker_program_stage_adds_a_third_identifier_naming_its_program() -> None:
    """One search on the program identifier selects every stage of a tracker program."""
    identifiers = _emitted(_one(_STAGE))["identifier"]
    assert identifiers == [
        {"system": f"{_IDENTIFIER_BASE}/program-stage", "value": "A03MvHHogjR"},
        {"system": f"{_IDENTIFIER_BASE}/program-stage-code", "value": "PS_BIRTH"},
        {"system": f"{_IDENTIFIER_BASE}/{PROGRAM_IDENTIFIER_SEGMENT}", "value": "IpHINAT79UW"},
    ]


def test_the_form_kind_is_carried_by_the_extension_and_by_the_code() -> None:
    """A reader learns the DHIS2 form kind from the D2FormType extension and from `Questionnaire.code`."""
    document = _emitted(_one(_STAGE))
    assert document["extension"][0] == {
        "url": f"{_CANONICAL}/StructureDefinition/d2-form-type",
        "valueCode": "tracker-event",
    }
    assert document["code"] == [{"system": f"{_CANONICAL}/CodeSystem/d2-form-type-cs", "code": "tracker-event"}]


def test_a_tracker_program_stage_is_captured_for_a_patient() -> None:
    """A stage form reports one enrolled person's visit; an aggregate form reports for a place."""
    assert _one(_STAGE).subjectType == ["Patient"]
    assert _one(_DATA_SET).subjectType == ["Location"]


def test_the_publication_state_is_derived_from_the_ig_status() -> None:
    """A draft IG publishes draft, experimental questionnaires; an active IG publishes neither."""
    draft = _one(_DATA_SET)
    active = _one(_DATA_SET, ig_status="active")
    assert (draft.status, draft.experimental) == ("draft", True)
    assert (active.status, active.experimental) == ("active", False)


def test_an_attribute_value_becomes_a_coded_d2_attribute_value_extension() -> None:
    """A DHIS2 attribute value carries its UID, the code the run joined, and the value."""
    source = _DATA_SET.model_copy(
        update={"attribute_values": [AttributeValueIn(attribute_uid="Atr1aaaaaaa", value="12A")]}
    )
    document = _emitted(_one(source, attribute_codes=AttributeCodeIndex(codes={"Atr1aaaaaaa": "REGISTER"})))
    assert document["extension"][1] == {
        "url": f"{_CANONICAL}/StructureDefinition/d2-attribute-value",
        "extension": [
            {"url": "attributeId", "valueString": "Atr1aaaaaaa"},
            {"url": "attributeCode", "valueString": "REGISTER"},
            {"url": "value", "valueString": "12A"},
        ],
    }


def test_an_uncoded_attribute_gets_no_attribute_code_sub_extension() -> None:
    """DHIS2 codes few of its attributes, and an empty code would claim it coded this one."""
    source = _DATA_SET.model_copy(
        update={"attribute_values": [AttributeValueIn(attribute_uid="Atr1aaaaaaa", value="12A")]}
    )
    nested = _emitted(_one(source))["extension"][1]["extension"]
    assert [entry["url"] for entry in nested] == ["attributeId", "value"]


def test_a_section_becomes_a_group_item_holding_its_questions() -> None:
    """The form's sections are the top-level items, and the questions nest under the section they belong to."""
    items = _items(_one(_DATA_SET))
    assert [(item.linkId, item.text, item.type) for item in items] == [
        ("Sec1aaaaaaa", "Immunization", "group"),
        ("Sec2aaaaaaa", "Demographics", "group"),
    ]
    assert [child.linkId for child in _children(items[0])] == ["De1aaaaaaaa", "De2aaaaaaaa"]


def test_a_section_holding_a_disaggregated_question_renders_as_a_grid() -> None:
    """A section of per-combo cells is a table; a section of plain questions carries no item control."""
    items = _items(_one(_DATA_SET))
    assert _emitted(items[0])["extension"] == [
        {
            "url": "http://hl7.org/fhir/StructureDefinition/questionnaire-itemControl",
            "valueCodeableConcept": {
                "coding": [{"system": "http://hl7.org/fhir/questionnaire-item-control", "code": "gtable"}]
            },
        }
    ]
    assert items[1].extension is None


def test_a_disaggregated_question_becomes_a_group_of_one_cell_per_option_combo() -> None:
    """Each cell asks the element's question for one category option combo, coded from the combo CodeSystem."""
    group = _children(_items(_one(_DATA_SET))[0])[1]
    assert (group.type, group.linkId) == ("group", "De2aaaaaaaa")
    cells = _emitted(group)["item"]
    assert [cell["linkId"] for cell in cells] == ["De2aaaaaaaa.Coc1aaaaaaa", "De2aaaaaaaa.Coc2aaaaaaa"]
    assert cells[0]["code"] == [
        {"system": f"{_CANONICAL}/CodeSystem/d2-coc-cs", "code": "Coc1aaaaaaa", "display": "<1y"}
    ]
    assert cells[0]["text"] == "<1y"
    assert cells[0]["type"] == "integer"


def test_only_the_cells_a_compulsory_operand_names_are_required() -> None:
    """A data set marks single cells mandatory, and the sibling cells stay optional rather than required false."""
    cells = _emitted(_children(_items(_one(_DATA_SET))[0])[1])["item"]
    assert cells[0]["required"] is True
    assert "required" not in cells[1]


def test_a_question_that_is_not_compulsory_carries_no_required_element() -> None:
    """`required` is written only when it is true - FHIR's own default is false."""
    assert "required" not in _emitted(_children(_items(_one(_DATA_SET))[0])[0])


def test_a_compulsory_question_is_required() -> None:
    """A data element the form marks compulsory asks a mandatory question."""
    item = _BCG.model_copy(update={"compulsory": True})
    source = _EVENT_PROGRAM.model_copy(update={"flat_items": [item]})
    assert _emitted(_items(_one(source))[0])["required"] is True


def test_an_event_question_stays_flat_whatever_category_combo_its_element_declares() -> None:
    """An event data value has no categoryOptionCombo slot, so an event form must not ask a per-cell question."""
    item = _items(_one(_EVENT_PROGRAM))[0]
    assert (item.linkId, item.type) == ("De2aaaaaaaa", "integer")
    assert item.item is None


def test_an_event_form_disaggregates_nothing_into_the_data_dictionary() -> None:
    """A combo only an event form's element declares is never referenced, so no combo pair is published."""
    build = build_data_dictionary_documents([_EVENT_PROGRAM], GenerateConfig(), _CANONICAL, ig_status="draft")
    assert [str(code_system.id) for code_system in build.code_systems] == ["d2-de-cs"]
    assert [str(value_set.id) for value_set in build.value_sets] == ["d2-de-vs"]


def test_an_option_set_bound_question_is_answered_from_the_absolute_value_set_url() -> None:
    """A `#choice` names the ValueSet the same run publishes, at the URL it is published under."""
    item = _emitted(_items(_one(_STAGE))[0])
    assert item["type"] == "choice"
    assert item["answerValueSet"] == f"{_CANONICAL}/ValueSet/d2-os-Os1aaaaaaaa-vs"


def test_an_option_set_the_plan_omits_falls_back_to_the_uid_name_with_one_note() -> None:
    """A bound set outside the selection still resolves, and the run says so rather than emitting a dangling name."""
    questionnaires, notes = _build([_STAGE], option_set_plan=OptionSetIdentityPlan())
    item = _emitted(_items(questionnaires["A03MvHHogjR"])[0])
    assert item["answerValueSet"] == f"{_CANONICAL}/ValueSet/d2-os-Os1aaaaaaaa-vs"
    assert notes == [
        "1 option sets a question binds are absent from the option-set selection; "
        "their answerValueSet names are derived from the UID: Os1aaaaaaaa"
    ]


def test_a_bounded_integer_value_type_carries_its_range_on_value_integer() -> None:
    """An integer question's bounds land on `valueInteger`, the element its item type asks for."""
    item = QuestionnaireItemIn(uid="De4aaaaaaaa", name="Doses", value_type="INTEGER_POSITIVE")
    source = _EVENT_PROGRAM.model_copy(update={"flat_items": [item]})
    assert _emitted(_items(_one(source))[0])["extension"] == [
        {"url": "http://hl7.org/fhir/StructureDefinition/minValue", "valueInteger": 1}
    ]


def test_a_bounded_decimal_value_type_carries_its_range_on_value_decimal() -> None:
    """A percentage answers as a decimal, so its 0-100 range lands on `valueDecimal`."""
    item = QuestionnaireItemIn(uid="De5aaaaaaaa", name="Coverage", value_type="PERCENTAGE")
    source = _EVENT_PROGRAM.model_copy(update={"flat_items": [item]})
    assert _emitted(_items(_one(source))[0])["extension"] == [
        {"url": "http://hl7.org/fhir/StructureDefinition/minValue", "valueDecimal": 0},
        {"url": "http://hl7.org/fhir/StructureDefinition/maxValue", "valueDecimal": 100},
    ]


def test_an_option_set_bound_question_takes_no_numeric_bounds() -> None:
    """A `#choice` has no numeric element to constrain, whatever value type the element declares."""
    item = QuestionnaireItemIn(
        uid="De6aaaaaaaa", name="Doses", value_type="INTEGER_POSITIVE", option_set_uid="Os1aaaaaaaa"
    )
    source = _EVENT_PROGRAM.model_copy(update={"flat_items": [item]})
    assert _items(_one(source))[0].extension is None


def test_a_multi_text_question_repeats() -> None:
    """`MULTI_TEXT` is multiple selection, so its `#choice` captures several answers."""
    item = QuestionnaireItemIn(
        uid="De7aaaaaaaa", name="Symptoms", value_type="MULTI_TEXT", option_set_uid="Os1aaaaaaaa"
    )
    source = _EVENT_PROGRAM.model_copy(update={"flat_items": [item]})
    assert _emitted(_items(_one(source))[0])["repeats"] is True


def test_a_single_valued_question_carries_no_repeats_element() -> None:
    """`repeats` is written only when it is true - FHIR's own default is false."""
    assert "repeats" not in _emitted(_items(_one(_STAGE))[0])


def test_the_title_carries_the_dhis2_name_verbatim_while_the_description_escapes_markup() -> None:
    """The title is data and keeps its `<`; the description is page furniture the publisher parses as HTML."""
    source = _EVENT_PROGRAM.model_copy(update={"name": "Mortality < 5 years"})
    document = _emitted(_one(source))
    assert document["title"] == "Mortality < 5 years"
    assert document["description"] == (
        "DHIS2 event program Mortality &lt; 5 years (VBqh0ynB2wv) as a data capture form."
    )


def test_a_tracker_program_stage_title_and_description_carry_both_identities() -> None:
    """A stage is shown under its program's name too - a bare 'Birth' names nothing on its own."""
    document = _emitted(_one(_STAGE))
    assert document["title"] == "Child Programme - Birth"
    assert document["description"] == (
        "DHIS2 tracker program stage Birth (A03MvHHogjR) of program Child Programme (IpHINAT79UW) "
        "as a data capture form."
    )


def test_a_form_holding_no_data_elements_carries_no_item_element() -> None:
    """A degenerate DHIS2 form is still a Questionnaire; FHIR has no empty collection to write."""
    source = QuestionnaireSourceIn(uid="Ds1aaaaaaaa", name="Empty", kind="aggregate")
    document = _emitted(_one(source))
    assert "item" not in document
    assert document["name"] == "D2DS_Ds1aaaaaaaa"


def test_a_section_holding_no_data_elements_carries_no_item_element() -> None:
    """An empty section is still a group, with nothing nested under it."""
    source = QuestionnaireSourceIn(
        uid="Ds1aaaaaaaa",
        name="Empty",
        kind="aggregate",
        sections=[QuestionnaireSectionIn(uid="Sec1aaaaaaa", name="Nothing")],
    )
    assert "item" not in _emitted(_one(source))["item"][0]


def test_the_naming_tokens_flow_into_the_names_and_the_support_ids() -> None:
    """Every emitted name and id is derived from `[generate.naming]`, never hard-coded."""
    config = GenerateConfig(naming=NamingConfig(prefix="Dhis", data_set="Set"))
    questionnaires, _ = _build([_DATA_SET], config)
    assert questionnaires["BfMAe6Itzgt"].name == "DhisSet_BfMAe6Itzgt"
    build = build_data_dictionary_documents([_DATA_SET], config, _CANONICAL, ig_status="draft")
    assert [str(code_system.id) for code_system in build.code_systems] == ["dhis-de-cs", "dhis-coc-cs"]
    assert [code_system.name for code_system in build.code_systems] == ["DhisDE_CS", "DhisCOC_CS"]


def test_the_data_element_code_system_declares_only_the_properties_its_concepts_carry() -> None:
    """A property no concept carries is left undeclared - the domain and the DHIS2 code alike."""
    with_domain = build_data_dictionary_documents([_DATA_SET], GenerateConfig(), _CANONICAL, ig_status="draft")
    assert [entry["code"] for entry in _emitted(with_domain.code_systems[0])["property"]] == [
        "dhis2-code",
        "domain",
        "value-type",
    ]
    without = build_data_dictionary_documents([_STAGE], GenerateConfig(), _CANONICAL, ig_status="draft")
    assert [entry["code"] for entry in _emitted(without.code_systems[0])["property"]] == ["value-type"]


def test_a_concept_states_no_dhis2_code_when_dhis2_states_none() -> None:
    """The concept code is already the UID, so a fall-back would publish it twice, once under a wrong label."""
    build = build_data_dictionary_documents([_DATA_SET], GenerateConfig(), _CANONICAL, ig_status="draft")
    concepts = {concept["code"]: concept for concept in _emitted(build.code_systems[0])["concept"]}
    coded = [entry for entry in concepts["De1aaaaaaaa"]["property"] if entry["code"] == "dhis2-code"]
    uncoded = [entry for entry in concepts["De3aaaaaaaa"]["property"] if entry["code"] == "dhis2-code"]

    assert coded == [{"code": "dhis2-code", "valueString": "DE_BCG_DOSES"}]
    assert uncoded == []


def test_the_support_value_set_includes_its_whole_code_system() -> None:
    """The pair is a ValueSet over every concept of its CodeSystem, at the URL the CodeSystem is published under."""
    build = build_data_dictionary_documents([_DATA_SET], GenerateConfig(), _CANONICAL, ig_status="draft")
    assert _emitted(build.value_sets[0])["compose"] == {"include": [{"system": f"{_CANONICAL}/CodeSystem/d2-de-cs"}]}


@pytest.mark.parametrize("item_type_code", sorted({*ITEM_TYPES_BY_VALUE_TYPE.values(), "choice", "group"}))
def test_every_item_type_the_target_computes_is_a_code_the_r4_item_accepts(item_type_code: str) -> None:
    """The builder reads a computed item type as an R4 code; the two tables must therefore agree."""
    assert QuestionnaireItem.model_validate({"linkId": "De1aaaaaaaa", "type": item_type_code}).type == item_type_code


@pytest.mark.parametrize("kind", sorted(FORM_KIND_PROFILES))
def test_a_form_kinds_alias_and_its_identifier_segment_name_the_same_system(kind: str) -> None:
    """The FSH path writes the `$DHIS2-*` alias and the JSON path the URL it expands to - one system, two spellings."""
    config = GenerateConfig()
    aliases = _aliases(config)
    profile = FORM_KIND_PROFILES[kind]  # type: ignore[index]
    base = f"{config.identifier_system_base}/id"
    assert f"Alias: {profile.identifier_system} = {base}/{profile.identifier_segment}\n" in aliases
    assert f"Alias: {profile.identifier_code_system} = {base}/{profile.code_identifier_segment}\n" in aliases


def test_the_program_grouping_alias_and_its_segment_name_the_same_system() -> None:
    """A tracker stage's grouping identifier resolves the same way on both paths."""
    config = GenerateConfig()
    base = f"{config.identifier_system_base}/id"
    assert f"Alias: $DHIS2-PROGRAM = {base}/{PROGRAM_IDENTIFIER_SEGMENT}\n" in _aliases(config)


def _aliases(config: GenerateConfig) -> str:
    """The `foundation/d2-aliases.fsh` the run writes, which every FSH identifier system resolves through."""
    artifacts = {
        artifact.relative_path: artifact.content for artifact in build_foundation_artifacts(config, ig_status="draft")
    }
    return artifacts["foundation/d2-aliases.fsh"]
