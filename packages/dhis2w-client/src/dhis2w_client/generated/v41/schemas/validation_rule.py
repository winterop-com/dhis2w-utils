"""Generated ValidationRule model for DHIS2 v41. Do not edit by hand."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ..common import Reference
from ..enums import AggregationType, DimensionItemType, Importance, Operator, PeriodType
from .attribute_value import AttributeValue


class ValidationRule(BaseModel):
    """Generated model for DHIS2 `ValidationRule`.

    DHIS2 Validation Rule - persisted metadata (generated from /api/schemas at DHIS2 v41).

    API endpoint: /api/validationRules.

    Field `Field(description=...)` entries flag DHIS2 semantics the bare
    type can't capture: which side of a relationship owns the link
    (writable) vs the inverse side (ignored by the API), uniqueness
    constraints, and length bounds.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    access: Any | None = Field(default=None, description="Reference to Access. Read-only (inverse side).")
    aggregateExportAttributeOptionCombo: str | None = Field(default=None, description="Length/value max=2147483647.")
    aggregateExportCategoryOptionCombo: str | None = Field(default=None, description="Length/value max=2147483647.")
    aggregationType: AggregationType | None = None
    attributeValues: list[AttributeValue] | None = Field(
        default=None, description="Collection of AttributeValue. Length/value max=255."
    )
    code: str | None = Field(default=None, description="Unique. Length/value max=50.")
    created: datetime | None = None
    createdBy: Reference | None = Field(default=None, description="Reference to User.")
    description: str | None = Field(default=None, description="Length/value min=2, max=2147483647.")
    dimensionItem: str | None = Field(default=None, description="Read-only.")
    dimensionItemType: DimensionItemType | None = None
    displayDescription: str | None = Field(default=None, description="Read-only.")
    displayFormName: str | None = Field(default=None, description="Read-only.")
    displayInstruction: str | None = Field(default=None, description="Read-only.")
    displayName: str | None = Field(default=None, description="Read-only.")
    displayShortName: str | None = Field(default=None, description="Read-only.")
    favorite: bool | None = Field(default=None, description="Read-only.")
    favorites: list[Any] | None = Field(default=None, description="Collection of String. Read-only (inverse side).")
    formName: str | None = Field(default=None, description="Length/value max=2147483647.")
    href: str | None = None
    id: str | None = Field(default=None, description="Unique. Length/value min=11, max=11.")
    importance: Importance | None = None
    instruction: str | None = Field(default=None, description="Length/value max=2147483647.")
    lastUpdated: datetime | None = None
    lastUpdatedBy: Reference | None = Field(default=None, description="Reference to User.")
    leftSide: Any | None = Field(default=None, description="Reference to Expression. Unique. Length/value max=255.")
    legendSet: Reference | None = Field(default=None, description="Reference to LegendSet. Read-only (inverse side).")
    legendSets: list[Any] | None = Field(default=None, description="Collection of LegendSet. Read-only (inverse side).")
    name: str | None = Field(default=None, description="Unique. Length/value min=1, max=230.")
    notificationTemplates: list[Any] | None = Field(
        default=None, description="Collection of ValidationNotificationTemplate. Read-only (inverse side)."
    )
    operator: Operator | None = None
    organisationUnitLevels: list[Any] | None = Field(default=None, description="Collection of Integer.")
    periodType: PeriodType | None = Field(default=None, description="Reference to PeriodType. Length/value max=255.")
    queryMods: Any | None = Field(default=None, description="Reference to QueryModifiers. Read-only (inverse side).")
    rightSide: Any | None = Field(default=None, description="Reference to Expression. Unique. Length/value max=255.")
    sharing: Any | None = Field(default=None, description="Reference to Sharing. Length/value max=255.")
    shortName: str | None = Field(default=None, description="Unique. Length/value min=1, max=50.")
    skipFormValidation: bool | None = None
    translations: list[Any] | None = Field(default=None, description="Collection of Translation. Length/value max=255.")
    user: Reference | None = Field(default=None, description="Reference to User. Read-only (inverse side).")
    validationRuleGroups: list[Any] | None = Field(
        default=None, description="Collection of ValidationRuleGroup. Read-only (inverse side)."
    )
