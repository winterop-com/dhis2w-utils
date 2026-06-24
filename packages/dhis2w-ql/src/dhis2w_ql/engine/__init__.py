"""Execution engine: source binding, pushdown planning, local execution, and sinks."""

from dhis2w_ql.engine.datasource import DataSource, InMemoryBinder, InMemoryDataSource, ResourceBinder
from dhis2w_ql.engine.executor import QueryEngine, QueryResult, serialize_rows, to_jsonable, write_rows
from dhis2w_ql.engine.plan import NativeFilter, NativeOrder, NativeQuery, QueryPlan, SourceCapabilities
from dhis2w_ql.engine.planner import plan_pipeline

__all__ = [
    "DataSource",
    "InMemoryBinder",
    "InMemoryDataSource",
    "NativeFilter",
    "NativeOrder",
    "NativeQuery",
    "QueryEngine",
    "QueryPlan",
    "QueryResult",
    "ResourceBinder",
    "SourceCapabilities",
    "plan_pipeline",
    "serialize_rows",
    "to_jsonable",
    "write_rows",
]
