"""How a route handler reaches the serve context the lifespan built.

The context is application state, not per-request state: one project, one store, one spool for
the life of the process. Handlers read it off `request.app.state` rather than through a FastAPI
dependency so nothing about it leaks into the route signatures, which are FHIR's, not ours.

The DHIS2 client is state of the same shape and lives beside it rather than on it: `ServeContext`
is a Pydantic model of what the facade serves, and a live HTTP client is not a value that model can
hold without opening itself to arbitrary types. It is None in the default mode, which is the whole
of what makes the patient routes live-only.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from starlette.requests import Request

if TYPE_CHECKING:
    from dhis2w_client import Dhis2Client

    from dhis2w_fhir_serve.app import ServeContext


def serve_context(request: Request) -> ServeContext:
    """The project, store, spool, patient index, and settings this process serves."""
    context: ServeContext = request.app.state.context
    return context


def live_client(request: Request) -> Dhis2Client | None:
    """The DHIS2 client this process holds open, or None when it serves a compiled guide."""
    client: Dhis2Client | None = getattr(request.app.state, "live_client", None)
    return client
