"""Typer sub-app for the tracker domain (mounted under `d2w data tracker`).

Tracked-entity listing keys on the TrackedEntityType — the `<type>` positional
on `list` + `get` accepts a TET name (case-insensitive) or UID directly. Names
are resolved server-side via `/api/trackedEntityTypes?filter=name:ilike:...`.

Every list/get command prints a concise Rich summary by default. Pass
`--json` to get the raw payload (useful for scripting + debugging).
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Annotated, Any

import typer
from pydantic import BaseModel

from dhis2w_core.profile import profile_from_env
from dhis2w_core.v41.cli_output import (
    ColumnSpec,
    DetailRow,
    format_reflist,
    is_json_output,
    render_detail,
    render_list,
)

app = typer.Typer(
    help="DHIS2 tracker — tracked entities by type, enrollments, events, relationships.",
    no_args_is_help=True,
)
enrollment_app = typer.Typer(help="Enrollments.", no_args_is_help=True)
event_app = typer.Typer(help="Events.", no_args_is_help=True)
relationship_app = typer.Typer(help="Relationships.", no_args_is_help=True)
app.add_typer(enrollment_app, name="enrollment")
app.add_typer(event_app, name="event")
app.add_typer(relationship_app, name="relationship")


def _as_json(items: Any) -> None:
    """Emit models or dicts as JSON for `--json` debug output."""
    if isinstance(items, BaseModel):
        typer.echo(items.model_dump_json(indent=2, exclude_none=True))
        return
    if isinstance(items, list) and items and isinstance(items[0], BaseModel):
        typer.echo(json.dumps([m.model_dump(exclude_none=True, mode="json") for m in items], indent=2, default=str))
        return
    typer.echo(json.dumps(items, indent=2, default=str))


def _attr_value(entity: Any, attribute_uid: str) -> str | None:
    """Pluck a single TrackerAttribute value off a TrackerTrackedEntity."""
    for attr in entity.attributes or []:
        if getattr(attr, "attribute", None) == attribute_uid:
            return getattr(attr, "value", None)
    return None


@app.command("list")
@app.command("ls", hidden=True)
def list_command(
    type: Annotated[
        str | None,
        typer.Argument(
            help="TrackedEntityType name (case-insensitive) or UID — e.g. 'Person' or 'tet01234567'. "
            "Give this OR --program (not both).",
        ),
    ] = None,
    program: Annotated[
        str | None,
        typer.Option(
            "--program",
            help="Program UID — list the program's tracked entities. Alternative to TYPE; "
            "DHIS2 rejects a program and a TrackedEntityType together.",
        ),
    ] = None,
    tracked_entities: Annotated[
        str | None,
        typer.Option("--te-uids", help="Comma-separated tracked-entity UIDs to fetch directly."),
    ] = None,
    org_unit: Annotated[
        str | None, typer.Option("--org-unit", "--ou", help="OrganisationUnit UID to scope the listing.")
    ] = None,
    ou_mode: Annotated[
        str,
        typer.Option(
            "--ou-mode",
            help="Org-unit scope: SELECTED | CHILDREN | DESCENDANTS | ACCESSIBLE | ALL (default DESCENDANTS).",
        ),
    ] = "DESCENDANTS",
    fields: Annotated[
        str | None, typer.Option("--fields", help="DHIS2 field selector (comma-separated; nest with []).")
    ] = None,
    filter: Annotated[
        str | None, typer.Option("--filter", help="Attribute filter 'ATTR_UID:op:value' (repeatable).")
    ] = None,
    page_size: Annotated[int, typer.Option("--page-size")] = 50,
    page: Annotated[int | None, typer.Option("--page", help="1-based page number.")] = None,
    updated_after: Annotated[
        str | None,
        typer.Option("--updated-after", help="ISO-8601 cutoff — only entities updated after this."),
    ] = None,
) -> None:
    """List tracked entities by TrackedEntityType (TYPE) or by --program — give exactly one.

    Example: d2w data tracker list Person --ou ImspTQPwCqd
    """
    from dhis2w_core.v41.plugins.tracker import service

    if (type is None) == (program is None):
        typer.secho(
            "error: give either a TrackedEntityType (TYPE) or --program, not both", err=True, fg=typer.colors.RED
        )
        raise typer.Exit(2)
    tet_uid: str | None = None
    if type is not None:
        try:
            tet_uid = asyncio.run(service.resolve_tracked_entity_type(profile_from_env(), type))
        except ValueError as exc:
            typer.secho(f"error: {exc}", err=True, fg=typer.colors.RED)
            raise typer.Exit(1) from exc
    entities = asyncio.run(
        service.list_tracked_entities(
            profile_from_env(),
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
    )
    if is_json_output():
        _as_json(entities)
        return
    rows = [e.model_dump(by_alias=True, exclude_none=True, mode="json") for e in entities]
    render_list(
        f"tracked entities ({'program=' + program if program else 'type=' + str(type)})",
        rows,
        [
            ColumnSpec("id", "trackedEntity", style="cyan", no_wrap=True),
            ColumnSpec("orgUnit", "orgUnit"),
            ColumnSpec("enrollments", "enrollments", formatter=lambda v: str(len(v or []))),
            ColumnSpec("attributes", "attributes", formatter=lambda v: str(len(v or []))),
            ColumnSpec("updatedAt", "updatedAt", style="dim"),
        ],
    )


@app.command("get")
def get_command(
    uid: Annotated[str, typer.Argument(help="Tracked entity UID.")],
    program: Annotated[str | None, typer.Option("--program", help="Program UID.")] = None,
    fields: Annotated[
        str | None, typer.Option("--fields", help="DHIS2 field selector (comma-separated; nest with []).")
    ] = None,
) -> None:
    """Fetch one tracked entity by UID (TrackedEntityType inferred from the entity)."""
    from dhis2w_core.v41.plugins.tracker import service

    entity = asyncio.run(service.get_tracked_entity(profile_from_env(), uid, program=program, fields=fields))
    if is_json_output():
        _as_json(entity)
        return
    attrs = entity.attributes or []
    attrs_lines = [f"{getattr(a, 'displayName', None) or a.attribute}: {a.value}" for a in attrs if a.value]
    enrollments = entity.enrollments or []
    rows = [
        DetailRow("trackedEntity", str(entity.trackedEntity or uid)),
        DetailRow("trackedEntityType", str(entity.trackedEntityType or "-")),
        DetailRow("orgUnit", str(entity.orgUnit or "-")),
        DetailRow("inactive", "yes" if entity.inactive else "no"),
        DetailRow("deleted", "yes" if entity.deleted else "no"),
        DetailRow("createdAt", str(entity.createdAt or "-")),
        DetailRow("updatedAt", str(entity.updatedAt or "-")),
        DetailRow(f"attributes ({len(attrs)})", "\n".join(attrs_lines) or "-"),
        DetailRow(f"enrollments ({len(enrollments)})", format_reflist(enrollments)),
    ]
    render_detail(f"tracked entity {entity.trackedEntity or uid}", rows)


@enrollment_app.command("list")
@enrollment_app.command("ls", hidden=True)
def enrollment_list_command(
    program: Annotated[str | None, typer.Option("--program", help="Program UID.")] = None,
    org_unit: Annotated[
        str | None, typer.Option("--org-unit", "--ou", help="OrganisationUnit UID to scope the listing.")
    ] = None,
    ou_mode: Annotated[
        str,
        typer.Option(
            "--ou-mode",
            help="Org-unit scope: SELECTED | CHILDREN | DESCENDANTS | ACCESSIBLE | ALL (default DESCENDANTS).",
        ),
    ] = "DESCENDANTS",
    tracked_entity: Annotated[str | None, typer.Option("--te", help="TrackedEntity UID.")] = None,
    status: Annotated[str | None, typer.Option("--status", help="ACTIVE | COMPLETED | CANCELLED")] = None,
    fields: Annotated[
        str | None, typer.Option("--fields", help="DHIS2 field selector (comma-separated; nest with []).")
    ] = None,
    page_size: Annotated[int, typer.Option("--page-size")] = 50,
    page: Annotated[int | None, typer.Option("--page")] = None,
    updated_after: Annotated[str | None, typer.Option("--updated-after")] = None,
) -> None:
    """List enrollments (tracker programs only)."""
    from dhis2w_core.v41.plugins.tracker import service

    enrollments = asyncio.run(
        service.list_enrollments(
            profile_from_env(),
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
    )
    if is_json_output():
        _as_json(enrollments)
        return
    rows = [e.model_dump(by_alias=True, exclude_none=True, mode="json") for e in enrollments]
    render_list(
        "enrollments",
        rows,
        [
            ColumnSpec("id", "enrollment", style="cyan", no_wrap=True),
            ColumnSpec("program", "program"),
            ColumnSpec("orgUnit", "orgUnit"),
            ColumnSpec("status", "status"),
            ColumnSpec("enrolledAt", "enrolledAt", style="dim"),
        ],
    )


@event_app.command("list")
@event_app.command("ls", hidden=True)
def event_list_command(
    program: Annotated[str | None, typer.Option("--program", help="Program UID.")] = None,
    program_stage: Annotated[
        str | None, typer.Option("--program-stage", help="ProgramStage UID to narrow to one stage.")
    ] = None,
    org_unit: Annotated[
        str | None, typer.Option("--org-unit", "--ou", help="OrganisationUnit UID to scope the listing.")
    ] = None,
    ou_mode: Annotated[
        str,
        typer.Option(
            "--ou-mode",
            help="Org-unit scope: SELECTED | CHILDREN | DESCENDANTS | ACCESSIBLE | ALL (default DESCENDANTS).",
        ),
    ] = "DESCENDANTS",
    tracked_entity: Annotated[str | None, typer.Option("--te", help="TrackedEntity UID.")] = None,
    enrollment: Annotated[str | None, typer.Option("--enrollment", help="Enrollment UID to list its events.")] = None,
    status: Annotated[
        str | None,
        typer.Option("--status", help="Event status: ACTIVE | COMPLETED | VISITED | SCHEDULE | OVERDUE | SKIPPED."),
    ] = None,
    occurred_after: Annotated[
        str | None, typer.Option("--after", help="Only events on/after this ISO date (YYYY-MM-DD).")
    ] = None,
    occurred_before: Annotated[
        str | None, typer.Option("--before", help="Only events on/before this ISO date (YYYY-MM-DD).")
    ] = None,
    fields: Annotated[
        str | None, typer.Option("--fields", help="DHIS2 field selector (comma-separated; nest with []).")
    ] = None,
    page_size: Annotated[int, typer.Option("--page-size")] = 50,
    page: Annotated[int | None, typer.Option("--page")] = None,
) -> None:
    """List events (event and tracker programs). Scope with --program and/or --org-unit.

    Example: data tracker event list --program <programUID> --ou <ouUID>
    """
    from dhis2w_core.v41.plugins.tracker import service

    events = asyncio.run(
        service.list_events(
            profile_from_env(),
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
    )
    if is_json_output():
        _as_json(events)
        return
    rows = [e.model_dump(by_alias=True, exclude_none=True, mode="json") for e in events]
    render_list(
        "events",
        rows,
        [
            ColumnSpec("id", "event", style="cyan", no_wrap=True),
            ColumnSpec("program", "program"),
            ColumnSpec("stage", "programStage"),
            ColumnSpec("orgUnit", "orgUnit"),
            ColumnSpec("status", "status"),
            ColumnSpec("occurredAt", "occurredAt", style="dim"),
            ColumnSpec("dataValues", "dataValues", formatter=lambda v: str(len(v or []))),
        ],
    )


@relationship_app.command("list")
@relationship_app.command("ls", hidden=True)
def relationship_list_command(
    tracked_entity: Annotated[str | None, typer.Option("--te", help="TrackedEntity UID.")] = None,
    enrollment: Annotated[str | None, typer.Option("--enrollment", help="Enrollment UID to list its events.")] = None,
    event: Annotated[str | None, typer.Option("--event")] = None,
    fields: Annotated[
        str | None, typer.Option("--fields", help="DHIS2 field selector (comma-separated; nest with []).")
    ] = None,
    page_size: Annotated[int, typer.Option("--page-size")] = 50,
) -> None:
    """List relationships (one of --te/--enrollment/--event required)."""
    from dhis2w_core.v41.plugins.tracker import service

    relationships = asyncio.run(
        service.list_relationships(
            profile_from_env(),
            tracked_entity=tracked_entity,
            enrollment=enrollment,
            event=event,
            fields=fields,
            page_size=page_size,
        )
    )
    if is_json_output():
        _as_json(relationships)
        return
    rows = [r.model_dump(by_alias=True, exclude_none=True, mode="json") for r in relationships]
    render_list(
        "relationships",
        rows,
        [
            ColumnSpec("id", "relationship", style="cyan", no_wrap=True),
            ColumnSpec("type", "relationshipType"),
            ColumnSpec("bidirectional", "bidirectional"),
            ColumnSpec("createdAt", "createdAt", style="dim"),
        ],
    )


@app.command("type")
def type_list_command() -> None:
    """List every configured TrackedEntityType on the connected instance (name + UID).

    The `list` and `get` commands accept either a name or a UID in their `<type>`
    positional — run this first to see what's configured.
    """

    async def _fetch() -> list[dict[str, Any]]:
        from dhis2w_core.v41.client_context import open_client

        async with open_client(profile_from_env()) as client:
            response = await client.get_raw(
                "/api/trackedEntityTypes",
                params={"fields": "id,name,description", "paging": "false"},
            )
        items = response.get("trackedEntityTypes", [])
        assert isinstance(items, list)
        return items

    types = asyncio.run(_fetch())
    if is_json_output():
        typer.echo(json.dumps(types, indent=2))
        return
    if not types:
        typer.echo("(no TrackedEntityTypes configured on this instance)")
        return
    render_list(
        "TrackedEntityTypes",
        types,
        [
            ColumnSpec("id", "id", style="cyan", no_wrap=True),
            ColumnSpec("name", "name"),
            ColumnSpec("description", "description", formatter=lambda v: str(v or "-")),
        ],
    )


@app.command("push")
def push_command(
    file: Annotated[Path, typer.Argument(help="JSON file containing the tracker bundle.")],
    import_strategy: Annotated[
        str | None, typer.Option("--strategy", help="CREATE | UPDATE | CREATE_AND_UPDATE | DELETE")
    ] = None,
    atomic_mode: Annotated[str | None, typer.Option("--atomic", help="ALL | OBJECT")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    async_mode: Annotated[bool, typer.Option("--async")] = False,
) -> None:
    """Bulk import via POST /api/tracker."""
    from dhis2w_core.v41.cli_output import render_webmessage
    from dhis2w_core.v41.plugins.tracker import service

    bundle = json.loads(file.read_text(encoding="utf-8"))
    response = asyncio.run(
        service.push_tracker(
            profile_from_env(),
            bundle,
            import_strategy=import_strategy,
            atomic_mode=atomic_mode,
            dry_run=dry_run,
            async_mode=async_mode,
        )
    )
    render_webmessage(response, action="pushed")


@app.command("delete")
def delete_command(
    uids: Annotated[list[str], typer.Argument(help="Tracked entity UID(s) to delete.")],
    async_mode: Annotated[
        bool, typer.Option("--async", help="Return a job reference immediately instead of waiting.")
    ] = False,
) -> None:
    """Delete tracked entities by UID (cascades to their enrollments + events)."""
    from dhis2w_core.v41.cli_output import render_webmessage
    from dhis2w_core.v41.plugins.tracker import service

    response = asyncio.run(
        service.delete_tracker_objects(profile_from_env(), kind="trackedEntities", uids=uids, async_mode=async_mode)
    )
    render_webmessage(response, action="deleted")


@event_app.command("delete")
def event_delete_command(
    uids: Annotated[list[str], typer.Argument(help="Event UID(s) to delete.")],
    async_mode: Annotated[
        bool, typer.Option("--async", help="Return a job reference immediately instead of waiting.")
    ] = False,
) -> None:
    """Delete events by UID."""
    from dhis2w_core.v41.cli_output import render_webmessage
    from dhis2w_core.v41.plugins.tracker import service

    response = asyncio.run(
        service.delete_tracker_objects(profile_from_env(), kind="events", uids=uids, async_mode=async_mode)
    )
    render_webmessage(response, action="deleted")


@enrollment_app.command("delete")
def enrollment_delete_command(
    uids: Annotated[list[str], typer.Argument(help="Enrollment UID(s) to delete.")],
    async_mode: Annotated[
        bool, typer.Option("--async", help="Return a job reference immediately instead of waiting.")
    ] = False,
) -> None:
    """Delete enrollments by UID."""
    from dhis2w_core.v41.cli_output import render_webmessage
    from dhis2w_core.v41.plugins.tracker import service

    response = asyncio.run(
        service.delete_tracker_objects(profile_from_env(), kind="enrollments", uids=uids, async_mode=async_mode)
    )
    render_webmessage(response, action="deleted")


def _parse_kv(values: list[str], *, flag_name: str) -> dict[str, str]:
    """Parse repeated `--kv key=value` flags into a dict; raise on malformed entries."""
    parsed: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise typer.BadParameter(f"{flag_name} expects 'UID=value', got {value!r}")
        key, raw = value.split("=", 1)
        key = key.strip()
        if not key:
            raise typer.BadParameter(f"{flag_name} key cannot be empty (got {value!r})")
        parsed[key] = raw
    return parsed


@app.command("register")
def register_command(
    program: Annotated[str, typer.Argument(help="Program UID to enroll into.")],
    org_unit: Annotated[
        str,
        typer.Option("--org-unit", "--ou", help="OrgUnit UID where the TE lives + is enrolled."),
    ],
    tracked_entity_type: Annotated[
        str | None,
        typer.Option(
            "--tet",
            help="TrackedEntityType UID. Defaults to the program's trackedEntityType if unset.",
        ),
    ] = None,
    attributes: Annotated[
        list[str] | None,
        typer.Option(
            "--attr",
            help="TrackedEntityAttribute UID=value. Repeatable. Example: --attr w75KJ2mc4zz=Jane",
        ),
    ] = None,
    enrolled_at: Annotated[
        str | None,
        typer.Option("--enrolled-at", help="Enrollment date (ISO, e.g. 2024-06-01). Defaults to today server-side."),
    ] = None,
) -> None:
    """Register a tracked entity + enroll in one program in one call.

    The typical clinic-intake flow: fills the TrackedEntityAttribute form,
    stamps an enrollment into the program, all atomic via POST /api/tracker.
    Prints the new tracked-entity + enrollment UIDs so the caller can
    reference them downstream.
    """
    from dhis2w_core.v41.plugins.tracker import service

    attrs = _parse_kv(attributes or [], flag_name="--attr")
    tet = tracked_entity_type
    if tet is None:
        from dhis2w_core.v41.client_context import open_client

        async def _resolve() -> str:
            async with open_client(profile_from_env()) as client:
                raw = await client.get_raw(f"/api/programs/{program}", params={"fields": "trackedEntityType[id]"})
            ref = raw.get("trackedEntityType") or {}
            if not isinstance(ref, dict) or not ref.get("id"):
                raise typer.BadParameter(
                    f"program {program!r} has no trackedEntityType — pass --tet explicitly.",
                )
            return str(ref["id"])

        tet = asyncio.run(_resolve())
    result = asyncio.run(
        service.register_tracked_entity(
            profile_from_env(),
            program=program,
            org_unit=org_unit,
            tracked_entity_type=tet,
            attributes=attrs,
            enrolled_at=enrolled_at,
        )
    )
    if is_json_output():
        typer.echo(result.model_dump_json(indent=2, exclude_none=True))
        return
    from dhis2w_core.v41.cli_output import DetailRow, render_detail

    render_detail(
        f"registered {result.tracked_entity} (enrollment {result.enrollment})",
        [
            DetailRow("tracked entity", result.tracked_entity),
            DetailRow("enrollment", result.enrollment),
            DetailRow("program", program),
            DetailRow("org unit", org_unit),
            DetailRow("status", str(result.response.status)),
        ],
    )


@enrollment_app.command("create")
def enrollment_create_command(
    tracked_entity: Annotated[str, typer.Argument(help="Existing TrackedEntity UID to enroll.")],
    program: Annotated[str, typer.Argument(help="Program UID to enroll into.")],
    org_unit: Annotated[str, typer.Option("--at", help="OrgUnit UID where the enrollment lives.")],
    enrolled_at: Annotated[
        str | None,
        typer.Option("--enrolled-at", help="ISO date; defaults to today server-side."),
    ] = None,
) -> None:
    """Enroll an existing tracked entity in a program."""
    from dhis2w_core.v41.plugins.tracker import service

    result = asyncio.run(
        service.enroll_tracked_entity(
            profile_from_env(),
            tracked_entity=tracked_entity,
            program=program,
            org_unit=org_unit,
            enrolled_at=enrolled_at,
        )
    )
    if is_json_output():
        typer.echo(result.model_dump_json(indent=2, exclude_none=True))
        return
    from dhis2w_core.v41.cli_output import DetailRow, render_detail

    render_detail(
        f"enrolled {tracked_entity} in {program}",
        [
            DetailRow("enrollment", result.enrollment),
            DetailRow("tracked entity", tracked_entity),
            DetailRow("program", program),
            DetailRow("org unit", org_unit),
            DetailRow("status", str(result.response.status)),
        ],
    )


@event_app.command("create")
def event_create_command(
    program: Annotated[str, typer.Option("--program", help="Program UID.")],
    program_stage: Annotated[str, typer.Option("--stage", help="ProgramStage UID.")],
    org_unit: Annotated[str, typer.Option("--at", help="OrgUnit UID where the event happened.")],
    enrollment: Annotated[
        str | None,
        typer.Option(
            "--enrollment",
            help=(
                "Enrollment UID for tracker (WITH_REGISTRATION) programs. Omit for "
                "event (WITHOUT_REGISTRATION) programs."
            ),
        ),
    ] = None,
    tracked_entity: Annotated[
        str | None,
        typer.Option(
            "--te",
            help="TrackedEntity UID (tracker programs only). Optional — DHIS2 derives from the enrollment.",
        ),
    ] = None,
    data_values: Annotated[
        list[str] | None,
        typer.Option(
            "--dv",
            help="DataElement UID=value. Repeatable. Example: --dv fClA2Erf6IO=5",
        ),
    ] = None,
    occurred_at: Annotated[
        str | None,
        typer.Option("--occurred-at", help="ISO event date; defaults to today server-side."),
    ] = None,
) -> None:
    """Add one event — tracker (with enrollment) or event-only (standalone).

    For tracker programs, pass --enrollment (the event binds to the
    enrollment's timeline). For event programs (WITHOUT_REGISTRATION —
    community surveys, case-investigation forms), omit --enrollment; the
    event stands alone, scoped by program + stage + org unit.
    """
    from dhis2w_core.v41.plugins.tracker import service

    dvs = _parse_kv(data_values or [], flag_name="--dv")
    result = asyncio.run(
        service.add_tracker_event(
            profile_from_env(),
            program=program,
            program_stage=program_stage,
            org_unit=org_unit,
            enrollment=enrollment,
            tracked_entity=tracked_entity,
            data_values=dvs,
            occurred_at=occurred_at,
        )
    )
    if is_json_output():
        typer.echo(result.model_dump_json(indent=2, exclude_none=True))
        return
    from dhis2w_core.v41.cli_output import DetailRow, render_detail

    render_detail(
        f"logged event {result.event}",
        [
            DetailRow("event", result.event),
            DetailRow("enrollment", enrollment or "(standalone)"),
            DetailRow("program", program),
            DetailRow("stage", program_stage),
            DetailRow("org unit", org_unit),
            DetailRow("data values", str(len(dvs))),
            DetailRow("status", str(result.response.status)),
        ],
    )


@app.command("outstanding")
def outstanding_command(
    program: Annotated[str, typer.Argument(help="Program UID — the scope for the 'what's due' report.")],
    org_unit: Annotated[
        str | None,
        typer.Option(
            "--org-unit",
            "--ou",
            help="Narrow to one OU subtree. Default: every active enrollment on the program.",
        ),
    ] = None,
    ou_mode: Annotated[str, typer.Option("--ou-mode", help="SELECTED | CHILDREN | DESCENDANTS | ALL")] = "DESCENDANTS",
    page_size: Annotated[int, typer.Option("--page-size", help="Max enrollments scanned (default 200).")] = 200,
) -> None:
    """List ACTIVE enrollments missing events on any non-repeatable program stage.

    Renders each hit with its tracked-entity UID, OU, and the program-stage
    UIDs that still need an event. A "what's due" report for tracker
    follow-ups.

    "Required" here means `repeatable=false` on the program stage —
    repeatable stages (weekly checkups, periodic screenings) don't have
    a single outstanding semantic and are skipped.
    """
    from dhis2w_core.v41.cli_output import ColumnSpec, render_list
    from dhis2w_core.v41.plugins.tracker import service

    rows = asyncio.run(
        service.outstanding_enrollments(
            profile_from_env(),
            program,
            org_unit=org_unit,
            ou_mode=ou_mode,
            page_size=page_size,
        )
    )
    if is_json_output():
        typer.echo(json.dumps([r.model_dump(exclude_none=True, mode="json") for r in rows], indent=2, default=str))
        return
    if not rows:
        typer.echo(f"no outstanding enrollments on program {program}.")
        return
    columns = [
        ColumnSpec(label="enrollment", key="enrollment"),
        ColumnSpec(label="tracked entity", key="tracked_entity"),
        ColumnSpec(label="org unit", key="org_unit"),
        ColumnSpec(label="enrolled at", key="enrolled_at", style="dim"),
        ColumnSpec(label="missing stages", key="missing_stages", formatter=lambda v: ", ".join(v or [])),
    ]
    render_list(
        f"outstanding enrollments on {program}",
        [r.model_dump(mode="json") for r in rows],
        columns=columns,
    )
