"""One person's summary, assembled: the IPS document this toolchain can honestly build about them.

WHAT AN IPS IS, AND WHAT THIS BUILDS. One FHIR **document**: a Bundle whose first entry is a
`Composition` and whose remaining entries are the resources that Composition's sections point at.
`Bundle-uv-ips` fixes `type` to `document`, requires `identifier` and `timestamp`, and carries the
invariant `bdl-ips-1` - an IPS document has no `Composition` besides the first.
`Composition-uv-ips` pins `type` to the LOINC pattern `60591-5`, constrains `subject` to one
`Patient`, and sets `section` to 3..* with `title`, `code`, and `text` required on every section
present. This module builds exactly that, and `docs/fhir/design/ips.md` is the argument behind
every choice in it.

**IT IS A LIBRARY AND NOT A ROUTE.** Everything below is a pure function of what somebody already
read: the person as the register projects them, and the doses as the record surface projected them.
`dhis2w_fhir_serve.routes.summary` is one caller and `d2w fhir` is free to be another - nothing here
opens a connection, reads a store, or knows what a request is.

**THREE REQUIRED SECTIONS, AND WHAT THEY SAY WHEN NOTHING IS MAPPED.** Problems, Allergies and
Intolerances, and Medication Summary are the sections the IPS puts a `SHALL:populate` obligation on
the Creator actor for, and this project maps none of them (`docs/fhir/design/ips.md` section 6:
Allergies is `HONESTLY EMPTY`, the other two are `WITH A MAPPING` nobody has written yet). So each
carries `Composition.section.emptyReason`, which is what the invariant `ips-comp-1` accepts in place
of an entry, with the `unavailable` code out of R4's own `list-empty-reason`. Nothing is invented to
fill them: an unmapped stage does not become a free-text Observation and an unmapped element does not
get swept into `Results` on the grounds that it was numeric.

**THE ONE MAPPED SECTION IS IMMUNIZATIONS.** `[ips.sections.immunizations]` says which program
stages record doses and which of their data elements each record a dose of one vaccine, and every
entry here traces to a line somebody wrote in that table. A project that maps it and a person who
has no dose recorded are different facts and read differently: the section is present with an empty
reason for the person, and absent entirely for the project.

**THE CAVEAT IS PART OF THE DOCUMENT.** The IG says in as many words that a system that can never
populate the three obligated sections "can produce valid IPS Bundle instances, although it cannot
comply with the Creator (IPS) actor obligations" - two claims, and this toolchain has to be able to
make each separately (R5). So the document says so itself, in `Composition.text`: R4's own
human-readable rendering of a resource, which every reader of a document sees and which survives
being saved to a file. `summary_caveat` is the same sentence as text, for a caller that states it
beside the response as well - the two-place idiom `dhis2w_fhir_serve.projection.serving` argues for
the projection's as-of instant, and for the same reason: one fact, stated where resources are read
and stated again where responses are.

**DETERMINISTIC** (R4 in section 8). Two assemblies of an unchanged record differ in
`Bundle.timestamp` and `Composition.date` and in nothing else: the sections are in a fixed order,
the doses are in the record's own order, and every id is derived from a DHIS2 identifier through
`uuid5` rather than minted per call.

**NO PROFILE IS CLAIMED.** `meta.profile` names none of the IPS StructureDefinitions, because live
serve mode publishes no StructureDefinitions and resolves none (R8): the IG is a vocabulary this
document conforms to, not a dependency the generated country guide takes on.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

from dhis2w_fhir.notes import pluralize
from dhis2w_fhir.r4 import (
    Bundle,
    BundleEntry,
    CodeableConcept,
    Coding,
    Composition,
    CompositionSection,
    Identifier,
    Immunization,
    ImmunizationProtocolApplied,
    Narrative,
    Reference,
    RegisteredEntity,
    json_resource,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__ = [
    "ALLERGIES_SECTION",
    "IMMUNIZATIONS_SECTION",
    "IPS_COMPOSITION_TYPE_CODE",
    "LIST_EMPTY_REASON_SYSTEM",
    "LOINC_SYSTEM",
    "MEDICATIONS_SECTION",
    "PROBLEMS_SECTION",
    "REQUIRED_SECTIONS",
    "AssembledSummary",
    "IpsSection",
    "RecordedDose",
    "build_patient_summary",
    "summary_caveat",
]

#: The two vocabularies a summary's own scaffolding is coded from: LOINC for the document type and
#: every section, and R4's own reason list for a section that carries nothing.
LOINC_SYSTEM = "http://loinc.org"
LIST_EMPTY_REASON_SYSTEM = "http://terminology.hl7.org/CodeSystem/list-empty-reason"

#: The LOINC code `Composition-uv-ips` pins the document type to, and what it is called.
IPS_COMPOSITION_TYPE_CODE = "60591-5"
IPS_COMPOSITION_TYPE_DISPLAY = "Patient summary Document"

#: What the title of the whole document is, which is the name the IG gives the thing.
IPS_DOCUMENT_TITLE = "International Patient Summary"

#: The empty reason a section carries when this project maps nothing into it, and the one it carries
#: when the mapping is there and this person has nothing recorded under it. Both are `unavailable`
#: out of R4's own value set - the IG names `unavailable` and `notasked` as the two generally wanted,
#: and nobody was asked anything here - and the section's own narrative says which of the two
#: situations produced it, because that is the part a reader has to be able to tell apart.
EMPTY_REASON_UNAVAILABLE = "unavailable"

#: The identifier system a `urn:uuid` is stated under, which is IETF's own registered namespace.
URN_IDENTIFIER_SYSTEM = "urn:ietf:rfc:3986"


class IpsSection(BaseModel):
    """One section of the summary: its LOINC code, its title, and the display that code carries."""

    model_config = ConfigDict(frozen=True)

    code: str
    title: str
    display: str

    def concept(self) -> CodeableConcept:
        """The section code as the IG's own section table spells it."""
        return CodeableConcept(coding=[Coding(system=LOINC_SYSTEM, code=self.code, display=self.display)])


#: The three sections `Composition-uv-ips` slices as required, in the order the IG's table lists them.
#: Membership here is the Creator actor's `SHALL:populate` obligation, and it decides what an unmapped
#: section does: one of these is present with an `emptyReason`, and any other one is omitted.
PROBLEMS_SECTION = IpsSection(code="11450-4", title="Problems", display="Problem list - Reported")
ALLERGIES_SECTION = IpsSection(
    code="48765-2",
    title="Allergies and Intolerances",
    display="Allergies and adverse reactions Document",
)
MEDICATIONS_SECTION = IpsSection(
    code="10160-0", title="Medication Summary", display="History of Medication use Narrative"
)
REQUIRED_SECTIONS = (PROBLEMS_SECTION, ALLERGIES_SECTION, MEDICATIONS_SECTION)

#: The one recommended section this project maps, which the IG puts at `SHOULD:populate-if-known`.
IMMUNIZATIONS_SECTION = IpsSection(code="11369-6", title="Immunizations", display="History of Immunization Narrative")

#: What each unmapped required section states in its own narrative, in the words that name the actual
#: reason: DHIS2 marks no data element as belonging to any of them, and this project has said nothing.
_UNMAPPED_SECTION_TEXT = (
    "This project maps no DHIS2 data element into this section, so the summary carries nothing here. "
    "DHIS2 states no such mapping itself, and nothing is invented to fill the section."
)

#: What the Immunizations section states when the mapping is there and this person has no dose on it.
_NO_DOSE_TEXT = (
    "The doses this project maps are recorded on data elements this person holds no value for, so "
    "this instance records no immunisation for them."
)


class RecordedDose(BaseModel):
    """One dose one recorded event holds: which vaccine, when, and which dose of the series.

    Read off the record the facade already serves rather than off DHIS2 a second way: the caller
    projects one tracked entity's events through the very machinery
    `GET /facade/tracked-entities/{uid}/events` answers with, and hands the doses in it here. `display` is
    the data element's name as the guide publishes it, and `dose_number` is the value DHIS2 stored
    where that value names a dose - `Dose 2`, `IPT 1` - and nothing where the value is a plain
    statement that the dose was given.
    """

    model_config = ConfigDict(frozen=True)

    event_uid: str
    data_element_uid: str
    display: str | None = None
    occurred_at: str | None = None
    """When the event occurred, as an R4 `dateTime`, or nothing where the instance dated it unreadably."""

    dose_number: str | None = None


class AssembledSummary(BaseModel):
    """One assembled summary: the document, and the honest statement that goes beside it."""

    model_config = ConfigDict(frozen=True)

    bundle: Bundle
    caveat: str
    """What this document is and is not, in one sentence - the same words `Composition.text` carries."""

    creator_conformant: bool = False
    """Whether the document claims the Creator (IPS) actor's obligations, which today it never does.

    The three obligated sections are unmapped in every project this toolchain serves, so the answer
    is false and the caveat says so. It is a field rather than a constant because R5 asks this
    project to state validity and conformance as two separate claims, and a caller reading one
    should not have to infer the other from a sentence.
    """


def summary_caveat(*, mapped_sections: Sequence[str], dose_count: int) -> str:
    """The one sentence a summary states about itself, in the document and beside the response.

    Two situations and two sentences, because they are different facts and a reader has to be able
    to tell them apart: a summary with a mapped section carrying real content, and a summary whose
    clinical sections are all empty. Both are valid IPS documents and neither is conformance with
    the Creator (IPS) actor, which is what the closing clause states in both.
    """
    obligated = ", ".join(section.title for section in REQUIRED_SECTIONS)
    conformance = "This document is a valid IPS Bundle and does not claim the Creator (IPS) actor's obligations."
    if not mapped_sections:
        return (
            f"No clinical section of this summary is mapped. {obligated} are the three sections the IPS "
            "requires, and each states an empty reason rather than carrying content nobody nominated: "
            "DHIS2 marks no data element as a problem, an allergy, or a medication, and this project has "
            f"nominated none. {conformance}"
        )
    mapped = ", ".join(mapped_sections)
    return (
        f"{mapped} is mapped and carries {pluralize(dose_count, 'dose')} read from this "
        f"person's own record. {obligated} are the three sections the IPS requires, and each states an "
        "empty reason rather than carrying content nobody nominated: DHIS2 marks no data element as a "
        f"problem, an allergy, or a medication, and this project has nominated none. {conformance}"
    )


def build_patient_summary(
    subject: RegisteredEntity,
    doses: Sequence[RecordedDose],
    *,
    vaccine_code_system: str,
    assembled_at: str,
    author_display: str,
    immunizations_mapped: bool = False,
    unpublished_stage_uids: Sequence[str] = (),
) -> AssembledSummary:
    """Assemble one person's summary out of what the register and the record already say about them.

    `subject` is the very resource `GET /Patient/{uid}` answers with, carried into the document
    unchanged, so the person a summary is about and the person the register serves can never
    disagree. `doses` is what the record projected; `vaccine_code_system` is the DHIS2 data-element
    identifier namespace their vaccine codes are stated under - the same namespace the published
    section map maps out of, so the document and the map name one thing one way.

    `immunizations_mapped` is the project's own word rather than something inferred from `doses`
    being empty: a mapped section with no dose is a statement about this person, and an unmapped one
    is a statement about the project, and the summary has to make them differently.

    `unpublished_stage_uids` names the mapped stages this guide publishes no form for, which the
    section states in its own narrative. A guide narrower than its mapping and a person who was
    never vaccinated produce the same count of doses and are not the same fact.
    """
    tracked_entity_uid = subject.id or ""
    subject_reference = Reference(reference=_urn(subject.resourceType, tracked_entity_uid))
    immunizations = [_immunization(dose, subject_reference, vaccine_code_system) for dose in doses]
    sections = [_empty_section(section) for section in REQUIRED_SECTIONS]
    if immunizations_mapped:
        sections.append(_immunizations_section(immunizations, unpublished_stage_uids))
    mapped_sections = [IMMUNIZATIONS_SECTION.title] if immunizations_mapped else []
    caveat = summary_caveat(mapped_sections=mapped_sections, dose_count=len(immunizations))
    composition = Composition(
        id=f"{tracked_entity_uid}-ips",
        text=_narrative(caveat),
        identifier=Identifier(system=URN_IDENTIFIER_SYSTEM, value=_urn("Composition", tracked_entity_uid)),
        status="final",
        type=CodeableConcept(
            coding=[
                Coding(
                    system=LOINC_SYSTEM,
                    code=IPS_COMPOSITION_TYPE_CODE,
                    display=IPS_COMPOSITION_TYPE_DISPLAY,
                )
            ]
        ),
        subject=subject_reference,
        date=assembled_at,
        author=[Reference(display=author_display)],
        title=IPS_DOCUMENT_TITLE,
        section=sections,
    )
    # Every entry of a document is addressed inside the document rather than at this server: an
    # `Immunization` is not a resource type this facade serves at a URL, and a `fullUrl` pointing at
    # one would be a link nobody can follow. `urn:uuid` is R4's own answer, and deriving it from the
    # DHIS2 identity is what makes two assemblies of an unchanged record name the same resources.
    # The Composition leads, which is what makes the Bundle a document rather than a collection.
    entries = [
        BundleEntry(fullUrl=_urn(composition.resourceType, composition.id or ""), resource=json_resource(composition)),
        BundleEntry(fullUrl=subject_reference.reference, resource=json_resource(subject)),
        *(
            BundleEntry(
                fullUrl=_urn(immunization.resourceType, immunization.id or ""),
                resource=json_resource(immunization),
            )
            for immunization in immunizations
        ),
    ]
    return AssembledSummary(
        bundle=Bundle(
            id=f"{tracked_entity_uid}-ips",
            type="document",
            identifier=Identifier(system=URN_IDENTIFIER_SYSTEM, value=_urn("Bundle", tracked_entity_uid)),
            timestamp=assembled_at,
            entry=entries,
        ),
        caveat=caveat,
    )


def _urn(*parts: str) -> str:
    """A `urn:uuid` derived from DHIS2 identity, so one record always assembles the same references."""
    return f"urn:uuid:{uuid.uuid5(uuid.NAMESPACE_URL, '/'.join(parts))}"


def _narrative(text: str) -> Narrative:
    """The XHTML rendering `Composition.section.text` is required (1..1) to carry, and `text` beside it."""
    return Narrative(status="generated", div=f'<div xmlns="http://www.w3.org/1999/xhtml"><p>{text}</p></div>')


def _empty_reason() -> CodeableConcept:
    """The reason a section with no entry states, out of R4's own `list-empty-reason`."""
    return CodeableConcept(coding=[Coding(system=LIST_EMPTY_REASON_SYSTEM, code=EMPTY_REASON_UNAVAILABLE)])


def _empty_section(section: IpsSection) -> CompositionSection:
    """One required section this project maps nothing into: present, empty, and saying why."""
    return CompositionSection(
        title=section.title,
        code=section.concept(),
        text=_narrative(_UNMAPPED_SECTION_TEXT),
        emptyReason=_empty_reason(),
    )


def _immunizations_section(
    immunizations: list[Immunization], unpublished_stage_uids: Sequence[str]
) -> CompositionSection:
    """The mapped section: every dose this person's record holds, or the reason it holds none."""
    unread = _unread_stages_text(unpublished_stage_uids)
    if not immunizations:
        return CompositionSection(
            title=IMMUNIZATIONS_SECTION.title,
            code=IMMUNIZATIONS_SECTION.concept(),
            text=_narrative(f"{_NO_DOSE_TEXT}{unread}"),
            emptyReason=_empty_reason(),
        )
    stated = ", ".join(
        immunization.vaccineCode.coding[0].display or immunization.vaccineCode.coding[0].code or ""
        for immunization in immunizations
        if immunization.vaccineCode is not None and immunization.vaccineCode.coding
    )
    return CompositionSection(
        title=IMMUNIZATIONS_SECTION.title,
        code=IMMUNIZATIONS_SECTION.concept(),
        text=_narrative(
            f"{pluralize(len(immunizations), 'dose')} recorded on this person's own events: {stated}.{unread}"
        ),
        entry=[Reference(reference=_urn("Immunization", immunization.id or "")) for immunization in immunizations],
    )


def _unread_stages_text(unpublished_stage_uids: Sequence[str]) -> str:
    """What the section adds about a mapped stage this guide publishes no form for, or nothing."""
    if not unpublished_stage_uids:
        return ""
    named = ", ".join(unpublished_stage_uids)
    return (
        f" This project maps {pluralize(len(unpublished_stage_uids), 'program stage')} it publishes no "
        f"form for ({named}), so whatever those events hold is outside this document: generate the "
        "stage's Questionnaire to read them here."
    )


def _immunization(dose: RecordedDose, subject: Reference, vaccine_code_system: str) -> Immunization:
    """One recorded dose as the `Immunization` the section points at.

    `status` is `completed` and never `not-done`: DHIS2 records a value for what happened, and R4
    requires a `statusReason` on a dose that was not given - a reason no instance stated and this
    project will not invent. `vaccineCode` carries the data element's own DHIS2 coding, because on a
    DHIS2 immunisation form the data element **is** the vaccine and the value is the dose; the IPS
    binds `vaccineCode` preferably rather than requiredly, so this violates no profile.
    """
    return Immunization(
        id=f"{dose.event_uid}-{dose.data_element_uid}",
        status="completed",
        vaccineCode=CodeableConcept(
            coding=[Coding(system=vaccine_code_system, code=dose.data_element_uid, display=dose.display)]
        ),
        patient=subject,
        occurrenceDateTime=dose.occurred_at,
        occurrenceString=None if dose.occurred_at is not None else "unknown",
        protocolApplied=(
            None if dose.dose_number is None else [ImmunizationProtocolApplied(doseNumberString=dose.dose_number)]
        ),
    )
