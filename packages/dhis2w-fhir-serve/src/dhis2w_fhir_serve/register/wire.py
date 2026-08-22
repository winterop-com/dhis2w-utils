"""The DHIS2 reads behind a register lookup, and the contract `/api/tracker/trackedEntities` actually holds to.

Five facts decide every request here, the first four established against a running instance and
recorded in the repository's `BUGS.md`:

1. **A search names a tracked entity type or a program, or it is refused** with `E1003`. The type
   comes from the published forms (`dhis2w_fhir_serve.register.index`); a program is never named,
   for the reason in point 3.
2. **A unique attribute gets no org-unit-scope exemption** (BUGS.md 74). The legacy documentation
   describes a unique value as an instance-wide key; the tracker endpoint scopes it like any other
   filter, so a lookup scoped to the capture unit misses exactly the entities identifier search
   exists to find. Every search here therefore sends `ouMode=ACCESSIBLE`: as wide as the requesting
   user may see, and no wider.
3. **An entity-scoped read with a program the entity is not enrolled in answers 404 `E1005`,
   claiming the tracked entity does not exist** (BUGS.md 72). So nothing here ever probes by
   program. The enrollments are read off the entity itself, without `program=`, and inspected here.
4. **The default projection omits the enrollments entirely**, and folds no program-level attribute
   value into the entity's own `attributes`. Both are field-selection defaults rather than
   statements about the person, so every read names its `fields` explicitly - including
   `enrollments[...]` and the attribute values those enrollments carry, without which a person
   found by a program attribute's unique value would come back not carrying it.
5. **A page states how many pages there are only when it is asked to.** `page` and `pageSize` come
   back on every request; `total` and `pageCount` come back only under `totalPages=true`, on 2.42
   and 2.43 alike. The listing asks for it, because a searchset that states a total is worth one
   count of a table DHIS2 has indexed; a lookup does not, because nobody asks an identifier search
   how many tracked entities the instance holds.

WHAT `reader` IS HERE IS THE POINT OF THE PARAMETER. Every read below takes a `RegisterReader` - one
raw GET answering parsed JSON - and never a `Dhis2Client`, because whose credentials a register read
runs under is settled per request rather than per process. Under `[serve] auth = "dhis2"` it is the
caller's own header on the process's credential-free pool; under `none` and `token` it is the
runtime's client, which `Dhis2Client` satisfies as it stands. `dhis2w_fhir_serve.passthrough` states
which is which, and nothing in this module branches on the answer.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import TYPE_CHECKING, Any

from dhis2w_client.errors import Dhis2ApiError
from dhis2w_client.generated.v42.oas import TrackerEnrollment, TrackerTrackedEntity
from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from dhis2w_fhir_serve.passthrough import RegisterReader

#: The tracker endpoint a lookup reads, and the one-entity form of it.
TRACKED_ENTITIES_PATH = "/api/tracker/trackedEntities"

#: What DHIS2 will accept in the UID slot of a path. A value of any other shape is refused with a
#: 400 naming the rule, so a lookup checks the shape here instead of spending a round trip to be
#: told - and a search value that is plainly not a UID is never read as one.
_DHIS2_UID_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9]{10}$")

#: The org-unit scope every search runs under - as wide as the requesting user may see (BUGS.md 74).
SEARCH_ORG_UNIT_MODE = "ACCESSIBLE"

#: How many rows one identifier lookup will carry back. An identifier is meant to name one entity;
#: a page this size is enough to show a client that its instance disagrees.
SEARCH_PAGE_SIZE = 50

#: The projection every read asks for. Named in full because the endpoint's default omits the
#: enrollments and the attribute values they carry - see this module's docstring, point 4.
_ATTRIBUTE_FIELDS = "attribute,code,displayName,value,valueType"
_ENROLLMENT_FIELDS = f"enrollment,program,status,enrolledAt,orgUnit,attributes[{_ATTRIBUTE_FIELDS}]"
TRACKED_ENTITY_FIELDS = (
    f"trackedEntity,trackedEntityType,orgUnit,attributes[{_ATTRIBUTE_FIELDS}],enrollments[{_ENROLLMENT_FIELDS}]"
)


#: The parameter that makes the tracker endpoint count the result set, and what it adds to the page.
#:
#: Verified against 2.42 and 2.43: `totalPages=true` puts `total` and `pageCount` in the `pager`
#: object beside `page` and `pageSize`, and without it the pager carries neither. The endpoint counts
#: the whole set to answer it, so it is asked for only by the listing, which states a Bundle total -
#: an identifier lookup wants the entities, not how many the instance holds.
TOTAL_PAGES_PARAMETER = "totalPages"

#: The projection a page of the listing asks for when it only needs a number off the pager.
_COUNT_ONLY_FIELDS = "trackedEntity"

#: The page size a count-only call asks for: the pager states the count whatever the page holds,
#: so one row is the smallest page DHIS2 will build to answer it.
_COUNT_ONLY_PAGE_SIZE = 1


class TrackedEntitiesPager(BaseModel):
    """Where one tracker page sits in its result set, as `totalPages=true` states it.

    `total` and `pageCount` are absent unless that parameter was passed, so both are optional here
    rather than defaulted to zero: "the instance did not say" and "the instance said none" are
    different answers, and a Bundle states a total only for the first.
    """

    model_config = ConfigDict(extra="allow")

    page: int | None = None
    pageSize: int | None = None
    total: int | None = None
    pageCount: int | None = None


class TrackedEntitiesPage(BaseModel):
    """One page of `/api/tracker/trackedEntities`: the entities on it, and where it sits."""

    model_config = ConfigDict(extra="allow")

    trackedEntities: list[TrackerTrackedEntity] = []
    pager: TrackedEntitiesPager | None = None


def upstream_refusal_text(error: Exception) -> str:
    """What DHIS2 said, for an operator-facing diagnostic - the body's message when the status line has none.

    DHIS2 sends an empty HTTP reason phrase, so `str(error)` can end at a bare colon while the
    refusal's actual cause sits in the JSON body; a diagnostic that names no cause is worse than
    the refusal itself. A transport error keeps its own text.
    """
    text = str(error)
    if not isinstance(error, Dhis2ApiError) or error.message:
        return text
    body = error.body if isinstance(error.body, dict) else {}
    body_message = str(body.get("message", "")).strip()
    return f"{text}{body_message}" if body_message else text


def _is_unknown_type_refusal(error: Dhis2ApiError) -> bool:
    """Whether DHIS2 refused because the named tracked entity type does not exist on the instance.

    A configured `[serve.tracked_entities] tracked_entity_types` uid is a string in a file no instance has
    checked, and DHIS2 answers a 400 naming the absent type rather than an empty page. The serving
    guide promises a mistyped id shows up as a surface that finds nothing, so the callers here fold
    this one refusal into an empty answer instead of a dead surface.
    """
    if error.status_code != 400:
        return False
    body = error.body if isinstance(error.body, dict) else {}
    message = str(body.get("message", ""))
    return body.get("errorCode") == "E1003" and "does not exist" in message


async def list_tracked_entities(
    reader: RegisterReader,
    *,
    tracked_entity_type_uid: str,
    page: int,
    page_size: int,
) -> TrackedEntitiesPage:
    """Read one page of one tracked entity type, counted so the page can say how many.

    No `filter=`: this is the listing, and its whole query is the type. `ouMode=ACCESSIBLE` for the
    same reason every search here sends it (BUGS.md 74) - the register a user may see is the register
    they are shown, and a listing scoped to the capture unit would answer a fraction of it without
    saying so. A type the instance does not hold answers an empty page, not a refusal.
    """
    try:
        raw = await reader.get_raw(
            TRACKED_ENTITIES_PATH,
            params={
                "trackedEntityType": tracked_entity_type_uid,
                "ouMode": SEARCH_ORG_UNIT_MODE,
                "fields": TRACKED_ENTITY_FIELDS,
                "page": page,
                "pageSize": page_size,
                TOTAL_PAGES_PARAMETER: "true",
            },
        )
    except Dhis2ApiError as error:
        if _is_unknown_type_refusal(error):
            return TrackedEntitiesPage()
        raise
    return TrackedEntitiesPage.model_validate(raw)


async def count_tracked_entity_pages(reader: RegisterReader, *, tracked_entity_type_uid: str, page_size: int) -> int:
    """How many pages of one type there are at one page size, asked without carrying anybody back.

    The listing needs this at one place only: a `previous` link crossing back over a type boundary
    lands on the last page of the type before it, and the last page is a number nothing on the
    current page states. The projection is the UID alone, because the answer read is the pager.
    A type the instance does not hold counts zero pages.
    """
    try:
        raw = await reader.get_raw(
            TRACKED_ENTITIES_PATH,
            params={
                "trackedEntityType": tracked_entity_type_uid,
                "ouMode": SEARCH_ORG_UNIT_MODE,
                "fields": _COUNT_ONLY_FIELDS,
                "page": 1,
                "pageSize": page_size,
                TOTAL_PAGES_PARAMETER: "true",
            },
        )
    except Dhis2ApiError as error:
        if _is_unknown_type_refusal(error):
            return 0
        raise
    pager = TrackedEntitiesPage.model_validate(raw).pager
    return 0 if pager is None or pager.pageCount is None else pager.pageCount


async def count_tracked_entities(reader: RegisterReader, *, tracked_entity_type_uid: str) -> int | None:
    """How many entities one tracked entity type holds, asked without carrying any of them back.

    The listing needs this when several types are in scope: DHIS2 counts one type at a time, so the
    searchset's total is the sum of one count per type, and a count is what this asks for - the UID
    projection at a page size of one, reading the pager and dropping the page. None means the
    instance stated no total, which is a different answer from a total of zero and stays different
    all the way to the Bundle. A type the instance does not hold holds nothing, so it counts zero.
    """
    try:
        raw = await reader.get_raw(
            TRACKED_ENTITIES_PATH,
            params={
                "trackedEntityType": tracked_entity_type_uid,
                "ouMode": SEARCH_ORG_UNIT_MODE,
                "fields": _COUNT_ONLY_FIELDS,
                "page": 1,
                "pageSize": _COUNT_ONLY_PAGE_SIZE,
                TOTAL_PAGES_PARAMETER: "true",
            },
        )
    except Dhis2ApiError as error:
        if _is_unknown_type_refusal(error):
            return 0
        raise
    pager = TrackedEntitiesPage.model_validate(raw).pager
    return None if pager is None else pager.total


async def search_tracked_entities(
    reader: RegisterReader,
    *,
    tracked_entity_type_uid: str,
    attribute_uid: str,
    value: str,
) -> list[TrackerTrackedEntity]:
    """Find every tracked entity of one type whose attribute holds one exact value.

    A type the instance does not hold matches nothing, not a refusal.
    """
    try:
        raw = await reader.get_raw(
            TRACKED_ENTITIES_PATH,
            params={
                "trackedEntityType": tracked_entity_type_uid,
                "filter": f"{attribute_uid}:eq:{value}",
                "ouMode": SEARCH_ORG_UNIT_MODE,
                "fields": TRACKED_ENTITY_FIELDS,
                "pageSize": SEARCH_PAGE_SIZE,
            },
        )
    except Dhis2ApiError as error:
        if _is_unknown_type_refusal(error):
            return []
        raise
    return TrackedEntitiesPage.model_validate(raw).trackedEntities


#: The other two tracker collections, and what a sync poll asks each of them for.
#:
#: `/api/tracker/enrollments` is the only one polled beside the tracked entities, and it is polled for
#: whose projection has gone stale rather than for anything it holds: a program-level attribute value
#: rides an enrollment, and a tracked entity's own `lastUpdated` does not move when one of its
#: enrollments does. `/api/tracker/events` is not polled at all - see `ProjectionEndpoint`.
ENROLLMENTS_PATH = "/api/tracker/enrollments"
_TOUCHED_ENROLLMENT_FIELDS = "enrollment,trackedEntity,updatedAt,deleted"

#: The parameter that makes a poll see a deletion, and it is a CONSTANT rather than a dial.
#:
#: `docs/fhir/design/projection.md` section 3.4, finding 2: without it a cursor poll returns zero rows
#: for a deleted entity and does not error, so a sync that forgot it would simply never learn that
#: anybody left. R10 makes it a constant for exactly that reason - its absence is silent, and the
#: single most dangerous line in a sync is the one that can be switched off by accident.
INCLUDE_DELETED_PARAMETER = "includeDeleted"

#: The cursor parameter a poll narrows itself with, in the instance's own zone-less spelling.
UPDATED_AFTER_PARAMETER = "updatedAfter"

#: The order every poll pages in.
#:
#: `createdAt` and not `updatedAt`, because paging needs an order that does not move underneath the
#: walk: an entity updated between page 2 and page 3 of a poll ordered by `updatedAt` moves to the
#: end and takes a row with it. `createdAt` is immutable per row, and which rows the walk covers is
#: the `updatedAfter` filter's job rather than the sort's.
POLL_ORDER = "createdAt:asc"

#: How many rows one poll page carries. The paper's section 3.2 measured 200 as the size where the
#: page count stops being what the walk costs (0.595 s for 800 people over five pages).
POLL_PAGE_SIZE = 200

#: The projection a poll asks for: the register's own fields, plus the two a cursor sync reads.
POLLED_TRACKED_ENTITY_FIELDS = f"{TRACKED_ENTITY_FIELDS},updatedAt,deleted"


class TouchedRow(BaseModel):
    """One row of an enrollment poll: whose projection it touches, when, and whether it is a tombstone."""

    model_config = ConfigDict(frozen=True)

    tracked_entity_uid: str | None = None
    updated_at: datetime | None = None
    deleted: bool = False


class TouchedPage(BaseModel):
    """One page of an enrollment poll, and how many pages the instance said there are."""

    model_config = ConfigDict(frozen=True)

    rows: tuple[TouchedRow, ...] = ()
    page_count: int | None = None


class EnrollmentsPage(BaseModel):
    """One page of `/api/tracker/enrollments`: the enrollments on it, and where it sits."""

    model_config = ConfigDict(extra="allow")

    enrollments: list[TrackerEnrollment] = []
    pager: TrackedEntitiesPager | None = None


async def poll_tracked_entities(
    reader: RegisterReader,
    *,
    tracked_entity_type_uid: str,
    updated_after: datetime | None,
    page: int,
    page_size: int = POLL_PAGE_SIZE,
) -> TrackedEntitiesPage:
    """Read one page of one tracked entity type as a sync polls it - tombstones included, always.

    `includeDeleted=true` rides every call and is not a parameter: without it a deleted entity is
    invisible to a cursor poll and nothing says so (section 3.4, finding 2). `updated_after` None is
    the initial full materialization, which reads the type whole.

    A type the instance does not hold answers an empty page, not a refusal - the same fold every
    other read here applies, because a mistyped UID in `[serve.tracked_entities]` should show up as a
    surface that finds nothing.
    """
    params: dict[str, Any] = {
        "trackedEntityType": tracked_entity_type_uid,
        "ouMode": SEARCH_ORG_UNIT_MODE,
        "fields": POLLED_TRACKED_ENTITY_FIELDS,
        "order": POLL_ORDER,
        "page": page,
        "pageSize": page_size,
        INCLUDE_DELETED_PARAMETER: "true",
        TOTAL_PAGES_PARAMETER: "true",
    }
    if updated_after is not None:
        params[UPDATED_AFTER_PARAMETER] = dhis2_instant(updated_after)
    try:
        raw = await reader.get_raw(TRACKED_ENTITIES_PATH, params=params)
    except Dhis2ApiError as error:
        if _is_unknown_type_refusal(error):
            return TrackedEntitiesPage()
        raise
    return TrackedEntitiesPage.model_validate(raw)


async def poll_enrollments(
    reader: RegisterReader,
    *,
    program_uid: str,
    updated_after: datetime | None,
    page: int,
    page_size: int = POLL_PAGE_SIZE,
) -> TouchedPage:
    """Read one page of one program's enrollments as a sync polls it, for whose projection moved.

    SCOPED BY PROGRAM BECAUSE THE ENDPOINT ADMITS NOTHING ELSE. `/api/tracker/enrollments` answers
    `E1003 "Program is mandatory"` to a query naming a tracked entity type, or naming nothing at all,
    so an enrollment poll walks the programs the guide publishes rather than the types the register
    serves. Recorded as BUGS.md 102 alongside its sibling's refusal, which is not even JSON.

    Only three fields are asked for. This poll never maps anything: what it answers is a list of
    tracked entities whose projection is stale, and each of them is re-read through the tracked
    entity path that every other projected row comes from, so there is exactly one mapping surface.
    """
    params: dict[str, Any] = {
        "program": program_uid,
        "ouMode": SEARCH_ORG_UNIT_MODE,
        "fields": _TOUCHED_ENROLLMENT_FIELDS,
        "order": POLL_ORDER,
        "page": page,
        "pageSize": page_size,
        INCLUDE_DELETED_PARAMETER: "true",
        TOTAL_PAGES_PARAMETER: "true",
    }
    if updated_after is not None:
        params[UPDATED_AFTER_PARAMETER] = dhis2_instant(updated_after)
    try:
        raw = await reader.get_raw(ENROLLMENTS_PATH, params=params)
    except Dhis2ApiError as error:
        if _is_unknown_type_refusal(error):
            return TouchedPage()
        raise
    page_read = EnrollmentsPage.model_validate(raw)
    return TouchedPage(
        rows=tuple(
            TouchedRow(
                tracked_entity_uid=enrollment.trackedEntity,
                updated_at=as_instant(enrollment.updatedAt),
                deleted=bool(enrollment.deleted),
            )
            for enrollment in page_read.enrollments
        ),
        page_count=None if page_read.pager is None else page_read.pager.pageCount,
    )


def as_instant(value: datetime | int | None) -> datetime | None:
    """One DHIS2 timestamp as a datetime, or None where it is not one this sync can compare against.

    The tracker's OpenAPI document types an instant as a date-time OR an epoch integer, and this repo
    does not guess which unit an integer is in (`routes.enrollments._instant` carries the same
    integer through as text for the same reason). A watermark is a comparison, so an instant nobody
    can place on a clock is one this sync declines to advance to.
    """
    return value if isinstance(value, datetime) else None


def dhis2_instant(value: datetime) -> str:
    """One instant spelled the way `updatedAfter` takes it - the instance's own zone-less reading.

    DHIS2 2.43 answers `updatedAt` as a wall-clock reading with no offset (BUGS.md 62) and takes
    `updatedAfter` in the same spelling, so a cursor read out of one answer goes back on the wire
    exactly as it arrived. Any offset this host attached would be a claim about a clock nobody
    consulted, so the value is written to seconds and the zone, if somebody attached one, is dropped.
    """
    return value.replace(tzinfo=None).isoformat(timespec="seconds")


def is_tracked_entity_uid(value: str) -> bool:
    """Whether a value could be a DHIS2 UID at all - eleven alphanumerics starting with a letter."""
    return _DHIS2_UID_PATTERN.match(value) is not None


async def fetch_tracked_entity(reader: RegisterReader, tracked_entity_uid: str) -> TrackerTrackedEntity | None:
    """Read one tracked entity by its UID, or None when the instance holds none under it.

    A value that is not UID-shaped is None without a request: DHIS2 answers 400 for one, and a
    bare identifier search tries this read for every value it is given, most of which are national
    IDs rather than UIDs.

    No `program=` parameter, ever: passing one turns "not enrolled in that program" into a 404
    asserting the tracked entity does not exist (BUGS.md 72), which would make an unenrolled person
    indistinguishable from a wrong UID.
    """
    if not is_tracked_entity_uid(tracked_entity_uid):
        return None
    try:
        raw = await reader.get_raw(
            f"{TRACKED_ENTITIES_PATH}/{tracked_entity_uid}", params={"fields": TRACKED_ENTITY_FIELDS}
        )
    except Dhis2ApiError as error:
        if error.status_code == 404:
            return None
        raise
    return TrackerTrackedEntity.model_validate(raw)
