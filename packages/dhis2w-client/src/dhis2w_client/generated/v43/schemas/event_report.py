"""Generated EventReport model for DHIS2 v43. Do not edit by hand."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ..common import Reference
from ..enums import (
    AggregationType,
    DigitGroupSeparator,
    DisplayDensity,
    EnrollmentStatus,
    EventDataType,
    EventOutputType,
    EventStatus,
    EventVisualizationType,
    FontSize,
    HideEmptyItemStrategy,
    RegressionType,
    UserOrgUnitType,
)
from .category_dimension import CategoryDimension
from .category_option_group_set_dimension import CategoryOptionGroupSetDimension
from .data_element_group_set_dimension import DataElementGroupSetDimension
from .organisation_unit_group_set_dimension import OrganisationUnitGroupSetDimension
from .tracked_entity_data_element_dimension import TrackedEntityDataElementDimension
from .tracked_entity_program_indicator_dimension import TrackedEntityProgramIndicatorDimension


class EventReport(BaseModel):
    """Generated model for DHIS2 `EventReport`.

    DHIS2 Event Report - persisted metadata (generated from /api/schemas at DHIS2 v43).

    API endpoint: /api/eventReports.

    Field `Field(description=...)` entries flag DHIS2 semantics the bare
    type can't capture: which side of a relationship owns the link
    (writable) vs the inverse side (ignored by the API), uniqueness
    constraints, and length bounds.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    access: Any | None = Field(default=None, description="Reference to Access. Read-only (inverse side).")
    aggregationType: AggregationType | None = None
    attributeDimensions: list[Any] | None = Field(
        default=None, description="Collection of TrackedEntityAttributeDimension."
    )
    attributeValueDimension: Reference | None = Field(default=None, description="Reference to TrackedEntityAttribute.")
    attributeValues: Any | None = Field(default=None, description="Reference to AttributeValues. Length/value max=255.")
    categoryDimensions: list[CategoryDimension] | None = Field(
        default=None, description="Collection of CategoryDimension."
    )
    categoryOptionGroupSetDimensions: list[CategoryOptionGroupSetDimension] | None = Field(
        default=None, description="Collection of CategoryOptionGroupSetDimension."
    )
    code: str | None = Field(default=None, description="Unique. Length/value max=50.")
    colSubTotals: bool | None = None
    colTotals: bool | None = None
    collapseDataDimensions: bool | None = None
    columnDimensions: list[Any] | None = Field(default=None, description="Collection of String.")
    columns: list[Any] | None = Field(
        default=None, description="Collection of DimensionalObject. Read-only (inverse side)."
    )
    completedOnly: bool | None = None
    created: datetime | None = None
    createdBy: Reference | None = Field(default=None, description="Reference to User.")
    cumulativeValues: bool | None = None
    dataDimensionItems: list[Any] | None = Field(
        default=None, description="Collection of DataDimensionItem. Read-only (inverse side)."
    )
    dataElementDimensions: list[TrackedEntityDataElementDimension] | None = Field(
        default=None, description="Collection of TrackedEntityDataElementDimension."
    )
    dataElementGroupSetDimensions: list[DataElementGroupSetDimension] | None = Field(
        default=None, description="Collection of DataElementGroupSetDimension. Read-only (inverse side)."
    )
    dataElementValueDimension: Reference | None = Field(default=None, description="Reference to DataElement.")
    dataType: EventDataType | None = None
    description: str | None = Field(default=None, description="Length/value min=1, max=2147483647.")
    digitGroupSeparator: DigitGroupSeparator | None = None
    displayBaseLineLabel: str | None = Field(default=None, description="Read-only.")
    displayDensity: DisplayDensity | None = None
    displayDescription: str | None = Field(default=None, description="Read-only.")
    displayFormName: str | None = Field(default=None, description="Read-only.")
    displayName: str | None = Field(default=None, description="Read-only.")
    displayShortName: str | None = Field(default=None, description="Read-only.")
    displaySubtitle: str | None = Field(default=None, description="Read-only.")
    displayTargetLineLabel: str | None = Field(default=None, description="Read-only.")
    displayTitle: str | None = Field(default=None, description="Read-only.")
    endDate: datetime | None = None
    eventStatus: EventStatus | None = None
    favorite: bool | None = Field(default=None, description="Read-only.")
    favorites: list[Any] | None = Field(default=None, description="Collection of String. Length/value max=255.")
    filterDimensions: list[Any] | None = Field(default=None, description="Collection of String.")
    filters: list[Any] | None = Field(
        default=None, description="Collection of DimensionalObject. Read-only (inverse side)."
    )
    fixColumnHeaders: bool | None = None
    fixRowHeaders: bool | None = None
    fontSize: FontSize | None = None
    formName: str | None = Field(default=None, description="Length/value max=2147483647.")
    hideEmptyColumns: bool | None = None
    hideEmptyRowItems: HideEmptyItemStrategy | None = None
    hideEmptyRows: bool | None = None
    hideLegend: bool | None = None
    hideNaData: bool | None = None
    hideSubtitle: bool | None = None
    hideTitle: bool | None = None
    href: str | None = None
    id: str | None = Field(default=None, description="Unique. Length/value min=11, max=11.")
    interpretations: list[Any] | None = Field(
        default=None, description="Collection of Interpretation. Read-only (inverse side)."
    )
    itemOrganisationUnitGroups: list[Any] | None = Field(
        default=None, description="Collection of OrganisationUnitGroup."
    )
    lastUpdated: datetime | None = None
    lastUpdatedBy: Reference | None = Field(default=None, description="Reference to User.")
    legacy: bool | None = None
    legend: Any | None = Field(default=None, description="Reference to LegendDefinitions. Read-only (inverse side).")
    metaData: Any | None = Field(default=None, description="Reference to Map. Read-only (inverse side).")
    name: str | None = Field(default=None, description="Length/value min=1, max=230.")
    noSpaceBetweenColumns: bool | None = None
    orgUnitField: str | None = Field(default=None, description="Length/value max=255.")
    organisationUnitGroupSetDimensions: list[OrganisationUnitGroupSetDimension] | None = Field(
        default=None, description="Collection of OrganisationUnitGroupSetDimension."
    )
    organisationUnitLevels: list[Any] | None = Field(default=None, description="Collection of Integer.")
    organisationUnits: list[Any] | None = Field(default=None, description="Collection of OrganisationUnit.")
    outputType: EventOutputType | None = None
    parentGraphMap: Any | None = Field(default=None, description="Reference to Map. Read-only (inverse side).")
    percentStackedValues: bool | None = None
    periods: list[Any] | None = Field(default=None, description="Collection of Period.")
    program: Reference | None = Field(default=None, description="Reference to Program.")
    programIndicatorDimensions: list[TrackedEntityProgramIndicatorDimension] | None = Field(
        default=None, description="Collection of TrackedEntityProgramIndicatorDimension."
    )
    programStage: Reference | None = Field(default=None, description="Reference to ProgramStage.")
    programStatus: EnrollmentStatus | None = None
    rawPeriods: list[Any] | None = Field(default=None, description="Collection of String. Length/value max=3650.")
    regressionType: RegressionType | None = None
    relativePeriods: Any | None = Field(
        default=None, description="Reference to RelativePeriods. Read-only (inverse side)."
    )
    rowDimensions: list[Any] | None = Field(default=None, description="Collection of String.")
    rowSubTotals: bool | None = None
    rowTotals: bool | None = None
    rows: list[Any] | None = Field(
        default=None, description="Collection of DimensionalObject. Read-only (inverse side)."
    )
    sharing: Any | None = Field(default=None, description="Reference to Sharing. Length/value max=255.")
    shortName: str | None = Field(default=None, description="Length/value min=1, max=50.")
    showData: bool | None = None
    showDimensionLabels: bool | None = None
    showHierarchy: bool | None = None
    simpleDimensions: list[Any] | None = Field(
        default=None, description="Collection of SimpleDimension. Length/value max=255."
    )
    skipRounding: bool | None = None
    sortOrder: int | None = Field(default=None, description="Length/value max=2147483647.")
    startDate: datetime | None = None
    subscribed: bool | None = Field(default=None, description="Read-only.")
    subscribers: list[Any] | None = Field(default=None, description="Collection of String. Length/value max=255.")
    subtitle: str | None = Field(default=None, description="Length/value max=255.")
    timeField: str | None = Field(default=None, description="Length/value max=255.")
    title: str | None = Field(default=None, description="Length/value max=255.")
    topLimit: int | None = Field(default=None, description="Length/value max=2147483647.")
    translations: list[Any] | None = Field(default=None, description="Collection of Translation. Length/value max=255.")
    type: EventVisualizationType | None = None
    user: Reference | None = Field(default=None, description="Reference to User. Read-only (inverse side).")
    userOrgUnitType: UserOrgUnitType | None = None
    userOrganisationUnit: bool | None = None
    userOrganisationUnitChildren: bool | None = None
    userOrganisationUnitGrandChildren: bool | None = None
    value: Reference | None = Field(
        default=None, description="Reference to DimensionalItemObject. Read-only (inverse side)."
    )
