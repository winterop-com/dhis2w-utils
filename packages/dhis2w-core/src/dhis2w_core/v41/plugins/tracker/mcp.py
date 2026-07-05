"""FastMCP tools for the tracker domain — registered under `data_tracker_*`."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from dhis2w_client.generated.v41.tracker import (
    TrackerBundle,
    TrackerEnrollment,
    TrackerEvent,
    TrackerRelationship,
    TrackerTrackedEntity,
)
from dhis2w_client.v41 import WebMessageResponse

from dhis2w_core.profile import resolve_profile
from dhis2w_core.v41.plugins.tracker import service
from dhis2w_core.v41.plugins.tracker.service import TrackedEntityTypeSummary


def register(mcp: Any) -> None:
    """Register tracker tools (entity/enrollment/event/relationship + bulk push)."""

    @mcp.tool()
    async def data_tracker_list(
        type: str,
        program: str | None = None,
        tracked_entities: str | None = None,
        org_unit: str | None = None,
        ou_mode: str = "DESCENDANTS",
        fields: str | None = None,
        filter: str | None = None,
        page_size: int = 50,
        page: int | None = None,
        updated_after: str | None = None,
        profile: str | None = None,
    ) -> list[TrackerTrackedEntity]:
        """List tracked entities of the given TrackedEntityType.

        `type` is a TrackedEntityType name (case-insensitive) or UID — e.g.
        `"Person"`, `"Patient"`, or `"tet01234567"`. Names are resolved
        server-side via `/api/trackedEntityTypes?filter=name:ilike:...`.

        Optional scoping: `program` (tracker program UID), `tracked_entities`
        (comma-separated UIDs to fetch specific entities directly),
        `org_unit` + `ou_mode` (SELECTED/CHILDREN/DESCENDANTS/ACCESSIBLE/CAPTURE/ALL).
        `filter` follows DHIS2's `uid:operator:value` syntax.
        """
        tet_uid = await service.resolve_tracked_entity_type(resolve_profile(profile), type)
        return await service.list_tracked_entities(
            resolve_profile(profile),
            program=program,
            tracked_entity_type=tet_uid,
            tracked_entities=tracked_entities,
            org_unit=org_unit,
            ou_mode=ou_mode,
            fields=fields,
            filter=filter,
            page_size=page_size,
            page=page,
            updated_after=updated_after,
        )

    @mcp.tool()
    async def data_tracker_get(
        uid: str,
        program: str | None = None,
        fields: str | None = None,
        profile: str | None = None,
    ) -> TrackerTrackedEntity:
        """Fetch one tracked entity by UID (TrackedEntityType inferred from the entity)."""
        return await service.get_tracked_entity(resolve_profile(profile), uid, program=program, fields=fields)

    @mcp.tool()
    async def data_tracker_type_list(profile: str | None = None) -> list[TrackedEntityTypeSummary]:
        """List every TrackedEntityType configured on the connected instance.

        Each entry has `id`, `name`, and `description`. Useful for picking the
        right `type` argument before calling `data_tracker_list`.
        """
        return await service.list_tracked_entity_types(resolve_profile(profile))

    @mcp.tool()
    async def data_tracker_enrollment_list(
        program: str | None = None,
        org_unit: str | None = None,
        ou_mode: str = "DESCENDANTS",
        tracked_entity: str | None = None,
        status: str | None = None,
        fields: str | None = None,
        page_size: int = 50,
        page: int | None = None,
        updated_after: str | None = None,
        profile: str | None = None,
    ) -> list[TrackerEnrollment]:
        """List DHIS2 tracker enrollments.

        `status` filter values: ACTIVE, COMPLETED, CANCELLED. Tracker
        programs only (event programs have no enrollments).
        """
        return await service.list_enrollments(
            resolve_profile(profile),
            program=program,
            org_unit=org_unit,
            ou_mode=ou_mode,
            tracked_entity=tracked_entity,
            status=status,
            fields=fields,
            page_size=page_size,
            page=page,
            updated_after=updated_after,
        )

    @mcp.tool()
    async def data_tracker_event_list(
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
        profile: str | None = None,
    ) -> list[TrackerEvent]:
        """List DHIS2 tracker events.

        Works for both event programs (no registration) and tracker programs.
        `status` values: ACTIVE, COMPLETED, VISITED, SCHEDULE, OVERDUE, SKIPPED.
        Date filters are ISO YYYY-MM-DD.
        """
        return await service.list_events(
            resolve_profile(profile),
            program=program,
            program_stage=program_stage,
            org_unit=org_unit,
            ou_mode=ou_mode,
            tracked_entity=tracked_entity,
            enrollment=enrollment,
            status=status,
            occurred_after=occurred_after,
            occurred_before=occurred_before,
            fields=fields,
            page_size=page_size,
            page=page,
        )

    @mcp.tool()
    async def data_tracker_relationship_list(
        tracked_entity: str | None = None,
        enrollment: str | None = None,
        event: str | None = None,
        fields: str | None = None,
        page_size: int = 50,
        profile: str | None = None,
    ) -> list[TrackerRelationship]:
        """List DHIS2 relationships (one of tracked_entity/enrollment/event required)."""
        return await service.list_relationships(
            resolve_profile(profile),
            tracked_entity=tracked_entity,
            enrollment=enrollment,
            event=event,
            fields=fields,
            page_size=page_size,
        )

    @mcp.tool()
    async def data_tracker_push(
        bundle: dict[str, Any],
        import_strategy: str | None = None,
        atomic_mode: str | None = None,
        dry_run: bool = False,
        async_mode: bool = False,
        profile: str | None = None,
    ) -> WebMessageResponse:
        """Bulk import a tracker bundle via POST /api/tracker.

        The `bundle` envelope shape:
          {"trackedEntities": [...], "enrollments": [...], "events": [...], "relationships": [...]}
        Any key may be omitted. `import_strategy` options: CREATE, UPDATE,
        CREATE_AND_UPDATE, DELETE. `atomic_mode` options: ALL, OBJECT.
        `dry_run=True` validates without writing. `async_mode=True` returns a
        job reference immediately.
        """
        return await service.push_tracker(
            resolve_profile(profile),
            TrackerBundle.model_validate(bundle),
            import_strategy=import_strategy,
            atomic_mode=atomic_mode,
            dry_run=dry_run,
            async_mode=async_mode,
        )

    @mcp.tool()
    async def data_tracker_register(
        program: str,
        org_unit: str,
        tracked_entity_type: str,
        attributes: dict[str, str] | None = None,
        enrolled_at: str | None = None,
        events: list[Mapping[str, Any]] | None = None,
        profile: str | None = None,
    ) -> dict[str, Any]:
        """Register a tracked entity + enroll in one program via POST /api/tracker.

        `attributes` maps TrackedEntityAttribute UID -> value. `events`
        optional list of `{"program_stage": uid, "org_unit": uid?,
        "occurred_at": date?, "data_values": {de_uid: value, ...}}`.
        Returns `{tracked_entity, enrollment, events, response}` — the new
        UIDs are assigned client-side and surfaced for downstream reference.
        """
        result = await service.register_tracked_entity(
            resolve_profile(profile),
            program=program,
            org_unit=org_unit,
            tracked_entity_type=tracked_entity_type,
            attributes=attributes,
            enrolled_at=enrolled_at,
            events=events,
        )
        return result.model_dump()

    @mcp.tool()
    async def data_tracker_enroll(
        tracked_entity: str,
        program: str,
        org_unit: str,
        enrolled_at: str | None = None,
        profile: str | None = None,
    ) -> dict[str, Any]:
        """Add an enrollment to an existing tracked entity."""
        result = await service.enroll_tracked_entity(
            resolve_profile(profile),
            tracked_entity=tracked_entity,
            program=program,
            org_unit=org_unit,
            enrolled_at=enrolled_at,
        )
        return result.model_dump()

    @mcp.tool()
    async def data_tracker_event_create(
        program: str,
        program_stage: str,
        org_unit: str,
        enrollment: str | None = None,
        tracked_entity: str | None = None,
        data_values: dict[str, str] | None = None,
        occurred_at: str | None = None,
        profile: str | None = None,
    ) -> dict[str, Any]:
        """Add one event — tracker (with enrollment) or event-only (standalone).

        Pass `enrollment` for WITH_REGISTRATION programs. Omit it for
        WITHOUT_REGISTRATION programs (community surveys, case-investigation
        forms, one-shot data collection not bound to a registered patient).
        """
        result = await service.add_tracker_event(
            resolve_profile(profile),
            program=program,
            program_stage=program_stage,
            org_unit=org_unit,
            enrollment=enrollment,
            tracked_entity=tracked_entity,
            data_values=data_values,
            occurred_at=occurred_at,
        )
        return result.model_dump()

    @mcp.tool()
    async def data_tracker_outstanding(
        program: str,
        org_unit: str | None = None,
        ou_mode: str = "DESCENDANTS",
        page_size: int = 200,
        profile: str | None = None,
    ) -> list[dict[str, Any]]:
        """List ACTIVE enrollments missing events on any non-repeatable stage.

        "What's due" report: one row per enrollment with its
        tracked-entity, org unit, and the list of missing program-stage
        UIDs. Repeatable stages are excluded — their `due` semantic
        isn't single-valued.
        """
        rows = await service.outstanding_enrollments(
            resolve_profile(profile),
            program,
            org_unit=org_unit,
            ou_mode=ou_mode,
            page_size=page_size,
        )
        return [r.model_dump() for r in rows]
