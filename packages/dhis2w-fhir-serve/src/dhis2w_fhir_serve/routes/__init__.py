"""Route assembly: every router the facade mounts, in the order the router table has to see them.

`/{resource_type}` and `/{resource_type}/{resource_id}` match any path of their shape, so the
read router mounts last and every router carrying a fixed path mounts ahead of it. `/metadata`,
`/spool`, `/uiconfig`, `/whoami`, `/evaluate`, and `/cds-services` are one-segment fixed paths and
all sit in that group, as do the deeper fixed paths under them - the
`/tracked-entities/{uid}/enrollments` listing and the `/tracked-entities/{uid}/events` record beside
it, `/terminology/validate-code` and
`/terminology/lookup`, and one service's `/cds-services/{id}`. FHIR resource types are PascalCase,
so a lowercase segment can never be one the read router should have claimed, whichever depth it
sits at.

`$evaluate` is a one-segment fixed path too, and a FHIR one: it is the system-level operation
answering an evaluation as a `Parameters` resource, so it mounts with the FHIR group while
`/evaluate` beside it answers this facade's own JSON. A segment beginning with `$` can shadow no
resource type either, and both addresses run the same evaluation over the same three contexts -
`dhis2w_fhir_serve.routes.evaluate_operation` argues the split.

`$summary` is the one FHIR path whose fixed segment sits at the END rather than the start, and it
mounts in that same group for exactly that reason: `/{ResourceType}/$summary` is the shape
`/{resource_type}/{resource_id}` also matches, so a summary router mounted after the read catch-alls
would never be reached and a client asking for one would be told there is no resource with the id
`$summary`. `dhis2w_fhir_serve.routes.summary` is what it answers.

The record router is in the FHIR group and the enrollment listing beside it is not, which is the one
distinction that group draws: a record answers a Bundle of the QuestionnaireResponses this guide
publishes, so a client that takes no JSON is refused before it runs, while the listing answers this
facade's own typed JSON. `dhis2w_fhir_serve.routes.history` and `dhis2w_fhir_serve.routes.enrollments`
each argue their own shape.

`/whoami` is the one path a posture adds rather than a scope guards. Every other route is mounted by
every run and the posture only decides which of them carry the check; that one answers who the
caller is, so under `auth = "none"` there is nobody to answer about and the route is absent.
`dhis2w_fhir_serve.routes.whoami` argues it.

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

Which routers are FHIR is decided here too, once, by the field a router is carried in. The FHIR
routers carry the `Accept` negotiation as a mount-time dependency - a client that takes no JSON is
refused before any of them runs - and the three that answer plain JSON about this facade rather
than FHIR resources out of it do not. See `dhis2w_fhir_serve.routes.negotiation`.

WHICH ROUTERS ARE BEHIND THE AUTHENTICATION CHECK is decided here as well, and stated the same way:
`ServeRouters.guarded` names them, and `[serve] auth_scope` is the whole of what decides the set.
`write` guards the state-changing surface, which is one route - `POST /QuestionnaireResponse`, the
create. Every other POST this facade serves writes nothing: `$generate` reads a published form and
answers with a draft, `/evaluate` and `$evaluate` run an expression over what is served, a CDS Hooks call answers
cards, and `POST /` is a refusal on every posture. `all` guards everything except `/metadata`, which
stays open because a client has to be able to read the posture it is expected to meet - a server
that refuses to say how to authenticate to it is one nobody can authenticate to. The UI mounts stay
open under both, for the same reason: a sign-in prompt has to be servable. `/whoami` is guarded under
both scopes, because a credential check that answered without checking would be no check at all.

All of that is stated as data by `serve_routers`, so an application mounting the facade beside its
own routes gets the order, the split, the capture choice, and the guarded set as values rather than
as four paragraphs it has to read. `register_routes` is a loop over what that function answers, and
holds no router knowledge of its own - including the check itself, which is one dependency an
embedding application is free to replace with its own over the same `guarded` set.
"""

from typing import Any

from dhis2w_fhir.config import ServeAuth, ServeAuthScope
from fastapi import APIRouter, Depends, FastAPI
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict

from dhis2w_fhir_serve.routes.negotiation import require_json_is_acceptable

__all__ = ["ServeRouters", "accept_head_wherever_get_is_served", "register_routes", "serve_routers"]


class ServeRouters(BaseModel):
    """Every router one facade mounts, grouped by what mounting it requires.

    The three fields are three different requirements, not a taxonomy: `fhir` must be mounted under
    `Depends(require_json_is_acceptable)`, `facade` must not, and `read` must be mounted after every
    fixed path an application serves - its own included, since `/{resource_type}` claims any
    one-segment path. Every one of them wants the HEAD sweep.
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    fhir: tuple[APIRouter, ...]
    """The FHIR surface: what a client that takes no JSON is refused before, at mount time."""

    facade: tuple[APIRouter, ...]
    """The routers answering plain JSON about this facade rather than FHIR resources out of it.

    Their order is the order an application picking a subset of the facade reads them in: what a
    running server holds (`/spool`, `/uiconfig`), what it answers about the instance
    (`/tracked-entities/{uid}/enrollments`), and what it runs over either (`/evaluate`,
    `/terminology/*`, `/cds-services`).
    """

    read: APIRouter
    """The catch-alls, named on their own because they mount last."""

    guarded: tuple[APIRouter, ...] = ()
    """The routers the authentication check belongs on, as objects also present in the fields above.

    A subset rather than a fourth group: a router is mounted once, in the group whose requirement it
    carries, and this names which of those mounts additionally take `Depends(require_authenticated)`.
    Empty under `[serve] auth = "none"`, which is what makes the default posture cost a request
    nothing. An application that authenticates its callers its own way mounts its own dependency over
    exactly this set.
    """

    def is_guarded(self, router: APIRouter) -> bool:
        """Whether one router carries the authentication check, compared by identity rather than by path."""
        return any(router is guarded for guarded in self.guarded)

    def in_mount_order(self) -> tuple[APIRouter, ...]:
        """Every router, in the order a route table has to see them: fixed paths first, catch-alls last."""
        return (*self.fhir, *self.facade, self.read)


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

    `auth` and `auth_scope` fill `guarded`. `none` guards nothing. `write` guards the create route
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
    from dhis2w_fhir_serve.routes.enrollments import router as enrollments_router
    from dhis2w_fhir_serve.routes.evaluate import router as evaluate_router
    from dhis2w_fhir_serve.routes.evaluate_operation import router as evaluate_operation_router
    from dhis2w_fhir_serve.routes.generate import router as generate_router
    from dhis2w_fhir_serve.routes.history import router as history_router
    from dhis2w_fhir_serve.routes.read import router as read_router
    from dhis2w_fhir_serve.routes.root import build_root_router
    from dhis2w_fhir_serve.routes.spool import router as spool_router
    from dhis2w_fhir_serve.routes.summary import router as summary_router
    from dhis2w_fhir_serve.routes.terminology import router as terminology_router
    from dhis2w_fhir_serve.routes.translate import router as translate_router
    from dhis2w_fhir_serve.routes.uiconfig import router as ui_config_router
    from dhis2w_fhir_serve.routes.whoami import router as whoami_router

    submissions = capture_router if capture else capture_refusal_router
    fhir = (
        metadata_router,
        submissions,
        build_root_router(serve_ui),
        evaluate_operation_router,
        translate_router,
        generate_router,
        history_router,
        summary_router,
    )
    # `/whoami` exists only where a posture does: a server that checks nobody has nobody to name, and
    # it leads the group because it is the one router that answers about the caller rather than about
    # what is served. See `dhis2w_fhir_serve.routes.whoami`.
    naming = (whoami_router,) if auth is not ServeAuth.NONE else ()
    facade = (
        *naming,
        spool_router,
        ui_config_router,
        enrollments_router,
        evaluate_router,
        terminology_router,
        cds_router,
    )
    return ServeRouters(
        fhir=fhir,
        facade=facade,
        read=read_router,
        guarded=_guarded_routers(
            auth=auth,
            auth_scope=auth_scope,
            capture=capture,
            submissions=submissions,
            conformance=metadata_router,
            naming=naming,
            fhir=fhir,
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
        return (*(router for router in fhir if router is not conformance), *facade, read)
    return (*naming, submissions) if capture else naming


def register_routes(
    app: FastAPI,
    serve_ui: bool = False,
    capture: bool = True,
    auth: ServeAuth = ServeAuth.NONE,
    auth_scope: ServeAuthScope = ServeAuthScope.WRITE,
    authentication: Any = None,
) -> None:
    """Mount the facade's routes: fixed paths first, the read catch-alls next, the UI shell last.

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
    for router in routers.facade:
        app.include_router(router, dependencies=[Depends(check)] if routers.is_guarded(router) else [])
    # The read catch-alls claim every path of their shape, so they mount after every fixed path -
    # which is why the one FHIR router that could not join the group above is mounted on its own.
    read_guard = [Depends(check)] if routers.is_guarded(routers.read) else []
    app.include_router(routers.read, dependencies=[*read_guard, Depends(require_json_is_acceptable)])
    if serve_ui:
        mount_ui_shell(app)


def accept_head_wherever_get_is_served(router: APIRouter) -> None:
    """Answer HEAD on every GET route - Starlette runs the endpoint and the server withholds the body."""
    for route in router.routes:
        if isinstance(route, APIRoute) and route.methods and "GET" in route.methods:
            route.methods.add("HEAD")
