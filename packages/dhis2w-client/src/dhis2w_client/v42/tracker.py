"""`Dhis2Client.tracker` — authoring workflows over `/api/tracker`.

Generic tracker CRUD already works through the generated tracker models
+ raw `/api/tracker` push, but the everyday operator flows ("register
this person, enroll them, log an event") involve stitching together the
`trackedEntities` / `enrollments` / `events` bundle sections by hand.
This accessor wraps the common shapes:

- `register` — create a tracked entity + enroll in one program in one
  request, optionally with the first events attached inline. Typical
  clinic intake.
- `enroll` — add an enrollment to an existing tracked entity. Typical
  second-program pickup.
- `add_event` — append one event to an existing enrollment. Typical
  follow-up visit.
- `outstanding` — list active enrollments missing events on any
  non-repeatable program stage. A "what's due" report.

Every write verb round-trips through `POST /api/tracker` — the same
endpoint the bulk `TrackerBundle` push uses — so atomicity + the
familiar `WebMessageResponse` envelope carry through. Every write verb
pre-generates the new UIDs client-side (so DHIS2 uses them verbatim
instead of allocating) and returns them on a typed result alongside the
response envelope, so callers can reference the newly-created rows
without parsing `bundleReport`.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field

from dhis2w_client.v42.envelopes import WebMessageResponse
from dhis2w_client.v42.uids import generate_uid

if TYPE_CHECKING:
    from dhis2w_client.v42.client import Dhis2Client

# Date arguments accept ISO strings, `date`, or `datetime` — serialised to
# DHIS2's ISO-8601 wire format at the call edge via `_to_iso`.
DateLike = str | date | datetime


def _to_iso(value: DateLike | None) -> str | None:
    """Normalise a `DateLike` to DHIS2's ISO-8601 string format (or None)."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


class RegisterResult(BaseModel):
    """Outcome of `TrackerAccessor.register` — the new UIDs + server response."""

    model_config = ConfigDict(frozen=True)

    tracked_entity: str
    enrollment: str
    events: list[str] = Field(default_factory=list)
    response: WebMessageResponse


class EnrollResult(BaseModel):
    """Outcome of `TrackerAccessor.enroll` — the enrollment UID + server response."""

    model_config = ConfigDict(frozen=True)

    enrollment: str
    response: WebMessageResponse


class EventResult(BaseModel):
    """Outcome of `TrackerAccessor.add_event` — the event UID + server response."""

    model_config = ConfigDict(frozen=True)

    event: str
    response: WebMessageResponse


class OutstandingEnrollment(BaseModel):
    """One active enrollment that's missing events on a required program stage."""

    model_config = ConfigDict(frozen=True)

    enrollment: str
    tracked_entity: str
    program: str
    org_unit: str
    enrolled_at: str | None = None
    missing_stages: list[str] = Field(
        default_factory=list,
        description="ProgramStage UIDs (non-repeatable) with no event on this enrollment.",
    )


class TrackerAccessor:
    """`Dhis2Client.tracker` — workflow helpers over `/api/tracker`."""

    def __init__(self, client: Dhis2Client) -> None:
        """Bind to the sharing client."""
        self._client = client

    async def register(
        self,
        *,
        program: str,
        org_unit: str,
        tracked_entity_type: str,
        attributes: Mapping[str, str] | None = None,
        enrolled_at: DateLike | None = None,
        occurred_at: DateLike | None = None,
        events: list[Mapping[str, Any]] | None = None,
        import_strategy: str = "CREATE_AND_UPDATE",
    ) -> RegisterResult:
        """Register a tracked entity + enroll in one program in one call.

        `attributes` maps TrackedEntityAttribute UID -> value (the clinic
        intake form). `events` is an optional list of `{"program_stage":
        <uid>, "org_unit": <uid>?, "occurred_at": <date>?, "data_values":
        {de_uid: value, ...}}` dicts — attach the first few stage events
        inline so the whole intake lands as one atomic POST.

        Returns a `RegisterResult` carrying the generated `tracked_entity`
        + `enrollment` UIDs so the caller can reference the new rows
        without parsing the `bundleReport`.
        """
        tracked_entity_uid = generate_uid()
        enrollment_uid = generate_uid()
        enrolled_at_iso = _to_iso(enrolled_at)
        occurred_at_iso = _to_iso(occurred_at) or enrolled_at_iso
        event_uids: list[str] = []
        events_payload: list[dict[str, Any]] = []
        for event in events or []:
            event_uid = generate_uid()
            event_uids.append(event_uid)
            events_payload.append(
                _event_dict(
                    event_uid=event_uid,
                    enrollment=enrollment_uid,
                    tracked_entity=tracked_entity_uid,
                    program=program,
                    program_stage=str(event["program_stage"]),
                    org_unit=str(event.get("org_unit") or org_unit),
                    occurred_at=_to_iso(event.get("occurred_at")),
                    data_values=event.get("data_values") or {},
                ),
            )
        attrs_payload: list[dict[str, Any]] = [
            {"attribute": attr_uid, "value": value} for attr_uid, value in (attributes or {}).items()
        ]
        enrollment_payload = {
            "enrollment": enrollment_uid,
            "trackedEntity": tracked_entity_uid,
            "program": program,
            "orgUnit": org_unit,
            "enrolledAt": enrolled_at_iso,
            "occurredAt": occurred_at_iso,
            "status": "ACTIVE",
            "events": events_payload,
        }
        te_payload = {
            "trackedEntity": tracked_entity_uid,
            "orgUnit": org_unit,
            "trackedEntityType": tracked_entity_type,
            "attributes": attrs_payload,
            "enrollments": [_strip_none(enrollment_payload)],
        }
        body = {"trackedEntities": [_strip_none(te_payload)]}
        response = await self._post_tracker(body, import_strategy=import_strategy)
        return RegisterResult(
            tracked_entity=tracked_entity_uid,
            enrollment=enrollment_uid,
            events=event_uids,
            response=response,
        )

    async def enroll(
        self,
        *,
        tracked_entity: str,
        program: str,
        org_unit: str,
        enrolled_at: DateLike | None = None,
        occurred_at: DateLike | None = None,
        import_strategy: str = "CREATE_AND_UPDATE",
    ) -> EnrollResult:
        """Enroll an existing tracked entity in a program.

        `enrolled_at` and `occurred_at` accept ISO strings, `date`, or
        `datetime` — all normalised to ISO on the wire. Omit to let DHIS2
        default to today.
        """
        enrollment_uid = generate_uid()
        enrolled_at_iso = _to_iso(enrolled_at)
        payload = {
            "enrollment": enrollment_uid,
            "trackedEntity": tracked_entity,
            "program": program,
            "orgUnit": org_unit,
            "enrolledAt": enrolled_at_iso,
            "occurredAt": _to_iso(occurred_at) or enrolled_at_iso,
            "status": "ACTIVE",
        }
        body = {"enrollments": [_strip_none(payload)]}
        response = await self._post_tracker(body, import_strategy=import_strategy)
        return EnrollResult(enrollment=enrollment_uid, response=response)

    async def add_event(
        self,
        *,
        program: str,
        program_stage: str,
        org_unit: str,
        enrollment: str | None = None,
        tracked_entity: str | None = None,
        data_values: Mapping[str, str] | None = None,
        occurred_at: DateLike | None = None,
        import_strategy: str = "CREATE_AND_UPDATE",
    ) -> EventResult:
        """Add one event — works for both tracker and event-only programs.

        For tracker programs (`WITH_REGISTRATION`), pass `enrollment` — the
        event binds to that enrollment's timeline. Pass `tracked_entity`
        too to skip the round-trip DHIS2 would do to look it up from the
        enrollment.

        For event programs (`WITHOUT_REGISTRATION`), omit `enrollment`
        and `tracked_entity`. The event stands alone, scoped only by
        `program` + `program_stage` + `org_unit`. Use case: community
        surveys, case-investigation forms, any one-shot data collection
        that isn't tied to a registered patient.

        `data_values` maps DataElement UID -> value. `occurred_at` is the
        event date (ISO string); defaults to today server-side.
        """
        event_uid = generate_uid()
        event_payload = _event_dict(
            event_uid=event_uid,
            enrollment=enrollment,
            tracked_entity=tracked_entity,
            program=program,
            program_stage=program_stage,
            org_unit=org_unit,
            occurred_at=_to_iso(occurred_at),
            data_values=data_values or {},
        )
        body = {"events": [event_payload]}
        response = await self._post_tracker(body, import_strategy=import_strategy)
        return EventResult(event=event_uid, response=response)

    async def outstanding(
        self,
        program: str,
        *,
        org_unit: str | None = None,
        ou_mode: str = "DESCENDANTS",
        page_size: int = 200,
    ) -> list[OutstandingEnrollment]:
        """List ACTIVE enrollments missing events on any non-repeatable stage.

        Pulls the program's non-repeatable program-stage UIDs, queries
        `/api/tracker/enrollments?program=<program>&programStatus=ACTIVE`
        with the event list inlined, and filters to enrollments whose
        events cover only a strict subset of the required stages. Every
        hit carries the list of missing stage UIDs.

        `org_unit` (+ `ou_mode`) scope the enrollment list. Default mode
        `DESCENDANTS` includes child OUs, which matches DHIS2's capture
        app default.

        "Required" here means "non-repeatable" per DHIS2's program-stage
        model. Repeatable stages (e.g. weekly checkups) don't have a
        single "due" semantic and are skipped.
        """
        required_stages = await self._non_repeatable_stage_uids(program)
        if not required_stages:
            return []
        params: dict[str, Any] = {
            "program": program,
            "programStatus": "ACTIVE",
            "fields": "enrollment,trackedEntity,program,orgUnit,enrolledAt,events[programStage]",
            "pageSize": page_size,
        }
        if org_unit is not None:
            params["orgUnit"] = org_unit
            params["ouMode"] = ou_mode
        raw = await self._client.get_raw("/api/tracker/enrollments", params=params)
        # DHIS2 response key varies across versions: `instances` in newer tracker
        # endpoints, `enrollments` in older ones. Accept either.
        rows = raw.get("instances") or raw.get("enrollments") or []
        outstanding: list[OutstandingEnrollment] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            event_stages = {
                event.get("programStage")
                for event in (row.get("events") or [])
                if isinstance(event, dict) and isinstance(event.get("programStage"), str)
            }
            missing = sorted(required_stages - event_stages)
            if not missing:
                continue
            outstanding.append(
                OutstandingEnrollment(
                    enrollment=str(row.get("enrollment", "")),
                    tracked_entity=str(row.get("trackedEntity", "")),
                    program=str(row.get("program", program)),
                    org_unit=str(row.get("orgUnit", "")),
                    enrolled_at=row.get("enrolledAt"),
                    missing_stages=missing,
                ),
            )
        return outstanding

    async def tracked_entities(
        self,
        *,
        program: str | None = None,
        tracked_entity_type: str | None = None,
        org_unit: str | Sequence[str] | None = None,
        ou_mode: str | None = None,
        tracked_entity: str | Sequence[str] | None = None,
        status: str | None = None,
        fields: str | None = None,
        filter: str | Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        updated_after: DateLike | None = None,
        extra_params: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """GET `/api/tracker/trackedEntities` and return the parsed page envelope.

        The read side of `register` / `enroll`. `org_unit`, `tracked_entity`,
        and `filter` each accept a single id or a sequence, repeating as
        `orgUnit=` / `trackedEntity=` / `filter=` query params the way the
        tracker API expects. `status` filters by enrollment status
        (`ACTIVE` / `COMPLETED` / `CANCELLED`) via `programStatus`. `fields`
        and `filter` are the tracker field-selector / attribute-filter
        strings, forwarded verbatim. `updated_after` accepts an ISO string,
        `date`, or `datetime`. `extra_params` covers the rest of the surface
        (`order`, `updatedBefore`, `enrollmentEnrolledAfter`, ...).

        Returns the raw page envelope: the rows live under `instances` on
        current majors (older trees key them under `trackedEntities`), beside
        the `page` / `pageSize` / `total` paging fields. Parse individual rows
        with `TrackedEntity.model_validate(row)` when a typed view is wanted.

        Raises `Dhis2ApiError` on 4xx / 5xx.
        """
        params = _read_params(
            program=program,
            tracked_entity_type=tracked_entity_type,
            org_unit=org_unit,
            ou_mode=ou_mode,
            tracked_entity=tracked_entity,
            status=status,
            status_param="programStatus",
            fields=fields,
            filter=filter,
            page=page,
            page_size=page_size,
            updated_after=updated_after,
            extra_params=extra_params,
        )
        return await self._client.get_raw("/api/tracker/trackedEntities", params=params)

    async def enrollments(
        self,
        *,
        program: str | None = None,
        org_unit: str | Sequence[str] | None = None,
        ou_mode: str | None = None,
        tracked_entity: str | Sequence[str] | None = None,
        enrollment: str | Sequence[str] | None = None,
        status: str | None = None,
        fields: str | None = None,
        page: int | None = None,
        page_size: int | None = None,
        updated_after: DateLike | None = None,
        extra_params: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """GET `/api/tracker/enrollments` and return the parsed page envelope.

        The read side of `enroll`. `org_unit`, `tracked_entity`, and
        `enrollment` each accept a single id or a sequence, repeating as
        `orgUnit=` / `trackedEntity=` / `enrollment=` query params. `status`
        filters by enrollment status (`ACTIVE` / `COMPLETED` / `CANCELLED`)
        via `programStatus`. `updated_after` accepts an ISO string, `date`,
        or `datetime`. `extra_params` covers the rest (`order`,
        `enrolledAfter`, `followUp`, ...).

        Returns the raw page envelope: the rows live under `instances` on
        current majors (older trees key them under `enrollments`), beside the
        paging fields.

        Raises `Dhis2ApiError` on 4xx / 5xx.
        """
        params = _read_params(
            program=program,
            org_unit=org_unit,
            ou_mode=ou_mode,
            tracked_entity=tracked_entity,
            enrollment=enrollment,
            status=status,
            status_param="programStatus",
            fields=fields,
            page=page,
            page_size=page_size,
            updated_after=updated_after,
            extra_params=extra_params,
        )
        return await self._client.get_raw("/api/tracker/enrollments", params=params)

    async def events(
        self,
        *,
        program: str | None = None,
        program_stage: str | None = None,
        org_unit: str | Sequence[str] | None = None,
        ou_mode: str | None = None,
        tracked_entity: str | Sequence[str] | None = None,
        enrollment: str | Sequence[str] | None = None,
        status: str | None = None,
        fields: str | None = None,
        filter: str | Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        updated_after: DateLike | None = None,
        occurred_after: DateLike | None = None,
        extra_params: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """GET `/api/tracker/events` and return the parsed page envelope.

        The read side of `add_event` — works for both tracker events (scoped
        by `enrollment` / `tracked_entity`) and standalone event-program
        events (scoped by `program` / `program_stage` / `org_unit`).
        `org_unit`, `tracked_entity`, `enrollment`, and `filter` each accept a
        single id or a sequence, repeating as the matching query param.
        `status` filters by event status (`ACTIVE` / `COMPLETED` /
        `SCHEDULE` / `SKIPPED` / `VISITED`) via `status`. `updated_after` and
        `occurred_after` accept an ISO string, `date`, or `datetime`.
        `extra_params` covers the rest (`order`, `occurredBefore`,
        `scheduledAfter`, `assignedUser`, ...).

        Returns the raw page envelope: the rows live under `instances` on
        current majors (older trees key them under `events`), beside the
        paging fields. Parse individual rows with `Event.model_validate(row)`
        when a typed view is wanted.

        Raises `Dhis2ApiError` on 4xx / 5xx.
        """
        params = _read_params(
            program=program,
            program_stage=program_stage,
            org_unit=org_unit,
            ou_mode=ou_mode,
            tracked_entity=tracked_entity,
            enrollment=enrollment,
            status=status,
            status_param="status",
            fields=fields,
            filter=filter,
            page=page,
            page_size=page_size,
            updated_after=updated_after,
            occurred_after=occurred_after,
            extra_params=extra_params,
        )
        return await self._client.get_raw("/api/tracker/events", params=params)

    async def _post_tracker(self, body: Mapping[str, Any], *, import_strategy: str) -> WebMessageResponse:
        """POST to `/api/tracker` with the standard sync-mode params."""
        raw = await self._client.post_raw(
            "/api/tracker",
            body=body,
            params={"importStrategy": import_strategy, "async": "false"},
        )
        return WebMessageResponse.model_validate(raw)

    async def _non_repeatable_stage_uids(self, program: str) -> set[str]:
        """Return the set of program-stage UIDs marked `repeatable=false`."""
        raw = await self._client.get_raw(
            f"/api/programs/{program}",
            params={"fields": "programStages[id,repeatable]"},
        )
        return {
            stage["id"]
            for stage in (raw.get("programStages") or [])
            if isinstance(stage, dict) and isinstance(stage.get("id"), str) and stage.get("repeatable") is not True
        }


def _read_params(
    *,
    program: str | None = None,
    program_stage: str | None = None,
    tracked_entity_type: str | None = None,
    org_unit: str | Sequence[str] | None = None,
    ou_mode: str | None = None,
    tracked_entity: str | Sequence[str] | None = None,
    enrollment: str | Sequence[str] | None = None,
    status: str | None = None,
    status_param: str = "status",
    fields: str | None = None,
    filter: str | Sequence[str] | None = None,
    page: int | None = None,
    page_size: int | None = None,
    updated_after: DateLike | None = None,
    occurred_after: DateLike | None = None,
    extra_params: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a `/api/tracker/*` read query, mapping snake args to wire params.

    Single-or-sequence args (`org_unit`, `tracked_entity`, `enrollment`,
    `filter`) repeat; scalars pass straight through; `None` is dropped so
    unset params never reach the wire. `status_param` names the wire key the
    `status` value rides — `programStatus` for tracked entities / enrollments,
    `status` for events. Date args normalise to ISO via `_to_iso`.
    """
    params: dict[str, Any] = {}
    if program is not None:
        params["program"] = program
    if program_stage is not None:
        params["programStage"] = program_stage
    if tracked_entity_type is not None:
        params["trackedEntityType"] = tracked_entity_type
    _repeat(params, "orgUnit", org_unit)
    if ou_mode is not None:
        params["ouMode"] = ou_mode
    _repeat(params, "trackedEntity", tracked_entity)
    _repeat(params, "enrollment", enrollment)
    if status is not None:
        params[status_param] = status
    if fields is not None:
        params["fields"] = fields
    _repeat(params, "filter", filter)
    if page is not None:
        params["page"] = page
    if page_size is not None:
        params["pageSize"] = page_size
    updated_after_iso = _to_iso(updated_after)
    if updated_after_iso is not None:
        params["updatedAfter"] = updated_after_iso
    occurred_after_iso = _to_iso(occurred_after)
    if occurred_after_iso is not None:
        params["occurredAfter"] = occurred_after_iso
    if extra_params:
        params.update(extra_params)
    return params


def _repeat(params: dict[str, Any], key: str, value: str | Sequence[str] | None) -> None:
    """Add `value` as a single-or-repeated query param, skipping `None`."""
    if value is None:
        return
    params[key] = [value] if isinstance(value, str) else list(value)


def _event_dict(
    *,
    event_uid: str,
    enrollment: str | None,
    tracked_entity: str | None,
    program: str,
    program_stage: str,
    org_unit: str,
    occurred_at: str | None,
    data_values: Mapping[str, Any],
) -> dict[str, Any]:
    """Build one `/api/tracker` event payload, pruning None fields.

    Default event status depends on program kind:
    - `COMPLETED` for standalone event-program events (no enrollment). An
      event program collects one-shot data; a fresh event is typically
      the final state, not mid-encounter. Callers that WILL update it
      later can pass their own payload through `client.post_raw`.
    - `ACTIVE` for enrollment-bound tracker events. Tracker visits stay
      ACTIVE until the clinician completes them in the capture app.
    """
    default_status = "ACTIVE" if enrollment is not None else "COMPLETED"
    return _strip_none(
        {
            "event": event_uid,
            "enrollment": enrollment,
            "trackedEntity": tracked_entity,
            "program": program,
            "programStage": program_stage,
            "orgUnit": org_unit,
            "occurredAt": occurred_at,
            "status": default_status,
            "dataValues": [{"dataElement": de_uid, "value": value} for de_uid, value in data_values.items()],
        },
    )


def _strip_none(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Drop keys whose value is `None` so DHIS2 doesn't reject on explicit nulls."""
    return {k: v for k, v in payload.items() if v is not None}


__all__ = [
    "DateLike",
    "EnrollResult",
    "EventResult",
    "OutstandingEnrollment",
    "RegisterResult",
    "TrackerAccessor",
]
