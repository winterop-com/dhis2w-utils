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

IssueCode = Literal["invalid", "not-found", "not-supported", "exception", "processing"]
"""The `OperationOutcome.issue.code` values the facade uses."""

logger = logging.getLogger(LOGGER_NAME)


class ServeError(Exception):
    """A failed interaction the facade can describe in FHIR's terms."""

    status_code: int = 500
    issue_code: IssueCode = "exception"

    def __init__(self, diagnostics: str) -> None:
        super().__init__(diagnostics)
        self.diagnostics = diagnostics


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


class BadSearchError(ServeError):
    """The search parameters cannot be read as a query."""

    status_code = 400
    issue_code = "invalid"

    def __init__(self, diagnostics: str) -> None:
        super().__init__(diagnostics)


class MethodNotAllowedError(ServeError):
    """The path is served, but not for that HTTP method."""

    status_code = 405
    issue_code = "not-supported"

    def __init__(self, method: str, path: str) -> None:
        super().__init__(f"`{method}` is not supported on `{path}`")
        self.method = method
        self.path = path


def outcome(
    status_code: int,
    severity: IssueSeverity,
    code: IssueCode,
    diagnostics: str,
    expression: tuple[str, ...] | None = None,
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
    return outcome(error.status_code, "error", error.issue_code, error.diagnostics)


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
        return outcome(404, "error", "not-found", f"`{request.url.path}` is not an endpoint this server serves")
    detail = exception.detail if isinstance(exception, StarletteHTTPException) else "request failed"
    return outcome(status_code, "error", "processing", str(detail))


async def _handle_unexpected_error(request: Request, exception: Exception) -> Response:
    """Answer an unexpected failure with a bare outcome, and keep the traceback in the log."""
    logger.exception("%s %s failed unexpectedly", request.method, request.url.path)
    return outcome(500, "fatal", "exception", "the server failed to process this request")
