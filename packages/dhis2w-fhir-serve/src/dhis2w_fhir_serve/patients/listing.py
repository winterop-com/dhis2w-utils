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
two numbers, the type's place in that order and the upstream page number within it, and the token
is those two folded into one opaque string: `t{type index}p{upstream page}`, base64url without
padding. `page=dDBwMg` is type 0, page 2. It is opaque in the sense that matters - a client mints
none of it, and its shape is this server's business - and decodable in one line by whoever is
reading a log.

A stateless token is the point. Nothing about a listing is remembered between requests, so a link
handed out an hour ago still resolves, and two clients walking the same listing share nothing.

WHAT A PAGE HOLDS. A page never mixes tracked entity types: `_count` is a maximum, and the last
page of each type carries whatever that type had left. Filling the remainder from the next type
would cost a second upstream request per page and put two kinds of person in one page for no gain a
client asked for. A configured type that holds nobody is skipped rather than served as an empty
page, so a `next` link never lands somewhere with nothing on it while people remain further on.

WHAT `total` MEANS. `Bundle.total` is the number of people in the whole searchset, and DHIS2 states
one per type. With a single type in scope that is the same number, and the Bundle carries it. With
several, the searchset's total is a sum of counts this server has not asked for - one extra request
per type, per page - so it states none rather than a number that is a fraction of the truth.
"""

from __future__ import annotations

import base64
import binascii
import re
from typing import TYPE_CHECKING

from dhis2w_client.generated.v42.oas import TrackerTrackedEntity
from pydantic import BaseModel, ConfigDict

from dhis2w_fhir_serve.errors import BadSearchError
from dhis2w_fhir_serve.patients.wire import TrackedEntitiesPage, count_tracked_entity_pages, list_tracked_entities

if TYPE_CHECKING:
    from dhis2w_client import Dhis2Client

#: The search parameter carrying the cursor, and the FHIR-defined one carrying the page size.
PAGE_PARAMETER = "page"
COUNT_PARAMETER = "_count"

#: The decoded shape of a cursor token: which configured type, and which page of it.
_CURSOR_PATTERN = re.compile(r"^t(\d+)p(\d+)$")

#: What a `page` value this server did not mint is answered with - it is a link to follow, not a number.
_UNREADABLE_CURSOR = (
    "`page` is not a page of this search: its value comes from the `next` or `previous` link of a "
    "result, and is not a number a client composes"
)


class ListingCursor(BaseModel):
    """Where one page of the listing sits: the type's place in the configured order, and its page."""

    model_config = ConfigDict(frozen=True)

    type_index: int = 0
    upstream_page: int = 1

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
        return cls(type_index=int(match.group(1)), upstream_page=upstream_page)

    def token(self) -> str:
        """This cursor as the `page` parameter carries it."""
        return base64.urlsafe_b64encode(f"t{self.type_index}p{self.upstream_page}".encode("ascii")).decode().rstrip("=")


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
            reached = ListingCursor(type_index=type_index, upstream_page=upstream_page)
            return PatientListingPage(
                entities=read.trackedEntities,
                cursor=reached,
                total=_searchset_total(read, tracked_entity_type_uids),
                next_cursor=_next_cursor(reached, read, count, len(tracked_entity_type_uids)),
                previous_cursor=await _previous_cursor(client, reached, tracked_entity_type_uids, count),
            )
        type_index += 1
        upstream_page = 1
    return PatientListingPage(
        cursor=cursor,
        total=None if read is None else _searchset_total(read, tracked_entity_type_uids),
        previous_cursor=await _previous_cursor(client, cursor, tracked_entity_type_uids, count),
    )


def _searchset_total(page: TrackedEntitiesPage, tracked_entity_type_uids: tuple[str, ...]) -> int | None:
    """The total of the whole searchset, which one type's total is only when one type is in scope."""
    if len(tracked_entity_type_uids) != 1 or page.pager is None:
        return None
    return page.pager.total


def _next_cursor(cursor: ListingCursor, page: TrackedEntitiesPage, count: int, type_count: int) -> ListingCursor | None:
    """The page after this one: the next page of this type, else the first page of the next type.

    How many pages the type has is what the instance stated, and the listing always asks for it. An
    answer carrying no pager at all - a proxy that dropped it - is read off the page itself instead:
    a full page may have more behind it, a short one is the end of the type. Both readings are safe,
    because a page the cursor reaches with nobody on it is skipped forward to the next type.
    """
    page_count = None if page.pager is None else page.pager.pageCount
    more_of_this_type = len(page.trackedEntities) >= count if page_count is None else cursor.upstream_page < page_count
    if more_of_this_type:
        return ListingCursor(type_index=cursor.type_index, upstream_page=cursor.upstream_page + 1)
    if cursor.type_index + 1 < type_count:
        return ListingCursor(type_index=cursor.type_index + 1)
    return None


async def _previous_cursor(
    client: Dhis2Client,
    cursor: ListingCursor,
    tracked_entity_type_uids: tuple[str, ...],
    count: int,
) -> ListingCursor | None:
    """The page before this one, which across a type boundary is the last page of the type before it.

    Nothing on this page states how many pages the preceding type has, so that one number is asked
    for - once, and only on the first page of a type that is not the first. Walking back over types
    that hold nobody mirrors the forward skip, so a client stepping back lands where stepping
    forward again would return it to.
    """
    if cursor.upstream_page > 1:
        return ListingCursor(type_index=cursor.type_index, upstream_page=cursor.upstream_page - 1)
    for preceding in range(min(cursor.type_index, len(tracked_entity_type_uids)) - 1, -1, -1):
        page_count = await count_tracked_entity_pages(
            client, tracked_entity_type_uid=tracked_entity_type_uids[preceding], page_size=count
        )
        if page_count > 0:
            return ListingCursor(type_index=preceding, upstream_page=page_count)
    return None
