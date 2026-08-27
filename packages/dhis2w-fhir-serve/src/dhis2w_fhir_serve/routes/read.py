"""Read and search over what the facade serves: `GET /{type}/{id}` and `GET /{type}`.

These two routes match any path of their shape, so they mount last - every fixed path the facade
serves is registered ahead of them. A type outside the served set is refused here rather than
falling through to a bare 404, so a client learns the difference between "this server does not
serve Specimen" and "there is no Questionnaire with that id".

The two catch-alls answer from three sources. Every definitional resource comes from the store,
byte-faithful to what the IG published - ConceptMap included, which is read here as a document and
translated through at `/ConceptMap/$translate`, the two being different ways to ask about the same
published maps, and the guide's own conformance resources included too, which is what makes a served
project self-hosting: a profile canonical found on a response is resolved with `url=` on the same
search this module answers for every other type. QuestionnaireResponse comes from the spool, where
each resource is a receipt of a submission - what a client sent, not what DHIS2 now holds. And the
register's resource types - the
ones the published `D2TET_CM` takes a tracked entity type onto - come from the DHIS2 instance, per
request, and are dispatched to `dhis2w_fhir_serve.routes.register` before anything here reads the
store. Which types those are is known only once the store has been loaded, so the dispatch is a
lookup at request time rather than a second pair of routes mounted ahead of these; the register
module is imported inside the handlers because it imports the search grammar below.

A receipt is answered whatever lifecycle state it is in. `d2w fhir forward` renames a drained
receipt into `forwarded/` or `rejected/`, and a read that started 404-ing at that moment would
expire the id a client was handed at capture time on a schedule nothing told it about. Which state
a receipt is in is not a QuestionnaireResponse element, so it is not stated here; `GET /facade/spool`
answers that, along with the rest of the receipt envelope.

Search over the store is lenient in FHIR's own sense: an unrecognised parameter is ignored rather
than refused, and the Bundle's `self` link echoes only the parameters that were honored, so a client
can see what the server actually applied. The register searches this module dispatches to refuse
instead, for the reason `dhis2w_fhir_serve.routes.register` gives: what an ignored parameter costs
there is the whole register handed back as a match set.

A QuestionnaireResponse search is paged, with the same `_count` and `page` pair the register listing
uses: `Bundle.total` is the whole searchset on every page of one walk, and a client's whole job is to
follow the `next` link. The store searches are not paged - what the guide published is a fixed set
that a client asked for by name, and this facade serves one project's worth of it - but they honor
`_count` all the same, as the cap it is on those searches rather than as a page size. See
`requested_entry_cap`.

`alternatives`, `identifier_token`, `base_url`, and `bundle_response` are the parts of that
grammar that are not about the store at all - how FHIR spells a token, and what a searchset Bundle
looks like - so `dhis2w_fhir_serve.routes.register` builds its answers with the same four, and a
result set from DHIS2 is shaped exactly like one from the store.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

from dhis2w_fhir.r4 import Bundle, BundleEntry, BundleEntrySearch, BundleLink, JsonResource
from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import QueryParams
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from dhis2w_fhir_serve.capability import QUESTIONNAIRE_RESPONSE_RESOURCE_TYPE, SERVED_READ_RESOURCE_TYPES
from dhis2w_fhir_serve.errors import FHIR_JSON_MEDIA_TYPE, BadSearchError, NotFoundError, NotServedError
from dhis2w_fhir_serve.routes.context import serve_context
from dhis2w_fhir_serve.spool import (
    COUNT_PARAMETER,
    PAGE_PARAMETER,
    ResponseSpool,
    SpoolCursor,
    SpoolPage,
    page_of,
    requested_cursor,
    requested_page_size,
)
from dhis2w_fhir_serve.store import IdentifierToken, SearchQuery

#: Every resource type the facade answers a read or a search for.
SERVED_RESOURCE_TYPES = (*SERVED_READ_RESOURCE_TYPES, QUESTIONNAIRE_RESPONSE_RESOURCE_TYPE)

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


def requested_entry_cap(stated: str | None) -> int | None:
    """How many entries a client asked one searchset to carry, or None when it named no `_count`.

    `_count` on a store search is a cap and not a pagination scheme, and deliberately so. The store
    is one project's published artifacts, searched by name; a client asking for `Questionnaire`
    holding an identifier wants the artifacts that identifier names, not the first page of them. So
    a capped search states `Bundle.total` for every match and hands back the first `_count` of them
    with an honest `self` link, and offers no `next` cursor to follow: there is no walk to continue,
    only a result the client chose to see less of. The register's identifier search answers the same
    way and for the same reason - what an identifier matched is a result set, not a listing.

    `_count=0` is R4's request for the total alone: the Bundle states how many matched and carries
    no entry at all. A `_count` that is not a whole number, or is negative, is a malformed query
    rather than an ambitious one, and is refused as such.
    """
    if stated is None:
        return None
    try:
        cap = int(stated)
    except ValueError as error:
        raise BadSearchError(f"`{COUNT_PARAMETER}` was given `{stated}`, which is not a number of rows") from error
    if cap < 0:
        raise BadSearchError(f"`{COUNT_PARAMETER}` was given `{stated}`: a result carries no negative number of rows")
    return cap


def parse_store_search(params: QueryParams) -> ParsedSearch:
    """Read `_id`, `url`, and `identifier` into a store query, ignoring every other parameter."""
    ids: list[str] = []
    urls: list[str] = []
    identifiers: list[IdentifierToken] = []
    honored: list[HonoredParameter] = []
    for name, raw in params.multi_items():
        if name == "_id":
            ids.extend(alternatives(name, raw))
        elif name == "url":
            urls.extend(alternatives(name, raw))
        elif name == "identifier":
            identifiers.extend(identifier_token(name, value) for value in alternatives(name, raw))
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
            ids.extend(alternatives(name, raw))
        elif name == "questionnaire":
            questionnaires.extend(alternatives(name, raw))
        else:
            continue
        honored.append(HonoredParameter(name=name, value=raw))
    return ParsedResponseSearch(ids=tuple(ids), questionnaires=tuple(questionnaires), honored=tuple(honored))


@router.get("/{resource_type}")
async def search_resource_type(request: Request, resource_type: str) -> Response:
    """Search one served resource type, from the DHIS2 instance for a register type and from the store otherwise."""
    from dhis2w_fhir_serve.routes.register import register_resource_types, search_register

    context = serve_context(request)
    if resource_type in register_resource_types(request):
        return await search_register(request, resource_type)
    _require_served(resource_type)
    service_base = base_url(request)
    if resource_type == QUESTIONNAIRE_RESPONSE_RESOURCE_TYPE:
        return await _search_receipts(request, context.spool, service_base)
    parsed = parse_store_search(request.query_params)
    entries = [
        _bundle_entry(service_base, entry.resource_type, entry.resource_id, entry.body)
        for entry in context.store.search(resource_type, parsed.query)
    ]
    return bundle_response(
        service_base,
        resource_type,
        parsed.honored,
        entries,
        requested_entry_cap(request.query_params.get(COUNT_PARAMETER)),
    )


async def _search_receipts(request: Request, spool: ResponseSpool, service_base: str) -> Response:
    """Answer one page of the receipts as a searchset, off the event loop and newest first.

    A receipt search is a directory read - blocking work that would otherwise stall every other
    request the facade is serving - and a spool that has taken ten thousand submissions is a Bundle
    nobody asked for, so the searchset is paged with the same `page` cursor the register listing
    uses. A file that will not parse is quarantined by the read rather than failing the search: the
    client asked for the receipts that are readable, and it gets them.

    `_count=0` is the one request that is not a page: it asks how many receipts matched, and is
    answered with the total and no entries, on the same terms as every other searchset this facade
    serves. It carries no `next` link either, because a page of nothing leads nowhere.
    """
    parsed = parse_response_search(request.query_params)
    stated_count = request.query_params.get(COUNT_PARAMETER)
    cursor = requested_cursor(request.query_params.get(PAGE_PARAMETER))
    reading = await run_in_threadpool(spool.search, None, None, parsed.ids)
    matched = tuple(
        receipt
        for receipt in reading.receipts
        if not parsed.questionnaires or receipt.questionnaire in parsed.questionnaires
    )
    if requested_entry_cap(stated_count) == 0:
        return total_only_response(service_base, QUESTIONNAIRE_RESPONSE_RESOURCE_TYPE, parsed.honored, len(matched))
    count = requested_page_size(stated_count)
    page = page_of(matched, cursor, count)
    entries = [
        _bundle_entry(service_base, QUESTIONNAIRE_RESPONSE_RESOURCE_TYPE, receipt.response_id, receipt.response)
        for receipt in page.receipts
    ]
    bundle = Bundle(
        type="searchset",
        total=page.total,
        link=_receipt_links(request, service_base, parsed.honored, page, count),
        entry=entries or None,
    )
    return Response(content=bundle.model_dump_json(exclude_none=True, by_alias=True), media_type=FHIR_JSON_MEDIA_TYPE)


def _receipt_links(
    request: Request,
    service_base: str,
    honored: tuple[HonoredParameter, ...],
    page: SpoolPage,
    count: int,
) -> list[BundleLink]:
    """`self`, and the neighbours that exist - each naming the page it leads to, explicitly."""
    links = [BundleLink(relation="self", url=_receipt_page_url(service_base, honored, page.cursor, count))]
    if page.previous_cursor is not None:
        links.append(
            BundleLink(relation="previous", url=_receipt_page_url(service_base, honored, page.previous_cursor, count))
        )
    if page.next_cursor is not None:
        links.append(BundleLink(relation="next", url=_receipt_page_url(service_base, honored, page.next_cursor, count)))
    return links


def _receipt_page_url(service_base: str, honored: tuple[HonoredParameter, ...], cursor: SpoolCursor, count: int) -> str:
    """One page of the receipt search, carrying the filters that were applied along with the cursor."""
    parameters = [(parameter.name, parameter.value) for parameter in honored]
    parameters.extend([(COUNT_PARAMETER, str(count)), (PAGE_PARAMETER, cursor.token())])
    return f"{service_base}/{QUESTIONNAIRE_RESPONSE_RESOURCE_TYPE}?{urlencode(parameters)}"


@router.get("/{resource_type}/{resource_id}")
async def read_resource(request: Request, resource_type: str, resource_id: str) -> Response:
    """Answer one resource: from the DHIS2 instance for a register type, from the store or the spool otherwise."""
    from dhis2w_fhir_serve.routes.register import read_registered_entity, register_resource_types

    context = serve_context(request)
    if resource_type in register_resource_types(request):
        return await read_registered_entity(request, resource_type, resource_id)
    _require_served(resource_type)
    if resource_type == QUESTIONNAIRE_RESPONSE_RESOURCE_TYPE:
        receipt = await run_in_threadpool(context.spool.get, resource_id)
        if receipt is None:
            raise NotFoundError(resource_type, resource_id)
        return JSONResponse(content=receipt.response, media_type=FHIR_JSON_MEDIA_TYPE)
    entry = context.store.by_type_and_id(resource_type, resource_id)
    if entry is None:
        raise NotFoundError(resource_type, resource_id)
    return JSONResponse(content=entry.body, media_type=FHIR_JSON_MEDIA_TYPE)


def _require_served(resource_type: str) -> None:
    """Refuse a resource type the facade does not serve, whatever the store happens to hold."""
    if resource_type not in SERVED_RESOURCE_TYPES:
        raise NotServedError(resource_type)


def alternatives(name: str, raw: str) -> list[str]:
    """Split one parameter into its comma-separated alternatives, refusing an empty one."""
    values = [value.strip() for value in raw.split(",")]
    if any(not value for value in values):
        raise BadSearchError(f"`{name}` was given an empty value")
    return values


def identifier_token(parameter: str, value: str) -> IdentifierToken:
    """Read a `system|value` token; a bare value, or an empty system, matches the value in any system.

    The parameter is named so the refusal names it: `identifier` and `_tag` are both token searches
    over the same grammar, and a client told its `identifier` was malformed when it wrote a `_tag`
    would look in the wrong half of its query.
    """
    if "|" not in value:
        return IdentifierToken(value=value)
    system, _, token = value.partition("|")
    if not token:
        raise BadSearchError(f"`{parameter}` token `{value}` names a system but no value")
    return IdentifierToken(system=system or None, value=token)


def base_url(request: Request) -> str:
    """The service base every `fullUrl` and `self` link is built from, without its trailing slash."""
    return str(request.base_url).rstrip("/")


def _bundle_entry(base_url: str, resource_type: str, resource_id: str, body: dict[str, Any]) -> BundleEntry:
    """Carry one resource into the result set at the URL it is served from."""
    return BundleEntry(
        fullUrl=f"{base_url}/{resource_type}/{resource_id}",
        resource=JsonResource.model_validate(body),
        search=BundleEntrySearch(mode="match"),
    )


def bundle_response(
    base_url: str,
    resource_type: str,
    honored: tuple[HonoredParameter, ...],
    entries: list[BundleEntry],
    cap: int | None = None,
) -> Response:
    """Serialise the result set: `total` is every match, `entry` is what `_count` let through.

    The `self` link names the parameters that were applied and the cap that was applied with them,
    so a client reading it back sees both what selected the matches and how many of them it is
    holding. `total` is the whole match set whether or not the cap cut it short - R4 defines it as
    the number of resources that matched the search, not the number on this page.
    """
    parameters = [(parameter.name, parameter.value) for parameter in honored]
    if cap is not None:
        parameters.append((COUNT_PARAMETER, str(cap)))
    query = urlencode(parameters)
    self_url = f"{base_url}/{resource_type}?{query}" if query else f"{base_url}/{resource_type}"
    served = entries if cap is None else entries[:cap]
    bundle = Bundle(
        type="searchset",
        total=len(entries),
        link=[BundleLink(relation="self", url=self_url)],
        entry=served or None,
    )
    return Response(
        content=bundle.model_dump_json(exclude_none=True, by_alias=True),
        media_type=FHIR_JSON_MEDIA_TYPE,
    )


def total_only_response(
    base_url: str,
    resource_type: str,
    honored: tuple[HonoredParameter, ...],
    total: int | None,
) -> Response:
    """Answer `_count=0` on a paged search: how many matched, and none of them.

    The paged searches cannot express this through `bundle_response`, because their total is a count
    of the whole listing rather than of the entries they were handed. A total of None is the answer
    a register listing gives when the instance stated no count for one of the types in it, and the
    Bundle then states no total rather than a number nobody counted.
    """
    parameters = [(parameter.name, parameter.value) for parameter in honored]
    parameters.append((COUNT_PARAMETER, "0"))
    bundle = Bundle(
        type="searchset",
        total=total,
        link=[BundleLink(relation="self", url=f"{base_url}/{resource_type}?{urlencode(parameters)}")],
    )
    return Response(
        content=bundle.model_dump_json(exclude_none=True, by_alias=True),
        media_type=FHIR_JSON_MEDIA_TYPE,
    )
