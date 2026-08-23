"""The published map from one instance's sex values onto R4's administrative-gender codes.

No SUSHI golden here, and deliberately: the map has no FSH twin to compile - it is written as a
predefined JSON resource the way the attribute-option-combo maps are - so the document itself is
stated in full below. That is the golden, and a change to the emitter shows up as a diff against a
document a reader can check against the R4 spec by eye.
"""

from __future__ import annotations

import json
from typing import Any

from dhis2w_fhir.config import GenerateConfig, NamingConfig
from dhis2w_fhir.ips import IdentityNominations
from dhis2w_fhir.resources.administrative_gender import (
    administrative_gender_map_file_prefix,
    administrative_gender_map_id,
    administrative_gender_map_name,
    build_administrative_gender_concept_map,
    build_administrative_gender_concept_map_artifacts,
)

_CANONICAL = "http://example.org/fhir"
_CONFIG = GenerateConfig(identifier_system_base="http://dhis2.org/fhir")
_SEX_ATTRIBUTE = "cejWyOfXge6"

_NOMINATIONS = IdentityNominations(
    name="w75KJ2mc4zz",
    sex=_SEX_ATTRIBUTE,
    administrative_gender={"Male": "male", "Female": "female"},
)

_EXPECTED: dict[str, Any] = {
    "resourceType": "ConceptMap",
    "id": "d2-sex-cm",
    "url": "http://example.org/fhir/ConceptMap/d2-sex-cm",
    "name": "D2Sex_CM",
    "title": "DHIS2 sex values as FHIR administrative gender codes",
    "description": (
        "Every value of the tracked entity attribute this project nominates as a person's sex, mapped "
        "onto the R4 administrative-gender code the register publishes as Patient.gender. DHIS2 states "
        "no such mapping, so the rows are this instance's own statement, made in [ips.identity] and "
        "published here so a consumer resolves a served gender without holding that file."
    ),
    "status": "draft",
    "experimental": True,
    "targetCanonical": "http://hl7.org/fhir/ValueSet/administrative-gender",
    "group": [
        {
            "source": "http://dhis2.org/fhir/tracked-entity-attribute/cejWyOfXge6",
            "target": "http://hl7.org/fhir/administrative-gender",
            "element": [
                {"code": "Female", "target": [{"code": "female", "equivalence": "equal"}]},
                {"code": "Male", "target": [{"code": "male", "equivalence": "equal"}]},
            ],
        }
    ],
}


def _document(nominations: IdentityNominations, config: GenerateConfig | None = None) -> dict[str, Any]:
    """The built map as the JSON object the writer serialises it to."""
    concept_map = build_administrative_gender_concept_map(nominations, config or _CONFIG, _CANONICAL, ig_status="draft")
    assert concept_map is not None
    body: dict[str, Any] = json.loads(concept_map.model_dump_json(exclude_none=True, by_alias=True))
    return body


def test_the_map_publishes_every_row_the_nomination_states() -> None:
    """The first map this project publishes onto a vocabulary that is not DHIS2's own, stated in full."""
    assert _document(_NOMINATIONS) == _EXPECTED


def test_the_rows_sort_by_the_dhis2_value_whatever_order_the_file_typed_them_in() -> None:
    """A regenerate of an unchanged file produces the same bytes, which is what makes a diff mean something."""
    reversed_table = IdentityNominations(sex=_SEX_ATTRIBUTE, administrative_gender={"Female": "female", "Male": "male"})

    assert _document(reversed_table)["group"] == _EXPECTED["group"]


def test_the_source_is_the_attributes_own_value_namespace() -> None:
    """The server maps a person's value, so a map keyed on anything else would publish a step nobody takes."""
    group = _document(_NOMINATIONS)["group"][0]

    assert group["source"] == f"http://dhis2.org/fhir/tracked-entity-attribute/{_SEX_ATTRIBUTE}"
    assert [element["code"] for element in group["element"]] == ["Female", "Male"]


def test_a_project_nominating_no_sex_publishes_no_map() -> None:
    """A map with no group states nothing, and an R4 group needs an element - so there is no file at all."""
    nominations = IdentityNominations(name="w75KJ2mc4zz")

    assert build_administrative_gender_concept_map(nominations, _CONFIG, _CANONICAL, ig_status="draft") is None
    assert build_administrative_gender_concept_map_artifacts(nominations, _CONFIG, _CANONICAL, ig_status="draft") == []


def test_the_artifact_lands_in_the_concept_map_directory_under_its_own_prefix() -> None:
    """Four families share `concept-maps/`, so each sweeps the names its own tokens produce."""
    artifacts = build_administrative_gender_concept_map_artifacts(_NOMINATIONS, _CONFIG, _CANONICAL, ig_status="draft")

    assert [artifact.relative_path for artifact in artifacts] == ["concept-maps/ConceptMap-d2-sex-cm.json"]
    assert artifacts[0].relative_path.startswith(f"concept-maps/{administrative_gender_map_file_prefix(_CONFIG)}")
    assert administrative_gender_map_file_prefix(_CONFIG) == "ConceptMap-d2-sex"


def test_the_naming_tokens_rename_the_map_the_way_they_rename_every_other_artifact() -> None:
    """A project that renames its prefix renames this map with the rest of the guide."""
    config = GenerateConfig(naming=NamingConfig(prefix="Lao"))

    assert administrative_gender_map_name(config) == "LaoSex_CM"
    assert administrative_gender_map_id(config) == "lao-sex-cm"
    assert _document(_NOMINATIONS, config)["id"] == "lao-sex-cm"


def test_an_active_guide_publishes_the_map_as_it_publishes_the_rest() -> None:
    """`status` and `experimental` follow `[ig] status`, so one guide never mixes the two postures."""
    concept_map = build_administrative_gender_concept_map(_NOMINATIONS, _CONFIG, _CANONICAL, ig_status="active")

    assert concept_map is not None
    assert concept_map.status == "active"
    assert concept_map.experimental is False
