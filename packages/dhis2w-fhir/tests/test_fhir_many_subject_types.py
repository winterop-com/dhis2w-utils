"""Fifty types is one config table: what the generator emits when an instance tracks many things.

`[generate.tracked_entity_types]` is one line per tracked entity type, and nothing about a project
with forty lines in it is a different code path from a project with one. This file holds the
generator to that at scale, over a fixture that tracks six kinds of thing across five FHIR resource
types - with two of the six deliberately published as the same resource, because that is the
arrangement a reader is most likely to be unsure about.

Three claims:

- **The published map is one row per type**, whatever the resource, and two types naming one resource
  are two rows rather than a collision. `D2TET_CM` is the contract a running facade reads, so a row
  lost here is a register that serves the wrong thing.
- **The response profiles admit the union of the resources, once each.** Two `Device` types widen the
  admitted set by one entry, not by two, and the order is the registry's rather than the config
  file's - so regenerating an unchanged project publishes unchanged bytes.
- **The types nobody typed are named.** A fifty-type instance needs a checklist rather than silence,
  and it gets one from both ends: the generate note names every type the run's own forms register
  and the table does not, and `d2w fhir validate` names every type THE INSTANCE HOLDS that the table
  does not - which is the wider list, because an instance holds types this project publishes no form
  for at all.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from dhis2w_fhir import (
    AttributeCodeIndex,
    GenerateConfig,
    build_questionnaire_documents,
    option_set_identities,
    published_tracked_entity_types,
    unmapped_tracked_entity_type_notes,
)
from dhis2w_fhir.foundation.schemas import TrackerSubjectTypes
from dhis2w_fhir.r4 import DEFAULT_SUBJECT_RESOURCE_TYPE
from dhis2w_fhir.resources.questionnaires.documents import build_data_dictionary_documents
from dhis2w_fhir.resources.questionnaires.schemas import QuestionnaireItemIn, QuestionnaireSourceIn, form_subject_type
from dhis2w_fhir.validation import build_code_validation
from dhis2w_fhir.validation.schemas import MetadataCollectionIn, MetadataItemIn

_CANONICAL = "http://example.org/fhir"

#: Six kinds of thing one instance tracks, and the FHIR resource each of them is. `Patient` is left
#: out of the table on purpose - a type nobody types is a person, which is what keeps a
#: person-tracking project's config empty and is the default this fixture also has to exercise.
_PERSON_TYPE = "TetPerson01"
_FRIDGE_TYPE = "TetFridge01"
_VEHICLE_TYPE = "TetVehicl01"
_HERD_TYPE = "TetHerd0001"
_WATER_POINT_TYPE = "TetWaterP01"
_SAMPLE_TYPE = "TetSample01"

_NAMES: dict[str, str] = {
    _PERSON_TYPE: "Person",
    _FRIDGE_TYPE: "Cold-chain fridge",
    _VEHICLE_TYPE: "Delivery vehicle",
    _HERD_TYPE: "Livestock herd",
    _WATER_POINT_TYPE: "Water point",
    _SAMPLE_TYPE: "Specimen batch",
}

#: The map: five resources from six types, the two vehicles-and-fridges rows sharing `Device`.
_MAPPING: dict[str, str] = {
    _FRIDGE_TYPE: "Device",
    _VEHICLE_TYPE: "Device",
    _HERD_TYPE: "Group",
    _WATER_POINT_TYPE: "Location",
    _SAMPLE_TYPE: "Specimen",
}

_CONFIG = GenerateConfig(tracked_entity_types=_MAPPING)


def _source(uid: str) -> QuestionnaireSourceIn:
    """The person-only registration form of one type, which is what publishes the type at all."""
    return QuestionnaireSourceIn(
        uid=uid,
        name=_NAMES[uid],
        kind="tracked-entity",
        tracked_entity_type_uid=uid,
        flat_items=[QuestionnaireItemIn(uid="TeaAssetTg1", name="Asset tag", value_type="TEXT", unique=True)],
    )


_SOURCES = [_source(uid) for uid in _NAMES]


def _map_document() -> dict[str, Any]:
    """The emitted `D2TET_CM`, as the writer writes it."""
    documents = build_data_dictionary_documents(_SOURCES, _CONFIG, _CANONICAL, ig_status="draft")
    concept_map = next(resource for resource in documents.concept_maps if resource.name == "D2TET_CM")
    document: dict[str, Any] = json.loads(concept_map.model_dump_json(exclude_none=True, by_alias=True))
    return document


def _rows() -> dict[str, str]:
    """Each published type's row of the map: the type UID onto the resource its first target names."""
    document = _map_document()
    return {
        element["code"]: element["target"][0]["code"] for group in document["group"] for element in group["element"]
    }


def test_the_map_holds_one_row_per_type_however_many_share_a_resource() -> None:
    """Six types, six rows. A resource two types name is named twice, once by each of them."""
    assert _rows() == {
        _PERSON_TYPE: DEFAULT_SUBJECT_RESOURCE_TYPE,
        _FRIDGE_TYPE: "Device",
        _VEHICLE_TYPE: "Device",
        _HERD_TYPE: "Group",
        _WATER_POINT_TYPE: "Location",
        _SAMPLE_TYPE: "Specimen",
    }


def test_the_row_of_an_untyped_type_is_the_person_it_defaults_to() -> None:
    """The default rides in the published map rather than in a reader's head - the row is explicit."""
    document = _map_document()
    displayed = {element["code"]: element["display"] for group in document["group"] for element in group["element"]}
    assert displayed[_PERSON_TYPE] == "Person"
    assert _rows()[_PERSON_TYPE] == DEFAULT_SUBJECT_RESOURCE_TYPE


@pytest.mark.parametrize("uid", list(_NAMES), ids=list(_NAMES))
def test_every_form_declares_the_resource_its_type_is_mapped_to(uid: str) -> None:
    """One line of the table types every form of that type, and a shared resource types two of them."""
    assert form_subject_type(_source(uid), _CONFIG.tracked_entity_types) == _MAPPING.get(
        uid, DEFAULT_SUBJECT_RESOURCE_TYPE
    )


def test_the_two_forms_sharing_a_resource_declare_the_same_subject_type() -> None:
    """The fridge form and the vehicle form are both about a `Device`, which is why one register serves both."""
    documents = build_questionnaire_documents(
        _SOURCES,
        _CONFIG,
        _CANONICAL,
        ig_status="draft",
        option_set_plan=option_set_identities([], _CONFIG),
        attribute_codes=AttributeCodeIndex(),
    )
    declared = {questionnaire.id: list(questionnaire.subjectType or []) for questionnaire in documents.questionnaires}
    assert declared[_FRIDGE_TYPE] == ["Device"]
    assert declared[_VEHICLE_TYPE] == ["Device"]


def test_the_response_profiles_admit_each_resource_once_in_the_registry_order() -> None:
    """The union is over resources, not over types: two `Device` types widen it by one entry."""
    admitted = TrackerSubjectTypes.of_mapping(_MAPPING)

    assert admitted.resource_types == ("Patient", "Group", "Device", "Location", "Specimen")


def test_the_generate_note_names_every_type_the_forms_publish_that_the_table_does_not() -> None:
    """A run that types five of six is told about the sixth by name, so the checklist has one line left."""
    notes = unmapped_tracked_entity_type_notes(published_tracked_entity_types(_SOURCES, {}))

    assert len(notes) == 1
    assert "6 tracked entity types" in notes[0].message
    for uid, name in _NAMES.items():
        assert f"{name} ({uid})" in notes[0].message


def _validation_findings(mapping: dict[str, str]) -> list[Any]:
    """Validate one instance sweep holding every type, under one `[generate.tracked_entity_types]`."""
    report = build_code_validation(
        [],
        [
            MetadataCollectionIn(
                resource="trackedEntityTypes",
                items=[MetadataItemIn(uid=uid, name=name) for uid, name in _NAMES.items()],
            )
        ],
        GenerateConfig(tracked_entity_types=mapping),
    )
    return [finding for finding in report.findings if finding.category == "unmapped-tracked-entity-type"]


def test_validate_names_every_instance_type_the_table_does_not_type() -> None:
    """THE FIFTY-TYPE CHECKLIST: one row per type nobody typed, with the config line that would type it."""
    findings = _validation_findings({})

    assert [finding.uid for finding in findings] == sorted(_NAMES, key=lambda uid: (_NAMES[uid], uid))
    assert {finding.name for finding in findings} == set(_NAMES.values())
    fridge = next(finding for finding in findings if finding.uid == _FRIDGE_TYPE)
    assert "absent from [generate.tracked_entity_types]" in fridge.message
    assert f'"{_FRIDGE_TYPE}" = "<resource>"' in fridge.message
    assert DEFAULT_SUBJECT_RESOURCE_TYPE in fridge.message


def test_a_typed_type_leaves_the_checklist() -> None:
    """The list shortens as the table grows, which is what makes it a checklist rather than a warning."""
    assert [finding.uid for finding in _validation_findings(_MAPPING)] == [_PERSON_TYPE]


def test_a_sweep_holding_no_tracked_entity_type_says_nothing() -> None:
    """An instance with no tracked entity type has no checklist, and silence is the honest report."""
    report = build_code_validation([], [MetadataCollectionIn(resource="dataElements", items=[])], GenerateConfig())

    assert [finding for finding in report.findings if finding.category == "unmapped-tracked-entity-type"] == []
