"""The running server's CapabilityStatement: what this process actually serves, right now.

The IG publishes a `kind #requirements` statement declaring what any DHIS2 capture server has
to support. This one is its `kind #instance` counterpart: it `instantiates` the IG's statement
and then narrows it to this installation - the profiles this project generated, and the read
types this store actually holds, so a client that reads `/metadata` never sees a resource type
advertised that the store cannot answer for.

The three facade surfaces that are not FHIR at all - the evaluator, the terminology reads, and the
CDS Hooks discovery - are named in the `description` rather than declared as resources or as
server-level operations, exactly as `GET /spool` is. A CapabilityStatement describes the FHIR
interface, and `rest.operation` would send a client following this document to `[base]/$evaluate`,
which is not an address this server serves. The sentence is what a person reading the conformance
document needs; the paths themselves are what a client calls.

The QuestionnaireResponse entry is the one that says what the facade is: responses are received
and stored as receipts. Reading one back returns the submission as it arrived, never a live view
of what DHIS2 now holds.

A process serving `[serve] capture = false` declares that entry without `create`, and with nothing
else about it changed. The receipts it already holds are read and searched at the same address, so
dropping their interactions would be this statement claiming less than the server does. `$generate`
stays for the same reason: it reads a published form and answers with a draft, and writes nothing.

The read set is the capture contract's read types plus ConceptMap. The IG's `kind #requirements`
statement names the resources a capture *client* resolves a form from, and ConceptMap is not one of
them - it is what a forwarder reads a concept back into DHIS2 identifiers with. This installation
serves it all the same, because the maps are published IG artifacts sitting in the same store as
everything else, and an instance is free to support more than the statement it instantiates.

Both operations are declared on the resource entry they are answered under, which is the entry a
client resolves the URL from. `$translate` is answered at `/ConceptMap/$translate` and is declared on
the ConceptMap entry; `$generate` is answered at `/Questionnaire/{id}/$generate` and is declared on
the Questionnaire entry. `rest.operation` would send a client following the statement to
`[base]/$translate`, which this server does not serve - a server-level slot is for a server-level
URL, and declaring a resource operation there names an endpoint that answers 404. Each rides its
entry, so each is declared exactly when the store holds that type: no ConceptMaps, no `$translate`.

`$generate`'s definition is the OperationDefinition the project's own IG publishes, not an HL7 one:
it is a custom operation, deliberately not SDC's `$populate`. `$translate` conforms to R4's own
ConceptMap definition and names it.

`rest.security` is declared in EVERY posture, `none` included. A conformance document that carries
the element only where there is something to protect leaves a client unable to tell "this server
authenticates nobody" from "this server did not say", and those are opposite facts. So the `none`
posture gets a statement of its own, in words: this server serves every caller. `/metadata` itself is
never behind the check, whatever `[serve] auth_scope` says, because a client has to be able to read
the posture it is expected to meet.

The register's entries are the ones that are not about the store at all. They are answered from the
DHIS2 instance per request, and which resource types they are is the published `D2TET_CM`'s to say -
one entry per FHIR resource the map takes an in-scope tracked entity type onto. They are declared
only by a process that has an instance - `--live`, over a project that publishes a registration form
and therefore names a tracked entity type. A compiled run declares none of them, which is the same
refusal the register gives, stated before the request rather than after it - and so does a live run
over a project whose `[serve.tracked_entities] enabled` is false, which is that same refusal reached
from the project rather than from the invocation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from dhis2w_fhir.config import ServeAuth, ServeAuthScope
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
    CapabilityStatementSecurity,
    CapabilityStatementSoftware,
    CodeableConcept,
    Coding,
)

from dhis2w_fhir_serve.spool import current_instant
from dhis2w_fhir_serve.store import CONCEPT_MAP_RESOURCE_TYPE

if TYPE_CHECKING:
    from dhis2w_fhir.config import FhirProject

    from dhis2w_fhir_serve.register.surface import RegisterSurface, ServedRegister
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


def register_documentation(resource_type: str, tracked_entity_type_labels: tuple[str, ...]) -> str:
    """What one register entry says it answers, and over which of the instance's tracked entity types."""
    over = ", ".join(tracked_entity_type_labels)
    return (
        f"One DHIS2 tracked entity per {resource_type}, read from the instance at request time, over the "
        f"tracked entity types this guide publishes as {resource_type}: {over}. Identity only - the tracked "
        "entity UID, the values of the attributes DHIS2 declares unique, and the rest of the attribute "
        f"values as extensions. Nothing a {resource_type} otherwise defines is filled in: DHIS2 states no "
        "mapping for those elements."
    )


#: What a register entry adds about the no-identifier search, which is either a page or a refusal.
LISTING_DOCUMENTATION = (
    "A search naming no identifier is answered with one page of the register: `_count` rows at a "
    "time, walked by following the Bundle's own `next` and `previous` links, whose `page` parameter "
    "names the page and is this server's to compose."
)
LISTING_OFF_DOCUMENTATION = (
    "A search naming no identifier is refused: this project serves the register by identifier only."
)

#: What a register entry states about several identifiers in one search, which widen rather than narrow.
IDENTIFIER_UNION_DOCUMENTATION = (
    "Several identifiers are alternatives rather than conditions: comma-separated values and the "
    "parameter repeated both widen the search, and every match is folded into one result set "
    "deduplicated by tracked entity."
)

#: What the `questionnaire` search parameter states about how it matches, which is not what a
#: reference search parameter usually implies - no version stripping, no reference resolution.
QUESTIONNAIRE_SEARCH_DOCUMENTATION = (
    "The canonical of the Questionnaire the stored responses answered. Matching is exact canonical "
    "equality: the value has to be the whole canonical the response carries, character for "
    "character, and no version suffix is stripped and no partial canonical matches."
)

#: What the QuestionnaireResponse entry states about the resources it holds.
RESPONSE_DOCUMENTATION = "One response per request; stored responses are receipts of what was submitted"

#: What that entry states instead on a server that receives nothing, since "one per request" would
#: describe an interaction this process refuses.
RESPONSE_VIEWER_DOCUMENTATION = "Stored responses are receipts of what was submitted; this server receives no new ones"

_REST_DOCUMENTATION = (
    "One QuestionnaireResponse per request on create; every other interaction is a read over the "
    "resources this project publishes."
)

_VIEWER_REST_DOCUMENTATION = (
    "Every interaction is a read - over the resources this project publishes, and over the responses "
    "it has already received."
)

#: R4's own code system for the schemes a `rest.security` may name.
SECURITY_SERVICE_SYSTEM = "http://terminology.hl7.org/CodeSystem/restful-security-service"

#: The one code in that system this facade uses. The DHIS2 posture takes a username and a password
#: over HTTP Basic, which is exactly what `Basic` names; the static-token posture takes a scheme the
#: value set has no code for, so it is stated as text, which an extensible binding is for.
BASIC_SECURITY_CODE = "Basic"
BEARER_TOKEN_SECURITY_TEXT = "Bearer token"
DHIS2_PERSONAL_ACCESS_TOKEN_SECURITY_TEXT = "DHIS2 personal access token"

#: What each posture says about itself. The `none` statement exists so an absence is never inferred.
NO_AUTHENTICATION_DESCRIPTION = (
    "This server authenticates nobody: every caller is served. It binds a loopback interface unless "
    "the project it serves states `[serve] auth` in its fhir.toml."
)
TOKEN_AUTHENTICATION_DESCRIPTION = (
    "Send `Authorization: Bearer <token>`, with one of the tokens this deployment holds in the "
    "environment variable D2W_FHIR_SERVE_TOKENS. The tokens name no person: a receipt captured under "
    "this posture records no submitter."
)
DHIS2_AUTHENTICATION_DESCRIPTION = (
    "Send the credentials you would sign in to the DHIS2 instance behind this server with - a "
    "username and password as HTTP Basic, or a DHIS2 personal access token as "
    "`Authorization: ApiToken <token>`. This server checks them by reading `/api/me` on that "
    "instance as you, and records the username it gets back on every receipt you capture. Reads of "
    "the register are answered under your own DHIS2 authorization: this server forwards your "
    "credentials to the instance, so DHIS2's sharing, organisation unit scopes, ownership, and "
    "access levels decide what you see."
)

#: What each scope adds about how much of the surface the posture covers.
WRITE_SCOPE_DESCRIPTION = (
    "Credentials are required to create a QuestionnaireResponse. Every read, every search, this "
    "document, and both operations are served without them."
)
DHIS2_WRITE_SCOPE_DESCRIPTION = (
    "Credentials are required to create a QuestionnaireResponse, and to read or search the register, "
    "which is answered under the credentials of whoever asks. This document, every read of the "
    "published guide, and both operations are served without them."
)
ALL_SCOPE_DESCRIPTION = "Credentials are required for every interaction except reading this document."


def build_server_capability(
    project: FhirProject,
    store_summary: StoreSummary,
    settings: ServeSettings,
    register_surface: RegisterSurface,
    server_version: str,
) -> CapabilityStatement:
    """State what this process serves: the capture contract, the read types the store holds, and the register."""
    canonical = project.config.ig.canonical
    names = FoundationNaming.from_naming(project.config.generate.naming)
    store_mode = "live" if settings.live else "compiled"
    resources = [
        _response_resource(project, canonical, capture=settings.capture),
        *(
            _read_resource(resource_type, project.config.generate.identifier_system_base, canonical, names)
            for resource_type in SERVED_READ_RESOURCE_TYPES
            if resource_type in store_summary.counts_by_type
        ),
        *_register_resources(settings, register_surface),
    ]
    return CapabilityStatement(
        status="active",
        date=current_instant(),
        kind="instance",
        description=(
            f"{project.config.ig.title} served as a FHIR capture facade: {store_summary.total} resources "
            f"across {len(store_summary.counts_by_type)} types. `GET /spool` states how many responses "
            f"are stored, which is a number that changes while this server runs. Beside the FHIR surface "
            f"this process also answers `POST /evaluate` (FHIRPath, CQL, and ELM over what it serves), "
            f"`GET /terminology/validate-code` and `GET /terminology/lookup` (this guide's own "
            f"vocabularies, not a terminology server), and `GET /cds-services` (CDS Hooks, one service)."
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
                documentation=_REST_DOCUMENTATION if settings.capture else _VIEWER_REST_DOCUMENTATION,
                security=build_security(settings.auth, settings.auth_scope),
                resource=resources,
            )
        ],
    )


def build_security(posture: ServeAuth, scope: ServeAuthScope) -> CapabilityStatementSecurity:
    """State how this process decides who is calling, in every posture including the one that does not.

    `cors` is false in all three because this facade sends no cross-origin headers at all: the capture
    UI it serves is same-origin with it, and a browser page from anywhere else is a deployment
    decision for whatever sits in front of this server.
    """
    if posture is ServeAuth.NONE:
        return CapabilityStatementSecurity(cors=False, description=NO_AUTHENTICATION_DESCRIPTION)
    stated = TOKEN_AUTHENTICATION_DESCRIPTION if posture is ServeAuth.TOKEN else DHIS2_AUTHENTICATION_DESCRIPTION
    covered = _scope_description(posture, scope)
    return CapabilityStatementSecurity(
        cors=False,
        service=_security_services(posture),
        description=f"{stated} {covered}",
    )


def _scope_description(posture: ServeAuth, scope: ServeAuthScope) -> str:
    """How much of the surface a posture covers, with the one line the `dhis2` posture makes untrue.

    `write` leaves reads open, and under every other posture that is the whole of it. Under `dhis2`
    a register read is answered under the caller's own DHIS2 authorization, so it asks for
    credentials in either scope - saying "every read is served without them" would be a promise this
    server does not keep.
    """
    if scope is not ServeAuthScope.WRITE:
        return ALL_SCOPE_DESCRIPTION
    return DHIS2_WRITE_SCOPE_DESCRIPTION if posture is ServeAuth.DHIS2 else WRITE_SCOPE_DESCRIPTION


def _security_services(posture: ServeAuth) -> list[CodeableConcept]:
    """The schemes one posture accepts, coded where R4's value set has a code and stated as text where not."""
    if posture is ServeAuth.TOKEN:
        return [CodeableConcept(text=BEARER_TOKEN_SECURITY_TEXT)]
    return [
        CodeableConcept(
            coding=[Coding(system=SECURITY_SERVICE_SYSTEM, code=BASIC_SECURITY_CODE, display=BASIC_SECURITY_CODE)],
            text=BASIC_SECURITY_CODE,
        ),
        CodeableConcept(text=DHIS2_PERSONAL_ACCESS_TOKEN_SECURITY_TEXT),
    ]


def _register_resources(
    settings: ServeSettings, register_surface: RegisterSurface
) -> list[CapabilityStatementResource]:
    """Declare one entry per FHIR resource the register answers, and none when it answers nothing.

    Three conditions gate the whole set. Two are properties of how the process was started rather
    than of the IG: the store has to be live, because a register entity is read from the DHIS2
    instance and there is no instance behind a compiled guide, and the project has to publish a
    registration form (or name a type in `[serve.tracked_entities]`), because the tracked entity type
    is what a DHIS2 search must be given. The third is the project's own word:
    `[serve.tracked_entities] enabled = false` removes the register, and a statement declaring it
    anyway would advertise an interaction every request to it refuses.

    Which entries there are is not gated at all - it is read off the published map. A project whose
    types all map to `Patient` declares exactly the one entry it always did; a project that also
    registers samples declares `Specimen` beside it, each naming in its documentation the tracked
    entity types it is served over, so a client reading the statement knows what a hit under either
    resource actually is.

    The listing is stated in each resource's documentation rather than as another search parameter:
    `_count` is a FHIR-wide parameter and `page` is this server's own naming of the cursor, and
    neither is a search parameter of the resource in the sense `searchParam` enumerates.
    """
    if not settings.live or not register_surface.serves_tracked_entities():
        return []
    index = register_surface.index
    return [
        CapabilityStatementResource(
            type=register.resource_type,
            documentation=_register_documentation(register_surface, register),
            interaction=[
                CapabilityStatementInteraction(code="read"),
                CapabilityStatementInteraction(code="search-type"),
            ],
            searchParam=[
                CapabilityStatementSearchParam(
                    name="identifier",
                    type="token",
                    documentation=(
                        f"The DHIS2 tracked entity UID under `{index.tracked_entity_system}`, or the value "
                        "of a tracked entity attribute this server holds as a search key under "
                        f"`{index.identifier_system_base}/tracked-entity-attribute/<uid>`. A token naming "
                        "no system is searched across every one of them."
                    ),
                )
            ],
        )
        for register in register_surface.registers()
    ]


def _register_documentation(register_surface: RegisterSurface, register: ServedRegister) -> str:
    """What one register entry says this server answers, listing included when this project serves one."""
    labels = tuple(
        published.uid if published.name is None else f"{published.name} ({published.uid})"
        for published in register.tracked_entity_types
    )
    stated = f"{register_documentation(register.resource_type, labels)} {IDENTIFIER_UNION_DOCUMENTATION}"
    if not register_surface.serves_listing():
        return f"{stated} {LISTING_OFF_DOCUMENTATION}"
    return f"{stated} {LISTING_DOCUMENTATION}"


def _operations(
    resource_type: str, canonical: str, names: FoundationNaming
) -> list[CapabilityStatementOperation] | None:
    """The operations one read type is answered under, or nothing for a type this server only reads.

    Two types carry one each, and each is the type its own URL names: `$generate` fills a served
    form, so it rides Questionnaire; `$translate` reads a mapping back into DHIS2 identifiers, so it
    rides ConceptMap. A client following either entry reaches the endpoint that answers it.
    """
    if resource_type == QUESTIONNAIRE_RESOURCE_TYPE:
        return [
            CapabilityStatementOperation(
                name=GENERATE_OPERATION_CODE,
                definition=f"{canonical}/OperationDefinition/{names.generate_operation_id}",
                documentation=GENERATE_DOCUMENTATION,
            )
        ]
    if resource_type == CONCEPT_MAP_RESOURCE_TYPE:
        return [
            CapabilityStatementOperation(
                name=TRANSLATE_OPERATION_NAME,
                definition=TRANSLATE_OPERATION_DEFINITION,
                documentation=TRANSLATE_DOCUMENTATION,
            )
        ]
    return None


def _response_resource(project: FhirProject, canonical: str, *, capture: bool) -> CapabilityStatementResource:
    """Declare the capture type: create where this server receives, read and search either way.

    The profiles are `CAPTURED_FORM_KINDS` resolved through the project's own naming, which is the
    same list `d2-capture-server.fsh` declares - a statement of what this facade both validates on
    receipt and translates into a DHIS2 payload on forward. They stay declared with capture off,
    because they are what the receipts on disk conform to and a client reading one still resolves them.
    """
    declarations = build_captured_response_profile_declarations(project.config.generate)
    return CapabilityStatementResource(
        type=QUESTIONNAIRE_RESPONSE_RESOURCE_TYPE,
        supportedProfile=[f"{canonical}/StructureDefinition/{declaration.profile_id}" for declaration in declarations],
        documentation=RESPONSE_DOCUMENTATION if capture else RESPONSE_VIEWER_DOCUMENTATION,
        interaction=[
            *([CapabilityStatementInteraction(code="create")] if capture else []),
            CapabilityStatementInteraction(code="read"),
            CapabilityStatementInteraction(code="search-type"),
        ],
        searchParam=[
            CapabilityStatementSearchParam(name="_id", type="token"),
            CapabilityStatementSearchParam(
                name="questionnaire",
                type="reference",
                documentation=QUESTIONNAIRE_SEARCH_DOCUMENTATION,
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
        operation=_operations(resource_type, canonical, names),
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
