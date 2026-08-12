"""Paging the register: how `GET /Patient` with no identifier walks the instance, one page at a time.

WHAT PAGES ARE NAMED WITH. FHIR fixes `_count` as the number of resources a client wants on a page
and leaves the naming of the page itself to the server - "the parameters used to continue a search
are implementation defined" (R4 3.1.1.4, `Bundle.link`). This server names it `page`, so a page of
the listing is `GET /Patient?_count=20&page=<token>`, and a client's whole job is to follow the
`next` and `previous` links rather than to build either parameter.

WHAT THE TOKEN IS. DHIS2 pages one tracked entity type at a time - the tracker endpoint requires a
type and offers no way to ask about two - so a listing over several configured types is several
upstream pagings walked in the order `[serve.patients] tracked_entity_types` declares them (or, when
it declares none, the order the published forms register them in). A page is therefore located by
two numbers, the type's place in that order and the upstream page number within it, plus the
searchset total once it has been counted, and the token is those folded into one opaque string:
`t{type index}p{upstream page}` with `n{total}` appended when a total is carried. `page=dDBwMg` is
type 0, page 2. It is opaque in the sense that matters - a client mints none of it, and its shape is
this server's business - and decodable in one line by whoever is reading a log.

A stateless token is the point. Nothing about a listing is remembered between requests, so a link
handed out an hour ago still resolves, and two clients walking the same listing share nothing. The
total rides the token for that reason rather than a cache: it is a fact this server counted once,
carried forward by the link rather than remembered against the client that followed it.

WHAT A PAGE HOLDS. A page never mixes tracked entity types: `_count` is a maximum, and the last
page of each type carries whatever that type had left. Filling the remainder from the next type
would cost a second upstream request per page and put two kinds of person in one page for no gain a
client asked for. A configured type that holds nobody is skipped rather than served as an empty
page, so a `next` link never lands somewhere with nothing on it while people remain further on.

WHAT `total` MEANS. `Bundle.total` is the number of people in the whole searchset, and DHIS2 states
one per type. With a single type in scope that is the same number, and every page of the listing
already carries it. With several, the searchset's total is the sum of one count per type, and this
server asks for those counts rather than declining to state a number it can get: one count-only
request per type, bounded by how many types the project put in scope, spent on the first page of a
walk and carried through the rest on the page token. A type whose pager states no total makes the
sum unknowable, and then the Bundle states no total - which is the instance's silence, not this
server's choice.
"""

from __future__ import annotations

import base64
import binascii
import re
from typing import TYPE_CHECKING

from dhis2w_client.generated.v42.oas import TrackerTrackedEntity
from pydantic import BaseModel, ConfigDict

from dhis2w_fhir_serve.errors import BadSearchError
from dhis2w_fhir_serve.patients.wire import (
    TrackedEntitiesPage,
    count_tracked_entities,
    count_tracked_entity_pages,
    list_tracked_entities,
)

if TYPE_CHECKING:
    from dhis2w_client import Dhis2Client

#: The search parameter carrying the cursor, and the FHIR-defined one carrying the page size.
PAGE_PARAMETER = "page"
COUNT_PARAMETER = "_count"

#: The decoded shape of a cursor token: which configured type, which page of it, and the searchset
#: total when one has been counted.
_CURSOR_PATTERN = re.compile(r"^t(\d+)p(\d+)(?:n(\d+))?$")

#: What a `page` value this server did not mint is answered with - it is a link to follow, not a number.
_UNREADABLE_CURSOR = (
    "`page` is not a page of this search: its value comes from the `next` or `previous` link of a "
    "result, and is not a number a client composes"
)


class ListingCursor(BaseModel):
    """Where one page of the listing sits, and the searchset total counted before it was reached."""

    model_config = ConfigDict(frozen=True)

    type_index: int = 0
    upstream_page: int = 1
    searchset_total: int | None = None
    """How many people the whole searchset holds, once a page of this walk has counted them.

    Absent on the cursor a client starts from, which is what makes the first page do the counting.
    A single type in scope never fills it: that walk reads the total off every page's own pager, so
    there is nothing to carry.
    """

    @classmethod
    def from_token(cls, token: str) -> ListingCursor:
        """Read one `page` token, refusing anything this server did not mint."""
        try:
            decoded = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4)).decode("ascii")
        except (binascii.Error, UnicodeDecodeError, ValueError) as error:
            raise BadSearchError(_UNREADABLE_CURSOR) from error
        match = _CURSOR_PATTERN.match(decoded)
        if match is None:
            raise BadSearchError(_UNREADABLE_CURSOR)
        upstream_page = int(match.group(2))
        if upstream_page < 1:
            raise BadSearchError(_UNREADABLE_CURSOR)
        total = match.group(3)
        return cls(
            type_index=int(match.group(1)),
            upstream_page=upstream_page,
            searchset_total=None if total is None else int(total),
        )

    def token(self) -> str:
        """This cursor as the `page` parameter carries it."""
        counted = "" if self.searchset_total is None else f"n{self.searchset_total}"
        decoded = f"t{self.type_index}p{self.upstream_page}{counted}"
        return base64.urlsafe_b64encode(decoded.encode("ascii")).decode().rstrip("=")


class PatientListingPage(BaseModel):
    """One page of the register: who is on it, where it is, and where the pages either side of it are."""

    model_config = ConfigDict(frozen=True)

    entities: list[TrackerTrackedEntity] = []
    cursor: ListingCursor = ListingCursor()
    """Where the people on this page actually came from, which is what the `self` link names."""

    total: int | None = None
    """How many people the whole searchset holds, when the instance stated it for all of it."""

    next_cursor: ListingCursor | None = None
    previous_cursor: ListingCursor | None = None


async def read_listing_page(
    client: Dhis2Client,
    *,
    tracked_entity_type_uids: tuple[str, ...],
    cursor: ListingCursor,
    count: int,
) -> PatientListingPage:
    """Read the page one cursor names, skipping forward over any configured type that holds nobody.

    Running off the end of the type list is an empty page rather than a refusal: a link minted before
    the register was emptied, or before a type left `[serve.patients]`, has become a page with nobody
    on it, and that is what a searchset says when the query is unsatisfied rather than malformed.
    """
    type_index = cursor.type_index
    upstream_page = cursor.upstream_page
    read: TrackedEntitiesPage | None = None
    while type_index < len(tracked_entity_type_uids):
        read = await list_tracked_entities(
            client,
            tracked_entity_type_uid=tracked_entity_type_uids[type_index],
            page=upstream_page,
            page_size=count,
        )
        if read.trackedEntities:
            total = await _searchset_total(client, read, tracked_entity_type_uids, cursor)
            reached = ListingCursor(
                type_index=type_index, upstream_page=upstream_page, searchset_total=cursor.searchset_total
            )
            return PatientListingPage(
                entities=read.trackedEntities,
                cursor=reached,
                total=total,
                next_cursor=_next_cursor(reached, read, count, len(tracked_entity_type_uids), total),
                previous_cursor=await _previous_cursor(client, reached, tracked_entity_type_uids, count, total),
            )
        type_index += 1
        upstream_page = 1
    total = None if read is None else await _searchset_total(client, read, tracked_entity_type_uids, cursor)
    return PatientListingPage(
        cursor=cursor,
        total=total,
        previous_cursor=await _previous_cursor(client, cursor, tracked_entity_type_uids, count, total),
    )


async def _searchset_total(
    client: Dhis2Client,
    page: TrackedEntitiesPage,
    tracked_entity_type_uids: tuple[str, ...],
    cursor: ListingCursor,
) -> int | None:
    """How many people the whole searchset holds, counted once per walk and reused afterwards.

    One type in scope is the free case: its page already states the total of the only type there is.
    Several types is the counted one - one count-only request per type, summed - and the sum is
    spent on the page that first needs it and then rides the page tokens of the links this page
    hands out. A type whose pager states no total leaves the sum unknowable, and an unknowable sum
    is stated as no total rather than as a partial one.
    """
    if len(tracked_entity_type_uids) <= 1:
        return None if page.pager is None else page.pager.total
    if cursor.searchset_total is not None:
        return cursor.searchset_total
    counted = 0
    for tracked_entity_type_uid in tracked_entity_type_uids:
        total = await count_tracked_entities(client, tracked_entity_type_uid=tracked_entity_type_uid)
        if total is None:
            return None
        counted += total
    return counted


def _next_cursor(
    cursor: ListingCursor,
    page: TrackedEntitiesPage,
    count: int,
    type_count: int,
    searchset_total: int | None,
) -> ListingCursor | None:
    """The page after this one: the next page of this type, else the first page of the next type.

    How many pages the type has is what the instance stated, and the listing always asks for it. An
    answer carrying no pager at all - a proxy that dropped it - is read off the page itself instead:
    a full page may have more behind it, a short one is the end of the type. Both readings are safe,
    because a page the cursor reaches with nobody on it is skipped forward to the next type.
    """
    carried = searchset_total if type_count > 1 else None
    page_count = None if page.pager is None else page.pager.pageCount
    more_of_this_type = len(page.trackedEntities) >= count if page_count is None else cursor.upstream_page < page_count
    if more_of_this_type:
        return ListingCursor(
            type_index=cursor.type_index, upstream_page=cursor.upstream_page + 1, searchset_total=carried
        )
    if cursor.type_index + 1 < type_count:
        return ListingCursor(type_index=cursor.type_index + 1, searchset_total=carried)
    return None


async def _previous_cursor(
    client: Dhis2Client,
    cursor: ListingCursor,
    tracked_entity_type_uids: tuple[str, ...],
    count: int,
    searchset_total: int | None,
) -> ListingCursor | None:
    """The page before this one, which across a type boundary is the last page of the type before it.

    Nothing on this page states how many pages the preceding type has, so that one number is asked
    for - once, and only on the first page of a type that is not the first. Walking back over types
    that hold nobody mirrors the forward skip, so a client stepping back lands where stepping
    forward again would return it to.
    """
    carried = searchset_total if len(tracked_entity_type_uids) > 1 else None
    if cursor.upstream_page > 1:
        return ListingCursor(
            type_index=cursor.type_index, upstream_page=cursor.upstream_page - 1, searchset_total=carried
        )
    for preceding in range(min(cursor.type_index, len(tracked_entity_type_uids)) - 1, -1, -1):
        page_count = await count_tracked_entity_pages(
            client, tracked_entity_type_uid=tracked_entity_type_uids[preceding], page_size=count
        )
        if page_count > 0:
            return ListingCursor(type_index=preceding, upstream_page=page_count, searchset_total=carried)
    return None
