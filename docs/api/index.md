# `dhis2w-client` API reference

> **Learning path · step 6 of 8** — Reference + edge cases. Prev: [Examples index](../examples.md). Next: [Architecture overview](../architecture/overview.md). For prose explanations with worked examples, the [`dhis2w-client` step-by-step guide](../guides/client-tutorial.md) is the better starting point — this page is the auto-rendered surface for symbol-by-symbol lookups.

Auto-generated from the `dhis2w-client` source via `mkdocstrings`. Every class, method, and function listed here is importable from `dhis2w_client` (top-level re-exports) or from its module.

## Layout

- [Client + lifecycle](client.md) — `Dhis2Client`, connect, close, raw escape hatches
- [Profile + lightweight open_client](profile.md) — `Profile`, `open_client`, `build_auth_for_basic`, `profile_from_env_raw`, exceptions — PAT/Basic library path with no `dhis2w-core` install
- [Auth providers](auth.md) — `BasicAuth`, `PatAuth`, `OAuth2Auth`, `SessionCookieAuth`, the `AuthProvider` Protocol, `OAuth2Token`, `TokenStore`
- [Errors](errors.md) — the exception hierarchy
- [Envelopes + responses](envelopes.md) — `WebMessageResponse`, `Conflict`, `ImportCount`, `ObjectReport`, `ImportReport`
- [Route auth schemes](auth-schemes.md) — the 5-variant discriminated `AuthScheme` union
- [Sharing](sharing.md) — typed `SharingObject` + `SharingBuilder` + `get_sharing` / `apply_sharing` helpers over `/api/sharing`
- [Generated-model helpers](generated.md) — `Dhis2` enum, `available_versions`, `load`
- [OpenAPI-derived models](oas.md) — the 562+ classes emitted under `generated/v42/oas/` from `/api/openapi.json`
- [System module](system.md) — `Me`, `SystemInfo`, `SystemModule`
- [Tracker reads](tracker.md) — instance models, status enums
- [Aggregate](aggregate.md) — `DataValue`, `DataValueSet`
- [Data values (streaming)](data-values.md) — `DataValuesAccessor` on `Dhis2Client.data_values` (streaming `/api/dataValueSets` imports)
- [Analytics](analytics.md) — `Grid`, `GridHeader` (OAS-emitted) + `AnalyticsMetaData` (typed parser helper over `Grid.metaData`)
- [Analytics streaming](analytics-stream.md) — `AnalyticsAccessor` on `Dhis2Client.analytics` (chunked `/api/analytics*` downloads)
- [Maintenance](maintenance.md) — `Notification`, `DataIntegrityCheck`, `DataIntegrityResult`, `DataIntegrityReport`
- [Metadata accessor](metadata-accessor.md) — `MetadataAccessor` on `Dhis2Client.metadata` (bulk delete + multi-resource operations)
- [Customize](customize.md) — `CustomizeAccessor`, `LoginCustomization`, `CustomizationResult`
- [Files](files.md) — `FilesAccessor`, `Document`, `FileResource`, `FileResourceDomain` — documents + file-resource uploads/downloads
- [Messaging](messaging.md) — `MessagingAccessor` on `Dhis2Client.messaging` (/api/messageConversations)
- [Apps](apps.md) — `AppsAccessor` on `Dhis2Client.apps` — install / uninstall / update over `/api/apps` + `/api/appHub`
- [Validation + predictors](validation.md) — `ValidationAccessor` + `PredictorsAccessor` for the run-rules + run-predictors workflow
- [Visualizations + dashboards](visualizations.md) — `VisualizationsAccessor` + `VisualizationSpec` + `DashboardsAccessor` + `DashboardSlot` for authoring saved analytics + composing dashboards
- [Maps](maps.md) — `MapsAccessor` + `MapSpec` + `MapLayerSpec` for thematic choropleths + map composition
- [Legend sets](legend-sets.md) — `LegendSetsAccessor` + `LegendSetSpec` + `LegendSpec` — colour-range authoring attached to visualizations and maps
- [Organisation units](organisation-units.md) — `OrganisationUnitsAccessor` + `OrganisationUnitGroupsAccessor` + `OrganisationUnitGroupSetsAccessor` + `OrganisationUnitLevelsAccessor` — tree-aware reads, per-level naming, group + group-set membership
- [Data elements](data-elements.md) — `DataElementsAccessor` + `DataElementGroupsAccessor` + `DataElementGroupSetsAccessor` — aggregate + tracker DE authoring, thematic groups, analytics dimensions
- [Indicators](indicators.md) — `IndicatorsAccessor` + `IndicatorGroupsAccessor` + `IndicatorGroupSetsAccessor` — computed-ratio authoring with expression validation, per-item membership shortcuts
- [Program indicators](program-indicators.md) — `ProgramIndicatorsAccessor` + `ProgramIndicatorGroupsAccessor` — tracker-analytics authoring (pair only; DHIS2 doesn't expose a ProgramIndicatorGroupSet)
- [Categories](categories.md) — `CategoriesAccessor` + `Category` — second tier of disaggregation: named axis groupings of CategoryOptions
- [Category combos](category-combos.md) — `CategoryCombosAccessor` + `CategoryCombo` — cross-product disaggregation attached to DataElements; v43 manual-COC-regen helper
- [Category combo builder](category-combo-builder.md) — `build_category_combo` + `CategoryComboBuildSpec` — declarative one-call Categories → CategoryCombo → COCs build
- [Category option combos](category-option-combos.md) — read-only `CategoryOptionCombosAccessor` — enumerate the materialised disaggregation cells of a CategoryCombo
- [Category options](category-options.md) — `CategoryOptionsAccessor` + `CategoryOptionGroupsAccessor` + `CategoryOptionGroupSetsAccessor` — disaggregation values + validity windows + analytics dimensions
- [Attribute values](attribute-values.md) — `AttributeValuesAccessor` — read + write the typed `attributeValues` field on any metadata resource
- [Option sets](option-sets.md) — `OptionSetsAccessor` + `OptionSpec` + `UpsertReport` — controlled-vocabulary option lists with declarative sync
- [Program rules](program-rules.md) — `ProgramRulesAccessor` — program-rule reads, variable resolution, expression validation, reverse-reference lookup
- [JSON Patch ops](json-patch.md) — `JsonPatchOp` + `JsonPatchOpAdapter` — typed RFC 6902 ops for `PATCH /api/{resource}/{uid}`
- [Tasks module](tasks.md) — `TaskModule` + `TaskCompletion` — poll DHIS2 background jobs (analytics, imports, predictors) to completion
- [SQL views](sql-views.md) — `SqlViewsAccessor` + `SqlViewRunner` for DHIS2 `SqlView` execution workflows
- [Periods](periods.md) — `PeriodType` StrEnum
- [UIDs](uids.md) — client-side UID generator + validator
