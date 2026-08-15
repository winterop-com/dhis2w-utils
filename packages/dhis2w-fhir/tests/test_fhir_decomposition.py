"""The category decomposition every category option combo concept carries, in both concept-code modes.

The data is the DHIS2 demo instance's own: the "Location and age group" combo splits over two
categories, so "Fixed, <1y" is the one combo that proves the axes are emitted in the combo's own
order and that a two-axis cell states both parts. The Outreach option carries a line break inside
its DHIS2 code, which is no valid FHIR `code`, so a code-mode run falls back to the UID there and
the coding into that category has to name the very code its CodeSystem holds.
"""

from __future__ import annotations

import pytest
from dhis2w_fhir import (
    GenerateConfig,
    build_attribute_combo_artifacts,
    build_category_artifacts,
    build_category_decomposition,
    build_data_dictionary_documents,
)
from dhis2w_fhir.attributes import AttributeCodeIndex
from dhis2w_fhir.config import NamingConfig
from dhis2w_fhir.r4 import CodeSystem
from dhis2w_fhir.resources.categories.schemas import CategoryIn
from dhis2w_fhir.resources.option_sets.schemas import OptionIn
from dhis2w_fhir.resources.questionnaires.schemas import (
    CategoryAxisIn,
    CategoryComboIn,
    CategoryOptionComboIn,
    QuestionnaireItemIn,
    QuestionnaireSourceIn,
)

_CANONICAL = "http://localhost:8080/fhir"

_LOCATION = CategoryIn(
    uid="fMZEcRHuamy",
    code="LOC_FIX_OUTREACH",
    name="Location Fixed/Outreach",
    options=[
        OptionIn(uid="qkPbeWaFsnU", code="FIXED", name="Fixed", sort_order=0),
        OptionIn(uid="wbrDrL2aYEc", code="OUTREACH\nOUTREACH", name="Outreach", sort_order=1),
    ],
)

_AGE = CategoryIn(
    uid="YNZyaJHiHYq",
    code="EPI_NUTR_AGE",
    name="EPI/nutrition age",
    options=[
        OptionIn(uid="btOyqprQ9e8", code="<1y", name="<1y", sort_order=0),
        OptionIn(uid="GEqzEKCHoGA", code=">1y", name=">1y", sort_order=1),
    ],
)

_PROJECT = CategoryIn(
    uid="yY2bQYqNt0o",
    code="PROJECT",
    name="Project",
    options=[
        OptionIn(uid="i4Nbp8S2G6A", code="Project01", name="Improve access to clean water", sort_order=0),
        OptionIn(uid="OUUdG3sdOqb", code="Project02", name="Provide access to primary health care", sort_order=1),
    ],
)

#: The disaggregation the demo instance reads location first and age group second.
_LOCATION_AND_AGE = CategoryComboIn(
    uid="dzjKKQq0cSO",
    name="Location and age group",
    categories=[
        CategoryAxisIn(uid="fMZEcRHuamy", option_uids=["qkPbeWaFsnU", "wbrDrL2aYEc"]),
        CategoryAxisIn(uid="YNZyaJHiHYq", option_uids=["btOyqprQ9e8", "GEqzEKCHoGA"]),
    ],
    option_combos=[
        CategoryOptionComboIn(
            uid="Prlt0C1RF0s",
            name="Fixed, <1y",
            code="COC_292",
            category_option_uids=["btOyqprQ9e8", "qkPbeWaFsnU"],
        ),
        CategoryOptionComboIn(
            uid="hEFKSsPV5et",
            name="Outreach, >1y",
            code="COC_289",
            category_option_uids=["GEqzEKCHoGA", "wbrDrL2aYEc"],
        ),
    ],
)

#: The data set's own key: one axis, so an attribute option combo names exactly one category option.
_PROJECT_COMBO = CategoryComboIn(
    uid="idcDPkDtepR",
    code="COMBO_PROJECT",
    name="Project",
    categories=[CategoryAxisIn(uid="yY2bQYqNt0o", option_uids=["i4Nbp8S2G6A", "OUUdG3sdOqb"])],
    option_combos=[
        CategoryOptionComboIn(
            uid="pO5CEqK6c1s",
            name="Improve access to clean water",
            code="COC_1452092",
            category_option_uids=["i4Nbp8S2G6A"],
        ),
        CategoryOptionComboIn(
            uid="BqblOcSwGey",
            name="Provide access to primary health care",
            code="COC_1452093",
            category_option_uids=["OUUdG3sdOqb"],
        ),
    ],
)

_SOURCE = QuestionnaireSourceIn(
    uid="BfMAe6Itzgt",
    name="Child Health",
    kind="aggregate",
    period_type="Monthly",
    attribute_combo=_PROJECT_COMBO,
    flat_items=[
        QuestionnaireItemIn(
            uid="s46m5MS0hxu",
            name="BCG doses given",
            value_type="INTEGER",
            domain_type="AGGREGATE",
            category_combo=_LOCATION_AND_AGE,
        )
    ],
)

_CATEGORIES = [_AGE, _LOCATION, _PROJECT]


def _id_mode() -> GenerateConfig:
    """The default run: every concept code is the DHIS2 UID and every slug is the UID too."""
    return GenerateConfig()


def _code_mode() -> GenerateConfig:
    """A run keyed on the DHIS2 codes: concept codes and identity slugs both come off the code."""
    return GenerateConfig(concept_code_source="code", naming=NamingConfig(source="code-or-id"))


def _attribute_combo_code_system(config: GenerateConfig, categories: list[CategoryIn]) -> CodeSystem:
    """The one attribute-option-combo CodeSystem the source's data set publishes."""
    decomposition = build_category_decomposition([_SOURCE], categories, config, _CANONICAL)
    build = build_attribute_combo_artifacts(
        [_SOURCE], config, _CANONICAL, ig_status="draft", decomposition=decomposition
    )
    documents = [
        CodeSystem.model_validate_json(artifact.content)
        for artifact in build.artifacts
        if artifact.relative_path.rsplit("/", 1)[-1].startswith("CodeSystem-")
    ]
    return documents[0]


def _option_combo_code_system(config: GenerateConfig, categories: list[CategoryIn]) -> CodeSystem:
    """The data dictionary's category-option-combo CodeSystem, over the cells the question splits into."""
    decomposition = build_category_decomposition([_SOURCE], categories, config, _CANONICAL)
    build = build_data_dictionary_documents(
        [_SOURCE], config, _CANONICAL, ig_status="draft", decomposition=decomposition
    )
    return next(code_system for code_system in build.code_systems if str(code_system.id).endswith("-coc-cs"))


def _properties(code_system: CodeSystem, concept_code: str) -> list[tuple[str, str, str, str]]:
    """One concept's category properties as (property code, system, code, display), in emission order."""
    concept = next(entry for entry in code_system.concept or [] if entry.code == concept_code)
    return [
        (
            str(concept_property.code),
            str(concept_property.valueCoding.system),
            str(concept_property.valueCoding.code),
            str(concept_property.valueCoding.display),
        )
        for concept_property in concept.property or []
        if concept_property.valueCoding is not None
    ]


def test_an_attribute_option_combo_states_the_category_option_it_is() -> None:
    """A single-axis attribute option combo carries one coding into its category's own CodeSystem."""
    code_system = _attribute_combo_code_system(_id_mode(), _CATEGORIES)

    assert _properties(code_system, "pO5CEqK6c1s") == [
        (
            "category-yY2bQYqNt0o",
            f"{_CANONICAL}/CodeSystem/d2-cat-yY2bQYqNt0o-cs",
            "i4Nbp8S2G6A",
            "Improve access to clean water",
        )
    ]


def test_a_two_axis_cell_states_both_parts_in_the_combos_own_order() -> None:
    """The Fixed-under-one-year cell reads location then age group, the order its combo splits over."""
    code_system = _option_combo_code_system(_id_mode(), _CATEGORIES)

    assert _properties(code_system, "Prlt0C1RF0s") == [
        ("category-fMZEcRHuamy", f"{_CANONICAL}/CodeSystem/d2-cat-fMZEcRHuamy-cs", "qkPbeWaFsnU", "Fixed"),
        ("category-YNZyaJHiHYq", f"{_CANONICAL}/CodeSystem/d2-cat-YNZyaJHiHYq-cs", "btOyqprQ9e8", "<1y"),
    ]


def test_a_code_mode_run_codes_the_axes_the_way_its_category_code_system_does() -> None:
    """Concept codes are DHIS2 codes, so the coding names the option's code and the slug names the category's."""
    code_system = _attribute_combo_code_system(_code_mode(), _CATEGORIES)

    assert _properties(code_system, "COC_1452092") == [
        (
            "category-PROJECT",
            f"{_CANONICAL}/CodeSystem/d2-cat-PROJECT-cs",
            "Project01",
            "Improve access to clean water",
        )
    ]


def test_an_option_whose_dhis2_code_is_no_fhir_code_is_named_by_the_uid_its_category_gave_it() -> None:
    """The Outreach option carries a line break in its DHIS2 code, so its category coded it by UID."""
    code_system = _option_combo_code_system(_code_mode(), _CATEGORIES)

    assert _properties(code_system, "hEFKSsPV5et") == [
        # `LOC_FIX_OUTREACH` is no FHIR id either, so the category's own slug is its UID.
        ("category-fMZEcRHuamy", f"{_CANONICAL}/CodeSystem/d2-cat-fMZEcRHuamy-cs", "wbrDrL2aYEc", "Outreach"),
        ("category-YNZyaJHiHYq", f"{_CANONICAL}/CodeSystem/d2-cat-YNZyaJHiHYq-cs", ">1y", ">1y"),
    ]


@pytest.mark.parametrize("config_name", ["id", "code"])
def test_every_emitted_coding_names_a_concept_the_category_code_system_really_holds(config_name: str) -> None:
    """The decomposition and the category pair read one assignment plan, so a coding can never dangle."""
    config = _id_mode() if config_name == "id" else _code_mode()
    published = {
        str(CodeSystem.model_validate_json(artifact.content).url): {
            str(concept.code) for concept in CodeSystem.model_validate_json(artifact.content).concept or []
        }
        for artifact in build_category_artifacts(
            _CATEGORIES, config, _CANONICAL, ig_status="draft", attribute_codes=AttributeCodeIndex()
        ).artifacts
        if artifact.relative_path.rsplit("/", 1)[-1].startswith("CodeSystem-")
    }
    code_system = _option_combo_code_system(config, _CATEGORIES)

    for concept in code_system.concept or []:
        for concept_property in concept.property or []:
            if concept_property.valueCoding is None:
                continue
            assert str(concept_property.valueCoding.code) in published[str(concept_property.valueCoding.system)]


def test_the_declarations_name_the_categories_the_concepts_decompose_over() -> None:
    """A reader of the CodeSystem alone learns which axis each property is, and that it is a coding."""
    code_system = _option_combo_code_system(_id_mode(), _CATEGORIES)

    declared = [
        (str(entry.code), str(entry.description), str(entry.type), str(entry.uri))
        for entry in code_system.property or []
        if str(entry.code).startswith("category-")
    ]
    assert declared == [
        (
            "category-YNZyaJHiHYq",
            "DHIS2 category EPI/nutrition age.",
            "Coding",
            "http://dhis2.org/fhir/property/category-YNZyaJHiHYq",
        ),
        (
            "category-fMZEcRHuamy",
            "DHIS2 category Location Fixed/Outreach.",
            "Coding",
            "http://dhis2.org/fhir/property/category-fMZEcRHuamy",
        ),
    ]


def test_a_category_the_run_does_not_publish_carries_no_property_and_is_reported() -> None:
    """A coding into a CodeSystem nobody wrote states nothing, so the axis is dropped and the run says so."""
    decomposition = build_category_decomposition([_SOURCE], [_LOCATION, _PROJECT], _id_mode(), _CANONICAL)
    code_system = _option_combo_code_system(_id_mode(), [_LOCATION, _PROJECT])

    assert _properties(code_system, "Prlt0C1RF0s") == [
        ("category-fMZEcRHuamy", f"{_CANONICAL}/CodeSystem/d2-cat-fMZEcRHuamy-cs", "qkPbeWaFsnU", "Fixed")
    ]
    assert [note.message for note in decomposition.notes] == [
        "1 categories a published category option combo splits over are not published; those combos "
        "state no property for them: YNZyaJHiHYq"
    ]


def test_the_default_category_combo_is_not_walked_at_all() -> None:
    """Neither vocabulary publishes it, so its option combo raises no axis and no gap to report."""
    default_combo = CategoryComboIn(
        uid="bjDvmb4bfuf",
        name="default",
        is_default=True,
        categories=[CategoryAxisIn(uid="GLevLNI9wkl", option_uids=["xYerKDKCefk"])],
        option_combos=[CategoryOptionComboIn(uid="HllvX50cXC0", name="default", category_option_uids=["xYerKDKCefk"])],
    )
    source = _SOURCE.model_copy(
        update={
            "flat_items": [
                QuestionnaireItemIn(
                    uid="s46m5MS0hxu",
                    name="BCG doses given",
                    value_type="INTEGER",
                    domain_type="AGGREGATE",
                    category_combo=default_combo,
                )
            ]
        }
    )
    decomposition = build_category_decomposition([source], _CATEGORIES, _id_mode(), _CANONICAL)

    assert [entry.option_combo_uid for entry in decomposition.compositions] == sorted(
        option_combo.uid for option_combo in _PROJECT_COMBO.option_combos
    )
    assert decomposition.notes == []


def test_a_run_without_a_decomposition_publishes_the_combos_own_code_alone() -> None:
    """The vocabularies stand on their own: a caller that states no decomposition emits what it always did."""
    build = build_data_dictionary_documents([_SOURCE], _id_mode(), _CANONICAL, ig_status="draft")
    code_system = next(entry for entry in build.code_systems if str(entry.id).endswith("-coc-cs"))

    assert [str(entry.code) for entry in code_system.property or []] == ["dhis2-code"]
    assert _properties(code_system, "Prlt0C1RF0s") == []
