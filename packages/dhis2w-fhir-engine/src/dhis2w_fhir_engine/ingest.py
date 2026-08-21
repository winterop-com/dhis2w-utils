"""The engine's boundary: a resource arrives as a wire dict or as a pydantic model, and becomes a dict here.

Every public entry point that ingests a FHIR resource - the evaluation contexts, the FHIRPath, CQL, and
ELM evaluators, the data sources, the measure evaluator - accepts `ResourceInput`. A model is dumped
exactly once, at that boundary, with `by_alias=True`, `exclude_none=True`, and `mode="json"`, which is
the same document the model would have serialised to. Everything below the boundary - the navigators,
the visitors, the retrieve filters - reads plain dicts and never sees a model.

The dump is a fresh structure, so an ingested model is never mutated by anything the engine does with it.
"""

from collections.abc import Iterable
from typing import Any

from pydantic import BaseModel

#: A FHIR resource as a caller may hand it over: the wire document, or a pydantic model of it.
type ResourceInput = dict[str, Any] | BaseModel


def as_resource_dict(resource: ResourceInput | None) -> dict[str, Any] | None:
    """Return the wire document for one ingested resource, dumping a model and passing a dict through."""
    if isinstance(resource, BaseModel):
        return resource.model_dump(mode="json", by_alias=True, exclude_none=True)
    return resource


def as_resource_dicts(resources: Iterable[ResourceInput]) -> list[dict[str, Any]]:
    """Return the wire documents for a collection of ingested resources."""
    return [dumped for resource in resources if (dumped := as_resource_dict(resource)) is not None]


def as_evaluation_input(value: ResourceInput | list[Any] | None) -> dict[str, Any] | list[Any] | None:
    """Return the input collection an expression evaluates over, dumping every model it holds."""
    if isinstance(value, list):
        return [as_resource_dict(item) if isinstance(item, BaseModel) else item for item in value]
    return as_resource_dict(value)
