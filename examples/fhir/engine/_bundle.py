"""The one inline FHIR R4 Bundle every pure-evaluation example in this directory reads.

The engine evaluates expressions over FHIR-shaped JSON, so an example needs data and nothing else -
no DHIS2, no server, no project on disk. This module holds that data once: a small immunisation
clinic's records, shaped the way `d2w fhir serve --live` shapes a DHIS2 tracker cohort, so what an
expression says here is what it would say against real output.

Four children, three of whom were vaccinated, two of whom were weighed. Those counts are what the
measure example scores and what the retrieve example narrows, so a reader can check the engine's
answer against the entries below by eye.

`clinic.json` beside this file is `clinic_bundle()` written out for the command line, and
`packages/dhis2w-fhir-engine/tests/test_example_clinic_bundle.py` holds the two byte for byte equal.
"""

from __future__ import annotations

from typing import Any

SNOMED = "http://snomed.info/sct"
LOINC = "http://loinc.org"
UCUM = "http://unitsofmeasure.org"

MEASLES_VACCINE_CODE = "836383007"
DIPHTHERIA_VACCINE_CODE = "871908002"
BODY_WEIGHT_CODE = "29463-7"

MEASLES_VACCINES_VALUE_SET_URL = "http://example.org/fhir/ValueSet/measles-vaccines"
"""The value set the terminology and retrieve examples scope a retrieve with."""

TRACKED_ENTITY_IDENTIFIER_SYSTEM = "http://example.org/dhis2/trackedEntities"
"""The identifier system a DHIS2-derived Patient carries its tracked entity identifier under."""

CLINIC_REGISTER_IDENTIFIER_SYSTEM = "http://example.org/clinic/register"
"""A second identifier system, so a filter over `identifier.where(system = ...)` has something to pick."""


def _patient(identifier: str, given: tuple[str, ...], family: str, gender: str, birth_date: str) -> dict[str, Any]:
    """One child as a FHIR R4 Patient."""
    return {
        "resourceType": "Patient",
        "id": identifier,
        "active": True,
        "identifier": [
            {"system": TRACKED_ENTITY_IDENTIFIER_SYSTEM, "value": identifier},
            {"system": CLINIC_REGISTER_IDENTIFIER_SYSTEM, "value": f"REG-{identifier.split('-')[-1]}"},
        ],
        "name": [{"use": "official", "given": list(given), "family": family}],
        "gender": gender,
        "birthDate": birth_date,
        "managingOrganization": {"reference": "Organization/ngelehun-chc"},
    }


def _immunization(identifier: str, patient_identifier: str, code: str, display: str, given_on: str) -> dict[str, Any]:
    """One dose administered, as a FHIR R4 Immunization."""
    return {
        "resourceType": "Immunization",
        "id": identifier,
        "status": "completed",
        "patient": {"reference": f"Patient/{patient_identifier}"},
        "occurrenceDateTime": given_on,
        "vaccineCode": {"coding": [{"system": SNOMED, "code": code, "display": display}]},
    }


def _weight(identifier: str, patient_identifier: str, grams: int, measured_on: str) -> dict[str, Any]:
    """One weight in grams, as a FHIR R4 Observation."""
    return {
        "resourceType": "Observation",
        "id": identifier,
        "status": "final",
        "subject": {"reference": f"Patient/{patient_identifier}"},
        "effectiveDateTime": measured_on,
        "code": {"coding": [{"system": LOINC, "code": BODY_WEIGHT_CODE, "display": "Body weight"}]},
        "valueQuantity": {"value": grams, "unit": "g", "system": UCUM, "code": "g"},
    }


PATIENTS: list[dict[str, Any]] = [
    _patient("child-1", ("Amara", "Isata"), "Kamara", "female", "2023-02-11"),
    _patient("child-2", ("Bintu",), "Sesay", "female", "2023-05-30"),
    _patient("child-3", ("Chernor",), "Bangura", "male", "2023-08-14"),
    _patient("child-4", ("Daphne",), "Koroma", "female", "2024-01-09"),
]
"""Four children. `child-4` was never vaccinated, which is what the measure's numerator misses."""

IMMUNIZATIONS: list[dict[str, Any]] = [
    _immunization("dose-1", "child-1", MEASLES_VACCINE_CODE, "Measles vaccine", "2024-02-20"),
    _immunization("dose-2", "child-2", MEASLES_VACCINE_CODE, "Measles vaccine", "2024-06-11"),
    _immunization("dose-3", "child-2", DIPHTHERIA_VACCINE_CODE, "Diphtheria vaccine", "2024-06-11"),
    _immunization("dose-4", "child-3", DIPHTHERIA_VACCINE_CODE, "Diphtheria vaccine", "2024-09-02"),
]

OBSERVATIONS: list[dict[str, Any]] = [
    _weight("weight-1", "child-1", 9200, "2024-02-20"),
    _weight("weight-2", "child-2", 8100, "2024-06-11"),
]

ORGANIZATION: dict[str, Any] = {
    "resourceType": "Organization",
    "id": "ngelehun-chc",
    "name": "Ngelehun CHC",
    "active": True,
}


def clinic_bundle() -> dict[str, Any]:
    """The whole clinic as one FHIR R4 collection Bundle."""
    resources = [*PATIENTS, *IMMUNIZATIONS, *OBSERVATIONS, ORGANIZATION]
    return {
        "resourceType": "Bundle",
        "type": "collection",
        "entry": [{"resource": resource} for resource in resources],
    }


def one_patient() -> dict[str, Any]:
    """The first child on their own, for the examples that navigate a single resource."""
    return PATIENTS[0]
