"""The DHIS2 read behind one entity's record: the events, off the entity, in one request.

FOUR FACTS DECIDE THE SHAPE OF THIS READ, and three of them are recorded in the repository's
`BUGS.md`:

1. **The events come off the tracked entity, never off a program.** `/api/tracker/events` demands a
   `program` unconditionally on 2.43 and answers a Tomcat HTML page when it is missing (BUGS.md 91),
   and its singular `enrollment=` filter is accepted and silently dropped on every major. Naming a
   program here would also mean naming one the entity might not be enrolled in, which answers 404
   claiming the entity does not exist (BUGS.md 72). The tracked entity read takes neither risk: the
   enrollments are a projection of the entity, and the events are a projection of those.
2. **No events listing is scoped by organisation unit.** `?orgUnit=` on the events collection filters
   by the enrollment owner's unit rather than the event's own (BUGS.md 69), so an event recorded away
   from the owning facility is invisible under the unit its payload names. An entity-scoped read
   serves every event whatever unit each was recorded at, which is the whole record and the only
   honest answer to "what happened to this person".
3. **The default projection carries none of this.** The tracked entity endpoint omits the enrollments
   entirely unless `fields` names them, so the projection is spelled out in full here - down to the
   data values, without which the record would be a list of dates.
4. **The order DHIS2 answers in is not an order** (BUGS.md 108). The nested events arrive sorted by
   neither their own date nor their creation - a seeded fridge answers 07:00, 06:00, 08:00 - and the
   `order=` the same request accepts does not reach them. So the record is ordered here, newest
   first, by the instant the event occurred and then by its UID. The tie-break is what makes two
   reads of an unchanged record answer the same bytes.

A DELETED EVENT IS NOT PART OF THE RECORD. `includeDeleted` is not passed, so a soft-deleted event is
absent, which is what a read of what the instance holds now means. The sync's polls pass it for the
opposite reason - a tombstone is exactly what a cursor walk is looking for.

WHAT `reader` IS HERE IS THE POINT OF THE PARAMETER, as it is for the register: every read takes a
`RegisterReader` and never a `Dhis2Client`, so whose credentials the record is read under is settled
per request. Under `[serve] auth = "dhis2"` it is the caller's own header, and DHIS2 decides per
caller which events come back. See `dhis2w_fhir_serve.passthrough`.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from dhis2w_client.errors import Dhis2ApiError
from dhis2w_client.generated.v42.oas import TrackerEvent, TrackerTrackedEntity
from pydantic import BaseModel, ConfigDict

from dhis2w_fhir_serve.register.wire import TRACKED_ENTITIES_PATH, is_tracked_entity_uid

if TYPE_CHECKING:
    from dhis2w_fhir_serve.passthrough import RegisterReader

#: The projection one record read asks for: the entity, its enrollments, and the events under them
#: with their data values. Named in full because the endpoint's default carries none of it.
_DATA_VALUE_FIELDS = "dataElement,value"
_EVENT_FIELDS = f"event,program,programStage,enrollment,status,occurredAt,orgUnit,dataValues[{_DATA_VALUE_FIELDS}]"
_ENROLLMENT_FIELDS = f"enrollment,program,status,events[{_EVENT_FIELDS}]"
TRACKED_ENTITY_RECORD_FIELDS = f"trackedEntity,trackedEntityType,enrollments[{_ENROLLMENT_FIELDS}]"


class RecordedValue(BaseModel):
    """One value one event holds: the DHIS2 data element it answers, and the string the instance stored."""

    model_config = ConfigDict(frozen=True)

    data_element_uid: str
    value: str


class RecordedEvent(BaseModel):
    """One event of one enrollment, as the instance holds it right now.

    Every field but the event's own UID is optional because the instance states each of them
    separately, and an event missing one is served with that fact missing rather than dropped: what
    a partial event costs is one element of the document it projects onto, and hiding the event
    would cost the whole of it.
    """

    model_config = ConfigDict(frozen=True)

    event_uid: str
    program_uid: str | None = None
    program_stage_uid: str | None = None
    enrollment_uid: str | None = None
    status: str | None = None
    """The DHIS2 event status verbatim - `ACTIVE`, `COMPLETED`, `SCHEDULE`, `SKIPPED`, or `VISITED`."""

    occurred_at: str | None = None
    """When the event occurred, as DHIS2 dated it, in the instance's own zone-less spelling (BUGS.md 62)."""

    organisation_unit_uid: str | None = None
    values: tuple[RecordedValue, ...] = ()

    def order_key(self) -> tuple[str, str]:
        """Where one event sits in the record: the instant it occurred, then its UID as the tie-break.

        An event the instance dates nothing sorts to the end of a newest-first walk, which is where an
        undated event belongs: it is not newer than anything that carries a date.
        """
        return (self.occurred_at or "", self.event_uid)


class TrackedEntityRecord(BaseModel):
    """Everything one tracked entity holds over time: who they are to DHIS2, and every event, newest first."""

    model_config = ConfigDict(frozen=True)

    tracked_entity_uid: str
    tracked_entity_type_uid: str | None = None
    events: tuple[RecordedEvent, ...] = ()


async def fetch_tracked_entity_record(reader: RegisterReader, tracked_entity_uid: str) -> TrackedEntityRecord | None:
    """Read one entity's whole record in one entity-scoped request, or None when the instance holds none.

    A value that is not UID-shaped is None without a request, exactly as the register's read is: DHIS2
    answers 400 for one, and this facade knows the shape of the identifier it mints its own links from.
    """
    if not is_tracked_entity_uid(tracked_entity_uid):
        return None
    try:
        raw = await reader.get_raw(
            f"{TRACKED_ENTITIES_PATH}/{tracked_entity_uid}", params={"fields": TRACKED_ENTITY_RECORD_FIELDS}
        )
    except Dhis2ApiError as error:
        if error.status_code == 404:
            return None
        raise
    return recorded_entity(TrackerTrackedEntity.model_validate(raw), tracked_entity_uid)


def recorded_entity(entity: TrackerTrackedEntity, tracked_entity_uid: str) -> TrackedEntityRecord:
    """Read one answered tracked entity into the record this facade serves, ordered newest first."""
    events = [
        _recorded_event(event, enrollment_uid=enrollment.enrollment, program_uid=enrollment.program)
        for enrollment in entity.enrollments or []
        for event in enrollment.events or []
        if event.event
    ]
    return TrackedEntityRecord(
        tracked_entity_uid=entity.trackedEntity or tracked_entity_uid,
        tracked_entity_type_uid=entity.trackedEntityType,
        events=tuple(sorted(events, key=RecordedEvent.order_key, reverse=True)),
    )


def _recorded_event(event: TrackerEvent, *, enrollment_uid: str | None, program_uid: str | None) -> RecordedEvent:
    """Read one answered event, taking the enrollment it hung under as the enrollment it belongs to.

    The event states both facts itself when the projection asks for them, and the enclosing enrollment
    states them too; the enclosing one wins, because that is the relationship this read established -
    the events were reached through it.
    """
    return RecordedEvent(
        event_uid=event.event or "",
        program_uid=program_uid or event.program,
        program_stage_uid=event.programStage,
        enrollment_uid=enrollment_uid or event.enrollment,
        status=None if event.status is None else str(event.status.value),
        occurred_at=instant_text(event.occurredAt),
        organisation_unit_uid=event.orgUnit,
        values=tuple(
            RecordedValue(data_element_uid=value.dataElement, value=value.value)
            for value in event.dataValues or []
            if value.dataElement and value.value is not None
        ),
    )


def instant_text(value: datetime | int | None) -> str | None:
    """One DHIS2 instant as text - the tracker's own spelling, not Python's `str()` of a datetime.

    The generated model types the element as an instant or an epoch integer, because the OpenAPI
    document allows both; an integer is carried through as it arrived rather than guessed a unit for,
    which is the reading `dhis2w_fhir_serve.routes.enrollments` gives the same element.
    """
    if value is None:
        return None
    return value.isoformat() if isinstance(value, datetime) else str(value)
