"""FHIR Terminology models.

This module defines Pydantic models for FHIR terminology operations
including codes, value sets, and validation requests/responses.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Coding(BaseModel):
    """FHIR Coding type.

    Represents a code from a code system.
    """

    model_config = ConfigDict(extra="allow")

    system: str | None = None
    version: str | None = None
    code: str | None = None
    display: str | None = None
    userSelected: bool | None = None


class CodeableConcept(BaseModel):
    """FHIR CodeableConcept type.

    Represents a concept with multiple possible codings.
    """

    model_config = ConfigDict(extra="allow")

    coding: list[Coding] = Field(default_factory=list)
    text: str | None = None


class ValueSetComposeIncludeConcept(BaseModel):
    """A concept to include in a value set."""

    code: str
    display: str | None = None


class ValueSetComposeInclude(BaseModel):
    """Include criteria for value set composition."""

    system: str | None = None
    version: str | None = None
    concept: list[ValueSetComposeIncludeConcept] = Field(default_factory=list)
    filter: list[dict[str, Any]] = Field(default_factory=list)
    valueSet: list[str] = Field(default_factory=list)


class ValueSetCompose(BaseModel):
    """Value set composition definition."""

    include: list[ValueSetComposeInclude] = Field(default_factory=list)
    exclude: list[ValueSetComposeInclude] = Field(default_factory=list)


class ValueSetExpansionContains(BaseModel):
    """A code in the value set expansion."""

    system: str | None = None
    version: str | None = None
    code: str | None = None
    display: str | None = None


class ValueSetExpansion(BaseModel):
    """Expanded codes for a value set."""

    identifier: str | None = None
    timestamp: str | None = None
    total: int | None = None
    contains: list[ValueSetExpansionContains] = Field(default_factory=list)


class ValueSet(BaseModel):
    """FHIR ValueSet resource.

    Represents a set of codes from one or more code systems.
    """

    model_config = ConfigDict(extra="allow")

    resourceType: str = "ValueSet"
    id: str | None = None
    url: str | None = None
    version: str | None = None
    name: str | None = None
    title: str | None = None
    status: str = "active"
    compose: ValueSetCompose | None = None
    expansion: ValueSetExpansion | None = None


class CodeSystem(BaseModel):
    """FHIR CodeSystem resource (simplified)."""

    model_config = ConfigDict(extra="allow")

    resourceType: str = "CodeSystem"
    id: str | None = None
    url: str | None = None
    version: str | None = None
    name: str | None = None
    status: str = "active"
    concept: list[dict[str, Any]] = Field(default_factory=list)


class ValidateCodeRequest(BaseModel):
    """Request for $validate-code operation."""

    url: str | None = None  # ValueSet URL
    valueSet: ValueSet | None = None  # Inline ValueSet
    code: str | None = None
    system: str | None = None
    version: str | None = None
    display: str | None = None
    coding: Coding | None = None
    codeableConcept: CodeableConcept | None = None


class ValidateCodeResponse(BaseModel):
    """Response from $validate-code operation."""

    result: bool
    message: str | None = None
    display: str | None = None


class SubsumesRequest(BaseModel):
    """Request for $subsumes operation."""

    codeA: str
    codeB: str
    system: str
    version: str | None = None


class SubsumesResponse(BaseModel):
    """Response from $subsumes operation.

    Outcome can be:
    - equivalent: A and B are equivalent
    - subsumes: A subsumes B
    - subsumed-by: A is subsumed by B
    - not-subsumed: A and B are not related
    """

    outcome: str  # equivalent | subsumes | subsumed-by | not-subsumed


class MemberOfRequest(BaseModel):
    """Request for memberOf check."""

    code: str
    system: str
    valueSetUrl: str
    version: str | None = None


class MemberOfResponse(BaseModel):
    """Response from memberOf check."""

    result: bool
    valueSetUrl: str
    code: str
    system: str
