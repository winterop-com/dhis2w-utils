"""Score a quality measure over real DHIS2 tracker data: read the cohort, map it to FHIR, run CQL.

The engine has no DHIS2 dependency at all - it evaluates expressions over FHIR-shaped JSON and knows
nothing about programs, stages, or data elements. That is what makes this example the interesting
one: everything DHIS2-specific happens in this file, above the engine, and the engine sees only FHIR.

Three steps, in order:

1. **Read.** One page of Child Programme (`IpHINAT79UW`) tracked entities off the live instance, with
   their enrollments and the weight data values recorded on their events.
2. **Map.** Each tracked entity becomes a `Patient`, each weight data value becomes an `Observation`,
   and both go into one collection `Bundle`. The mapping is deliberately small and literal, so the
   number the measure reports can be checked against the number DHIS2 returned.
3. **Score.** A CQL measure whose numerator is "has a weight recorded", evaluated once per child,
   rendered as a FHIR R4 MeasureReport.

The DHIS2 numbers are recomputed in Python first and asserted against the engine's answer, so this
example fails loudly if the mapping and the measure ever disagree.

Usage:
    uv run python examples/fhir/engine/e2e_measure_from_dhis2.py

Reads `DHIS2_URL`, `DHIS2_USERNAME`, and `DHIS2_PASSWORD` from the environment, defaulting to the
local stack at `http://localhost:8080` as `admin` / `district`.

Needs the seeded local stack (`make dhis2-run`). Unlike every other example in this directory, this
one talks to DHIS2 - the rest evaluate over inline data and need nothing running.
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import date, datetime
from typing import Any

import httpx
from dhis2w_client import BasicAuth, Dhis2Client
from dhis2w_fhir_engine.r4 import BundleDataSource, MeasureEvaluator, MeasureScoring, PopulationType
from pydantic import BaseModel, ConfigDict, Field

CHILD_PROGRAMME_UID = "IpHINAT79UW"
"""Child Programme - the seeded tracker program whose tracked entities become FHIR Patients."""

FIRST_NAME_ATTRIBUTE_UID = "w75KJ2mc4zz"
LAST_NAME_ATTRIBUTE_UID = "zDhUuAYrxNC"
GENDER_ATTRIBUTE_UID = "cejWyOfXge6"

WEIGHT_DATA_ELEMENT_UIDS = ("UXz7xuGCEhU", "GQY2lXrypjO")
"""The two numeric weight data elements recorded on Child Programme events, both in grams."""

TRACKED_ENTITY_PAGE_SIZE = 12
"""One small page, so the cohort stays fixed and the run costs a handful of round-trips."""

TRACKED_ENTITY_FIELDS = (
    "trackedEntity,orgUnit,attributes,"
    "enrollments[enrollment,status,enrolledAt,occurredAt,events[event,programStage,occurredAt,dataValues]]"
)

DHIS2_GENDER_TO_FHIR = {"Male": "male", "Female": "female"}
"""DHIS2 stores the Child Programme gender attribute as free text; FHIR wants an AdministrativeGender code."""

UCUM_SYSTEM = "http://unitsofmeasure.org"
WEIGHT_UNIT_CODE = "g"

WEIGHT_RECORDED_MEASURE = """
library Dhis2ChildProgrammeWeightRecorded version '1.0'
using FHIR version '4.0.1'

context Patient

define "Initial Population":
    true

define "Denominator":
    "Initial Population"

define "Numerator":
    exists([Observation])
"""


class TrackedEntityAttributeValue(BaseModel):
    """One tracked entity attribute value as `/api/tracker/trackedEntities` returns it."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    attribute: str
    value: str | None = None


class TrackerDataValue(BaseModel):
    """One event data value as `/api/tracker/trackedEntities` returns it."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    data_element: str = Field(alias="dataElement")
    value: str | None = None


class TrackerEvent(BaseModel):
    """One program stage event with the data values recorded on it."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    event: str
    occurred_at: datetime | None = Field(default=None, alias="occurredAt")
    data_values: list[TrackerDataValue] = Field(default_factory=list, alias="dataValues")


class TrackerEnrollment(BaseModel):
    """One enrollment of a tracked entity into a program, with its events."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    enrollment: str
    status: str | None = None
    occurred_at: datetime | None = Field(default=None, alias="occurredAt")
    events: list[TrackerEvent] = Field(default_factory=list)


class TrackerTrackedEntity(BaseModel):
    """One tracked entity with its attribute values and enrollments."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    tracked_entity: str = Field(alias="trackedEntity")
    organisation_unit: str | None = Field(default=None, alias="orgUnit")
    attributes: list[TrackedEntityAttributeValue] = Field(default_factory=list)
    enrollments: list[TrackerEnrollment] = Field(default_factory=list)


class TrackedEntitiesPage(BaseModel):
    """One page of `/api/tracker/trackedEntities`."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    tracked_entities: list[TrackerTrackedEntity] = Field(default_factory=list, alias="trackedEntities")


class WeightMeasurement(BaseModel):
    """One weight in grams recorded on a Child Programme event."""

    model_config = ConfigDict(frozen=True)

    event_identifier: str
    data_element_identifier: str
    occurred_on: date
    weight_in_grams: float


class TrackedPerson(BaseModel):
    """One Child Programme tracked entity, flattened to the fields the FHIR mapping needs."""

    model_config = ConfigDict(frozen=True)

    tracked_entity_identifier: str
    organisation_unit_identifier: str | None = None
    given_name: str | None = None
    family_name: str | None = None
    dhis2_gender: str | None = None
    date_of_birth: date | None = None
    weight_measurements: list[WeightMeasurement] = Field(default_factory=list)

    @property
    def fhir_gender(self) -> str:
        """Map the DHIS2 gender attribute onto a FHIR AdministrativeGender code."""
        if self.dhis2_gender is None:
            return "unknown"
        return DHIS2_GENDER_TO_FHIR.get(self.dhis2_gender, "other")


class SeededCohort(BaseModel):
    """The DHIS2 records this example read, plus their FHIR R4 projection."""

    model_config = ConfigDict(frozen=True)

    base_url: str
    tracked_people: list[TrackedPerson] = Field(default_factory=list)

    @property
    def weight_measurement_count(self) -> int:
        """Total number of weight data values across the whole cohort."""
        return sum(len(person.weight_measurements) for person in self.tracked_people)

    def patient_resource(self, person: TrackedPerson) -> dict[str, Any]:
        """Map one tracked entity onto a FHIR R4 Patient resource."""
        patient: dict[str, Any] = {
            "resourceType": "Patient",
            "id": person.tracked_entity_identifier,
            "identifier": [
                {
                    "system": f"{self.base_url}/api/tracker/trackedEntities",
                    "value": person.tracked_entity_identifier,
                }
            ],
            "gender": person.fhir_gender,
        }
        if person.given_name or person.family_name:
            name: dict[str, Any] = {"use": "official"}
            if person.family_name:
                name["family"] = person.family_name
            if person.given_name:
                name["given"] = [person.given_name]
            patient["name"] = [name]
        if person.date_of_birth is not None:
            patient["birthDate"] = person.date_of_birth.isoformat()
        if person.organisation_unit_identifier:
            patient["managingOrganization"] = {"reference": f"Organization/{person.organisation_unit_identifier}"}
        return patient

    def observation_resources(self, person: TrackedPerson) -> list[dict[str, Any]]:
        """Map one tracked entity's weight data values onto FHIR R4 Observation resources."""
        return [
            {
                "resourceType": "Observation",
                "id": f"{measurement.event_identifier}-{measurement.data_element_identifier}",
                "status": "final",
                "subject": {"reference": f"Patient/{person.tracked_entity_identifier}"},
                "effectiveDateTime": measurement.occurred_on.isoformat(),
                "code": {
                    "coding": [
                        {
                            "system": f"{self.base_url}/api/dataElements",
                            "code": measurement.data_element_identifier,
                        }
                    ]
                },
                "valueQuantity": {
                    "value": measurement.weight_in_grams,
                    "unit": WEIGHT_UNIT_CODE,
                    "system": UCUM_SYSTEM,
                    "code": WEIGHT_UNIT_CODE,
                },
            }
            for measurement in person.weight_measurements
        ]

    def patient_resources(self) -> list[dict[str, Any]]:
        """Every tracked entity in the cohort as a FHIR R4 Patient."""
        return [self.patient_resource(person) for person in self.tracked_people]

    def bundle(self) -> dict[str, Any]:
        """The whole cohort as one FHIR R4 collection Bundle."""
        resources = list(self.patient_resources())
        for person in self.tracked_people:
            resources.extend(self.observation_resources(person))
        return {
            "resourceType": "Bundle",
            "type": "collection",
            "entry": [{"resource": resource} for resource in resources],
        }


def _attribute_value(entity: TrackerTrackedEntity, attribute_identifier: str) -> str | None:
    """Read one tracked entity attribute value by attribute identifier."""
    for attribute in entity.attributes:
        if attribute.attribute == attribute_identifier:
            return attribute.value
    return None


def _weight_measurements(enrollment: TrackerEnrollment) -> list[WeightMeasurement]:
    """Collect the numeric weight data values recorded on one enrollment's events."""
    measurements: list[WeightMeasurement] = []
    for event in enrollment.events:
        if event.occurred_at is None:
            continue
        for data_value in event.data_values:
            if data_value.data_element not in WEIGHT_DATA_ELEMENT_UIDS or data_value.value is None:
                continue
            try:
                weight_in_grams = float(data_value.value)
            except ValueError:
                continue
            measurements.append(
                WeightMeasurement(
                    event_identifier=event.event,
                    data_element_identifier=data_value.data_element,
                    occurred_on=event.occurred_at.date(),
                    weight_in_grams=weight_in_grams,
                )
            )
    return measurements


def _tracked_person(entity: TrackerTrackedEntity) -> TrackedPerson:
    """Flatten one tracker payload entity into the record the FHIR mapping consumes."""
    enrollment = entity.enrollments[0] if entity.enrollments else None
    measurements: list[WeightMeasurement] = []
    for each_enrollment in entity.enrollments:
        measurements.extend(_weight_measurements(each_enrollment))
    return TrackedPerson(
        tracked_entity_identifier=entity.tracked_entity,
        organisation_unit_identifier=entity.organisation_unit,
        given_name=_attribute_value(entity, FIRST_NAME_ATTRIBUTE_UID),
        family_name=_attribute_value(entity, LAST_NAME_ATTRIBUTE_UID),
        dhis2_gender=_attribute_value(entity, GENDER_ATTRIBUTE_UID),
        # The Child Programme labels its enrollment incident date "Date of birth", so `occurredAt`
        # is the child's birth date on this program.
        date_of_birth=enrollment.occurred_at.date() if enrollment and enrollment.occurred_at else None,
        weight_measurements=measurements,
    )


async def read_seeded_cohort(base_url: str, username: str, password: str) -> SeededCohort:
    """Read one page of Child Programme tracked entities off the live instance."""
    async with Dhis2Client(base_url, BasicAuth(username=username, password=password)) as client:
        page = await client.get(
            "/api/tracker/trackedEntities",
            model=TrackedEntitiesPage,
            params={
                "program": CHILD_PROGRAMME_UID,
                "orgUnitMode": "ACCESSIBLE",
                "pageSize": TRACKED_ENTITY_PAGE_SIZE,
                # `createdAt`, not `trackedEntity`: ordering by the identifier answers 409 E7145 on
                # 2.43.1 with an ambiguous column reference. See BUGS.md #97.
                "order": "createdAt:asc",
                "totalPages": "false",
                "fields": TRACKED_ENTITY_FIELDS,
            },
        )
    return SeededCohort(
        base_url=base_url,
        tracked_people=[_tracked_person(entity) for entity in page.tracked_entities],
    )


async def main() -> None:
    """Read the DHIS2 cohort, map it into FHIR, score the measure, and check the counts agree."""
    base_url = os.environ.get("DHIS2_URL", "http://localhost:8080").rstrip("/")
    username = os.environ.get("DHIS2_USERNAME", "admin")
    password = os.environ.get("DHIS2_PASSWORD", "district")

    print(f"reading Child Programme ({CHILD_PROGRAMME_UID}) tracked entities from {base_url}")
    cohort = await read_seeded_cohort(base_url, username, password)

    if not cohort.tracked_people:
        print(
            f"error: {base_url} holds no Child Programme ({CHILD_PROGRAMME_UID}) tracked entities. "
            "Run `make dhis2-run` to start the seeded Sierra Leone demo database.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    # The DHIS2-side answer, computed in Python before the engine is asked anything.
    expected_denominator = len(cohort.tracked_people)
    expected_numerator = sum(1 for person in cohort.tracked_people if person.weight_measurements)
    print(f"  {expected_denominator} tracked entities, {cohort.weight_measurement_count} weight data values")
    print(f"  {expected_numerator} of those children carry at least one weight")
    print()

    bundle = cohort.bundle()
    print(f"mapped to a {bundle['type']} Bundle of {len(bundle['entry'])} FHIR resources")
    print("  one Patient per tracked entity, one Observation per weight data value")
    print()

    data_source = BundleDataSource(bundle)
    evaluator = MeasureEvaluator(data_source=data_source)
    evaluator.set_scoring(MeasureScoring.PROPORTION)
    evaluator.load_measure(WEIGHT_RECORDED_MEASURE)

    report = evaluator.evaluate_population(cohort.patient_resources(), data_source=data_source)
    group = report.groups[0]
    denominator = group.populations[PopulationType.DENOMINATOR.value].count
    numerator = group.populations[PopulationType.NUMERATOR.value].count

    print(f"measure {report.measure_id}, scored as a {MeasureScoring.PROPORTION.value}")
    print(f"  denominator  {denominator}   every mapped tracked entity")
    print(f"  numerator    {numerator}   those with a weight recorded on a DHIS2 event")
    print(f"  score        {group.measure_score}")
    print()

    if (denominator, numerator) != (expected_denominator, expected_numerator):
        print(
            f"error: the engine scored {numerator}/{denominator} but DHIS2's own records say "
            f"{expected_numerator}/{expected_denominator} - the mapping and the measure disagree",
            file=sys.stderr,
        )
        raise SystemExit(1)

    fhir_report = report.to_fhir()
    print(f"to_fhir() -> a {fhir_report['resourceType']} citing measure {fhir_report['measure']}")
    print(f"  numerator identifiers: {sorted(group.populations[PopulationType.NUMERATOR.value].patients)[:4]} ...")
    print()
    print("The engine imported no DHIS2 module. Everything above the Bundle is this file's work;")
    print("everything below it is FHIRPath, CQL, and a MeasureReport.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except httpx.RequestError as error:
        print(
            f"error: no DHIS2 answered at {error.request.url.host}:{error.request.url.port} ({error}). "
            "Run `make dhis2-run`, or set DHIS2_URL, DHIS2_USERNAME and DHIS2_PASSWORD to your own instance.",
            file=sys.stderr,
        )
        raise SystemExit(1) from error
