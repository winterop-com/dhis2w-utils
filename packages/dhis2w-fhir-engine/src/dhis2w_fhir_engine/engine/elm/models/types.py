"""ELM type specifier models."""

# The specifiers form one pydantic tagged union keyed on the `type` discriminator: the base
# `ELMTypeSpecifier` declares `type: str` and each member narrows it to its own `Literal`. Narrowing a
# mutable attribute is an incompatible override in the general case, so suppress that one rule for the
# whole module rather than on each of the members. Every other rule stays in force.
# pyright: reportIncompatibleVariableOverride=false

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class ELMTypeSpecifier(BaseModel):
    """Base type specifier."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    type: str


class ELMNamedTypeSpecifier(ELMTypeSpecifier):
    """Named type specifier (e.g., FHIR.Patient, System.Integer)."""

    type: Literal["NamedTypeSpecifier"] = "NamedTypeSpecifier"
    namespace: str | None = None
    name: str


class ELMListTypeSpecifier(ELMTypeSpecifier):
    """List type specifier."""

    type: Literal["ListTypeSpecifier"] = "ListTypeSpecifier"
    elementType: ELMTypeSpecifier | None = None


class ELMIntervalTypeSpecifier(ELMTypeSpecifier):
    """Interval type specifier."""

    type: Literal["IntervalTypeSpecifier"] = "IntervalTypeSpecifier"
    pointType: ELMTypeSpecifier | None = None


class ELMTupleElementDefinition(BaseModel):
    """Tuple element definition."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    name: str
    elementType: ELMTypeSpecifier | None = None
    type: ELMTypeSpecifier | None = None  # Alias for elementType in some ELM versions


class ELMTupleTypeSpecifier(ELMTypeSpecifier):
    """Tuple type specifier."""

    type: Literal["TupleTypeSpecifier"] = "TupleTypeSpecifier"
    element: list[ELMTupleElementDefinition] = Field(default_factory=list)


class ELMChoiceTypeSpecifier(ELMTypeSpecifier):
    """Choice type specifier (union of types)."""

    type: Literal["ChoiceTypeSpecifier"] = "ChoiceTypeSpecifier"
    choice: list[ELMTypeSpecifier] = Field(default_factory=list)


# Type alias for any type specifier
AnyTypeSpecifier = Annotated[
    ELMNamedTypeSpecifier
    | ELMListTypeSpecifier
    | ELMIntervalTypeSpecifier
    | ELMTupleTypeSpecifier
    | ELMChoiceTypeSpecifier
    | ELMTypeSpecifier,
    Field(discriminator="type"),
]
