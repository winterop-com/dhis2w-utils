"""The running server's CapabilityStatement: what this process actually serves, right now.

The IG publishes a `kind #requirements` statement declaring what any DHIS2 capture server has
to support. This one is its `kind #instance` counterpart: it `instantiates` the IG's statement
and then narrows it to this installation - the profiles this project generated, and the read
types this store actually holds, so a client that reads `/metadata` never sees a resource type
advertised that the store cannot answer for.

`$evaluate` is the one operation declared at `rest.operation`, the server-level slot, because it is
the one operation whose URL is the service base's: it runs over whichever resource the request names
as its context, so no resource type owns it. A client following this document reaches
`[base]/$evaluate` and is answered there.

The facade surfaces that are not FHIR at all - `POST /evaluate`'s own JSON shape, the terminology
reads, and the CDS Hooks discovery - are named in the `description` rather than declared, exactly as
`GET /spool` is. A CapabilityStatement describes the FHIR interface, and a slot pointing at
`[base]/terminology/lookup` would be naming a path FHIR has no interaction for. The sentence is what
a person reading the conformance document needs; the paths themselves are what a client calls.

The QuestionnaireResponse entry is the one that says what the facade is: responses are received
and stored as receipts. Reading one back returns the submission as it arrived, never a live view
of what DHIS2 now holds.

Where a live run serves the record, that entry says the other half too: what DHIS2 now holds about one
tracked entity is read at `/tracked-entities/{uid}/events`, in the same shape and under the same
profiles. It is stated in the documentation rather than declared as an interaction because it is not
one - the address is the tracked entity's, and `read` and `search-type` on this type are the receipts.
The register's own entries carry the pointer as well, so a client that found somebody learns where
their record is without reading the whole statement.

A process serving `[serve] capture = false` declares that entry without `create`, and with nothing
else about it changed. The receipts it already holds are read and searched at the same address, so
dropping their interactions would be this statement claiming less than the server does. `$generate`
stays for the same reason: it reads a published form and answers with a draft, and writes nothing.

The read set is the capture contract's read types, plus ConceptMap, plus the guide's own conformance
resources. The IG's `kind #requirements` statement names the resources a capture *client* resolves a
form from, and neither of the other two groups is among them - ConceptMap is what a forwarder reads a
concept back into DHIS2 identifiers with, and a StructureDefinition is what a validator resolves a
profile from. This installation serves both all the same, because they are published IG artifacts
sitting in the same store as everything else, and an instance is free to support more than the
statement it instantiates.

The conformance entries are the ones that make a served project self-hosting: a guide's canonicals
have to resolve somewhere, and until the guide is published under its own canonical this server is
the only address they have. They carry the same interactions and the same three search parameters as
every other read type, and `CONFORMANCE_DOCUMENTATION` is where the entry says why it is there - `url`
is the parameter that matters on them, because a client holding a profile canonical it found on a
response has a canonical and no id. Each is declared exactly when the store holds that type, on the
same terms as ConceptMap: a project served before it was ever compiled declares none of them.

The resource operations are declared on the resource entry they are answered under, which is the
entry a client resolves the URL from. `$translate` is answered at `/ConceptMap/$translate` and is declared on
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
checks no credential" from "this server did not say", and those are opposite facts. So the `none`
posture gets a statement of its own, in words. `/metadata` itself is
never behind the check, whatever `[serve] auth_scope` says, because a client has to be able to read
the posture it is expected to meet.

The `jwt` posture is the one that has to say more than a scheme. A caller who knows this server takes
a bearer token still cannot get one without knowing which issuer to ask, so the issuer rides on the
element as an extension - `JWT_ISSUER_EXTENSION_URL` - beside the `OAuth` code that names the scheme.
Never a key, never an audience, never a claim name: the issuer is public by construction, since it is
printed inside every token that issuer signs, and the rest is this deployment's own business.

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

from dhis2w_fhir.config import SearchBackend, ServeAuth, ServeAuthScope
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
    Extension,
)

from dhis2w_fhir_serve.register.filtering import ATTRIBUTE_FILTER_PARAMETER
from dhis2w_fhir_serve.register.projection import PERSON_RESOURCE_TYPES
from dhis2w_fhir_serve.spool import current_instant
from dhis2w_fhir_serve.store import CONCEPT_MAP_RESOURCE_TYPE, GUIDE_CONFORMANCE_RESOURCE_TYPES

if TYPE_CHECKING:
    from dhis2w_fhir.config import FhirProject

    from dhis2w_fhir_serve.register.surface import RegisterSurface, ServedRegister
    from dhis2w_fhir_serve.settings import ServeSettings
    from dhis2w_fhir_serve.store import StoreSummary

#: The resource type the facade receives captures on, alongside the read types it serves.
QUESTIONNAIRE_RESPONSE_RESOURCE_TYPE = "QuestionnaireResponse"

#: Every type the facade answers a read and a search for: the capture contract's, ConceptMap, and the
#: conformance resources the compiled guide publishes.
SERVED_READ_RESOURCE_TYPES = (
    *CAPTURE_SERVER_READ_RESOURCE_TYPES,
    CONCEPT_MAP_RESOURCE_TYPE,
    *GUIDE_CONFORMANCE_RESOURCE_TYPES,
)

#: What a conformance entry states about why this server answers for it.
#:
#: The sentence a client needs is the one about canonicals: a profile named on a response, an
#: extension url carried inside one, and the operation definition this document names are all
#: canonicals somebody has to be able to resolve, and until the guide is published somewhere of its
#: own this server is the only address they have. `url` is how they are asked for, which is why the
#: declaration says so rather than leaving a client to search by id it has no way of knowing.
CONFORMANCE_DOCUMENTATION = (
    "A conformance resource of the guide this server serves, hosted here read-only so the guide is "
    "resolvable before it is published anywhere of its own. Every canonical the resources this "
    "server answers carry - the profiles a response claims, the extensions the served forms and "
    "responses use, and the operation definitions this document names - is asked for here with "
    "`url={canonical}`. It comes from the compiled guide in either store mode: a live run hosts "
    "whatever was last compiled beside the project, and a run with nothing compiled beside it holds "
    "none of these and declares none."
)

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

#: The system-level operation the facade evaluates expressions at, and the definition it names.
#:
#: The definition is this project's own, and is defined in prose rather than emitted as an IG
#: artifact - the same footing `JWT_ISSUER_EXTENSION_URL` below stands on, and for the same reason:
#: it describes what this server does, not what a guide this server publishes contains.
#: `docs/fhir/401-consume-the-fhir-api.md` is where it is defined.
EVALUATE_OPERATION_NAME = "evaluate"
EVALUATE_OPERATION_DEFINITION = "https://winterop-com.github.io/dhis2w-utils/fhir/OperationDefinition/serve-evaluate"

#: What the `$evaluate` operation states about what it evaluates, and over what.
EVALUATE_DOCUMENTATION = (
    "Evaluate one FHIRPath expression, CQL library, or compiled ELM library over one resource this "
    "server serves - a published resource of the guide named by type and id, a resource posted in "
    "the request, or one tracked entity of the register read from the DHIS2 instance - and answer a "
    "Parameters resource: one parameter per define, named by the define, an OperationOutcome part "
    "where a define refused, and an `outcome` parameter carrying the line and column a parser "
    "stopped on. POST a Parameters resource naming `language` and `source`."
)

#: The resource type `$generate` is answered on, and what the operation states about its output.
QUESTIONNAIRE_RESOURCE_TYPE = "Questionnaire"
GENERATE_DOCUMENTATION = (
    "Generate a synthetic QuestionnaireResponse against one served form, optionally from a named "
    "`seed` for a reproducible answer. The generated response is postable to this server's own "
    "QuestionnaireResponse endpoint unchanged."
)


def register_documentation(resource_type: str, over: str) -> str:
    """What one register entry says it answers, and over which of the instance's tracked entity types."""
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

#: What a projection-served register entry adds: where its answers come from, and when they are true.
PROJECTION_DOCUMENTATION = (
    "Which entities a search names comes from this project's materialized projection of the "
    "instance, and every searchset says the instant it is as of - an `outcome` entry beside the "
    "matches, and an `X-DHIS2W-Projection-As-Of` header beside the response. Each named entity is "
    "then read from the instance under your own DHIS2 authorization, so the projection decides who "
    "is on the page and DHIS2 decides who you may see; a read of one entity by its id is answered "
    "from the instance and is as of now. A projection-served searchset states no total, because how "
    "many of its rows you may see is the instance's to say one read at a time."
)

#: What the `_tag` search parameter means on a register, and why it is the parameter for the job.
#:
#: A registered resource states its DHIS2 tracked entity type as a `meta.tag`, so R4's own token
#: search over `meta.tag` is how a caller asks one resource about one of the types it is served over -
#: no parameter this server invented, and no fact the resource does not already carry.
TAG_SEARCH_DOCUMENTATION = (
    "Which DHIS2 tracked entity type the entities are, for a resource served over several of them: "
    "`_tag={system}|{uid}` naming the tracked entity type system this guide publishes, or `_tag={uid}` "
    "naming the type UID alone. Several tags widen the search the way several identifiers do. It "
    "narrows the listing and the identifier search alike, and rides the `next` and `previous` links "
    "of a listing so a walk stays inside the type it started in. A tag naming a type this resource is "
    "not served over matches nothing."
)

#: What the `d2-attribute` filter means, and the one sentence about it that must never be dropped.
#:
#: A filter that looks like search and matches only exact values is a trap unless every declaration of
#: it says which it is, so the equality sentence leads - stated plainly, since a conformance document
#: is read as prose and a shouted clause reads as a warning label rather than as a fact. The
#: attributes themselves are named after it,
#: per register, by `_filter_documentation` - prose, because a searchParam's documentation is prose;
#: `/uiconfig` carries the same set as values for a screen that has to draw a control over them.
ATTRIBUTE_FILTER_DOCUMENTATION = (
    "The value of one tracked entity attribute, spelled `d2-attribute={trackedEntityAttributeUid}|"
    "{value}`. It matches that value exactly - equality and nothing else: no prefix, no substring, no "
    "range, no ordering, and case is ignored exactly as this instance's own `eq` ignores it. Repeat "
    "the parameter to narrow further; two of them are the entities holding both values. A comma is "
    "part of the value rather than a separator, because a DHIS2 attribute value may contain one. It "
    "narrows the listing, the identifier search, and the `_count=0` count alike, and it rides the "
    "`next` and `previous` links of a listing so a walk stays inside the filter it started in. "
    "`identifier` is how you name one entity; this is how you ask which of them hold a value."
)

#: What the `_content` search parameter means here, and the one thing it deliberately does not claim.
CONTENT_SEARCH_DOCUMENTATION = (
    "A case-insensitive substring of any value the entity holds - its identifiers and its other "
    "tracked entity attribute values alike - matched over the projection's index. It is spelled "
    "`_content` rather than `name` or `family` because this server does not know which of an "
    "entity's DHIS2 attribute values is a name, and will not guess: DHIS2 states no such mapping. "
    "The match is a substring and not a transliteration, so a name stored in one script is not "
    "found from another."
)

#: The IPS operation the facade answers over the people in its register, and the definition it
#: conforms to. Both are the IPS's own: `OperationDefinition/summary` is published by
#: `hl7.fhir.uv.ips` on `Patient` at instance and type level, so this server implements a named
#: operation rather than inventing one (`docs/fhir/design/ips.md` R6).
SUMMARY_OPERATION_CODE = "summary"
SUMMARY_OPERATION_DEFINITION = "http://hl7.org/fhir/uv/ips/OperationDefinition/summary"

#: What the `$summary` operation states on the register entry it is answered under.
#:
#: The IPS defines `summary` on `Patient` at instance and type level and declares exactly that one
#: operation in its own Server CapabilityStatement, so this entry names the IPS's definition rather
#: than one this project publishes - the operation is theirs and this is an implementation of it.
SUMMARY_DOCUMENTATION = (
    "Assemble this person's International Patient Summary: one FHIR document Bundle, a Composition "
    "carrying the three sections the IPS requires, and the sections this project maps carrying "
    "entries read from that person's own record. `GET /{type}/{id}/$summary` names one person by "
    "their DHIS2 tracked entity UID; `GET /{type}/$summary?identifier=` resolves one through the "
    "same identifier search this register answers, and refuses a value several people hold. Every "
    "document states in its own `Composition.text` which sections carry no mapping and that it does "
    "not claim the Creator (IPS) actor's obligations."
)

#: What a register entry adds where the record is served: where to read what happened to one of them.
REGISTER_RECORD_DOCUMENTATION = (
    "What one of them has been through is read at `GET /tracked-entities/{uid}/events`, as one "
    "QuestionnaireResponse per event of their enrollments."
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

#: What this installation says it is, one sentence per store mode. Each names the thing the process
#: stands in front of, and both state the fact about the receipts that a client reading one needs.
LIVE_IMPLEMENTATION_DESCRIPTION = (
    "A FHIR capture facade over a live DHIS2 instance. What it stores are receipts of submissions as "
    "they arrived, not a live view of what the instance now holds."
)
COMPILED_IMPLEMENTATION_DESCRIPTION = (
    "A FHIR capture facade over a compiled implementation guide. What it stores are receipts of "
    "submissions as they arrived, and no DHIS2 instance stands behind this process to read from."
)

#: What the QuestionnaireResponse entry states about the resources it holds.
RESPONSE_DOCUMENTATION = "One response per request; stored responses are receipts of what was submitted"

#: What that entry states instead on a server that receives nothing, since "one per request" would
#: describe an interaction this process refuses.
RESPONSE_VIEWER_DOCUMENTATION = "Stored responses are receipts of what was submitted; this server receives no new ones"

#: What the same entry adds where the record is served, which is the other half of the same sentence.
#:
#: A receipt and a record are two documents of one resource type answering two questions, and a client
#: reading this entry has to be able to tell them apart before it asks: a receipt is what a client sent
#: and is read at `QuestionnaireResponse/{id}`, and a record is what the instance holds now and is read
#: under the tracked entity it belongs to. The address is stated here rather than declared as an
#: interaction because it is not one: `read` and `search-type` on this entry are the receipts.
RECORD_DOCUMENTATION = (
    "What the instance holds about one tracked entity now is a different read, at "
    "`GET /tracked-entities/{uid}/events`: every event of that entity's enrollments, newest first, each "
    "as the response the program stage's own published form describes, and each read from DHIS2 at "
    "request time under the authorization of whoever asked. `_count` and `page` walk it, and one event "
    "is read at `GET /tracked-entities/{uid}/events/{eventUid}`."
)

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

#: The two codes in that system this facade uses. The DHIS2 posture takes a username and a password
#: over HTTP Basic, which is exactly what `Basic` names; the JWT posture takes a bearer token from an
#: OAuth 2.0 authorization server, which is what `OAuth` names. The static-token posture takes a
#: scheme the value set has no code for, so it is stated as text, which an extensible binding is for.
BASIC_SECURITY_CODE = "Basic"
OAUTH_SECURITY_CODE = "OAuth"
BEARER_TOKEN_SECURITY_TEXT = "Bearer token"
JWT_BEARER_TOKEN_SECURITY_TEXT = "JWT bearer token"
DHIS2_PERSONAL_ACCESS_TOKEN_SECURITY_TEXT = "DHIS2 personal access token"

#: Where the `jwt` posture states WHICH issuer it takes tokens from.
#:
#: R4 has no element for it: `security.service` names schemes, and an issuer is not a scheme. So it
#: rides as an extension on `security`, which is what BackboneElement extensions are for, under a URL
#: this project defines - `docs/fhir/301-serving.md` is where it is defined. THE ISSUER AND NOTHING
#: ELSE crosses: never a key, never an audience, never a claim name. The issuer is the one fact a
#: caller needs and the one fact that was never secret - it is printed on every token it signs.
JWT_ISSUER_EXTENSION_URL = "https://winterop-com.github.io/dhis2w-utils/fhir/StructureDefinition/serve-jwt-issuer"

#: What each posture says about itself. The `none` statement exists so an absence is never inferred.
NO_AUTHENTICATION_DESCRIPTION = (
    "This server checks no credential. It listens on the loopback interface only, unless the project "
    "it serves states [serve] auth in its fhir.toml."
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

JWT_AUTHENTICATION_DESCRIPTION = (
    "Send a token from the OpenID Connect issuer named in this element's issuer extension, as "
    "`Authorization: Bearer <token>`. Obtaining one is that issuer's business: this server mints no "
    "token and runs no authorization server. It verifies the signature against the keys the issuer "
    "publishes, checks the issuer, the expiry, and the audience it was configured with, and records "
    "the username claim on every receipt you capture."
)
JWT_FORWARDED_REGISTER_DESCRIPTION = (
    "Reads of the register are answered under your own DHIS2 authorization: this server forwards your "
    "token to the instance, which resolves it to a DHIS2 user because it trusts the same issuer, so "
    "DHIS2's sharing, organisation unit scopes, ownership, and access levels decide what you see."
)
JWT_UNFORWARDED_REGISTER_DESCRIPTION = (
    "The register is not served here. This server will not read it as anybody but the caller who "
    "asked, and forwarding your token to DHIS2 needs both `[serve.jwt] forward_bearer` on this server "
    "and a DHIS2 instance configured to trust the same issuer. The published guide and the received "
    "responses are served as usual."
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


def build_security(
    posture: ServeAuth, scope: ServeAuthScope, *, issuer: str | None = None, forward_bearer: bool = False
) -> CapabilityStatementSecurity:
    """State how this process decides who is calling, in every posture including the one that does not.

    `cors` is false in all four because this facade sends no cross-origin headers at all: the capture
    UI it serves is same-origin with it, and a browser page from anywhere else is a deployment
    decision for whatever sits in front of this server.

    `issuer` and `forward_bearer` are the `jwt` posture's and are ignored in the other three. The
    issuer is stated because a caller cannot get a token without knowing who to ask; `forward_bearer`
    is stated because it decides whether the register answers at all, and a client discovering that
    from a 501 would be a client this document had misled.
    """
    if posture is ServeAuth.NONE:
        return CapabilityStatementSecurity(cors=False, description=NO_AUTHENTICATION_DESCRIPTION)
    if posture is ServeAuth.JWT:
        return _jwt_security(scope, issuer=issuer, forward_bearer=forward_bearer)
    stated = TOKEN_AUTHENTICATION_DESCRIPTION if posture is ServeAuth.TOKEN else DHIS2_AUTHENTICATION_DESCRIPTION
    covered = _scope_description(posture, scope)
    return CapabilityStatementSecurity(
        cors=False,
        service=_security_services(posture),
        description=f"{stated} {covered}",
    )


def _jwt_security(scope: ServeAuthScope, *, issuer: str | None, forward_bearer: bool) -> CapabilityStatementSecurity:
    """The `jwt` posture's statement: the scheme, the issuer, and what the register does under it."""
    register = JWT_FORWARDED_REGISTER_DESCRIPTION if forward_bearer else JWT_UNFORWARDED_REGISTER_DESCRIPTION
    covered = ALL_SCOPE_DESCRIPTION if scope is not ServeAuthScope.WRITE else WRITE_SCOPE_DESCRIPTION
    return CapabilityStatementSecurity(
        cors=False,
        extension=None if issuer is None else [Extension(url=JWT_ISSUER_EXTENSION_URL, valueString=issuer)],
        service=[
            CodeableConcept(
                coding=[Coding(system=SECURITY_SERVICE_SYSTEM, code=OAUTH_SECURITY_CODE, display=OAUTH_SECURITY_CODE)],
                text=JWT_BEARER_TOKEN_SECURITY_TEXT,
            )
        ],
        description=f"{JWT_AUTHENTICATION_DESCRIPTION} {register} {covered}",
    )


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
    resources = [
        _response_resource(
            project,
            canonical,
            capture=settings.capture,
            record=settings.live and register_surface.serves_events(),
        ),
        *(
            _read_resource(resource_type, project.config.generate.identifier_system_base, canonical, names)
            for resource_type in SERVED_READ_RESOURCE_TYPES
            if resource_type in store_summary.counts_by_type
        ),
        *_register_resources(settings, register_surface, project.config.ips.enabled),
    ]
    return CapabilityStatement(
        status="active",
        date=current_instant(),
        kind="instance",
        description=(
            f"{project.config.ig.title} served as a FHIR capture facade: {store_summary.total} resources "
            f"in the store, served under the {len(resources)} resource types this statement declares. "
            f"`GET /spool` states how many responses "
            f"are stored, which is a number that changes while this server runs. Beside the FHIR surface "
            f"this process also answers `POST /evaluate` (the same evaluation the declared `$evaluate` "
            f"operation answers, in this project's own JSON shape, with the line and column a parser "
            f"stopped on), "
            f"`GET /terminology/validate-code` and `GET /terminology/lookup` (this guide's own "
            f"vocabularies, not a terminology server), and `GET /cds-services` (CDS Hooks, one service)."
        ),
        instantiates=[f"{canonical}/CapabilityStatement/{names.capture_server_id}"],
        software=CapabilityStatementSoftware(name=SOFTWARE_NAME, version=server_version),
        implementation=CapabilityStatementImplementation(description=_implementation_description(settings)),
        fhirVersion="4.0.1",
        format=["json"],
        rest=[
            CapabilityStatementRest(
                mode="server",
                documentation=_REST_DOCUMENTATION if settings.capture else _VIEWER_REST_DOCUMENTATION,
                security=build_security(
                    settings.auth,
                    settings.auth_scope,
                    issuer=settings.jwt.issuer,
                    forward_bearer=settings.jwt.forward_bearer,
                ),
                resource=resources,
                operation=[
                    CapabilityStatementOperation(
                        name=EVALUATE_OPERATION_NAME,
                        definition=EVALUATE_OPERATION_DEFINITION,
                        documentation=EVALUATE_DOCUMENTATION,
                    )
                ],
            )
        ],
    )


def _implementation_description(settings: ServeSettings) -> str:
    """What this installation is, in the words of the mode it was started in.

    The two modes are two different things rather than one thing with a flag on it: a live process
    stands in front of a DHIS2 instance, and a compiled one stands in front of a build, so each says
    what it is rather than sharing a sentence with a parenthesis in it. What they share is the fact
    about the receipts, which is true of both and is what a client reading one back has to know.
    """
    if settings.live:
        return LIVE_IMPLEMENTATION_DESCRIPTION
    return COMPILED_IMPLEMENTATION_DESCRIPTION


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
    settings: ServeSettings, register_surface: RegisterSurface, summaries: bool
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

    `summaries` is `[ips] enabled`, and it decides whether the entries carrying people declare
    `$summary`. It rides the entry rather than the server, for the reason `$translate` and
    `$generate` do: `rest.operation` would send a client following this document to `[base]/$summary`,
    which is not an address this server answers, and a resource operation's URL is the resource's.
    """
    if not settings.live or not register_surface.serves_tracked_entities():
        return []
    index = register_surface.index
    return [
        CapabilityStatementResource(
            type=register.resource_type,
            documentation=_register_documentation(settings, register_surface, register),
            operation=_summary_operation(summaries, register.resource_type),
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
                ),
                CapabilityStatementSearchParam(
                    name="_tag",
                    type="token",
                    documentation=(
                        f"{TAG_SEARCH_DOCUMENTATION} The system is "
                        f"`{index.tracked_entity_type_system}`, and the types this resource is served "
                        f"over are {_type_labels(register)}."
                    ),
                ),
                CapabilityStatementSearchParam(
                    name=ATTRIBUTE_FILTER_PARAMETER,
                    type="token",
                    documentation=_filter_documentation(register),
                ),
                *(
                    [
                        CapabilityStatementSearchParam(
                            name="_content",
                            type="string",
                            documentation=CONTENT_SEARCH_DOCUMENTATION,
                        )
                    ]
                    if settings.search.backend is SearchBackend.PROJECTION
                    else []
                ),
            ],
        )
        for register in register_surface.registers()
    ]


def _summary_operation(summaries: bool, resource_type: str) -> list[CapabilityStatementOperation] | None:
    """Declare `$summary` on a register entry that answers it, and on no other.

    Two conditions, and both are already true of the route: the project has to turn the surface on
    with `[ips] enabled`, and the resource has to be one R4 gives a person. A `Specimen` register is
    a register of samples, and declaring a patient summary on it would advertise an interaction
    every request to it refuses by name.
    """
    if not summaries or resource_type not in PERSON_RESOURCE_TYPES:
        return None
    return [
        CapabilityStatementOperation(
            name=SUMMARY_OPERATION_CODE,
            definition=SUMMARY_OPERATION_DEFINITION,
            documentation=SUMMARY_DOCUMENTATION,
        )
    ]


def _filter_documentation(register: ServedRegister) -> str:
    """What one register's value filter answers, and which attributes it answers it on.

    The attributes are named in the declaration rather than left to a client to discover, because the
    parameter is worthless without them: `d2-attribute` names an attribute by DHIS2 UID, and a UID is
    not something anybody guesses. They are the attributes this register's own types collect, so a
    register of samples names a sample's attributes and never a person's.
    """
    if not register.filter_attributes:
        return (
            f"{ATTRIBUTE_FILTER_DOCUMENTATION} This register filters on no attribute: the guide "
            "publishes no registration form for the tracked entity types it is served over, so "
            "nothing states what they collect."
        )
    return f"{ATTRIBUTE_FILTER_DOCUMENTATION} The attributes it filters on are {_attribute_labels(register)}."


def _attribute_labels(register: ServedRegister) -> str:
    """The filterable attributes as a client has to read them - the UID, the name, and what the values are.

    The bound ValueSet is named where DHIS2 binds an option set, because that is the difference
    between a filter a caller can enumerate the values of and one they have to already know a value
    of. `/uiconfig` carries the same canonical as a value, for a screen drawing a control from it.
    """
    labels: list[str] = []
    for attribute in register.filter_attributes:
        named = (
            attribute.attribute_uid if attribute.display is None else f"{attribute.display} ({attribute.attribute_uid})"
        )
        stated = named if attribute.value_type is None else f"{named}, whose values are {attribute.value_type}"
        labels.append(stated if attribute.value_set is None else f"{stated} drawn from `{attribute.value_set}`")
    return "; ".join(labels)


def _type_labels(register: ServedRegister) -> str:
    """The tracked entity types one resource is served over, named the way the instance names them."""
    return ", ".join(
        published.uid if published.name is None else f"{published.name} ({published.uid})"
        for published in register.tracked_entity_types
    )


def _register_documentation(
    settings: ServeSettings, register_surface: RegisterSurface, register: ServedRegister
) -> str:
    """What one register entry says this server answers: what a hit is, how it pages, where it came from."""
    stated = (
        f"{register_documentation(register.resource_type, _type_labels(register))} {IDENTIFIER_UNION_DOCUMENTATION}"
    )
    listing = LISTING_DOCUMENTATION if register_surface.serves_listing() else LISTING_OFF_DOCUMENTATION
    record = f" {REGISTER_RECORD_DOCUMENTATION}" if register_surface.serves_events() else ""
    if settings.search.backend is not SearchBackend.PROJECTION:
        return f"{stated} {listing}{record}"
    return f"{stated} {listing} {PROJECTION_DOCUMENTATION}{record}"


def _read_documentation(resource_type: str) -> str | None:
    """What one read entry states about itself, which only the conformance resources need to say.

    The published artifacts a capture client reads need no sentence here: a Questionnaire entry
    saying that a Questionnaire is a form would tell a reader what the type name already told them.
    The conformance resources do need one, because what they are here for is not obvious from the
    type - a server hosting its own guide's profiles is a thing a client has to be told it may lean on.
    """
    if resource_type in GUIDE_CONFORMANCE_RESOURCE_TYPES:
        return CONFORMANCE_DOCUMENTATION
    return None


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


def _response_resource(
    project: FhirProject, canonical: str, *, capture: bool, record: bool = False
) -> CapabilityStatementResource:
    """Declare the capture type: create where this server receives, read and search either way.

    The profiles are `CAPTURED_FORM_KINDS` resolved through the project's own naming, which is the
    same list `d2-capture-server.fsh` declares - a statement of what this facade both validates on
    receipt and translates into a DHIS2 payload on forward. They stay declared with capture off,
    because they are what the receipts on disk conform to and a client reading one still resolves them.

    `record` states the other half of what this resource type means here: where a live run serves one
    tracked entity's own events, the same profiles describe documents read from the instance rather
    than received from a client, and the entry says which address answers which question. The
    interactions are unchanged, because a record is read under the tracked entity it belongs to and
    not at this type's own address.
    """
    declarations = build_captured_response_profile_declarations(project.config.generate)
    stated = RESPONSE_DOCUMENTATION if capture else RESPONSE_VIEWER_DOCUMENTATION
    return CapabilityStatementResource(
        type=QUESTIONNAIRE_RESPONSE_RESOURCE_TYPE,
        supportedProfile=[f"{canonical}/StructureDefinition/{declaration.profile_id}" for declaration in declarations],
        documentation=f"{stated}. {RECORD_DOCUMENTATION}" if record else stated,
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
        documentation=_read_documentation(resource_type),
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
