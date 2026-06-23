"""d2path: a path + expression language with collection semantics.

d2path is the expression sub-language embedded in d2ql (used inside `where`, `select`, `order`,
and `transform`). It navigates plain dicts (any JSON, including FHIR) or pydantic models (DHIS2 wire
models) uniformly and evaluates a documented set of operators and functions.
"""

from dhis2w_ql.d2path.evaluator import EvalContext, Evaluator, Resolver

__all__ = ["EvalContext", "Evaluator", "Resolver"]
