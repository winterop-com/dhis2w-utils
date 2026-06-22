"""Plan models: what a pipeline pushes down to a source vs. what runs locally.

`NativeQuery` is the part a capable source (e.g. the DHIS2 list endpoint) can satisfy directly —
filters, ordering, and paging. `QueryPlan` pairs it with the residual stages the engine evaluates
locally over the fetched rows. Source-agnostic: a DHIS2 compiler turns `NativeQuery` into
`filter=`/`order=`/paging params; an in-memory source ignores it and lets everything run local.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from dhis2w_ql.ast import Stage


class SourceCapabilities(BaseModel):
    """Declares which pushdown operations a source can satisfy natively."""

    model_config = ConfigDict(frozen=True)

    filter: bool = False
    order: bool = False
    paging: bool = False


class NativeFilter(BaseModel):
    """A single field filter pushed to the source (`property OPERATOR value`)."""

    model_config = ConfigDict(frozen=True)

    property: str
    operator: Literal["eq", "ne", "ilike", "like", "gt", "ge", "lt", "le", "in"]
    value: Any


class NativeOrder(BaseModel):
    """A single sort key pushed to the source."""

    model_config = ConfigDict(frozen=True)

    property: str
    descending: bool = False


class NativeQuery(BaseModel):
    """The pushed-down portion of a pipeline against a named resource."""

    model_config = ConfigDict(frozen=True)

    resource: str
    filters: list[NativeFilter] = Field(default_factory=list)
    root_junction: Literal["AND", "OR"] = "AND"
    order: list[NativeOrder] = Field(default_factory=list)
    limit: int | None = None
    skip: int | None = None


class QueryPlan(BaseModel):
    """A pushed-down `NativeQuery` plus the stages the engine still runs locally."""

    model_config = ConfigDict(frozen=True)

    native: NativeQuery
    residual: list[Annotated[Stage, Field(discriminator="kind")]] = Field(default_factory=list)
