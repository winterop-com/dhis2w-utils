"""The register: `GET /{resourceType}` and `GET /{resourceType}/{id}` answered from the DHIS2 instance.

These are the resource types this server answers from DHIS2 rather than from what it loaded at
startup, and the only ones whose answer can differ between two requests a second apart. Which types
they are is the published `D2TET_CM`'s to say: one row per tracked entity type the project's forms
register, each naming the FHIR resource its registrations are served as. A project tracking people
alone serves `Patient` and nothing else here; a project that also tracks samples serves `Specimen`
beside it, over exactly the types the map puts there. `dhis2w_fhir_serve.routes.read` dispatches to
this module for those types and answers from the store for every other, so there is one pair of
catch-all routes rather than a pair per resource.

**One implementation, parameterized by resource type.** Nothing below branches on which resource is
being answered. A `Specimen` is searched by the same identifier grammar, paged by the same cursor,
and projected by the same rule as a `Patient` - see `dhis2w_fhir_serve.register.projection` for why
that projection states no resource-specific element for any of them.

**Whose data this is depends on who asked.** Under `[serve] auth = "dhis2"` every read below carries
the CALLER'S own `Authorization` header to the instance, so DHIS2's sharing, organisation-unit
scopes, ownership, and access levels decide what comes back, per caller, and this module applies no
rule of its own. Under `none` and `token` the reads run over the runtime's client and answer with
that profile's rights. `dhis2w_fhir_serve.passthrough` is where that is decided and why.

**Live mode only.** The default mode serves a compiled guide and holds no DHIS2 client, so there is
no instance to ask; it answers a `not-supported` OperationOutcome saying so, and `/metadata`
declares none of these types, which is the same fact stated ahead of the request. A live process
whose project publishes no registration form answers the same way for the same reason one step
further in: with no published tracked entity type, `/api/tracker/trackedEntities` has nothing to be
given and refuses the query (`E1003`).

**`[serve.tracked_entities]` says how much of this surface exists.** `enabled = false` refuses every
route here and declares no register type at `/metadata`, which is the compiled-mode posture arrived
at from the project rather than from the invocation - and it is checked first, because a project that
serves no tracked entity serves none whichever way the process was started. `listing = false` refuses
the no-identifier request alone and leaves identifier search exactly as it is. Both refusals name the
key that produced them, so an operator reading the outcome knows which line to change.

**A request naming no `identifier` is the listing**: a paged searchset over the tracked entity types
that resource is served over, which `dhis2w_fhir_serve.register.listing` walks and links. `_count` is
honoured up to `[serve.tracked_entities] page_size_limit` and clamped rather than refused above it,
and `_count=0` asks how large the register is - answered by counting the instance rather than by
building a page nobody wants.

**A parameter this surface cannot apply is refused, and that is the whole reason `search_register`
reads the query rather than filtering it.** The store searches ignore what they do not recognise,
because the worst an ignored parameter costs there is a larger result set than a client expected.
Here it costs the register itself: `family=Smith` answered with the listing is every registered
person handed back as though each were a Smith. So the query is checked before anything is read, and
anything but `identifier` (plus `_count`, and `page` on the listing) is a 400 naming what is
answered. See `_require_answerable_parameters`.

**`identifier` is the whole search surface** for naming one entity, in both of FHIR's token forms:

- `identifier={system}|{value}` names which key the value is. `{base}/id/tracked-entity` is the
  tracked entity UID itself and is answered by reading that one entity, not by filtering - a UID is
  not an attribute and no `filter=` expression could ask for it. Every other system names one
  tracked entity attribute the guide publishes, and the search filters on it.
- `identifier={value}` names no key, so every key is tried: the UID read plus one filtered search
  per key attribute, folded into one result set and deduplicated by tracked entity UID. An entity
  holding the same value in two of them appears once.

Which attributes are keys is the surface's answer, not this module's: by default the ones DHIS2
declares unique or searchable, and the ones `[serve.tracked_entities] search_attributes` names when
it names any. A searchable non-unique attribute matching several entities is answered with all of
them - a searchset carries as many matches as there are, and a register listing is already the shape
that renders them.

A system this guide publishes nothing for matches nothing, and answers an empty searchset rather
than an error: FHIR's search semantics make an unmatched token an empty result, and a 404 would
tell a client its query was malformed when it was merely unsatisfied. Empty is likewise what an
identifier nothing holds answers - never a 404, which on a search path would mean the endpoint
does not exist.

Searching across every tracked entity type one resource is served over is deliberate. DHIS2 requires
exactly one type per query, so a resource carrying two of them costs two requests per key; that is
the price of not making a client know which type its identifier belongs to.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import urlencode

from dhis2w_client.errors import Dhis2ClientError
from dhis2w_fhir.r4 import Bundle, BundleEntry, BundleEntrySearch, BundleLink, json_resource
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from dhis2w_fhir_serve.errors import (
    FHIR_JSON_MEDIA_TYPE,
    BadSearchError,
    NoPublishedSubjectTypeError,
    NotFoundError,
    NotServedError,
    NotServedFromCompiledIgError,
    RegisterDisabledError,
    RegisterListingDisabledError,
    UnsupportedSearchParameterError,
    UpstreamError,
)
from dhis2w_fhir_serve.passthrough import register_reader
from dhis2w_fhir_serve.register.listing import (
    COUNT_PARAMETER,
    PAGE_PARAMETER,
    ListingCursor,
    RegisterListingPage,
    count_listing_total,
    read_listing_page,
)
from dhis2w_fhir_serve.register.projection import registered_entity_for
from dhis2w_fhir_serve.register.wire import fetch_tracked_entity, search_tracked_entities, upstream_refusal_text
from dhis2w_fhir_serve.routes.context import serve_context
from dhis2w_fhir_serve.routes.read import (
    HonoredParameter,
    alternatives,
    base_url,
    bundle_response,
    identifier_token,
    requested_entry_cap,
    total_only_response,
)
from dhis2w_fhir_serve.store import IdentifierToken

if TYPE_CHECKING:
    from dhis2w_client.generated.v42.oas import TrackerTrackedEntity

    from dhis2w_fhir_serve.passthrough import RegisterReader
    from dhis2w_fhir_serve.register.surface import RegisterSurface

#: The one search parameter the facade answers a register lookup on.
IDENTIFIER_SEARCH_PARAMETER = "identifier"


def register_resource_types(request: Request) -> tuple[str, ...]:
    """Every resource type this process answers from the instance, which is what a read dispatches on."""
    return serve_context(request).register_surface.register_resource_types()


async def search_register(request: Request, resource_type: str) -> Response:
    """Answer the entities an identifier names, or - naming none - one page of the register."""
    reader, surface = await _live_lookup(request, resource_type)
    honored: list[HonoredParameter] = []
    tokens: list[IdentifierToken] = []
    for name, raw in request.query_params.multi_items():
        if name != IDENTIFIER_SEARCH_PARAMETER:
            continue
        tokens.extend(identifier_token(value) for value in alternatives(name, raw))
        honored.append(HonoredParameter(name=name, value=raw))
    _require_answerable_parameters(request, resource_type, searching=bool(tokens))
    service_base = base_url(request)
    if not tokens:
        return await _listing_response(request, reader, surface, resource_type, service_base)
    entities = await _matching_entities(reader, surface, resource_type, tokens)
    entries = _entries(entities, surface, resource_type, service_base)
    cap = requested_entry_cap(request.query_params.get(COUNT_PARAMETER))
    return bundle_response(service_base, resource_type, tuple(honored), entries, cap)


def _require_answerable_parameters(request: Request, resource_type: str, searching: bool) -> None:
    """Refuse a register request naming a parameter this server cannot apply to it.

    A register search is `identifier` and nothing else, so `family=Smith` is a query this facade has
    no way to run. Answering it with the listing would hand back the whole register as though every
    row in it were a Smith, and the `self` link's silence about the parameter is not a signal any
    client reads. `_count` shapes the answer on either path; `page` names a page of the listing, and
    a search naming an identifier is answered whole rather than paged.
    """
    for name in request.query_params:
        if name in {IDENTIFIER_SEARCH_PARAMETER, COUNT_PARAMETER}:
            continue
        if name == PAGE_PARAMETER:
            if not searching:
                continue
            raise BadSearchError(
                f"`{PAGE_PARAMETER}` names a page of the `{resource_type}` listing, and a search naming "
                f"`{IDENTIFIER_SEARCH_PARAMETER}` is answered whole"
            )
        raise UnsupportedSearchParameterError(resource_type, name, IDENTIFIER_SEARCH_PARAMETER)


async def read_registered_entity(request: Request, resource_type: str, tracked_entity_uid: str) -> Response:
    """Answer one entity by its DHIS2 tracked entity UID, which is what a search result links to."""
    reader, surface = await _live_lookup(request, resource_type)
    entity = await _read(reader, tracked_entity_uid)
    if entity is None or not _is_served_as(entity, surface, resource_type):
        raise NotFoundError(resource_type, tracked_entity_uid)
    registered = registered_entity_for(entity, surface.index, resource_type)
    return JSONResponse(
        content=registered.model_dump(mode="json", exclude_none=True, by_alias=True), media_type=FHIR_JSON_MEDIA_TYPE
    )


def _is_served_as(entity: TrackerTrackedEntity, surface: RegisterSurface, resource_type: str) -> bool:
    """Whether one entity's own type is served as the resource it was asked for under.

    An entity DHIS2 states no type for is answered under whatever resource was asked, because the
    only alternative is refusing to serve an entity the instance itself did not classify.
    """
    if entity.trackedEntityType is None:
        return True
    return entity.trackedEntityType in surface.tracked_entity_type_uids_for(resource_type)


async def _live_lookup(request: Request, resource_type: str) -> tuple[RegisterReader, RegisterSurface]:
    """The reader and the surface a lookup runs against, refusing every way this process serves neither.

    The config comes first: a project whose `[serve.tracked_entities]` serves nothing serves nothing
    however the process was started, so telling its operator to restart with `--live` would be advice
    that changes nothing. The resource comes last, because "this server does not serve `Specimen`" is
    only true of a process that serves the register at all.

    `register_reader` is where the posture is answered, and under `dhis2` it is also where a request
    carrying no credential is refused: what comes back is read as the caller, so a request with
    nobody to be is a 401 rather than a page read as the facade. It sits between the two because
    authenticating a caller comes before telling them what this guide publishes.
    """
    surface = serve_context(request).register_surface
    if not surface.tracked_entities.enabled:
        raise RegisterDisabledError(resource_type)
    reader = await register_reader(request)
    if reader is None:
        raise NotServedFromCompiledIgError(resource_type)
    if not surface.serves_tracked_entities():
        raise NoPublishedSubjectTypeError(resource_type)
    if not surface.tracked_entity_type_uids_for(resource_type):
        raise NotServedError(resource_type)
    return reader, surface


async def _listing_response(
    request: Request, reader: RegisterReader, surface: RegisterSurface, resource_type: str, service_base: str
) -> Response:
    """Answer one page of the register, or refuse the whole listing when the project serves none."""
    if not surface.serves_listing():
        raise RegisterListingDisabledError(resource_type)
    if requested_entry_cap(request.query_params.get(COUNT_PARAMETER)) == 0:
        return await _register_size_response(reader, surface, resource_type, service_base)
    count = _requested_count(request, surface)
    cursor = _requested_cursor(request)
    try:
        page = await read_listing_page(
            reader,
            tracked_entity_type_uids=surface.tracked_entity_type_uids_for(resource_type),
            cursor=cursor,
            count=count,
        )
    except Dhis2ClientError as error:
        raise UpstreamError(
            f"the DHIS2 instance did not answer the tracked entity listing: {upstream_refusal_text(error)}"
        ) from error
    bundle = Bundle(
        type="searchset",
        total=page.total,
        link=_listing_links(service_base, resource_type, page, count),
        entry=_entries(page.entities, surface, resource_type, service_base) or None,
    )
    return Response(content=bundle.model_dump_json(exclude_none=True, by_alias=True), media_type=FHIR_JSON_MEDIA_TYPE)


async def _register_size_response(
    reader: RegisterReader, surface: RegisterSurface, resource_type: str, service_base: str
) -> Response:
    """Answer `_count=0` with how large the register is and nobody in it.

    Nothing is paged to answer this, because there is no page to build: the count is asked of the
    instance directly, one count-only request per tracked entity type in scope, which is the same
    read a first page spends to state its total.
    """
    try:
        total = await count_listing_total(
            reader, tracked_entity_type_uids=surface.tracked_entity_type_uids_for(resource_type)
        )
    except Dhis2ClientError as error:
        raise UpstreamError(
            f"the DHIS2 instance did not answer the tracked entity count: {upstream_refusal_text(error)}"
        ) from error
    return total_only_response(service_base, resource_type, (), total)


def _requested_count(request: Request, surface: RegisterSurface) -> int:
    """How many entities this page carries: what the client asked for, bounded by what the project allows.

    A `_count` above the limit is served the limit rather than refused - R4 says a server may return
    fewer resources than were asked for - while a `_count` that is not a whole number, or is below
    zero, is a malformed query rather than an ambitious one and is refused by `requested_entry_cap`
    before this runs. Zero never reaches here either: it asks for the total alone, which is a count
    rather than a page.
    """
    stated = request.query_params.get(COUNT_PARAMETER)
    cap = requested_entry_cap(stated)
    if cap is None:
        return surface.tracked_entities.page_size
    return min(cap, surface.tracked_entities.page_size_limit)


def _requested_cursor(request: Request) -> ListingCursor:
    """Which page was asked for - the first one when the request names none."""
    stated = request.query_params.get(PAGE_PARAMETER)
    return ListingCursor() if stated is None else ListingCursor.from_token(stated)


def _listing_links(service_base: str, resource_type: str, page: RegisterListingPage, count: int) -> list[BundleLink]:
    """`self`, and the neighbours that exist - each naming the page it leads to, explicitly."""
    links = [BundleLink(relation="self", url=_listing_url(service_base, resource_type, page.cursor, count))]
    if page.previous_cursor is not None:
        links.append(
            BundleLink(relation="previous", url=_listing_url(service_base, resource_type, page.previous_cursor, count))
        )
    if page.next_cursor is not None:
        links.append(
            BundleLink(relation="next", url=_listing_url(service_base, resource_type, page.next_cursor, count))
        )
    return links


def _listing_url(service_base: str, resource_type: str, cursor: ListingCursor, count: int) -> str:
    """One page of the listing as a client may ask for it again and be given the same page."""
    query = urlencode([(COUNT_PARAMETER, count), (PAGE_PARAMETER, cursor.token())])
    return f"{service_base}/{resource_type}?{query}"


def _entries(
    entities: list[TrackerTrackedEntity], surface: RegisterSurface, resource_type: str, service_base: str
) -> list[BundleEntry]:
    """Carry each entity into the result set at the URL this server serves it from."""
    return [
        BundleEntry(
            fullUrl=f"{service_base}/{resource_type}/{entity.trackedEntity}",
            resource=json_resource(registered_entity_for(entity, surface.index, resource_type)),
            search=BundleEntrySearch(mode="match"),
        )
        for entity in entities
    ]


async def _matching_entities(
    reader: RegisterReader,
    surface: RegisterSurface,
    resource_type: str,
    tokens: tuple[IdentifierToken, ...] | list[IdentifierToken],
) -> list[TrackerTrackedEntity]:
    """Fold every token's matches into one result set, in the order they were found, once per entity."""
    found: dict[str, TrackerTrackedEntity] = {}
    for token in tokens:
        for entity in await _entities_for_token(reader, surface, resource_type, token):
            if entity.trackedEntity is not None and _is_served_as(entity, surface, resource_type):
                found.setdefault(entity.trackedEntity, entity)
    return list(found.values())


async def _entities_for_token(
    reader: RegisterReader, surface: RegisterSurface, resource_type: str, token: IdentifierToken
) -> list[TrackerTrackedEntity]:
    """Answer one identifier token: a UID read, one attribute search, or every key at once for a bare value."""
    if token.system == surface.index.tracked_entity_system:
        entity = await _read(reader, token.value)
        return [] if entity is None else [entity]
    if token.system is not None:
        attribute = surface.attribute_for_system(token.system)
        if attribute is None:
            return []
        return await _search(reader, surface, resource_type, attribute.attribute_uid, token.value)
    entity = await _read(reader, token.value)
    found = [] if entity is None else [entity]
    for attribute in surface.search_attributes:
        found.extend(await _search(reader, surface, resource_type, attribute.attribute_uid, token.value))
    return found


async def _read(reader: RegisterReader, tracked_entity_uid: str) -> TrackerTrackedEntity | None:
    """Read one entity, turning a DHIS2 failure into the outcome that says the instance failed."""
    try:
        return await fetch_tracked_entity(reader, tracked_entity_uid)
    except Dhis2ClientError as error:
        raise UpstreamError(
            f"the DHIS2 instance did not answer the tracked entity read: {upstream_refusal_text(error)}"
        ) from error


async def _search(
    reader: RegisterReader, surface: RegisterSurface, resource_type: str, attribute_uid: str, value: str
) -> list[TrackerTrackedEntity]:
    """Search every tracked entity type this resource covers for one attribute value, one type per query."""
    found: list[TrackerTrackedEntity] = []
    for tracked_entity_type_uid in surface.tracked_entity_type_uids_for(resource_type):
        try:
            found.extend(
                await search_tracked_entities(
                    reader,
                    tracked_entity_type_uid=tracked_entity_type_uid,
                    attribute_uid=attribute_uid,
                    value=value,
                )
            )
        except Dhis2ClientError as error:
            raise UpstreamError(
                f"the DHIS2 instance did not answer the tracked entity search: {upstream_refusal_text(error)}"
            ) from error
    return found
