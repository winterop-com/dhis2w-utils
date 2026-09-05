"""Service layer for the `tracker` plugin — DHIS2 tracker API (/api/tracker/*).

Read paths return typed pydantic models from `dhis2w_client.generated.v42.tracker`:

  list_tracked_entities   -> list[TrackerTrackedEntity]
  get_tracked_entity      -> TrackerTrackedEntity
  list_enrollments        -> list[TrackerEnrollment]
  list_events             -> list[TrackerEvent]
  list_relationships      -> list[TrackerRelationship]

DHIS2 wraps each list in a domain envelope (`{pager, events: [...]}` etc.) —
the service unwraps it and returns the flat typed list. Callers that need
the `pager` block can call `list_raw` variants (not implemented yet).

Write paths return the typed `WebMessageResponse` envelope.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from dhis2w_client.generated.v42.tracker import (
    TrackerBundle,
    TrackerEnrollment,
    TrackerEvent,
    TrackerRelationship,
    TrackerTrackedEntity,
)
from dhis2w_client.v42 import EnrollResult, EventResult, OutstandingEnrollment, RegisterResult, WebMessageResponse
from dhis2w_client.v42.tracker import DateLike
from pydantic import BaseModel, ConfigDict

from dhis2w_core.profile import Profile
from dhis2w_core.v42.client_context import open_client

_DHIS2_UID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9]{10}$")


class TrackedEntityTypeSummary(BaseModel):
    """Picker-sized `{id, name, description}` projection of a TrackedEntityType.

    A deliberate projection of the generated `TrackedEntityType` schema: the listing and the
    name-to-UID lookup only ever request `fields=id,name,description`, and returning the full
    generated class would balloon the MCP tool's return schema for what is a picker listing.
    """

    model_config = ConfigDict(extra="allow")

    id: str
    name: str | None = None
    description: str | None = None


class _TrackedEntityTypeLookup(BaseModel):
    """`{trackedEntityTypes: [{id, name, ...}, ...]}` envelope from /api/trackedEntityTypes."""

    model_config = ConfigDict(extra="allow")

    trackedEntityTypes: list[TrackedEntityTypeSummary] = []


async def list_tracked_entity_types(profile: Profile) -> list[TrackedEntityTypeSummary]:
    """List every configured TrackedEntityType (id, name, description) via /api/trackedEntityTypes."""
    async with open_client(profile) as client:
        envelope = await client.get(
            "/api/trackedEntityTypes",
            model=_TrackedEntityTypeLookup,
            params={"fields": "id,name,description", "paging": "false"},
        )
    return envelope.trackedEntityTypes


async def resolve_tracked_entity_type(profile: Profile, name_or_uid: str) -> str:
    """Return the TrackedEntityType UID for a name or UID.

    If `name_or_uid` matches DHIS2's UID pattern (`[A-Za-z][A-Za-z0-9]{10}`)
    it's returned as-is. Otherwise the value is treated as a case-insensitive
    name + queried via `/api/trackedEntityTypes?filter=name:ilike:...&fields=id`.

    Raises `ValueError` if no matching type is found, or the name is ambiguous.
    """
    if _DHIS2_UID_RE.match(name_or_uid):
        return name_or_uid
    async with open_client(profile) as client:
        envelope = await client.get(
            "/api/trackedEntityTypes",
            model=_TrackedEntityTypeLookup,
            params={"filter": f"name:ilike:{name_or_uid}", "fields": "id,name"},
        )
    matches = envelope.trackedEntityTypes
    if not matches:
        raise ValueError(
            f"no TrackedEntityType matches name {name_or_uid!r} — run `d2w data tracker type` to see configured types"
        )
    if len(matches) > 1:
        names = [m.name for m in matches]
        raise ValueError(f"name {name_or_uid!r} is ambiguous — matches {names!r}. Pass the UID instead.")
    return str(matches[0].id)


class _TrackedEntitiesEnvelope(BaseModel):
    """`{pager, trackedEntities: [...]}` envelope returned by /api/tracker/trackedEntities."""

    model_config = ConfigDict(extra="allow")

    trackedEntities: list[TrackerTrackedEntity] = []


class _EnrollmentsEnvelope(BaseModel):
    """`{pager, enrollments: [...]}` envelope."""

    model_config = ConfigDict(extra="allow")

    enrollments: list[TrackerEnrollment] = []


class _EventsEnvelope(BaseModel):
    """`{pager, events: [...]}` envelope."""

    model_config = ConfigDict(extra="allow")

    events: list[TrackerEvent] = []


class _RelationshipsEnvelope(BaseModel):
    """`{pager, relationships: [...]}` envelope returned by /api/tracker/relationships."""

    model_config = ConfigDict(extra="allow")

    relationships: list[TrackerRelationship] = []


async def list_tracked_entities(
    profile: Profile,
    *,
    program: str | None = None,
    tracked_entity_type: str | None = None,
    tracked_entities: str | None = None,
    org_unit: str | None = None,
    ou_mode: str = "DESCENDANTS",
    fields: str | None = None,
    filter: str | None = None,
    page_size: int = 50,
    page: int | None = None,
    updated_after: str | None = None,
) -> list[TrackerTrackedEntity]:
    """List tracked entities via GET /api/tracker/trackedEntities.

    At minimum, supply one of `program`, `tracked_entity_type`, or
    `tracked_entities` (comma-separated UIDs). `program` must point at a
    tracker program (programType=WITH_REGISTRATION).
    """
    params: dict[str, Any] = {"ouMode": ou_mode, "pageSize": page_size}
    if program is not None:
        params["program"] = program
    if tracked_entity_type is not None:
        params["trackedEntityType"] = tracked_entity_type
    if tracked_entities is not None:
        params["trackedEntities"] = tracked_entities
    if org_unit is not None:
        params["orgUnit"] = org_unit
    if fields is not None:
        params["fields"] = fields
    if filter is not None:
        params["filter"] = filter
    if page is not None:
        params["page"] = page
    if updated_after is not None:
        params["updatedAfter"] = updated_after

    async with open_client(profile) as client:
        raw = await client.get_raw("/api/tracker/trackedEntities", params=params)
    return _TrackedEntitiesEnvelope.model_validate(raw).trackedEntities


async def get_tracked_entity(
    profile: Profile,
    uid: str,
    *,
    program: str | None = None,
    fields: str | None = None,
) -> TrackerTrackedEntity:
    """Fetch one tracked entity by UID via GET /api/tracker/trackedEntities/{uid}."""
    params: dict[str, Any] = {}
    if program is not None:
        params["program"] = program
    if fields is not None:
        params["fields"] = fields
    async with open_client(profile) as client:
        raw = await client.get_raw(f"/api/tracker/trackedEntities/{uid}", params=params)
    return TrackerTrackedEntity.model_validate(raw)


async def list_enrollments(
    profile: Profile,
    *,
    program: str | None = None,
    org_unit: str | None = None,
    ou_mode: str = "DESCENDANTS",
    tracked_entity: str | None = None,
    status: str | None = None,
    fields: str | None = None,
    page_size: int = 50,
    page: int | None = None,
    updated_after: str | None = None,
) -> list[TrackerEnrollment]:
    """List enrollments via GET /api/tracker/enrollments (tracker programs only)."""
    params: dict[str, Any] = {"ouMode": ou_mode, "pageSize": page_size}
    if program is not None:
        params["program"] = program
    if org_unit is not None:
        params["orgUnit"] = org_unit
    if tracked_entity is not None:
        params["trackedEntity"] = tracked_entity
    if status is not None:
        params["status"] = status
    if fields is not None:
        params["fields"] = fields
    if page is not None:
        params["page"] = page
    if updated_after is not None:
        params["updatedAfter"] = updated_after

    async with open_client(profile) as client:
        raw = await client.get_raw("/api/tracker/enrollments", params=params)
    return _EnrollmentsEnvelope.model_validate(raw).enrollments


async def list_events(
    profile: Profile,
    *,
    program: str | None = None,
    program_stage: str | None = None,
    org_unit: str | None = None,
    ou_mode: str = "DESCENDANTS",
    tracked_entity: str | None = None,
    enrollment: str | None = None,
    status: str | None = None,
    occurred_after: str | None = None,
    occurred_before: str | None = None,
    fields: str | None = None,
    page_size: int = 50,
    page: int | None = None,
) -> list[TrackerEvent]:
    """List events via GET /api/tracker/events.

    Works with both event programs (no registration) and tracker programs. The endpoint
    spells its two entity filters inconsistently: `trackedEntity` is singular and
    `enrollments` is plural, and the other spelling of each is accepted and silently
    dropped, so a wrong one returns the whole program (BUGS.md #91). The
    organisation unit mode rides `orgUnitMode`: on DHIS2 2.42 and 2.43 this
    endpoint reads only that key, where the tracked entity and enrollment reads
    only read `ouMode` (BUGS.md #113).
    """
    params: dict[str, Any] = {"orgUnitMode": ou_mode, "pageSize": page_size}
    for key, value in (
        ("program", program),
        ("programStage", program_stage),
        ("orgUnit", org_unit),
        ("trackedEntity", tracked_entity),
        ("enrollments", enrollment),
        ("status", status),
        ("occurredAfter", occurred_after),
        ("occurredBefore", occurred_before),
        ("fields", fields),
        ("page", page),
    ):
        if value is not None:
            params[key] = value

    async with open_client(profile) as client:
        raw = await client.get_raw("/api/tracker/events", params=params)
    return _EventsEnvelope.model_validate(raw).events


async def list_relationships(
    profile: Profile,
    *,
    tracked_entity: str | None = None,
    enrollment: str | None = None,
    event: str | None = None,
    fields: str | None = None,
    page_size: int = 50,
) -> list[TrackerRelationship]:
    """List relationships via GET /api/tracker/relationships.

    One of `tracked_entity`, `enrollment`, or `event` is required to scope the
    query (DHIS2 does not support an unscoped relationship listing).
    """
    params: dict[str, Any] = {"pageSize": page_size}
    for key, value in (
        ("trackedEntity", tracked_entity),
        ("enrollment", enrollment),
        ("event", event),
        ("fields", fields),
    ):
        if value is not None:
            params[key] = value
    async with open_client(profile) as client:
        raw = await client.get_raw("/api/tracker/relationships", params=params)
    return _RelationshipsEnvelope.model_validate(raw).relationships


async def push_tracker(
    profile: Profile,
    bundle: TrackerBundle,
    *,
    import_strategy: str | None = None,
    atomic_mode: str | None = None,
    dry_run: bool = False,
    async_mode: bool = False,
) -> WebMessageResponse:
    """Bulk import via POST /api/tracker with a typed `TrackerBundle` of tracker objects.

    The bundle carries `trackedEntities` / `enrollments` / `events` /
    `relationships` lists; empty lists are dropped from the wire payload so
    the request body names only the object kinds actually pushed.
    `import_strategy` is one of `CREATE`, `UPDATE`, `CREATE_AND_UPDATE`,
    `DELETE`. `atomic_mode` is `ALL` or `OBJECT`. `dry_run=True` sends
    `importMode=VALIDATE` so DHIS2 runs the full import pipeline and reports
    per-object errors without committing anything. The push runs synchronously
    (`async=false`) by default so those per-object errors surface inline on the
    returned `WebMessageResponse`; `async_mode=True` sends `async=true` to
    return a job reference immediately (response.id = the job UID to poll).
    """
    params: dict[str, Any] = {}
    if import_strategy is not None:
        params["importStrategy"] = import_strategy
    if atomic_mode is not None:
        params["atomicMode"] = atomic_mode
    if dry_run:
        params["importMode"] = "VALIDATE"
    params["async"] = "true" if async_mode else "false"

    body = {
        key: value
        for key, value in bundle.model_dump(by_alias=True, exclude_none=True, mode="json").items()
        if value != []
    }
    async with open_client(profile) as client:
        return await client.post("/api/tracker", body, params=params, model=WebMessageResponse)


_TRACKER_ID_FIELD = {"trackedEntities": "trackedEntity", "enrollments": "enrollment", "events": "event"}


async def delete_tracker_objects(
    profile: Profile,
    *,
    kind: str,
    uids: list[str],
    atomic_mode: str | None = None,
    async_mode: bool = False,
) -> WebMessageResponse:
    """Delete tracker objects by UID (kind = trackedEntities | enrollments | events) via importStrategy=DELETE.

    Builds the minimal `{<kind>: [{<idField>: uid}, ...]}` bundle and pushes it with DELETE.
    Deleting a tracked entity cascades to its enrollments and events.
    """
    id_field = _TRACKER_ID_FIELD.get(kind)
    if id_field is None:
        raise ValueError(f"unknown tracker kind {kind!r}; expected one of: {', '.join(sorted(_TRACKER_ID_FIELD))}")
    bundle = TrackerBundle.model_validate({kind: [{id_field: uid} for uid in uids]})
    return await push_tracker(profile, bundle, import_strategy="DELETE", atomic_mode=atomic_mode, async_mode=async_mode)


async def register_tracked_entity(
    profile: Profile,
    *,
    program: str,
    org_unit: str,
    tracked_entity_type: str,
    attributes: dict[str, str] | None = None,
    enrolled_at: DateLike | None = None,
    occurred_at: DateLike | None = None,
    events: list[Mapping[str, Any]] | None = None,
    import_strategy: str = "CREATE_AND_UPDATE",
) -> RegisterResult:
    """Register a tracked entity + enroll in one program via `client.tracker.register`."""
    async with open_client(profile) as client:
        return await client.tracker.register(
            program=program,
            org_unit=org_unit,
            tracked_entity_type=tracked_entity_type,
            attributes=attributes,
            enrolled_at=enrolled_at,
            occurred_at=occurred_at,
            events=events,
            import_strategy=import_strategy,
        )


async def enroll_tracked_entity(
    profile: Profile,
    *,
    tracked_entity: str,
    program: str,
    org_unit: str,
    enrolled_at: DateLike | None = None,
    occurred_at: DateLike | None = None,
    import_strategy: str = "CREATE_AND_UPDATE",
) -> EnrollResult:
    """Add an enrollment to an existing tracked entity via `client.tracker.enroll`."""
    async with open_client(profile) as client:
        return await client.tracker.enroll(
            tracked_entity=tracked_entity,
            program=program,
            org_unit=org_unit,
            enrolled_at=enrolled_at,
            occurred_at=occurred_at,
            import_strategy=import_strategy,
        )


async def add_tracker_event(
    profile: Profile,
    *,
    program: str,
    program_stage: str,
    org_unit: str,
    enrollment: str | None = None,
    tracked_entity: str | None = None,
    data_values: dict[str, str] | None = None,
    occurred_at: DateLike | None = None,
    import_strategy: str = "CREATE_AND_UPDATE",
) -> EventResult:
    """Add one event — tracker (with enrollment) or event-only (standalone)."""
    async with open_client(profile) as client:
        return await client.tracker.add_event(
            enrollment=enrollment,
            program=program,
            program_stage=program_stage,
            org_unit=org_unit,
            tracked_entity=tracked_entity,
            data_values=data_values,
            occurred_at=occurred_at,
            import_strategy=import_strategy,
        )


async def outstanding_enrollments(
    profile: Profile,
    program: str,
    *,
    org_unit: str | None = None,
    ou_mode: str = "DESCENDANTS",
    page_size: int = 200,
) -> list[OutstandingEnrollment]:
    """List ACTIVE enrollments missing events on any non-repeatable stage."""
    async with open_client(profile) as client:
        return await client.tracker.outstanding(
            program,
            org_unit=org_unit,
            ou_mode=ou_mode,
            page_size=page_size,
        )
