# Maps

`MapsAccessor` on `Dhis2Client.maps` covers the authoring surface over `/api/maps`: `list_all`, `get`, `create_from_spec`, `clone`, `delete`. `MapSpec` is a typed builder that captures the viewport (longitude / latitude / zoom / basemap) plus an ordered list of `MapLayerSpec` layers and produces a full `Map` that DHIS2's metadata importer accepts. `MapLayerSpec` covers the most common layer type — thematic choropleth — with sensible defaults; drop to the generated `Map` / `MapView` models for the full knob set (event layers, earth-engine, custom rendering strategies).

## Layer types

A DHIS2 Map holds one or more `MapView` layers rendered bottom-up:

- **Thematic** (`layer="thematic"`) — the workhorse. Choropleth (`thematicMapType="CHOROPLETH"`) colours each org unit by a data value; graduated symbols (`"BUBBLE"`) scale point size instead. Needs geo-referenced org units (polygons for choropleth, points for bubbles).
- **Boundary** (`layer="boundary"`) — outline-only base layer; typically sits below a thematic.
- **Facility** (`layer="facility"`) — point markers for facility-level org units.
- **Earth engine / event / org unit** — rarer types supported via raw `MapView` construction.

## Georeferenced org units are required

Thematic + boundary layers rely on `OrganisationUnit.geometry` being a GeoJSON-compatible polygon / multipolygon / point. Without it the Maps app falls back to a default viewport and you see a choropleth floating over a blank / wrong-continent basemap. The seed's Sierra Leonean districts carry rough bounding polygons so the demos render in the right place.

## `MapSpec` + `MapLayerSpec` — builders over the generated models

`Map` and `MapView` are the **generated models** — pydantic emitted from DHIS2's OpenAPI schema with every viewport, basemap, rendering-strategy, and axis-placement knob the Maps app exposes, plus DHIS2 bookkeeping. Authoring a choropleth by populating those fields directly for each map is tedious + error-prone.

`MapSpec` + `MapLayerSpec` are the **authoring shapes** — frozen pydantic models whose fields cover the common-case knobs: viewport (`longitude`, `latitude`, `zoom`, `basemap`), ordered layers, and per-layer `(data_elements / indicators, periods, organisation_units, legend_set, thematic_map_type, classes, color_low, color_high, opacity)`. `MapsAccessor.create_from_spec` materialises the spec into a full typed `Map` with every derived `MapView` row populated.

The spec exists because the wire shape branches on `MapLayerSpec.layer_kind`: thematic layers need `dataDimensionItems[]` plus `rowDimensions` / `columnDimensions` / `filterDimensions` populated, while boundary and facility layers leave those fields empty and DHIS2 rejects payloads that mix the two. `MapLayerSpec.to_map_view()` encodes that branch once; the kwargs alternative would replay it at every call site. Same pattern as `VisualizationSpec` / `LegendSetSpec` / `LegendSpec` / `OptionSpec` — see the [Legend sets doc](legend-sets.md#legendsetspec-legendspec-the-builder-pattern) for the full spec-vs-generated-model cross-reference table and the rule for when reaching for a spec is the right call.

## Why `create_from_spec` always goes through `/api/metadata`

Same reason as `Visualization`: a direct `PUT /api/maps/{uid}` with nested `mapViews` silently drops the derived `rows` / `columns` / `filters` collections DHIS2 renders from. The accessor routes through `POST /api/metadata?importStrategy=CREATE_AND_UPDATE` so the importer expands every dimension selector — don't bypass it.

## Related

- [Visualizations + dashboards](visualizations.md) — maps share the same dimension model (`dx`, `pe`, `ou`) as visualizations; same analytics query drives both.
- [Analytics](analytics.md) — sanity-check the data path with `client.get_raw("/api/analytics", params={...})` before saving a map.
- CLI surface: `d2w metadata list maps / get / create / clone / delete` + `d2w browser map screenshot <uid>`.

::: dhis2w_client.v42.maps
