"""`GET /tracked-entities/{uid}/events` - one tracked entity's own record, read from the instance per request.

THE REGISTER ANSWERS WHO SOMEBODY IS AND THIS ANSWERS WHAT HAPPENED TO THEM. `GET /{RegisterType}/{uid}`
serves the identity of one tracked entity; this serves the events of every enrollment that entity
holds, each as the `QuestionnaireResponse` the guide already publishes for its program stage. Both are
read from DHIS2 at request time, under the credentials of whoever asked, and neither is cached.

WHY A QuestionnaireResponse AND NOT A CLINICAL RESOURCE. The capture contract states one shape for a
tracker event, the forwarder writes DHIS2 from that shape, and the instance-sourced example corpus is
built by projecting real events into it. Serving the record in the same shape means the guide
describes one event once - what a client may post is what a client reads back. Whether a DHIS2 event
is *also* an `Encounter`, or its values *also* `Observation`s, is the SDC `$extract` question the
enrollment resource paper leaves open on purpose, and `$extract` runs over a QuestionnaireResponse:
the form-faithful document is the substrate that line needs, not a rival to it. No clinical claim is
made here, because DHIS2 states no mapping onto one.

THE SUBJECT NEED NOT BE A PERSON. The record is keyed by tracked entity UID and the subject of each
document is whatever resource type the published `D2TET_CM` takes that entity's type onto - so a cold
chain fridge's temperature readings are served exactly as a person's visits are, with `Device` in the
subject's `type` where the fridge is registered as one. Nothing below branches on person-hood.

**Live mode only, and gated twice.** A compiled guide has no instance behind it and says so.
`[serve.tracked_entities] enabled = false` takes the register away and this with it;
`[serve.tracked_entities] events = false` takes this away alone, which is the posture for a deployment
that publishes who its subjects are and not what was recorded about them. Each refusal names the key
that produced it.

**A page is a slice of the record, and the record is read whole.** DHIS2 serves the events nested
under the enrollments of one entity in a single request and offers no paging inside that projection,
so the whole record arrives and this server pages the ordered result. `Bundle.total` is therefore
every event this caller may see, counted under their own credentials - unlike a projection-served
searchset, which states none. `_count` is honoured up to `[serve.tracked_entities] page_size_limit`
and clamped rather than refused above it; `_count=0` asks how long the record is and is answered with
the number and no entries.

**Every entry names the URL its document is really served at.** One event is read at
`GET /tracked-entities/{uid}/events/{eventUid}`, and that is what the entry's `fullUrl` carries.
`QuestionnaireResponse/{id}` on this server is deliberately NOT that URL: that address answers the
spool, where a resource of that id is a receipt of what a client submitted rather than what DHIS2 now
holds, and pointing a Bundle entry at it would merge the two.

**A stage this project publishes no form for is stated rather than skipped quietly.** Those events are
counted in `total` - they are events the entity holds - carry no document, and the searchset closes
with an `outcome` entry naming the stages, which is R4's own way for a server to say something about a
search inside the search's answer. The alternative is a short answer a client reads as a short record.

**The parameters are `_count` and `page`, and anything else is refused.** A parameter this surface
cannot apply, ignored, would answer a narrower question with the whole record - the same reason
`dhis2w_fhir_serve.routes.register` refuses one.
"""

from __future__ import annotations

from urllib.parse import urlencode

from dhis2w_client.errors import Dhis2ClientError
from dhis2w_fhir.notes import pluralize, verb_for_count
from dhis2w_fhir.r4 import (
    Bundle,
    BundleEntry,
    BundleEntrySearch,
    BundleLink,
    OperationOutcome,
    OperationOutcomeIssue,
    QuestionnaireResponse,
    json_resource,
)
from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from dhis2w_fhir_serve.errors import (
    FHIR_JSON_MEDIA_TYPE,
    NoPublishedSubjectTypeError,
    NotFoundError,
    NotServedFromCompiledIgError,
    RecordDisabledError,
    RegisterDisabledError,
    UnsupportedSearchParameterError,
    UpstreamError,
)
from dhis2w_fhir_serve.history.projection import ProjectedRecord, RecordProjection
from dhis2w_fhir_serve.history.wire import RecordedEvent, TrackedEntityRecord, fetch_tracked_entity_record
from dhis2w_fhir_serve.passthrough import RegisterReader, register_reader
from dhis2w_fhir_serve.register.wire import upstream_refusal_text
from dhis2w_fhir_serve.routes.capture import capture_state
from dhis2w_fhir_serve.routes.context import serve_context
from dhis2w_fhir_serve.routes.read import base_url, requested_entry_cap
from dhis2w_fhir_serve.spool import COUNT_PARAMETER, PAGE_PARAMETER, SpoolCursor, requested_cursor

#: Where the record is served from. Lowercase segments, so no FHIR resource type can collide, and
#: under the tracked entity whose record it is - the enrollment listing's own address, one level down.
TRACKED_ENTITY_EVENTS_PATH = "/tracked-entities/{tracked_entity_uid}/events"
TRACKED_ENTITY_EVENT_PATH = "/tracked-entities/{tracked_entity_uid}/events/{event_uid}"

#: What the config refusals name, so a client reads one word for the whole surface.
EVENTS_SURFACE_NAME = "events"

#: What a 404 names, which is the one thing that was asked for rather than the surface it was asked of.
EVENT_NAME = "event"
TRACKED_ENTITY_NAME = "tracked entity"

#: The parameters a record read answers. Everything else is refused rather than ignored.
ANSWERED_PARAMETERS = (COUNT_PARAMETER, PAGE_PARAMETER)

router = APIRouter()


class RecordPage(BaseModel):
    """One page of a record: the events on it, and where the pages either side of it are."""

    model_config = ConfigDict(frozen=True)

    events: tuple[RecordedEvent, ...] = ()
    total: int = 0
    cursor: SpoolCursor = SpoolCursor()
    next_cursor: SpoolCursor | None = None
    previous_cursor: SpoolCursor | None = None


@router.get(TRACKED_ENTITY_EVENTS_PATH)
async def read_tracked_entity_events(request: Request, tracked_entity_uid: str) -> Response:
    """Answer one page of one tracked entity's record, newest event first."""
    reader = await _reader(request)
    _require_answerable_parameters(request)
    record = await _record(reader, tracked_entity_uid)
    service_base = base_url(request)
    if requested_entry_cap(request.query_params.get(COUNT_PARAMETER)) == 0:
        return _record_length(service_base, tracked_entity_uid, len(record.events))
    count = _requested_count(request)
    page = _page_of(record.events, requested_cursor(request.query_params.get(PAGE_PARAMETER)), count)
    projected = _projection(request).project(record, page.events)
    bundle = Bundle(
        type="searchset",
        total=page.total,
        link=_links(service_base, tracked_entity_uid, page, count),
        entry=[
            *(_entry(service_base, tracked_entity_uid, response) for response in projected.responses),
            *_unpublished_stage_entries(projected),
        ]
        or None,
    )
    return Response(content=bundle.model_dump_json(exclude_none=True, by_alias=True), media_type=FHIR_JSON_MEDIA_TYPE)


@router.get(TRACKED_ENTITY_EVENT_PATH)
async def read_tracked_entity_event(request: Request, tracked_entity_uid: str, event_uid: str) -> Response:
    """Answer one event of one tracked entity's record, which is what a page's entry links to.

    The event is looked for inside the record rather than read by its own UID, which is what keeps the
    read entity-scoped: an event of somebody else is not this entity's record, and answering one here
    would let a caller walk from a person they may see to an event about a person they may not.
    """
    record = await _record(await _reader(request), tracked_entity_uid)
    found = next((event for event in record.events if event.event_uid == event_uid), None)
    if found is None:
        raise NotFoundError(EVENT_NAME, event_uid)
    projected = _projection(request).project_event(record, found)
    if projected.response is None:
        raise NotFoundError(EVENT_NAME, event_uid)
    return JSONResponse(
        content=projected.response.model_dump(mode="json", exclude_none=True, by_alias=True),
        media_type=FHIR_JSON_MEDIA_TYPE,
    )


async def _reader(request: Request) -> RegisterReader:
    """What this request reads the instance through, refusing every way this process serves no record.

    The project's own word comes first, in the order the register states it: a project that serves no
    tracked entity serves no record either, and one that serves identity alone says so before a client
    is told to restart the process with `--live`. The connection comes next, which is also where a
    forwarding posture refuses a request carrying no credential, since what comes back is read as the
    caller. Every one of these is settled before a parameter is read and before the instance is
    asked anything, so a request this server will not answer costs it no round trip.
    """
    surface = serve_context(request).register_surface
    if not surface.tracked_entities.enabled:
        raise RegisterDisabledError(EVENTS_SURFACE_NAME)
    if not surface.tracked_entities.events:
        raise RecordDisabledError(EVENTS_SURFACE_NAME)
    reader = await register_reader(request)
    if reader is None:
        raise NotServedFromCompiledIgError(EVENTS_SURFACE_NAME)
    if not surface.serves_tracked_entities():
        raise NoPublishedSubjectTypeError(EVENTS_SURFACE_NAME)
    return reader


async def _record(reader: RegisterReader, tracked_entity_uid: str) -> TrackedEntityRecord:
    """Read one entity's whole record, or refuse a UID the instance holds nobody under."""
    try:
        record = await fetch_tracked_entity_record(reader, tracked_entity_uid)
    except Dhis2ClientError as error:
        raise UpstreamError(
            f"the DHIS2 instance did not answer the tracked entity read: {upstream_refusal_text(error)}"
        ) from error
    if record is None:
        raise NotFoundError(TRACKED_ENTITY_NAME, tracked_entity_uid)
    return record


def _projection(request: Request) -> RecordProjection:
    """What this request projects the record through: the project's names, its served forms, its zone.

    The naming and the index cache are the capture path's own, which is the point: the forms a record
    is read through are the forms a submission is checked against, so one form can never type a value
    one way on the way in and another on the way out.
    """
    context = serve_context(request)
    state = capture_state(request)
    return RecordProjection(
        naming=state.naming,
        store=context.store,
        indexes=state.indexes,
        timezone=context.project.config.generate.timezone,
    )


def _require_answerable_parameters(request: Request) -> None:
    """Refuse a record read naming a parameter this surface cannot apply to it."""
    for name in request.query_params:
        if name not in ANSWERED_PARAMETERS:
            raise UnsupportedSearchParameterError(EVENTS_SURFACE_NAME, name, ANSWERED_PARAMETERS)


def _requested_count(request: Request) -> int:
    """How many events this page carries: what the client asked for, bounded by what the project allows.

    The bounds are the register's own - `[serve.tracked_entities] page_size` and `page_size_limit` -
    because they are what an operator already wrote down for how much of the instance this server hands
    over at once, and a record is the same question asked about one subject.
    """
    tracked_entities = serve_context(request).register_surface.tracked_entities
    cap = requested_entry_cap(request.query_params.get(COUNT_PARAMETER))
    return tracked_entities.page_size if cap is None else min(cap, tracked_entities.page_size_limit)


def _page_of(events: tuple[RecordedEvent, ...], cursor: SpoolCursor, count: int) -> RecordPage:
    """Slice one page out of the ordered record, and name the pages either side of it.

    An offset past the end is an empty page rather than a refusal, for the reason the receipts listing
    gives: a link minted before an event was deleted has become a page with nothing on it, and that is
    a true statement about the record rather than a malformed request.
    """
    offset = min(cursor.offset, len(events))
    page = events[offset : offset + count]
    following = offset + len(page)
    return RecordPage(
        events=page,
        total=len(events),
        cursor=SpoolCursor(offset=offset),
        next_cursor=SpoolCursor(offset=following) if following < len(events) else None,
        previous_cursor=SpoolCursor(offset=max(offset - count, 0)) if offset > 0 else None,
    )


def _record_length(service_base: str, tracked_entity_uid: str, total: int) -> Response:
    """Answer `_count=0` with how many events the record holds and none of them.

    Built here rather than through the store's `total_only_response`, because that one names the
    searched resource type in the `self` link and this record is not read at a resource type's
    address - a link naming one would send a client somewhere this server does not answer.
    """
    query = urlencode([(COUNT_PARAMETER, "0")])
    bundle = Bundle(
        type="searchset",
        total=total,
        link=[BundleLink(relation="self", url=f"{service_base}{_events_path(tracked_entity_uid)}?{query}")],
    )
    return Response(content=bundle.model_dump_json(exclude_none=True, by_alias=True), media_type=FHIR_JSON_MEDIA_TYPE)


def _links(service_base: str, tracked_entity_uid: str, page: RecordPage, count: int) -> list[BundleLink]:
    """`self`, and the neighbours that exist - each naming the page it leads to, explicitly."""
    links = [BundleLink(relation="self", url=_page_url(service_base, tracked_entity_uid, page.cursor, count))]
    if page.previous_cursor is not None:
        previous = _page_url(service_base, tracked_entity_uid, page.previous_cursor, count)
        links.append(BundleLink(relation="previous", url=previous))
    if page.next_cursor is not None:
        links.append(
            BundleLink(relation="next", url=_page_url(service_base, tracked_entity_uid, page.next_cursor, count))
        )
    return links


def _page_url(service_base: str, tracked_entity_uid: str, cursor: SpoolCursor, count: int) -> str:
    """One page of the record as a client may ask for it again and be given the same page."""
    query = urlencode([(COUNT_PARAMETER, str(count)), (PAGE_PARAMETER, cursor.token())])
    return f"{service_base}{_events_path(tracked_entity_uid)}?{query}"


def _entry(service_base: str, tracked_entity_uid: str, response: QuestionnaireResponse) -> BundleEntry:
    """Carry one projected event into the result set at the URL this server serves it from."""
    return BundleEntry(
        fullUrl=f"{service_base}{_events_path(tracked_entity_uid)}/{response.id}",
        resource=json_resource(response),
        search=BundleEntrySearch(mode="match"),
    )


def _events_path(tracked_entity_uid: str) -> str:
    """Where one entity's record is served, as a path a link can be built from."""
    return TRACKED_ENTITY_EVENTS_PATH.format(tracked_entity_uid=tracked_entity_uid)


def _unpublished_stage_entries(projected: ProjectedRecord) -> list[BundleEntry]:
    """The `outcome` entry a page carrying events of an unpublished stage closes with, or nothing.

    `information` severity and the `informational` code, because nothing went wrong: the instance holds
    events of a program stage this project's guide does not publish a form for, and there is no
    document to serve them as. The entry is not a match and does not count toward `total`, which is
    where those events are counted.
    """
    if not projected.unpublished_stage_uids:
        return []
    stages = ", ".join(projected.unpublished_stage_uids)
    return [
        BundleEntry(
            resource=json_resource(
                OperationOutcome(
                    issue=[
                        OperationOutcomeIssue(
                            severity="information",
                            code="informational",
                            diagnostics=(
                                f"{pluralize(projected.unprojected_events, 'event')} on this page "
                                f"{verb_for_count(projected.unprojected_events, 'is', 'are')} of a program stage "
                                f"this guide publishes no form for ({stages}), so this server holds no document "
                                "to serve them as. They are counted in the total, because the instance holds "
                                "them: generate the stage's Questionnaire to read them here."
                            ),
                        )
                    ]
                )
            ),
            search=BundleEntrySearch(mode="outcome"),
        )
    ]
