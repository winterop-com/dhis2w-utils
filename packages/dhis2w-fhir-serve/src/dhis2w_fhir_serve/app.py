"""The FastAPI application: what the process loads at startup, and what every route reads from.

The factory takes settings and returns an app; everything the app serves is loaded once in the
lifespan and held on `app.state.context`. That is what makes the facade cheap - the store is
parsed once, the CapabilityStatement is rendered once, and a request does index lookups and
nothing else. What the lifespan loads is `dhis2w_fhir_serve.runtime`'s to say: this module opens one
runtime, attaches it, and says in one log line what was loaded.

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
from contextlib import asynccontextmanager

from fastapi import FastAPI

from dhis2w_fhir_serve.errors import register_error_handlers
from dhis2w_fhir_serve.log import LOGGER_NAME, RequestLogMiddleware
from dhis2w_fhir_serve.routes import register_routes
from dhis2w_fhir_serve.runtime import attach_serve_runtime, open_serve_runtime, server_version
from dhis2w_fhir_serve.settings import ServeSettings

#: The title the app carries, matching the command that runs it.
APPLICATION_TITLE = "d2w fhir serve"

logger = logging.getLogger(LOGGER_NAME)


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

    `settings.auth` and `settings.auth_scope` decide which routers carry the authentication check,
    which is settled at build time for the same reason. What the check then DOES is a request-time
    question and lives in `dhis2w_fhir_serve.auth`; an application embedding the facade mounts its own
    dependency over the same set. Nothing secret reaches this factory: the tokens a `token` posture
    compares against are read from the environment by the check itself, never from the settings.
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
    register_routes(
        app,
        serve_ui=settings.ui,
        capture=settings.capture,
        auth=settings.auth,
        auth_scope=settings.auth_scope,
    )
    return app


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Open the runtime this process serves, attach it where the handlers read it, and say what was loaded."""
    settings: ServeSettings = app.state.settings
    async with open_serve_runtime(settings) as runtime:
        attach_serve_runtime(app, runtime)
        context = runtime.context
        summary = context.store.summary()
        # This line fires before the server binds its socket - ASGI lifespan startup completes
        # first, then uvicorn opens the listeners - so it states what was loaded, never that the
        # server is up. The CLI's bind preflight owns the taken-port failure mode.
        logger.info(
            "loaded %s at %s: %d resources across %d types, %d stored responses",
            "live DHIS2" if settings.live else "the compiled IG",
            context.project.project_root,
            summary.total,
            len(summary.counts_by_type),
            context.spool.count(),
        )
        yield
