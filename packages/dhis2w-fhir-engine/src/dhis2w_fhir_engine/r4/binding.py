"""The FHIR R4 version binding handed to the version-neutral evaluation core."""

from pathlib import Path

from ..binding import BuiltinCqlLibrary, FhirVersionBinding

FHIR_VERSION = "4.0.1"
"""The FHIR release this binding describes."""

STRUCTURE_DEFINITION_BASE = "http://hl7.org/fhir/StructureDefinition"
"""Canonical base URL for R4 core resource profiles."""

_SUBJECT_OR_PATIENT = ("subject.reference", "patient.reference")

_PATIENT_REFERENCE_PATHS: dict[str, tuple[str, ...]] = {
    "AllergyIntolerance": ("patient.reference",),
    "CarePlan": _SUBJECT_OR_PATIENT,
    "Claim": ("patient.reference",),
    "Condition": _SUBJECT_OR_PATIENT,
    "Coverage": ("beneficiary.reference",),
    "Device": ("patient.reference",),
    "DiagnosticReport": _SUBJECT_OR_PATIENT,
    "Encounter": _SUBJECT_OR_PATIENT,
    "ExplanationOfBenefit": ("patient.reference",),
    "Goal": _SUBJECT_OR_PATIENT,
    "Immunization": ("patient.reference",),
    "MedicationRequest": _SUBJECT_OR_PATIENT,
    "MedicationStatement": _SUBJECT_OR_PATIENT,
    "Observation": _SUBJECT_OR_PATIENT,
    "Procedure": _SUBJECT_OR_PATIENT,
}

_PROFILED_RESOURCE_TYPES = (
    "AllergyIntolerance",
    "CarePlan",
    "Condition",
    "DiagnosticReport",
    "Encounter",
    "Immunization",
    "MedicationRequest",
    "Observation",
    "Patient",
    "Procedure",
)


def _builtin_libraries() -> tuple[BuiltinCqlLibrary, ...]:
    """Read the CQL libraries shipped beside this binding."""
    builtin_directory = Path(__file__).parent / "builtins"
    fhir_helpers = builtin_directory / "FHIRHelpers.cql"
    if not fhir_helpers.exists():
        return ()
    return (
        BuiltinCqlLibrary(
            name="FHIRHelpers",
            version=FHIR_VERSION,
            source=fhir_helpers.read_text(encoding="utf-8"),
        ),
    )


R4_BINDING = FhirVersionBinding(
    name="R4",
    fhir_version=FHIR_VERSION,
    patient_reference_paths=_PATIENT_REFERENCE_PATHS,
    default_patient_reference_paths=_SUBJECT_OR_PATIENT,
    profile_base_urls={
        resource_type: f"{STRUCTURE_DEFINITION_BASE}/{resource_type}" for resource_type in _PROFILED_RESOURCE_TYPES
    },
    builtin_libraries=_builtin_libraries(),
)
"""The FHIR R4 binding: resource-type facts, profile URLs, and FHIRHelpers 4.0.1."""
