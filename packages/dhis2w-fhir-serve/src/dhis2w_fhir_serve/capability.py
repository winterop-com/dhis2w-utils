"""The running server's CapabilityStatement: what this process actually serves, right now.

The IG publishes a `kind #requirements` statement declaring what any DHIS2 capture server has
to support. This one is its `kind #instance` counterpart: it `instantiates` the IG's statement
and then narrows it to this installation - the profiles this project generated, and the read
types this store actually holds, so a client that reads `/metadata` never sees a resource type
advertised that the store cannot answer for.

The QuestionnaireResponse entry is the one that says what the facade is: responses are received
and stored as receipts. Reading one back returns the submission as it arrived, never a live view
of what DHIS2 now holds.

The read set is the capture contract's read types plus ConceptMap. The IG's `kind #requirements`
statement names the resources a capture *client* resolves a form from, and ConceptMap is not one of
them - it is what a forwarder reads a concept back into DHIS2 identifiers with. This installation
serves it all the same, because the maps are published IG artifacts sitting in the same store as
everything else, and an instance is free to support more than the statement it instantiates.

`$translate` follows the same rule as the read types: it is declared only when the store actually
holds ConceptMaps. It is declared on `rest` rather than on the ConceptMap entry because R4 defines
it as a type-level operation, which is where `rest.operation` belongs.

`$generate` is declared the other way round, on the Questionnaire resource entry, because it is an
instance-level operation on a resource type this server does read - and it is declared only when the
store holds Questionnaires, for the same reason `$translate` waits for ConceptMaps. Its definition is
the OperationDefinition the project's own IG publishes, not an HL7 one: `$generate` is a custom
operation, deliberately not SDC's `$populate`.

Patient is the one entry that is not about the store at all. It is answered from the DHIS2 instance
per request, so it is declared only by a process that has one - `--live`, over a project that
publishes a registration form and therefore names a tracked entity type. A compiled run declares no
Patient, which is the same refusal `GET /Patient` gives, stated before the request rather than
after it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from dhis2w_fhir.foundation import (
    CAPTURE_SERVER_READ_RESOURCE_TYPES,
    GENERATE_OPERATION_CODE,
    build_captured_response_profile_declarations,
)
from dhis2w_fhir.foundation.schemas import FoundationNaming
from dhis2w_fhir.r4 import (
    CapabilityStatement,
    CapabilityStatementImplementation,
    CapabilityStatementInteraction,
    CapabilityStatementOperation,
    CapabilityStatementResource,
    CapabilityStatementRest,
    CapabilityStatementSearchParam,
    CapabilityStatementSoftware,
)

from dhis2w_fhir_serve.spool import current_instant
from dhis2w_fhir_serve.store import CONCEPT_MAP_RESOURCE_TYPE

if TYPE_CHECKING:
    from dhis2w_fhir.config import FhirProject

    from dhis2w_fhir_serve.patients.index import PatientIndex
    from dhis2w_fhir_serve.settings import ServeSettings
    from dhis2w_fhir_serve.store import StoreSummary

#: The resource type the facade receives captures on, alongside the read types it serves.
QUESTIONNAIRE_RESPONSE_RESOURCE_TYPE = "QuestionnaireResponse"

#: Every type the facade answers a read and a search for: the capture contract's, plus ConceptMap.
SERVED_READ_RESOURCE_TYPES = (*CAPTURE_SERVER_READ_RESOURCE_TYPES, CONCEPT_MAP_RESOURCE_TYPE)

#: The name the software element reports, matching the command that runs it.
SOFTWARE_NAME = "d2w fhir serve"

#: The R4 operation the facade answers over its ConceptMaps, and the definition it conforms to.
TRANSLATE_OPERATION_NAME = "translate"
TRANSLATE_OPERATION_DEFINITION = "http://hl7.org/fhir/OperationDefinition/ConceptMap-translate"

#: What the translate operation states about the mappings it answers from.
TRANSLATE_DOCUMENTATION = (
    "Translate a generated concept code into the DHIS2 option UID and option code the "
    "published ConceptMaps map it onto."
)

#: The resource type `$generate` is answered on, and what the operation states about its output.
QUESTIONNAIRE_RESOURCE_TYPE = "Questionnaire"
GENERATE_DOCUMENTATION = (
    "Generate a synthetic QuestionnaireResponse against one served form, optionally from a named "
    "`seed` for a reproducible answer. The generated response is postable to this server's own "
    "QuestionnaireResponse endpoint unchanged."
)

#: The resource type answered from the DHIS2 instance rather than from the store, and what it states.
PATIENT_RESOURCE_TYPE = "Patient"
PATIENT_DOCUMENTATION = (
    "One DHIS2 tracked entity per Patient, read from the instance at request time. Identity only - "
    "the tracked entity UID, the values of the attributes DHIS2 declares unique, and the rest of the "
    "attribute values as extensions. No name, gender, or birth date: DHIS2 states no mapping for them."
)

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
    patient_index: PatientIndex,
    server_version: str,
) -> CapabilityStatement:
    """State what this process serves: the capture contract, the read types the store holds, and live Patient."""
    canonical = project.config.ig.canonical
    names = FoundationNaming.from_naming(project.config.generate.naming)
    store_mode = "live" if settings.live else "compiled"
    resources = [
        _response_resource(project, canonical),
        *(
            _read_resource(resource_type, project.config.generate.identifier_system_base, canonical, names)
            for resource_type in SERVED_READ_RESOURCE_TYPES
            if resource_type in store_summary.counts_by_type
        ),
        *_patient_resource(settings, patient_index),
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
                operation=_operations(store_summary),
            )
        ],
    )


def _patient_resource(settings: ServeSettings, patient_index: PatientIndex) -> list[CapabilityStatementResource]:
    """Declare Patient only when this process can actually answer for one.

    Two conditions, and both are properties of how the process was started rather than of the IG:
    the store has to be live, because a Patient is read from the DHIS2 instance and there is no
    instance behind a compiled guide, and the project has to publish a registration form, because
    the tracked entity type it names is what a DHIS2 search must be given. A statement that declared
    Patient anyway would advertise an interaction every request to it refuses.
    """
    if not settings.live or not patient_index.serves_patients():
        return []
    return [
        CapabilityStatementResource(
            type=PATIENT_RESOURCE_TYPE,
            documentation=PATIENT_DOCUMENTATION,
            interaction=[
                CapabilityStatementInteraction(code="read"),
                CapabilityStatementInteraction(code="search-type"),
            ],
            searchParam=[
                CapabilityStatementSearchParam(
                    name="identifier",
                    type="token",
                    documentation=(
                        f"The DHIS2 tracked entity UID under `{patient_index.tracked_entity_system}`, or the value "
                        "of a tracked entity attribute DHIS2 declares unique under "
                        f"`{patient_index.identifier_system_base}/tracked-entity-attribute/<uid>`. A token naming "
                        "no system is searched across every one of them."
                    ),
                )
            ],
        )
    ]


def _operations(store_summary: StoreSummary) -> list[CapabilityStatementOperation] | None:
    """Declare `$translate` when the store holds ConceptMaps, and declare nothing when it does not.

    The operation is declared on `rest` rather than on the ConceptMap resource entry: R4 defines
    `$translate` as a type-level operation, and `rest.operation` is where a type-level one belongs.
    """
    if CONCEPT_MAP_RESOURCE_TYPE not in store_summary.counts_by_type:
        return None
    return [
        CapabilityStatementOperation(
            name=TRANSLATE_OPERATION_NAME,
            definition=TRANSLATE_OPERATION_DEFINITION,
            documentation=TRANSLATE_DOCUMENTATION,
        )
    ]


def _generate_operation(
    resource_type: str, canonical: str, names: FoundationNaming
) -> list[CapabilityStatementOperation] | None:
    """Declare `$generate` on the Questionnaire entry, naming the OperationDefinition this IG publishes.

    Every other read type gets nothing: `$generate` fills a form, and Questionnaire is the only
    resource type this server serves that is one.
    """
    if resource_type != QUESTIONNAIRE_RESOURCE_TYPE:
        return None
    return [
        CapabilityStatementOperation(
            name=GENERATE_OPERATION_CODE,
            definition=f"{canonical}/OperationDefinition/{names.generate_operation_id}",
            documentation=GENERATE_DOCUMENTATION,
        )
    ]


def _response_resource(project: FhirProject, canonical: str) -> CapabilityStatementResource:
    """Declare the capture type: create, read, search, and the response profiles this server captures.

    The profiles are `CAPTURED_FORM_KINDS` resolved through the project's own naming, which is the
    same list `d2-capture-server.fsh` declares - a statement of what this facade both validates on
    receipt and translates into a DHIS2 payload on forward.
    """
    declarations = build_captured_response_profile_declarations(project.config.generate)
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


def _read_resource(
    resource_type: str,
    identifier_system_base: str,
    canonical: str,
    names: FoundationNaming,
) -> CapabilityStatementResource:
    """Declare one read type the store holds, with the three search parameters the facade answers."""
    return CapabilityStatementResource(
        type=resource_type,
        operation=_generate_operation(resource_type, canonical, names),
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
