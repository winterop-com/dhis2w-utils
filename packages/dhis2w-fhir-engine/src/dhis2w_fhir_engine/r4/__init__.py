"""FHIR R4 binding: everything in the engine that knows about a concrete FHIR release.

The grammars, parsers, AST, and evaluators one level up are version-neutral. This subpackage owns the
R4 facts they consume — resource-type element paths, canonical profile URLs, FHIRHelpers 4.0.1 — plus
the R4 data sources, measure evaluation, and terminology service. A later FHIR release lands as a
sibling subpackage exporting its own `FhirVersionBinding`.
"""

from .binding import FHIR_VERSION, R4_BINDING, STRUCTURE_DEFINITION_BASE
from .builtins import builtin_resolver, get_builtin_resolver
from .datasource import BundleDataSource, FHIRDataSource, InMemoryDataSource, PatientBundleDataSource
from .measure import (
    GroupResult,
    MeasureEvaluator,
    MeasureGroup,
    MeasurePopulation,
    MeasureReport,
    MeasureScoring,
    PatientResult,
    PopulationCount,
    PopulationType,
    StratifierResult,
)
from .terminology import (
    CodeableConcept,
    Coding,
    FHIRTerminologyService,
    InMemoryTerminologyService,
    MemberOfRequest,
    MemberOfResponse,
    SubsumesRequest,
    SubsumesResponse,
    TerminologyService,
    ValidateCodeRequest,
    ValidateCodeResponse,
    ValueSet,
)

__all__ = [
    # Version binding
    "FHIR_VERSION",
    "R4_BINDING",
    "STRUCTURE_DEFINITION_BASE",
    # Built-in CQL libraries
    "builtin_resolver",
    "get_builtin_resolver",
    # Data sources
    "BundleDataSource",
    "FHIRDataSource",
    "InMemoryDataSource",
    "PatientBundleDataSource",
    # Measure evaluation
    "GroupResult",
    "MeasureEvaluator",
    "MeasureGroup",
    "MeasurePopulation",
    "MeasureReport",
    "MeasureScoring",
    "PatientResult",
    "PopulationCount",
    "PopulationType",
    "StratifierResult",
    # Terminology
    "CodeableConcept",
    "Coding",
    "FHIRTerminologyService",
    "InMemoryTerminologyService",
    "MemberOfRequest",
    "MemberOfResponse",
    "SubsumesRequest",
    "SubsumesResponse",
    "TerminologyService",
    "ValidateCodeRequest",
    "ValidateCodeResponse",
    "ValueSet",
]
