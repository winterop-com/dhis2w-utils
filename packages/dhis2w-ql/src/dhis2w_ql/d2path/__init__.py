"""d2path: a FHIRPath/JSONPath-compatible path + expression language with collection semantics.

d2path is the expression sub-language embedded in d2ql (used inside `where`, `select`, `order`,
and `transform`). It navigates plain dicts (FHIR/JSON) or pydantic models (DHIS2 wire models)
uniformly and evaluates a documented FHIRPath-compatible subset of operators and functions.
"""

from dhis2w_ql.d2path.evaluator import EvalContext, Evaluator, Resolver

__all__ = ["EvalContext", "Evaluator", "Resolver"]
