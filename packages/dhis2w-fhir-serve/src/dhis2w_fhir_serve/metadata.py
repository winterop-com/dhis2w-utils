"""`GET /metadata` - the conformance endpoint, answered from a body built once at startup.

The statement describes the store and the spool as the process found them, so it is built in the
lifespan and served verbatim from then on. Rebuilding it per request would re-read nothing new:
the compiled store is fixed for the life of the process, and the counts it reports are stated as
what the server started with.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import APIRouter
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from dhis2w_fhir_serve.capability import build_server_capability
from dhis2w_fhir_serve.errors import FHIR_JSON_MEDIA_TYPE
from dhis2w_fhir_serve.routes.context import serve_context

if TYPE_CHECKING:
    from dhis2w_fhir.config import FhirProject

    from dhis2w_fhir_serve.settings import ServeSettings
    from dhis2w_fhir_serve.store import StoreSummary

router = APIRouter()


def build_metadata_body(
    project: FhirProject,
    store_summary: StoreSummary,
    spool_count: int,
    settings: ServeSettings,
    server_version: str,
) -> dict[str, Any]:
    """Render the server's CapabilityStatement as the JSON body `/metadata` answers with.

    The dict is the wire document itself - the same HTTP-boundary escape hatch `StoreEntry.body`
    documents - held pre-rendered so the endpoint serialises nothing per request.
    """
    capability = build_server_capability(
        project=project,
        store_summary=store_summary,
        spool_count=spool_count,
        settings=settings,
        server_version=server_version,
    )
    return capability.model_dump(mode="json", exclude_none=True, by_alias=True)


@router.get("/metadata")
async def read_metadata(request: Request) -> Response:
    """Answer with the CapabilityStatement this server started with."""
    return JSONResponse(content=serve_context(request).capability_body, media_type=FHIR_JSON_MEDIA_TYPE)
