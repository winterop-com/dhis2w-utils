"""How a route handler reaches the serve context the lifespan built.

The context is application state, not per-request state: one project, one store, one spool for
the life of the process. Handlers read it off `request.app.state` rather than through a FastAPI
dependency so nothing about it leaks into the route signatures, which are FHIR's, not ours.

The DHIS2 client is state of the same shape and lives beside it rather than on it: `ServeContext`
is a Pydantic model of what the facade serves, and a live HTTP client is not a value that model can
hold without opening itself to arbitrary types. It is None in the default mode, which is the whole
of what makes the register routes live-only. `ServeRuntime` is the name for the pair, and
`attach_serve_runtime` is what writes both of them under the two names this module reads.

The `dhis2` posture holds a third: a connection to the same instance carrying no credential at all,
which a register read borrows to send the CALLER'S header over. It is state of the process for the
same reason the client is - a pool, not a value - and it is None in every other posture, because
nothing else forwards anybody's credential. `dhis2w_fhir_serve.passthrough` is what reads it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from starlette.requests import Request

if TYPE_CHECKING:
    import httpx
    from dhis2w_client import Dhis2Client

    from dhis2w_fhir_serve.runtime import ServeContext

#: Where the three pieces of runtime state live on the application, named here because this is what
#: reads them: an application mounting the facade's routers writes the same three, through
#: `dhis2w_fhir_serve.runtime.attach_serve_runtime`.
SERVE_CONTEXT_ATTRIBUTE = "context"
LIVE_CLIENT_ATTRIBUTE = "live_client"
CALLER_CLIENT_ATTRIBUTE = "caller_client"


def serve_context(request: Request) -> ServeContext:
    """The project, store, spool, register surface, and settings this process serves."""
    context: ServeContext = getattr(request.app.state, SERVE_CONTEXT_ATTRIBUTE)
    return context


def live_client(request: Request) -> Dhis2Client | None:
    """The DHIS2 client this process holds open, or None when it serves a compiled guide."""
    client: Dhis2Client | None = getattr(request.app.state, LIVE_CLIENT_ATTRIBUTE, None)
    return client


def caller_client(request: Request) -> httpx.AsyncClient | None:
    """The credential-free connection pass-through reads borrow, or None outside the `dhis2` posture."""
    connection: httpx.AsyncClient | None = getattr(request.app.state, CALLER_CLIENT_ATTRIBUTE, None)
    return connection
