"""`GET /metadata-health` - what is not right about the DHIS2 metadata this run publishes from.

WHAT IT ANSWERS. The `d2w fhir validate` analysis, run over the connection this process already
holds, plus one analysis the command does not do: how far the selection is translated. A name the
IG publisher cannot survive, a code no FHIR system will take, an object with no code at all, and a
locale somebody stopped translating into halfway through are four different problems with one
audience - whoever maintains the instance - so they are one page rather than four.

WHY IT IS NOT FHIR. There is no FHIR shape for "this DHIS2 name has a `<` in it". An OperationOutcome
is what a server answers a request with, not a report about somebody else's metadata, and the
translation coverage has no resource at all. So this is `/spool`'s shape for `/spool`'s reasons:
plain `application/json`, Pydantic models rather than a Bundle, mounted with the other fixed paths
ahead of the read catch-alls. `dhis2w_fhir_serve.routes.spool` argues that choice in full.

The path carries a hyphen, which no FHIR resource type does and no other route here claims - a
resource type is PascalCase and every facade path beside this one is a single lowercase word - so
`/metadata-health` shadows neither `/metadata` nor a served type.

LIVE RUNS ONLY, AND A COMPILED RUN SAYS SO IN THE BODY. Grading metadata needs metadata to grade,
and a compiled guide is a directory of resources with no instance behind it. The register routes
refuse that state as an OperationOutcome because a FHIR client asked them a FHIR question; this
route answers a body carrying `available: false` and the sentence a screen renders, because "there
is nothing here to check and here is why" is a state rather than a failure - and a page that had to
read it off a 4xx would end up inventing the sentence itself.

REPORTING ONLY. The route reads. Changing a name, a code, or a translation in DHIS2 from a finding
is the next slice, and the FHIR roadmap's near-term section is where it is stated.
"""

from __future__ import annotations

from fastapi import APIRouter
from starlette.requests import Request

from dhis2w_fhir_serve.health import MetadataHealth, compiled_run_health, read_metadata_health
from dhis2w_fhir_serve.routes.context import live_client, serve_context

#: Where the report is served from. Lowercase and hyphenated, so no FHIR resource type can collide.
METADATA_HEALTH_PATH = "/metadata-health"

router = APIRouter()


@router.get(METADATA_HEALTH_PATH)
async def read_metadata_health_report(request: Request) -> MetadataHealth:
    """Answer what the DHIS2 instance behind this run holds that the guide cannot carry cleanly."""
    client = live_client(request)
    if client is None:
        return compiled_run_health()
    return await read_metadata_health(client, serve_context(request).project.config.generate)
