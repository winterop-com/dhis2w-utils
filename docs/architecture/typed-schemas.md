# Typed schemas

`dhis2w-client` exports three families of pydantic models that give callers a typed surface over the DHIS2 JSON API. All three are derived from DHIS2's OpenAPI spec (`/api/openapi.json`) with a per-version copy committed under `packages/dhis2w-client/src/dhis2w_client/generated/v{N}/openapi.json`.

## 1. WebMessageResponse — write-envelope model

Every POST / PUT / PATCH / DELETE through `/api/*` returns one of DHIS2's WebMessage envelopes. `WebMessageResponse` models the common shape, leaving the inner `response` field loose (its subtype varies by endpoint) but giving callers typed methods to narrow it.

```python
from dhis2w_client import WebMessageResponse
response = await route_service.add_route(profile, payload)

response.httpStatus           # "Created"
response.httpStatusCode       # 201
response.status               # "OK"

response.created_uid          # "abc123uid12" — pulls response.uid, closes BUGS.md #4f
report = response.object_report()          # typed ObjectReport when the inner is a create/update
counts = response.import_count()           # typed ImportCount for /api/dataValueSets imports
full_report = response.import_report()     # typed ImportReport for /api/metadata bulk imports
conflicts = response.conflicts()           # list[Conflict] — /api/dataValueSets + /api/tracker rejections (response.conflicts[])
rows = response.conflict_rows()            # list[ConflictRow] — unified view across /api/dataValueSets AND /api/metadata
rejected = response.rejected_indexes()     # list[int] — indexes in the payload array DHIS2 refused
```

Available subtypes: `ObjectReport`, `ImportCount`, `ImportReport`, `ErrorReport`, `Stats`, `TypeReport`, `Conflict`, `ConflictRow` — all exported from `dhis2w_client`.

**Two conflict shapes, one renderer.** DHIS2 surfaces errors in two different places depending on the endpoint:

- `/api/dataValueSets` + `/api/tracker` — `response.conflicts[]` (flat list). `conflicts()` returns these verbatim.
- `/api/metadata` — `response.typeReports[*].objectReports[*].errorReports[*]` (three-level tree, each error tagged with the owning resource type + UID). `conflicts()` misses these entirely.

`conflict_rows()` normalises both shapes into a flat `list[ConflictRow]` (`resource`, `uid`, `property`, `value`, `error_code`, `message`, `indexes`) so CLI / agent renderers can show one Rich table regardless of where the error lived on the wire. `dhis2w_core.cli_output.render_conflicts(rows)` is the default renderer — grouped by resource + error code, truncated to the first 25 rows by default.

On a rejected write, `Dhis2ApiError.body` carries the raw body and `Dhis2ApiError.web_message` lazily parses it into a `WebMessageResponse`, so callers react to `conflict_rows()` / `importCount` without re-parsing. The CLI's clean-error renderer chains into `render_conflicts` automatically on any 4xx that carries structured error detail.

Every plugin's write service returns `WebMessageResponse`:

| Plugin | Methods |
|---|---|
| route | `add_route`, `update_route`, `patch_route`, `delete_route` |
| aggregate | `push_data_values`, `set_data_value`, `delete_data_value` |
| tracker | `push_tracker` |
| analytics | `refresh_analytics` |

## 2. AuthScheme — discriminated union for Route auth

Route auth blocks (see [Route API guide](../guides/connecting-to-dhis2.md)) are polymorphic — the `type` field discriminates between five variants. The union is typed end-to-end.

```python
from dhis2w_client import (
    AuthScheme,
    AuthSchemeAdapter,
    HttpBasicAuthScheme,
    ApiTokenAuthScheme,
    ApiHeadersAuthScheme,
    ApiQueryParamsAuthScheme,
    OAuth2ClientCredentialsAuthScheme,
    auth_scheme_from_route,
)

# Validate a dict into the right subclass:
scheme = AuthSchemeAdapter.validate_python({"type": "http-basic", "username": "u", "password": "p"})
assert isinstance(scheme, HttpBasicAuthScheme)

# Parse an existing Route's auth field:
route = await client.resources.routes.get("abc123uid12")
scheme = auth_scheme_from_route(route)
match scheme:
    case HttpBasicAuthScheme(username=u):      ...
    case ApiTokenAuthScheme(token=t):          ...
    case OAuth2ClientCredentialsAuthScheme():  ...
```

| `type` value | Class | Use for |
|---|---|---|
| `http-basic` | `HttpBasicAuthScheme` | `Authorization: Basic base64(u:p)` |
| `api-token` | `ApiTokenAuthScheme` | DHIS2-flavour static token — `Authorization: ApiToken <v>` (NOT standard `Bearer`, see BUGS.md #4e) |
| `api-headers` | `ApiHeadersAuthScheme` | Arbitrary custom headers map |
| `api-query-params` | `ApiQueryParamsAuthScheme` | Query-string param map |
| `oauth2-client-credentials` | `OAuth2ClientCredentialsAuthScheme` | Upstream OAuth2 client-credentials flow |

The generated `Route.auth` stays typed as `Any | None` because DHIS2's `/api/schemas` endpoint can't express polymorphic unions — the helper `auth_scheme_from_route(route)` narrows it.

## 3. Aggregate + Analytics read models

`dhis2w_client/aggregate.py`:

| Class | Endpoint | Shape |
|---|---|---|
| `DataValueSet` | `/api/dataValueSets` GET | `{dataSet, completeDate, period, orgUnit, dataValues: [DataValue]}` |
| `DataValue` | (inside DataValueSet) | `{dataElement, period, orgUnit, categoryOptionCombo, value, ...}` |

`dhis2w_client/analytics.py`:

| Class | Endpoint | Shape | Source |
|---|---|---|---|
| `Grid` | `/api/analytics*` envelope | `{headers: [GridHeader] \| None, rows: [[Any]] \| None, metaData: dict \| None, width, height, headerWidth, rowContext, …}` | OAS (`generated/v42/oas/grid.py`) |
| `GridHeader` | (column) | `{name, column, valueType, type, hidden, meta, legendSet, optionSet, programStage, stageOffset, repeatableStageParams}` | OAS (`generated/v42/oas/grid_header.py`) |
| `AnalyticsMetaData` | (parser helper over `Grid.metaData`) | `{items: dict, dimensions: dict[str, list[str]]}` | hand-written |

`analytics_service.query_analytics(...)` returns `Grid | DataValueSet` — the union reflects that `--shape dvs` (the `/api/analytics/dataValueSet.json` variant) returns a `DataValueSet` shape instead of the standard `headers + rows` envelope.

```python
response = await service.query_analytics(profile, shape="table", dimensions=[...])
match response:
    case Grid(rows=rows):  # standard / raw / events / enrollments / outlier
        for row in rows or []:
            ...
    case DataValueSet(dataValues=values):  # dvs
        for dv in values:
            ...
```

`Grid.metaData` is `dict[str, Any]` on the wire (dimension lookups + item descriptors keyed by UID). Callers that want the typed `{items, dimensions}` substructure lift it via `AnalyticsMetaData.model_validate(grid.metaData)`.

## 4. Tracker instance models

`/api/tracker/*` returns runtime instance data (enrollments, events, etc.), not metadata definitions — these shapes are in OpenAPI only. The OAS codegen emits the classes under `dhis2w_client.generated.v42.oas.*`; `dhis2w_client.generated.v42.tracker` is a shim that re-exports them (plus the hand-written `TrackerBundle` write envelope, which isn't in OpenAPI under that name):

| Class | Endpoint | Key fields |
|---|---|---|
| `TrackerTrackedEntity` | `/api/tracker/trackedEntities` | `trackedEntity`, `trackedEntityType`, `orgUnit`, `attributes`, `enrollments` |
| `TrackerEnrollment` | `/api/tracker/enrollments` | `enrollment`, `trackedEntity`, `program`, `status`, `events`, `attributes` |
| `TrackerEvent` | `/api/tracker/events` | `event`, `enrollment`, `program`, `programStage`, `orgUnit`, `status`, `dataValues` |
| `TrackerRelationship` | `/api/tracker/relationships` | `relationship`, `relationshipType`, `from_`, `to` |
| `TrackerBundle` | `POST /api/tracker` | `trackedEntities`, `enrollments`, `events`, `relationships` |

Nested value types — `TrackerAttribute`, `TrackerDataValue`, `TrackerNote`, `TrackerRelationshipItem` — are re-exported from the same module.

Status enums use `StrEnum` so they round-trip through JSON cleanly:

```python
from dhis2w_client.generated.v42.tracker import EnrollmentStatus, EventStatus

EnrollmentStatus.ACTIVE      # "ACTIVE"  -> "ACTIVE" in JSON
EventStatus("SCHEDULE")      # parses from DHIS2's wire value
```

### TrackedEntityType — metadata vs instance

A `TrackerTrackedEntity` carries `trackedEntityType: str | None` as a UID reference. The full TrackedEntityType metadata (name, description, per-type attributes like "Person" vs "Patient" vs "Lab Sample") is a metadata resource and lives under the generated `/api/schemas` codegen:

```python
entity = await client.resources.tracked_entity_types.get("tet01234567")
entity.name          # "Person", "Patient", ...
```

Join via `TrackerTrackedEntity.trackedEntityType` (UID) → `client.resources.tracked_entity_types.get(uid)`.

## Generated StrEnums (from `/api/schemas` CONSTANT properties)

Every CONSTANT property across every DHIS2 schema resolves to a `StrEnum` in `dhis2w_client.generated.v{N}.enums`:

```python
from dhis2w_client.generated.v42.enums import (
    AggregationType,
    DataElementDomain,
    PeriodType,
    ValueType,
)

AggregationType.SUM              # -> "SUM"
ValueType.INTEGER_ZERO_OR_POSITIVE  # -> "INTEGER_ZERO_OR_POSITIVE"
DataElementDomain("AGGREGATE")    # parses from DHIS2's wire value
```

The codegen dedupes by the DHIS2 Java class (`org.hisp.dhis.common.ValueType` etc.) so `ValueType` on `DataElement`, `Program`, `ProgramTrackedEntityAttribute`, and every other resource refers to the same enum class. Collision resolution (e.g. `org.hisp.dhis.event.EventStatus` vs `org.hisp.dhis.mapping.EventStatus`) prefixes the ambiguous class with the penultimate package segment.

Because `StrEnum` subclasses `str`, passing a bare string still validates: `DataElement(valueType="NUMBER")` works alongside `DataElement(valueType=ValueType.NUMBER)`.

## Why two codegen paths?

- **`/api/schemas` codegen** — generates the 100+ metadata resources (DataElement, DataSet, Program, …) plus their CONSTANT-property StrEnums. Output lands in `generated/v{N}/schemas/` + `generated/v{N}/enums.py` + `generated/v{N}/resources.py`. This is what `client.resources.data_elements.list()` returns.
- **`/api/openapi.json` codegen** — generates the instance-side shapes `/api/schemas` can't describe: `WebMessage` envelopes, tracker read/write models, `DataValue` / `DataValueSet`, auth-scheme leaves, data-integrity checks, `SystemInfo`. Output lands in `generated/v{N}/oas/`. Entry points: `d2w dev codegen oas-rebuild --version v{N}`.

The top-level domain modules (`dhis2w_client.v42.envelopes`, `.aggregate`, `.system`, `.maintenance`, `.auth_schemes`, `.generated.v42.tracker`) are thin shims over the OAS output. They add caller-friendly helpers (`WebMessageResponse.created_uid()`, `TrackerBundle`, the `AuthScheme` discriminated union) that OpenAPI doesn't express on its own.

Items that stay hand-written entirely: `Me` (not in OpenAPI), `PeriodType` (Java class hierarchy upstream, not an enum), and `analytics.py` (OpenAPI ships `Grid` / `GridHeader` / `GridResponse` which differ in shape from our current analytics accessors — a behaviour-changing migration left for a future touch).
