"""Read and search over what the facade serves: `GET /{type}/{id}` and `GET /{type}`.

These two routes match any path of their shape, so they mount last - every fixed path the facade
serves is registered ahead of them. A type outside the served set is refused here rather than
falling through to a bare 404, so a client learns the difference between "this server does not
serve Patient" and "there is no Questionnaire with that id".

The two catch-alls answer from two sources. Every definitional resource comes from the store,
byte-faithful to what the IG published. QuestionnaireResponse comes from the spool, where each
resource is a receipt of a submission - what a client sent, not what DHIS2 now holds.

Search is lenient in FHIR's own sense: an unrecognised parameter is ignored rather than refused,
and the Bundle's `self` link echoes only the parameters that were honored, so a client can see
what the server actually applied.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

from dhis2w_fhir.foundation import CAPTURE_SERVER_READ_RESOURCE_TYPES
from dhis2w_fhir.r4 import Bundle, BundleEntry, BundleEntrySearch, BundleLink, JsonResource
from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field
from starlette.datastructures import QueryParams
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from dhis2w_fhir_serve.capability import QUESTIONNAIRE_RESPONSE_RESOURCE_TYPE
from dhis2w_fhir_serve.errors import FHIR_JSON_MEDIA_TYPE, BadSearchError, NotFoundError, NotServedError
from dhis2w_fhir_serve.routes.context import serve_context
from dhis2w_fhir_serve.store import IdentifierToken, SearchQuery

#: Every resource type the facade answers a read or a search for.
SERVED_RESOURCE_TYPES = (*CAPTURE_SERVER_READ_RESOURCE_TYPES, QUESTIONNAIRE_RESPONSE_RESOURCE_TYPE)

router = APIRouter()


class HonoredParameter(BaseModel):
    """One search parameter the facade applied, as the Bundle `self` link echoes it back."""

    model_config = ConfigDict(frozen=True)

    name: str
    value: str


class ParsedSearch(BaseModel):
    """A store search: the query it runs, and the parameters the `self` link reports as applied."""

    model_config = ConfigDict(frozen=True)

    query: SearchQuery = Field(default_factory=SearchQuery)
    honored: tuple[HonoredParameter, ...] = ()


class ParsedResponseSearch(BaseModel):
    """A spool search: the receipts it selects, and the parameters the `self` link reports as applied."""

    model_config = ConfigDict(frozen=True)

    ids: tuple[str, ...] = ()
    questionnaires: tuple[str, ...] = ()
    honored: tuple[HonoredParameter, ...] = ()


def parse_store_search(params: QueryParams) -> ParsedSearch:
    """Read `_id`, `url`, and `identifier` into a store query, ignoring every other parameter."""
    ids: list[str] = []
    urls: list[str] = []
    identifiers: list[IdentifierToken] = []
    honored: list[HonoredParameter] = []
    for name, raw in params.multi_items():
        if name == "_id":
            ids.extend(_alternatives(name, raw))
        elif name == "url":
            urls.extend(_alternatives(name, raw))
        elif name == "identifier":
            identifiers.extend(_identifier_token(value) for value in _alternatives(name, raw))
        else:
            continue
        honored.append(HonoredParameter(name=name, value=raw))
    query = SearchQuery(ids=tuple(ids), urls=tuple(urls), identifiers=tuple(identifiers))
    return ParsedSearch(query=query, honored=tuple(honored))


def parse_response_search(params: QueryParams) -> ParsedResponseSearch:
    """Read `_id` and `questionnaire` into a spool search, ignoring every other parameter."""
    ids: list[str] = []
    questionnaires: list[str] = []
    honored: list[HonoredParameter] = []
    for name, raw in params.multi_items():
        if name == "_id":
            ids.extend(_alternatives(name, raw))
        elif name == "questionnaire":
            questionnaires.extend(_alternatives(name, raw))
        else:
            continue
        honored.append(HonoredParameter(name=name, value=raw))
    return ParsedResponseSearch(ids=tuple(ids), questionnaires=tuple(questionnaires), honored=tuple(honored))


@router.get("/{resource_type}")
async def search_resource_type(request: Request, resource_type: str) -> Response:
    """Search one served resource type, answering with a `searchset` Bundle."""
    context = serve_context(request)
    _require_served(resource_type)
    base_url = _base_url(request)
    if resource_type == QUESTIONNAIRE_RESPONSE_RESOURCE_TYPE:
        parsed_responses = parse_response_search(request.query_params)
        envelopes = [
            envelope
            for envelope in context.spool.search(ids=parsed_responses.ids)
            if not parsed_responses.questionnaires or envelope.questionnaire in parsed_responses.questionnaires
        ]
        entries = [
            _bundle_entry(base_url, resource_type, envelope.response_id, envelope.response) for envelope in envelopes
        ]
        return _bundle_response(base_url, resource_type, parsed_responses.honored, entries)
    parsed = parse_store_search(request.query_params)
    entries = [
        _bundle_entry(base_url, entry.resource_type, entry.resource_id, entry.body)
        for entry in context.store.search(resource_type, parsed.query)
    ]
    return _bundle_response(base_url, resource_type, parsed.honored, entries)


@router.get("/{resource_type}/{resource_id}")
async def read_resource(request: Request, resource_type: str, resource_id: str) -> Response:
    """Answer one resource verbatim, from the store or - for a receipt - from the spool."""
    context = serve_context(request)
    _require_served(resource_type)
    if resource_type == QUESTIONNAIRE_RESPONSE_RESOURCE_TYPE:
        envelope = context.spool.get(resource_id)
        if envelope is None:
            raise NotFoundError(resource_type, resource_id)
        return JSONResponse(content=envelope.response, media_type=FHIR_JSON_MEDIA_TYPE)
    entry = context.store.by_type_and_id(resource_type, resource_id)
    if entry is None:
        raise NotFoundError(resource_type, resource_id)
    return JSONResponse(content=entry.body, media_type=FHIR_JSON_MEDIA_TYPE)


def _require_served(resource_type: str) -> None:
    """Refuse a resource type the facade does not serve, whatever the store happens to hold."""
    if resource_type not in SERVED_RESOURCE_TYPES:
        raise NotServedError(resource_type)


def _alternatives(name: str, raw: str) -> list[str]:
    """Split one parameter into its comma-separated alternatives, refusing an empty one."""
    values = [value.strip() for value in raw.split(",")]
    if any(not value for value in values):
        raise BadSearchError(f"`{name}` was given an empty value")
    return values


def _identifier_token(value: str) -> IdentifierToken:
    """Read a `system|value` token; a bare value, or an empty system, matches the value in any system."""
    if "|" not in value:
        return IdentifierToken(value=value)
    system, _, token = value.partition("|")
    if not token:
        raise BadSearchError(f"`identifier` token `{value}` names a system but no value")
    return IdentifierToken(system=system or None, value=token)


def _base_url(request: Request) -> str:
    """The service base every `fullUrl` and `self` link is built from, without its trailing slash."""
    return str(request.base_url).rstrip("/")


def _bundle_entry(base_url: str, resource_type: str, resource_id: str, body: dict[str, Any]) -> BundleEntry:
    """Carry one resource into the result set at the URL it is served from."""
    return BundleEntry(
        fullUrl=f"{base_url}/{resource_type}/{resource_id}",
        resource=JsonResource.model_validate(body),
        search=BundleEntrySearch(mode="match"),
    )


def _bundle_response(
    base_url: str,
    resource_type: str,
    honored: tuple[HonoredParameter, ...],
    entries: list[BundleEntry],
) -> Response:
    """Serialise the result set, with a `self` link naming only the parameters that were applied."""
    query = urlencode([(parameter.name, parameter.value) for parameter in honored])
    self_url = f"{base_url}/{resource_type}?{query}" if query else f"{base_url}/{resource_type}"
    bundle = Bundle(
        type="searchset",
        total=len(entries),
        link=[BundleLink(relation="self", url=self_url)],
        entry=entries or None,
    )
    return Response(
        content=bundle.model_dump_json(exclude_none=True, by_alias=True),
        media_type=FHIR_JSON_MEDIA_TYPE,
    )
