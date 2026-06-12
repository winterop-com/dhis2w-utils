# OpenAPI-derived models

Everything `/api/openapi.json#/components/schemas` describes, emitted as pydantic + `StrEnum` by the OAS codegen. v42 ships **562 classes + 260 StrEnums + 104 scalar aliases** under `dhis2w_client.generated.v42.oas`.

Most callers reach these models indirectly — the domain shims re-export the relevant slices:

- `dhis2w_client.v42.envelopes` — `WebMessage` (as `WebMessageResponse` subclass), `ImportReport`, `ObjectReport`, `TypeReport`, `Stats`, `ErrorReport`, `ImportCount`, `ImportConflict` (as `Conflict`).
- `dhis2w_client.v42.aggregate` — `DataValue`, `DataValueSet`.
- `dhis2w_client.v42.system` — `SystemInfo`.
- `dhis2w_client.v42.maintenance` — `DataIntegrityCheck`, `DataIntegrityIssue`.
- `dhis2w_client.v42.auth_schemes` — the 5 `*AuthScheme` leaves (each subclassed to add the `type` discriminator).
- `dhis2w_client.generated.v42.tracker` — `TrackerTrackedEntity`, `TrackerEnrollment`, `TrackerEvent`, `TrackerRelationship`, `TrackerRelationshipItem`, `TrackerDataValue`, `TrackerAttribute`, `TrackerNote`, plus `EnrollmentStatus` / `EventStatus`.

Import directly from the OAS module when you need a shape the shims don't expose — e.g. `TrackerImportReport`, `Grid`, `AppIcons`, any of the 400+ admin-parameters / dimension-item / filter-wrapper schemas:

```python
from dhis2w_client.generated.v42.oas import TrackerImportReport, Grid

report = TrackerImportReport.model_validate(raw)
grid = Grid.model_validate(analytics_response)
```

Regeneration (from the committed `openapi.json`, no network):

```bash
uv run d2w dev codegen oas-rebuild --version v42
```

See [Codegen](../codegen.md) for emitter specifics — every-field-optional rule, the `_MAX_CLOSED_ENUM_SIZE` threshold that demotes 488-member `ErrorCode` to a `str` alias, the `DHIS2Warning` builtin-shadow rename, the `_types_namespace` injection trick that resolves sibling references without cycles.

The `__all__` list on `dhis2w_client.generated.v42.oas` holds every emitted symbol.
