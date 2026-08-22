"""Tests for the identifier namespaces a guide's ConceptMaps target, published as complete CodeSystems.

A DHIS2 identifier namespace declared only as a NamingSystem answers no `$validate-code`, so the IG
publisher asks a terminology server about every mapped identifier one un-batched request at a time
and is told UNKNOWN_CODESYSTEM every time. The contract asserted here is what stops that: every
namespace a map targets also exists as a CodeSystem at the same URL, marked `complete`, listing
every identifier the maps put in it.
"""

from __future__ import annotations

import json
from typing import Any

from dhis2w_fhir.config import GenerateConfig, NamingConfig
from dhis2w_fhir.foundation import build_naming_system_declarations
from dhis2w_fhir.r4 import ConceptMap, ConceptMapGroup, ConceptMapGroupElement, ConceptMapGroupElementTarget
from dhis2w_fhir.resources.attribute_combos import (
    build_attribute_combo_concept_maps,
    build_attribute_combo_identifier_artifacts,
)
from dhis2w_fhir.resources.categories import build_category_concept_maps, build_category_identifier_artifacts
from dhis2w_fhir.resources.categories.schemas import CategoryIn
from dhis2w_fhir.resources.identifier_terminology import (
    build_identifier_code_system_artifacts,
    build_identifier_code_systems,
)
from dhis2w_fhir.resources.option_sets import build_option_set_concept_maps, build_option_set_identifier_artifacts
from dhis2w_fhir.resources.option_sets.schemas import OptionIn, OptionSetIn
from dhis2w_fhir.resources.questionnaires.schemas import (
    CategoryComboIn,
    CategoryOptionComboIn,
    QuestionnaireItemIn,
    QuestionnaireSourceIn,
)

_CANONICAL = "http://example.org/fhir"

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

_EPI_STOCK = QuestionnaireSourceIn(
    uid="TuL8IOPzpHh",
    name="EPI Stock",
    code="DS_1149441",
    kind="aggregate",
    period_type="Monthly",
    attribute_combo=_PROJECT_COMBO,
    flat_items=[QuestionnaireItemIn(uid="De1aaaaaaaa", name="BCG doses given", value_type="INTEGER")],
)

_BIRTH_TYPE = OptionSetIn(
    uid="Xa1b2c3d4e5",
    code="birth-type",
    name="Birth type",
    options=[
        OptionIn(uid="EBE0c8sZazS", code="CS", name="Scheduled Cesarean", sort_order=2),
        OptionIn(uid="kRRUtYaGett", code="NB", name="Natural Birth", sort_order=1),
        OptionIn(uid="GVcG84DTFOB", code=None, name="Unplanned Cesarean", sort_order=3),
    ],
)

_DELIVERY_PLACE = OptionSetIn(
    uid="Ya1b2c3d4e5",
    code="delivery-place",
    name="Delivery place",
    options=[OptionIn(uid="Dp1aaaaaaaa", code="HOME", name="At home", sort_order=1)],
)

_SEX = CategoryIn(
    uid="O5P6e8yu1T6",
    code="sex",
    name="Sex",
    options=[
        OptionIn(uid="TNYQzTHdoxL", code="F", name="Female", sort_order=0),
        OptionIn(uid="apsOixVZlf1", code="M", name="Male", sort_order=1),
    ],
)

_AGE = CategoryIn(
    uid="P5P6e8yu1T6",
    code="age",
    name="Age",
    options=[
        OptionIn(uid="TNYQzTHdoxL", code="F", name="Female", sort_order=0),
        OptionIn(uid="Ag1aaaaaaaa", code="U5", name="Under five", sort_order=1),
    ],
)


#: Two option sets whose options carry one DHIS2 code between them, which a real instance does:
#: a diagnosis coded `Preeclampsia` belongs to as many sets as ask the question.
_FIRST_DIAGNOSIS = OptionSetIn(
    uid="Dg1aaaaaaaa",
    code="diagnosis-antenatal",
    name="Antenatal diagnosis",
    options=[OptionIn(uid="Op1aaaaaaaa", code="Preeclampsia", name="Preeclampsia", sort_order=1)],
)

_SECOND_DIAGNOSIS = OptionSetIn(
    uid="Dg2aaaaaaaa",
    code="diagnosis-delivery",
    name="Delivery diagnosis",
    options=[OptionIn(uid="Op2aaaaaaaa", code="Preeclampsia", name="Preeclampsia", sort_order=1)],
)


def _option_set_systems(config: GenerateConfig) -> list[dict[str, Any]]:
    """The identifier CodeSystems one option-set selection emits, parsed back from the files it writes."""
    return [
        json.loads(artifact.content)
        for artifact in build_option_set_identifier_artifacts(
            [_BIRTH_TYPE, _DELIVERY_PLACE], config, _CANONICAL, ig_status="draft"
        )
    ]


def _by_url(documents: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Index emitted CodeSystems by the namespace URL each one enumerates."""
    return {document["url"]: document for document in documents}


def test_every_namespace_an_option_set_map_targets_gets_a_code_system() -> None:
    """The maps name the namespaces, so a family that grows a group cannot leave one un-enumerated."""
    config = GenerateConfig()
    targeted = {
        group.target
        for concept_map in build_option_set_concept_maps(
            [_BIRTH_TYPE, _DELIVERY_PLACE], config, _CANONICAL, ig_status="draft"
        )
        for group in concept_map.group or []
    }

    emitted = _by_url(_option_set_systems(config))

    assert targeted == {"http://dhis2.org/fhir/id/option", "http://dhis2.org/fhir/id/option-code"}
    assert set(emitted) == targeted


def test_every_namespace_a_category_map_targets_gets_a_code_system() -> None:
    """The category family owns its own two namespaces, and enumerates both into the directory it owns."""
    config = GenerateConfig()
    targeted = {
        group.target
        for concept_map in build_category_concept_maps([_SEX, _AGE], config, _CANONICAL, ig_status="draft")
        for group in concept_map.group or []
    }

    artifacts = build_category_identifier_artifacts([_SEX, _AGE], config, _CANONICAL, ig_status="draft")

    assert targeted == {
        "http://dhis2.org/fhir/id/category-option",
        "http://dhis2.org/fhir/id/category-option-code",
    }
    assert set(_by_url([json.loads(artifact.content) for artifact in artifacts])) == targeted
    assert [artifact.relative_path for artifact in artifacts] == [
        "categories/CodeSystem-d2-category-option-id-cs.json",
        "categories/CodeSystem-d2-category-option-code-id-cs.json",
    ]


def test_the_code_system_is_complete_and_counts_what_it_lists() -> None:
    """`content: complete` is the whole point - `not-present` sends the publisher to the server anyway."""
    document = _by_url(_option_set_systems(GenerateConfig()))["http://dhis2.org/fhir/id/option"]

    assert document["content"] == "complete"
    assert document["caseSensitive"] is True
    assert document["count"] == len(document["concept"])


def test_the_concepts_are_every_targeted_identifier_deduplicated_and_sorted() -> None:
    """One row per identifier, in code order, whichever map named it - a shared option is listed once."""
    emitted = _by_url(
        [
            json.loads(artifact.content)
            for artifact in build_category_identifier_artifacts(
                [_SEX, _AGE], GenerateConfig(), _CANONICAL, ig_status="draft"
            )
        ]
    )

    uids = emitted["http://dhis2.org/fhir/id/category-option"]["concept"]

    assert [concept["code"] for concept in uids] == ["Ag1aaaaaaaa", "TNYQzTHdoxL", "apsOixVZlf1"]
    assert [concept["display"] for concept in uids] == ["Under five", "Female", "Male"]


def test_one_code_shared_by_two_option_sets_is_one_concept() -> None:
    """Two sets naming the same DHIS2 option code enumerate it once.

    The IG publisher anchors a concept row by its code, so the same code stated twice yields two
    rows carrying one anchor id, and the publisher's own QA pass reports the page as holding
    duplicate anchor ids while still exiting 0.
    """
    emitted = _by_url(
        [
            json.loads(artifact.content)
            for artifact in build_option_set_identifier_artifacts(
                [_FIRST_DIAGNOSIS, _SECOND_DIAGNOSIS], GenerateConfig(), _CANONICAL, ig_status="draft"
            )
        ]
    )

    document = emitted["http://dhis2.org/fhir/id/option-code"]

    assert [concept["code"] for concept in document["concept"]] == ["Preeclampsia"]
    assert document["count"] == 1


def test_every_emitted_code_system_states_each_code_once() -> None:
    """The invariant the publisher's anchor ids depend on, asserted over every namespace a family emits."""
    documents = [
        json.loads(artifact.content)
        for artifact in (
            *build_option_set_identifier_artifacts(
                [_BIRTH_TYPE, _DELIVERY_PLACE, _FIRST_DIAGNOSIS, _SECOND_DIAGNOSIS],
                GenerateConfig(),
                _CANONICAL,
                ig_status="draft",
            ),
            *build_category_identifier_artifacts([_SEX, _AGE], GenerateConfig(), _CANONICAL, ig_status="draft"),
        )
    ]

    for document in documents:
        codes = [concept["code"] for concept in document["concept"]]
        assert len(codes) == len(set(codes)), f"{document['url']} states a code twice"


def test_the_option_uids_and_the_option_codes_are_enumerated_separately() -> None:
    """Two namespaces, two code systems: an option whose DHIS2 code is unusable reaches only the UID one."""
    emitted = _by_url(_option_set_systems(GenerateConfig()))

    assert [concept["code"] for concept in emitted["http://dhis2.org/fhir/id/option"]["concept"]] == [
        "Dp1aaaaaaaa",
        "EBE0c8sZazS",
        "GVcG84DTFOB",
        "kRRUtYaGett",
    ]
    assert [concept["code"] for concept in emitted["http://dhis2.org/fhir/id/option-code"]["concept"]] == [
        "CS",
        "HOME",
        "NB",
    ]


def test_each_code_system_shares_its_url_with_the_naming_system_of_the_same_namespace() -> None:
    """The two declarations are twins: the NamingSystem says what the URL is, the CodeSystem says what is in it."""
    config = GenerateConfig()
    declared = {declaration.url for declaration in build_naming_system_declarations(config)}

    emitted = _option_set_systems(config)

    assert {document["url"] for document in emitted} <= declared
    assert [document["name"] for document in emitted] == [
        "D2OptionIdentifierSystem_CS",
        "D2OptionCodeIdentifierSystem_CS",
    ]


def test_a_target_system_that_is_not_a_dhis2_namespace_emits_nothing() -> None:
    """The tracked entity type map targets the core FHIR resource-type system, which the publisher holds already."""
    foreign = ConceptMap(
        id="d2-tet-cm",
        url=f"{_CANONICAL}/ConceptMap/d2-tet-cm",
        group=[
            ConceptMapGroup(
                source=f"{_CANONICAL}/CodeSystem/d2-tet-cs",
                target="http://hl7.org/fhir/resource-types",
                element=[
                    ConceptMapGroupElement(
                        code="Te1aaaaaaaa",
                        display="Person",
                        target=[ConceptMapGroupElementTarget(code="Patient", equivalence="equal")],
                    )
                ],
            )
        ],
    )

    assert build_identifier_code_systems([foreign], GenerateConfig(), ig_status="draft") == []


def test_the_namespace_urls_follow_the_configured_identifier_system_base() -> None:
    """A project publishing its own identifier base enumerates that base, never the DHIS2 default."""
    config = GenerateConfig(identifier_system_base="https://health.example/ids")

    emitted = _by_url(_option_set_systems(config))

    assert set(emitted) == {"https://health.example/ids/id/option", "https://health.example/ids/id/option-code"}


def test_the_names_follow_the_configured_naming_prefix() -> None:
    """The CodeSystem and its NamingSystem twin are named off the same token, so the pair never drifts apart."""
    config = GenerateConfig(naming=NamingConfig(prefix="HN"))

    artifacts = build_option_set_identifier_artifacts([_BIRTH_TYPE], config, _CANONICAL, ig_status="draft")

    assert [artifact.relative_path for artifact in artifacts] == [
        "terminology/CodeSystem-hn-option-id-cs.json",
        "terminology/CodeSystem-hn-option-code-id-cs.json",
    ]
    assert json.loads(artifacts[0].content)["name"] == "HNOptionIdentifierSystem_CS"


def test_the_emitted_bytes_repeat_exactly_across_two_runs() -> None:
    """`sync_json_artifacts` only reports an unchanged run quiet when the bytes repeat, so ordering is a contract."""
    config = GenerateConfig()

    first = build_option_set_identifier_artifacts([_BIRTH_TYPE, _DELIVERY_PLACE], config, _CANONICAL, ig_status="draft")
    second = build_option_set_identifier_artifacts(
        [_DELIVERY_PLACE, _BIRTH_TYPE], config, _CANONICAL, ig_status="draft"
    )

    assert [artifact.content for artifact in first] == [artifact.content for artifact in second]


def test_a_selection_that_maps_nothing_emits_no_code_system() -> None:
    """An empty selection publishes no map, so there is no namespace to enumerate and no file to sweep around."""
    assert build_option_set_identifier_artifacts([], GenerateConfig(), _CANONICAL, ig_status="draft") == []
    assert build_identifier_code_system_artifacts("terminology", [], GenerateConfig(), ig_status="draft") == []


def test_the_publication_state_follows_the_guide() -> None:
    """An active guide publishes active, non-experimental identifier terminology, like every other resource it emits."""
    document = json.loads(
        build_option_set_identifier_artifacts([_BIRTH_TYPE], GenerateConfig(), _CANONICAL, ig_status="active")[
            0
        ].content
    )

    assert document["status"] == "active"
    assert document["experimental"] is False


def test_the_attribute_combo_family_enumerates_its_own_namespaces() -> None:
    """The combo maps target the option-combo namespaces, and nothing else in the guide enumerates those."""
    config = GenerateConfig()
    targeted = {
        group.target
        for concept_map in build_attribute_combo_concept_maps([_EPI_STOCK], config, _CANONICAL, ig_status="draft")
        for group in concept_map.group or []
    }

    artifacts = build_attribute_combo_identifier_artifacts([_EPI_STOCK], config, _CANONICAL, ig_status="draft")

    assert targeted == {
        "http://dhis2.org/fhir/id/category-option-combo",
        "http://dhis2.org/fhir/id/category-option-combo-code",
    }
    emitted = _by_url([json.loads(artifact.content) for artifact in artifacts])
    assert set(emitted) == targeted
    assert [
        concept["code"] for concept in emitted["http://dhis2.org/fhir/id/category-option-combo-code"]["concept"]
    ] == [
        "COC_1452090",
        "COC_1452093",
    ]
    assert [artifact.relative_path for artifact in artifacts] == [
        "attribute-option-combos/CodeSystem-d2-category-option-combo-id-cs.json",
        "attribute-option-combos/CodeSystem-d2-category-option-combo-code-id-cs.json",
    ]
