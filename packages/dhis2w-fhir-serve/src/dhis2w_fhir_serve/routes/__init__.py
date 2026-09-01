"""Route assembly: every router the facade mounts, where each group mounts, and in what order.

TWO SURFACES, TWO ADDRESSES. The base URL is FHIR's. `/metadata` is its contract, the read
catch-alls answer resource types out of the store, and every path a FHIR client is entitled to guess
at is where the specification says it is. Everything this facade answers ABOUT ITSELF - the receipts
it holds, the settings it was started with, who it just decided the caller is, the expression
evaluator, the vocabularies it publishes, the register listings it reads from the instance - is a
different API with a different contract, and it is served under `/facade` as an application of its
own with its own OpenAPI document at `/facade/openapi.json`. `dhis2w_fhir_serve.routes.spool` argues
why those answers are not FHIR; this module is where that argument becomes an address.

`/cds-services` is the third family and it is at the root beside FHIR, because CDS Hooks fixes the
discovery path at `{base}/cds-services` exactly as FHIR fixes `{base}/metadata`. It answers plain
JSON and it is not this facade's own API - it is somebody else's specification implemented here, and
a specification's path is not ours to move. `dhis2w_fhir_serve.routes.cds` is the implementation.

WHAT MOUNTS BEFORE WHAT, AT THE ROOT. `/{resource_type}` and `/{resource_type}/{resource_id}` match
any path of their shape, so the read router mounts last and every router carrying a fixed path mounts
ahead of it. `/metadata`, `/cds-services`, and the `/facade` mount itself are one-segment fixed paths
and all sit in that group - as is `/cds-services/{id}` one level down. FHIR resource types are
PascalCase, so a lowercase segment can never be one the read router should have claimed, whichever
depth it sits at.

`$evaluate` is a one-segment fixed path too, and a FHIR one: it is the system-level operation
answering an evaluation as a `Parameters` resource, so it mounts with the FHIR group while
`POST /facade/evaluate` answers the same evaluation as this facade's own JSON. A segment beginning
with `$` can shadow no resource type either, and both addresses run the same evaluation over the same
three contexts - `dhis2w_fhir_serve.routes.evaluate_operation` argues the split.

`$summary` is the one FHIR path whose fixed segment sits at the END rather than the start, and it
mounts in that same group for exactly that reason: `/{ResourceType}/$summary` is the shape
`/{resource_type}/{resource_id}` also matches, so a summary router mounted after the read catch-alls
would never be reached and a client asking for one would be told there is no resource with the id
`$summary`. `dhis2w_fhir_serve.routes.summary` is what it answers.

THE INSTANCE-SOURCED READS ARE THE FACADE'S, ALL THREE OF THEM. `/facade/tracked-entities/{uid}/enrollments`
lists what one entity is enrolled in, `/facade/tracked-entities/{uid}/events` is that entity's
record, and `/facade/data-sets/{uid}/responses` is what the instance holds for one data set - and
none of them is a FHIR interaction: the CapabilityStatement names them in prose and declares none,
because FHIR has no interaction at any of those addresses. The record and the data set responses
answer `application/fhir+json` all the same - a Bundle of QuestionnaireResponses is a FHIR document
however it was asked for - which is why they carry the `Accept` negotiation as their own mount-time
requirement rather than as the group's. `ServeRouters.negotiated` is that requirement stated as data.

`/facade/whoami` is the one path whose ANSWER a posture decides rather than a scope guarding it.
Every other route is mounted by every run and the posture only decides which of them carry the check;
that one answers who the caller is, so under `auth = "none"` there is nobody to answer about and the
address is mounted as the refusal that says so. `dhis2w_fhir_serve.routes.whoami` argues it.

The register's resource types are the exception that needs no mount of its own. They are FHIR
resource types answered from the DHIS2 instance rather than from the store, but which types they are
is a property of the guide this process loaded, so the read router dispatches to
`dhis2w_fhir_serve.routes.register` at request time instead of a router claiming paths that could
only be named once the store was open.

`capture` picks which router claims `POST /QuestionnaireResponse`: the create route, or the refusal
that names `[serve] capture = false`. One of the two is always mounted, so the address never falls
through to the read catch-all - which would answer the same 405 without saying why.

The capture UI sits on both sides of that line, which is why `serve_ui` is an argument here rather
than something the UI module could arrange for itself. Its asset tree is a fixed path and mounts
with the other fixed paths, ahead of the catch-alls that would otherwise claim
`/assets/<file>`; its shell is a catch-all of its own and mounts after everything. See
`dhis2w_fhir_serve.ui` for what each mount is and why the split is not optional.

Every GET route also answers HEAD. RFC 9110 defines HEAD as GET without the body, and FHIR
liveness probes lean on that - a monitor asking `HEAD /metadata` is asking whether the server is
up, and a 405 there reads as down. FastAPI registers only the methods a decorator names, so the
parity is applied here in one sweep over each router as it is mounted rather than repeated (and
one day forgotten) on every route. The UI mounts need no sweep: `StaticFiles` answers HEAD itself.

WHICH ROUTERS ARE BEHIND THE AUTHENTICATION CHECK is decided here as well, and stated the same way:
`ServeRouters.guarded` names them, and `[serve] auth_scope` is the whole of what decides the set.
`write` guards the state-changing surface, which is one route - `POST /QuestionnaireResponse`, the
create. Every other POST this facade serves writes nothing: `$generate` reads a published form and
answers with a draft, `POST /facade/evaluate` and `$evaluate` run an expression over what is served,
a CDS Hooks call answers cards, and `POST /` is a refusal on every posture. `all` guards everything
except `/metadata`, which stays open because a client has to be able to read the posture it is
expected to meet - a server that refuses to say how to authenticate to it is one nobody can
authenticate to. `/facade/openapi.json` and the documentation page beside it stay open under both
scopes for exactly that reason: they are the facade API's own `/metadata`, and a contract nobody may
read is a contract nobody can meet. Neither carries a credential in either direction, and neither
says anything a request to `/metadata` does not. The UI mounts stay open under both, because a
sign-in prompt has to be servable. `/facade/whoami` is guarded under both scopes, because a
credential check that answered without checking would be no check at all.

All of that is stated as data by `serve_routers`, so an application mounting the facade beside its
own routes gets the order, the split, the capture choice, and the guarded set as values rather than
as four paragraphs it has to read. `register_routes` is a loop over what that function answers, and
holds no router knowledge of its own - including the check itself, which is one dependency an
embedding application is free to replace with its own over the same `guarded` set.
"""

import warnings
from typing import Any

from dhis2w_fhir.config import ServeAuth, ServeAuthScope
from fastapi import APIRouter, Depends, FastAPI
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict

from dhis2w_fhir_serve.routes.negotiation import require_json_is_acceptable

__all__ = [
    "FACADE_API_TITLE",
    "FACADE_DOCUMENTATION_PATH",
    "FACADE_MOUNT_PATH",
    "FACADE_OPENAPI_PATH",
    "ServeRouters",
    "accept_head_wherever_get_is_served",
    "api_routes",
    "build_facade_api",
    "describe_each_read_once",
    "facade_operation_id",
    "register_routes",
    "serve_routers",
]

#: Where this facade's own API lives, and where its contract is published inside that mount.
#:
#: One lowercase segment, so it shadows no PascalCase FHIR resource type - the same rule every
#: fixed path on this server follows. The two paths below are relative to the mount, so the
#: document is read at `/facade/openapi.json` and the page at `/facade/docs`.
FACADE_MOUNT_PATH = "/facade"
FACADE_OPENAPI_PATH = "/openapi.json"
FACADE_DOCUMENTATION_PATH = "/docs"

#: What the facade API calls itself in its own OpenAPI document and on its documentation page.
FACADE_API_TITLE = "d2w fhir serve - facade API"

#: The one-sentence subtitle of that document: what this API is, said before anything is listed.
FACADE_API_SUMMARY = "Everything a d2w fhir serve facade answers about itself, rather than out of FHIR."

#: The document's own introduction, which is the first thing a reader of the contract meets.
FACADE_API_DESCRIPTION = """
This is the operational API of one `d2w fhir serve` process: the receipts it is holding, the
settings it was started with, who it decided the caller is, the expression evaluator, the
vocabularies the served guide publishes, and the DHIS2 register listings and data set values a
live run reads per request.

**It is not the FHIR API.** The FHIR surface is served at the base URL beside this mount, and its
contract is the CapabilityStatement at `GET /metadata` - not this document. A client reading
Questionnaires, posting a QuestionnaireResponse, or searching the register wants that surface. The
two are separate on purpose: FHIR's paths belong to the specification, and these belong to this
server.

Every operation here answers `application/json`, except the tracked entity record and one data
set's responses, which answer a FHIR `Bundle` as `application/fhir+json` - both are FHIR documents
read at addresses FHIR defines no interaction for.

Refusals are FHIR `OperationOutcome` documents, exactly as they are on the FHIR surface, so one
client reads one refusal shape whichever surface it met.

Whether an operation here needs a credential is `[serve] auth_scope`: under `write` only the FHIR
create route is guarded and everything here is open; under `all` every operation here needs one,
except this document itself. `GET /facade/whoami` is guarded under both, because a credential check
that answered without checking would be no check at all.
""".strip()

#: How the document groups its operations, and what each group is for.
FACADE_API_TAGS = [
    {"name": "Caller", "description": "Who this server decided the caller is, under the posture that decided it."},
    {"name": "Receipts", "description": "The submissions this facade has stored, and what became of each of them."},
    {"name": "Configuration", "description": "How this process was started, as far as a screen has to act on it."},
    {
        "name": "Metadata health",
        "description": "What the DHIS2 instance behind a live run holds that the guide cannot carry cleanly.",
    },
    {
        "name": "Register",
        "description": "What a live run reads about one tracked entity from the DHIS2 instance, per request.",
    },
    {
        "name": "Data sets",
        "description": "What a live run reads from the DHIS2 instance about one data set's own values, per request.",
    },
    {"name": "Evaluation", "description": "Running a FHIRPath expression or a CQL library over what is served."},
    {"name": "Terminology", "description": "Asking about the code systems and value sets this guide publishes."},
]


class ServeRouters(BaseModel):
    """Every router one facade mounts, grouped by what mounting it requires.

    The four fields are four different requirements, not a taxonomy: `fhir` mounts at the base URL
    under `Depends(require_json_is_acceptable)`, `cds_hooks` mounts at the base URL without it,
    `facade` mounts under a prefix of the mounting application's choosing - `/facade` is where this
    package's own factory puts it - and `read` mounts at the base URL after every fixed path an
    application serves, its own included, since `/{resource_type}` claims any one-segment path.
    Every one of them wants the HEAD sweep.

    THE GROUPS ARE WHAT AN EMBEDDER PICKS FROM, and the picking is the point of stating them as
    data. An application that wants FHIR out of DHIS2 and intends to operate itself mounts `fhir`
    and `read` and stops: what it gets serves `/metadata`, the reads, the searches, and the capture,
    and not one operational endpoint - no receipts listing, no settings document, no caller check,
    no evaluator, no vocabularies, no register listings. An application that wants the controls
    hands this value to `build_facade_api` and mounts what comes back, at `/facade` or at a prefix
    of its own, and gets an OpenAPI contract describing exactly what it mounted.
    `register_routes` is both choices made the way this package's factory makes them.
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    fhir: tuple[APIRouter, ...]
    """The FHIR surface: what a client that takes no JSON is refused before, at mount time."""

    cds_hooks: tuple[APIRouter, ...]
    """The CDS Hooks discovery document and the one service behind it, whose path the specification fixes.

    At the base URL rather than under the facade mount, and not because it is FHIR: CDS Hooks defines
    discovery at `{base}/cds-services`, so an EHR configured with this server's base URL asks for
    that path and no other. It answers plain JSON, so it carries no `Accept` negotiation.
    """

    facade: tuple[APIRouter, ...]
    """The routers answering about this facade rather than serving FHIR resources out of it.

    Mounted under one prefix as an application of its own, which is what gives them an OpenAPI
    document of their own. Their order is the order a reader meets them in: who is calling
    (`/whoami`), what a running server holds (`/spool`, `/uiconfig`, `/metadata-health`), what it
    answers about the instance (`/tracked-entities/{uid}/enrollments`, the record beside it, and one
    data set's own responses), and what it runs over either (`/evaluate`, `/terminology/*`).
    """

    read: APIRouter
    """The catch-alls, named on their own because they mount last."""

    guarded: tuple[APIRouter, ...] = ()
    """The routers the authentication check belongs on, as objects also present in the fields above.

    A subset rather than a fifth group: a router is mounted once, in the group whose requirement it
    carries, and this names which of those mounts additionally take `Depends(require_authenticated)`.
    Empty under `[serve] auth = "none"`, which is what makes the default posture cost a request
    nothing. An application that authenticates its callers its own way mounts its own dependency over
    exactly this set.
    """

    negotiated: tuple[APIRouter, ...] = ()
    """The routers outside the FHIR group that carry the `Accept` negotiation anyway.

    A subset for the same reason `guarded` is one, and today it names two routers: the tracked entity
    record and one data set's own responses. Both are the facade's own addresses - FHIR declares no
    interaction at either - and what both answer is a FHIR Bundle, so a client that takes no JSON is
    refused before it runs exactly as it is on the FHIR surface. Every other router in `facade`
    answers `application/json` and negotiates nothing.
    """

    def is_guarded(self, router: APIRouter) -> bool:
        """Whether one router carries the authentication check, compared by identity rather than by path."""
        return any(router is guarded for guarded in self.guarded)

    def is_negotiated(self, router: APIRouter) -> bool:
        """Whether one router outside the FHIR group carries the `Accept` negotiation as well."""
        return any(router is negotiated for negotiated in self.negotiated)

    def in_mount_order(self) -> tuple[APIRouter, ...]:
        """Every router, in the order a route table has to see them: fixed paths first, catch-alls last."""
        return (*self.fhir, *self.cds_hooks, *self.facade, self.read)


def serve_routers(
    *,
    capture: bool = True,
    serve_ui: bool = False,
    auth: ServeAuth = ServeAuth.NONE,
    auth_scope: ServeAuthScope = ServeAuthScope.WRITE,
) -> ServeRouters:
    """The facade's routers for one posture, with what mounting each group requires stated as data.

    `capture` picks which router claims `POST /QuestionnaireResponse` - the create route, or the
    refusal that names `[serve] capture = false`. `serve_ui` decides whether the service base router
    claims `GET /`: with the capture UI mounted, the shell serves it instead, and a router claiming
    the path in order to refuse it would take it away from the mount. Neither is a request-time
    question, which is why both are settled here.

    `auth` also picks which `/whoami` is mounted - the one that names the caller a check established,
    or the one that refuses under `none` because no check ran. `auth` and `auth_scope` fill
    `guarded`. `none` guards nothing. `write` guards the create route
    and only the create route, and guards nothing at all on a server that receives nothing - putting
    a 405 behind a credential would answer "who are you" where the honest answer is "this server
    takes no submissions". `all` guards every router but `/metadata`.

    The routers are imported inside this function rather than at module scope: a route module reaches
    the serve context through `dhis2w_fhir_serve.routes.context`, which imports this package, so
    importing the route modules from this package's body would close the cycle.
    """
    from dhis2w_fhir_serve.metadata import router as metadata_router
    from dhis2w_fhir_serve.routes.capture import refusal_router as capture_refusal_router
    from dhis2w_fhir_serve.routes.capture import router as capture_router
    from dhis2w_fhir_serve.routes.cds import router as cds_router
    from dhis2w_fhir_serve.routes.data_sets import router as data_sets_router
    from dhis2w_fhir_serve.routes.enrollments import router as enrollments_router
    from dhis2w_fhir_serve.routes.evaluate import router as evaluate_router
    from dhis2w_fhir_serve.routes.evaluate_operation import router as evaluate_operation_router
    from dhis2w_fhir_serve.routes.generate import router as generate_router
    from dhis2w_fhir_serve.routes.history import router as history_router
    from dhis2w_fhir_serve.routes.metadata_health import router as metadata_health_router
    from dhis2w_fhir_serve.routes.read import router as read_router
    from dhis2w_fhir_serve.routes.root import build_root_router
    from dhis2w_fhir_serve.routes.spool import router as spool_router
    from dhis2w_fhir_serve.routes.summary import router as summary_router
    from dhis2w_fhir_serve.routes.terminology import router as terminology_router
    from dhis2w_fhir_serve.routes.translate import router as translate_router
    from dhis2w_fhir_serve.routes.uiconfig import router as ui_config_router
    from dhis2w_fhir_serve.routes.whoami import refusal_router as whoami_refusal_router
    from dhis2w_fhir_serve.routes.whoami import router as whoami_router

    submissions = capture_router if capture else capture_refusal_router
    fhir = (
        metadata_router,
        submissions,
        build_root_router(serve_ui),
        evaluate_operation_router,
        translate_router,
        generate_router,
        summary_router,
    )
    cds_hooks = (cds_router,)
    # `/whoami` names a caller only where a posture does: a server that checks nobody has nobody to
    # name, and under `none` the address is mounted as the refusal that says so - left unmounted it
    # would answer the facade mount's own 404 rather than the sentence that says which posture is
    # missing. It leads the group because it is the one router that answers about the caller rather
    # than about what is served. See `dhis2w_fhir_serve.routes.whoami`.
    naming = (whoami_router,) if auth is not ServeAuth.NONE else (whoami_refusal_router,)
    facade = (
        *naming,
        spool_router,
        ui_config_router,
        metadata_health_router,
        enrollments_router,
        history_router,
        data_sets_router,
        evaluate_router,
        terminology_router,
    )
    return ServeRouters(
        fhir=fhir,
        cds_hooks=cds_hooks,
        facade=facade,
        read=read_router,
        negotiated=(history_router, data_sets_router),
        guarded=_guarded_routers(
            auth=auth,
            auth_scope=auth_scope,
            capture=capture,
            submissions=submissions,
            conformance=metadata_router,
            naming=naming,
            fhir=fhir,
            cds_hooks=cds_hooks,
            facade=facade,
            read=read_router,
        ),
    )


def _guarded_routers(
    *,
    auth: ServeAuth,
    auth_scope: ServeAuthScope,
    capture: bool,
    submissions: APIRouter,
    conformance: APIRouter,
    naming: tuple[APIRouter, ...],
    fhir: tuple[APIRouter, ...],
    cds_hooks: tuple[APIRouter, ...],
    facade: tuple[APIRouter, ...],
    read: APIRouter,
) -> tuple[APIRouter, ...]:
    """Which routers the authentication check belongs on, for one posture and one scope.

    `naming` is in the set under both scopes, which is the one thing `/whoami` needs to be worth
    asking: a route that answered "nobody" where `write` leaves the reads open would turn a wrong
    password into a shrug, and the address exists to give a verdict on a credential.
    """
    if auth is ServeAuth.NONE:
        return ()
    if auth_scope is ServeAuthScope.ALL:
        return (*(router for router in fhir if router is not conformance), *cds_hooks, *facade, read)
    return (*naming, submissions) if capture else naming


def build_facade_api(
    routers: ServeRouters, *, authentication: Any, state: Any = None, mount_path: str = FACADE_MOUNT_PATH
) -> FastAPI:
    """Build this facade's own API as an application of its own, so it can publish its own contract.

    A sub-application rather than a prefix on a router, and the OpenAPI document is the whole reason:
    the base URL's application publishes none - its contract is the CapabilityStatement, and an
    OpenAPI document of the FHIR surface could only describe two catch-alls over a path variable - so
    the facade API gets an application whose document describes exactly the operations in it.

    `mount_path` is where the mounting application puts it, and it is stated in the document's own
    `servers` rather than left for a reader to work out: the paths in an OpenAPI document are
    relative to the server it names, so a document that named none would describe `/spool` at a URL
    this process answers nothing at.

    `state` is the state object the mounting application holds its runtime on. A mounted application
    is what `request.app` resolves to inside it, so the two share one `State` rather than copying
    values between them: `attach_serve_runtime` writes the runtime once, and both applications read
    the same four names back. Passing None leaves the sub-application its own state, which is what a
    caller mounting these routers without this package's factory arranges for itself.

    The error handlers are registered here as well as on the mounting application. Starlette's
    exception middleware is per-application, so an exception raised inside this mount never reaches
    the handlers outside it - and a `NotFoundError` that answered a bare 500 instead of an
    `OperationOutcome` would make refusals under this mount a different shape from refusals beside it.

    THE CONTRACT ITSELF IS OPEN IN EVERY SCOPE. `/openapi.json` and the documentation page are this
    application's own routes rather than routes on any router in `guarded`, so no posture puts a
    credential in front of them - deliberately, and for `/metadata`'s reason: a description of how to
    call a server says nothing a caller could not learn by calling it, and one nobody may read is one
    nobody can meet.

    THE DOCUMENTATION PAGE IS THE ONE THING HERE THAT REACHES ANOTHER ORIGIN. It is FastAPI's Swagger
    UI, whose script and stylesheet come from a public CDN, so a machine with no route out serves the
    page and renders nothing in it. The document itself is this server's own bytes and needs nobody:
    a deployment behind a closed network reads `/openapi.json` and opens it in whatever it already
    has. `/docs` is the convenience, not the contract.
    """
    from dhis2w_fhir_serve.errors import register_error_handlers
    from dhis2w_fhir_serve.runtime import server_version

    api = FastAPI(
        title=FACADE_API_TITLE,
        summary=FACADE_API_SUMMARY,
        description=FACADE_API_DESCRIPTION,
        version=server_version(),
        openapi_tags=FACADE_API_TAGS,
        servers=[{"url": mount_path, "description": "This facade's own API, beside the FHIR base URL."}],
        openapi_url=FACADE_OPENAPI_PATH,
        docs_url=FACADE_DOCUMENTATION_PATH,
        redoc_url=None,
        generate_unique_id_function=facade_operation_id,
    )
    if state is not None:
        api.state = state
    register_error_handlers(api)
    for router in routers.facade:
        guard = [Depends(authentication)] if routers.is_guarded(router) else []
        negotiation = [Depends(require_json_is_acceptable)] if routers.is_negotiated(router) else []
        api.include_router(router, dependencies=[*guard, *negotiation])
    describe_each_read_once(api)
    return api


def api_routes(app: FastAPI) -> tuple[APIRoute, ...]:
    """Every API route one application answers, in table order, however deeply a router nests them.

    `include_router` does not flatten what it includes: an application's own `routes` holds one
    object per inclusion and the routes are inside it, and a mounted application holds its own table
    the same way. Anything reading a route table - a test comparing two applications, a debug dump -
    has to walk through those rather than over them, so the walk is written once here. The paths are
    each router's own, so a route under a mount reads as the mount serves it rather than as the base
    URL does.
    """
    found: list[APIRoute] = []
    _collect_api_routes(app.routes, found)
    return tuple(found)


def _collect_api_routes(routes: Any, found: list[APIRoute]) -> None:
    """Append every `APIRoute` in one route list, descending into anything holding routes of its own."""
    for route in routes:
        if isinstance(route, APIRoute):
            found.append(route)
            continue
        included = getattr(route, "original_router", None)
        nested = getattr(route, "routes", None) if included is None else included.routes
        if nested is not None:
            _collect_api_routes(nested, found)


def facade_operation_id(route: APIRoute) -> str:
    """What one operation is called in the facade API's document, which is the handler's own name.

    FastAPI's default composes the name, the path, and the method into one identifier, which reads as
    machinery in a document a person opens. The handler names here are already the sentence - a
    generated client calling `read_spool()` needs no more.
    """
    return route.name


def describe_each_read_once(api: FastAPI) -> None:
    """Render the facade API's document now, describing every read once rather than twice.

    `accept_head_wherever_get_is_served` gives every GET route a HEAD twin so a liveness probe is
    answered, and FastAPI describes a route once per method - so a document built over those routes
    carries a HEAD twin of every read: the same operation, under the same identifier, said again with
    no body. HEAD is GET without the body and there is nothing about it a reader of a contract needs,
    so the twins come out of the document here.

    That is also the whole of what the duplicate-identifier warning below is about, which is why it is
    silenced rather than worked around: FastAPI reaches the same operation identifier twice because
    the two methods are one operation, and dropping the twin is this function agreeing with it.

    Rendered while the application is being built rather than on the first request that asks for it,
    so the document a caller reads is settled before anything can read it.
    """
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="Duplicate Operation ID", category=UserWarning)
        document = api.openapi()
    paths: dict[str, dict[str, Any]] = document.get("paths", {})
    for operations in paths.values():
        operations.pop("head", None)
    api.openapi_schema = document


def register_routes(
    app: FastAPI,
    serve_ui: bool = False,
    capture: bool = True,
    auth: ServeAuth = ServeAuth.NONE,
    auth_scope: ServeAuthScope = ServeAuthScope.WRITE,
    authentication: Any = None,
) -> None:
    """Mount the facade's routes: FHIR at the base URL, this facade's own API at `/facade`, the shell last.

    The UI mounts are this function's own and are not in `ServeRouters`: they are `StaticFiles`
    rather than routers, and their order requirement only makes sense inside this facade's own route
    table. See `dhis2w_fhir_serve.ui`.

    `authentication` is the dependency the guarded routers carry, and defaults to
    `dhis2w_fhir_serve.auth.require_authenticated`. An application that already knows who its callers
    are passes its own callable here - the set it is mounted over is `ServeRouters.guarded`, which is
    a value that application can read for itself.

    The check is mounted AHEAD of the content negotiation on the FHIR routers it shares a mount with:
    a caller this server will not answer learns that before it learns which media types the server
    answers in.
    """
    from dhis2w_fhir_serve.auth import require_authenticated
    from dhis2w_fhir_serve.ui import mount_ui_assets, mount_ui_shell

    check = require_authenticated if authentication is None else authentication
    routers = serve_routers(capture=capture, serve_ui=serve_ui, auth=auth, auth_scope=auth_scope)
    if serve_ui:
        mount_ui_assets(app)
    for router in routers.in_mount_order():
        accept_head_wherever_get_is_served(router)
    for router in routers.fhir:
        guard = [Depends(check)] if routers.is_guarded(router) else []
        app.include_router(router, dependencies=[*guard, Depends(require_json_is_acceptable)])
    for router in routers.cds_hooks:
        app.include_router(router, dependencies=[Depends(check)] if routers.is_guarded(router) else [])
    app.mount(FACADE_MOUNT_PATH, build_facade_api(routers, authentication=check, state=app.state))
    # The read catch-alls claim every path of their shape, so they mount after every fixed path -
    # the `/facade` mount above included, since `/facade` is a one-segment path like any other.
    read_guard = [Depends(check)] if routers.is_guarded(routers.read) else []
    app.include_router(routers.read, dependencies=[*read_guard, Depends(require_json_is_acceptable)])
    if serve_ui:
        mount_ui_shell(app)


def accept_head_wherever_get_is_served(router: APIRouter) -> None:
    """Answer HEAD on every GET route - Starlette runs the endpoint and the server withholds the body."""
    for route in router.routes:
        if isinstance(route, APIRoute) and route.methods and "GET" in route.methods:
            route.methods.add("HEAD")
