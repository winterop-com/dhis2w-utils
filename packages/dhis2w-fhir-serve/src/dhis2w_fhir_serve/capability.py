"""The running server's CapabilityStatement: what this process actually serves, right now.

The IG publishes a `kind #requirements` statement declaring what any DHIS2 capture server has
to support. This one is its `kind #instance` counterpart: it `instantiates` the IG's statement
and then narrows it to this installation - the profiles this project generated, and the read
types this store actually holds, so a client that reads `/metadata` never sees a resource type
advertised that the store cannot answer for.

The QuestionnaireResponse entry is the one that says what the facade is: responses are received
and stored as receipts. Reading one back returns the submission as it arrived, never a live view
of what DHIS2 now holds.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from dhis2w_fhir.foundation import CAPTURE_SERVER_READ_RESOURCE_TYPES, build_response_profile_declarations
from dhis2w_fhir.foundation.schemas import FoundationNaming
from dhis2w_fhir.r4 import (
    CapabilityStatement,
    CapabilityStatementImplementation,
    CapabilityStatementInteraction,
    CapabilityStatementResource,
    CapabilityStatementRest,
    CapabilityStatementSearchParam,
    CapabilityStatementSoftware,
)

from dhis2w_fhir_serve.spool import current_instant

if TYPE_CHECKING:
    from dhis2w_fhir.config import FhirProject

    from dhis2w_fhir_serve.settings import ServeSettings
    from dhis2w_fhir_serve.store import StoreSummary

#: The resource type the facade receives captures on, alongside the read types it serves.
QUESTIONNAIRE_RESPONSE_RESOURCE_TYPE = "QuestionnaireResponse"

#: The name the software element reports, matching the command that runs it.
SOFTWARE_NAME = "d2w fhir serve"

#: What the QuestionnaireResponse entry states about the resources it holds.
RESPONSE_DOCUMENTATION = "One response per request; stored responses are receipts of what was submitted"

_REST_DOCUMENTATION = (
    "One QuestionnaireResponse per request on create; every other interaction is a read over the "
    "resources this project publishes."
)


def build_server_capability(
    project: FhirProject,
    store_summary: StoreSummary,
    spool_count: int,
    settings: ServeSettings,
    server_version: str,
) -> CapabilityStatement:
    """State what this process serves: the capture contract, plus the read types the store holds."""
    canonical = project.config.ig.canonical
    names = FoundationNaming.from_naming(project.config.generate.naming)
    store_mode = "live" if settings.live else "compiled"
    resources = [
        _response_resource(project, canonical),
        *(
            _read_resource(resource_type, project.config.generate.identifier_system_base)
            for resource_type in CAPTURE_SERVER_READ_RESOURCE_TYPES
            if resource_type in store_summary.counts_by_type
        ),
    ]
    return CapabilityStatement(
        status="active",
        date=current_instant(),
        kind="instance",
        description=(
            f"{project.config.ig.title} served as a FHIR capture facade: {store_summary.total} resources "
            f"across {len(store_summary.counts_by_type)} types, and {spool_count} stored responses at startup."
        ),
        instantiates=[f"{canonical}/CapabilityStatement/{names.capture_server_id}"],
        software=CapabilityStatementSoftware(name=SOFTWARE_NAME, version=server_version),
        implementation=CapabilityStatementImplementation(
            description=(
                f"DHIS2 FHIR capture facade ({store_mode} store); stored QuestionnaireResponses are "
                "submissions as received - receipts, not a live view of DHIS2 data"
            )
        ),
        fhirVersion="4.0.1",
        format=["json"],
        rest=[
            CapabilityStatementRest(
                mode="server",
                documentation=_REST_DOCUMENTATION,
                resource=resources,
            )
        ],
    )


def _response_resource(project: FhirProject, canonical: str) -> CapabilityStatementResource:
    """Declare the capture type: create, read, search, and the response profiles this project generated."""
    declarations = build_response_profile_declarations(project.config.generate)
    return CapabilityStatementResource(
        type=QUESTIONNAIRE_RESPONSE_RESOURCE_TYPE,
        supportedProfile=[f"{canonical}/StructureDefinition/{declaration.profile_id}" for declaration in declarations],
        documentation=RESPONSE_DOCUMENTATION,
        interaction=[
            CapabilityStatementInteraction(code="create"),
            CapabilityStatementInteraction(code="read"),
            CapabilityStatementInteraction(code="search-type"),
        ],
        searchParam=[
            CapabilityStatementSearchParam(name="_id", type="token"),
            CapabilityStatementSearchParam(
                name="questionnaire",
                type="reference",
                documentation="The canonical of the Questionnaire the stored responses answered.",
            ),
        ],
    )


def _read_resource(resource_type: str, identifier_system_base: str) -> CapabilityStatementResource:
    """Declare one read type the store holds, with the three search parameters the facade answers."""
    return CapabilityStatementResource(
        type=resource_type,
        interaction=[
            CapabilityStatementInteraction(code="read"),
            CapabilityStatementInteraction(code="search-type"),
        ],
        searchParam=[
            CapabilityStatementSearchParam(name="_id", type="token"),
            CapabilityStatementSearchParam(name="url", type="uri"),
            CapabilityStatementSearchParam(
                name="identifier",
                type="token",
                documentation=(
                    "The DHIS2 identifiers the resource carries. A system-qualified token groups a form's "
                    f"artifacts by the DHIS2 object they came from - `identifier={identifier_system_base}"
                    "/id/program|<uid>` selects everything generated from one program."
                ),
            ),
        ],
    )
