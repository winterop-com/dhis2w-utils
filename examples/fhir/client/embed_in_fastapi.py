"""Mount the facade inside your own FastAPI application, behind your own authentication.

`create_app` builds a whole application for one project. An application that already IS a FastAPI
service wants the other seam: its own app, its own routes, its own credentials, with the facade
mounted beside them. Three functions are the whole contract.

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

TWO POSTURES, AND THIS PROGRAM SHOWS BOTH. `serve_routers` groups the routers by what mounting each
group requires, and an embedder picks from that:

- **The FHIR surface alone.** Mount `routers.fhir` and `routers.read` and stop. The result serves
  `/metadata`, the resource reads, the searches, and the capture - and not one operational endpoint.
  No receipts listing, no settings document, no evaluator, no vocabularies, nothing that answers
  about the process. That is the posture for a service that wants FHIR out of DHIS2 and intends to
  operate itself.
- **The controls as well.** Hand `routers` to `build_facade_api` and mount what comes back wherever
  you want it - `/facade` is where this package's own factory puts it, and a service that already
  owns that path is free to choose another. The mount publishes its own OpenAPI document, so
  `/facade/openapi.json` describes exactly the operations you mounted.

`register_routes` is the second posture with both choices made for you: FHIR at the base URL, CDS
Hooks beside it, this facade's own API at `/facade`, the catch-alls last.

MOUNT YOUR OWN ROUTES FIRST. The facade's read routes are catch-alls - `/{resource_type}` claims any
one-segment path - and they mount last so every fixed path mounted ahead of them wins. A route added
after that is a route the catch-all already claimed.

Usage:
    uv run python examples/fhir/client/embed_in_fastapi.py [PROJECT_DIRECTORY]

With no argument it embeds the shared example project (see `_fixture.py`). Nothing listens: the
applications are driven over an ASGI transport, exactly as `embed_the_facade.py` drives its own.
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
    FACADE_MOUNT_PATH,
    ServeSettings,
    accept_head_wherever_get_is_served,
    attach_serve_runtime,
    build_facade_api,
    open_serve_runtime,
    register_error_handlers,
    register_routes,
    require_json_is_acceptable,
    serve_routers,
)
from fastapi import Depends, FastAPI, HTTPException, Request

FHIR_JSON = "application/fhir+json"
NOT_FOUND = 404
UNAUTHENTICATED = 401

EMBEDDED_BASE_URL = "http://embedded"
"""The authority an ASGI transport puts in front of every path - it names no host and reaches none."""

EXAMPLE_KEY_HEADER = "X-Example-Key"
EXAMPLE_KEY = "the-application-decides"
"""This application's own idea of a credential, standing in for whatever a real service checks."""

OWN_CONTROLS_PREFIX = "/controls"
"""Where this example puts the operational API, to show that the mount path is the embedder's."""


def require_example_key(request: Request) -> None:
    """The embedding application's own authentication - what it mounts over the facade's guarded routers."""
    if request.headers.get(EXAMPLE_KEY_HEADER) != EXAMPLE_KEY:
        raise HTTPException(status_code=UNAUTHENTICATED, detail="this service needs its own key")


@asynccontextmanager
async def facade_lifespan(application: FastAPI, settings: ServeSettings) -> AsyncGenerator[None]:
    """Load the facade while a service starts, and close what it opened when the service stops."""
    async with open_serve_runtime(settings) as runtime:
        attach_serve_runtime(application, runtime)
        yield


def build_application(settings: ServeSettings) -> FastAPI:
    """One FastAPI service that serves its own routes and the whole facade over the same project.

    `register_routes` is the posture that takes everything: the FHIR surface at the base URL, CDS
    Hooks beside it, and this facade's own API at `/facade` with its own OpenAPI document.
    """

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncGenerator[None]:
        """Hand this service's startup to the facade's own loader."""
        async with facade_lifespan(application, settings):
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


def build_hand_mounted_application(settings: ServeSettings, controls_prefix: str | None) -> FastAPI:
    """One FastAPI service that mounts the groups itself, with or without the operational API.

    `controls_prefix` is the choice this example exists to show. None mounts two of the four groups
    and leaves the rest out: no receipts listing, no settings document, no caller check, no
    evaluator, no vocabularies, no register listings, and no CDS Hooks discovery. `/metadata` still
    describes everything the application does serve, because the CapabilityStatement is built from
    what the store holds rather than from what was mounted.

    A prefix mounts the controls there instead. `build_facade_api` answers a FastAPI application, so
    mounting it is one call, and what it publishes at `{prefix}/openapi.json` describes exactly the
    operations inside it. It is handed this application's `state`, which is what makes the runtime
    attached to the outer application the runtime its handlers read.

    The FHIR routers carry the `Accept` negotiation at their mount and the catch-alls go last, which
    is the whole of what `ServeRouters` asks of a caller mounting them by hand.
    """

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncGenerator[None]:
        """Hand this service's startup to the facade's own loader."""
        async with facade_lifespan(application, settings):
            yield

    application = FastAPI(lifespan=lifespan)
    register_error_handlers(application)
    routers = serve_routers(capture=settings.capture, auth=settings.auth, auth_scope=settings.auth_scope)
    for router in routers.in_mount_order():
        accept_head_wherever_get_is_served(router)
    for router in routers.fhir:
        guard = [Depends(require_example_key)] if routers.is_guarded(router) else []
        application.include_router(router, dependencies=[*guard, Depends(require_json_is_acceptable)])
    if controls_prefix is not None:
        controls = build_facade_api(
            routers, authentication=require_example_key, state=application.state, mount_path=controls_prefix
        )
        application.mount(controls_prefix, controls)
    read_guard = [Depends(require_example_key)] if routers.is_guarded(routers.read) else []
    application.include_router(routers.read, dependencies=[*read_guard, Depends(require_json_is_acceptable)])
    return application


async def main() -> None:
    """Stand both postures up in this process and show what each of them answers."""
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

            # The controls, under the mount, behind the same key - and their contract, which is open
            # in every scope for `/metadata`'s reason.
            listing = await client.get(f"{FACADE_MOUNT_PATH}/spool", headers={EXAMPLE_KEY_HEADER: EXAMPLE_KEY})
            print(f"GET {FACADE_MOUNT_PATH}/spool with the key -> {listing.status_code}")
            contract = (await client.get(f"{FACADE_MOUNT_PATH}/openapi.json")).raise_for_status().json()
            print(
                f"GET {FACADE_MOUNT_PATH}/openapi.json -> {len(contract['paths'])} operations, "
                f"served under {contract['servers'][0]['url']} (no key sent)"
            )

    await show_the_fhir_only_posture(settings)
    await show_the_controls_under_a_prefix_of_your_own(settings)


async def show_the_fhir_only_posture(settings: ServeSettings) -> None:
    """Stand up the FHIR-only posture and show that it serves FHIR and nothing operational at all."""
    application = build_hand_mounted_application(settings, controls_prefix=None)
    async with application.router.lifespan_context(application):
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(transport=transport, base_url=EMBEDDED_BASE_URL, timeout=60.0) as client:
            headers = {"Accept": FHIR_JSON, EXAMPLE_KEY_HEADER: EXAMPLE_KEY}
            metadata = await client.get("/metadata", headers={"Accept": FHIR_JSON})
            forms = await client.get("/Questionnaire", headers=headers, params={"_count": 1})
            print(f"\nFHIR only: GET /metadata -> {metadata.status_code}, GET /Questionnaire -> {forms.status_code}")

            missing = await client.get(f"{FACADE_MOUNT_PATH}/spool", headers=headers)
            print(f"FHIR only: GET {FACADE_MOUNT_PATH}/spool -> {missing.status_code} (nothing operational mounted)")
            if missing.status_code != NOT_FOUND:
                raise AssertionError("the FHIR-only posture mounted an operational endpoint")


async def show_the_controls_under_a_prefix_of_your_own(settings: ServeSettings) -> None:
    """Stand up the other posture, with the operational API somewhere this service chose."""
    application = build_hand_mounted_application(settings, controls_prefix=OWN_CONTROLS_PREFIX)
    async with application.router.lifespan_context(application):
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(transport=transport, base_url=EMBEDDED_BASE_URL, timeout=60.0) as client:
            headers = {EXAMPLE_KEY_HEADER: EXAMPLE_KEY}
            listing = await client.get(f"{OWN_CONTROLS_PREFIX}/spool", headers=headers)
            contract = (await client.get(f"{OWN_CONTROLS_PREFIX}/openapi.json")).raise_for_status().json()
            print(f"\nControls at {OWN_CONTROLS_PREFIX}: GET {OWN_CONTROLS_PREFIX}/spool -> {listing.status_code}")
            print(
                f"Controls at {OWN_CONTROLS_PREFIX}: the contract names {len(contract['paths'])} operations "
                f"under {contract['servers'][0]['url']}"
            )


if __name__ == "__main__":
    run_example(main)
