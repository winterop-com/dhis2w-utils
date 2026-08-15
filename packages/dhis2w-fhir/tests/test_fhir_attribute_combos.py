"""Tests for the attribute-option-combo terminology: the pair, its economy, and the extensions binding it.

A DHIS2 data value set is keyed by `(orgUnit, period, attributeOptionCombo)`, and the third key
comes from the data set's own category combo. The family publishes that key as terminology - one
CodeSystem/ValueSet pair per distinct non-default combo - and binds it in two places: the
Questionnaire declares the vocabulary by canonical, and the response names one concept out of it.

The economy is the assignment target's: a default-combo data set publishes nothing, because
absence already means the default attribute option combo.
"""

from __future__ import annotations

import datetime
import json
from typing import Any

from dhis2w_fhir.attributes import AttributeCodeIndex
from dhis2w_fhir.config import GenerateConfig, NamingConfig
from dhis2w_fhir.resources.attribute_combos import (
    ATTRIBUTE_COMBO_DIRECTORY,
    AttributeComboBuild,
    attribute_combo_concept_map_file_prefix,
    attribute_combo_sources,
    build_attribute_combo_artifacts,
    build_attribute_combo_concept_map_artifacts,
)
from dhis2w_fhir.resources.examples import build_example_artifacts, build_synthetic_responses
from dhis2w_fhir.resources.examples.documents import build_example_documents
from dhis2w_fhir.resources.examples.schemas import ExampleAnswerIn, ExampleResponseIn
from dhis2w_fhir.resources.option_sets.schemas import OptionSetIdentityPlan
from dhis2w_fhir.resources.questionnaires import build_questionnaire_artifacts
from dhis2w_fhir.resources.questionnaires.documents import build_questionnaire_documents
from dhis2w_fhir.resources.questionnaires.schemas import (
    CategoryComboIn,
    CategoryOptionComboIn,
    QuestionnaireItemIn,
    QuestionnaireSourceIn,
)

_CANONICAL = "http://example.org/fhir"

#: The day the synthetic draws are anchored on - a period-typed form resolves its period from it.
_TODAY = datetime.date(2026, 8, 8)

_ITEM = QuestionnaireItemIn(uid="De1aaaaaaaa", name="BCG doses given", value_type="INTEGER")

_PROJECT_COMBO = CategoryComboIn(
    uid="idcDPkDtepR",
    name="Project",
    code="PROJECT",
    is_default=False,
    option_combos=[
        CategoryOptionComboIn(uid="BqblOcSwGey", name="Primary health care", code="COC_1452093"),
        CategoryOptionComboIn(uid="oawMLLH7OjA", name="Basic education", code="COC_1452090"),
    ],
)

_DEFAULT_COMBO = CategoryComboIn(uid="bjDvmb4bfuf", name="default", code="default", is_default=True)

_EPI_STOCK = QuestionnaireSourceIn(
    uid="TuL8IOPzpHh",
    name="EPI Stock",
    code="DS_1149441",
    kind="aggregate",
    period_type="Monthly",
    attribute_combo=_PROJECT_COMBO,
    flat_items=[_ITEM],
)

_SECOND_ON_THE_SAME_COMBO = QuestionnaireSourceIn(
    uid="BfMAe6Itzgt",
    name="Child Health",
    kind="aggregate",
    period_type="Monthly",
    attribute_combo=_PROJECT_COMBO,
    flat_items=[_ITEM],
)

_DEFAULT_DATA_SET = QuestionnaireSourceIn(
    uid="Lpw6GcnTrmS",
    name="Emergency Response",
    kind="aggregate",
    period_type="Monthly",
    attribute_combo=_DEFAULT_COMBO,
    flat_items=[_ITEM],
)

_EVENT_PROGRAM = QuestionnaireSourceIn(
    uid="VBqh0ynB2wv", name="Malaria case registration", kind="event", flat_items=[_ITEM]
)


def _build(sources: list[QuestionnaireSourceIn], config: GenerateConfig | None = None) -> AttributeComboBuild:
    """Run the attribute-combo emitter over one selection of forms."""
    return build_attribute_combo_artifacts(sources, config or GenerateConfig(), _CANONICAL, ig_status="draft")


def _document(build: AttributeComboBuild, index: int = 0) -> dict[str, Any]:
    """One emitted artifact parsed back out of the JSON the sync writes verbatim."""
    parsed: dict[str, Any] = json.loads(build.artifacts[index].content)
    return parsed


def _questionnaire_extensions(
    sources: list[QuestionnaireSourceIn], build: AttributeComboBuild, uid: str
) -> list[dict[str, Any]]:
    """The extensions the JSON questionnaire emitter puts on one form."""
    config = GenerateConfig()
    documents = build_questionnaire_documents(
        sources,
        config,
        _CANONICAL,
        ig_status="draft",
        option_set_plan=OptionSetIdentityPlan(),
        attribute_codes=AttributeCodeIndex(),
        attribute_combos=build.plan,
    )
    questionnaire = next(item for item in documents.questionnaires if item.id == uid)
    emitted: dict[str, Any] = json.loads(questionnaire.model_dump_json(exclude_none=True, by_alias=True))
    extensions: list[dict[str, Any]] = emitted["extension"]
    return extensions


def _questionnaire_fsh(sources: list[QuestionnaireSourceIn], build: AttributeComboBuild, uid: str) -> str:
    """The FSH one form's Questionnaire is written as."""
    config = GenerateConfig()
    fsh = build_questionnaire_artifacts(
        sources,
        config,
        _CANONICAL,
        ig_status="draft",
        option_set_plan=OptionSetIdentityPlan(),
        attribute_codes=AttributeCodeIndex(),
        attribute_combos=build.plan,
    )
    return next(artifact.content for artifact in fsh.artifacts if artifact.relative_path.endswith(f"{uid}.fsh"))


def test_a_non_default_combo_publishes_one_pair_the_form_binds_by_canonical() -> None:
    """The pair is the vocabulary a response draws its attribute option combo from, named on the form."""
    build = _build([_EPI_STOCK])

    assert [artifact.relative_path for artifact in build.artifacts] == [
        f"{ATTRIBUTE_COMBO_DIRECTORY}/CodeSystem-d2-aoc-idcDPkDtepR-cs.json",
        f"{ATTRIBUTE_COMBO_DIRECTORY}/ValueSet-d2-aoc-idcDPkDtepR-vs.json",
    ]
    code_system = _document(build)
    assert code_system["name"] == "D2AOC_idcDPkDtepR_CS"
    assert code_system["count"] == 2
    assert [concept["code"] for concept in code_system["concept"]] == ["BqblOcSwGey", "oawMLLH7OjA"]
    assert code_system["identifier"] == [
        {"system": "http://dhis2.org/fhir/id/category-combo", "value": "idcDPkDtepR"},
        {"system": "http://dhis2.org/fhir/id/category-combo-code", "value": "PROJECT"},
    ]
    value_set = _document(build, 1)
    assert value_set["name"] == "D2AOC_idcDPkDtepR_VS"
    assert value_set["compose"]["include"] == [{"system": f"{_CANONICAL}/CodeSystem/d2-aoc-idcDPkDtepR-cs"}]


def test_every_concept_carries_the_dhis2_code_the_combo_is_written_under() -> None:
    """A forwarder resolving a coding needs the DHIS2 code too, so it rides along as a concept property."""
    code_system = _document(_build([_EPI_STOCK]))

    assert code_system["property"] == [
        {
            "code": "dhis2-code",
            "uri": "http://dhis2.org/fhir/property/dhis2-code",
            "description": "DHIS2 category option combo code.",
            "type": "string",
        }
    ]
    assert [concept["property"][0]["valueString"] for concept in code_system["concept"]] == [
        "COC_1452093",
        "COC_1452090",
    ]


def test_a_default_combo_data_set_publishes_nothing() -> None:
    """Absence means the default attribute option combo, which is what a consumer already assumed."""
    build = _build([_DEFAULT_DATA_SET, _EVENT_PROGRAM])

    assert build.artifacts == []
    assert build.plan.combo_uids == {}
    assert _questionnaire_extensions([_DEFAULT_DATA_SET], build, "Lpw6GcnTrmS") == [
        {"url": f"{_CANONICAL}/StructureDefinition/d2-form-type", "valueCode": "aggregate"},
        {"url": f"{_CANONICAL}/StructureDefinition/d2-period-type", "valueCode": "Monthly"},
    ]


def test_two_data_sets_on_one_combo_share_one_pair() -> None:
    """The pair belongs to the category combo, not to the form, so a shared combo is published once."""
    sources = [_EPI_STOCK, _SECOND_ON_THE_SAME_COMBO]
    build = _build(sources)

    assert len(build.artifacts) == 2
    assert build.plan.combo_uids == {"TuL8IOPzpHh": "idcDPkDtepR", "BfMAe6Itzgt": "idcDPkDtepR"}
    canonical = f"{_CANONICAL}/ValueSet/d2-aoc-idcDPkDtepR-vs"
    for uid in ("TuL8IOPzpHh", "BfMAe6Itzgt"):
        assert {
            "url": f"{_CANONICAL}/StructureDefinition/d2-attribute-option-combos",
            "valueCanonical": canonical,
        } in _questionnaire_extensions(sources, build, uid)


def test_only_an_aggregate_form_contributes_a_combo() -> None:
    """An event data value has no attribute option combo on the wire, so no program publishes one."""
    assert attribute_combo_sources([_EVENT_PROGRAM, _DEFAULT_DATA_SET]) == []
    assert [combo.uid for combo in attribute_combo_sources([_EPI_STOCK, _EVENT_PROGRAM])] == ["idcDPkDtepR"]


def test_the_stem_follows_the_code_naming_source() -> None:
    """A code-sourced run names the pair by the category combo's DHIS2 code, as every family does."""
    config = GenerateConfig(naming=NamingConfig(source="code"))
    build = _build([_EPI_STOCK], config)

    assert [artifact.relative_path for artifact in build.artifacts] == [
        f"{ATTRIBUTE_COMBO_DIRECTORY}/CodeSystem-d2-aoc-PROJECT-cs.json",
        f"{ATTRIBUTE_COMBO_DIRECTORY}/ValueSet-d2-aoc-PROJECT-vs.json",
    ]
    assert _document(build)["name"] == "D2AOC_PROJECT_CS"


def test_the_concept_codes_follow_the_configured_concept_code_source() -> None:
    """With `concept_code_source = "code"` the concept code is the DHIS2 code and the UID rides along."""
    build = _build([_EPI_STOCK], GenerateConfig(concept_code_source="code"))
    code_system = _document(build)

    assert [concept["code"] for concept in code_system["concept"]] == ["COC_1452093", "COC_1452090"]
    assert [concept["property"][0] for concept in code_system["concept"]] == [
        {"code": "dhis2-id", "valueCode": "BqblOcSwGey"},
        {"code": "dhis2-id", "valueCode": "oawMLLH7OjA"},
    ]


def test_the_concept_map_takes_every_concept_back_to_both_dhis2_identifiers() -> None:
    """A forwarder resolves `attributeOptionCombo` from one document, whichever the concept code is."""
    artifacts = build_attribute_combo_concept_map_artifacts(
        [_EPI_STOCK], GenerateConfig(), _CANONICAL, ig_status="draft"
    )

    assert [artifact.relative_path for artifact in artifacts] == ["concept-maps/ConceptMap-d2-aoc-idcDPkDtepR-cm.json"]
    document = json.loads(artifacts[0].content)
    assert [group["target"] for group in document["group"]] == [
        "http://dhis2.org/fhir/id/category-option-combo",
        "http://dhis2.org/fhir/id/category-option-combo-code",
    ]
    assert [(row["code"], row["target"][0]["code"]) for row in document["group"][1]["element"]] == [
        ("BqblOcSwGey", "COC_1452093"),
        ("oawMLLH7OjA", "COC_1452090"),
    ]


def test_the_concept_map_family_sweeps_its_own_file_prefix() -> None:
    """Three families share `concept-maps/`, so each sweeps only the ids its own naming tokens produce."""
    assert attribute_combo_concept_map_file_prefix(GenerateConfig()) == "ConceptMap-d2-aoc-"


def test_the_two_questionnaire_emitters_declare_the_same_vocabulary() -> None:
    """FSH names the ValueSet through `Canonical(...)`, the document path through the URL SUSHI resolves."""
    build = _build([_EPI_STOCK])

    assert (
        "* extension[D2AttributeOptionCombos].valueCanonical = Canonical(D2AOC_idcDPkDtepR_VS)"
        in _questionnaire_fsh([_EPI_STOCK], build, "TuL8IOPzpHh")
    )
    assert {
        "url": f"{_CANONICAL}/StructureDefinition/d2-attribute-option-combos",
        "valueCanonical": f"{_CANONICAL}/ValueSet/d2-aoc-idcDPkDtepR-vs",
    } in _questionnaire_extensions([_EPI_STOCK], build, "TuL8IOPzpHh")


def _synthetic_documents(sources: list[QuestionnaireSourceIn], build: AttributeComboBuild) -> list[dict[str, Any]]:
    """Build three synthetic responses per form and return the documents they emit."""
    config = GenerateConfig()
    synthetic = build_synthetic_responses(sources, [], 3, "ImspTQPwCqd", _TODAY)
    documents = build_example_documents(
        sources,
        synthetic.responses,
        [],
        config,
        _CANONICAL,
        option_set_plan=OptionSetIdentityPlan(),
        attribute_combos=build.plan,
    )
    return [json.loads(response.model_dump_json(exclude_none=True, by_alias=True)) for response in documents.responses]


def _combo_codings(documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The D2AttributeOptionCombo coding each response carries, in emission order."""
    return [
        extension["valueCoding"]
        for document in documents
        for extension in document["extension"]
        if extension["url"] == f"{_CANONICAL}/StructureDefinition/d2-attribute-option-combo"
    ]


def test_a_synthetic_response_draws_a_valid_combo_deterministically() -> None:
    """The draw comes off a seeded stream, so the same instance state yields the same corpus twice."""
    build = _build([_EPI_STOCK])
    codings = _combo_codings(_synthetic_documents([_EPI_STOCK], build))

    assert len(codings) == 3
    assert {coding["system"] for coding in codings} == {f"{_CANONICAL}/CodeSystem/d2-aoc-idcDPkDtepR-cs"}
    assert {coding["code"] for coding in codings} <= {"BqblOcSwGey", "oawMLLH7OjA"}
    assert codings == _combo_codings(_synthetic_documents([_EPI_STOCK], build))


def test_a_synthetic_response_on_the_default_combo_carries_no_extension() -> None:
    """A default-combo form publishes no vocabulary, so there is nothing for a response to name."""
    build = _build([_DEFAULT_DATA_SET])

    assert _combo_codings(_synthetic_documents([_DEFAULT_DATA_SET], build)) == []


def test_an_instance_sourced_response_carries_the_combo_it_was_captured_under() -> None:
    """The instance path already groups by the full data-value key, so the third key travels onto the response."""
    build = _build([_EPI_STOCK])
    config = GenerateConfig()
    response = ExampleResponseIn(
        instance_id="TuL8IOPzpHh-202607-ImspTQPwCqd",
        target_uid="TuL8IOPzpHh",
        kind="aggregate",
        organisation_unit_uid="ImspTQPwCqd",
        status_code="completed",
        attribute_option_combo_uid="oawMLLH7OjA",
        answers=[ExampleAnswerIn(data_element_uid="De1aaaaaaaa", value="12")],
    )
    documents = build_example_documents(
        [_EPI_STOCK],
        [response],
        [],
        config,
        _CANONICAL,
        option_set_plan=OptionSetIdentityPlan(),
        attribute_combos=build.plan,
    )
    fsh = build_example_artifacts(
        [_EPI_STOCK],
        [response],
        [],
        config,
        _CANONICAL,
        option_set_plan=OptionSetIdentityPlan(),
        attribute_combos=build.plan,
    )

    assert _combo_codings([json.loads(documents.responses[0].model_dump_json(exclude_none=True, by_alias=True))]) == [
        {
            "system": f"{_CANONICAL}/CodeSystem/d2-aoc-idcDPkDtepR-cs",
            "code": "oawMLLH7OjA",
            "display": "Basic education",
        }
    ]
    assert (
        '* extension[D2AttributeOptionCombo].valueCoding = D2AOC_idcDPkDtepR_CS#oawMLLH7OjA "Basic education"'
        in fsh.artifacts[0].content
    )
