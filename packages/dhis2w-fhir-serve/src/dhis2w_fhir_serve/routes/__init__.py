"""Route assembly: every router the facade mounts, in the order the router table has to see them.

`/{resource_type}` and `/{resource_type}/{resource_id}` match any path of their shape, so the
read router mounts last and every router carrying a fixed path mounts ahead of it. `/metadata`,
`/spool`, and `/uiconfig` are one-segment fixed paths and all sit in that group, as does the
`/tracked-entities/{uid}/enrollments` listing; FHIR resource types are PascalCase, so a lowercase
segment can never be one the read router should have claimed.

The register's resource types are the exception that needs no mount of its own. They are FHIR
resource types answered from the DHIS2 instance rather than from the store, but which types they are
is a property of the guide this process loaded, so the read router dispatches to
`dhis2w_fhir_serve.routes.register` at request time instead of a router claiming paths that could
only be named once the store was open.

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

Which routers are FHIR is decided here too, once, by the list a router is mounted from. The FHIR
routers carry the `Accept` negotiation as a mount-time dependency - a client that takes no JSON is
refused before any of them runs - and the three that answer plain JSON about this facade rather
than FHIR resources out of it do not. See `dhis2w_fhir_serve.routes.negotiation`.
"""

from fastapi import APIRouter, Depends, FastAPI
from fastapi.routing import APIRoute

__all__ = ["register_routes"]


def register_routes(app: FastAPI, serve_ui: bool = False) -> None:
    """Mount the facade's routes: fixed paths first, the read catch-alls next, the UI shell last.

    The routers are imported here rather than at module scope: a route module reaches the serve
    context through `dhis2w_fhir_serve.routes.context`, which imports this package, so importing
    the route modules from this package's body would close the cycle.
    """
    from dhis2w_fhir_serve.metadata import router as metadata_router
    from dhis2w_fhir_serve.routes.capture import router as capture_router
    from dhis2w_fhir_serve.routes.enrollments import router as enrollments_router
    from dhis2w_fhir_serve.routes.generate import router as generate_router
    from dhis2w_fhir_serve.routes.negotiation import require_json_is_acceptable
    from dhis2w_fhir_serve.routes.read import router as read_router
    from dhis2w_fhir_serve.routes.root import build_root_router
    from dhis2w_fhir_serve.routes.spool import router as spool_router
    from dhis2w_fhir_serve.routes.translate import router as translate_router
    from dhis2w_fhir_serve.routes.uiconfig import router as ui_config_router
    from dhis2w_fhir_serve.ui import mount_ui_assets, mount_ui_shell

    if serve_ui:
        mount_ui_assets(app)
    fhir_routers: tuple[APIRouter, ...] = (
        metadata_router,
        capture_router,
        build_root_router(serve_ui),
        translate_router,
        generate_router,
    )
    facade_routers: tuple[APIRouter, ...] = (spool_router, ui_config_router, enrollments_router)
    for router in (*fhir_routers, *facade_routers, read_router):
        _accept_head_wherever_get_is_served(router)
    for router in fhir_routers:
        app.include_router(router, dependencies=[Depends(require_json_is_acceptable)])
    for router in facade_routers:
        app.include_router(router)
    # The read catch-alls claim every path of their shape, so they mount after every fixed path -
    # which is why the one FHIR router that could not join the group above is named on its own.
    app.include_router(read_router, dependencies=[Depends(require_json_is_acceptable)])
    if serve_ui:
        mount_ui_shell(app)


def _accept_head_wherever_get_is_served(router: APIRouter) -> None:
    """Answer HEAD on every GET route - Starlette runs the endpoint and the server withholds the body."""
    for route in router.routes:
        if isinstance(route, APIRoute) and route.methods and "GET" in route.methods:
            route.methods.add("HEAD")
