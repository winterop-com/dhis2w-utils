"""FHIRPath, CQL, and ELM evaluation over FHIR data, with clinical quality measure evaluation.

The grammar, parser, AST, and evaluator layers are FHIR-version-neutral: FHIRPath is normative and CQL
is 1.5, neither of which names a FHIR release. Everything bound to a concrete release lives under
`dhis2w_fhir_engine.r4` and reaches the neutral core as a `FhirVersionBinding` value, so a later
release lands as a sibling subpackage rather than a fork of the engine. Importing this package installs
R4 as the binding evaluators use when a caller supplies none.
"""

from .binding import NEUTRAL_BINDING, BuiltinCqlLibrary, FhirVersionBinding, default_binding, set_default_binding
from .engine import EvaluationContext, FHIRPathError, FHIRPathType, FunctionRegistry, Quantity
from .engine.cql import CQLEvaluator, CQLLibrary, compile_library, evaluate
from .engine.elm import ELMEvaluator, ELMLibrary, ELMLoader, ELMSerializer
from .engine.fhirpath import FHIRPathEvaluator, unwrap_primitives
from .r4 import (
    R4_BINDING,
    BundleDataSource,
    FHIRDataSource,
    InMemoryDataSource,
    InMemoryTerminologyService,
    MeasureEvaluator,
    MeasureReport,
    PatientBundleDataSource,
)

set_default_binding(R4_BINDING)

__all__ = [
    # Version binding
    "BuiltinCqlLibrary",
    "FhirVersionBinding",
    "NEUTRAL_BINDING",
    "R4_BINDING",
    "default_binding",
    "set_default_binding",
    # FHIRPath
    "EvaluationContext",
    "FHIRPathError",
    "FHIRPathEvaluator",
    "FHIRPathType",
    "FunctionRegistry",
    "Quantity",
    "unwrap_primitives",
    # CQL
    "CQLEvaluator",
    "CQLLibrary",
    "compile_library",
    "evaluate",
    # ELM
    "ELMEvaluator",
    "ELMLibrary",
    "ELMLoader",
    "ELMSerializer",
    # R4 data access and measures
    "BundleDataSource",
    "FHIRDataSource",
    "InMemoryDataSource",
    "InMemoryTerminologyService",
    "MeasureEvaluator",
    "MeasureReport",
    "PatientBundleDataSource",
]
