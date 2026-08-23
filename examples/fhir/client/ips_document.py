"""One person's DHIS2 tracker record assembled into an International Patient Summary document.

An IPS is one FHIR `document`: a Bundle whose first entry is a Composition and whose remaining
entries are the resources that Composition's sections point at.

**This is the assembly done by hand, in typed Python, against a live instance.** The served
surface is `d2w fhir serve --live` answering `GET /Patient/{uid}/$summary`
([`../cli/summary.sh`](../cli/summary.sh) walks it), and it maps its one section through
[`[ips.sections]`](../../../docs/fhir/301-what-goes-in.md#ips-sections) rather than through
constants. This file states its own nominations instead, and maps a different section - **Results**
rather than Immunizations - so that what it shows is how a section is assembled at all, over a
project whose `fhir.toml` nominates nothing.

**What it maps.** `Patient.name` from the two tracked entity attributes nominated below as the given
and family halves - DHIS2 has no name field, so a name is a nomination or it is nothing. Then the
**Results** section (LOINC `30954-2`), one `Observation` per data value of a nominated data element,
each coded by the data element's own DHIS2 identity, because nothing maps a DHIS2 data element onto
SNOMED CT or LOINC yet. The value stays the string DHIS2 sent: a `Quantity` needs a unit and a unit
system nobody has stated.

**What it asserts absent, and how.** IPS v2.0.1 (STU 2) removed the `absent-unknown-uv-ips` code
system, so absence is stated one of two ways, and the three sections the Creator actor SHALL
populate show both. **Problems** and **Allergies and Intolerances** each carry an entry asserting
absence - a `Condition` and an `AllergyIntolerance` coded SNOMED CT `1287211007` "No information
available". **Medication Summary** carries `emptyReason` `unavailable` and no entry, which the
invariant `ips-comp-1` accepts instead. Both are valid; neither is conformance with the Creator
(IPS) actor, and which one this project should serve is a call the paper reserves.

`Patient.birthDate` is required (1..1) and this instance publishes no birth-date attribute to
nominate, so the element carries the data-absent-reason extension with `unknown` on its `_birthDate`
sibling - the IG's own worked example. `Patient.gender` is left off entirely, because this file states
no gender map: `gender` is bound to `administrative-gender` with a required binding, and the
translation is `[ips.identity.administrative_gender]`'s to state and `D2Sex_CM`'s to publish.

No IPS validator runs offline, so the verification story is this example's own reference check -
every reference the Composition makes resolves to a Bundle entry - plus the model round-trips in
`packages/dhis2w-fhir/tests/test_fhir_r4_schemas.py`.

The person, the enrollment, and the two events are created here and deleted again before the run
ends, so the example leaves the instance exactly as it found it.

Usage:
    uv run python examples/fhir/client/ips_document.py

Requires a DHIS2 profile (`d2w profile list`) and the seeded Child Programme.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from _runner import run_example
from dhis2w_client import Dhis2ApiError
from dhis2w_client.generated.v42.oas import TrackerTrackedEntity
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import profile_from_env
from dhis2w_fhir.r4 import (
    DATA_ABSENT_REASON_EXTENSION_URL,
    AllergyIntolerance,
    Bundle,
    BundleEntry,
    CodeableConcept,
    Coding,
    Composition,
    CompositionSection,
    Condition,
    Element,
    Extension,
    HumanName,
    Identifier,
    Narrative,
    Observation,
    Organization,
    Patient,
    Reference,
    json_resource,
    zoned_date_time,
)
from pydantic import BaseModel, ConfigDict

#: The seeded tracker program this reads a record out of, and the two stages it logs a visit on.
PROGRAM = "IpHINAT79UW"
TRACKED_ENTITY_TYPE = "nEenWmSyUEp"
BIRTH_STAGE = "A03MvHHogjR"
POSTNATAL_STAGE = "ZzYYXq4fJie"

#: What the created record holds, by DHIS2 identifier, and when. Fixed, so two runs of this example
#: differ in nothing but the UIDs DHIS2 mints.
ATTRIBUTE_VALUES = {"w75KJ2mc4zz": "Aminata", "zDhUuAYrxNC": "Kamara", "cejWyOfXge6": "Female"}
BIRTH_DATA_VALUES = {"a3kGcGDCuk6": "8", "UXz7xuGCEhU": "3200"}
POSTNATAL_DATA_VALUES = {"GQY2lXrypjO": "4100"}
BIRTH_DATE = "2026-01-05"
POSTNATAL_DATE = "2026-02-16"

#: The instant the summary states it was assembled, on `Bundle.timestamp` and `Composition.date`. A
#: served summary would stamp the real one; a constant is what keeps two runs here comparable.
ASSEMBLED_AT = "2026-03-01T09:00:00Z"

#: The systems the codes here are drawn from. The three DHIS2 ones are what a generated guide
#: publishes its own identifiers under.
TRACKED_ENTITY_SYSTEM = "http://example.org/fhir/id/tracked-entity"
ORGANISATION_UNIT_SYSTEM = "http://example.org/fhir/id/organisation-unit"
DATA_ELEMENT_SYSTEM = "http://example.org/fhir/CodeSystem/d2-de-cs"
LOINC = "http://loinc.org"
SNOMED = "http://snomed.info/sct"
LIST_EMPTY_REASON = "http://terminology.hl7.org/CodeSystem/list-empty-reason"


#: What a document bundle carries, entry by entry: the Composition and everything it reaches.
type CarriedResource = Composition | Patient | Organization | Condition | AllergyIntolerance | Observation


class IdentityNomination(BaseModel):
    """Which tracked entity attribute carries which demographic fact - the paper's `[ips.identity]`."""

    model_config = ConfigDict(frozen=True)

    given_name: str
    family_name: str
    birth_date: str | None = None
    sex: str | None = None


class SummarySection(BaseModel):
    """One assembled section, with the account this example prints for it beside it."""

    model_config = ConfigDict(frozen=True)

    section: CompositionSection
    populated: bool
    note: str


class AssembledSummary(BaseModel):
    """The document this example assembles, and the sections it was assembled out of."""

    model_config = ConfigDict(frozen=True)

    bundle: Bundle
    sections: list[SummarySection]


#: The identity nominations, stated for this instance. It publishes no birth-date attribute at all,
#: which is why `birth_date` names none - and why the subject's birth date is a stated absence.
IDENTITY = IdentityNomination(given_name="w75KJ2mc4zz", family_name="zDhUuAYrxNC", sex="cejWyOfXge6")

#: Which data elements belong in which IPS section - what `[ips.sections]` states for a served
#: summary, stated here for the one section this file assembles.
RESULTS_DATA_ELEMENTS = ("a3kGcGDCuk6", "UXz7xuGCEhU", "GQY2lXrypjO")

#: The concept the IPS leaves for a section a system holds nothing about, now that v2.0.1 has
#: removed the `absent-unknown-uv-ips` code system: an ordinary resource, an exceptional concept.
NO_INFORMATION_AVAILABLE = CodeableConcept(
    coding=[Coding(system=SNOMED, code="1287211007", display="No information available")]
)


def urn(*parts: str) -> str:
    """A `urn:uuid` derived from DHIS2 identity, so one record always assembles the same references."""
    return f"urn:uuid:{uuid.uuid5(uuid.NAMESPACE_URL, '/'.join(parts))}"


def narrative(text: str) -> Narrative:
    """The XHTML rendering every `Composition.section.text` is required (1..1) to carry."""
    return Narrative(status="generated", div=f'<div xmlns="http://www.w3.org/1999/xhtml">{text}</div>')


def loinc(code: str, display: str) -> CodeableConcept:
    """One IPS section code, spelled as the IG's section table spells it."""
    return CodeableConcept(coding=[Coding(system=LOINC, code=code, display=display)])


def attribute_value(entity: TrackerTrackedEntity, attribute_uid: str | None) -> str | None:
    """One attribute value off the entity or off its enrollments; None when nobody stated it."""
    if attribute_uid is None:
        return None
    holders = list(entity.attributes or [])
    for enrollment in entity.enrollments or []:
        holders.extend(enrollment.attributes or [])
    return next((held.value for held in holders if held.attribute == attribute_uid and held.value), None)


def event_date_time(occurred_at: datetime | int | None) -> str | None:
    """An event date as an R4 dateTime - DHIS2 sends the wall clock with no zone (BUGS.md #62)."""
    return zoned_date_time(occurred_at.isoformat()) if isinstance(occurred_at, datetime) else None


def patient_of(entity: TrackerTrackedEntity) -> Patient:
    """The subject: the nominated names, and a stated absence where a nomination has no value."""
    tracked_entity_uid = entity.trackedEntity or ""
    given = attribute_value(entity, IDENTITY.given_name)
    birth_date = attribute_value(entity, IDENTITY.birth_date)
    absent = Element(extension=[Extension(url=DATA_ABSENT_REASON_EXTENSION_URL, valueCode="unknown")])
    return Patient(
        id=tracked_entity_uid,
        identifier=[Identifier(system=TRACKED_ENTITY_SYSTEM, value=tracked_entity_uid)],
        name=[HumanName(family=attribute_value(entity, IDENTITY.family_name), given=[given] if given else None)],
        birthDate=birth_date,
        birthDate_element=None if birth_date else absent,
    )


def observations_of(entity: TrackerTrackedEntity, subject: Reference, names: dict[str, str]) -> list[Observation]:
    """One Observation per data value of a nominated data element, events in date order."""
    events = [event for enrollment in entity.enrollments or [] for event in enrollment.events or []]
    return [
        Observation(
            id=f"{event.event}-{data_element}",
            status="final",
            code=CodeableConcept(
                coding=[Coding(system=DATA_ELEMENT_SYSTEM, code=data_element, display=names.get(data_element))]
            ),
            subject=subject,
            effectiveDateTime=event_date_time(event.occurredAt),
            valueString=value,
        )
        for event in sorted(events, key=lambda held: str(held.occurredAt))
        for data_element in RESULTS_DATA_ELEMENTS
        for value in [{held.dataElement: held.value for held in event.dataValues or []}.get(data_element)]
        if value is not None
    ]


def sections_of(
    absent_problem: Condition, absent_allergy: AllergyIntolerance, observations: list[Observation]
) -> list[SummarySection]:
    """The four sections this record can honestly carry, in the order the document states them."""
    return [
        SummarySection(
            section=CompositionSection(
                title="Problems",
                code=loinc("11450-4", "Problem list - Reported"),
                text=narrative("This DHIS2 instance states nothing about this person's problems."),
                entry=[Reference(reference=urn("Condition", absent_problem.id or ""))],
            ),
            populated=False,
            note="asserted absence: a Condition coded SNOMED CT 1287211007",
        ),
        SummarySection(
            section=CompositionSection(
                title="Allergies and Intolerances",
                code=loinc("48765-2", "Allergies and adverse reactions Document"),
                text=narrative("This DHIS2 instance collects no allergy information."),
                entry=[Reference(reference=urn("AllergyIntolerance", absent_allergy.id or ""))],
            ),
            populated=False,
            note="asserted absence: an AllergyIntolerance coded SNOMED CT 1287211007",
        ),
        SummarySection(
            section=CompositionSection(
                title="Medication Summary",
                code=loinc("10160-0", "History of Medication use Narrative"),
                text=narrative("This DHIS2 instance states nothing about this person's medication."),
                emptyReason=CodeableConcept(coding=[Coding(system=LIST_EMPTY_REASON, code="unavailable")]),
            ),
            populated=False,
            note="emptyReason unavailable, and no entry at all",
        ),
        SummarySection(
            section=CompositionSection(
                title="Results",
                code=loinc("30954-2", "Relevant diagnostic tests/laboratory data Narrative"),
                text=narrative(f"{len(observations)} value(s) on the nominated data elements."),
                entry=[Reference(reference=urn("Observation", held.id or "")) for held in observations] or None,
            ),
            populated=bool(observations),
            note="one Observation per data value, coded by DHIS2 identity",
        ),
    ]


def assemble(entity: TrackerTrackedEntity, organisation: Organization, names: dict[str, str]) -> AssembledSummary:
    """Assemble the whole document: the subject, the one mapped section, and the three required ones."""
    tracked_entity_uid = entity.trackedEntity or ""
    subject = Reference(reference=urn("Patient", tracked_entity_uid))
    absent_problem = Condition(id=f"{tracked_entity_uid}-problems", code=NO_INFORMATION_AVAILABLE, subject=subject)
    absent_allergy = AllergyIntolerance(
        id=f"{tracked_entity_uid}-allergies", code=NO_INFORMATION_AVAILABLE, patient=subject
    )
    observations = observations_of(entity, subject, names)
    sections = sections_of(absent_problem, absent_allergy, observations)
    composition = Composition(
        id=f"{tracked_entity_uid}-ips",
        identifier=Identifier(system="urn:ietf:rfc:3986", value=urn("Composition", tracked_entity_uid)),
        status="final",
        type=loinc("60591-5", "Patient summary Document"),
        subject=subject,
        date=ASSEMBLED_AT,
        author=[Reference(reference=urn("Organization", organisation.id or ""))],
        title="International Patient Summary",
        section=[carried.section for carried in sections],
    )
    # The Composition first, then every resource its sections reach, each at the `urn:uuid` its
    # references name. `bdl-ips-1`: a document carries no second Composition.
    entries: list[CarriedResource] = [
        composition,
        patient_of(entity),
        organisation,
        absent_problem,
        absent_allergy,
        *observations,
    ]
    bundle = Bundle(
        type="document",
        identifier=Identifier(system="urn:ietf:rfc:3986", value=urn("Bundle", tracked_entity_uid)),
        timestamp=ASSEMBLED_AT,
        entry=[
            BundleEntry(fullUrl=urn(resource.resourceType, resource.id or ""), resource=json_resource(resource))
            for resource in entries
        ],
    )
    return AssembledSummary(bundle=bundle, sections=sections)


def unresolved_references(summary: AssembledSummary) -> list[str]:
    """Every reference the Composition makes that no entry of the bundle answers."""
    served = {entry.fullUrl for entry in summary.bundle.entry or []}
    documents = [entry.resource for entry in summary.bundle.entry or [] if entry.resource is not None]
    composition = Composition.model_validate(documents[0].model_dump(by_alias=True))
    made = [composition.subject, *(composition.author or [])]
    made.extend(entry for carried in summary.sections for entry in carried.section.entry or [])
    named = [reference.reference for reference in made if reference is not None and reference.reference]
    return sorted(reference for reference in named if reference not in served)


async def main() -> None:
    """Create one record, assemble the summary it can honestly carry, then delete what was created."""
    async with open_client(profile_from_env()) as client:
        facilities = await client.resources.organisation_units.list(
            fields="id,name", filters=["level:eq:4"], page_size=1
        )
        organisation_unit: Any = facilities[0]
        organisation = Organization(
            id=organisation_unit.id,
            identifier=[Identifier(system=ORGANISATION_UNIT_SYSTEM, value=organisation_unit.id)],
            name=organisation_unit.name,
        )
        elements = await client.resources.data_elements.list(
            fields="id,name", filters=[f"id:in:[{','.join(RESULTS_DATA_ELEMENTS)}]"]
        )
        names = {element.id: element.name for element in elements}
        registered = await client.tracker.register(
            program=PROGRAM,
            org_unit=organisation_unit.id,
            tracked_entity_type=TRACKED_ENTITY_TYPE,
            attributes=ATTRIBUTE_VALUES,
            enrolled_at=BIRTH_DATE,
            events=[
                {"program_stage": BIRTH_STAGE, "occurred_at": BIRTH_DATE, "data_values": BIRTH_DATA_VALUES},
                {"program_stage": POSTNATAL_STAGE, "occurred_at": POSTNATAL_DATE, "data_values": POSTNATAL_DATA_VALUES},
            ],
        )
        print(f"created tracked entity {registered.tracked_entity} at {organisation_unit.name}")
        try:
            raw = await client.get_raw(
                f"/api/tracker/trackedEntities/{registered.tracked_entity}",
                params={
                    "fields": "trackedEntity,trackedEntityType,orgUnit,attributes[attribute,value],"
                    "enrollments[enrollment,attributes[attribute,value],"
                    "events[event,programStage,occurredAt,dataValues[dataElement,value]]]"
                },
            )
            summary = assemble(TrackerTrackedEntity.model_validate(raw), organisation, names)
            print("\nsection by section:")
            for carried in summary.sections:
                state = "populated" if carried.populated else "absent"
                entries = len(carried.section.entry or [])
                print(f"  {carried.section.title:<28} {state:<10} {entries} entry(ies) - {carried.note}")
            dangling = unresolved_references(summary)
            print(f"\nevery reference the Composition makes resolves to a Bundle entry: {not dangling}")
            if dangling:
                print(f"  unresolved: {dangling}")
            print()
            print(summary.bundle.model_dump_json(indent=2, exclude_none=True, by_alias=True))
        finally:
            await client.post_raw(
                "/api/tracker",
                body={"trackedEntities": [{"trackedEntity": registered.tracked_entity}]},
                params={"importStrategy": "DELETE", "async": "false"},
            )
            print(f"\ndeleted tracked entity {registered.tracked_entity}, with its enrollment and its events")
            try:
                await client.get_raw(f"/api/tracker/trackedEntities/{registered.tracked_entity}")
            except Dhis2ApiError as error:
                print(f"the instance no longer holds it: HTTP {error.status_code}")


if __name__ == "__main__":
    run_example(main)
