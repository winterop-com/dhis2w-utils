"""Mount the facade's routers inside your own FastAPI application, behind your own authentication.

`create_app` builds a whole application for one project. An application that already IS a FastAPI
service wants the other seam: its own app, its own routes, its own credentials, with the FHIR
surface mounted beside them. Three functions are the whole contract.

**`open_serve_runtime(settings)`** loads what one facade holds - the project, the store, the spool,
the register - as a value, without building an application at all. The caller owns its lifetime, so
it goes in the caller's own lifespan.

**`attach_serve_runtime(app, runtime)`** puts that runtime where every route handler reads it from.
It is the whole of what an application mounting these routers has to promise them.

**`register_routes(app, ..., authentication=...)`** mounts them. `authentication` is the dependency
the guarded routers carry, and an application that already knows who its callers are passes its own
- here, one header check. Which routers it lands on is `ServeRouters.guarded`, a value this program
can read for itself: `auth_scope = "all"` guards everything but `/metadata`, which stays open
because a client has to be able to read the posture it is expected to meet.

MOUNT YOUR OWN ROUTES FIRST. The facade's read routes are catch-alls - `/{resource_type}` claims any
one-segment path - and `register_routes` puts them last so every fixed path mounted ahead of them
wins. A route added after this call is a route the catch-all already claimed.

Usage:
    uv run python examples/fhir/client/embed_in_fastapi.py [PROJECT_DIRECTORY]

With no argument it embeds the shared example project (see `_fixture.py`). Nothing listens: the
application is driven over an ASGI transport, exactly as `embed_the_facade.py` drives its own.
"""

from __future__ import annotations

import sys
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from _fixture import example_project
from _runner import run_example
from dhis2w_fhir import ServeAuth, ServeAuthScope
from dhis2w_fhir_serve import (
    ServeSettings,
    attach_serve_runtime,
    open_serve_runtime,
    register_error_handlers,
    register_routes,
    serve_routers,
)
from fastapi import FastAPI, HTTPException, Request

FHIR_JSON = "application/fhir+json"
UNAUTHENTICATED = 401

EMBEDDED_BASE_URL = "http://embedded"
"""The authority an ASGI transport puts in front of every path - it names no host and reaches none."""

EXAMPLE_KEY_HEADER = "X-Example-Key"
EXAMPLE_KEY = "the-application-decides"
"""This application's own idea of a credential, standing in for whatever a real service checks."""


def require_example_key(request: Request) -> None:
    """The embedding application's own authentication - what it mounts over the facade's guarded routers."""
    if request.headers.get(EXAMPLE_KEY_HEADER) != EXAMPLE_KEY:
        raise HTTPException(status_code=UNAUTHENTICATED, detail="this service needs its own key")


def build_application(settings: ServeSettings) -> FastAPI:
    """One FastAPI service that serves its own routes and the FHIR facade over the same project."""

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncGenerator[None]:
        """Load the facade while this service starts, and close what it opened when it stops."""
        async with open_serve_runtime(settings) as runtime:
            attach_serve_runtime(application, runtime)
            yield

    application = FastAPI(lifespan=lifespan)
    register_error_handlers(application)

    # This service's own route, mounted before the facade's catch-alls claim one-segment paths.
    @application.get("/status")
    async def status() -> dict[str, str]:
        """What this service says about itself, which is not something the facade answers."""
        return {"service": "the embedding application", "fhir": "mounted below"}

    register_routes(
        application,
        capture=settings.capture,
        auth=settings.auth,
        auth_scope=settings.auth_scope,
        authentication=require_example_key,
    )
    return application


async def main() -> None:
    """Stand the embedding service up in this process and show which of its paths take the key."""
    directory = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else example_project()
    settings = ServeSettings(project_dir=directory, live=True, auth=ServeAuth.TOKEN, auth_scope=ServeAuthScope.ALL)
    application = build_application(settings)

    # The guarded set is data, not a paragraph: this is what the caller's dependency was mounted on.
    routers = serve_routers(capture=settings.capture, auth=settings.auth, auth_scope=settings.auth_scope)
    print(f"guarded routers: {len(routers.guarded)} of {len(routers.in_mount_order())}")

    async with application.router.lifespan_context(application):
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(transport=transport, base_url=EMBEDDED_BASE_URL, timeout=60.0) as client:
            own = (await client.get("/status")).raise_for_status().json()
            print(f"GET /status -> {own['service']}")

            # Open under `all`, because a client has to be able to read how to authenticate here.
            metadata = await client.get("/metadata", headers={"Accept": FHIR_JSON})
            print(f"GET /metadata -> {metadata.status_code} (no key sent)")

            # The refusal this application raised, answered as an OperationOutcome: the facade's own
            # error handlers are registered on this app, so a FHIR client reads a FHIR refusal even
            # though the check that raised it is the application's.
            refused = await client.get("/Questionnaire", headers={"Accept": FHIR_JSON})
            diagnostics = refused.json()["issue"][0]["diagnostics"]
            print(f"GET /Questionnaire -> {refused.status_code} {diagnostics}")

            allowed = await client.get(
                "/Questionnaire",
                headers={"Accept": FHIR_JSON, EXAMPLE_KEY_HEADER: EXAMPLE_KEY},
                params={"_count": 3},
            )
            bundle = allowed.raise_for_status().json()
            print(f"GET /Questionnaire with the key -> {allowed.status_code}, {bundle.get('total', 0)} form(s)")


if __name__ == "__main__":
    run_example(main)
