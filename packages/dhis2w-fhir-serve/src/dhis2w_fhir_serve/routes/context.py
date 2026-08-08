"""How a route handler reaches the serve context the lifespan built.

The context is application state, not per-request state: one project, one store, one spool for
the life of the process. Handlers read it off `request.app.state` rather than through a FastAPI
dependency so nothing about it leaks into the route signatures, which are FHIR's, not ours.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from starlette.requests import Request

if TYPE_CHECKING:
    from dhis2w_fhir_serve.app import ServeContext


def serve_context(request: Request) -> ServeContext:
    """The project, store, spool, and settings this process serves."""
    context: ServeContext = request.app.state.context
    return context
