"""FHIR version binding: the version-bound knowledge the version-neutral engine consumes as a value."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class BuiltinCqlLibrary(BaseModel):
    """A CQL library shipped with a FHIR version binding, such as FHIRHelpers."""

    model_config = ConfigDict(frozen=True)

    name: str
    version: str
    source: str


class FhirVersionBinding(BaseModel):
    """Everything the neutral evaluation core needs to know about one concrete FHIR version.

    The grammars, parsers, AST, and evaluators carry no FHIR version knowledge. Each version binding
    supplies the resource-type and element facts they need, and is handed to an evaluator as a value.
    A binding for another FHIR release is a sibling subpackage that builds one of these.
    """

    model_config = ConfigDict(frozen=True)

    name: str = Field(description="Short release name, e.g. 'R4'.")
    fhir_version: str = Field(description="Full version string as it appears in `using FHIR version`.")
    patient_reference_paths: dict[str, tuple[str, ...]] = Field(
        default_factory=dict,
        description="Per resource type, the element paths that reference the subject patient.",
    )
    default_patient_reference_paths: tuple[str, ...] = Field(
        default=(),
        description="Patient reference paths tried for resource types with no specific entry.",
    )
    profile_base_urls: dict[str, str] = Field(
        default_factory=dict,
        description="Per resource type, the canonical base StructureDefinition URL used by conformsTo().",
    )
    builtin_libraries: tuple[BuiltinCqlLibrary, ...] = Field(
        default=(),
        description="CQL libraries always resolvable during evaluation under this binding.",
    )

    def patient_paths_for(self, resource_type: str) -> tuple[str, ...]:
        """Return the patient reference paths for a resource type, falling back to the defaults."""
        return self.patient_reference_paths.get(resource_type, self.default_patient_reference_paths)

    def profile_url_for(self, resource_type: str) -> str | None:
        """Return the canonical base profile URL for a resource type, or None when unknown."""
        return self.profile_base_urls.get(resource_type)


NEUTRAL_BINDING = FhirVersionBinding(name="neutral", fhir_version="")
"""Binding with no version-bound facts, used when a caller supplies none and none is registered."""

_default_binding: FhirVersionBinding = NEUTRAL_BINDING


def set_default_binding(binding: FhirVersionBinding) -> None:
    """Install the binding that evaluators use when a caller passes none."""
    global _default_binding
    _default_binding = binding


def default_binding() -> FhirVersionBinding:
    """Return the binding evaluators use when a caller passes none."""
    return _default_binding


def resolve_binding(binding: "FhirVersionBinding | Any | None") -> FhirVersionBinding:
    """Return the caller's binding, or the installed default when the caller passed none."""
    if isinstance(binding, FhirVersionBinding):
        return binding
    return _default_binding
