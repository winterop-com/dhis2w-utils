"""d2ql: a pipeline query + transform language with the d2path expression core.

- `d2ql` is the pipeline language (`source | where | select | transform | order | limit >> sink`),
  with `define` / `define function` library definitions.
- `d2path` (in `dhis2w_ql.d2path`) is the embedded FHIRPath/JSONPath-compatible expression language.
- `dhis2w_ql.engine` runs a parsed library against a `ResourceBinder`, pushing supported work down
  to the source and evaluating the rest locally.
"""

from dhis2w_ql.ast import AggregateStage, CallSource, Define, DefineFunction, FoldStage, Library, Pipeline
from dhis2w_ql.d2path import EvalContext, Evaluator, Resolver
from dhis2w_ql.engine import (
    DataSource,
    InMemoryBinder,
    InMemoryDataSource,
    NativeFilter,
    NativeOrder,
    NativeQuery,
    QueryEngine,
    QueryPlan,
    QueryResult,
    ResourceBinder,
    SourceCapabilities,
    plan_pipeline,
    to_jsonable,
    write_rows,
)
from dhis2w_ql.errors import D2qlError, EvaluationError, LexError, ParseError, SemanticError
from dhis2w_ql.generate import DEFAULT_SCHEMA, GeneratedExample, SchemaSpec, generate
from dhis2w_ql.parser import parse, parse_expression, parse_pipeline
from dhis2w_ql.samples import SAMPLES, Sample, samples_by_category
from dhis2w_ql.tokenizer import Token, TokenKind, tokenize

__all__ = [
    "DEFAULT_SCHEMA",
    "AggregateStage",
    "CallSource",
    "D2qlError",
    "DataSource",
    "Define",
    "DefineFunction",
    "EvalContext",
    "EvaluationError",
    "Evaluator",
    "FoldStage",
    "GeneratedExample",
    "SchemaSpec",
    "generate",
    "InMemoryBinder",
    "InMemoryDataSource",
    "LexError",
    "Library",
    "NativeFilter",
    "NativeOrder",
    "NativeQuery",
    "ParseError",
    "Pipeline",
    "QueryEngine",
    "QueryPlan",
    "QueryResult",
    "SAMPLES",
    "Resolver",
    "ResourceBinder",
    "Sample",
    "SemanticError",
    "SourceCapabilities",
    "Token",
    "TokenKind",
    "parse",
    "parse_expression",
    "parse_pipeline",
    "plan_pipeline",
    "samples_by_category",
    "to_jsonable",
    "tokenize",
    "write_rows",
]
