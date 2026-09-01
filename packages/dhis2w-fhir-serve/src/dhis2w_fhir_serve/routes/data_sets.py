"""`GET /facade/data-sets/{uid}/responses` - what DHIS2 holds for one form, read from the instance per request.

THE RECEIPTS ANSWER WHAT WAS SUBMITTED AND THIS ANSWERS WHAT THE INSTANCE HOLDS. A stored
QuestionnaireResponse is evidence of a submission; this reads `/api/dataValueSets` while the client
waits and serves what came back as the `QuestionnaireResponse` the data set's own published form
describes - the same document a client posts a capture in. It is the aggregate half of what
`GET /facade/tracked-entities/{uid}/events` is for a tracker event, and it closes the read leg: a
client can capture a form through the guide and read it back through the guide without ever speaking
the DHIS2 API.

IT IS THE FACADE'S ADDRESS AND A FHIR DOCUMENT, WHICH IS NOT A CONTRADICTION. FHIR defines no
interaction at a DHIS2 data set's address - the CapabilityStatement names this one in prose and
declares nothing at it, exactly as it names the record - so the address belongs to this facade and
sits under its mount. What comes back is still a FHIR searchset Bundle under `application/fhir+json`,
so this router carries the `Accept` negotiation the rest of the facade API does not.
`dhis2w_fhir_serve.routes.ServeRouters.negotiated` is that requirement stated as data.

**`orgUnit` and `period` are required, and that is a bound rather than a permission.** A read missing
either is a read of every organisation unit for every period the data set collects, which on a
national data set is the whole instance in one response. Nothing here decides who may see what: an
aggregate value's only subject is an organisation unit, so there is no walk from something a caller
may see to something they may not, and the rights stay DHIS2's - every read carries the caller's own
`Authorization` under a forwarding posture, and DHIS2 enforces sharing on the data set, on the
category options behind both combos, and on the organisation unit against the caller's data view
scope. `dhis2w_fhir_serve.passthrough` is the whole of how.

**`period` repeats, up to a stated maximum.** Several periods are several reporting keys and
therefore several documents, which is what a client comparing this month against last month wants.
Every one of them is read whole, so the count is what bounds the request's cost, and
`[serve.data_sets] period_limit` is where a project writes down how much it will answer at once. A
request above it is refused with both numbers, because splitting the read is the client's move and it
cannot make it without knowing the limit.

**Live mode only, and gated once.** A compiled guide has no instance behind it and says so.
`[serve.data_sets] responses = false` takes this surface away and leaves the published forms, the
receipts, and the register exactly as they were. There is no second key beside it, because there is
no aggregate register for one to take away.

**A page is a slice of the selection, and the selection is read whole.** `/api/dataValueSets` offers
no cursor and no offset - its `limit` truncates silently - so the bounded selection arrives in one
answer and this server pages the ordered result. `Bundle.total` is therefore every document this
caller may see, counted under their own credentials. The order is the reporting key itself,
`(orgUnit, period, attributeOptionCombo)` ascending, so two reads of an unchanged period answer the
same bytes (BUGS.md 108 is why an order is stated rather than passed on).

**Every entry names the URL its document is really served at.** One form is read at
`GET /facade/data-sets/{uid}/responses/{responseId}`, where the response id is the three reporting
keys the read was bounded by - so the id names the read, and the item route needs no parameters of
its own. `QuestionnaireResponse/{id}` on this server is deliberately NOT that URL: that address
answers the spool, where a resource of that id is a receipt of what a client submitted.

**The parameters are `orgUnit`, `period`, `attributeOptionCombo`, `_count`, and `page`, and anything
else is refused.** A parameter this surface cannot apply, ignored, would answer a narrower question
with the whole selection - the same reason the register and the record refuse one.
"""

from __future__ import annotations

from urllib.parse import urlencode

from dhis2w_client.errors import Dhis2ClientError
from dhis2w_fhir.grouping import ReportedForm, group_data_values
from dhis2w_fhir.period import parse_period
from dhis2w_fhir.r4 import Bundle, BundleEntry, BundleEntrySearch, BundleLink, QuestionnaireResponse, json_resource
from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from dhis2w_fhir_serve.capture.index import CaptureIndex
from dhis2w_fhir_serve.errors import (
    FHIR_JSON_MEDIA_TYPE,
    BadSearchError,
    DataSetResponsesDisabledError,
    MissingSearchParameterError,
    NotFoundError,
    NotServedFromCompiledIgError,
    TooManySearchValuesError,
    UnsupportedSearchParameterError,
    UpstreamError,
)
from dhis2w_fhir_serve.history.aggregate import (
    DEFAULT_ATTRIBUTE_OPTION_COMBO,
    RESPONSE_ID_SEPARATOR,
    AggregateProjection,
    response_id,
)
from dhis2w_fhir_serve.history.data_values import fetch_data_values
from dhis2w_fhir_serve.passthrough import RegisterReader, register_reader
from dhis2w_fhir_serve.register.wire import upstream_refusal_text
from dhis2w_fhir_serve.routes.capture import capture_state
from dhis2w_fhir_serve.routes.context import serve_context
from dhis2w_fhir_serve.routes.history import FhirJsonResponse, record_base_url
from dhis2w_fhir_serve.routes.negotiation import FORMAT_PARAMETER
from dhis2w_fhir_serve.routes.read import requested_entry_cap
from dhis2w_fhir_serve.spool import COUNT_PARAMETER, PAGE_PARAMETER, SpoolCursor, requested_cursor

#: Where a data set's responses are served from, under the facade API's mount and under the data set
#: whose responses they are - the same shape the tracked entity record takes one level down.
DATA_SET_RESPONSES_PATH = "/data-sets/{data_set_uid}/responses"
DATA_SET_RESPONSE_PATH = "/data-sets/{data_set_uid}/responses/{response_id}"

#: What these two operations are grouped under in the facade API's document.
DATA_SET_TAG = "Data sets"

#: What the config refusals name, so a client reads one word for the whole surface.
RESPONSES_SURFACE_NAME = "responses"

#: What a 404 names, which is the one thing that was asked for rather than the surface it was asked of.
DATA_SET_NAME = "data set"
RESPONSE_NAME = "reported form"

#: The two parameters that bound the read, what naming them looks like, and what omitting either costs.
ORGANISATION_UNIT_PARAMETER = "orgUnit"
PERIOD_PARAMETER = "period"
ATTRIBUTE_OPTION_COMBO_PARAMETER = "attributeOptionCombo"
BOUNDED_READ_REQUIREMENT = "a data set's responses are read with `orgUnit` and at least one `period`"
UNBOUNDED_READ_COST = (
    "a read naming neither is every organisation unit that reports the data set, for every period it "
    "collects, in one answer"
)

#: The config key a period count is bounded by, named in the refusal that enforces it.
PERIOD_LIMIT_KEY = "[serve.data_sets] period_limit"

#: The parameters a responses read answers. Everything else is refused rather than ignored.
ANSWERED_PARAMETERS = (
    ORGANISATION_UNIT_PARAMETER,
    PERIOD_PARAMETER,
    ATTRIBUTE_OPTION_COMBO_PARAMETER,
    COUNT_PARAMETER,
    PAGE_PARAMETER,
)

#: The parameters one reported form's own read answers, which is none: its id names all three keys.
ANSWERED_ITEM_PARAMETERS = (FORMAT_PARAMETER,)

#: How many keys a response id carries, and what the third one is when the data set rides the
#: default category combo.
_RESPONSE_ID_KEYS = 3

router = APIRouter()


class ResponseSelection(BaseModel):
    """What one read is bounded by: the data set, the unit, the periods, and the combo it narrows to."""

    model_config = ConfigDict(frozen=True)

    data_set_uid: str
    organisation_unit_uid: str
    period_isos: tuple[str, ...]
    attribute_option_combo_uid: str | None = None


class ResponsePage(BaseModel):
    """One page of a data set's responses: the forms on it, and where the pages either side of it are."""

    model_config = ConfigDict(frozen=True)

    forms: tuple[ReportedForm, ...] = ()
    total: int = 0
    cursor: SpoolCursor = SpoolCursor()
    next_cursor: SpoolCursor | None = None
    previous_cursor: SpoolCursor | None = None


@router.get(
    DATA_SET_RESPONSES_PATH,
    tags=[DATA_SET_TAG],
    summary="Read what DHIS2 holds for one data set",
    description=(
        "What the DHIS2 instance holds for one data set, at one organisation unit, over the periods "
        "this request names - each reporting key as the QuestionnaireResponse the data set's own "
        "published form describes, which is the same shape a client posts a capture in.\n\n"
        "`orgUnit` and one or more `period` values are required: a read missing either is every "
        "organisation unit for every period the data set collects. `period` repeats up to "
        "`[serve.data_sets] period_limit`, `attributeOptionCombo` narrows the answer to values filed "
        "under one combo, `_count` and `page` walk the pages, `_count=0` asks how many forms the "
        "selection holds, and any other parameter is refused rather than ignored.\n\n"
        "The answer is a FHIR searchset `Bundle` under `application/fhir+json`. `total` is every form "
        "this caller may see, counted under their own credentials.\n\n"
        "Live runs only, and gated by `[serve.data_sets] responses`."
    ),
    response_class=FhirJsonResponse,
    responses={200: {"model": Bundle, "description": "One page of the selection as a FHIR searchset Bundle."}},
)
async def read_data_set_responses(request: Request, data_set_uid: str) -> Response:
    """Answer one page of what the instance holds for one data set, ordered by the reporting key."""
    reader = await _reader(request)
    selection = _selection(request, data_set_uid)
    projection = _projection(request)
    index = _published_form(request, projection, selection)
    service_base = record_base_url(request)
    forms = await _reported_forms(reader, selection)
    if requested_entry_cap(request.query_params.get(COUNT_PARAMETER)) == 0:
        return _selection_length(service_base, selection, len(forms))
    count = _requested_count(request)
    page = _page_of(forms, requested_cursor(request.query_params.get(PAGE_PARAMETER)), count)
    bundle = Bundle(
        type="searchset",
        total=page.total,
        link=_links(service_base, selection, page, count),
        entry=[_entry(service_base, selection, projection.project(index, form)) for form in page.forms] or None,
    )
    return Response(content=bundle.model_dump_json(exclude_none=True, by_alias=True), media_type=FHIR_JSON_MEDIA_TYPE)


@router.get(
    DATA_SET_RESPONSE_PATH,
    tags=[DATA_SET_TAG],
    summary="Read one reported form of a data set",
    description=(
        "One reporting key of one data set - one organisation unit, one period, one attribute option "
        "combo - as the QuestionnaireResponse the data set's published form describes, which is the "
        "document each entry of the collection above links to.\n\n"
        "The response id carries all three keys, so this read needs no parameters: it is "
        "`{orgUnit}-{period}-{attributeOptionCombo}`, with `default` in the third place where the "
        "values named no attribute option combo at all."
    ),
    response_class=FhirJsonResponse,
    responses={200: {"model": QuestionnaireResponse, "description": "The reported form as the form's own document."}},
)
async def read_data_set_response(request: Request, data_set_uid: str, response_id: str) -> Response:
    """Answer one reported form of one data set, which is what a page's entry links to.

    The id is the three keys the read is bounded by, so it is read straight rather than looked for
    inside a wider selection - which is what keeps this read as narrow as the collection's own.
    """
    reader = await _reader(request)
    _require_answerable_parameters(request, ANSWERED_ITEM_PARAMETERS)
    selection = _selection_of(data_set_uid, response_id)
    projection = _projection(request)
    index = _published_form(request, projection, selection)
    found = next((form for form in await _reported_forms(reader, selection) if _matches(form, response_id)), None)
    if found is None:
        raise NotFoundError(RESPONSE_NAME, response_id)
    return JSONResponse(
        content=projection.project(index, found).model_dump(mode="json", exclude_none=True, by_alias=True),
        media_type=FHIR_JSON_MEDIA_TYPE,
    )


async def _reader(request: Request) -> RegisterReader:
    """What this request reads the instance through, refusing every way this process serves no responses.

    The project's own word comes first: a project that publishes its forms and not what was reported
    against them says so before a client is told to restart the process with `--live`. The connection
    comes next, which is also where a forwarding posture refuses a request carrying no credential,
    since what comes back is read as the caller. Both are settled before a parameter is read and
    before the instance is asked anything.
    """
    if not serve_context(request).settings.data_sets.responses:
        raise DataSetResponsesDisabledError(RESPONSES_SURFACE_NAME)
    reader = await register_reader(request)
    if reader is None:
        raise NotServedFromCompiledIgError(RESPONSES_SURFACE_NAME)
    return reader


def _projection(request: Request) -> AggregateProjection:
    """What this request projects the reported values through: the project's names, forms, and zone.

    The naming and the index cache are the capture path's own, which is the point: the form a value
    is read back through is the form a submission of that value is checked against, so one form can
    never type a cell one way on the way in and another on the way out.
    """
    context = serve_context(request)
    state = capture_state(request)
    return AggregateProjection(
        naming=state.naming,
        store=context.store,
        indexes=state.indexes,
        timezone=context.project.config.generate.timezone,
    )


def _published_form(request: Request, projection: AggregateProjection, selection: ResponseSelection) -> CaptureIndex:
    """The served form the read is projected through, or a 404 for a data set this project serves none for.

    A 404 rather than an entry in the answer, and that is where this differs from an event of an
    unpublished program stage: a data set the guide publishes no form for has no partial selection to
    page - there is nothing to serve the values as, and nothing else the request could have meant.

    A data set outside a stated `[serve.data_sets] data_sets` list is answered exactly the same way,
    and deliberately: a project that named the data sets it answers for has said the others are not
    served here, and a refusal that named the key instead would tell every caller which data sets the
    instance holds.
    """
    served = serve_context(request).settings.data_sets.data_sets
    if served and selection.data_set_uid not in served:
        raise NotFoundError(DATA_SET_NAME, selection.data_set_uid)
    index = projection.form_for(selection.data_set_uid)
    if index is None:
        raise NotFoundError(DATA_SET_NAME, selection.data_set_uid)
    return index


def _selection(request: Request, data_set_uid: str) -> ResponseSelection:
    """Read the bounds one collection request states, refusing every way it states none this server answers."""
    _require_answerable_parameters(request, ANSWERED_PARAMETERS)
    limit = serve_context(request).settings.data_sets.period_limit
    organisation_unit_uid = _required_value(request, ORGANISATION_UNIT_PARAMETER)
    periods = tuple(value.strip() for value in request.query_params.getlist(PERIOD_PARAMETER) if value.strip())
    if not periods:
        raise MissingSearchParameterError(
            RESPONSES_SURFACE_NAME, PERIOD_PARAMETER, BOUNDED_READ_REQUIREMENT, UNBOUNDED_READ_COST
        )
    if len(periods) > limit:
        raise TooManySearchValuesError(RESPONSES_SURFACE_NAME, PERIOD_PARAMETER, len(periods), limit, PERIOD_LIMIT_KEY)
    for period in periods:
        _require_dhis2_period(period)
    combo = request.query_params.get(ATTRIBUTE_OPTION_COMBO_PARAMETER)
    return ResponseSelection(
        data_set_uid=data_set_uid,
        organisation_unit_uid=organisation_unit_uid,
        period_isos=periods,
        attribute_option_combo_uid=combo.strip() if combo and combo.strip() else None,
    )


def _selection_of(data_set_uid: str, stated_response_id: str) -> ResponseSelection:
    """Read one response id back into the three keys it names, refusing a value that names anything else."""
    parts = stated_response_id.split(RESPONSE_ID_SEPARATOR)
    if len(parts) != _RESPONSE_ID_KEYS or not all(parts):
        raise NotFoundError(RESPONSE_NAME, stated_response_id)
    organisation_unit_uid, period, combo = parts
    _require_dhis2_period(period)
    return ResponseSelection(
        data_set_uid=data_set_uid,
        organisation_unit_uid=organisation_unit_uid,
        period_isos=(period,),
        attribute_option_combo_uid=None if combo == DEFAULT_ATTRIBUTE_OPTION_COMBO else combo,
    )


def _required_value(request: Request, parameter: str) -> str:
    """One parameter this read is bounded by, or the refusal naming what the read needs and why."""
    stated = request.query_params.get(parameter)
    if stated is None or not stated.strip():
        raise MissingSearchParameterError(
            RESPONSES_SURFACE_NAME, parameter, BOUNDED_READ_REQUIREMENT, UNBOUNDED_READ_COST
        )
    return stated.strip()


def _require_dhis2_period(period: str) -> None:
    """Refuse a period this server cannot read as one, before the instance is asked about it.

    DHIS2 answers a period it cannot parse with an empty export rather than a refusal, so a client
    that mistyped one would read "nothing was reported" where the truth is "nobody asked".
    """
    try:
        parse_period(period)
    except ValueError as error:
        raise BadSearchError(
            f"`{PERIOD_PARAMETER}` was given `{period}`, which is not a DHIS2 period identifier "
            "(`202601` for January 2026, `2026Q1` for a quarter, `20260115` for a day)"
        ) from error


def _require_answerable_parameters(request: Request, answered: tuple[str, ...]) -> None:
    """Refuse a read naming a parameter this surface cannot apply to it.

    `_format` is passed over: it names the format the answer comes back in, which the negotiation
    settled before this ran, and it narrows the answer by nothing.
    """
    for name in request.query_params:
        if name not in answered and name != FORMAT_PARAMETER:
            raise UnsupportedSearchParameterError(RESPONSES_SURFACE_NAME, name, answered)


async def _reported_forms(reader: RegisterReader, selection: ResponseSelection) -> tuple[ReportedForm, ...]:
    """Read the bounded selection whole and order it by the reporting key, newest nothing and oldest nothing.

    A total order rather than a recency one: an aggregate form has no instant, only a period, and two
    reads of an unchanged period have to answer the same bytes. The attribute option combo is filtered
    here rather than sent to the instance, for the reason `history.data_values` states.
    """
    try:
        envelope = await fetch_data_values(
            reader,
            data_set_uid=selection.data_set_uid,
            organisation_unit_uid=selection.organisation_unit_uid,
            period_isos=selection.period_isos,
        )
    except Dhis2ClientError as error:
        raise UpstreamError(
            f"the DHIS2 instance did not answer the data value read: {upstream_refusal_text(error)}"
        ) from error
    default_period = selection.period_isos[0] if len(selection.period_isos) == 1 else None
    grouped = group_data_values(envelope, default_period_iso=default_period)
    narrowed = [
        form
        for form in grouped
        if form.organisation_unit_uid
        and form.period_iso
        and (
            selection.attribute_option_combo_uid is None
            or form.attribute_option_combo_uid == selection.attribute_option_combo_uid
        )
    ]
    return tuple(sorted(narrowed, key=lambda form: form.reporting_key))


def _matches(form: ReportedForm, stated_response_id: str) -> bool:
    """Whether one reported form is the one an id names, compared on the id the form itself mints."""
    return response_id(form) == stated_response_id


def _requested_count(request: Request) -> int:
    """How many forms this page carries: what the client asked for, bounded by what the project allows."""
    data_sets = serve_context(request).settings.data_sets
    cap = requested_entry_cap(request.query_params.get(COUNT_PARAMETER))
    return data_sets.page_size if cap is None else min(cap, data_sets.page_size_limit)


def _page_of(forms: tuple[ReportedForm, ...], cursor: SpoolCursor, count: int) -> ResponsePage:
    """Slice one page out of the ordered selection, and name the pages either side of it.

    An offset past the end is an empty page rather than a refusal, for the reason the receipts listing
    gives: a link minted before a value was deleted has become a page with nothing on it, and that is
    a true statement about the selection rather than a malformed request.
    """
    offset = min(cursor.offset, len(forms))
    page = forms[offset : offset + count]
    following = offset + len(page)
    return ResponsePage(
        forms=page,
        total=len(forms),
        cursor=SpoolCursor(offset=offset),
        next_cursor=SpoolCursor(offset=following) if following < len(forms) else None,
        previous_cursor=SpoolCursor(offset=max(offset - count, 0)) if offset > 0 else None,
    )


def _selection_length(service_base: str, selection: ResponseSelection, total: int) -> Response:
    """Answer `_count=0` with how many forms the selection holds and none of them."""
    bundle = Bundle(
        type="searchset",
        total=total,
        link=[
            BundleLink(
                relation="self",
                url=f"{service_base}{_responses_path(selection)}?{_query(selection, [(COUNT_PARAMETER, '0')])}",
            )
        ],
    )
    return Response(content=bundle.model_dump_json(exclude_none=True, by_alias=True), media_type=FHIR_JSON_MEDIA_TYPE)


def _links(service_base: str, selection: ResponseSelection, page: ResponsePage, count: int) -> list[BundleLink]:
    """`self`, and the neighbours that exist - each naming the page it leads to, explicitly."""
    links = [BundleLink(relation="self", url=_page_url(service_base, selection, page.cursor, count))]
    if page.previous_cursor is not None:
        links.append(
            BundleLink(relation="previous", url=_page_url(service_base, selection, page.previous_cursor, count))
        )
    if page.next_cursor is not None:
        links.append(BundleLink(relation="next", url=_page_url(service_base, selection, page.next_cursor, count)))
    return links


def _page_url(service_base: str, selection: ResponseSelection, cursor: SpoolCursor, count: int) -> str:
    """One page of the selection as a client may ask for it again and be given the same page."""
    query = _query(selection, [(COUNT_PARAMETER, str(count)), (PAGE_PARAMETER, cursor.token())])
    return f"{service_base}{_responses_path(selection)}?{query}"


def _query(selection: ResponseSelection, paging: list[tuple[str, str]]) -> str:
    """The whole query one link carries: the bounds the read was made under, then the paging.

    The bounds ride on every link because they are what the read is: a `next` link that dropped them
    would name a request this server refuses, and a client following it would be told to name an
    organisation unit it had already named.
    """
    parameters = [(ORGANISATION_UNIT_PARAMETER, selection.organisation_unit_uid)]
    parameters.extend((PERIOD_PARAMETER, period) for period in selection.period_isos)
    if selection.attribute_option_combo_uid is not None:
        parameters.append((ATTRIBUTE_OPTION_COMBO_PARAMETER, selection.attribute_option_combo_uid))
    parameters.extend(paging)
    return urlencode(parameters)


def _entry(service_base: str, selection: ResponseSelection, response: QuestionnaireResponse) -> BundleEntry:
    """Carry one projected form into the result set at the URL this server serves it from."""
    return BundleEntry(
        fullUrl=f"{service_base}{_responses_path(selection)}/{response.id}",
        resource=json_resource(response),
        search=BundleEntrySearch(mode="match"),
    )


def _responses_path(selection: ResponseSelection) -> str:
    """Where one data set's responses are served, as a path a link can be built from."""
    return DATA_SET_RESPONSES_PATH.format(data_set_uid=selection.data_set_uid)
