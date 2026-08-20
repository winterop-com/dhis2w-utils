"""What one running facade holds, as a value a caller can open without starting a server.

A facade is a project, the resources it serves, the spool it writes receipts into, the register it
answers for, and - under `--live` - one DHIS2 client held open for the life of the process. Loading
all of that is what the ASGI lifespan does, and it is the only thing the lifespan does: this module
is those steps, in order, behind an async context manager, and `dhis2w_fhir_serve.app` is its first
caller.

That split is what lets a test, a batch job, or an embedding application have a loaded store, a
spool, and a register surface for a project without building an application it never intends to
serve - and it is what lets an application that already runs FastAPI mount the facade's routers over
a runtime it opened itself, which is the contract `attach_serve_runtime` states.

The client's lifetime is the context manager's: entering opens it when the settings say the store is
built live, leaving closes it, and a caller that already holds an authenticated one hands it in and
keeps ownership of it. It rides beside the served context rather than on it, for the reason
`dhis2w_fhir_serve.routes.context` gives - a Pydantic model of what a facade serves is not the place
for a live HTTP connection - and `ServeRuntime` is the name for the pair.
"""

from __future__ import annotations

from contextlib import AsyncExitStack, asynccontextmanager
from importlib.metadata import version
from typing import TYPE_CHECKING, Any

from dhis2w_client import Dhis2Client
from dhis2w_fhir.config import FhirProject, load_project
from pydantic import BaseModel, ConfigDict

from dhis2w_fhir_serve.live import build_live_store, open_live_client
from dhis2w_fhir_serve.metadata import build_metadata_body
from dhis2w_fhir_serve.register.index import TrackedEntityIndex
from dhis2w_fhir_serve.register.surface import RegisterSurface
from dhis2w_fhir_serve.routes.context import LIVE_CLIENT_ATTRIBUTE, SERVE_CONTEXT_ATTRIBUTE
from dhis2w_fhir_serve.settings import ServeSettings
from dhis2w_fhir_serve.spool import ResponseSpool
from dhis2w_fhir_serve.store import ResourceStore, load_compiled_store

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from fastapi import FastAPI

#: The distribution the server reports as its software version.
DISTRIBUTION_NAME = "dhis2w-fhir-serve"


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


class ServeRuntime(BaseModel):
    """One loaded facade: everything it serves, and the DHIS2 client it holds open beside that.

    The client is the reason this model allows arbitrary types where `ServeContext` does not. It is
    a live connection rather than a value, it is None in the default mode - which is the whole of
    what makes the register routes live-only - and naming the pair is what an application mounting
    the facade's routers has to be handed.
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    context: ServeContext
    live_client: Dhis2Client | None = None


@asynccontextmanager
async def open_serve_runtime(
    settings: ServeSettings, *, client: Dhis2Client | None = None
) -> AsyncGenerator[ServeRuntime]:
    """Load one facade: the project, its store, its spool, its register, and the statement it answers `/metadata` with.

    Entering opens the DHIS2 client a live run reads through and leaving closes it. A caller that
    already holds an authenticated client hands it in instead, and keeps it open afterwards - the
    runtime never closes a connection it did not open. Handing one to a run that is not live is
    refused rather than ignored: `live` is what says this facade reads an instance, and a client
    beside `live = False` is two statements that disagree.

    Nothing here is retried and nothing is defaulted. `CompiledIgMissingError` from a project that
    has never been built, or an unreachable instance, propagates out and the server refuses to
    start, rather than serving an empty guide that reads to a client as a project that published
    nothing.
    """
    if client is not None and not settings.live:
        raise ValueError("a DHIS2 client is only read through by a live run: build the settings with live=True")
    project = load_project(settings.project_dir)
    async with AsyncExitStack() as connections:
        live = client
        if settings.live and live is None:
            live = await connections.enter_async_context(open_live_client(project, settings))
        store = await build_store(settings, project, live)
        spool = ResponseSpool.at(project.project_root, settings.spool_dir)
        register_surface = RegisterSurface.resolve(
            TrackedEntityIndex.from_store(project, store), settings.tracked_entities
        )
        yield ServeRuntime(
            context=ServeContext(
                project=project,
                store=store,
                spool=spool,
                settings=settings,
                register_surface=register_surface,
                capability_body=build_metadata_body(
                    project=project,
                    store_summary=store.summary(),
                    settings=settings,
                    register_surface=register_surface,
                    server_version=server_version(),
                ),
            ),
            live_client=live,
        )


def attach_serve_runtime(app: FastAPI, runtime: ServeRuntime) -> None:
    """Put one loaded runtime where every route handler reads it from, before the first request.

    This is the whole of what an application mounting the facade's routers must promise them. The
    state is the application's rather than the request's because one project, one store, and one
    spool are properties of the process, and the two names it writes are the two
    `dhis2w_fhir_serve.routes.context` reads back.
    """
    setattr(app.state, SERVE_CONTEXT_ATTRIBUTE, runtime.context)
    setattr(app.state, LIVE_CLIENT_ATTRIBUTE, runtime.live_client)


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
