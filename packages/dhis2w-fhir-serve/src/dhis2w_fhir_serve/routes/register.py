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

**`[serve.search] backend = "projection"` MOVES THE FINDING HALF AND LEAVES THE DISCLOSING HALF WHERE
IT IS.** Under that backend the searchset's membership, its paging, and its `_content` answer all come
out of the materialized projection `d2w fhir sync` fills - one indexed query over a local file rather
than one tracker query per key per tracked entity type, and answerable in ways an exact-match filter
is not. Three things stay exactly as they are, and they are the three that matter:

- **Every record is still read live, under the caller's own credentials.** The projection says who is
  on the page; `fetch_tracked_entity` says whether this caller may have them, per person, per request.
  That is `docs/fhir/design/projection.md` R9 and its recommended posture (iii) in full, and it is why
  a projection can answer the finding half without this facade taking on one line of DHIS2's
  authorization model. `GET /{resourceType}/{id}` is a person-level read and therefore stays live
  whatever the backend says.
- **Every projection-served answer states the instant it is as of** - an `outcome` entry in the
  searchset and a header beside it (`dhis2w_fhir_serve.projection.serving`). A live answer states
  none, because it is as of the moment the instance answered.
- **No projection-served answer states a `total`.** The projection counted its rows under the build
  identity the sync ran as, and how many of them THIS caller may see is DHIS2's to say one read at a
  time - so a count taken before that is a number about somebody else, and a Bundle states no total
  rather than one nobody counted for the person reading it.

`_content` is the one search parameter that arrives with the backend, and it is R4's own parameter for
a text search over a resource's whole content. It is the honest spelling: this server does not know
which of a person's DHIS2 attribute values is their name - `register.projection` says at length why it
refuses to guess - so it offers a search across all of them rather than a `family` it would be
inventing. Under `backend = "dhis2"` the parameter is refused exactly as every other unanswerable one
is, because an exact-match filter cannot answer it.

**A SEARCH FINDS IDENTIFIERS AND A READ RESOLVES THEM.** Every filtered search here goes through
`dhis2w_fhir_serve.projection.NameSearchIndex`, which answers with tracked entity UIDs and scores and
never with records; each match is then read back through `fetch_tracked_entity` under the credentials
this request runs as. Splitting it that way is what lets a search index sit behind the seam without
this facade ever deciding on DHIS2's behalf who may see whom - the index says an identifier matched,
and the instance says whether this caller may have the person behind it
(`docs/fhir/design/projection.md` R9). `[serve.search] backend` names which index; `dhis2` is the
instance itself, and it is the default.

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
from dhis2w_fhir.config import SearchBackend
from dhis2w_fhir.r4 import Bundle, BundleEntry, BundleEntrySearch, BundleLink, json_resource
from pydantic import BaseModel, ConfigDict
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from dhis2w_fhir_serve.errors import (
    FHIR_JSON_MEDIA_TYPE,
    BadSearchError,
    NoPublishedSubjectTypeError,
    NotFoundError,
    NotServedError,
    NotServedFromCompiledIgError,
    ProjectionEmptyError,
    ProjectionNotConfiguredError,
    RegisterDisabledError,
    RegisterListingDisabledError,
    UnsupportedSearchParameterError,
    UpstreamError,
)
from dhis2w_fhir_serve.passthrough import RegisterReader, register_reader
from dhis2w_fhir_serve.projection.base import (
    NameQuery,
    NameSearchIndex,
    ProjectionCursor,
    ProjectionQuery,
    ProjectionStore,
)
from dhis2w_fhir_serve.projection.factory import build_name_search_index
from dhis2w_fhir_serve.projection.serving import as_of_entry, as_of_headers
from dhis2w_fhir_serve.register.listing import (
    COUNT_PARAMETER,
    PAGE_PARAMETER,
    ListingCursor,
    RegisterListingPage,
    count_listing_total,
    read_listing_page,
)
from dhis2w_fhir_serve.register.projection import registered_entity_for
from dhis2w_fhir_serve.register.surface import RegisterSurface
from dhis2w_fhir_serve.register.wire import fetch_tracked_entity, upstream_refusal_text
from dhis2w_fhir_serve.routes.context import projection_store, serve_context
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

#: The one search parameter the facade answers a register lookup on.
IDENTIFIER_SEARCH_PARAMETER = "identifier"

#: The search parameter a projection-served register answers beside it: R4's own text search over a
#: resource's whole content, which is what an index over every attribute value a person holds is.
CONTENT_SEARCH_PARAMETER = "_content"


class RegisterLookup(BaseModel):
    """What one register request runs against: the connection, what this run serves, and where it searches.

    They are resolved together because a request that cannot have one has no use for the others: a
    compiled run holds no connection, a project serving no tracked entity type has nothing to search,
    and the index is built over the very connection - or the very store - the resolution reads through.
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    reader: RegisterReader
    surface: RegisterSurface
    index: NameSearchIndex

    store: ProjectionStore | None = None
    """The materialized projection, where this run answers a search from one, and None otherwise.

    None is both postures a live run can be in: `[serve.search] backend = "dhis2"`, and a project that
    configured no projection at all. Either way the searches below read the instance, which is what
    they have always done.
    """

    def from_projection(self) -> bool:
        """Whether this request's searchset membership comes from the projection rather than the instance."""
        return self.store is not None


def register_resource_types(request: Request) -> tuple[str, ...]:
    """Every resource type this process answers from the instance, which is what a read dispatches on."""
    return serve_context(request).register_surface.register_resource_types()


async def search_register(request: Request, resource_type: str) -> Response:
    """Answer the entities a search names, or - naming none - one page of the register."""
    lookup = await _live_lookup(request, resource_type)
    honored: list[HonoredParameter] = []
    tokens: list[IdentifierToken] = []
    contents: list[tuple[str, ...]] = []
    for name, raw in request.query_params.multi_items():
        if name == IDENTIFIER_SEARCH_PARAMETER:
            tokens.extend(identifier_token(value) for value in alternatives(name, raw))
        elif name == CONTENT_SEARCH_PARAMETER:
            contents.append(tuple(alternatives(name, raw)))
        else:
            continue
        honored.append(HonoredParameter(name=name, value=raw))
    _require_answerable_parameters(request, lookup, resource_type, searching=bool(tokens or contents))
    service_base = base_url(request)
    cap = requested_entry_cap(request.query_params.get(COUNT_PARAMETER))
    if not tokens and not contents:
        return await _listing_response(request, lookup, resource_type, service_base)
    if lookup.from_projection():
        return await _projection_search_response(
            lookup, resource_type, tokens, tuple(contents), service_base, tuple(honored), cap
        )
    entities = await _matching_entities(lookup, resource_type, tokens)
    entries = _entries(entities, lookup.surface, resource_type, service_base)
    return bundle_response(service_base, resource_type, tuple(honored), entries, cap)


def _require_answerable_parameters(
    request: Request, lookup: RegisterLookup, resource_type: str, searching: bool
) -> None:
    """Refuse a register request naming a parameter this server cannot apply to it.

    A register search is `identifier`, plus `_content` where a projection answers it, and nothing
    else - so `family=Smith` is a query this facade has no way to run. Answering it with the listing
    would hand back the whole register as though every row in it were a Smith, and the `self` link's
    silence about the parameter is not a signal any client reads. `_count` shapes the answer on either
    path; `page` names a page of the listing, and a search naming a value is answered whole rather
    than paged, whichever backend found it.

    `_content` is refused under `[serve.search] backend = "dhis2"` for the same reason every other
    unanswerable parameter is: an exact-match tracker filter cannot search a resource's content, and
    a facade that answered it with the listing would be answering a question it was not asked. The
    refusal names the parameters that ARE answered, so the difference reads as this server's posture
    rather than as a missing feature.
    """
    answerable = {IDENTIFIER_SEARCH_PARAMETER, COUNT_PARAMETER}
    if lookup.from_projection():
        answerable.add(CONTENT_SEARCH_PARAMETER)
    for name in request.query_params:
        if name in answerable:
            continue
        if name == PAGE_PARAMETER:
            if not searching:
                continue
            raise BadSearchError(
                f"`{PAGE_PARAMETER}` names a page of the `{resource_type}` listing, and a search naming "
                f"`{IDENTIFIER_SEARCH_PARAMETER}` is answered whole"
            )
        raise UnsupportedSearchParameterError(resource_type, name, tuple(sorted(answerable - {COUNT_PARAMETER})))


async def read_registered_entity(request: Request, resource_type: str, tracked_entity_uid: str) -> Response:
    """Answer one entity by its DHIS2 tracked entity UID, which is what a search result links to."""
    lookup = await _live_lookup(request, resource_type)
    entity = await _read(lookup.reader, tracked_entity_uid)
    if entity is None or not _is_served_as(entity, lookup.surface, resource_type):
        raise NotFoundError(resource_type, tracked_entity_uid)
    registered = registered_entity_for(entity, lookup.surface.index, resource_type)
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


async def _live_lookup(request: Request, resource_type: str) -> RegisterLookup:
    """What a lookup runs against, refusing every way this process serves none of it.

    The config comes first: a project whose `[serve.tracked_entities]` serves nothing serves nothing
    however the process was started, so telling its operator to restart with `--live` would be advice
    that changes nothing. The resource comes last, because "this server does not serve `Specimen`" is
    only true of a process that serves the register at all.

    `register_reader` is where the posture is answered, and under `dhis2` it is also where a request
    carrying no credential is refused: what comes back is read as the caller, so a request with
    nobody to be is a 401 rather than a page read as the facade. It sits between the two because
    authenticating a caller comes before telling them what this guide publishes.

    The index is built last, over the reader under `[serve.search] backend = "dhis2"` and over the
    projection under `"projection"`. Under the first, the connection a search runs over is the
    connection a match is resolved back through and one request never uses two; under the second they
    are deliberately two things, because that split is the whole design - the projection says who
    matched and the instance says who may be seen.

    THE READER IS REQUIRED UNDER EITHER BACKEND. A projection-served search still resolves every match
    live under the caller's own credentials, so a process with no instance behind it can no more
    answer a projection-served register than a live one - R9's posture (iii) makes the live read part
    of every answer rather than a fallback for when the projection is cold.
    """
    context = serve_context(request)
    surface = context.register_surface
    if not surface.tracked_entities.enabled:
        raise RegisterDisabledError(resource_type)
    reader = await register_reader(request)
    if reader is None:
        raise NotServedFromCompiledIgError(resource_type)
    if not surface.serves_tracked_entities():
        raise NoPublishedSubjectTypeError(resource_type)
    if not surface.tracked_entity_type_uids_for(resource_type):
        raise NotServedError(resource_type)
    backend = context.settings.search.backend
    store = projection_store(request) if backend is SearchBackend.PROJECTION else None
    return RegisterLookup(
        reader=reader,
        surface=surface,
        index=build_name_search_index(backend, reader=reader, store=store),
        store=store,
    )


async def _listing_response(
    request: Request, lookup: RegisterLookup, resource_type: str, service_base: str
) -> Response:
    """Answer one page of the register, or refuse the whole listing when the project serves none."""
    surface = lookup.surface
    reader = lookup.reader
    if not surface.serves_listing():
        raise RegisterListingDisabledError(resource_type)
    if lookup.from_projection():
        return await _projection_listing_response(request, lookup, resource_type, service_base)
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


async def _projection_search_response(
    lookup: RegisterLookup,
    resource_type: str,
    tokens: list[IdentifierToken],
    contents: tuple[tuple[str, ...], ...],
    service_base: str,
    honored: tuple[HonoredParameter, ...],
    cap: int | None,
) -> Response:
    """Answer a search whose membership the projection decided and whose records the instance authorized.

    The two parameters combine the way R4 says they do. Values within one parameter are alternatives,
    so they are folded into one set of candidates; two different parameters are conditions that both
    hold, so their candidate sets are intersected. `identifier` runs over the token index - an exact
    match, because an identifier names somebody rather than describes them - and `_content` runs over
    the folded attribute values, which is a case-insensitive substring and is what an index over a
    person's own values can honestly claim to be.

    Then every candidate is read from DHIS2 under the credentials this request runs as. A person the
    projection holds and this caller may not see is carried by neither the entries nor the total,
    which is the whole of R9's posture (iii): the projection decides who is on the page and the
    instance decides who may see them.

    A projection nothing has been synced into refuses rather than answering an empty searchset, the
    same way the listing does: "nobody matched" and "nobody has looked" are different facts, and
    only one of them is true here.

    How many matches are resolved is bounded by `[serve.tracked_entities] page_size_limit`, which is
    the same bound the listing puts on a page. Every resolution is a live read, so an unbounded
    `_content` search matching a whole district would be that many sequential reads while somebody
    waits - and the limit an operator already wrote down for a page is what they meant by "as many
    people as this server hands over at once".
    """
    if lookup.store is None:
        raise ProjectionNotConfiguredError
    cursor = await lookup.store.cursor()
    if cursor.updated_at is None:
        raise ProjectionEmptyError(resource_type)
    candidates = await _projection_candidates(lookup, resource_type, tokens, contents)
    resolved = await _resolved_entities(lookup, resource_type, candidates, _resolution_cap(lookup, cap))
    return _projection_bundle(
        resource_type,
        _entries(resolved, lookup.surface, resource_type, service_base),
        _search_links(service_base, resource_type, honored, cap),
        cursor,
    )


async def _projection_listing_response(
    request: Request, lookup: RegisterLookup, resource_type: str, service_base: str
) -> Response:
    """Answer one page of the register out of the projection, resolving each row live as the caller.

    The page is named the way every other page of this listing is named - `_count` and an opaque
    `page` token a client only ever follows - so a client cannot tell the two backends apart by the
    shape of a link. What it CAN tell them apart by is the `outcome` entry stating the cursor, which
    is D6's one stated exception and the point of R3.

    THE ANSWER STATES NO TOTAL. The projection knows exactly how many rows it holds, and that number
    was counted under the identity the sync ran as rather than under the identity of whoever is
    asking. Handing it over would tell a caller scoped to one district how large the national register
    is, so the Bundle states no total - the same silence it already keeps when the instance states no
    count. `_count=0` asks how large the register is, and this is the one posture that cannot answer
    it: what comes back is the cursor, no entries, and no `next` link, because a page of nothing
    leads nowhere. A client that has to have the number reads the live backend, where the count is
    taken under its own credentials.
    """
    if lookup.store is None:
        raise ProjectionNotConfiguredError
    count = _requested_count(request, lookup.surface)
    cursor_token = _requested_cursor(request)
    offset = (cursor_token.upstream_page - 1) * count
    page = await lookup.store.search(ProjectionQuery(resource_type=resource_type, offset=offset, count=count))
    if page.cursor.updated_at is None:
        raise ProjectionEmptyError(resource_type)
    resolved = await _resolved_entities(
        lookup, resource_type, tuple(resource.resource_id for resource in page.resources), None
    )
    links = [BundleLink(relation="self", url=_listing_url(service_base, resource_type, cursor_token, count))]
    if cursor_token.upstream_page > 1:
        previous = ListingCursor(upstream_page=cursor_token.upstream_page - 1)
        links.append(BundleLink(relation="previous", url=_listing_url(service_base, resource_type, previous, count)))
    # The store's own total decides whether there is a page after this one, and never leaves the
    # server: it is a count taken under the identity the sync ran as, which is a number about
    # somebody else - so it links the walk and is not stated. See this function's docstring.
    # `_count=0` asked for no entries at all, and a page of nothing leads nowhere.
    if count > 0 and page.total is not None and offset + len(page.resources) < page.total:
        following = ListingCursor(upstream_page=cursor_token.upstream_page + 1)
        links.append(BundleLink(relation="next", url=_listing_url(service_base, resource_type, following, count)))
    return _projection_bundle(
        resource_type,
        _entries(resolved, lookup.surface, resource_type, service_base),
        links,
        page.cursor,
    )


def _resolution_cap(lookup: RegisterLookup, requested: int | None) -> int:
    """How many matches a projection-served search reads back, bounded by what this project allows.

    A `_count` above the limit is served the limit rather than refused, which is the rule
    `_requested_count` states for the listing and the one R4 gives a server for a `_count` it will
    not meet. Naming no `_count` gets the limit too: every resolution is a live read, and a search
    that matched a district is not an instruction to spend a district's worth of round trips.
    """
    limit = lookup.surface.tracked_entities.page_size_limit
    return limit if requested is None else min(requested, limit)


async def _projection_candidates(
    lookup: RegisterLookup,
    resource_type: str,
    tokens: list[IdentifierToken],
    contents: tuple[tuple[str, ...], ...],
) -> tuple[str, ...]:
    """Which tracked entities this search names, before the instance has been asked about any of them."""
    conditions: list[dict[str, None]] = []
    if tokens:
        matched: dict[str, None] = {}
        for token in tokens:
            for resource_id in await _projection_token_matches(lookup, resource_type, token):
                matched.setdefault(resource_id, None)
        conditions.append(matched)
    for alternatives_of_one_parameter in contents:
        matched = {}
        for value in alternatives_of_one_parameter:
            found = await lookup.index.find(
                NameQuery(
                    value=value,
                    tracked_entity_type_uids=lookup.surface.tracked_entity_type_uids_for(resource_type),
                )
            )
            for match in found.matches:
                matched.setdefault(match.tracked_entity_uid, None)
        conditions.append(matched)
    if not conditions:
        return ()
    first, *rest = conditions
    return tuple(resource_id for resource_id in first if all(resource_id in other for other in rest))


async def _projection_token_matches(
    lookup: RegisterLookup, resource_type: str, token: IdentifierToken
) -> tuple[str, ...]:
    """Which projected resources hold one identifier token, matched exactly over the token index.

    A token naming a system is looked for under that system alone; a bare value is looked for under
    every system the projection holds, which is the same "the client does not know which key this is"
    the live path answers by trying each of them. The tracked entity UID needs no special case here
    the way it does live: the projected resource carries it as an `identifier` like any other, so one
    index answers a UID and a national identifier with the same query.
    """
    if lookup.store is None:
        return ()
    page = await lookup.store.search(
        ProjectionQuery(
            resource_type=resource_type,
            identifiers=(token.value,),
            identifier_systems=() if token.system is None else (token.system,),
        )
    )
    return tuple(resource.resource_id for resource in page.resources)


async def _resolved_entities(
    lookup: RegisterLookup, resource_type: str, candidates: tuple[str, ...], cap: int | None
) -> list[TrackerTrackedEntity]:
    """Read each candidate from DHIS2 as the caller, keeping the ones the instance let through.

    This is where R9 happens, one person at a time. A candidate the caller may not see comes back as
    nothing - DHIS2 hides what a caller may not see rather than refusing it - and is carried by no
    part of the answer. A candidate whose type is not the one this resource is served over is dropped
    for the same reason the live path drops it: a sample never comes back as a person.
    """
    kept: list[TrackerTrackedEntity] = []
    for tracked_entity_uid in candidates:
        if cap is not None and len(kept) >= cap:
            break
        entity = await _read(lookup.reader, tracked_entity_uid)
        if entity is not None and _is_served_as(entity, lookup.surface, resource_type):
            kept.append(entity)
    return kept


def _projection_bundle(
    resource_type: str,
    entries: list[BundleEntry],
    links: list[BundleLink],
    cursor: ProjectionCursor | None,
) -> Response:
    """Serialise a projection-served searchset: the matches, the links, and the instant it is as of.

    The as-of statement rides twice, and `dhis2w_fhir_serve.projection.serving` argues why: an
    `outcome` entry, which is R4's own way for a server to say something about a search inside the
    search's answer, and a header beside it for whoever reads responses rather than resources.
    """
    stated = cursor if cursor is not None else ProjectionCursor()
    bundle = Bundle(type="searchset", link=links, entry=[*entries, as_of_entry(stated)])
    return Response(
        content=bundle.model_dump_json(exclude_none=True, by_alias=True),
        media_type=FHIR_JSON_MEDIA_TYPE,
        headers=as_of_headers(stated),
    )


def _search_links(
    service_base: str, resource_type: str, honored: tuple[HonoredParameter, ...], cap: int | None
) -> list[BundleLink]:
    """The `self` link of a search answered whole - what was applied, and the cap applied with it."""
    parameters = [(parameter.name, parameter.value) for parameter in honored]
    if cap is not None:
        parameters.append((COUNT_PARAMETER, str(cap)))
    query = urlencode(parameters)
    url = f"{service_base}/{resource_type}?{query}" if query else f"{service_base}/{resource_type}"
    return [BundleLink(relation="self", url=url)]


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
    lookup: RegisterLookup,
    resource_type: str,
    tokens: tuple[IdentifierToken, ...] | list[IdentifierToken],
) -> list[TrackerTrackedEntity]:
    """Fold every token's matches into one result set, in the order they were found, once per entity."""
    found: dict[str, TrackerTrackedEntity] = {}
    for token in tokens:
        for entity in await _entities_for_token(lookup, resource_type, token):
            if entity.trackedEntity is not None and _is_served_as(entity, lookup.surface, resource_type):
                found.setdefault(entity.trackedEntity, entity)
    return list(found.values())


async def _entities_for_token(
    lookup: RegisterLookup, resource_type: str, token: IdentifierToken
) -> list[TrackerTrackedEntity]:
    """Answer one identifier token: a UID read, one attribute search, or every key at once for a bare value."""
    surface = lookup.surface
    if token.system == surface.index.tracked_entity_system:
        entity = await _read(lookup.reader, token.value)
        return [] if entity is None else [entity]
    if token.system is not None:
        attribute = surface.attribute_for_system(token.system)
        if attribute is None:
            return []
        return await _search(lookup, resource_type, (attribute.attribute_uid,), token.value)
    entity = await _read(lookup.reader, token.value)
    found = [] if entity is None else [entity]
    keys = tuple(attribute.attribute_uid for attribute in surface.search_attributes)
    found.extend(await _search(lookup, resource_type, keys, token.value))
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
    lookup: RegisterLookup, resource_type: str, attribute_uids: tuple[str, ...], value: str
) -> list[TrackerTrackedEntity]:
    """Find who holds one value under these keys, then read each of them back as the caller.

    THE TWO HALVES ARE THE SEAM AND THE WHOLE POINT OF IT. `find` discloses matches - a tracked
    entity UID and a score - and never a record, so a backend that is not the instance can answer it
    without this facade deciding on DHIS2's behalf who may see whom. The record then comes from
    `fetch_tracked_entity` under the credentials this request runs as, so DHIS2 authorizes every
    disclosure per match per caller, exactly as it does for a read of one entity by its UID
    (`docs/fhir/design/projection.md` R9). A person the search found and the read cannot see is
    carried by neither, which is that decision going to the instance rather than being made here.

    Under `[serve.search] backend = "dhis2"` both halves are the same live connection, so a lookup
    that matches nobody costs exactly what it always did and a lookup that matches somebody spends
    one read on the person it is about to hand over.
    """
    try:
        matches = await lookup.index.find(
            NameQuery(
                value=value,
                attribute_uids=attribute_uids,
                tracked_entity_type_uids=lookup.surface.tracked_entity_type_uids_for(resource_type),
            )
        )
    except Dhis2ClientError as error:
        raise UpstreamError(
            f"the DHIS2 instance did not answer the tracked entity search: {upstream_refusal_text(error)}"
        ) from error
    found: list[TrackerTrackedEntity] = []
    for match in matches.matches:
        entity = await _read(lookup.reader, match.tracked_entity_uid)
        if entity is not None:
            found.append(entity)
    return found
