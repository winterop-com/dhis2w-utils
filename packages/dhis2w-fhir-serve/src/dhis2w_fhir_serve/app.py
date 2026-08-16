"""The FastAPI application: what the process loads at startup, and what every route reads from.

The factory takes settings and returns an app; everything the app serves is loaded once in the
lifespan and held on `app.state.context`. That is what makes the facade cheap - the store is
parsed once, the CapabilityStatement is rendered once, and a request does index lookups and
nothing else.

The spool is the one exception, and deliberately so: it is a path, not a loaded index, and every
read of it re-reads the directory. `d2w fhir forward` runs as a separate process and moves receipt
files between the spool's three states while this server is up, so anything cached here would go
stale within seconds of a drain. See `dhis2w_fhir_serve.spool`.

The default mode is fully offline: a compiled IG on disk is the whole world, and no DHIS2 client is
constructed anywhere in this module. `--live` swaps the store for one built from a DHIS2 instance,
and keeps the client that built it open for the life of the process, because the register routes
answer from the instance per request rather than from anything loaded here. That client is the only
thing in a running facade that is neither the store nor the spool, and it lives on `app.state`
rather than on the context for the reason `dhis2w_fhir_serve.routes.context` states. It is closed
when the lifespan unwinds; the default mode never opens one, which is what makes the register routes
live-only.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import AsyncExitStack, asynccontextmanager
from importlib.metadata import version
from typing import TYPE_CHECKING, Any

from dhis2w_fhir.config import FhirProject, load_project
from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict

from dhis2w_fhir_serve.errors import register_error_handlers
from dhis2w_fhir_serve.live import build_live_store, open_live_client
from dhis2w_fhir_serve.log import LOGGER_NAME, RequestLogMiddleware
from dhis2w_fhir_serve.metadata import build_metadata_body
from dhis2w_fhir_serve.register.index import TrackedEntityIndex
from dhis2w_fhir_serve.register.surface import RegisterSurface
from dhis2w_fhir_serve.routes import register_routes
from dhis2w_fhir_serve.settings import ServeSettings
from dhis2w_fhir_serve.spool import ResponseSpool
from dhis2w_fhir_serve.store import ResourceStore, load_compiled_store

if TYPE_CHECKING:
    from dhis2w_client import Dhis2Client

#: The distribution the server reports as its software version.
DISTRIBUTION_NAME = "dhis2w-fhir-serve"

#: The title the app carries, matching the command that runs it.
APPLICATION_TITLE = "d2w fhir serve"

logger = logging.getLogger(LOGGER_NAME)


class ServeContext(BaseModel):
    """Everything one running facade serves: the project, its resources, its spool, its settings."""

    model_config = ConfigDict(frozen=True)

    project: FhirProject
    store: ResourceStore
    spool: ResponseSpool
    settings: ServeSettings
    register_surface: RegisterSurface
    """What this process answers for: the published register, narrowed by `[serve.tracked_entities]`."""

    capability_body: dict[str, Any]
    """The `/metadata` document, pre-rendered - the same HTTP-boundary escape hatch `StoreEntry.body` documents."""


def create_app(settings: ServeSettings) -> FastAPI:
    """Build the FHIR facade for one project, loading nothing until the lifespan runs.

    Docs and the OpenAPI document are switched off: this is a FHIR endpoint, and its contract is
    the CapabilityStatement at `/metadata`, not an OpenAPI schema. The two routes it serves are
    catch-alls over `application/fhir+json` bodies, which an OpenAPI document could only
    misdescribe as untyped JSON on a path variable.

    `settings.ui` adds the built capture UI as a static mount at `/`, after every FHIR route.
    A missing bundle raises here, while the app is being built, so `--ui` on a checkout that has
    never built the frontend fails as one line rather than as a white page on the first request.

    `settings.capture` decides which router claims `POST /QuestionnaireResponse` - the create route,
    or the refusal that names the key. It is settled here, at build time, because it is what this
    server offers rather than something a request could be judged against.
    """
    app = FastAPI(
        title=APPLICATION_TITLE,
        version=server_version(),
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=_lifespan,
    )
    app.state.settings = settings
    app.add_middleware(RequestLogMiddleware)
    register_error_handlers(app)
    register_routes(app, serve_ui=settings.ui, capture=settings.capture)
    return app


async def build_store(settings: ServeSettings, project: FhirProject, client: Dhis2Client | None) -> ResourceStore:
    """Select the store the facade serves from: the compiled IG on disk, or one built live from DHIS2.

    `client` is the connection a live run holds open, and None in the default mode - the two are the
    same fact stated once, which is why the caller opens it rather than this function.

    Both paths are deliberate about failing loudly, and neither is retried: `CompiledIgMissingError`
    or an unreachable instance propagates out of the lifespan and the server refuses to start,
    rather than serving an empty IG that reads to a client as a project that published nothing.
    """
    if client is not None:
        return await build_live_store(project, settings, client)
    return load_compiled_store(project)


def server_version() -> str:
    """The installed version of this package, as the app and its CapabilityStatement report it."""
    return version(DISTRIBUTION_NAME)


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Load the project and its store once, hold the live client open, and point the facade at its spool."""
    settings: ServeSettings = app.state.settings
    project = load_project(settings.project_dir)
    async with AsyncExitStack() as connections:
        client = await connections.enter_async_context(open_live_client(project, settings)) if settings.live else None
        app.state.live_client = client
        store = await build_store(settings, project, client)
        spool = ResponseSpool.at(project.project_root, settings.spool_dir)
        summary = store.summary()
        register_surface = RegisterSurface.resolve(
            TrackedEntityIndex.from_store(project, store), settings.tracked_entities
        )
        app.state.context = ServeContext(
            project=project,
            store=store,
            spool=spool,
            settings=settings,
            register_surface=register_surface,
            capability_body=build_metadata_body(
                project=project,
                store_summary=summary,
                settings=settings,
                register_surface=register_surface,
                server_version=server_version(),
            ),
        )
        # This line fires before the server binds its socket - ASGI lifespan startup completes
        # first, then uvicorn opens the listeners - so it states what was loaded, never that the
        # server is up. The CLI's bind preflight owns the taken-port failure mode.
        logger.info(
            "loaded %s at %s: %d resources across %d types, %d stored responses",
            "live DHIS2" if settings.live else "the compiled IG",
            project.project_root,
            summary.total,
            len(summary.counts_by_type),
            spool.count(),
        )
        yield
