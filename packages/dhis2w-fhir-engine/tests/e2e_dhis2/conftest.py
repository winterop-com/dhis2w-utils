"""Live-stack fixtures that read seeded DHIS2 tracker data and map it into FHIR R4 resources.

`dhis2w-fhir-engine` ships no DHIS2 dependency: the engine evaluates FHIRPath and CQL over
FHIR-shaped JSON and knows nothing about tracker programs. The DHIS2 binding therefore lives here,
in the dev-only test tree, where `dhis2w-client` is available. Every import of `dhis2w_client` in
this member stays inside `tests/e2e_dhis2/`.

The cohort comes from the Sierra Leone demo database seeded by `make dhis2-run` /
`make dhis2-seed`: the Child Programme (`IpHINAT79UW`) tracked entities, their enrollments, and the
weight data values recorded on their events. The mapping into FHIR is deliberately small and
literal, so the numbers a test asserts are the numbers DHIS2 returned.
"""

from __future__ import annotations

import asyncio
import os
from datetime import date, datetime
from typing import Any

import httpx
import pytest
from dhis2w_client import BasicAuth, Dhis2ApiError, Dhis2Client
from pydantic import BaseModel, ConfigDict, Field

# --- Seeded DHIS2 metadata this test group reads -----------------------------------------------

CHILD_PROGRAMME_UID = "IpHINAT79UW"
"""Child Programme — the seeded tracker program whose tracked entities become FHIR Patients."""

FIRST_NAME_ATTRIBUTE_UID = "w75KJ2mc4zz"
LAST_NAME_ATTRIBUTE_UID = "zDhUuAYrxNC"
GENDER_ATTRIBUTE_UID = "cejWyOfXge6"

WEIGHT_DATA_ELEMENT_UIDS = ("UXz7xuGCEhU", "GQY2lXrypjO")
"""The two numeric weight data elements recorded on Child Programme events, both in grams."""

WEIGHT_UNIT_CODE = "g"
UCUM_SYSTEM = "http://unitsofmeasure.org"

TRACKED_ENTITY_PAGE_SIZE = 12
"""One small page, so the cohort stays fixed and the whole suite costs a handful of round-trips."""

DISTRICT_LEVEL = 2
DISTRICT_PAGE_SIZE = 6

DHIS2_GENDER_TO_FHIR = {"Male": "male", "Female": "female"}
"""DHIS2 stores the Child Programme gender attribute as free text; FHIR wants an AdministrativeGender code."""


# --- Connection settings -----------------------------------------------------------------------


class Dhis2StackSettings(BaseModel):
    """Connection details for the local DHIS2 stack the end-to-end tests read from."""

    model_config = ConfigDict(frozen=True)

    base_url: str
    username: str
    password: str

    @classmethod
    def from_environment(cls) -> Dhis2StackSettings:
        """Build settings from the variables `make dhis2-seed` writes into `.env.auth`."""
        return cls(
            base_url=os.environ.get("DHIS2_URL", "http://localhost:8080").rstrip("/"),
            username=os.environ.get("DHIS2_USERNAME", "admin"),
            password=os.environ.get("DHIS2_PASSWORD", "district"),
        )


def skip_unless_stack_reachable(settings: Dhis2StackSettings) -> None:
    """Skip the test when the local DHIS2 stack does not answer a short root probe."""
    try:
        with httpx.Client(timeout=2.0) as probe:
            probe.get(f"{settings.base_url}/dhis-web-login/")
    except (httpx.RequestError, httpx.HTTPError) as exc:
        pytest.skip(
            f"local DHIS2 stack not reachable at {settings.base_url} ({exc}). "
            "Run `make dhis2-run DHIS2_VERSION=43` first."
        )


# --- DHIS2 tracker wire shapes -----------------------------------------------------------------


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
    program_stage: str | None = Field(default=None, alias="programStage")
    occurred_at: datetime | None = Field(default=None, alias="occurredAt")
    data_values: list[TrackerDataValue] = Field(default_factory=list, alias="dataValues")


class TrackerEnrollment(BaseModel):
    """One enrollment of a tracked entity into a program, with its events."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    enrollment: str
    status: str | None = None
    enrolled_at: datetime | None = Field(default=None, alias="enrolledAt")
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


# --- The cohort, in terms this test group cares about ------------------------------------------


class WeightMeasurementRecord(BaseModel):
    """One weight in grams recorded on a Child Programme event."""

    model_config = ConfigDict(frozen=True)

    event_identifier: str
    data_element_identifier: str
    occurred_on: date
    weight_in_grams: float


class TrackedPersonRecord(BaseModel):
    """One Child Programme tracked entity, flattened to the fields the FHIR mapping needs."""

    model_config = ConfigDict(frozen=True)

    tracked_entity_identifier: str
    organisation_unit_identifier: str | None = None
    given_name: str | None = None
    family_name: str | None = None
    dhis2_gender: str | None = None
    date_of_birth: date | None = None
    enrollment_status: str | None = None
    weight_measurements: list[WeightMeasurementRecord] = Field(default_factory=list)

    @property
    def fhir_gender(self) -> str:
        """Map the DHIS2 gender attribute onto a FHIR AdministrativeGender code."""
        if self.dhis2_gender is None:
            return "unknown"
        return DHIS2_GENDER_TO_FHIR.get(self.dhis2_gender, "other")


class DistrictRecord(BaseModel):
    """One DHIS2 organisation unit at district level."""

    model_config = ConfigDict(frozen=True)

    organisation_unit_identifier: str
    name: str


class WeightDataElementRecord(BaseModel):
    """One weight data element, carrying the display name DHIS2 holds for it."""

    model_config = ConfigDict(frozen=True)

    identifier: str
    display_name: str


class SeededCohort(BaseModel):
    """The seeded DHIS2 records this test group read, plus their FHIR R4 projection.

    The mapping lives on the model so every test reads the same resources from the same fetch, and
    so a count asserted against the engine can be re-derived from `tracked_people` directly.
    """

    model_config = ConfigDict(frozen=True)

    base_url: str
    tracked_people: list[TrackedPersonRecord] = Field(default_factory=list)
    districts: list[DistrictRecord] = Field(default_factory=list)
    weight_data_elements: list[WeightDataElementRecord] = Field(default_factory=list)

    @property
    def weight_measurement_count(self) -> int:
        """Total number of weight data values across the whole cohort."""
        return sum(len(person.weight_measurements) for person in self.tracked_people)

    def weight_data_element_name(self, identifier: str) -> str:
        """Display name DHIS2 holds for a weight data element, falling back to its identifier."""
        for element in self.weight_data_elements:
            if element.identifier == identifier:
                return element.display_name
        return identifier

    def patient_resource(self, person: TrackedPersonRecord) -> dict[str, Any]:
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

    def observation_resources(self, person: TrackedPersonRecord) -> list[dict[str, Any]]:
        """Map one tracked entity's weight data values onto FHIR R4 Observation resources."""
        observations: list[dict[str, Any]] = []
        for measurement in person.weight_measurements:
            observations.append(
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
                                "display": self.weight_data_element_name(measurement.data_element_identifier),
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
            )
        return observations

    def organization_resources(self) -> list[dict[str, Any]]:
        """Map the fetched districts onto FHIR R4 Organization resources."""
        return [
            {
                "resourceType": "Organization",
                "id": district.organisation_unit_identifier,
                "name": district.name,
                "active": True,
            }
            for district in self.districts
        ]

    def patient_resources(self) -> list[dict[str, Any]]:
        """Every tracked entity in the cohort as a FHIR R4 Patient."""
        return [self.patient_resource(person) for person in self.tracked_people]

    def all_observation_resources(self) -> list[dict[str, Any]]:
        """Every weight data value in the cohort as a FHIR R4 Observation."""
        observations: list[dict[str, Any]] = []
        for person in self.tracked_people:
            observations.extend(self.observation_resources(person))
        return observations

    def bundle(self) -> dict[str, Any]:
        """The whole cohort as one FHIR R4 collection Bundle."""
        resources = self.patient_resources() + self.all_observation_resources() + self.organization_resources()
        return bundle_of(resources)

    def person_bundle(self, person: TrackedPersonRecord) -> dict[str, Any]:
        """One tracked entity and its observations as a patient-scoped collection Bundle."""
        return bundle_of([self.patient_resource(person), *self.observation_resources(person)])


def bundle_of(resources: list[dict[str, Any]]) -> dict[str, Any]:
    """Wrap FHIR resources in a collection Bundle."""
    return {
        "resourceType": "Bundle",
        "type": "collection",
        "entry": [{"resource": resource} for resource in resources],
    }


# --- Reading the cohort off the live stack -----------------------------------------------------

_TRACKED_ENTITY_FIELDS = (
    "trackedEntity,orgUnit,attributes,"
    "enrollments[enrollment,status,enrolledAt,occurredAt,events[event,programStage,occurredAt,dataValues]]"
)


def _attribute_value(entity: TrackerTrackedEntity, attribute_identifier: str) -> str | None:
    """Read one tracked entity attribute value by attribute identifier."""
    for attribute in entity.attributes:
        if attribute.attribute == attribute_identifier:
            return attribute.value
    return None


def _weight_measurements(enrollment: TrackerEnrollment) -> list[WeightMeasurementRecord]:
    """Collect the numeric weight data values recorded on one enrollment's events."""
    measurements: list[WeightMeasurementRecord] = []
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
                WeightMeasurementRecord(
                    event_identifier=event.event,
                    data_element_identifier=data_value.data_element,
                    occurred_on=event.occurred_at.date(),
                    weight_in_grams=weight_in_grams,
                )
            )
    return measurements


def _tracked_person(entity: TrackerTrackedEntity) -> TrackedPersonRecord:
    """Flatten one tracker payload entity into the record the FHIR mapping consumes."""
    enrollment = entity.enrollments[0] if entity.enrollments else None
    measurements: list[WeightMeasurementRecord] = []
    for each_enrollment in entity.enrollments:
        measurements.extend(_weight_measurements(each_enrollment))
    return TrackedPersonRecord(
        tracked_entity_identifier=entity.tracked_entity,
        organisation_unit_identifier=entity.organisation_unit,
        given_name=_attribute_value(entity, FIRST_NAME_ATTRIBUTE_UID),
        family_name=_attribute_value(entity, LAST_NAME_ATTRIBUTE_UID),
        dhis2_gender=_attribute_value(entity, GENDER_ATTRIBUTE_UID),
        # The Child Programme labels its enrollment incident date "Date of birth", so `occurredAt`
        # is the child's birth date on this program.
        date_of_birth=enrollment.occurred_at.date() if enrollment and enrollment.occurred_at else None,
        enrollment_status=enrollment.status if enrollment else None,
        weight_measurements=measurements,
    )


async def read_seeded_cohort(settings: Dhis2StackSettings) -> SeededCohort:
    """Read one page of Child Programme tracked entities, the districts, and the weight metadata."""
    auth = BasicAuth(username=settings.username, password=settings.password)
    async with Dhis2Client(settings.base_url, auth) as client:
        page = await client.get(
            "/api/tracker/trackedEntities",
            model=TrackedEntitiesPage,
            params={
                "program": CHILD_PROGRAMME_UID,
                "orgUnitMode": "ACCESSIBLE",
                "pageSize": TRACKED_ENTITY_PAGE_SIZE,
                "order": "createdAt:asc",
                "totalPages": "false",
                "fields": _TRACKED_ENTITY_FIELDS,
            },
        )
        organisation_units = await client.organisation_units.list_all(
            level=DISTRICT_LEVEL,
            page=1,
            page_size=DISTRICT_PAGE_SIZE,
        )
        weight_data_elements: list[WeightDataElementRecord] = []
        for data_element_identifier in WEIGHT_DATA_ELEMENT_UIDS:
            try:
                data_element = await client.data_elements.get(data_element_identifier)
            except Dhis2ApiError:
                continue
            weight_data_elements.append(
                WeightDataElementRecord(
                    identifier=data_element_identifier,
                    display_name=data_element.displayName or data_element.name or data_element_identifier,
                )
            )

    districts = [
        DistrictRecord(organisation_unit_identifier=unit.id, name=unit.displayName or unit.name or unit.id)
        for unit in organisation_units
        if unit.id
    ]
    return SeededCohort(
        base_url=settings.base_url,
        tracked_people=[_tracked_person(entity) for entity in page.tracked_entities],
        districts=districts,
        weight_data_elements=weight_data_elements,
    )


def skip_unless_cohort_usable(cohort: SeededCohort) -> None:
    """Skip when the stack is up but the seeded metadata these tests read is absent."""
    if not cohort.tracked_people:
        pytest.skip(
            f"DHIS2 at {cohort.base_url} has no Child Programme ({CHILD_PROGRAMME_UID}) tracked entities. "
            "Run `make dhis2-run DHIS2_VERSION=43` to start the seeded Sierra Leone demo database."
        )
    if not cohort.weight_data_elements:
        skipped = ", ".join(WEIGHT_DATA_ELEMENT_UIDS)
        pytest.skip(
            f"DHIS2 at {cohort.base_url} holds none of the Child Programme weight data elements ({skipped}). "
            "Run `make dhis2-run DHIS2_VERSION=43` to start the seeded Sierra Leone demo database."
        )
    if not cohort.districts:
        pytest.skip(
            f"DHIS2 at {cohort.base_url} has no organisation units at level {DISTRICT_LEVEL}. "
            "Run `make dhis2-run DHIS2_VERSION=43` to start the seeded Sierra Leone demo database."
        )
    if cohort.weight_measurement_count == 0:
        pytest.skip(
            f"the Child Programme tracked entities read from {cohort.base_url} carry no weight data values. "
            "Run `make dhis2-run DHIS2_VERSION=43` to start the seeded Sierra Leone demo database."
        )


# --- Fixtures ----------------------------------------------------------------------------------


@pytest.fixture(scope="session")
def dhis2_stack_settings() -> Dhis2StackSettings:
    """Connection settings for the local stack, skipping the group when it is unreachable."""
    settings = Dhis2StackSettings.from_environment()
    skip_unless_stack_reachable(settings)
    return settings


@pytest.fixture(scope="session")
def seeded_cohort(dhis2_stack_settings: Dhis2StackSettings) -> SeededCohort:
    """One live read of the seeded DHIS2 cohort, shared by every test in this group."""
    cohort = asyncio.run(read_seeded_cohort(dhis2_stack_settings))
    skip_unless_cohort_usable(cohort)
    return cohort


@pytest.fixture(scope="session")
def cohort_bundle(seeded_cohort: SeededCohort) -> dict[str, Any]:
    """The whole seeded cohort as one FHIR R4 collection Bundle."""
    return seeded_cohort.bundle()
