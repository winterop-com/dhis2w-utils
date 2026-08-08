"""Golden tests for the pre-built category CodeSystem/ValueSet JSON and the names it assigns."""

import json
from typing import Any

import pytest
from dhis2w_fhir.attributes import AttributeCodeIndex, AttributeValueIn
from dhis2w_fhir.config import GenerateConfig, NamingConfig
from dhis2w_fhir.i18n import TranslationIn
from dhis2w_fhir.names import CodeStemError
from dhis2w_fhir.resources.categories import build_category_artifacts, category_identities
from dhis2w_fhir.resources.categories.schemas import CategoryIn, CategorySelection
from dhis2w_fhir.resources.option_sets.schemas import OptionIn
from dhis2w_fhir.status import IgStatus
from dhis2w_fhir.writer import JsonBuild

_CODE_STEMS = GenerateConfig(naming=NamingConfig(source="code"))
_CODE_OR_ID_STEMS = GenerateConfig(naming=NamingConfig(source="code-or-id"))
_CODE_SOURCE = GenerateConfig(concept_code_source="code")
_CANONICAL = "http://example.org/fhir"

_SEX = CategoryIn(
    uid="O5P6e8yu1T6",
    code="sex",
    name="Sex",
    options=[
        OptionIn(uid="TNYQzTHdoxL", code="F", name="Female", sort_order=0),
        OptionIn(uid="apsOixVZlf1", code="M", name="Male", sort_order=1),
    ],
)

_EXPECTED_CODE_STEM_CODE_SYSTEM = {
    "resourceType": "CodeSystem",
    "id": "d2-cat-sex-cs",
    "url": "http://example.org/fhir/CodeSystem/d2-cat-sex-cs",
    "identifier": [
        {"system": "http://dhis2.org/fhir/id/category", "value": "O5P6e8yu1T6"},
        {"system": "http://dhis2.org/fhir/id/category-code", "value": "sex"},
    ],
    "name": "D2CAT_Sex_CS",
    "title": "Sex",
    "description": "DHIS2 category Sex (O5P6e8yu1T6). Concept codes are DHIS2 category option UIDs.",
    "status": "draft",
    "experimental": True,
    "caseSensitive": True,
    "content": "complete",
    "count": 2,
    "valueSet": "http://example.org/fhir/ValueSet/d2-cat-sex-vs",
    "property": [
        {
            "code": "dhis2-code",
            "uri": "http://dhis2.org/fhir/property/dhis2-code",
            "description": "DHIS2 category option code.",
            "type": "string",
        }
    ],
    "concept": [
        {"code": "TNYQzTHdoxL", "display": "Female", "property": [{"code": "dhis2-code", "valueString": "F"}]},
        {"code": "apsOixVZlf1", "display": "Male", "property": [{"code": "dhis2-code", "valueString": "M"}]},
    ],
}

_EXPECTED_CODE_STEM_VALUE_SET = {
    "resourceType": "ValueSet",
    "id": "d2-cat-sex-vs",
    "url": "http://example.org/fhir/ValueSet/d2-cat-sex-vs",
    "identifier": [
        {"system": "http://dhis2.org/fhir/id/category", "value": "O5P6e8yu1T6"},
        {"system": "http://dhis2.org/fhir/id/category-code", "value": "sex"},
    ],
    "name": "D2CAT_Sex_VS",
    "title": "Sex",
    "description": "DHIS2 category Sex (O5P6e8yu1T6). Concept codes are DHIS2 category option UIDs.",
    "status": "draft",
    "experimental": True,
    "compose": {"include": [{"system": "http://example.org/fhir/CodeSystem/d2-cat-sex-cs"}]},
}


def _build(categories: list[CategoryIn], config: GenerateConfig, ig_status: IgStatus = "draft") -> JsonBuild:
    """Build the category terminology for one selection against the test canonical."""
    return build_category_artifacts(
        categories, config, _CANONICAL, ig_status=ig_status, attribute_codes=AttributeCodeIndex()
    )


def _documents(build: JsonBuild) -> dict[str, dict[str, Any]]:
    """Every emitted file, keyed by its relative path, parsed back into a plain JSON document."""
    return {artifact.relative_path: json.loads(artifact.content) for artifact in build.artifacts}


def _concept_codes(document: dict[str, Any]) -> list[str]:
    """The concept codes one CodeSystem document carries, in emission order."""
    return [concept["code"] for concept in document.get("concept", [])]


def test_code_stem_golden() -> None:
    """Code-stemmed emission: the category's DHIS2 code drives the id, url, file name, and FSH name."""
    build = _build([_SEX], _CODE_STEMS)
    assert [artifact.relative_path for artifact in build.artifacts] == [
        "categories/CodeSystem-d2-cat-sex-cs.json",
        "categories/ValueSet-d2-cat-sex-vs.json",
    ]
    documents = _documents(build)
    assert documents["categories/CodeSystem-d2-cat-sex-cs.json"] == _EXPECTED_CODE_STEM_CODE_SYSTEM
    assert documents["categories/ValueSet-d2-cat-sex-vs.json"] == _EXPECTED_CODE_STEM_VALUE_SET
    assert [note.message for note in build.notes] == []


def test_id_source_is_default() -> None:
    """Default naming source is id: file, id, and computational name all derive from the category id."""
    documents = _documents(_build([_SEX], GenerateConfig()))
    code_system = documents["categories/CodeSystem-d2-cat-O5P6e8yu1T6-cs.json"]
    assert code_system["id"] == "d2-cat-O5P6e8yu1T6-cs"
    assert code_system["name"] == "D2CAT_O5P6e8yu1T6_CS"
    assert code_system["title"] == "Sex"
    assert documents["categories/ValueSet-d2-cat-O5P6e8yu1T6-vs.json"]["name"] == "D2CAT_O5P6e8yu1T6_VS"


def test_the_emitted_names_are_the_ones_the_identity_plan_assigned() -> None:
    """SUSHI fishes a predefined resource by `name`, so the emitted name is the plan's FSH name."""
    identity = category_identities([_SEX], GenerateConfig()).identities[0]
    documents = _documents(_build([_SEX], GenerateConfig()))
    assert identity.code_system_name == "D2CAT_O5P6e8yu1T6_CS"
    assert documents[f"categories/CodeSystem-{identity.code_system_id}.json"]["name"] == identity.code_system_name
    assert documents[f"categories/ValueSet-{identity.value_set_id}.json"]["name"] == identity.value_set_name


def test_code_source_carries_the_uid_as_the_complementary_property() -> None:
    """In code mode the DHIS2 code is the concept code and the UID rides along as dhis2-id."""
    documents = _documents(_build([_SEX], _CODE_SOURCE))
    code_system = documents["categories/CodeSystem-d2-cat-O5P6e8yu1T6-cs.json"]
    assert _concept_codes(code_system) == ["F", "M"]
    assert code_system["concept"][0]["property"] == [{"code": "dhis2-id", "valueCode": "TNYQzTHdoxL"}]
    assert code_system["property"][0]["description"] == "DHIS2 category option UID."
    assert code_system["description"].endswith("Concept codes are DHIS2 category option codes.")


def test_an_unusable_code_falls_back_to_the_uid_with_a_note() -> None:
    """A category option whose DHIS2 code is not a valid FHIR code takes the UID, and the note names it."""
    category = CategoryIn(
        uid="O5P6e8yu1T6",
        name="Sex",
        options=[OptionIn(uid="TNYQzTHdoxL", code="F  F", name="Female", sort_order=0)],
    )
    build = _build([category], _CODE_SOURCE)
    documents = _documents(build)
    assert _concept_codes(documents["categories/CodeSystem-d2-cat-O5P6e8yu1T6-cs.json"]) == ["TNYQzTHdoxL"]
    assert [note.message for note in build.notes] == [
        "category 'Sex': category option TNYQzTHdoxL has code 'F  F' is not a valid FHIR code; falling back to the UID"
    ]


def test_an_option_with_no_code_left_to_take_is_skipped_once() -> None:
    """A category option whose UID fall-back is a peer's DHIS2 code is skipped rather than emitted twice."""
    category = CategoryIn(
        uid="O5P6e8yu1T6",
        name="Sex",
        options=[
            OptionIn(uid="TNYQzTHdoxL", code="apsOixVZlf1", name="Female", sort_order=0),
            OptionIn(uid="apsOixVZlf1", code="apsOixVZlf1", name="Male", sort_order=1),
        ],
    )
    build = _build([category], _CODE_SOURCE)
    code_system = _documents(build)["categories/CodeSystem-d2-cat-O5P6e8yu1T6-cs.json"]
    assert _concept_codes(code_system) == ["apsOixVZlf1"]
    assert code_system["count"] == 1
    assert any("could not receive a unique concept code" in note.message for note in build.notes)
    assert any("category option" in note.message for note in build.notes)


def test_translations_land_as_the_title_element_and_concept_designations() -> None:
    """A category's NAME translations become the _title extension, its options' become designations."""
    category = CategoryIn(
        uid="O5P6e8yu1T6",
        name="Sex",
        translations=[TranslationIn(locale="lo", property="NAME", value="ເພດ")],
        options=[
            OptionIn(
                uid="TNYQzTHdoxL",
                code="F",
                name="Female",
                sort_order=0,
                translations=[TranslationIn(locale="lo", property="NAME", value="ຍິງ")],
            )
        ],
    )
    code_system = _documents(_build([category], GenerateConfig()))["categories/CodeSystem-d2-cat-O5P6e8yu1T6-cs.json"]
    assert code_system["_title"]["extension"][0]["extension"][1]["valueString"] == "ເພດ"
    assert code_system["concept"][0]["designation"] == [{"language": "lo", "value": "ຍິງ"}]


def test_attribute_values_land_as_d2_attribute_value_extensions_on_both_halves() -> None:
    """The source category's DHIS2 attribute values ride along as D2AttributeValue extensions."""
    category = CategoryIn(
        uid="O5P6e8yu1T6",
        name="Sex",
        attribute_values=[AttributeValueIn(attribute_uid="ihn1wb9eho8", value="KE03")],
        options=[OptionIn(uid="TNYQzTHdoxL", code="F", name="Female", sort_order=0)],
    )
    build = build_category_artifacts(
        [category],
        GenerateConfig(),
        _CANONICAL,
        ig_status="draft",
        attribute_codes=AttributeCodeIndex(codes={"ihn1wb9eho8": "registryId"}),
    )
    for document in _documents(build).values():
        extension = document["extension"][0]
        assert extension["url"] == "http://example.org/fhir/StructureDefinition/d2-attribute-value"
        assert extension["extension"] == [
            {"url": "attributeId", "valueString": "ihn1wb9eho8"},
            {"url": "attributeCode", "valueString": "registryId"},
            {"url": "value", "valueString": "KE03"},
        ]


def test_a_unique_attribute_value_lands_as_an_identifier_on_both_halves() -> None:
    """A value DHIS2 declares unique names the category, so it joins the identifier list instead."""
    category = CategoryIn(
        uid="O5P6e8yu1T6",
        name="Sex",
        attribute_values=[AttributeValueIn(attribute_uid="ihn1wb9eho8", value="KE03")],
        options=[OptionIn(uid="TNYQzTHdoxL", code="F", name="Female", sort_order=0)],
    )
    build = build_category_artifacts(
        [category],
        GenerateConfig(),
        _CANONICAL,
        ig_status="draft",
        attribute_codes=AttributeCodeIndex(codes={"ihn1wb9eho8": "registryId"}, unique_uids=frozenset({"ihn1wb9eho8"})),
    )
    for document in _documents(build).values():
        assert document.get("extension") is None
        assert document["identifier"][-1] == {"system": "http://dhis2.org/fhir/attribute/ihn1wb9eho8", "value": "KE03"}


def test_code_or_id_collisions_fall_back_to_the_id_for_every_collider() -> None:
    """Two categories sharing one DHIS2 code both take the id as their stem, and the note names both."""
    twin = CategoryIn(uid="Nx0aRzPMuYt", code="sex", name="Sex", options=[])
    plan = category_identities([_SEX, twin], _CODE_OR_ID_STEMS)
    assert [identity.slug for identity in plan.identities] == ["Nx0aRzPMuYt", "O5P6e8yu1T6"]
    assert plan.identities[1].code_system_name == "D2CAT_O5P6e8yu1T6_CS"
    assert [note.message for note in plan.notes] == [
        "2 category codes unusable as identity stems; fell back to the id: Sex (Nx0aRzPMuYt), Sex (O5P6e8yu1T6)"
    ]


def test_code_or_id_keeps_the_usable_code_and_notes_the_fallback() -> None:
    """A usable, unique code is the stem; a category without one falls back to the id with the note."""
    uncoded = CategoryIn(uid="Nx0aRzPMuYt", name="Age group", options=[])
    plan = category_identities([_SEX, uncoded], _CODE_OR_ID_STEMS)
    assert [identity.slug for identity in plan.identities] == ["Nx0aRzPMuYt", "sex"]
    assert plan.identities[1].code_system_name == "D2CAT_Sex_CS"
    assert [note.message for note in plan.notes] == [
        "1 category codes unusable as identity stems; fell back to the id: Age group (Nx0aRzPMuYt)"
    ]


def test_code_source_refuses_a_category_without_a_usable_code() -> None:
    """`source = "code"` refuses the run before anything is written, naming the offender."""
    uncoded = CategoryIn(uid="Nx0aRzPMuYt", name="Age group", options=[])
    with pytest.raises(CodeStemError) as caught:
        _build([_SEX, uncoded], _CODE_STEMS)
    assert "Age group (Nx0aRzPMuYt) has no code" in str(caught.value)
    assert "`d2w fhir validate` names every offender" in str(caught.value)


def test_the_naming_token_is_configurable() -> None:
    """`[generate.naming] category` composes the FSH name and the id stem; an empty token drops it."""
    documents = _documents(_build([_SEX], GenerateConfig(naming=NamingConfig(category="Category"))))
    assert "categories/CodeSystem-d2-category-O5P6e8yu1T6-cs.json" in documents
    assert documents["categories/CodeSystem-d2-category-O5P6e8yu1T6-cs.json"]["name"] == "D2Category_O5P6e8yu1T6_CS"
    dropped = _documents(_build([_SEX], GenerateConfig(naming=NamingConfig(prefix="", category=""))))
    assert "categories/CodeSystem-O5P6e8yu1T6-cs.json" in dropped
    assert dropped["categories/CodeSystem-O5P6e8yu1T6-cs.json"]["name"] == "O5P6e8yu1T6_CS"


def test_an_active_ig_emits_active_non_experimental_terminology() -> None:
    """The IG life cycle drives the status and experimental flag of both halves."""
    for document in _documents(_build([_SEX], GenerateConfig(), ig_status="active")).values():
        assert document["status"] == "active"
        assert "experimental" not in document or document["experimental"] is False


def test_selection_defaults_to_every_category() -> None:
    """An absent `[generate.categories]` include list selects the whole instance."""
    assert CategorySelection().include_ids == []
    assert GenerateConfig().categories.include_ids == []


def test_page_furniture_escapes_the_markup_characters_the_publisher_parses() -> None:
    """A name holding `<` aborts the IG publisher: `fhir2.base.template` pastes the title into HTML raw."""
    hostile = CategoryIn(
        uid="Xa1b2c3d4e5",
        name="Age (<5 >5) & up",
        options=[OptionIn(uid="Op1aaaaaaaa", code="LT5", name="<5", sort_order=0)],
    )

    documents = _documents(_build([hostile], GenerateConfig()))

    for document in documents.values():
        assert document["title"] == "Age (&lt;5 &gt;5) &amp; up"
        for character in "<>":
            assert character not in document["title"]
            assert character not in document["description"]
    # The other half of the rule: a concept display is data a consumer reads back, not page
    # furniture, so it carries the DHIS2 text verbatim.
    code_system = documents["categories/CodeSystem-d2-cat-Xa1b2c3d4e5-cs.json"]
    assert [concept["display"] for concept in code_system["concept"]] == ["<5"]
