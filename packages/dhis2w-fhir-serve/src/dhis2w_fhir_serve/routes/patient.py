"""`GET /Patient` and `GET /Patient/{id}` - who a person is in the DHIS2 instance behind this facade.

This is the one FHIR resource type this server answers from DHIS2 rather than from what it loaded at
startup, and the only one whose answer can differ between two requests a second apart. It mounts
ahead of the read catch-alls so `/Patient` never reaches the store, which holds none.

**Live mode only.** The default mode serves a compiled guide and holds no DHIS2 client, so there is
no instance to ask; it answers a `not-supported` OperationOutcome saying so, and `/metadata`
declares no Patient at all, which is the same fact stated ahead of the request. A live process whose
project publishes no registration form answers the same way for the same reason one step further
in: with no published tracked entity type, `/api/tracker/trackedEntities` has nothing to be given
and refuses the query (`E1003`).

**`[serve.patients]` says how much of this surface exists.** `enabled = false` refuses every route
here and declares no Patient at `/metadata`, which is the compiled-mode posture arrived at from the
project rather than from the invocation - and it is checked first, because a project that serves no
people serves none whichever way the process was started. `listing = false` refuses the
no-identifier request alone and leaves identifier search exactly as it is. Both refusals name the
key that produced them, so an operator reading the outcome knows which line to change.

**A request naming no `identifier` is the listing**: a paged searchset over the tracked entity types
in scope, which `dhis2w_fhir_serve.patients.listing` walks and links. `_count` is honoured up to
`[serve.patients] page_size_limit` and clamped rather than refused above it.

**`identifier` is the whole search surface** for naming one person, in both of FHIR's token forms:

- `identifier={system}|{value}` names which key the value is. `{base}/id/tracked-entity` is the
  tracked entity UID itself and is answered by reading that one entity, not by filtering - a UID is
  not an attribute and no `filter=` expression could ask for it. Every other system names one
  tracked entity attribute the guide publishes as unique, and the search filters on it.
- `identifier={value}` names no key, so every key is tried: the UID read plus one filtered search
  per unique attribute, folded into one result set and deduplicated by tracked entity UID. A person
  holding the same value in two of them appears once.

Which attributes are keys is the surface's answer, not this module's: the ones DHIS2 declares unique
by default, and the ones `[serve.patients] search_attributes` names when it names any.

A system this guide publishes nothing for matches nothing, and answers an empty searchset rather
than an error: FHIR's search semantics make an unmatched token an empty result, and a 404 would
tell a client its query was malformed when it was merely unsatisfied. Empty is likewise what an
identifier no person holds answers - never a 404, which on a search path would mean the endpoint
does not exist.

Searching across every published tracked entity type is deliberate. DHIS2 requires exactly one type
per query, so a project publishing registration forms for two of them costs two requests per key;
that is the price of not making a client know which type its identifier belongs to.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import urlencode

from dhis2w_client.errors import Dhis2ClientError
from dhis2w_fhir.r4 import Bundle, BundleEntry, BundleEntrySearch, BundleLink, json_resource
from fastapi import APIRouter
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from dhis2w_fhir_serve.errors import (
    FHIR_JSON_MEDIA_TYPE,
    BadSearchError,
    NoPublishedSubjectTypeError,
    NotFoundError,
    NotServedFromCompiledIgError,
    PatientListingDisabledError,
    PatientSurfaceDisabledError,
    UpstreamError,
)
from dhis2w_fhir_serve.patients.listing import (
    COUNT_PARAMETER,
    PAGE_PARAMETER,
    ListingCursor,
    PatientListingPage,
    read_listing_page,
)
from dhis2w_fhir_serve.patients.projection import patient_for
from dhis2w_fhir_serve.patients.wire import fetch_tracked_entity, search_tracked_entities, upstream_refusal_text
from dhis2w_fhir_serve.routes.context import live_client, serve_context
from dhis2w_fhir_serve.routes.read import HonoredParameter, alternatives, base_url, bundle_response, identifier_token
from dhis2w_fhir_serve.store import IdentifierToken

if TYPE_CHECKING:
    from dhis2w_client import Dhis2Client
    from dhis2w_client.generated.v42.oas import TrackerTrackedEntity

    from dhis2w_fhir_serve.patients.surface import PatientSurface

#: The resource type these routes answer for.
PATIENT_RESOURCE_TYPE = "Patient"

#: The one search parameter the facade answers a patient lookup on.
IDENTIFIER_SEARCH_PARAMETER = "identifier"

router = APIRouter()


@router.get(f"/{PATIENT_RESOURCE_TYPE}")
async def search_patients(request: Request) -> Response:
    """Answer the people an identifier names, or - naming none - one page of the register."""
    client, surface = _live_lookup(request)
    honored: list[HonoredParameter] = []
    tokens: list[IdentifierToken] = []
    for name, raw in request.query_params.multi_items():
        if name != IDENTIFIER_SEARCH_PARAMETER:
            continue
        tokens.extend(identifier_token(value) for value in alternatives(name, raw))
        honored.append(HonoredParameter(name=name, value=raw))
    service_base = base_url(request)
    if not tokens:
        return await _listing_response(request, client, surface, service_base)
    entities = await _matching_entities(client, surface, tokens)
    entries = _entries(entities, surface, service_base)
    return bundle_response(service_base, PATIENT_RESOURCE_TYPE, tuple(honored), entries)


@router.get(f"/{PATIENT_RESOURCE_TYPE}/{{tracked_entity_uid}}")
async def read_patient(request: Request, tracked_entity_uid: str) -> Response:
    """Answer one person by their DHIS2 tracked entity UID, which is what a search result links to."""
    client, surface = _live_lookup(request)
    entity = await _read(client, tracked_entity_uid)
    if entity is None:
        raise NotFoundError(PATIENT_RESOURCE_TYPE, tracked_entity_uid)
    patient = patient_for(entity, surface.index)
    return JSONResponse(
        content=patient.model_dump(mode="json", exclude_none=True, by_alias=True), media_type=FHIR_JSON_MEDIA_TYPE
    )


def _live_lookup(request: Request) -> tuple[Dhis2Client, PatientSurface]:
    """The client and the surface a lookup runs against, refusing every way this process serves neither.

    The config comes first: a project whose `[serve.patients]` serves no people serves none however
    the process was started, so telling its operator to restart with `--live` would be advice that
    changes nothing.
    """
    surface = serve_context(request).patient_surface
    if not surface.patients.enabled:
        raise PatientSurfaceDisabledError(PATIENT_RESOURCE_TYPE)
    client = live_client(request)
    if client is None:
        raise NotServedFromCompiledIgError(PATIENT_RESOURCE_TYPE)
    if not surface.serves_patients():
        raise NoPublishedSubjectTypeError(PATIENT_RESOURCE_TYPE)
    return client, surface


async def _listing_response(
    request: Request, client: Dhis2Client, surface: PatientSurface, service_base: str
) -> Response:
    """Answer one page of the register, or refuse the whole listing when the project serves none."""
    if not surface.serves_listing():
        raise PatientListingDisabledError(PATIENT_RESOURCE_TYPE)
    count = _requested_count(request, surface)
    cursor = _requested_cursor(request)
    try:
        page = await read_listing_page(
            client, tracked_entity_type_uids=surface.tracked_entity_type_uids, cursor=cursor, count=count
        )
    except Dhis2ClientError as error:
        raise UpstreamError(
            f"the DHIS2 instance did not answer the tracked entity listing: {upstream_refusal_text(error)}"
        ) from error
    bundle = Bundle(
        type="searchset",
        total=page.total,
        link=_listing_links(service_base, page, count),
        entry=_entries(page.entities, surface, service_base) or None,
    )
    return Response(content=bundle.model_dump_json(exclude_none=True, by_alias=True), media_type=FHIR_JSON_MEDIA_TYPE)


def _requested_count(request: Request, surface: PatientSurface) -> int:
    """How many people this page carries: what the client asked for, bounded by what the project allows.

    A `_count` above the limit is served the limit rather than refused - R4 says a server may return
    fewer resources than were asked for - while a `_count` that is not a positive number is a
    malformed query rather than an ambitious one, and is refused as such.
    """
    stated = request.query_params.get(COUNT_PARAMETER)
    if stated is None:
        return surface.patients.page_size
    try:
        count = int(stated)
    except ValueError as error:
        raise BadSearchError(f"`{COUNT_PARAMETER}` was given `{stated}`, which is not a number of people") from error
    if count < 1:
        raise BadSearchError(f"`{COUNT_PARAMETER}` was given `{stated}`: a page carries at least one person")
    return min(count, surface.patients.page_size_limit)


def _requested_cursor(request: Request) -> ListingCursor:
    """Which page was asked for - the first one when the request names none."""
    stated = request.query_params.get(PAGE_PARAMETER)
    return ListingCursor() if stated is None else ListingCursor.from_token(stated)


def _listing_links(service_base: str, page: PatientListingPage, count: int) -> list[BundleLink]:
    """`self`, and the neighbours that exist - each naming the page it leads to, explicitly."""
    links = [BundleLink(relation="self", url=_listing_url(service_base, page.cursor, count))]
    if page.previous_cursor is not None:
        links.append(BundleLink(relation="previous", url=_listing_url(service_base, page.previous_cursor, count)))
    if page.next_cursor is not None:
        links.append(BundleLink(relation="next", url=_listing_url(service_base, page.next_cursor, count)))
    return links


def _listing_url(service_base: str, cursor: ListingCursor, count: int) -> str:
    """One page of the listing as a client may ask for it again and be given the same page."""
    query = urlencode([(COUNT_PARAMETER, count), (PAGE_PARAMETER, cursor.token())])
    return f"{service_base}/{PATIENT_RESOURCE_TYPE}?{query}"


def _entries(entities: list[TrackerTrackedEntity], surface: PatientSurface, service_base: str) -> list[BundleEntry]:
    """Carry each person into the result set at the URL this server serves them from."""
    return [
        BundleEntry(
            fullUrl=f"{service_base}/{PATIENT_RESOURCE_TYPE}/{entity.trackedEntity}",
            resource=json_resource(patient_for(entity, surface.index)),
            search=BundleEntrySearch(mode="match"),
        )
        for entity in entities
    ]


async def _matching_entities(
    client: Dhis2Client, surface: PatientSurface, tokens: tuple[IdentifierToken, ...] | list[IdentifierToken]
) -> list[TrackerTrackedEntity]:
    """Fold every token's matches into one result set, in the order they were found, once per person."""
    found: dict[str, TrackerTrackedEntity] = {}
    for token in tokens:
        for entity in await _entities_for_token(client, surface, token):
            if entity.trackedEntity is not None:
                found.setdefault(entity.trackedEntity, entity)
    return list(found.values())


async def _entities_for_token(
    client: Dhis2Client, surface: PatientSurface, token: IdentifierToken
) -> list[TrackerTrackedEntity]:
    """Answer one identifier token: a UID read, one attribute search, or every key at once for a bare value."""
    if token.system == surface.index.tracked_entity_system:
        entity = await _read(client, token.value)
        return [] if entity is None else [entity]
    if token.system is not None:
        attribute = surface.attribute_for_system(token.system)
        if attribute is None:
            return []
        return await _search(client, surface, attribute.attribute_uid, token.value)
    entity = await _read(client, token.value)
    found = [] if entity is None else [entity]
    for attribute in surface.identifier_attributes:
        found.extend(await _search(client, surface, attribute.attribute_uid, token.value))
    return found


async def _read(client: Dhis2Client, tracked_entity_uid: str) -> TrackerTrackedEntity | None:
    """Read one entity, turning a DHIS2 failure into the outcome that says the instance failed."""
    try:
        return await fetch_tracked_entity(client, tracked_entity_uid)
    except Dhis2ClientError as error:
        raise UpstreamError(
            f"the DHIS2 instance did not answer the tracked entity read: {upstream_refusal_text(error)}"
        ) from error


async def _search(
    client: Dhis2Client, surface: PatientSurface, attribute_uid: str, value: str
) -> list[TrackerTrackedEntity]:
    """Search every tracked entity type in scope for one attribute value, since DHIS2 takes one type per query."""
    found: list[TrackerTrackedEntity] = []
    for tracked_entity_type_uid in surface.tracked_entity_type_uids:
        try:
            found.extend(
                await search_tracked_entities(
                    client,
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
