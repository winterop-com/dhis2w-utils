"""`POST /facade/evaluate` - run one FHIRPath expression, CQL library, or ELM library against this facade's data.

WHY THIS SHAPE IS NOT FHIR'S. This endpoint answers a diagnostic, not a document: the line and the
column a parser stopped on, one row per define whether it answered or refused, and the difference
between a define that matched nothing and a define that was never run. FHIR has no empty collection
and `Parameters` has no line number, so this answer is plain `application/json` and Pydantic models -
`/spool`'s shape for `/spool`'s reasons, served under the facade API's own mount rather than at the
FHIR base. `dhis2w_fhir_serve.routes.spool` argues that choice in full, and the capture UI's Evaluate
screen is the reader this shape is for.

`POST /$evaluate` at the FHIR base is the wire-true sibling and answers the same evaluation as a
`Parameters` resource, for a client that speaks operations rather than this project's JSON. It is the
root's only evaluation spelling, because the root is FHIR's.
`dhis2w_fhir_serve.routes.evaluate_operation` is that operation, and it resolves its context through
`evaluation_subject` below - so the two addresses reach exactly the same three resources.

WHAT AN EXPRESSION MAY REACH, STATED ONCE. Exactly the resource the request named as its context,
and nothing else. Three kinds of context are offered and each is a different way of naming one
resource: `stored` reads it out of the served guide by type and id, `inline` is the JSON the caller
posted, and `registered` reads one tracked entity out of the DHIS2 instance a live facade holds open
and projects it the way `GET /Patient/{uid}` does. There is no fourth kind that searches, no file
path, and no library directory - `dhis2w_fhir_serve.evaluation` states what keeps that true of the
engine calls themselves.

THE REGISTERED CONTEXT IS LIVE-ONLY, and refuses the way every other register route refuses: the
config first (`[serve.tracked_entities] enabled`), then the missing instance, then a guide that
publishes no registration form, then a resource type the register does not serve. That order is
`dhis2w_fhir_serve.routes.register`'s and the reasons are its. It is read the way the register is
read, too: under `[serve] auth = "dhis2"` the entity comes back under the CALLER'S own DHIS2
authorization, so an expression can only ever run over a person its caller may see.

A BAD EXPRESSION IS 200. An expression that will not parse, a library whose define refuses, a define
name the library does not declare - each answers 200 with the diagnostic saying so, because the
request was perfectly well formed and the server did exactly what it was asked. This is `$translate`'s
posture: a concept the maps say nothing about is an answer with a message, not an error. What does
answer an OperationOutcome is a request this facade cannot serve at all - a stored resource it does
not hold, a register it does not publish.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Any, Literal

from dhis2w_client.errors import Dhis2ClientError
from dhis2w_fhir.r4.schemas import DEFAULT_SUBJECT_RESOURCE_TYPE
from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request

from dhis2w_fhir_serve.errors import (
    NoPublishedSubjectTypeError,
    NotFoundError,
    NotServedError,
    NotServedFromCompiledIgError,
    RegisterDisabledError,
    UpstreamError,
)
from dhis2w_fhir_serve.evaluation import EvaluationLanguage, EvaluationOutcome, evaluate_source
from dhis2w_fhir_serve.passthrough import register_reader
from dhis2w_fhir_serve.register.projection import registered_entity_for
from dhis2w_fhir_serve.register.wire import fetch_tracked_entity, upstream_refusal_text
from dhis2w_fhir_serve.routes.context import serve_context

if TYPE_CHECKING:
    from dhis2w_fhir_serve.passthrough import RegisterReader
    from dhis2w_fhir_serve.register.surface import RegisterSurface

#: Where an evaluation is asked for, under the facade API's mount.
EVALUATE_PATH = "/evaluate"

#: What this operation is grouped under in the facade API's document.
EVALUATE_TAG = "Evaluation"

router = APIRouter()


class StoredResourceContext(BaseModel):
    """One resource of the served guide, named the way a read names it: by type and id."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["stored"] = "stored"
    resource_type: str
    resource_id: str


class InlineResourceContext(BaseModel):
    """One resource the caller posted, evaluated as it arrived."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["inline"] = "inline"
    resource: dict[str, Any]
    """The resource verbatim - the same HTTP-boundary escape hatch `StoreEntry.body` documents.

    An expression may be written against any FHIR resource type, including ones this repo has no
    model for, and the engine evaluates over FHIR-shaped JSON rather than over models. Parsing it
    into a model here would mean parsing it back out again one function later.
    """


class RegisteredEntityContext(BaseModel):
    """One tracked entity the DHIS2 instance holds, as the register serves it.

    The resource type is the one the published map takes the entity's type onto - `Patient` for a
    project that tracks people, whatever the map states for the rest - so it is named rather than
    assumed, exactly as the register's own read path names it.
    """

    model_config = ConfigDict(frozen=True)

    kind: Literal["registered"] = "registered"
    resource_type: str = DEFAULT_SUBJECT_RESOURCE_TYPE
    tracked_entity_uid: str


EvaluationContext = Annotated[
    StoredResourceContext | InlineResourceContext | RegisteredEntityContext, Field(discriminator="kind")
]
"""The three ways a request names the one resource an expression runs over."""


class EvaluationRequest(BaseModel):
    """One evaluation as a caller asks for it: a language, a source, a context, and optionally one define."""

    model_config = ConfigDict(frozen=True)

    language: EvaluationLanguage
    source: str
    """The FHIRPath expression, the CQL library text, or the ELM library as JSON."""

    expression_name: str | None = None
    """Which define to answer. Omitted, a CQL or ELM library answers every define it declares."""

    context: EvaluationContext | None = None
    """The resource to evaluate over. Omitted, the expression runs over no resource at all."""


@router.post(
    EVALUATE_PATH,
    tags=[EVALUATE_TAG],
    summary="Evaluate an expression or a library",
    description=(
        "Runs one FHIRPath expression, CQL library, or compiled ELM library over one resource and "
        "answers what it produced, one row per define, together with everything that went wrong and "
        "where.\n\n"
        "An expression reaches exactly the resource the request named as its context and nothing "
        "else. There are three ways to name one and no fourth: `stored` reads it out of the served "
        "guide by type and id, `inline` is the JSON the request carries, and `registered` reads one "
        "tracked entity out of the DHIS2 instance a live run holds open. Naming no context runs the "
        "expression over no resource at all.\n\n"
        "A source that will not parse is a 200 carrying the diagnostic, not a refusal: the request "
        "was well formed and this server did exactly what it was asked. What answers an "
        "OperationOutcome is a request this facade cannot serve at all - a stored resource it does "
        "not hold, a register it does not publish.\n\n"
        "`POST /$evaluate` at the FHIR base answers the same evaluation as a `Parameters` resource."
    ),
    response_description="What each expression or define answered, and every diagnostic the run produced.",
)
async def evaluate_expression(request: Request, asked: EvaluationRequest) -> EvaluationOutcome:
    """Evaluate one source over one resource, answering its results and everything that went wrong.

    The evaluation runs off the event loop. Parsing a grammar and walking an expression tree is
    blocking, CPU-bound work, and a facade doing it inline would stall every other request it is
    serving - including the capture that is trying to post a receipt.
    """
    subject = await evaluation_subject(request, asked.context)
    return await run_in_threadpool(evaluate_source, asked.language, asked.source, subject, asked.expression_name)


async def evaluation_subject(request: Request, context: EvaluationContext | None) -> dict[str, Any] | None:
    """The one resource an expression may reach, resolved from whichever way the request named it.

    Public because `POST /$evaluate` resolves its context through this very function: the two
    endpoints answer in two shapes and reach exactly the same three resources, and a second
    resolution path would be a second answer to "what may an expression read".
    """
    if context is None:
        return None
    if isinstance(context, InlineResourceContext):
        return context.resource
    if isinstance(context, StoredResourceContext):
        entry = serve_context(request).store.by_type_and_id(context.resource_type, context.resource_id)
        if entry is None:
            raise NotFoundError(context.resource_type, context.resource_id)
        return entry.body
    return await _registered(request, context)


async def _registered(request: Request, context: RegisteredEntityContext) -> dict[str, Any]:
    """One tracked entity read from the instance and projected the way the register serves it.

    The projection is dumped back to JSON because that is the engine's argument type: it evaluates
    over FHIR documents, so a model handed in would be one this function parsed and the evaluator
    immediately re-read.
    """
    reader, surface = await _live_register(request, context.resource_type)
    try:
        entity = await fetch_tracked_entity(reader, context.tracked_entity_uid)
    except Dhis2ClientError as error:
        raise UpstreamError(
            f"the DHIS2 instance did not answer the tracked entity read: {upstream_refusal_text(error)}"
        ) from error
    if entity is None:
        raise NotFoundError(context.resource_type, context.tracked_entity_uid)
    registered = registered_entity_for(entity, surface.index, context.resource_type)
    return registered.model_dump(mode="json", exclude_none=True, by_alias=True)


async def _live_register(request: Request, resource_type: str) -> tuple[RegisterReader, RegisterSurface]:
    """The reader and the surface a register context is read through, refusing in the register's own order."""
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
