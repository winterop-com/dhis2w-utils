"""The service base, `/`: what FHIR puts there, and why this facade puts nothing.

`POST [base]` is FHIR's batch and transaction endpoint - a Bundle of interactions run in one
request. This facade runs neither, and a client that posts one is asking a real FHIR question that
deserves a real FHIR answer: 405 with an OperationOutcome naming what the server does instead,
rather than the 404 an unrouted path would give, which reads as "wrong address" when the address
was right and the interaction was not.

`PUT`, `PATCH`, and `DELETE` land in the same refusal. FHIR defines none of them at the base, so
each is the same fact stated about a different verb, and one sentence covers all four.

THE READ IS LEFT ALONE, and that is why this router is built rather than declared. With `--ui` the
capture UI's shell is mounted at `/` and serves the browser that opens the facade; without it the
base has no read at all and answers 404, the same as any other unserved path. Starlette answers a
path that matches a route on every count except the method with 405, so a router claiming `GET /`
in order to refuse it would turn that 404 into a method mismatch and claim the path away from the
UI mount besides. `build_root_router` therefore names `GET` only where nothing else will, and the
handler answers it with the 404 that path has always had.
"""

from __future__ import annotations

from fastapi import APIRouter
from starlette.requests import Request
from starlette.responses import Response

from dhis2w_fhir_serve.errors import BatchNotSupportedError, NotAnEndpointError

#: The path a FHIR service base is, and the methods this facade refuses on it.
SERVICE_BASE_PATH = "/"
BASE_INTERACTION_METHODS = ("POST", "PUT", "PATCH", "DELETE")

#: The methods answered by whatever serves the base instead - the UI shell, when one is mounted.
READ_METHODS = ("GET", "HEAD")


def build_root_router(serve_ui: bool) -> APIRouter:
    """The service base router: batch refused always, the read claimed only when nothing else serves it."""
    router = APIRouter()
    methods: list[str] = list(BASE_INTERACTION_METHODS) if serve_ui else [*BASE_INTERACTION_METHODS, *READ_METHODS]
    router.add_api_route(SERVICE_BASE_PATH, _refuse_base_interaction, methods=methods, include_in_schema=False)
    return router


async def _refuse_base_interaction(request: Request) -> Response:
    """Refuse the interaction the service base was asked for, in the terms it was asked in."""
    if request.method in READ_METHODS:
        raise NotAnEndpointError(request.url.path)
    raise BatchNotSupportedError(request.method)
