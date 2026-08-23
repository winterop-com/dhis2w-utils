"""The facade's error vocabulary: what a route raises, and the OperationOutcome each one answers with.

FHIR gives one error body for every failed interaction, so every handler here ends in the same
place - an OperationOutcome served as `application/fhir+json`. The routes raise a `ServeError`
naming what went wrong in FHIR's own terms; the handlers turn that into the status and issue
code R4 pairs with it.

An unexpected exception is the one case the client learns nothing about: the outcome says the
server failed, and the traceback goes to the log, because a stack trace on the wire tells a
capture client nothing it can act on and tells an attacker plenty.
"""

from __future__ import annotations

import logging
from typing import Literal

from dhis2w_fhir.r4 import OperationOutcome, OperationOutcomeIssue
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from dhis2w_fhir_serve.log import LOGGER_NAME

#: The media type every FHIR interaction answers with, success or failure.
FHIR_JSON_MEDIA_TYPE = "application/fhir+json"

IssueSeverity = Literal["fatal", "error", "warning", "information"]
"""The `OperationOutcome.issue.severity` values the facade uses."""

IssueCode = Literal["invalid", "not-found", "not-supported", "exception", "processing", "login", "forbidden"]
"""The `OperationOutcome.issue.code` values the facade uses.

`login` is R4's own code for "the user or system was not able to be authenticated", which is what a
401 off `dhis2w_fhir_serve.auth` means. It is a child of `security` in the issue-type hierarchy, and
the child says the actual thing. `forbidden` is its sibling - "the user does not have the rights to
perform this action" - and the facade uses it for one answer only: a 403 the DHIS2 instance gave a
caller on a pass-through read, carried through as `dhis2w_fhir_serve.passthrough` describes.
"""

logger = logging.getLogger(LOGGER_NAME)


class ServeError(Exception):
    """A failed interaction the facade can describe in FHIR's terms."""

    status_code: int = 500
    issue_code: IssueCode = "exception"

    def __init__(self, diagnostics: str) -> None:
        super().__init__(diagnostics)
        self.diagnostics = diagnostics

    def response_headers(self) -> dict[str, str]:
        """The headers this refusal has to carry beyond the body, which for almost every one is none.

        A `dict[str, str]` because HTTP headers are the boundary, and the one refusal that overrides
        this is `dhis2w_fhir_serve.auth.UnauthenticatedError`: RFC 9110 requires a 401 to name the
        challenge a client should meet.
        """
        return {}


class NotFoundError(ServeError):
    """The resource type is served, but nothing is stored under that id."""

    status_code = 404
    issue_code = "not-found"

    def __init__(self, resource_type: str, resource_id: str) -> None:
        super().__init__(f"no {resource_type} with id `{resource_id}` is served here")
        self.resource_type = resource_type
        self.resource_id = resource_id


class NotServedError(ServeError):
    """The facade serves a fixed set of resource types, and this is not one of them."""

    status_code = 404
    issue_code = "not-supported"

    def __init__(self, resource_type: str) -> None:
        super().__init__(f"this server does not serve the resource type `{resource_type}`")
        self.resource_type = resource_type


class NotServedFromCompiledIgError(ServeError):
    """The resource type is answered from the DHIS2 instance, and this process serves a compiled guide instead.

    Same status and issue code as `NotServedError`, because that is what it is from the client's
    side - this server does not support that interaction - with the reason stated so the operator
    reads it as a way the process was started rather than as a missing feature.
    """

    status_code = 404
    issue_code = "not-supported"

    def __init__(self, resource_type: str) -> None:
        super().__init__(
            f"`{resource_type}` is answered from the DHIS2 instance this facade runs against, and this "
            "process serves a compiled implementation guide; start it with `--live` to search the register."
        )
        self.resource_type = resource_type


class RegisterDisabledError(ServeError):
    """The project serves no tracked entity at all: `[serve.tracked_entities] enabled` is false.

    Same status and issue code as `NotServedFromCompiledIgError`, and for the same reason - from
    the client's side this server does not support the interaction - with the config key named so
    the operator reads it as a decision this project wrote down rather than as a missing feature.
    """

    status_code = 404
    issue_code = "not-supported"

    def __init__(self, resource_type: str) -> None:
        super().__init__(
            f"`{resource_type}` is not served here: this project sets `[serve.tracked_entities] enabled` to "
            "false; set it true in fhir.toml and serve again to search or list the register"
        )
        self.resource_type = resource_type


class RegisterListingDisabledError(ServeError):
    """The register may be searched here but not listed: `[serve.tracked_entities] listing` is false."""

    status_code = 404
    issue_code = "not-supported"

    def __init__(self, resource_type: str) -> None:
        super().__init__(
            f"this facade serves no `{resource_type}` listing; name an `identifier` to search for one, "
            "or set `[serve.tracked_entities] listing = true` in fhir.toml and serve again"
        )
        self.resource_type = resource_type


class RecordDisabledError(ServeError):
    """This project publishes who its subjects are and not what was recorded about them.

    `[serve.tracked_entities] events` is false, so the register answers and the record does not. Same
    status and issue code as every other "this server does not serve that here", with the key named so
    an operator reads it as a decision this project wrote down rather than as a missing feature.
    """

    status_code = 404
    issue_code = "not-supported"

    def __init__(self, resource_type: str) -> None:
        super().__init__(
            f"this facade serves no `{resource_type}`: this project publishes who its tracked entities "
            "are and not what was recorded about them; set `[serve.tracked_entities] events = true` in "
            "fhir.toml and serve again"
        )
        self.resource_type = resource_type


class ProjectionNotConfiguredError(ServeError):
    """A search was told to read the materialized projection and this process holds none.

    Loud rather than silent, and for the reason `PassThroughUnavailableError` is loud: the silent
    alternative is answering the lookup from the DHIS2 instance instead, which would be a different
    search than the one `fhir.toml` states, with a different cost, and no cursor to read it by.
    `fhir.toml` refuses the pair before the socket opens, so this is what a runtime assembled by hand
    meets rather than what an operator meets.
    """

    def __init__(self) -> None:
        """Carry the refusal naming both keys, since the fix is the two of them agreeing."""
        super().__init__(
            "this server answers a register search from the materialized projection - `[serve.search] "
            'backend = "projection"` - and holds none to read: state `[serve.projection] store = '
            '"sqlite"` and fill it with `d2w fhir sync`'
        )


class ProjectionEmptyError(ServeError):
    """The projection is configured and nothing has ever been synced into it.

    404 and `not-supported`, the same pair every other "this server does not answer that here"
    carries, because from the client's side that is what it is. The distinction that matters is in
    the diagnostic: an empty projection is not a register with nobody in it, and answering an empty
    searchset would tell a client the instance holds no people when nobody has looked yet.
    """

    status_code = 404
    issue_code = "not-supported"

    def __init__(self, resource_type: str) -> None:
        """Carry the refusal naming the resource, the projection, and the command that fills it."""
        super().__init__(
            f"`{resource_type}` is answered from this project's materialized projection, and nothing has "
            "been synced into it yet - so this server has read nothing about the register rather than "
            "read that it is empty. Run `d2w fhir sync` and ask again."
        )
        self.resource_type = resource_type


class NoPublishedSubjectTypeError(ServeError):
    """The facade runs live, but the guide publishes no registration form, so it knows of no type to search."""

    status_code = 404
    issue_code = "not-supported"

    def __init__(self, resource_type: str) -> None:
        super().__init__(
            f"this project publishes no registration form, so no tracked entity type is served here and "
            f"`{resource_type}` cannot be searched; generate a tracker program's registration form first."
        )
        self.resource_type = resource_type


class UpstreamError(ServeError):
    """The DHIS2 instance behind this facade refused or failed the read a request depends on."""

    status_code = 502
    issue_code = "exception"

    def __init__(self, diagnostics: str) -> None:
        super().__init__(diagnostics)


class BadSearchError(ServeError):
    """The search parameters cannot be read as a query."""

    status_code = 400
    issue_code = "invalid"

    def __init__(self, diagnostics: str) -> None:
        super().__init__(diagnostics)


class UnsupportedSearchParameterError(ServeError):
    """The search names a parameter this server does not answer that resource type on.

    Refusing is the whole point. A parameter the facade cannot apply, ignored, is answered with
    everything the endpoint holds - and a client that asked for the people called Smith reads that
    result set as the people called Smith. A 400 naming the parameter that is answered is the one
    reply that cannot be misread.
    """

    status_code = 400
    issue_code = "invalid"

    def __init__(self, resource_type: str, parameter: str, supported_parameters: tuple[str, ...]) -> None:
        """Carry the refusal naming what was asked for and what this server answers instead."""
        named = ", ".join(f"`{supported}`" for supported in supported_parameters)
        answers = f"{named} is the one it supports" if len(supported_parameters) == 1 else f"it answers {named}"
        super().__init__(f"`{parameter}` is not a search parameter this server answers `{resource_type}` on: {answers}")
        self.resource_type = resource_type
        self.parameter = parameter
        self.supported_parameters = supported_parameters


class BadOperationError(ServeError):
    """The parameters an operation was invoked with cannot be read as what the operation declares."""

    status_code = 400
    issue_code = "invalid"

    def __init__(self, diagnostics: str) -> None:
        super().__init__(diagnostics)


class NotAnEndpointError(ServeError):
    """Nothing is served at that path, whatever method it was asked for."""

    status_code = 404
    issue_code = "not-found"

    def __init__(self, path: str) -> None:
        super().__init__(f"`{path}` is not an endpoint this server serves")
        self.path = path


class CaptureDisabledError(ServeError):
    """This server publishes its guide and receives nothing: `[serve] capture` is false.

    405 rather than 404, because the path is served - a client may read and search the receipts this
    project already holds at the very address it may not post to - and the create interaction is the
    one thing gone. The config key is named for the reason `RegisterDisabledError` names its own: an
    operator reading it should see a decision this project wrote down, not a missing feature.
    """

    status_code = 405
    issue_code = "not-supported"

    def __init__(self, resource_type: str) -> None:
        super().__init__(
            f"this server receives no {resource_type}: this project sets `[serve] capture` to false, so it "
            "serves its guide and stores nothing new; set it true in fhir.toml and serve again to capture"
        )
        self.resource_type = resource_type


class MethodNotAllowedError(ServeError):
    """The path is served, but not for that HTTP method."""

    status_code = 405
    issue_code = "not-supported"

    def __init__(self, method: str, path: str) -> None:
        super().__init__(f"`{method}` is not supported on `{path}`")
        self.method = method
        self.path = path


class BatchNotSupportedError(ServeError):
    """The service base was posted to, which in FHIR is a batch or a transaction this facade does not run.

    `POST [base]` is the one interaction the root path has, so the refusal names it rather than
    stating a bare method mismatch: a client sending a Bundle there is asking for batch processing,
    and this facade takes one QuestionnaireResponse per request instead.
    """

    status_code = 405
    issue_code = "not-supported"

    def __init__(self, method: str) -> None:
        super().__init__(
            f"`{method} /` is not served here: this server runs no batch and no transaction. Post one "
            "QuestionnaireResponse per request to `/QuestionnaireResponse`."
        )
        self.method = method


class NotAcceptableError(ServeError):
    """The request accepts no format this server answers in."""

    status_code = 406
    issue_code = "not-supported"

    def __init__(self, accept: str) -> None:
        super().__init__(
            f"`{accept}` accepts no JSON, and this server answers `{FHIR_JSON_MEDIA_TYPE}` only; "
            "ask for that, for `application/json`, or for `*/*`"
        )
        self.accept = accept


class UnsupportedMediaTypeError(ServeError):
    """The request body is declared in a media type this server does not read."""

    status_code = 415
    issue_code = "not-supported"

    def __init__(self, media_type: str) -> None:
        super().__init__(
            f"`{media_type}` is not a media type this server reads; send the body as `{FHIR_JSON_MEDIA_TYPE}`"
        )
        self.media_type = media_type


def outcome(
    status_code: int,
    severity: IssueSeverity,
    code: IssueCode,
    diagnostics: str,
    expression: tuple[str, ...] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    """Build the OperationOutcome response one failed interaction answers with."""
    body = OperationOutcome(
        issue=[
            OperationOutcomeIssue(
                severity=severity,
                code=code,
                diagnostics=diagnostics,
                expression=list(expression) if expression else None,
            )
        ]
    )
    return JSONResponse(
        status_code=status_code,
        content=body.model_dump(mode="json", exclude_none=True, by_alias=True),
        media_type=FHIR_JSON_MEDIA_TYPE,
        headers=headers,
    )


def register_error_handlers(app: FastAPI) -> None:
    """Answer every failure - raised, routed, or unexpected - with an OperationOutcome."""
    app.add_exception_handler(ServeError, _handle_serve_error)
    app.add_exception_handler(RequestValidationError, _handle_validation_error)
    app.add_exception_handler(StarletteHTTPException, _handle_http_exception)
    app.add_exception_handler(Exception, _handle_unexpected_error)


async def _handle_serve_error(request: Request, exception: Exception) -> Response:
    """Answer a raised `ServeError` with the status and issue code it names."""
    error = exception if isinstance(exception, ServeError) else ServeError(str(exception))
    return outcome(
        error.status_code, "error", error.issue_code, error.diagnostics, headers=error.response_headers() or None
    )


async def _handle_validation_error(request: Request, exception: Exception) -> Response:
    """Answer a request FastAPI could not read as invalid, naming the elements it stumbled on."""
    expression: tuple[str, ...] = ()
    if isinstance(exception, RequestValidationError):
        expression = tuple(".".join(str(part) for part in error["loc"]) for error in exception.errors())
    return outcome(400, "error", "invalid", "the request could not be read", expression or None)


async def _handle_http_exception(request: Request, exception: Exception) -> Response:
    """Answer Starlette's own routing failures - an unrouted path, a method the path does not take."""
    status_code = exception.status_code if isinstance(exception, StarletteHTTPException) else 500
    if status_code == 405:
        error = MethodNotAllowedError(request.method, request.url.path)
        return outcome(error.status_code, "error", error.issue_code, error.diagnostics)
    if status_code == 404:
        missing = NotAnEndpointError(request.url.path)
        return outcome(missing.status_code, "error", missing.issue_code, missing.diagnostics)
    detail = exception.detail if isinstance(exception, StarletteHTTPException) else "request failed"
    return outcome(status_code, "error", "processing", str(detail))


async def _handle_unexpected_error(request: Request, exception: Exception) -> Response:
    """Answer an unexpected failure with a bare outcome, and keep the traceback in the log."""
    logger.exception("%s %s failed unexpectedly", request.method, request.url.path)
    return outcome(500, "fatal", "exception", "the server failed to process this request")
