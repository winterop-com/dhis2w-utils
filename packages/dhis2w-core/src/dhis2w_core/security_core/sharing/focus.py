"""The default sharing scan's type scope: a curated, schema-validated set of exposure-prone types.

There is no reliable server-side filter for non-default sharing (the `sharing.public` filter is
silently ignored when the instance's default sharing is itself public, and the legacy
`publicAccess` / `externalAccess` fields are not filterable at all — see BUGS.md), so the scan pages
objects and decodes their sharing client-side. To keep the default audit bounded and high-signal, it
targets the data-bearing types plus the classically exposure-prone metadata (dashboards, documents,
maps, visualizations, SQL views, reports), rather than every shareable type. `data_bearing` is never
guessed: it comes from the live `/api/schemas` `dataShareable` flag. The full inventory across every
shareable type is the interactive explorer's opt-in mode (PR 7b), not the default findings scan.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class SharingFocusType(BaseModel):
    """A type the default sharing scan targets: its schema name and the REST collection plural."""

    model_config = ConfigDict(frozen=True)

    name: str
    plural: str


class SchemaShareability(BaseModel):
    """One `/api/schemas` record reduced to the sharing-relevant flags."""

    model_config = ConfigDict(frozen=True)

    name: str
    plural: str
    shareable: bool = False
    data_shareable: bool = False


class ResolvedFocusType(BaseModel):
    """A focus type confirmed shareable on the live server, with its plural and data-bearing flag."""

    model_config = ConfigDict(frozen=True)

    name: str
    plural: str
    data_bearing: bool = False


# The curated default scan scope. Plurals are stable across v41/v42/v43; `data_bearing` is resolved
# from the live schema, never from this table. Every plural here is in the security GET allowlist.
SHARING_FOCUS_TYPES: tuple[SharingFocusType, ...] = (
    SharingFocusType(name="dataSet", plural="dataSets"),
    SharingFocusType(name="program", plural="programs"),
    SharingFocusType(name="programStage", plural="programStages"),
    SharingFocusType(name="trackedEntityType", plural="trackedEntityTypes"),
    SharingFocusType(name="categoryOption", plural="categoryOptions"),
    SharingFocusType(name="relationshipType", plural="relationshipTypes"),
    SharingFocusType(name="sqlView", plural="sqlViews"),
    SharingFocusType(name="aggregateDataExchange", plural="aggregateDataExchanges"),
    SharingFocusType(name="dashboard", plural="dashboards"),
    SharingFocusType(name="document", plural="documents"),
    SharingFocusType(name="map", plural="maps"),
    SharingFocusType(name="visualization", plural="visualizations"),
    SharingFocusType(name="eventReport", plural="eventReports"),
    SharingFocusType(name="eventVisualization", plural="eventVisualizations"),
    SharingFocusType(name="report", plural="reports"),
)


def resolve_focus_types(schemas: list[SchemaShareability]) -> list[ResolvedFocusType]:
    """Intersect the curated focus set with the live schema flags, keeping only shareable types.

    A focus type the server does not report as shareable is dropped; `data_bearing` is taken from the
    live `dataShareable` flag so the data axis is only ever flagged on types the server agrees bear data.
    """
    shareable_by_name = {schema.name: schema for schema in schemas if schema.shareable}
    resolved: list[ResolvedFocusType] = []
    for focus in SHARING_FOCUS_TYPES:
        schema = shareable_by_name.get(focus.name)
        if schema is None:
            continue
        resolved.append(ResolvedFocusType(name=focus.name, plural=focus.plural, data_bearing=schema.data_shareable))
    return resolved
