"""`GET /cds-services` and `POST /cds-services/{id}` - CDS Hooks, one service wide.

IT IS AT THE BASE URL AND IT IS NOT FHIR, WHICH IS THE ONE THING TO SAY FIRST. Everything else this
facade answers in plain JSON about itself - the receipts, the settings, the evaluator, the
vocabularies - is served under `/facade`, and this is not, because the path is not ours. CDS Hooks
fixes discovery at `{base}/cds-services` exactly as FHIR fixes `{base}/metadata`: an EHR configured
with this server's base URL asks for that path and no other, and a specification's path is not a
thing an implementation may move. So the base URL carries three families - FHIR's, CDS Hooks', and
the `/facade` mount - and two of the three are somebody else's specification.
`dhis2w_fhir_serve.routes` states the mounting.

WHAT IS HERE. The discovery document CDS Hooks defines, listing exactly one service, and that
service's invocation endpoint. The service evaluates a CQL library over the resources the hook
prefetched and answers one card per define that had something to say. That is the whole of it: there
is no feedback endpoint, no `systemActions`, no suggestions, no SMART links, and no second service.
Each of those is a real part of the specification and none of them would mean anything from a facade
that holds no EHR state - a suggestion is an offer to write into a record this server does not have.

WHERE THE LIBRARY COMES FROM. Two ways, both stated in the request's own hook context. `library` is
CQL text the caller wrote, which is what makes this useful before a guide publishes any Library at
all; `libraryId` names a Library resource in the served guide, whose inline `content` this server
decodes. Naming neither is refused, because a decision-support service with no logic in it is a
service that would answer no cards and teach nobody why.

Both of those are extensions of the hook context this facade invented, and they are the honest place
for them: CDS Hooks fixes the shape of a `patient-view` context and has no slot for "the rules to
run", because in the specification's world the service *is* the rules. Here the rules are the
caller's, which is what makes this a playground for a guide's own CQL rather than a deployed decision
support service.

WHAT BECOMES A CARD. A define answering true becomes an `info` card summarising the define's name; a
define answering a non-empty string becomes an `info` card whose summary is that string. Everything
else - false, null, an empty collection, a number, a resource - becomes no card, because CDS Hooks
cards are sentences shown to a clinician and there is no honest sentence to make out of a Patient.
A library that will not parse becomes one `warning` card carrying the parser's own message: an EHR
gets an answer it can render rather than a 500 it can only log.

THE DATA IS THE PREFETCH, AND NOTHING ELSE. `fhirServer` and `fhirAuthorization` are read off the
request and deliberately never followed: a facade that called back out to whatever URL a hook named
would be a request-forgery engine wearing a decision-support hat. What the EHR prefetched is what
the library sees.
"""

from __future__ import annotations

import base64
import binascii
from typing import TYPE_CHECKING, Any, Literal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request

from dhis2w_fhir_serve.errors import BadOperationError, NotFoundError
from dhis2w_fhir_serve.evaluation import (
    DiagnosticKind,
    EvaluationLanguage,
    EvaluationOutcome,
    evaluate_source,
)
from dhis2w_fhir_serve.routes.context import serve_context

if TYPE_CHECKING:
    from dhis2w_fhir_serve.store import ResourceStore

#: Where the discovery document and the one service are served from. Lowercase, so nothing collides.
CDS_SERVICES_PATH = "/cds-services"
CDS_SERVICE_PATH = "/cds-services/{service_id}"

#: The one service this facade offers, and the hook it answers on.
CQL_LIBRARY_SERVICE_ID = "cql-library"
CQL_LIBRARY_SERVICE_HOOK = "patient-view"

#: The resource type a served library is read from, and the media type its inline content must be.
LIBRARY_RESOURCE_TYPE = "Library"
CQL_CONTENT_TYPE = "text/cql"

CardIndicator = Literal["info", "warning", "critical"]
"""How urgent a card is, in CDS Hooks' own three words."""

#: The card urgency each kind of answer is given. Nothing here is ever `critical`: this server has no
#: clinical claim to make, and an EHR that saw one would be right to act on it.
INFORMATION_INDICATOR: CardIndicator = "info"
WARNING_INDICATOR: CardIndicator = "warning"

router = APIRouter()


class CdsService(BaseModel):
    """One service in the discovery document: what it answers on, what it is, and what it wants prefetched."""

    model_config = ConfigDict(frozen=True)

    id: str
    hook: str
    title: str
    description: str
    prefetch: dict[str, str] = Field(default_factory=dict)
    """The prefetch templates an EHR fills before invoking, keyed the way the request carries them."""

    usageRequirements: str | None = None
    """What a caller must supply beyond the hook's own context for this service to answer anything."""


class CdsDiscovery(BaseModel):
    """`GET /cds-services` - every service this facade offers, which is one."""

    model_config = ConfigDict(frozen=True)

    services: tuple[CdsService, ...] = ()


class CqlLibraryHookContext(BaseModel):
    """The hook's context, plus the two elements this facade adds to say which rules to run.

    `extra="allow"` because a hook context is the EHR's to shape: `patient-view` carries `userId`,
    `patientId`, and `encounterId` today, and a hook this service is later pointed at will carry
    something else entirely. Refusing a context element this facade does not read would refuse
    perfectly valid invocations.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    patient_id: str | None = Field(default=None, alias="patientId")
    user_id: str | None = Field(default=None, alias="userId")
    library: str | None = None
    """The CQL library text to evaluate, when the caller brings its own rules."""

    library_id: str | None = Field(default=None, alias="libraryId")
    """The id of a Library resource in the served guide, when the guide publishes the rules."""

    expression_name: str | None = Field(default=None, alias="expressionName")
    """One define to answer. Omitted, every define the library declares is considered for a card."""


class CdsHookRequest(BaseModel):
    """One hook invocation as CDS Hooks defines it, read down to what this service acts on."""

    model_config = ConfigDict(populate_by_name=True)

    hook: str
    hook_instance: str = Field(alias="hookInstance")
    context: CqlLibraryHookContext = Field(default_factory=CqlLibraryHookContext)
    prefetch: dict[str, Any] = Field(default_factory=dict)
    """What the EHR read for this invocation - the same HTTP-boundary escape hatch `StoreEntry.body` documents.

    Each value is a FHIR resource or a Bundle of them, of whatever types the EHR's prefetch templates
    named, and all of it goes to the evaluator as the FHIR-shaped JSON the engine reads.
    """

    fhir_server: str | None = Field(default=None, alias="fhirServer")
    """The EHR's own FHIR base. Read and never followed - see this module's docstring."""


class CdsCardSource(BaseModel):
    """Who is saying this: the guide whose logic produced the card."""

    model_config = ConfigDict(frozen=True)

    label: str
    url: str | None = None


class CdsCard(BaseModel):
    """One thing this service has to say about the patient in front of the user."""

    model_config = ConfigDict(frozen=True)

    summary: str
    indicator: CardIndicator
    source: CdsCardSource
    detail: str | None = None


class CdsHookResponse(BaseModel):
    """What one invocation answered. An empty card list is an answer: the rules had nothing to say."""

    model_config = ConfigDict(frozen=True)

    cards: tuple[CdsCard, ...] = ()


@router.get(CDS_SERVICES_PATH)
async def discover_services(request: Request) -> CdsDiscovery:
    """List the services this facade offers, which is the one that runs a CQL library over a prefetch."""
    return CdsDiscovery(
        services=(
            CdsService(
                id=CQL_LIBRARY_SERVICE_ID,
                hook=CQL_LIBRARY_SERVICE_HOOK,
                title="Evaluate a CQL library",
                description=(
                    "Evaluates a CQL library over the prefetched resources and answers one card per define "
                    "that resolves to true or to a message. The library is the caller's: send it as "
                    "`context.library`, or name a Library this guide publishes as `context.libraryId`."
                ),
                prefetch={
                    "patient": "Patient/{{context.patientId}}",
                    "conditions": "Condition?patient={{context.patientId}}",
                    "observations": "Observation?patient={{context.patientId}}",
                },
                usageRequirements=(
                    "Send the rules to run as `context.library` (CQL text) or `context.libraryId` "
                    "(a Library published by this guide). This service holds no rules of its own."
                ),
            ),
        )
    )


@router.post(CDS_SERVICE_PATH)
async def invoke_service(request: Request, service_id: str, invocation: CdsHookRequest) -> CdsHookResponse:
    """Run the named service's library over what the hook prefetched, and answer the cards it produced.

    The evaluation runs off the event loop for the reason `POST /facade/evaluate` runs off it: parsing
    a grammar and walking a tree is blocking work a facade must not do inline.
    """
    if service_id != CQL_LIBRARY_SERVICE_ID:
        raise NotFoundError("cds-services", service_id)
    context = serve_context(request)
    source = _library_source(invocation.context, context.store)
    outcome = await run_in_threadpool(
        evaluate_source,
        EvaluationLanguage.CQL,
        source,
        _prefetched_bundle(invocation),
        invocation.context.expression_name,
    )
    return CdsHookResponse(cards=_cards(outcome, CdsCardSource(label=context.project.config.ig.title)))


def _library_source(context: CqlLibraryHookContext, store: ResourceStore) -> str:
    """The CQL this invocation asked to be run: the caller's own text, or a Library the guide publishes."""
    if context.library is not None and context.library.strip() != "":
        return context.library
    if context.library_id is None:
        raise BadOperationError(
            "this service holds no rules of its own: send the CQL to run as `context.library`, or name a "
            "Library this guide publishes as `context.libraryId`"
        )
    entry = store.by_type_and_id(LIBRARY_RESOURCE_TYPE, context.library_id)
    if entry is None:
        raise NotFoundError(LIBRARY_RESOURCE_TYPE, context.library_id)
    decoded = _inline_cql(entry.body)
    if decoded is None:
        raise BadOperationError(
            f"`{LIBRARY_RESOURCE_TYPE}/{context.library_id}` carries no inline `{CQL_CONTENT_TYPE}` content; "
            "this server runs the CQL a Library embeds and never fetches one by url"
        )
    return decoded


def _inline_cql(body: dict[str, Any]) -> str | None:
    """The CQL a Library embeds, base64-decoded, or None when it embeds none.

    Only `content[].data` is read. A `content[].url` names a document somewhere else, and following
    it would be this server making requests on a caller's behalf - which is the door this module's
    docstring says stays shut.
    """
    contents = body.get("content")
    for content in contents if isinstance(contents, list) else []:
        if not isinstance(content, dict) or CQL_CONTENT_TYPE not in str(content.get("contentType", "")):
            continue
        data = content.get("data")
        if not isinstance(data, str):
            continue
        try:
            return base64.b64decode(data, validate=True).decode("utf-8")
        except (binascii.Error, UnicodeDecodeError, ValueError):
            continue
    return None


def _prefetched_bundle(invocation: CdsHookRequest) -> dict[str, Any]:
    """Everything the EHR prefetched, as the one collection Bundle a CQL retrieve reads through.

    A prefetch value is either one resource or a Bundle of them, and both are flattened into the same
    collection: a library asking for `[Condition]` should not have to know which prefetch key the EHR
    put the conditions under.
    """
    entries: list[dict[str, Any]] = []
    for prefetched in invocation.prefetch.values():
        if not isinstance(prefetched, dict):
            continue
        if prefetched.get("resourceType") == "Bundle":
            for entry in prefetched.get("entry") or []:
                resource = entry.get("resource") if isinstance(entry, dict) else None
                if isinstance(resource, dict):
                    entries.append({"resource": resource})
            continue
        if isinstance(prefetched.get("resourceType"), str):
            entries.append({"resource": prefetched})
    return {"resourceType": "Bundle", "type": "collection", "entry": entries}


def _cards(outcome: EvaluationOutcome, source: CdsCardSource) -> tuple[CdsCard, ...]:
    """The cards one evaluation produced: one per define that said something, plus any parse failure."""
    cards = [
        CdsCard(
            summary=f"The CQL library did not parse{_at(diagnostic.line, diagnostic.column)}",
            indicator=WARNING_INDICATOR,
            source=source,
            detail=diagnostic.message,
        )
        for diagnostic in outcome.diagnostics
        if diagnostic.kind is DiagnosticKind.PARSE
    ]
    cards.extend(
        CdsCard(summary=summary, indicator=INFORMATION_INDICATOR, source=source)
        for result in outcome.results
        for summary in [_summary(result.name, result.values)]
        if summary is not None
    )
    return tuple(cards)


def _summary(name: str, values: tuple[Any, ...]) -> str | None:
    """The sentence one define is worth showing, or None when it is worth showing nothing.

    True is worth the define's own name, because a define named `Overdue for a visit` answering true
    is already the sentence. A non-empty string is worth itself, because a library that wrote out a
    message meant that message to be read. Everything else is worth nothing.
    """
    if len(values) != 1:
        return None
    value = values[0]
    if value is True:
        return name
    if isinstance(value, str) and value.strip() != "":
        return value
    return None


def _at(line: int | None, column: int | None) -> str:
    """Where the parser stopped, said the way a person reads it, or nothing when it stated no position."""
    if line is None:
        return ""
    if column is None:
        return f" at line {line}"
    return f" at line {line}, column {column}"
