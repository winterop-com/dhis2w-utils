"""The assembled summary: what the document carries, what it states empty, and what it says about itself.

`docs/fhir/design/ips.md` section 9, phase 2. The library under test is a pure function of a subject
and a list of doses, so everything here is assembled without a server, a store, or an instance -
which is the point of `dhis2w_fhir.summary` being a library and not a route.
"""

from __future__ import annotations

from typing import Any

import pytest
from dhis2w_fhir.r4 import Composition, Identifier, Meta, Narrative, RegisteredEntity
from dhis2w_fhir.summary import (
    ALLERGIES_SECTION,
    IMMUNIZATIONS_SECTION,
    IPS_COMPOSITION_TYPE_CODE,
    LIST_EMPTY_REASON_SYSTEM,
    LOINC_SYSTEM,
    MEDICATIONS_SECTION,
    PROBLEMS_SECTION,
    REQUIRED_SECTIONS,
    AssembledSummary,
    RecordedDose,
    build_patient_summary,
)

_TRACKED_ENTITY_UID = "PLoWmEuLJl2"
_TRACKED_ENTITY_SYSTEM = "http://dhis2.org/fhir/id/tracked-entity"
_DATA_ELEMENT_SYSTEM = "http://dhis2.org/fhir/id/data-element"
_ASSEMBLED_AT = "2026-03-01T09:00:00Z"
_AUTHOR = "d2w fhir serve 1.9.0"


def _subject() -> RegisteredEntity:
    """The person as the register serves them, which is what a summary carries unchanged."""
    return RegisteredEntity(
        resourceType="Patient",
        id=_TRACKED_ENTITY_UID,
        meta=Meta(),
        identifier=[Identifier(system=_TRACKED_ENTITY_SYSTEM, value=_TRACKED_ENTITY_UID)],
    )


def _dose(
    data_element_uid: str = "bx6fsa0t90x",
    *,
    event_uid: str = "EvBirth0001",
    display: str | None = "MCH BCG dose",
    occurred_at: str | None = "2025-04-16T00:00:00Z",
    dose_number: str | None = None,
) -> RecordedDose:
    """One dose the record projected, in the shape `dhis2w_fhir_serve.summary` hands over."""
    return RecordedDose(
        event_uid=event_uid,
        data_element_uid=data_element_uid,
        display=display,
        occurred_at=occurred_at,
        dose_number=dose_number,
    )


def _assemble(*doses: RecordedDose, immunizations_mapped: bool = True, **overrides: Any) -> AssembledSummary:
    """Assemble one summary of the fixture person, with whatever doses the test states."""
    return build_patient_summary(
        _subject(),
        doses,
        vaccine_code_system=_DATA_ELEMENT_SYSTEM,
        assembled_at=_ASSEMBLED_AT,
        author_display=_AUTHOR,
        immunizations_mapped=immunizations_mapped,
        **overrides,
    )


def _composition(summary: AssembledSummary) -> Composition:
    """The document's first entry, which is what makes the Bundle a document."""
    entries = summary.bundle.entry or []
    body = entries[0].resource
    assert body is not None
    return Composition.model_validate(body.model_dump(by_alias=True))


def _text_of(narrative: Narrative | None) -> str:
    """The XHTML one narrative carries, which every section of a summary is required (1..1) to have."""
    assert narrative is not None
    assert narrative.div is not None
    return narrative.div


def _resources(summary: AssembledSummary, resource_type: str) -> list[dict[str, Any]]:
    """Every entry of one resource type, as the wire carries it."""
    return [
        entry.resource.model_dump(by_alias=True, exclude_none=True)
        for entry in summary.bundle.entry or []
        if entry.resource is not None and entry.resource.resourceType == resource_type
    ]


def test_the_bundle_is_a_document_with_an_identifier_and_a_timestamp() -> None:
    """`Bundle-uv-ips` fixes the type to `document` and requires both of those elements 1..1."""
    summary = _assemble(_dose())

    assert summary.bundle.type == "document"
    assert summary.bundle.identifier is not None
    assert summary.bundle.identifier.value.startswith("urn:uuid:") if summary.bundle.identifier.value else False
    assert summary.bundle.timestamp == _ASSEMBLED_AT


def test_the_composition_leads_and_is_the_only_one() -> None:
    """The invariant `bdl-ips-1`: an IPS document has no Composition besides the first."""
    summary = _assemble(_dose())

    entries = summary.bundle.entry or []
    assert entries[0].resource is not None
    assert entries[0].resource.resourceType == "Composition"
    assert len(_resources(summary, "Composition")) == 1


def test_the_composition_is_typed_as_a_patient_summary_about_one_patient() -> None:
    """`Composition-uv-ips` pins `type` to LOINC 60591-5 and `subject` to one Patient."""
    summary = _assemble()
    composition = _composition(summary)

    assert composition.type is not None
    assert composition.type.coding is not None
    assert composition.type.coding[0].system == LOINC_SYSTEM
    assert composition.type.coding[0].code == IPS_COMPOSITION_TYPE_CODE
    assert composition.subject is not None
    subject_urls = [entry.fullUrl for entry in summary.bundle.entry or [] if entry.fullUrl]
    assert composition.subject.reference in subject_urls


def test_the_subject_is_the_resource_the_register_already_serves() -> None:
    """One person, one projection: the register's answer is carried into the document unchanged."""
    summary = _assemble()

    served = _resources(summary, "Patient")
    assert len(served) == 1
    assert served[0]["id"] == _TRACKED_ENTITY_UID
    assert served[0]["identifier"] == [{"system": _TRACKED_ENTITY_SYSTEM, "value": _TRACKED_ENTITY_UID}]


def test_the_three_required_sections_state_an_empty_reason() -> None:
    """`ips-comp-1` accepts an `emptyReason` in place of an entry, and this project maps none of them."""
    composition = _composition(_assemble(_dose()))

    sections = composition.section or []
    required = sections[: len(REQUIRED_SECTIONS)]
    assert [section.title for section in required] == [
        PROBLEMS_SECTION.title,
        ALLERGIES_SECTION.title,
        MEDICATIONS_SECTION.title,
    ]
    for section in required:
        assert section.entry is None
        assert section.emptyReason is not None
        assert section.emptyReason.coding is not None
        assert section.emptyReason.coding[0].system == LIST_EMPTY_REASON_SYSTEM
        assert section.text is not None


def test_every_section_carries_a_title_a_code_and_a_narrative() -> None:
    """`Composition-uv-ips` makes all three 1..1 on every section present, empty or not."""
    composition = _composition(_assemble(_dose()))

    for section in composition.section or []:
        assert section.title
        assert section.code is not None
        assert _text_of(section.text)


def test_a_mapped_dose_becomes_an_immunization_the_section_points_at() -> None:
    """The one mapped section carries real entries, each an Immunization coded by DHIS2 identity."""
    summary = _assemble(_dose(dose_number="Dose 2"))
    composition = _composition(summary)

    immunizations = _resources(summary, "Immunization")
    assert len(immunizations) == 1
    assert immunizations[0]["status"] == "completed"
    assert immunizations[0]["vaccineCode"]["coding"][0] == {
        "system": _DATA_ELEMENT_SYSTEM,
        "code": "bx6fsa0t90x",
        "display": "MCH BCG dose",
    }
    assert immunizations[0]["occurrenceDateTime"] == "2025-04-16T00:00:00Z"
    assert immunizations[0]["protocolApplied"] == [{"doseNumberString": "Dose 2"}]

    section = (composition.section or [])[-1]
    assert section.title == IMMUNIZATIONS_SECTION.title
    assert section.entry is not None
    assert len(section.entry) == 1
    assert section.emptyReason is None


def test_a_dose_with_no_dose_number_states_no_protocol() -> None:
    """A boolean dose element says a dose was given and names no series, so nothing is invented."""
    summary = _assemble(_dose())

    assert "protocolApplied" not in _resources(summary, "Immunization")[0]


def test_a_mapped_section_with_no_dose_is_present_and_empty() -> None:
    """A mapped section this person has nothing under is a fact about the person, stated in-band."""
    composition = _composition(_assemble())

    section = (composition.section or [])[-1]
    assert section.title == IMMUNIZATIONS_SECTION.title
    assert section.entry is None
    assert section.emptyReason is not None


def test_an_unmapped_section_is_omitted_entirely() -> None:
    """A recommended section nobody mapped is left out, which is what section 5 says to do with one."""
    composition = _composition(_assemble(immunizations_mapped=False))

    assert [section.title for section in composition.section or []] == [section.title for section in REQUIRED_SECTIONS]


def test_a_summary_with_no_mapped_section_is_served_and_says_so() -> None:
    """The owner's call: such a document is built, with the caveat stated rather than left to be worked out."""
    summary = _assemble(immunizations_mapped=False)
    composition = _composition(summary)

    assert "No clinical section of this summary is mapped" in summary.caveat
    assert summary.creator_conformant is False
    assert summary.caveat in _text_of(composition.text)


def test_the_caveat_is_the_documents_own_narrative() -> None:
    """`Composition.text` is where a reader of the document meets it, so the sentence lives there."""
    summary = _assemble(_dose())
    composition = _composition(summary)

    assert summary.caveat in _text_of(composition.text)
    assert "does not claim the Creator (IPS) actor's obligations" in summary.caveat
    assert "1 dose" in summary.caveat


def test_the_author_is_stated_and_nobody_is_invented() -> None:
    """Nobody in DHIS2 authored this document, so the author is the software that assembled it."""
    composition = _composition(_assemble())

    assert composition.author is not None
    assert composition.author[0].display == _AUTHOR
    assert composition.author[0].reference is None


def test_a_mapped_stage_the_guide_publishes_no_form_for_is_named() -> None:
    """A guide narrower than its mapping and a person never vaccinated are not the same fact."""
    composition = _composition(_assemble(unpublished_stage_uids=("A03MvHHogjR",)))

    narrative = _text_of((composition.section or [])[-1].text)
    assert "A03MvHHogjR" in narrative
    assert "publishes no" in narrative


def test_two_assemblies_of_one_record_differ_only_in_the_two_instants() -> None:
    """R4: the ids come off DHIS2 identifiers, so a regenerate of an unchanged record is the same document."""
    first = _assemble(_dose(), _dose("FqlgKAG8HOu", display="MCH Measles dose"))
    second = build_patient_summary(
        _subject(),
        [_dose(), _dose("FqlgKAG8HOu", display="MCH Measles dose")],
        vaccine_code_system=_DATA_ELEMENT_SYSTEM,
        assembled_at="2026-04-02T10:11:12Z",
        author_display=_AUTHOR,
        immunizations_mapped=True,
    )

    def _without_instants(summary: AssembledSummary) -> dict[str, Any]:
        body = summary.bundle.model_dump(mode="json", by_alias=True, exclude_none=True)
        body.pop("timestamp")
        for entry in body["entry"]:
            entry["resource"].pop("date", None)
        return body

    assert _without_instants(first) == _without_instants(second)


def test_every_reference_the_composition_makes_resolves_to_an_entry() -> None:
    """A document whose sections point outside itself is a document nobody can read."""
    summary = _assemble(_dose(), _dose("FqlgKAG8HOu", display="MCH Measles dose"))
    composition = _composition(summary)

    served = {entry.fullUrl for entry in summary.bundle.entry or []}
    made = [composition.subject]
    made.extend(entry for section in composition.section or [] for entry in section.entry or [])
    named = [reference.reference for reference in made if reference is not None and reference.reference]
    assert named
    assert all(reference in served for reference in named)


@pytest.mark.parametrize("resource_type", ["Composition", "Patient", "Immunization"])
def test_every_entry_is_addressed_inside_the_document(resource_type: str) -> None:
    """`urn:uuid` and never a URL: an Immunization is not a resource type this facade serves."""
    summary = _assemble(_dose())

    urls = [
        entry.fullUrl
        for entry in summary.bundle.entry or []
        if entry.resource is not None and entry.resource.resourceType == resource_type
    ]
    assert urls
    assert all(url is not None and url.startswith("urn:uuid:") for url in urls)


def test_no_entry_carries_a_search_mode() -> None:
    """`Bundle-uv-ips` pins `entry.search`, `entry.request`, and `entry.response` to 0..0."""
    summary = _assemble(_dose())

    assert all(entry.search is None for entry in summary.bundle.entry or [])
