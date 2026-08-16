# Schema diff: v41 -> v42 -> v43

Reference of every schema change across the three supported DHIS2 majors (v41 = `2.41.8.1`, v42 = `2.42.4.1`, v43 = `2.43.0.0`) as seen by `dhis2w-client`'s codegen. Two sources of truth:

- **`/api/schemas`** drives `dhis2w_client.generated.v{N}.schemas` (and the `client.resources.X` accessors). Run `d2w dev codegen diff v41 v42` or `d2w dev codegen diff v42 v43` to regenerate the schema-side diff.
- **`/api/openapi.json`** drives `dhis2w_client.generated.v{N}.oas` (the request/response shapes used by tracker, auth schemes, data-value imports, etc.). Diff is a plain `ls` comparison of the per-version `oas/` trees — there is no dedicated CLI command for it yet.

If you only care about the workable patterns ("how do I read this v43 field"), jump to [Working with version-specific types](versioning.md#working-with-version-specific-types) in the versioning page. This page is the lookup index.

## Snapshot

### v41 -> v42

| Source | Added | Removed | Changed |
| --- | ---: | ---: | ---: |
| `/api/schemas` (resource models) | 3 | 9 | 86 |

v42 is a meaningful jump: the OAuth2 metadata stack (oauth2Authorization, oauth2AuthorizationConsent, oauth2Client) lands as first-class resources, several deprecated v41 resources are dropped, and many surfaces gain `displayDescription` / `displayShortName` fields. The v41 -> v42 detail section covers each of those.

### v42 -> v43

| Source | Added | Removed | Changed |
| --- | ---: | ---: | ---: |
| `/api/schemas` (resource models) | 0 | 3 | 40 |
| `/api/openapi.json` (OAS payload models) | 20 | 23 | n/a |

Smaller surface change than v41 -> v42 but with concrete breaking-shape items (DashboardItem.user -> users, TrackedEntityAttribute.favorite -> favorites, Section.user removed, Program.favorite removed). The OAS side reorganises around `DataValueChangelog*` and the `TrackerSingleEvent` / `TrackerTrackerEvent` split. Detail in the v42 -> v43 section below.

## v41 -> v42

### Added schemas

Three new top-level resources land in v42, all from the OAuth2 server-side metadata stack:

| Schema | Class | Role |
| --- | --- | --- |
| `oauth2Authorization` | `org.hisp.dhis.security.oauth2.authorization.Dhis2OAuth2Authorization` | Persisted OAuth2 authorization grants — the server-side store backing `/oauth2/authorize`. |
| `oauth2AuthorizationConsent` | `org.hisp.dhis.security.oauth2.consent.Dhis2OAuth2AuthorizationConsent` | Per-user-per-client consent records. |
| `oauth2Client` | `org.hisp.dhis.security.oauth2.client.Dhis2OAuth2Client` | Registered OAuth2 client metadata (replaces the older `oAuth2Client` resource). |

### Removed schemas

| Schema | Notes |
| --- | --- |
| `oAuth2Client` | Superseded by `oauth2Client` (above). The new resource has the same surface but normalises naming. |
| `programInstance` | Tracker enrollment; folded into the tracker API. Use `/api/tracker/enrollments` for v42+. |
| `programStageInstance` | Tracker event; same story — use `/api/tracker/events`. |
| `programStageInstanceFilter` | Replaced by `eventFilter`. |
| `eventChart` (the metadata-resource form) | Still queryable via the analytics endpoints; the metadata resource was redundant. |
| `legendDefinitions` | Folded into the per-resource `legendSet` field. |
| `s_m_s_command` | SMS command admin moved out of the metadata resource list. |
| `tracked_entity_instance` | Tracker tracked-entity; v42 routes through `/api/tracker/trackedEntities`. |
| `tracked_entity_instance_filter` | Replaced by `trackedEntityFilter`. |

### Notable shape changes (selected)

The full `d2w dev codegen diff v41 v42` output is in the appendix below; the high-signal items:

- **`displayDescription` / `displayShortName` added** to many surfaces: dashboard, indicatorGroup, indicatorGroupSet, optionSet, program, programStage, validationRule. v41-pinned models miss these at typed-access time but they survive on `model_extra`.
- **Tracker resources moved to the `/api/tracker` endpoint**: enrollments, events, trackedEntities, relationships. Code that hit the `/api/programInstance` or `/api/programStageInstance` routes on v41 needs to switch to the tracker routes on v42+.
- **`legendSet` / `legendSets` field added** to many resources (dataElement, indicator, programIndicator). Replaces the v41 `legendDefinitions` indirection.
- **OAuth2 server-side metadata** — Dhis2OAuth2Authorization, Dhis2OAuth2AuthorizationConsent, Dhis2OAuth2Client — see Added schemas above.

### Working with v41 -> v42 differences

- v41-pinned helpers reading a v42 instance: pure-additions land on `model_extra`; the dropped `programInstance` / `programStageInstance` resources are gone — use `client.tracker.*` accessors instead.
- v42-pinned helpers reading a v41 instance: the OAuth2 resources don't exist — calls return 404. Same fall-back patterns as the v42 -> v43 section apply.

## v42 -> v43

The OAS "removals" are mostly internal `*Params` DTOs that v43 collapsed; the OAS "additions" are mostly new request/response models for data-value change-logs, the tracker event split, and a few date-time primitives. Both are listed in full below.

### Schemas-side: removed resources

These three resources are gone in v43. Anyone calling the matching `client.resources.X` accessor on a v43 instance will get `AttributeError`.

| Schema | Class on the server | Notes |
| --- | --- | --- |
| `dataInputPeriods` | `org.hisp.dhis.dataset.DataInputPeriod` | Folded into `dataSet.dataInputPeriods` inline; no top-level resource. |
| `externalFileResource` | `org.hisp.dhis.fileresource.ExternalFileResource` | Use the `externalAccess` field on `fileResource` directly. |
| `pushanalysis` | `org.hisp.dhis.pushanalysis.PushAnalysis` | Push-analysis is removed in v43. |

### Schemas-side: breaking shape changes

The six places where a v42-typed pydantic model **cannot parse** v43 wire data, or vice versa. If a hand-written helper in `dhis2w-client` is pinned to v42 (most are), these are the schemas where parsing fails on a v43 instance.

| Schema | Field | v42 wire shape | v43 wire shape |
| --- | --- | --- | --- |
| `dashboardItem` | `user` / `users` | `Reference \| None`, fieldName `user` | `list[User]`, fieldName renamed to `users` |
| `dashboardItem` | `code` / `id` | `IDENTIFIER` (max 50, unique) | `TEXT` (max 255, not unique); `id` becomes required |
| `trackedEntityAttribute` | `favorite` / `favorites` | `bool`, fieldName `favorite` | `list[str]` (set of usernames), fieldName renamed to `favorites` |
| `section` | `user` | `Reference \| None` | removed entirely |
| `program` | `favorite` | `list[str]` | removed entirely |
| `legend` | most fields | full identifiable-object surface | almost everything removed (see "Legend collapse" below) |

### Legend collapse

`legend` lost ~20 fields in v43 — `access`, `attributeValues`, `code`, `color`, `created`, `createdBy`, `displayName`, `endValue`, `favorite`, `href`, `id`, `image`, `lastUpdated`, `lastUpdatedBy`, `name`, `sharing`, `startValue`, `translation`, `user` — and gained `set`, `showKey`, `strategy`, `style`. This is the largest single-schema delta. Treat `legend` as effectively rebuilt across versions.

### Schemas-side: pure additions

New fields only present in v43. v42-pinned models lose them at typed-access time but they round-trip through `model_extra` because every generated model uses `ConfigDict(extra="allow")`.

| Schema | New fields |
| --- | --- |
| `dashboardItem` | `displayText` |
| `dataApprovalLevel` | `translations` (replaces `translation`) |
| `dataApprovalWorkflow` | `translations` (replaces `translation`) |
| `eventChart` | `fixColumnHeaders`, `fixRowHeaders`, `hideEmptyColumns` |
| `eventReport` | `fixColumnHeaders`, `fixRowHeaders`, `hideEmptyColumns` |
| `eventVisualization` | `fixColumnHeaders`, `fixRowHeaders`, `hideEmptyColumns` |
| `indicatorGroupSet` | `displayDescription`, `displayShortName` |
| `legendSet` | `translations` (replaces `translation`) |
| `map` | `basemaps` (collection of `Basemap`, see OAS below) |
| `mapView` | `eventCoordinateFieldFallback` |
| `program` | `displayEnrollmentsLabel`, `displayEventsLabel`, `displayProgramStagesLabel`, `enableChangeLog`, `enrollmentCategoryCombo`, `enrollmentsLabel`, `eventsLabel`, `programStagesLabel` |
| `programRuleAction` | `legendSet`, `priority` |
| `programStage` | `displayEventsLabel`, `eventsLabel` |
| `trackedEntityAttribute` | `blockedSearchOperators`, `minCharactersToSearch`, `preferredSearchOperator`, `skipAnalytics`, `trigramIndexable`, `trigramIndexed` |
| `trackedEntityType` | `displayTrackedEntityTypesLabel`, `enableChangeLog`, `trackedEntityTypesLabel` |
| `userGroup` | `description` |

### Schemas-side: dropped fields (per resource)

Fields removed in v43, beyond the breaking-shape and resource removals above. Most are the `favorite: bool` per-user flag being yanked from a long list of resources — DHIS2 moved the favouriting model server-side. These fields will simply be missing on v43-parsed models; reading them on a v42-pinned model against v43 wire data raises `AttributeError`.

| Schema | Removed fields |
| --- | --- |
| `access` | `externalize` |
| `categoryCombo` | `favorite` |
| `categoryOption` | `aggregationType`, `dimensionItem`, `dimensionItemType`, `favorite`, `legendSet`, `legendSets` |
| `dashboard` | `displayFormName`, `displayShortName`, `formName`, `shortName` |
| `dashboardItem` | `displayName`, `favorite` |
| `dataApprovalLevel` | `favorite`, `translation` |
| `dataApprovalWorkflow` | `favorite`, `translation` |
| `indicatorGroup` | `favorite` |
| `indicatorGroupSet` | `favorite` |
| `legendSet` | `favorite`, `translation` |
| `optionSet` | `favorite` |
| `programTrackedEntityAttribute` | `skipIndividualAnalytics` |
| `section` | `favorite`, `user` |
| `sharing` | `external` |

### Schemas-side: bound shifts (informational)

DHIS2 v43 tightened a lot of `description` bounds (max 2_147_483_647 -> 255), promoted several `id` / `code` fields from `IDENTIFIER` to `TEXT`, and downgraded `href` from `URL` to `TEXT`. None of these affect pydantic parsing — pydantic doesn't enforce DHIS2's `min`/`max`/`propertyType` metadata bounds — but they show up in the full diff if you grep for `propertyType` or `max:`. They are not listed individually here. See the appendix or run the `diff` CLI for the per-field detail.

### OAS-side: additions

New OAS-derived models in `dhis2w_client.generated.v43.oas` that were not in v42. Most are tracker / data-value / dimensional-object DTOs that v43 split out, plus a few date-time primitives.

| Model | Likely role |
| --- | --- |
| `Basemap` | Backing model for `Map.basemaps` |
| `DataValueCategoryParams`, `DataValuePostParams` | Aggregate data-value request DTOs |
| `DataValueChangelogEntry` | Backing model for `/api/dataValues/audit` change-log responses |
| `DimensionalItemObjectParams`, `DimensionalObjectParams`, `IdentifiableObjectParams` | Generic query-param DTOs that replace older `Base*` and per-resource `*Params` shapes |
| `Event` | Tracker event base shape |
| `IsoChronology`, `LocalDate` | Java-time primitives surfaced by the OAS now (replace ad-hoc string fields in v42) |
| `ProgramNotificationInstance`, `ProgramNotificationTemplateSnapshot` | Program-notification tracking shapes |
| `SectionRenderingObject`, `ValueTypeRenderingObject` | Form-rendering object shapes |
| `SystemCapability` | New `/api/system/capabilities` response item |
| `TrackedEntity` | Tracker tracked-entity payload (replaces v42's `TrackedEntity` import path; the old name was different) |
| `TrackerEventParams` | Tracker event query DTO |
| `TrackerSingleEvent`, `TrackerTrackerEvent` | The split between event-program "single" events and tracker-program "tracker" events — v43 separates them where v42 had one shared shape |

### OAS-side: removals

Models present in v42 that are gone in v43. Mostly internal `*Params` DTOs the OAS no longer emits separately, plus the push-analysis cluster.

| Removed model | Notes |
| --- | --- |
| `AnalyticsPeriodBoundaryParams` | Inlined |
| `BaseDimensionalItemObject`, `BaseDimensionalObject`, `BaseDimensionalObjectParams` | Replaced by the `Identifiable*Params` cluster |
| `DataEntryFormParams` | Inlined |
| `DataValueAuditDto`, `DataValueCategoryDto`, `DataValueDto` | Replaced by the new `DataValue*Params` / `DataValueChangelogEntry` cluster |
| `EventDataValue`, `EventParams` | Replaced by `Event` / `TrackerEventParams` |
| `IndicatorTypeParams`, `LegendParams`, `RelationshipParams`, `UserRoleParams` | Inlined |
| `PotentialDuplicateParams` | Inlined |
| `PushAnalysis`, `PushAnalysisJobParameters`, `PushAnalysisParams` | Push-analysis is removed (matches the schemas-side `pushanalysis` removal) |
| `TrackedEntityAttributeValueParams`, `TrackedEntityParams`, `TrackedEntityProgramOwnerParams` | Inlined |
| `TrackerEvent` | Renamed to `TrackerTrackerEvent` (or `TrackerSingleEvent` for event-program events) |
| `TrigramSummary` | Removed |

### Field renames (the ones that matter)

The two cases where a v42 field has a v43 counterpart under a different name. Both are in the breaking-shape table above; surfacing here as a lookup index:

| Schema | v42 field | v43 field | Notes |
| --- | --- | --- | --- |
| `dashboardItem` | `user` (singular `Reference`) | `users` (`list[User]`) | Wire fieldName is `users` in v43. |
| `trackedEntityAttribute` | `favorite` (singular `bool`) | `favorites` (`list[str]`) | Wire fieldName is `favorites` in v43; values are usernames. |
| `eventChart`, `eventReport`, `eventVisualization`, `mapView` | `period` collection (fieldName `periods`) | `period` collection (fieldName `persistedPeriods`) | The Python attribute name does not change — the wire fieldName does. Pydantic alias handles round-trip via the generator. |

### Code examples — accessing changed schemas

Copy-pasteable patterns for the most common cases. Read-side examples (showing how a v42-typed model parses a v43 wire payload via `model_extra` or how to upgrade to a typed `ProgramV43` import) live under `examples/client/`. Write-side examples for genuinely v43-only fields live under `examples/client/v43/`.

Read-side (v42-pinned reads of v43 wire data):

- [`dashboard_item_users.py`](https://github.com/winterop-com/dhis2w-utils/blob/main/examples/client/v43/dashboard_item_users.py)
- [`tracked_entity_attribute_favorites.py`](https://github.com/winterop-com/dhis2w-utils/blob/main/examples/client/v43/tracked_entity_attribute_favorites.py)
- [`event_visualization_fix_headers.py`](https://github.com/winterop-com/dhis2w-utils/blob/main/examples/client/v43/event_visualization_fix_headers.py)
- [`map_basemaps.py`](https://github.com/winterop-com/dhis2w-utils/blob/main/examples/client/v43/map_basemaps.py)
- [`section_user_removed.py`](https://github.com/winterop-com/dhis2w-utils/blob/main/examples/client/v43/section_user_removed.py)
- [`removed_resources.py`](https://github.com/winterop-com/dhis2w-utils/blob/main/examples/client/v43/removed_resources.py)

Write-side (v43-only setters via the v43 accessor):

- [`program_set_labels.py`](https://github.com/winterop-com/dhis2w-utils/blob/main/examples/client/v43/program_set_labels.py) — UI label overrides.
- [`program_set_change_log.py`](https://github.com/winterop-com/dhis2w-utils/blob/main/examples/client/v43/program_set_change_log.py) — `enableChangeLog` audit toggle.
- [`program_set_enrollment_category_combo.py`](https://github.com/winterop-com/dhis2w-utils/blob/main/examples/client/v43/program_set_enrollment_category_combo.py) — alt CC at enrollment time.

The narrative pattern descriptions are at [Working with version-specific types](versioning.md#working-with-version-specific-types).

All examples assume:

```python
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import profile_from_env
```

### `DashboardItem.user` -> `users` (rename + reshape)

v42 has a singular `user: Reference | None`. v43 has `users: list[User]` (wire fieldName `users`). The hand-written `client.dashboards` accessor parses against the v42 shape, so v43 wire data lands in `model_extra`.

```python
async with open_client(profile_from_env()) as client:
    dashboard = (await client.dashboards.list_all())[0]
    for item in dashboard.dashboardItems or []:
        if client.version_key == "v43":
            users = (item.model_extra or {}).get("users") or []
            owner_ids = [u.get("id") for u in users]
        else:
            owner_ids = [item.user.id] if item.user else []
        print(f"item {item.id} owners={owner_ids}")
```

For typed v43 access, import the v43 model directly:

```python
from dhis2w_client.generated.v43.schemas.dashboard import Dashboard as DashboardV43

raw = await client.get_raw(f"/api/dashboards/{dashboard.id}")
typed = DashboardV43.model_validate(raw)
for item in typed.dashboardItems or []:
    print(item.id, [u.id for u in item.users or []])
```

### `TrackedEntityAttribute.favorite` -> `favorites` (rename + reshape)

v42 has `favorite: bool` (per-user flag). v43 has `favorites: list[str]` (set of usernames who favourited). Plus six new search-tuning fields (`blockedSearchOperators`, `minCharactersToSearch`, `preferredSearchOperator`, `skipAnalytics`, `trigramIndexable`, `trigramIndexed`).

```python
from dhis2w_client.generated.v43.schemas.tracked_entity_attribute import (
    TrackedEntityAttribute as TrackedEntityAttributeV43,
)

raw = await client.get_raw(f"/api/trackedEntityAttributes/{uid}")
attribute = TrackedEntityAttributeV43.model_validate(raw)
print(
    f"favorited_by={attribute.favorites} "
    f"trigram_indexed={attribute.trigramIndexed} "
    f"min_search_chars={attribute.minCharactersToSearch}"
)
```

### `Section.user` (removed in v43)

The `user` reference is gone in v43. Defensive read from a v42-pinned model:

```python
section = await client.sections.get(section_uid)
owner = getattr(section, "user", None) if client.version_key == "v42" else None
```

Or fail fast if your code requires the field:

```python
if client.version_key != "v42":
    raise RuntimeError("Section.user is only available on v42")
```

### `Program.favorite` (removed in v43)

v42 had `favorite: list[str]`. v43 removed it entirely (the favouriting model moved to per-resource `favorites: list[str]` for resources that still expose it; Program no longer participates).

```python
program = await client.programs.get(program_uid)
if client.version_key == "v42":
    favorited_by = getattr(program, "favorite", None) or []
else:
    favorited_by = []  # field removed in v43
```

### `Program` v43-only additions (three orthogonal concerns)

v43 adds eight new fields to `Program`. They cluster into three unrelated concerns that just happen to share the schema delta — the accessor + CLI + MCP surface them as three separate setters rather than one omnibus tool:

| Concern | Fields | Accessor | CLI | MCP tool |
| --- | --- | --- | --- | --- |
| UI label overrides | `enrollmentsLabel`, `eventsLabel`, `programStagesLabel` (+ matching `display*`) | `client.programs.set_labels(uid, ...)` | `d2w metadata programs set-labels` | `metadata_program_set_labels` |
| Server-side audit toggle | `enableChangeLog` | `client.programs.set_change_log_enabled(uid, enabled)` | `d2w metadata programs set-change-log` | `metadata_program_set_change_log_enabled` |
| Alt enrollment CategoryCombo | `enrollmentCategoryCombo` | `client.programs.set_enrollment_category_combo(uid, cc_uid)` | `d2w metadata programs set-enrollment-category-combo` | `metadata_program_set_enrollment_category_combo` |

**Reading** the new fields on v43 — the v43 `ProgramsAccessor` requests them in its read fields, so they surface as typed attributes on the parsed `Program` when the active version is v43:

```python
from dhis2w_core.profile import profile_from_env
from dhis2w_core.v43.client_context import open_client

async with open_client(profile_from_env()) as client:
    program = await client.programs.get(program_uid)
    print(program.enableChangeLog, program.enrollmentsLabel, program.eventsLabel)
```

`dhis2w_core.v43.client_context.open_client` yields a `dhis2w_client.v43.Dhis2Client` directly so static typing flows through the v43-only `Program` attributes. If you're using the top-level `dhis2w_core.client_context.open_client` instead, the accessors are still dispatched to v43 at runtime when `client.version_key == "v43"` — but type-checkers see them as the v42 shape, so `program.enableChangeLog` would need a `# type: ignore[attr-defined]` or a cast.

**Writing** — three separate calls, one per concern:

```python
# UI label overrides only
await client.programs.set_labels(
    program_uid,
    enrollments_label="Visits",
    events_label="Encounters",
    program_stages_label="Care Stages",
)

# Server-side audit toggle only
await client.programs.set_change_log_enabled(program_uid, True)

# Alt enrollment CategoryCombo only
await client.programs.set_enrollment_category_combo(program_uid, alt_cc_uid)
```

Worked examples (one per concern):

- [`examples/client/v43/program_set_labels.py`](https://github.com/winterop-com/dhis2w-utils/blob/main/examples/client/v43/program_set_labels.py)
- [`examples/client/v43/program_set_change_log.py`](https://github.com/winterop-com/dhis2w-utils/blob/main/examples/client/v43/program_set_change_log.py)
- [`examples/client/v43/program_set_enrollment_category_combo.py`](https://github.com/winterop-com/dhis2w-utils/blob/main/examples/client/v43/program_set_enrollment_category_combo.py)

CLI + MCP equivalents (v43-only):

```bash
d2w metadata programs set-labels PRG... --enrollments-label Visits --events-label Encounters
d2w metadata programs set-change-log PRG... --enable
d2w metadata programs set-enrollment-category-combo PRG... CC_ALT...
```

For v42-pinned typed reads of v43 wire data — e.g. parsing a raw response directly with the v42 model — the fields fall through to `model_extra`. Use the v43 `Program` import to get them typed:

```python
from dhis2w_client.generated.v43.schemas.program import Program as ProgramV43

raw = await client.get_raw(f"/api/programs/{program_uid}")
program_v43 = ProgramV43.model_validate(raw)
print(program_v43.enableChangeLog, program_v43.enrollmentsLabel)
```

### `EventVisualization.fixColumnHeaders` + friends (v43-only additions)

`EventChart`, `EventReport`, and `EventVisualization` all gained `fixColumnHeaders`, `fixRowHeaders`, and `hideEmptyColumns` in v43. (The regular `Visualization` already had them in v42.)

```python
viz = await client.visualizations.get(viz_uid)
extras = viz.model_extra or {}
fix_columns = extras.get("fixColumnHeaders")
fix_rows = extras.get("fixRowHeaders")
hide_empty = extras.get("hideEmptyColumns")
```

### `Map.basemaps` (v43-only addition)

```python
map_obj = await client.maps.get(map_uid)
basemaps = (map_obj.model_extra or {}).get("basemaps") or []  # v43 only
for bm in basemaps:
    print(bm.get("id"), bm.get("name"))
```

For typed access via the new v43 `Basemap` model:

```python
from dhis2w_client.generated.v43.oas.basemap import Basemap

raw = await client.get_raw(f"/api/maps/{map_uid}")
basemaps = [Basemap.model_validate(bm) for bm in (raw.get("basemaps") or [])]
```

### Removed top-level resources (`pushanalysis`, `externalFileResource`, `dataInputPeriods`)

These resources don't exist on v43. There is no `client.resources.pushanalysis` accessor on the v43 client because the codegen reflects the live `/api/schemas` response. Branch on version before accessing:

```python
if client.version_key == "v42":
    pushes = await client.get_raw("/api/pushAnalysis?fields=id,name&pageSize=10")
    print(pushes)
else:
    print("pushAnalysis is removed in v43")
```

`dataInputPeriods` is folded inline under `dataSet.dataInputPeriods` in v43 — no top-level resource, but the data is still reachable through `client.data_sets.get(uid)` which already includes the inline collection on both versions.

### `userGroup.description` (v43-only addition)

A single new field, illustrative of the simplest pure-addition case:

```python
group = await client.user_groups.get(group_uid)
description = (group.model_extra or {}).get("description") if client.version_key == "v43" else None
```

## Reproducing this diff

```bash
# Schemas-side
uv run d2w dev codegen diff v42 v43

# OAS-side (no CLI; plain ls comparison)
diff \
  <(ls packages/dhis2w-client/src/dhis2w_client/generated/v42/oas/ | grep -v __pycache__) \
  <(ls packages/dhis2w-client/src/dhis2w_client/generated/v43/oas/)
```

## Appendix: complete v42 -> v43 schemas-side diff

Raw output of `d2w dev codegen diff v42 v43`. Reproduced verbatim so the field-by-field bound shifts are searchable in the docs site.

```text
Schema diff: v42 -> v43
  added schemas: 0   removed schemas: 3   changed schemas: 40

## Removed (only in v42)
  - dataInputPeriods  (3 props, klass=org.hisp.dhis.dataset.DataInputPeriod)
  - externalFileResource  (19 props, klass=org.hisp.dhis.fileresource.ExternalFileResource)
  - pushanalysis  (20 props, klass=org.hisp.dhis.pushanalysis.PushAnalysis)

## Changed
  ~ access
      - externalize  (BOOLEAN)
  ~ attribute
      ~ valueType:
  ~ category
      ~ valueType:
  ~ categoryCombo
      - favorite  (BOOLEAN)
      ~ href: propertyType: 'URL' -> 'TEXT', max: 1.7976931348623157e+308 -> 2147483647.0
      ~ translation: max: 255.0 -> 1.7976931348623157e+308
  ~ categoryOption
      - aggregationType  (CONSTANT)
      - dimensionItem  (TEXT)
      - dimensionItemType  (CONSTANT)
      - favorite  (BOOLEAN)
      - legendSet  (REFERENCE)
      - legendSets  (COLLECTION collection of LegendSet)
      ~ description: min: 1.0 -> 0.0, max: 2147483647.0 -> 255.0
      ~ href: propertyType: 'URL' -> 'TEXT', max: 1.7976931348623157e+308 -> 2147483647.0
      ~ shortName: min: 1.0 -> 0.0
      ~ translation: max: 255.0 -> 1.7976931348623157e+308
  ~ categoryOptionGroupSet
      ~ valueType:
  ~ dashboard
      - displayFormName  (TEXT)
      - displayShortName  (TEXT)
      - formName  (TEXT)
      - shortName  (TEXT)
      ~ description: min: 1.0 -> 0.0, max: 2147483647.0 -> 255.0
      ~ translation: max: 255.0 -> 1.7976931348623157e+308
  ~ dashboardItem
      + displayText  (TEXT)
      - displayName  (TEXT)
      - favorite  (BOOLEAN)
      ~ code: propertyType: 'IDENTIFIER' -> 'TEXT', unique: True -> False, max: 50.0 -> 255.0
      ~ created: required: False -> True
      ~ href: propertyType: 'URL' -> 'TEXT', max: 1.7976931348623157e+308 -> 2147483647.0
      ~ id: propertyType: 'IDENTIFIER' -> 'TEXT', required: False -> True, min: 11.0 -> 0.0
      ~ lastUpdated: required: False -> True
      ~ name: min: 1.0 -> 0.0
      ~ translation: max: 255.0 -> 1.7976931348623157e+308
      ~ user: propertyType: 'REFERENCE' -> 'COLLECTION', klass: 'org.hisp.dhis.user.User' -> 'java.util.List', itemKlass: None -> 'org.hisp.dhis.user.User', itemPropertyType: None -> 'REFERENCE', collection: False -> True, owner: False -> True, persisted: False -> True, min: None -> 0.0, max: None -> 1.7976931348623157e+308, fieldName: 'user' -> 'users'
  ~ dataApprovalLevel
      + translations  (COLLECTION collection of Translation)
      - favorite  (BOOLEAN)
      - translation  (COLLECTION collection of Translation)
      ~ href: propertyType: 'URL' -> 'TEXT', max: 1.7976931348623157e+308 -> 2147483647.0
      ~ name: min: 1.0 -> 0.0
      ~ orgUnitLevel: min: 0.0 -> -2147483648.0
  ~ dataApprovalWorkflow
      + translations  (COLLECTION collection of Translation)
      - favorite  (BOOLEAN)
      - translation  (COLLECTION collection of Translation)
      ~ code: propertyType: 'IDENTIFIER' -> 'TEXT'
      ~ href: propertyType: 'URL' -> 'TEXT', max: 1.7976931348623157e+308 -> 2147483647.0
      ~ name: min: 1.0 -> 0.0
  ~ dataElement
      ~ valueType:
  ~ dataElementGroupSet
      ~ valueType:
  ~ eventChart
      + fixColumnHeaders  (BOOLEAN)
      + fixRowHeaders  (BOOLEAN)
      + hideEmptyColumns  (BOOLEAN)
      ~ period: itemPropertyType: 'REFERENCE' -> 'COMPLEX', fieldName: 'periods' -> 'persistedPeriods'
  ~ eventReport
      + fixColumnHeaders  (BOOLEAN)
      + fixRowHeaders  (BOOLEAN)
      + hideEmptyColumns  (BOOLEAN)
      ~ period: itemPropertyType: 'REFERENCE' -> 'COMPLEX', fieldName: 'periods' -> 'persistedPeriods'
  ~ eventVisualization
      + fixColumnHeaders  (BOOLEAN)
      + fixRowHeaders  (BOOLEAN)
      + hideEmptyColumns  (BOOLEAN)
      ~ period: itemPropertyType: 'REFERENCE' -> 'COMPLEX', fieldName: 'periods' -> 'persistedPeriods'
  ~ identifiableObject
      ~ domain:
  ~ indicatorGroup
      - favorite  (BOOLEAN)
      ~ description: max: 2147483647.0 -> 255.0
      ~ href: propertyType: 'URL' -> 'TEXT', max: 1.7976931348623157e+308 -> 2147483647.0
      ~ name: unique: False -> True
      ~ translation: max: 255.0 -> 1.7976931348623157e+308
  ~ indicatorGroupSet
      + displayDescription  (TEXT)
      + displayShortName  (TEXT)
      - favorite  (BOOLEAN)
      ~ description: max: 2147483647.0 -> 255.0
      ~ href: propertyType: 'URL' -> 'TEXT', max: 1.7976931348623157e+308 -> 2147483647.0
      ~ translation: max: 255.0 -> 1.7976931348623157e+308
  ~ interpretation
      ~ period: propertyType: 'REFERENCE' -> 'COMPLEX', min: None -> 0.0, max: None -> 255.0
  ~ legend
      + set  (REFERENCE)
      + showKey  (BOOLEAN)
      + strategy  (CONSTANT)
      + style  (CONSTANT)
      - access  (COMPLEX)
      - attributeValues  (COMPLEX)
      - code  (IDENTIFIER)
      - color  (TEXT)
      - created  (DATE)
      - createdBy  (REFERENCE)
      - displayName  (TEXT)
      - endValue  (NUMBER)
      - favorite  (BOOLEAN)
      - href  (URL)
      - id  (IDENTIFIER)
      - image  (TEXT)
      - lastUpdated  (DATE)
      - lastUpdatedBy  (REFERENCE)
      - name  (TEXT)
      - sharing  (COMPLEX)
      - startValue  (NUMBER)
      - translation  (COLLECTION collection of Translation)
      - user  (REFERENCE)
  ~ legendSet
      + translations  (COLLECTION collection of Translation)
      - favorite  (BOOLEAN)
      - translation  (COLLECTION collection of Translation)
      ~ code: propertyType: 'IDENTIFIER' -> 'TEXT', unique: True -> False
      ~ href: propertyType: 'URL' -> 'TEXT', max: 1.7976931348623157e+308 -> 2147483647.0
      ~ name: min: 1.0 -> 0.0
  ~ map
      + basemaps  (COLLECTION collection of Basemap)
  ~ mapView
      + eventCoordinateFieldFallback  (TEXT)
      ~ period: itemPropertyType: 'REFERENCE' -> 'COMPLEX', fieldName: 'periods' -> 'persistedPeriods'
  ~ optionGroupSet
      ~ valueType:
  ~ optionSet
      - favorite  (BOOLEAN)
      ~ description: max: 2147483647.0 -> 255.0
      ~ href: propertyType: 'URL' -> 'TEXT', max: 1.7976931348623157e+308 -> 2147483647.0
      ~ translation: max: 255.0 -> 1.7976931348623157e+308
      ~ valueType:
      ~ version: required: False -> True
  ~ organisationUnitGroupSet
      ~ valueType:
  ~ program
      + displayEnrollmentsLabel  (TEXT)
      + displayEventsLabel  (TEXT)
      + displayProgramStagesLabel  (TEXT)
      + enableChangeLog  (BOOLEAN)
      + enrollmentCategoryCombo  (REFERENCE)
      + enrollmentsLabel  (TEXT)
      + eventsLabel  (TEXT)
      + programStagesLabel  (TEXT)
      - favorite  (COLLECTION collection of String)
      ~ description: max: 2147483647.0 -> 255.0
      ~ enrollmentDateLabel: max: 2147483647.0 -> 255.0
      ~ enrollmentLabel: max: 2147483647.0 -> 255.0
      ~ eventLabel: max: 2147483647.0 -> 255.0
      ~ followUpLabel: max: 2147483647.0 -> 255.0
      ~ formName: max: 2147483647.0 -> 255.0
      ~ href: propertyType: 'URL' -> 'TEXT', max: 1.7976931348623157e+308 -> 2147483647.0
      ~ incidentDateLabel: max: 2147483647.0 -> 255.0
      ~ noteLabel: max: 2147483647.0 -> 255.0
      ~ orgUnitLabel: max: 2147483647.0 -> 255.0
      ~ programStageLabel: max: 2147483647.0 -> 255.0
      ~ relationshipLabel: max: 2147483647.0 -> 255.0
      ~ trackedEntityAttributeLabel: max: 2147483647.0 -> 255.0
      ~ translation: max: 255.0 -> 1.7976931348623157e+308
      ~ userRole: owner: False -> True
  ~ programDataElement
      ~ valueType:
  ~ programRuleAction
      + legendSet  (REFERENCE)
      + priority  (INTEGER)
      ~ programRuleActionType:
  ~ programRuleVariable
      ~ valueType:
  ~ programStage
      + displayEventsLabel  (TEXT)
      + eventsLabel  (TEXT)
      ~ description: min: 2.0 -> 1.0
  ~ programTrackedEntityAttribute
      - skipIndividualAnalytics  (BOOLEAN)
      ~ valueType:
  ~ section
      - favorite  (BOOLEAN)
      - user  (REFERENCE)
      ~ code: propertyType: 'IDENTIFIER' -> 'TEXT', min: 0.0 -> 1.0
      ~ description: max: 2147483647.0 -> 255.0
      ~ id: propertyType: 'IDENTIFIER' -> 'TEXT', required: False -> True
      ~ showColumnTotals: required: False -> True
      ~ showRowTotals: required: False -> True
      ~ translation: max: 255.0 -> 1.7976931348623157e+308
  ~ sharing
      - external  (BOOLEAN)
  ~ trackedEntityAttribute
      + blockedSearchOperators  (COLLECTION collection of QueryOperator)
      + minCharactersToSearch  (INTEGER)
      + preferredSearchOperator  (CONSTANT)
      + skipAnalytics  (BOOLEAN)
      + trigramIndexable  (BOOLEAN)
      + trigramIndexed  (BOOLEAN)
      ~ favorite: propertyType: 'BOOLEAN' -> 'COLLECTION', klass: 'java.lang.Boolean' -> 'java.util.Set', itemKlass: None -> 'java.lang.String', itemPropertyType: None -> 'TEXT', collection: False -> True, writable: False -> True, min: None -> 0.0, max: None -> 1.7976931348623157e+308, fieldName: 'favorite' -> 'favorites'
      ~ valueType:
  ~ trackedEntityType
      + displayTrackedEntityTypesLabel  (TEXT)
      + enableChangeLog  (BOOLEAN)
      + trackedEntityTypesLabel  (TEXT)
  ~ trackedEntityTypeAttribute
      ~ valueType:
  ~ userGroup
      + description  (TEXT)
  ~ validationResult
      ~ period: propertyType: 'REFERENCE' -> 'COMPLEX', min: None -> 0.0, max: None -> 1.7976931348623157e+308
  ~ visualization
      ~ period: itemPropertyType: 'REFERENCE' -> 'COMPLEX', fieldName: 'periods' -> 'persistedPeriods'
```


## Appendix: complete v41 -> v42 schemas-side diff

Raw output of `d2w dev codegen diff v41 v42`. Reproduced verbatim so the field-by-field bound shifts are searchable in the docs site.

```text
Schema diff: v41 -> v42
  added schemas: 3   removed schemas: 9   changed schemas: 86

## Added in v42
  + oauth2Authorization  (49 props, klass=org.hisp.dhis.security.oauth2.authorization.Dhis2OAuth2Authorization)
  + oauth2AuthorizationConsent  (19 props, klass=org.hisp.dhis.security.oauth2.consent.Dhis2OAuth2AuthorizationConsent)
  + oauth2Client  (27 props, klass=org.hisp.dhis.security.oauth2.client.Dhis2OAuth2Client)

## Removed (only in v41)
  - attributeValues  (2 props, klass=org.hisp.dhis.attribute.AttributeValue)
  - enrollment  (36 props, klass=org.hisp.dhis.program.Enrollment)
  - oAuth2Client  (20 props, klass=org.hisp.dhis.security.oauth2.OAuth2Client)
  - relationship  (24 props, klass=org.hisp.dhis.relationship.Relationship)
  - relationshipItem  (4 props, klass=org.hisp.dhis.relationship.RelationshipItem)
  - softDeletableObject  (39 props, klass=org.hisp.dhis.program.Event)
  - trackedEntityAttributeValue  (6 props, klass=org.hisp.dhis.trackedentityattributevalue.TrackedEntityAttributeValue)
  - trackedEntityInstance  (31 props, klass=org.hisp.dhis.trackedentity.TrackedEntity)
  - userCredentialsDto  (24 props, klass=org.hisp.dhis.user.UserCredentialsDto)

## Changed
  ~ aggregateDataExchange
      + attributeValues  (COMPLEX)
      - attributeValue  (COLLECTION collection of AttributeValue)
  ~ analyticsPeriodBoundary
      + attributeValues  (COMPLEX)
      - attributeValue  (COLLECTION collection of AttributeValue)
  ~ analyticsTableHook
      + attributeValues  (COMPLEX)
      - attributeValue  (COLLECTION collection of AttributeValue)
      ~ resourceTableType: 
  ~ apiToken
      + attributeValues  (COMPLEX)
      - attributeValue  (COLLECTION collection of AttributeValue)
  ~ attribute
      + attributeValues  (COMPLEX)
      - attributeValue  (COLLECTION collection of AttributeValue)
  ~ category
      + attributeValues  (COMPLEX)
      - attributeValue  (COLLECTION collection of AttributeValue)
  ~ categoryCombo
      + attributeValues  (COMPLEX)
      - attributeValue  (COLLECTION collection of AttributeValue)
  ~ categoryOption
      + attributeValues  (COMPLEX)
      - attributeValue  (COLLECTION collection of AttributeValue)
      ~ dimensionItemType: 
  ~ categoryOptionCombo
      + attributeValues  (COMPLEX)
      - attributeValue  (COLLECTION collection of AttributeValue)
      ~ dimensionItemType: 
  ~ categoryOptionGroup
      + attributeValues  (COMPLEX)
      - attributeValue  (COLLECTION collection of AttributeValue)
      ~ dimensionItemType: 
  ~ categoryOptionGroupSet
      + attributeValues  (COMPLEX)
      - attributeValue  (COLLECTION collection of AttributeValue)
  ~ constant
      + attributeValues  (COMPLEX)
      - attributeValue  (COLLECTION collection of AttributeValue)
  ~ dashboard
      + attributeValues  (COMPLEX)
      + embedded  (COMPLEX)
      - attributeValue  (COLLECTION collection of AttributeValue)
      ~ shortName: max: 2147483647.0 -> 50.0
  ~ dashboardItem
      + attributeValues  (COMPLEX)
      - attributeValue  (COLLECTION collection of AttributeValue)
  ~ dataApprovalLevel
      + attributeValues  (COMPLEX)
      - attributeValue  (COLLECTION collection of AttributeValue)
  ~ dataApprovalWorkflow
      + attributeValues  (COMPLEX)
      - attributeValue  (COLLECTION collection of AttributeValue)
      ~ categoryCombo: required: False -> True
  ~ dataElement
      + attributeValues  (COMPLEX)
      - attributeValue  (COLLECTION collection of AttributeValue)
      ~ dimensionItemType: 
  ~ dataElementGroup
      + attributeValues  (COMPLEX)
      - attributeValue  (COLLECTION collection of AttributeValue)
      ~ dimensionItemType: 
  ~ dataElementGroupSet
      + attributeValues  (COMPLEX)
      - attributeValue  (COLLECTION collection of AttributeValue)
  ~ dataElementOperand
      + attributeValues  (COMPLEX)
      - attributeValue  (COLLECTION collection of AttributeValue)
      ~ dimensionItemType: 
  ~ dataEntryForm
      + attributeValues  (COMPLEX)
      - attributeValue  (COLLECTION collection of AttributeValue)
  ~ dataSet
      + attributeValues  (COMPLEX)
      + displayOptions  (TEXT)
      - attributeValue  (COLLECTION collection of AttributeValue)
      ~ dimensionItemType: 
      ~ expiryDays: propertyType: 'INTEGER' -> 'NUMBER', klass: 'java.lang.Integer' -> 'java.lang.Double', max: 2147483647.0 -> 1.7976931348623157e+308
  ~ dataSetNotificationTemplate
      + attributeValues  (COMPLEX)
      - attributeValue  (COLLECTION collection of AttributeValue)
  ~ document
      + attributeValues  (COMPLEX)
      - attributeValue  (COLLECTION collection of AttributeValue)
  ~ eventChart
      + attributeValues  (COMPLEX)
      + metaData  (COMPLEX)
      - attributeValue  (COLLECTION collection of AttributeValue)
      ~ programStatus: klass: 'org.hisp.dhis.program.ProgramStatus' -> 'org.hisp.dhis.program.EnrollmentStatus'
      ~ shortName: max: 2147483647.0 -> 50.0
  ~ eventFilter
      + attributeValues  (COMPLEX)
      - attributeValue  (COLLECTION collection of AttributeValue)
  ~ eventReport
      + attributeValues  (COMPLEX)
      + metaData  (COMPLEX)
      - attributeValue  (COLLECTION collection of AttributeValue)
      ~ programStatus: klass: 'org.hisp.dhis.program.ProgramStatus' -> 'org.hisp.dhis.program.EnrollmentStatus'
      ~ shortName: max: 2147483647.0 -> 50.0
  ~ eventVisualization
      + attributeValues  (COMPLEX)
      + metaData  (COMPLEX)
      - attributeValue  (COLLECTION collection of AttributeValue)
      ~ programStatus: klass: 'org.hisp.dhis.program.ProgramStatus' -> 'org.hisp.dhis.program.EnrollmentStatus'
      ~ shortName: max: 2147483647.0 -> 50.0
  ~ expressionDimensionItem
      + attributeValues  (COMPLEX)
      - attributeValue  (COLLECTION collection of AttributeValue)
      ~ dimensionItemType: 
  ~ externalFileResource
      + attributeValues  (COMPLEX)
      - attributeValue  (COLLECTION collection of AttributeValue)
  ~ externalMapLayer
      + attributeValues  (COMPLEX)
      - attributeValue  (COLLECTION collection of AttributeValue)
  ~ identifiableObject
      + attributeValues  (COMPLEX)
      - attributeValue  (COLLECTION collection of AttributeValue)
  ~ indicator
      + attributeValues  (COMPLEX)
      - attributeValue  (COLLECTION collection of AttributeValue)
      ~ dimensionItemType: 
  ~ indicatorGroup
      + attributeValues  (COMPLEX)
      - attributeValue  (COLLECTION collection of AttributeValue)
  ~ indicatorGroupSet
      + attributeValues  (COMPLEX)
      - attributeValue  (COLLECTION collection of AttributeValue)
  ~ indicatorType
      + attributeValues  (COMPLEX)
      - attributeValue  (COLLECTION collection of AttributeValue)
  ~ interpretation
      + attributeValues  (COMPLEX)
      - attributeValue  (COLLECTION collection of AttributeValue)
  ~ interpretationComment
      + attributeValues  (COMPLEX)
      - attributeValue  (COLLECTION collection of AttributeValue)
  ~ legend
      + attributeValues  (COMPLEX)
      - attributeValue  (COLLECTION collection of AttributeValue)
  ~ legendSet
      + attributeValues  (COMPLEX)
      - attributeValue  (COLLECTION collection of AttributeValue)
  ~ map
      + attributeValues  (COMPLEX)
      - attributeValue  (COLLECTION collection of AttributeValue)
      ~ shortName: max: 2147483647.0 -> 50.0
  ~ mapView
      + attributeValues  (COMPLEX)
      + metaData  (COMPLEX)
      - attributeValue  (COLLECTION collection of AttributeValue)
      ~ name: owner: False -> True, persisted: False -> True, min: 0.0 -> 1.0, max: 2147483647.0 -> 230.0
      ~ programStatus: klass: 'org.hisp.dhis.program.ProgramStatus' -> 'org.hisp.dhis.program.EnrollmentStatus'
      ~ shortName: max: 2147483647.0 -> 50.0
  ~ messageConversation
      + attributeValues  (COMPLEX)
      - attributeValue  (COLLECTION collection of AttributeValue)
  ~ metadataVersion
      + attributeValues  (COMPLEX)
      - attributeValue  (COLLECTION collection of AttributeValue)
  ~ option
      + attributeValues  (COMPLEX)
      - attributeValue  (COLLECTION collection of AttributeValue)
      ~ shortName: max: 2147483647.0 -> 50.0
  ~ optionGroup
      + attributeValues  (COMPLEX)
      - attributeValue  (COLLECTION collection of AttributeValue)
      ~ dimensionItemType: 
  ~ optionGroupSet
      + attributeValues  (COMPLEX)
      - attributeValue  (COLLECTION collection of AttributeValue)
      ~ shortName: max: 2147483647.0 -> 50.0
  ~ optionSet
      + attributeValues  (COMPLEX)
      - attributeValue  (COLLECTION collection of AttributeValue)
  ~ organisationUnit
      + attributeValues  (COMPLEX)
      - attributeValue  (COLLECTION collection of AttributeValue)
      ~ dimensionItemType: 
  ~ organisationUnitGroup
      + attributeValues  (COMPLEX)
      - attributeValue  (COLLECTION collection of AttributeValue)
      ~ dimensionItemType: 
  ~ organisationUnitGroupSet
      + attributeValues  (COMPLEX)
      - attributeValue  (COLLECTION collection of AttributeValue)
  ~ organisationUnitLevel
      + attributeValues  (COMPLEX)
      - attributeValue  (COLLECTION collection of AttributeValue)
  ~ predictor
      + attributeValues  (COMPLEX)
      - attributeValue  (COLLECTION collection of AttributeValue)
  ~ predictorGroup
      + attributeValues  (COMPLEX)
      - attributeValue  (COLLECTION collection of AttributeValue)
  ~ program
      + attributeValues  (COMPLEX)
      + categoryMappings  (COLLECTION collection of ProgramCategoryMapping)
      - attributeValue  (COLLECTION collection of AttributeValue)
  ~ programAttributeDimension
      + attributeValues  (COMPLEX)
      - attributeValue  (COLLECTION collection of AttributeValue)
      ~ dimensionItemType: 
      ~ shortName: max: 2147483647.0 -> 50.0
  ~ programDataElement
      + attributeValues  (COMPLEX)
      - attributeValue  (COLLECTION collection of AttributeValue)
      ~ dimensionItemType: 
  ~ programIndicator
      + aggregateExportDataElement  (TEXT)
      + attributeCombo  (REFERENCE)
      + attributeValues  (COMPLEX)
      + categoryCombo  (REFERENCE)
      + categoryMappingIds  (COLLECTION collection of String)
      - attributeValue  (COLLECTION collection of AttributeValue)
      ~ dimensionItemType: 
  ~ programIndicatorGroup
      + attributeValues  (COMPLEX)
      - attributeValue  (COLLECTION collection of AttributeValue)
  ~ programNotificationTemplate
      + attributeValues  (COMPLEX)
      - attributeValue  (COLLECTION collection of AttributeValue)
  ~ programRule
      + attributeValues  (COMPLEX)
      - attributeValue  (COLLECTION collection of AttributeValue)
  ~ programRuleAction
      + attributeValues  (COMPLEX)
      - attributeValue  (COLLECTION collection of AttributeValue)
      ~ templateUid: persisted: True -> False, max: 255.0 -> 2147483647.0
  ~ programRuleVariable
      + attributeValues  (COMPLEX)
      - attributeValue  (COLLECTION collection of AttributeValue)
  ~ programSection
      + attributeValues  (COMPLEX)
      - attributeValue  (COLLECTION collection of AttributeValue)
      ~ shortName: max: 2147483647.0 -> 50.0
  ~ programStage
      + attributeValues  (COMPLEX)
      - attributeValue  (COLLECTION collection of AttributeValue)
      ~ shortName: max: 2147483647.0 -> 50.0
  ~ programStageDataElement
      + attributeValues  (COMPLEX)
      - attributeValue  (COLLECTION collection of AttributeValue)
  ~ programStageSection
      + attributeValues  (COMPLEX)
      - attributeValue  (COLLECTION collection of AttributeValue)
      ~ shortName: max: 2147483647.0 -> 50.0
  ~ programStageWorkingList
      + attributeValues  (COMPLEX)
      - attributeValue  (COLLECTION collection of AttributeValue)
  ~ programTrackedEntityAttribute
      + attributeValues  (COMPLEX)
      + skipIndividualAnalytics  (BOOLEAN)
      - attributeValue  (COLLECTION collection of AttributeValue)
  ~ pushanalysis
      + attributeValues  (COMPLEX)
      - attributeValue  (COLLECTION collection of AttributeValue)
  ~ relationshipType
      + attributeValues  (COMPLEX)
      - attributeValue  (COLLECTION collection of AttributeValue)
  ~ report
      + attributeValues  (COMPLEX)
      - attributeValue  (COLLECTION collection of AttributeValue)
  ~ reportingRate
      + attributeValues  (COMPLEX)
      - attributeValue  (COLLECTION collection of AttributeValue)
      ~ dimensionItemType: 
  ~ section
      + attributeValues  (COMPLEX)
      - attributeValue  (COLLECTION collection of AttributeValue)
  ~ smscommand
      + attributeValues  (COMPLEX)
      - attributeValue  (COLLECTION collection of AttributeValue)
      ~ parserType: 
  ~ sqlView
      + attributeValues  (COMPLEX)
      - attributeValue  (COLLECTION collection of AttributeValue)
  ~ trackedEntityAttribute
      + attributeValues  (COMPLEX)
      - attributeValue  (COLLECTION collection of AttributeValue)
      ~ dimensionItemType: 
  ~ trackedEntityFilter
      + attributeValues  (COMPLEX)
      - attributeValue  (COLLECTION collection of AttributeValue)
      ~ enrollmentStatus: klass: 'org.hisp.dhis.program.ProgramStatus' -> 'org.hisp.dhis.program.EnrollmentStatus'
  ~ trackedEntityType
      + attributeValues  (COMPLEX)
      - attributeValue  (COLLECTION collection of AttributeValue)
      ~ shortName: owner: False -> True, required: False -> True, persisted: False -> True, unique: False -> True, max: 2147483647.0 -> 50.0
  ~ trackedEntityTypeAttribute
      + attributeValues  (COMPLEX)
      - attributeValue  (COLLECTION collection of AttributeValue)
  ~ user
      + attributeValues  (COMPLEX)
      + emailVerificationToken  (TEXT)
      + emailVerified  (BOOLEAN)
      + verifiedEmail  (TEXT)
      - attributeValue  (COLLECTION collection of AttributeValue)
      - twoFactorEnabled  (BOOLEAN)
      - userCredentials  (COMPLEX)
      ~ firstName: required: False -> True, min: 1.0 -> 2.0
      ~ name: owner: False -> True, writable: True -> False, persisted: False -> True, max: 2147483647.0 -> 321.0
      ~ settings: klass: 'org.hisp.dhis.user.UserSettings' -> 'java.util.Map'
      ~ surname: required: False -> True, min: 1.0 -> 2.0
  ~ userGroup
      + attributeValues  (COMPLEX)
      - attributeValue  (COLLECTION collection of AttributeValue)
  ~ userRole
      + attributeValues  (COMPLEX)
      - attributeValue  (COLLECTION collection of AttributeValue)
  ~ validationRule
      + attributeValues  (COMPLEX)
      - attributeValue  (COLLECTION collection of AttributeValue)
      ~ dimensionItemType: 
      ~ shortName: max: 2147483647.0 -> 50.0
  ~ validationRuleGroup
      + attributeValues  (COMPLEX)
      - attributeValue  (COLLECTION collection of AttributeValue)
  ~ visualization
      + attributeValues  (COMPLEX)
      + metaData  (COMPLEX)
      - attributeValue  (COLLECTION collection of AttributeValue)
      ~ shortName: max: 2147483647.0 -> 50.0

```
