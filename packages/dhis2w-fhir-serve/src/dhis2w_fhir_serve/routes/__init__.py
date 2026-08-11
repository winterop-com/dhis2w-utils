"""Route assembly: every router the facade mounts, in the order the router table has to see them.

`/{resource_type}` and `/{resource_type}/{resource_id}` match any path of their shape, so the
read router mounts last and every router carrying a fixed path mounts ahead of it. `/metadata`,
`/spool`, and `/uiconfig` are one-segment fixed paths and all sit in that group, as does the
`/patients/{uid}/enrollments` listing; FHIR resource types are PascalCase, so a lowercase segment
can never be one the read router should have claimed.

`/Patient` is the one PascalCase path in that group. It is a FHIR resource type, and it is answered
from the DHIS2 instance rather than from the store the read router holds, so it mounts ahead of the
catch-alls that would otherwise answer it out of a store that has never held a Patient.

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
"""

from fastapi import APIRouter, FastAPI
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
    from dhis2w_fhir_serve.routes.patient import router as patient_router
    from dhis2w_fhir_serve.routes.read import router as read_router
    from dhis2w_fhir_serve.routes.spool import router as spool_router
    from dhis2w_fhir_serve.routes.translate import router as translate_router
    from dhis2w_fhir_serve.routes.uiconfig import router as ui_config_router
    from dhis2w_fhir_serve.ui import mount_ui_assets, mount_ui_shell

    if serve_ui:
        mount_ui_assets(app)
    for router in (
        metadata_router,
        capture_router,
        spool_router,
        ui_config_router,
        enrollments_router,
        translate_router,
        generate_router,
        patient_router,
        read_router,
    ):
        _accept_head_wherever_get_is_served(router)
        app.include_router(router)
    if serve_ui:
        mount_ui_shell(app)


def _accept_head_wherever_get_is_served(router: APIRouter) -> None:
    """Answer HEAD on every GET route - Starlette runs the endpoint and the server withholds the body."""
    for route in router.routes:
        if isinstance(route, APIRoute) and route.methods and "GET" in route.methods:
            route.methods.add("HEAD")
