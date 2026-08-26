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

A live run that forwards credentials - `[serve] auth = "dhis2"`, or `"jwt"` with
`[serve.jwt] forward_bearer = true` - opens a second connection to the same instance, and this one
carries no credential: it is the pool a register read sends the CALLER'S own `Authorization` over, so
DHIS2 decides per caller what comes back. `dhis2w_fhir_serve.passthrough` states why, and opens it;
the lifespan owns it exactly as it owns the client, so both close when the process unwinds.

A project holding a materialized projection opens it here too - `[serve.projection] store` names the
backend, `dhis2w_fhir_serve.projection.factory` builds it, and this context manager owns it exactly as
it owns the two HTTP connections, so the database closes when the process unwinds. It is opened
whether or not `[serve.search]` reads it, because a projection is a thing this project holds rather
than a thing one search does.

A run under `[serve] auth = "jwt"` also reads its issuer here, before anything is served: the
discovery document and then the keys it names. That is a network read at startup and it is a
deliberate one - an issuer this machine cannot reach is a posture this process cannot honour, and
finding that out on a caller's behalf would mean a server that starts and 401s everybody for a
reason none of them can act on. `dhis2w_fhir_serve.oidc` does the reading and `auth.open_jwt_verifier`
turns a failure into the same refusal the other postures raise.
"""

from __future__ import annotations

from contextlib import AsyncExitStack, asynccontextmanager
from importlib.metadata import version
from typing import TYPE_CHECKING, Any

import httpx
from dhis2w_client import Dhis2Client
from dhis2w_fhir.config import FhirProject, ServeAuth, load_project
from pydantic import BaseModel, ConfigDict

from dhis2w_fhir_serve.auth import JWT_VERIFIER_ATTRIBUTE, open_jwt_verifier
from dhis2w_fhir_serve.live import build_live_store, open_live_client
from dhis2w_fhir_serve.metadata import build_metadata_body
from dhis2w_fhir_serve.oidc import JwtVerifier
from dhis2w_fhir_serve.passthrough import open_pass_through_client
from dhis2w_fhir_serve.projection.base import ProjectionStore
from dhis2w_fhir_serve.projection.factory import build_projection_store
from dhis2w_fhir_serve.register.index import TrackedEntityIndex
from dhis2w_fhir_serve.register.surface import RegisterSurface
from dhis2w_fhir_serve.routes.context import (
    CALLER_CLIENT_ATTRIBUTE,
    LIVE_CLIENT_ATTRIBUTE,
    PROJECTION_STORE_ATTRIBUTE,
    SERVE_CONTEXT_ATTRIBUTE,
)
from dhis2w_fhir_serve.settings import ServeSettings
from dhis2w_fhir_serve.spool import ResponseSpool
from dhis2w_fhir_serve.store import ResourceStore, attach_builtin_conformance, load_compiled_store

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator
    from pathlib import Path

    from dhis2w_fhir.config import ProjectionConfig
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

    caller_client: httpx.AsyncClient | None = None
    """The credential-free pool a register read forwards one caller's `Authorization` over.

    None in every mode but live, and in every posture that forwards nothing - `none`, `token`, and
    `jwt` with `[serve.jwt] forward_bearer` off. See `dhis2w_fhir_serve.passthrough`.
    """

    jwt_verifier: JwtVerifier | None = None
    """The `jwt` posture's issuer and its published keys, read while the server started.

    None in every other posture. It holds public keys and no secret, so unlike the client beside it
    there is nothing here a process would want to keep from itself.
    """

    projection_store: ProjectionStore | None = None
    """The materialized projection this project holds, or None where `[serve.projection]` names none.

    A database connection rather than a value, which is why it rides here beside the two HTTP ones
    rather than on `ServeContext`. Nothing in this process writes it - D2 makes `d2w fhir sync` the
    only writer - and every read of it states the cursor it was read at.
    """


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

    A live run under a forwarding posture opens the credential-free pool beside it, which is what a
    register read forwards the caller's own header over. It is opened here, rather than lazily at
    the first request, because it is the connection that decides whose rights an answer is read
    under: a process that could not open it should refuse to serve rather than discover that on a
    caller's behalf. A run under the `jwt` posture reads its issuer here for the same reason - the
    discovery document and the keys it names, before a single request is taken.

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
        caller = None
        if live is not None and _forwards_credentials(settings) and settings.dhis2_base_url is not None:
            caller = await connections.enter_async_context(
                open_pass_through_client(settings.dhis2_base_url, provenance=facade_provenance())
            )
        verifier = await open_jwt_verifier(settings.jwt) if settings.auth is ServeAuth.JWT else None
        projection = await connections.enter_async_context(
            open_projection_store(settings.projection, project_root=project.project_root)
        )
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
            caller_client=caller,
            jwt_verifier=verifier,
            projection_store=projection,
        )


def _forwards_credentials(settings: ServeSettings) -> bool:
    """Whether this run's posture sends a caller's own `Authorization` on to DHIS2, and so needs the pool."""
    if settings.auth is ServeAuth.DHIS2:
        return True
    return settings.auth is ServeAuth.JWT and settings.jwt.forward_bearer


def attach_serve_runtime(app: FastAPI, runtime: ServeRuntime) -> None:
    """Put one loaded runtime where every route handler reads it from, before the first request.

    This is the whole of what an application mounting the facade's routers must promise them. The
    state is the application's rather than the request's because one project, one store, and one
    spool are properties of the process. Four of the five names it writes are the four
    `dhis2w_fhir_serve.routes.context` reads back; the fifth is the JWT verifier, which
    `dhis2w_fhir_serve.auth` reads because it is the only thing that has a use for it.
    """
    setattr(app.state, SERVE_CONTEXT_ATTRIBUTE, runtime.context)
    setattr(app.state, LIVE_CLIENT_ATTRIBUTE, runtime.live_client)
    setattr(app.state, CALLER_CLIENT_ATTRIBUTE, runtime.caller_client)
    setattr(app.state, JWT_VERIFIER_ATTRIBUTE, runtime.jwt_verifier)
    setattr(app.state, PROJECTION_STORE_ATTRIBUTE, runtime.projection_store)


async def build_store(settings: ServeSettings, project: FhirProject, client: Dhis2Client | None) -> ResourceStore:
    """Select the store the facade serves from: the compiled IG on disk, or one built live from DHIS2.

    `client` is the connection a live run holds open, and None in the default mode - the two are the
    same fact stated once, which is why the caller opens it rather than this function.

    Both paths are deliberate about failing loudly, and neither is retried: `CompiledIgMissingError`
    or an unreachable instance propagates out of the lifespan and the server refuses to start,
    rather than serving an empty IG that reads to a client as a project that published nothing.
    """
    if client is not None:
        return attach_builtin_conformance(await build_live_store(project, settings, client))
    return attach_builtin_conformance(load_compiled_store(project))


@asynccontextmanager
async def open_projection_store(
    config: ProjectionConfig, *, project_root: Path
) -> AsyncGenerator[ProjectionStore | None]:
    """Open the projection this project holds, closing it on the way out, or hold none where it names none.

    Nothing is read while it opens and nothing is refused: a projection nobody has synced into is a
    valid state of a valid file, and the surface that would answer out of it says so per request
    rather than stopping the server. That keeps R11 true - a facade configured with a projection is
    not a facade that fails differently from one without.
    """
    store = build_projection_store(config, project_root=project_root)
    if store is None:
        yield None
        return
    try:
        yield store
    finally:
        await _closed(store)


async def _closed(store: ProjectionStore) -> None:
    """Dispose of a projection's connection where the backend holds one to dispose of."""
    closer = getattr(store, "close", None)
    if closer is not None:
        await closer()


def server_version() -> str:
    """The installed version of this package, as the app and its CapabilityStatement report it."""
    return version(DISTRIBUTION_NAME)


def facade_provenance() -> str:
    """What a pass-through read names itself as to the instance: this software, and its version."""
    return f"{DISTRIBUTION_NAME}/{server_version()}"
