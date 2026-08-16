"""Generated CategoryOption model for DHIS2 v43. Do not edit by hand."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ..common import Reference
from ..enums import DimensionItemType, TotalAggregationType


class CategoryOption(BaseModel):
    """Generated model for DHIS2 `CategoryOption`.

    DHIS2 Category Option - persisted metadata (generated from /api/schemas at DHIS2 v43).

    API endpoint: /api/categoryOptions.

    Field `Field(description=...)` entries flag DHIS2 semantics the bare
    type can't capture: which side of a relationship owns the link
    (writable) vs the inverse side (ignored by the API), uniqueness
    constraints, and length bounds.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    access: Any | None = Field(default=None, description="Reference to Access. Read-only (inverse side).")
    aggregationType: bool | None = Field(default=None, description="Read-only.")
    attributeValues: Any | None = Field(default=None, description="Reference to AttributeValues. Length/value max=255.")
    categories: list[Any] | None = Field(default=None, description="Collection of Category. Read-only (inverse side).")
    categoryOptionCombos: list[Any] | None = Field(
        default=None, description="Collection of CategoryOptionCombo. Read-only (inverse side)."
    )
    categoryOptionGroups: list[Any] | None = Field(
        default=None, description="Collection of CategoryOptionGroup. Read-only (inverse side)."
    )
    code: str | None = Field(default=None, description="Unique. Length/value max=50.")
    created: datetime | None = None
    createdBy: Reference | None = Field(default=None, description="Reference to User.")
    description: str | None = Field(default=None, description="Length/value max=255.")
    dimensionItem: str | None = Field(default=None, description="Read-only.")
    dimensionItemType: DimensionItemType | None = Field(default=None, description="Read-only.")
    displayDescription: str | None = Field(default=None, description="Read-only.")
    displayFormName: str | None = Field(default=None, description="Read-only.")
    displayName: str | None = Field(default=None, description="Read-only.")
    displayShortName: str | None = Field(default=None, description="Read-only.")
    endDate: datetime | None = None
    formName: str | None = Field(default=None, description="Length/value min=2, max=230.")
    href: str | None = Field(default=None, description="Length/value max=2147483647.")
    id: str | None = Field(default=None, description="Unique. Length/value min=11, max=11.")
    isDefault: bool | None = Field(default=None, description="Read-only.")
    lastUpdated: datetime | None = None
    lastUpdatedBy: Reference | None = Field(default=None, description="Reference to User.")
    name: str | None = Field(default=None, description="Unique. Length/value min=1, max=230.")
    organisationUnits: list[Any] | None = Field(default=None, description="Collection of OrganisationUnit.")
    queryMods: Any | None = Field(default=None, description="Reference to QueryModifiers. Read-only (inverse side).")
    sharing: Any | None = Field(default=None, description="Reference to Sharing. Length/value max=255.")
    shortName: str | None = Field(default=None, description="Unique. Length/value max=50.")
    startDate: datetime | None = None
    style: Any | None = Field(default=None, description="Reference to ObjectStyle. Length/value max=255.")
    totalAggregationType: TotalAggregationType | None = Field(default=None, description="Read-only.")
    translations: list[Any] | None = Field(default=None, description="Collection of Translation.")
    user: Reference | None = Field(default=None, description="Reference to User. Read-only (inverse side).")
