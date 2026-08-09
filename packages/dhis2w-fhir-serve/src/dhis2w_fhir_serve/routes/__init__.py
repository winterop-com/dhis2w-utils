"""Route assembly: every router the facade mounts, in the order the router table has to see them.

`/{resource_type}` and `/{resource_type}/{resource_id}` match any path of their shape, so the
read router mounts last and every router carrying a fixed path mounts ahead of it. `/metadata` and
`/spool` are both one-segment fixed paths and both sit in that group; FHIR resource types are
PascalCase, so a lowercase segment can never be one the read router should have claimed.

The capture UI sits on both sides of that line, which is why `serve_ui` is an argument here rather
than something the UI module could arrange for itself. Its asset tree is a fixed path and mounts
with the other fixed paths, ahead of the catch-alls that would otherwise claim
`/assets/<file>`; its shell is a catch-all of its own and mounts after everything. See
`dhis2w_fhir_serve.ui` for what each mount is and why the split is not optional.
"""

from fastapi import FastAPI

__all__ = ["register_routes"]


def register_routes(app: FastAPI, serve_ui: bool = False) -> None:
    """Mount the facade's routes: fixed paths first, the read catch-alls next, the UI shell last.

    The routers are imported here rather than at module scope: a route module reaches the serve
    context through `dhis2w_fhir_serve.routes.context`, which imports this package, so importing
    the route modules from this package's body would close the cycle.
    """
    from dhis2w_fhir_serve.metadata import router as metadata_router
    from dhis2w_fhir_serve.routes.capture import router as capture_router
    from dhis2w_fhir_serve.routes.generate import router as generate_router
    from dhis2w_fhir_serve.routes.read import router as read_router
    from dhis2w_fhir_serve.routes.spool import router as spool_router
    from dhis2w_fhir_serve.routes.translate import router as translate_router
    from dhis2w_fhir_serve.ui import mount_ui_assets, mount_ui_shell

    if serve_ui:
        mount_ui_assets(app)
    app.include_router(metadata_router)
    app.include_router(capture_router)
    app.include_router(spool_router)
    app.include_router(translate_router)
    app.include_router(generate_router)
    app.include_router(read_router)
    if serve_ui:
        mount_ui_shell(app)
