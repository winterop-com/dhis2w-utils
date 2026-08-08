"""The FastAPI application: what the process loads at startup, and what every route reads from.

The factory takes settings and returns an app; everything the app serves is loaded once in the
lifespan and held on `app.state.context`. That is what makes the facade cheap - the store is
parsed once, the spool is scanned once, the CapabilityStatement is rendered once, and a request
does index lookups and nothing else.

The default mode is fully offline: a compiled IG on disk is the whole world, and no DHIS2 client
is constructed anywhere in this module. `--live` swaps the store for one built from a DHIS2
instance, which is the one seam `build_store` marks.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from importlib.metadata import version
from typing import Any

from dhis2w_fhir.config import FhirProject, load_project
from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict

from dhis2w_fhir_serve.errors import register_error_handlers
from dhis2w_fhir_serve.live import build_live_store
from dhis2w_fhir_serve.log import LOGGER_NAME, RequestLogMiddleware
from dhis2w_fhir_serve.metadata import build_metadata_body
from dhis2w_fhir_serve.routes import register_routes
from dhis2w_fhir_serve.settings import ServeSettings
from dhis2w_fhir_serve.spool import RECEIVED_RESPONSES_RELATIVE_PATH, ResponseSpool
from dhis2w_fhir_serve.store import ResourceStore, load_compiled_store

#: The distribution the server reports as its software version.
DISTRIBUTION_NAME = "dhis2w-fhir-serve"

#: The title the app carries, matching the command that runs it.
APPLICATION_TITLE = "d2w fhir serve"

logger = logging.getLogger(LOGGER_NAME)


class ServeContext(BaseModel):
    """Everything one running facade serves: the project, its resources, its receipts, its settings."""

    model_config = ConfigDict(frozen=True)

    project: FhirProject
    store: ResourceStore
    spool: ResponseSpool
    settings: ServeSettings
    capability_body: dict[str, Any]
    """The `/metadata` document, pre-rendered - the same HTTP-boundary escape hatch `StoreEntry.body` documents."""


def create_app(settings: ServeSettings) -> FastAPI:
    """Build the FHIR facade for one project, loading nothing until the lifespan runs.

    Docs and the OpenAPI document are switched off: this is a FHIR endpoint, and its contract is
    the CapabilityStatement at `/metadata`, not an OpenAPI schema. The two routes it serves are
    catch-alls over `application/fhir+json` bodies, which an OpenAPI document could only
    misdescribe as untyped JSON on a path variable.
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
    register_routes(app)
    return app


async def build_store(settings: ServeSettings, project: FhirProject) -> ResourceStore:
    """Select the store the facade serves from: the compiled IG on disk, or one built live from DHIS2.

    Both paths are deliberate about failing loudly, and neither is retried: `CompiledIgMissingError`
    or an unreachable instance propagates out of the lifespan and the server refuses to start,
    rather than serving an empty IG that reads to a client as a project that published nothing.
    """
    if settings.live:
        return await build_live_store(project, settings)
    return load_compiled_store(project)


def server_version() -> str:
    """The installed version of this package, as the app and its CapabilityStatement report it."""
    return version(DISTRIBUTION_NAME)


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Load the project, its store, and its spool once, and hold them for the life of the process."""
    settings: ServeSettings = app.state.settings
    project = load_project(settings.project_dir)
    store = await build_store(settings, project)
    spool = ResponseSpool.scan(project.project_root / RECEIVED_RESPONSES_RELATIVE_PATH)
    summary = store.summary()
    app.state.context = ServeContext(
        project=project,
        store=store,
        spool=spool,
        settings=settings,
        capability_body=build_metadata_body(
            project=project,
            store_summary=summary,
            spool_count=spool.count(),
            settings=settings,
            server_version=server_version(),
        ),
    )
    logger.info(
        "serving %s from %s: %d resources across %d types, %d stored responses",
        "live DHIS2" if settings.live else "the compiled IG",
        project.project_root,
        summary.total,
        len(summary.counts_by_type),
        spool.count(),
    )
    yield
