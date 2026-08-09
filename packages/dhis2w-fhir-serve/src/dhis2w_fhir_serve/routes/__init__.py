"""Route assembly: every router the facade mounts, in the order the router table has to see them.

`/{resource_type}` and `/{resource_type}/{resource_id}` match any path of their shape, so the
read router mounts last and every router carrying a fixed path mounts ahead of it.
"""

from fastapi import FastAPI

__all__ = ["register_routes"]


def register_routes(app: FastAPI) -> None:
    """Mount the facade's routers: fixed paths first, the read catch-alls last.

    The routers are imported here rather than at module scope: a route module reaches the serve
    context through `dhis2w_fhir_serve.routes.context`, which imports this package, so importing
    the route modules from this package's body would close the cycle.
    """
    from dhis2w_fhir_serve.metadata import router as metadata_router
    from dhis2w_fhir_serve.routes.capture import router as capture_router
    from dhis2w_fhir_serve.routes.generate import router as generate_router
    from dhis2w_fhir_serve.routes.read import router as read_router
    from dhis2w_fhir_serve.routes.translate import router as translate_router

    app.include_router(metadata_router)
    app.include_router(capture_router)
    app.include_router(translate_router)
    app.include_router(generate_router)
    app.include_router(read_router)
