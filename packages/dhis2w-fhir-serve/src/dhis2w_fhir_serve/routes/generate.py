"""`GET|POST /Questionnaire/{id}/$generate` - the instance-level operation that fills a served form.

The operation answers one served Questionnaire with a synthetic QuestionnaireResponse: every question
answered with a value its own type, bounds, and terminology binding admit, wrapped in the context its
form kind's response profile requires. What makes it worth serving is that the answer is immediately
postable - `$generate` output sent to this server's own `POST /QuestionnaireResponse` answers 201,
which is the round trip a capture UI's fill-with-test-data button and an API-driven stress corpus both
stand on. `tests/test_generate_endpoint.py` holds that invariant per form kind.

The spool is read as part of answering: a generated stage response answers against the tracked entity
and the enrollment a spooled registration of the same program minted, so the operation's output is a
function of the project's receipts as well as its forms - see `dhis2w_fhir_serve.synthesize`.

This is a **custom** operation, deliberately not SDC's `$populate`. `$populate` means fill this form
from real context about a real subject; `$generate` invents its data, and a client that knows what
`$populate` means would be misled by seeing it here. The IG publishes the OperationDefinition, and
`/metadata` declares it on the Questionnaire resource entry beside the read interactions.

The path is fixed, so this router mounts ahead of the read catch-alls: `/{resource_type}/{resource_id}`
matches `/Questionnaire/BfMAe6Itzgt/$generate` just as happily and would answer it as a read.
"""

from __future__ import annotations

import datetime
import json
from typing import Any

from dhis2w_fhir.foundation import GENERATE_SEED_PARAMETER
from dhis2w_fhir.r4 import Parameters, Questionnaire
from fastapi import APIRouter
from pydantic import ValidationError
from starlette.datastructures import QueryParams
from starlette.requests import Request
from starlette.responses import Response

from dhis2w_fhir_serve.capture.index import QUESTIONNAIRE_RESOURCE_TYPE, UnreadableQuestionnaireError
from dhis2w_fhir_serve.errors import FHIR_JSON_MEDIA_TYPE, BadOperationError, NotFoundError, ServeError
from dhis2w_fhir_serve.routes.capture import capture_state
from dhis2w_fhir_serve.routes.context import serve_context
from dhis2w_fhir_serve.synthesize import MAXIMUM_SEED, draw_seed, generate_response

#: The path the operation is served at; `capability.py` declares it by the name R4 gives it.
GENERATE_PATH = f"/{QUESTIONNAIRE_RESOURCE_TYPE}/{{resource_id}}/$generate"

router = APIRouter()


class UngeneratableFormError(ServeError):
    """The Questionnaire is served, but it is not one this server can generate a response to."""

    status_code = 422
    issue_code = "not-supported"

    def __init__(self, resource_id: str, diagnostics: str) -> None:
        super().__init__(f"`Questionnaire/{resource_id}` cannot be generated against: {diagnostics}")
        self.resource_id = resource_id


@router.get(GENERATE_PATH)
async def generate_from_questionnaire(request: Request, resource_id: str) -> Response:
    """Answer one served form with a synthetic response, drawn from the seed the query names."""
    return _generated(request, resource_id, read_seed(request.query_params))


@router.post(GENERATE_PATH)
async def post_generate_from_questionnaire(request: Request, resource_id: str) -> Response:
    """The POST spelling of the same operation, taking its seed from a Parameters body or the query."""
    body_seed = read_body_seed(await request.body())
    return _generated(request, resource_id, body_seed if body_seed is not None else read_seed(request.query_params))


def read_seed(params: QueryParams) -> int | None:
    """Read the `seed` query parameter, refusing anything the operation's `integer` input cannot carry."""
    raw = params.get(GENERATE_SEED_PARAMETER)
    if raw is None or raw == "":
        return None
    return _checked_seed(raw)


def read_body_seed(raw_body: bytes) -> int | None:
    """Read `seed` off a POSTed Parameters body, which R4 allows a client to invoke an operation with.

    An empty body is how a client says "any seed", and is the shape a bare `POST .../$generate` sends.
    A body that is not a Parameters resource is refused rather than ignored: a client that meant to
    name a seed and misspelled the resource would otherwise be answered with a different response
    than it asked for, silently.
    """
    if not raw_body.strip():
        return None
    try:
        payload: Any = json.loads(raw_body)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise BadOperationError(f"the request body is not valid JSON ({error})") from error
    try:
        parameters = Parameters.model_validate(payload)
    except ValidationError as error:
        raise BadOperationError(f"the request body is not a Parameters resource ({error})") from error
    for parameter in parameters.parameter or []:
        if parameter.name != GENERATE_SEED_PARAMETER:
            continue
        if parameter.valueInteger is not None:
            return _checked_seed(str(parameter.valueInteger))
        if parameter.valueString is not None:
            return _checked_seed(parameter.valueString)
        raise BadOperationError(f"the `{GENERATE_SEED_PARAMETER}` parameter carries no `valueInteger`")
    return None


def _checked_seed(raw: str) -> int:
    """One seed as the operation declares it: a non-negative R4 integer."""
    try:
        seed = int(raw)
    except ValueError as error:
        raise BadOperationError(f"`{GENERATE_SEED_PARAMETER}` takes a whole number, not `{raw}`") from error
    if seed < 0 or seed > MAXIMUM_SEED:
        raise BadOperationError(f"`{GENERATE_SEED_PARAMETER}` takes a value between 0 and {MAXIMUM_SEED}")
    return seed


def _generated(request: Request, resource_id: str, seed: int | None) -> Response:
    """Resolve the named form, generate one response to it, and serialise it as the operation's output."""
    context = serve_context(request)
    state = capture_state(request)
    entry = context.store.by_type_and_id(QUESTIONNAIRE_RESOURCE_TYPE, resource_id)
    if entry is None or entry.canonical_url is None:
        raise NotFoundError(QUESTIONNAIRE_RESOURCE_TYPE, resource_id)
    try:
        index = state.indexes.resolve(entry.canonical_url, state.naming, context.store)
        questionnaire = Questionnaire.model_validate(entry.body)
    except (UnreadableQuestionnaireError, ValidationError) as error:
        raise UngeneratableFormError(resource_id, _diagnostics(error)) from error
    response = generate_response(
        questionnaire,
        index,
        state.naming,
        context.store,
        seed=seed if seed is not None else draw_seed(),
        today=datetime.date.today(),
        spool=context.spool,
    )
    return Response(
        content=response.model_dump_json(exclude_none=True, by_alias=True),
        media_type=FHIR_JSON_MEDIA_TYPE,
    )


def _diagnostics(error: UnreadableQuestionnaireError | ValidationError) -> str:
    """Say why a served Questionnaire could not be generated against, in the terms it failed on."""
    return error.diagnostics if isinstance(error, UnreadableQuestionnaireError) else str(error)
