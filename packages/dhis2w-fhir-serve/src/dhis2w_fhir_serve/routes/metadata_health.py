"""`GET /facade/metadata-health` - what is not right about the DHIS2 metadata this run publishes from.

WHAT IT ANSWERS. The `d2w fhir validate` analysis, run over the connection this process already
holds, plus one analysis the command does not do: how far the selection is translated. A name the
IG publisher cannot survive, a code no FHIR system will take, an object with no code at all, and a
locale somebody stopped translating into halfway through are four different problems with one
audience - whoever maintains the instance - so they are one page rather than four.

WHY IT IS NOT FHIR. There is no FHIR shape for "this DHIS2 name has a `<` in it". An OperationOutcome
is what a server answers a request with, not a report about somebody else's metadata, and the
translation coverage has no resource at all. So this is `/spool`'s shape for `/spool`'s reasons, at
`/spool`'s address: plain `application/json`, Pydantic models rather than a Bundle, served under the
facade API's own mount rather than at the FHIR base. `dhis2w_fhir_serve.routes.spool` argues that
choice in full.

The name carries a hyphen and the address carries the mount, so nothing about it can be mistaken for
`/metadata` - which is the FHIR base's CapabilityStatement and a different document about a different
thing.

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

#: Where the report is served from, under the facade API's mount.
METADATA_HEALTH_PATH = "/metadata-health"

#: What this operation is grouped under in the facade API's document.
METADATA_HEALTH_TAG = "Metadata health"

router = APIRouter()


@router.get(
    METADATA_HEALTH_PATH,
    tags=[METADATA_HEALTH_TAG],
    summary="Grade the DHIS2 metadata behind this run",
    description=(
        "The `d2w fhir validate` analysis over the connection this process already holds, plus how "
        "far the selection is translated: a name the IG publisher cannot survive, a code no FHIR "
        "system will take, an object with no code at all, and a locale somebody stopped translating "
        "into halfway.\n\n"
        "A run serving a compiled guide off disk answers 200 with `available` false and the sentence "
        "saying there is no instance to grade - a state rather than a failure, so a screen renders "
        "this server's own words instead of inventing them off a 4xx. Reporting only: nothing here "
        "changes anything in DHIS2."
    ),
    response_description=(
        "What the instance holds that the guide cannot carry cleanly, or why there is nothing to grade."
    ),
)
async def read_metadata_health_report(request: Request) -> MetadataHealth:
    """Answer what the DHIS2 instance behind this run holds that the guide cannot carry cleanly."""
    client = live_client(request)
    if client is None:
        return compiled_run_health()
    return await read_metadata_health(client, serve_context(request).project.config.generate)
