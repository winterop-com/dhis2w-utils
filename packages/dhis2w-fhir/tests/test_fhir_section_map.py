"""The published map from this instance's DHIS2 objects onto the IPS sections they feed.

No SUSHI golden here for the reason `test_fhir_administrative_gender_map.py` gives: the map has no
FSH twin to compile, so the document itself is stated in full below and a change to the emitter
shows up as a diff against something a reader can check against the IPS section table by eye.
"""

from __future__ import annotations

import json
from typing import Any

from dhis2w_fhir.config import GenerateConfig, NamingConfig
from dhis2w_fhir.ips import ImmunizationsMapping, SectionMappings
from dhis2w_fhir.resources.ips_sections import (
    build_section_concept_map,
    build_section_concept_map_artifacts,
    section_map_file_prefix,
    section_map_id,
    section_map_name,
)

_CANONICAL = "http://example.org/fhir"
_CONFIG = GenerateConfig(identifier_system_base="http://dhis2.org/fhir")

_MAPPING = SectionMappings(
    immunizations=ImmunizationsMapping(
        program_stages=("ZzYYXq4fJie", "A03MvHHogjR"),
        dose_data_elements=("FqlgKAG8HOu", "bx6fsa0t90x"),
    )
)

_IMMUNIZATIONS_TARGET = [{"code": "11369-6", "display": "History of Immunization Narrative", "equivalence": "equal"}]

_EXPECTED: dict[str, Any] = {
    "resourceType": "ConceptMap",
    "id": "d2-section-cm",
    "url": "http://example.org/fhir/ConceptMap/d2-section-cm",
    "name": "D2Section_CM",
    "title": "DHIS2 program stages and data elements as International Patient Summary sections",
    "description": (
        "Every DHIS2 program stage and data element this project nominates as feeding a section of an "
        "International Patient Summary, mapped onto that section's LOINC code. DHIS2 states no such "
        "mapping - it marks no data element as an immunisation, a problem, or an allergy - so the rows "
        "are this instance's own statement, made in [ips.sections] and published here so a consumer can "
        "audit which recorded values a served summary carries without holding that file."
    ),
    "status": "draft",
    "experimental": True,
    "group": [
        {
            "source": "http://dhis2.org/fhir/id/program-stage",
            "target": "http://loinc.org",
            "element": [
                {"code": "A03MvHHogjR", "target": _IMMUNIZATIONS_TARGET},
                {"code": "ZzYYXq4fJie", "target": _IMMUNIZATIONS_TARGET},
            ],
        },
        {
            "source": "http://dhis2.org/fhir/id/data-element",
            "target": "http://loinc.org",
            "element": [
                {"code": "FqlgKAG8HOu", "target": _IMMUNIZATIONS_TARGET},
                {"code": "bx6fsa0t90x", "target": _IMMUNIZATIONS_TARGET},
            ],
        },
    ],
}


def _document(sections: SectionMappings, config: GenerateConfig | None = None) -> dict[str, Any]:
    """The built map as the JSON object the writer serialises it to."""
    concept_map = build_section_concept_map(sections, config or _CONFIG, _CANONICAL, ig_status="draft")
    assert concept_map is not None
    body: dict[str, Any] = json.loads(concept_map.model_dump_json(exclude_none=True, by_alias=True))
    return body


def test_the_map_publishes_every_row_the_mapping_states() -> None:
    """`fhir.toml` is the input and this is the published output, stated in full."""
    assert _document(_MAPPING) == _EXPECTED


def test_the_rows_sort_by_uid_whatever_order_the_file_typed_them_in() -> None:
    """A regenerate of an unchanged file produces the same bytes, which is what makes a diff mean something."""
    retyped = SectionMappings(
        immunizations=ImmunizationsMapping(
            program_stages=("A03MvHHogjR", "ZzYYXq4fJie"),
            dose_data_elements=("bx6fsa0t90x", "FqlgKAG8HOu"),
        )
    )

    assert _document(retyped)["group"] == _EXPECTED["group"]


def test_the_sources_are_the_dhis2_identifier_namespaces() -> None:
    """A generated concept code moves with the naming source; a UID namespace never does."""
    groups = _document(_MAPPING)["group"]

    assert [group["source"] for group in groups] == [
        "http://dhis2.org/fhir/id/program-stage",
        "http://dhis2.org/fhir/id/data-element",
    ]
    assert {group["target"] for group in groups} == {"http://loinc.org"}


def test_a_project_mapping_no_section_publishes_no_map() -> None:
    """A map with no group states nothing, so there is no file at all rather than an empty one."""
    assert build_section_concept_map(SectionMappings(), _CONFIG, _CANONICAL, ig_status="draft") is None
    assert build_section_concept_map_artifacts(SectionMappings(), _CONFIG, _CANONICAL, ig_status="draft") == []


def test_the_artifact_lands_in_the_concept_map_directory_under_its_own_prefix() -> None:
    """Four families share `concept-maps/`, so each sweeps the names its own tokens produce."""
    artifacts = build_section_concept_map_artifacts(_MAPPING, _CONFIG, _CANONICAL, ig_status="draft")

    assert [artifact.relative_path for artifact in artifacts] == ["concept-maps/ConceptMap-d2-section-cm.json"]
    assert section_map_file_prefix(_CONFIG) == "ConceptMap-d2-section"


def test_the_naming_tokens_rename_the_map_the_way_they_rename_every_other_artifact() -> None:
    """A project that renames its prefix renames this map with the rest of the guide."""
    config = GenerateConfig(naming=NamingConfig(prefix="Lao"))

    assert section_map_name(config) == "LaoSection_CM"
    assert section_map_id(config) == "lao-section-cm"
    assert _document(_MAPPING, config)["id"] == "lao-section-cm"


def test_an_active_guide_publishes_the_map_as_it_publishes_the_rest() -> None:
    """`status` and `experimental` follow `[ig] status`, so one guide never mixes the two postures."""
    concept_map = build_section_concept_map(_MAPPING, _CONFIG, _CANONICAL, ig_status="active")

    assert concept_map is not None
    assert concept_map.status == "active"
    assert concept_map.experimental is False
