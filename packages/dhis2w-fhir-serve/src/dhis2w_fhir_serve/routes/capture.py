"""`POST /QuestionnaireResponse`: the one write the facade accepts, and the refusal in its place.

A project that sets `[serve] capture = false` mounts `refusal_router` instead of `router`, and the
address answers 405 with an OperationOutcome naming the key. The refusal is a route rather than the
405 Starlette would produce on its own from the read router's GET: both are the same status and the
same shape, and only one of them says why. Nothing else about the resource type moves - the receipts
already spooled are read, searched, and counted at the same paths.

The interaction is FHIR's `create`, and it answers the way R4 says a create answers - 201, a
`Location` header naming where the created resource is served from, and an OperationOutcome
saying what happened. What is created is a receipt: the submission as it arrived, stamped with
the id it is now served under, plus every warning the server had to record about it.

The body is read as raw bytes rather than through a FastAPI request model. A capture is validated
against the served IG - its questionnaires, its terminology, its profiles - which is a contract a
FastAPI parameter model cannot express, and reading the bytes here is also what keeps the stored
copy byte-faithful to what the client sent.

Nothing here talks to DHIS2. Accepting a capture means the submission was understood and kept,
not that it has been written to an instance. Kept means durable: the receipt is fsynced and its
directory entry with it before the 201 goes out, so a 201 is a promise that survives power loss.

A CORRECTION OR A WITHDRAWAL IS REFUSED HERE where the project's dials are off. `[forward]
corrections` and `[forward] withdrawals` are read off `fhir.toml` onto the capture state, and a
submission carrying `status = "amended"` or `status = "entered-in-error"` against an off dial is
answered 422 with the key named. With the dial on it is stored like any other receipt, status and
all - see `dhis2w_fhir_serve.capture.validate`.

WHO SUBMITTED IT is stamped on the receipt where this run established anybody. Under
`[serve] auth = "dhis2"` the check has already read `/api/me` as the caller, so the username DHIS2
answered with is on the request and goes onto the envelope. Under every other posture there is no
person to name and the field stays absent - a static token is not a submitter, and a server that
authenticates nobody knows nobody.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from dhis2w_fhir_serve.auth import request_identity
from dhis2w_fhir_serve.capability import QUESTIONNAIRE_RESPONSE_RESOURCE_TYPE
from dhis2w_fhir_serve.capture.index import CaptureIndexCache
from dhis2w_fhir_serve.capture.naming import CaptureNaming
from dhis2w_fhir_serve.capture.outcome import CaptureIssue, CaptureRejection, rejection_outcome, success_outcome
from dhis2w_fhir_serve.capture.validate import CaptureLifecyclePostures, ValidatedCapture, validate_response
from dhis2w_fhir_serve.errors import FHIR_JSON_MEDIA_TYPE, CaptureDisabledError, UnsupportedMediaTypeError
from dhis2w_fhir_serve.routes.context import serve_context
from dhis2w_fhir_serve.spool import StoredResponseEnvelope, current_instant, new_response_id

#: Where the capture state is held on the app. It is deliberately not part of `ServeContext`: the
#: context is everything the lifespan loaded, and this is built by the first request that needs a
#: form read - a capture, or a record read projecting one entity's events through the same forms -
#: and filled in as questionnaires are met.
CAPTURE_STATE_ATTRIBUTE = "capture"

#: The JSON media types a capture body may be declared as. `application/fhir+json` is what FHIR
#: asks for, `application/json` is what every generic HTTP client sends by default, and any other
#: `+json` structured syntax still says the bytes are JSON. A body declared as anything else -
#: XML, a form post, plain text - is refused with 415 before the bytes are read, because the
#: declaration says the client is not sending what this endpoint parses. An absent Content-Type
#: declares nothing and the body is read as the JSON it has to be either way.
_JSON_MEDIA_TYPES = frozenset({FHIR_JSON_MEDIA_TYPE, "application/json"})
_JSON_MEDIA_TYPE_SUFFIX = "+json"

router = APIRouter()

#: What a viewer-posture run mounts in the create route's place - the same path, answering why.
refusal_router = APIRouter()


@refusal_router.post(f"/{QUESTIONNAIRE_RESPONSE_RESOURCE_TYPE}")
async def refuse_questionnaire_response(request: Request) -> Response:
    """Refuse a submission this project does not receive, naming the key that decided it."""
    raise CaptureDisabledError(QUESTIONNAIRE_RESPONSE_RESOURCE_TYPE)


class CaptureState(BaseModel):
    """What a capture request needs beyond the serve context: the project's names, dials, and index cache."""

    model_config = ConfigDict(frozen=True)

    naming: CaptureNaming
    indexes: CaptureIndexCache = Field(default_factory=CaptureIndexCache)
    postures: CaptureLifecyclePostures = CaptureLifecyclePostures()
    """Whether this project receives a submission that corrects, or one that retracts, a forwarded receipt.

    A project-level fact read off `fhir.toml` exactly as the naming above is, and held here for the
    same reason: it is settled once by the project and never by a request. `ServeSettings` carries
    what the *run* was invoked with; these two are what the project says, and `d2w fhir forward`
    reads the same keys out of the same file.
    """


@router.post(f"/{QUESTIONNAIRE_RESPONSE_RESOURCE_TYPE}")
async def create_questionnaire_response(request: Request) -> Response:
    """Receive one QuestionnaireResponse: validate it against the served IG, store it, and say where it lives."""
    _require_json_body(request)
    context = serve_context(request)
    state = capture_state(request)
    try:
        validated = validate_response(
            await request.body(),
            state.indexes,
            state.naming,
            context.store,
            context.settings.strict_codes,
            state.postures,
        )
    except CaptureRejection as rejection:
        return JSONResponse(
            status_code=rejection.http_status,
            content=rejection_outcome(rejection.issues).model_dump(mode="json", exclude_none=True, by_alias=True),
            media_type=FHIR_JSON_MEDIA_TYPE,
        )
    envelope = _receipt(validated, request)
    # Off the event loop: the write is a temporary file, an fsync of it, a rename, and an fsync of
    # the directory - blocking work the facade must not do inline, since the point of the fsyncs is
    # that they wait for the device.
    await run_in_threadpool(context.spool.save, envelope)
    return _created(request, envelope.response_id, validated.warnings)


def _require_json_body(request: Request) -> None:
    """Refuse a body declared in a media type this endpoint does not parse, with 415 and an OperationOutcome."""
    declared = request.headers.get("content-type")
    if declared is None or not declared.strip():
        return
    media_type = declared.split(";", 1)[0].strip().lower()
    if media_type in _JSON_MEDIA_TYPES or media_type.endswith(_JSON_MEDIA_TYPE_SUFFIX):
        return
    raise UnsupportedMediaTypeError(media_type)


def capture_state(request: Request) -> CaptureState:
    """The capture state of this app, built from the served project the first time a form is read.

    Shared with the record surface, which projects one entity's events through the same naming and
    the same index cache a submission is validated against - one form typed one way, whichever
    direction a value is travelling. `dhis2w_fhir_serve.routes.history` is the other caller.
    """
    held: CaptureState | None = getattr(request.app.state, CAPTURE_STATE_ATTRIBUTE, None)
    if held is not None:
        return held
    project = serve_context(request).project
    state = CaptureState(
        naming=CaptureNaming.from_project(project),
        postures=CaptureLifecyclePostures.from_project(project),
    )
    setattr(request.app.state, CAPTURE_STATE_ATTRIBUTE, state)
    return state


def _receipt(validated: ValidatedCapture, request: Request) -> StoredResponseEnvelope:
    """Mint the receipt for one accepted submission, stamping the id it is served under onto the stored copy."""
    response_id = new_response_id()
    stored: dict[str, Any] = {**validated.response, "id": response_id}
    identity = request_identity(request)
    return StoredResponseEnvelope(
        response_id=response_id,
        received_at=current_instant(),
        form_kind=validated.form_kind,
        questionnaire=validated.canonical,
        submitted_by=None if identity is None else identity.username,
        warnings=tuple(warning.diagnostics or "" for warning in validated.warnings),
        response=stored,
    )


def _created(request: Request, response_id: str, warnings: tuple[CaptureIssue, ...]) -> Response:
    """Answer an accepted capture: 201, where the receipt is served from, and what the server had to note."""
    base_url = str(request.base_url).rstrip("/")
    return JSONResponse(
        status_code=201,
        content=success_outcome(response_id, warnings).model_dump(mode="json", exclude_none=True, by_alias=True),
        media_type=FHIR_JSON_MEDIA_TYPE,
        headers={"Location": f"{base_url}/{QUESTIONNAIRE_RESPONSE_RESOURCE_TYPE}/{response_id}"},
    )
