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

**`identifier` is the whole search surface**, in both of FHIR's token forms:

- `identifier={system}|{value}` names which key the value is. `{base}/id/tracked-entity` is the
  tracked entity UID itself and is answered by reading that one entity, not by filtering - a UID is
  not an attribute and no `filter=` expression could ask for it. Every other system names one
  tracked entity attribute the guide publishes as unique, and the search filters on it.
- `identifier={value}` names no key, so every key is tried: the UID read plus one filtered search
  per unique attribute, folded into one result set and deduplicated by tracked entity UID. A person
  holding the same value in two of them appears once.

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

from dhis2w_client.errors import Dhis2ClientError
from dhis2w_fhir.r4 import BundleEntry, BundleEntrySearch, json_resource
from fastapi import APIRouter
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from dhis2w_fhir_serve.errors import (
    FHIR_JSON_MEDIA_TYPE,
    NoPublishedSubjectTypeError,
    NotFoundError,
    NotServedFromCompiledIgError,
    UpstreamError,
)
from dhis2w_fhir_serve.patients.projection import patient_for
from dhis2w_fhir_serve.patients.wire import fetch_tracked_entity, search_tracked_entities
from dhis2w_fhir_serve.routes.context import live_client, serve_context
from dhis2w_fhir_serve.routes.read import HonoredParameter, alternatives, base_url, bundle_response, identifier_token
from dhis2w_fhir_serve.store import IdentifierToken

if TYPE_CHECKING:
    from dhis2w_client import Dhis2Client
    from dhis2w_client.generated.v42.oas import TrackerTrackedEntity

    from dhis2w_fhir_serve.patients.index import PatientIndex

#: The resource type these routes answer for.
PATIENT_RESOURCE_TYPE = "Patient"

#: The one search parameter the facade answers a patient lookup on.
IDENTIFIER_SEARCH_PARAMETER = "identifier"

router = APIRouter()


@router.get(f"/{PATIENT_RESOURCE_TYPE}")
async def search_patients(request: Request) -> Response:
    """Search the instance for the people an identifier names, answering with a `searchset` Bundle."""
    client, index = _live_lookup(request)
    honored: list[HonoredParameter] = []
    tokens: list[IdentifierToken] = []
    for name, raw in request.query_params.multi_items():
        if name != IDENTIFIER_SEARCH_PARAMETER:
            continue
        tokens.extend(identifier_token(value) for value in alternatives(name, raw))
        honored.append(HonoredParameter(name=name, value=raw))
    entities = await _matching_entities(client, index, tokens)
    service_base = base_url(request)
    entries = [
        BundleEntry(
            fullUrl=f"{service_base}/{PATIENT_RESOURCE_TYPE}/{entity.trackedEntity}",
            resource=json_resource(patient_for(entity, index)),
            search=BundleEntrySearch(mode="match"),
        )
        for entity in entities
    ]
    return bundle_response(service_base, PATIENT_RESOURCE_TYPE, tuple(honored), entries)


@router.get(f"/{PATIENT_RESOURCE_TYPE}/{{tracked_entity_uid}}")
async def read_patient(request: Request, tracked_entity_uid: str) -> Response:
    """Answer one person by their DHIS2 tracked entity UID, which is what a search result links to."""
    client, index = _live_lookup(request)
    entity = await _read(client, tracked_entity_uid)
    if entity is None:
        raise NotFoundError(PATIENT_RESOURCE_TYPE, tracked_entity_uid)
    patient = patient_for(entity, index)
    return JSONResponse(
        content=patient.model_dump(mode="json", exclude_none=True, by_alias=True), media_type=FHIR_JSON_MEDIA_TYPE
    )


def _live_lookup(request: Request) -> tuple[Dhis2Client, PatientIndex]:
    """The client and the index a lookup runs against, refusing both ways this process can hold neither."""
    client = live_client(request)
    if client is None:
        raise NotServedFromCompiledIgError(PATIENT_RESOURCE_TYPE)
    index = serve_context(request).patient_index
    if not index.serves_patients():
        raise NoPublishedSubjectTypeError(PATIENT_RESOURCE_TYPE)
    return client, index


async def _matching_entities(
    client: Dhis2Client, index: PatientIndex, tokens: tuple[IdentifierToken, ...] | list[IdentifierToken]
) -> list[TrackerTrackedEntity]:
    """Fold every token's matches into one result set, in the order they were found, once per person."""
    found: dict[str, TrackerTrackedEntity] = {}
    for token in tokens:
        for entity in await _entities_for_token(client, index, token):
            if entity.trackedEntity is not None:
                found.setdefault(entity.trackedEntity, entity)
    return list(found.values())


async def _entities_for_token(
    client: Dhis2Client, index: PatientIndex, token: IdentifierToken
) -> list[TrackerTrackedEntity]:
    """Answer one identifier token: a UID read, one attribute search, or every key at once for a bare value."""
    if token.system == index.tracked_entity_system:
        entity = await _read(client, token.value)
        return [] if entity is None else [entity]
    if token.system is not None:
        attribute = index.attribute_for_system(token.system)
        if attribute is None or not attribute.unique:
            return []
        return await _search(client, index, attribute.attribute_uid, token.value)
    entity = await _read(client, token.value)
    found = [] if entity is None else [entity]
    for attribute in index.identifier_attributes():
        found.extend(await _search(client, index, attribute.attribute_uid, token.value))
    return found


async def _read(client: Dhis2Client, tracked_entity_uid: str) -> TrackerTrackedEntity | None:
    """Read one entity, turning a DHIS2 failure into the outcome that says the instance failed."""
    try:
        return await fetch_tracked_entity(client, tracked_entity_uid)
    except Dhis2ClientError as error:
        raise UpstreamError(f"the DHIS2 instance did not answer the tracked entity read: {error}") from error


async def _search(
    client: Dhis2Client, index: PatientIndex, attribute_uid: str, value: str
) -> list[TrackerTrackedEntity]:
    """Search every published tracked entity type for one attribute value, since DHIS2 takes one type per query."""
    found: list[TrackerTrackedEntity] = []
    for tracked_entity_type_uid in index.tracked_entity_type_uids:
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
            raise UpstreamError(f"the DHIS2 instance did not answer the tracked entity search: {error}") from error
    return found
