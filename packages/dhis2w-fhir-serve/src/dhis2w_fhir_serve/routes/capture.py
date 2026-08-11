"""`POST /QuestionnaireResponse`: the one write the facade accepts.

The interaction is FHIR's `create`, and it answers the way R4 says a create answers - 201, a
`Location` header naming where the created resource is served from, and an OperationOutcome
saying what happened. What is created is a receipt: the submission as it arrived, stamped with
the id it is now served under, plus every warning the server had to record about it.

The body is read as raw bytes rather than through a FastAPI request model. A capture is validated
against the served IG - its questionnaires, its terminology, its profiles - which is a contract a
FastAPI parameter model cannot express, and reading the bytes here is also what keeps the stored
copy byte-faithful to what the client sent.

Nothing here talks to DHIS2. Accepting a capture means the submission was understood and kept,
not that it has been written to an instance.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from dhis2w_fhir_serve.capability import QUESTIONNAIRE_RESPONSE_RESOURCE_TYPE
from dhis2w_fhir_serve.capture.index import CaptureIndexCache
from dhis2w_fhir_serve.capture.naming import CaptureNaming
from dhis2w_fhir_serve.capture.outcome import CaptureIssue, CaptureRejection, rejection_outcome, success_outcome
from dhis2w_fhir_serve.capture.validate import ValidatedCapture, validate_response
from dhis2w_fhir_serve.errors import FHIR_JSON_MEDIA_TYPE, UnsupportedMediaTypeError
from dhis2w_fhir_serve.routes.context import serve_context
from dhis2w_fhir_serve.spool import StoredResponseEnvelope, current_instant, new_response_id

#: Where the capture state is held on the app. It is deliberately not part of `ServeContext`: the
#: context is everything the lifespan loaded, and this is built by the first capture request and
#: filled in as questionnaires are met, so a facade that is only ever read from never builds it.
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


class CaptureState(BaseModel):
    """What a capture request needs beyond the serve context: the project's names, and its index cache."""

    model_config = ConfigDict(frozen=True)

    naming: CaptureNaming
    indexes: CaptureIndexCache = Field(default_factory=CaptureIndexCache)


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
        )
    except CaptureRejection as rejection:
        return JSONResponse(
            status_code=rejection.http_status,
            content=rejection_outcome(rejection.issues).model_dump(mode="json", exclude_none=True, by_alias=True),
            media_type=FHIR_JSON_MEDIA_TYPE,
        )
    envelope = _receipt(validated)
    context.spool.save(envelope)
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
    """The capture state of this app, built from the served project the first time a capture arrives."""
    held: CaptureState | None = getattr(request.app.state, CAPTURE_STATE_ATTRIBUTE, None)
    if held is not None:
        return held
    state = CaptureState(naming=CaptureNaming.from_project(serve_context(request).project))
    setattr(request.app.state, CAPTURE_STATE_ATTRIBUTE, state)
    return state


def _receipt(validated: ValidatedCapture) -> StoredResponseEnvelope:
    """Mint the receipt for one accepted submission, stamping the id it is served under onto the stored copy."""
    response_id = new_response_id()
    stored: dict[str, Any] = {**validated.response, "id": response_id}
    return StoredResponseEnvelope(
        response_id=response_id,
        received_at=current_instant(),
        form_kind=validated.form_kind,
        questionnaire=validated.canonical,
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
