"""FSH emission for the foundation layer: the DHIS2 identifier systems, D2Period, and the capture contract.

These artifacts depend on `fhir.toml` alone, never on a DHIS2 instance. `d2-aliases.fsh`
turns `[generate] identifier_system_base` into the `$DHIS2-*` aliases every instance file
references; `d2-naming-systems.fsh` declares each of those URLs as a NamingSystem, so a
consumer meeting a DHIS2 identifier can resolve what it means; `d2-period.fsh` defines the
reporting-period Extension plus the period-type CodeSystem/ValueSet backing its required
binding; `d2-form-type.fsh` defines the form-type Extension every generated Questionnaire
carries, plus its own CodeSystem/ValueSet pair.

Two more artifacts turn that vocabulary into a capture contract a third party can build
against without reading DHIS2: `d2-responses.fsh` profiles the QuestionnaireResponse a
capture client sends - one profile per form kind, each pinning the context the response has
to carry - and `d2-capture-server.fsh` states the interactions a server accepting those
responses supports.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from jinja2 import Environment, PackageLoader, StrictUndefined, select_autoescape

from dhis2w_fhir.foundation.schemas import (
    FORM_TYPE_DEFINITIONS,
    IDENTIFIER_SYSTEM_SUBJECTS,
    FormTypeDefinition,
    FoundationNaming,
    NamingSystemDeclaration,
    ResponseProfileDeclaration,
)
from dhis2w_fhir.names import page_text
from dhis2w_fhir.period.schemas import PERIOD_TYPE_DEFINITIONS
from dhis2w_fhir.resources.organisation_units.naming import OrganisationUnitNaming
from dhis2w_fhir.status import IgStatus, experimental_for_status
from dhis2w_fhir.writer import FshArtifact

if TYPE_CHECKING:
    from dhis2w_fhir.config import GenerateConfig

__all__ = [
    "CAPTURE_SERVER_READ_RESOURCE_TYPES",
    "FORM_TYPE_DEFINITIONS",
    "FormTypeDefinition",
    "FoundationNaming",
    "NamingSystemDeclaration",
    "ResponseProfileDeclaration",
    "build_foundation_artifacts",
    "build_response_profile_declarations",
]

#: The `NamingSystem.date` every declaration carries. R4 makes the element mandatory, and a
#: generated timestamp would rewrite the file on every run - this is the date the DHIS2
#: identifier-system convention was fixed, so regeneration stays byte-stable.
_IDENTIFIER_SYSTEM_DECLARED_DATE = "2026-08-01"

#: The `CapabilityStatement.date` the capture server carries. R4 makes the element mandatory and
#: a generated timestamp would rewrite the file on every run, so the date is pinned for the same
#: byte-stability reason the NamingSystem declarations pin theirs.
_CAPTURE_SERVER_DECLARED_DATE = "2026-01-01"

#: The resources a capture client reads to build a response, each supporting read and search.
CAPTURE_SERVER_READ_RESOURCE_TYPES = ("Questionnaire", "CodeSystem", "ValueSet", "Location", "Organization")

#: What `CapabilityStatement.rest.documentation` states about the shape of one capture request.
_CAPTURE_SERVER_REST_DOCUMENTATION = (
    "One QuestionnaireResponse per request: a capture client posts a single response per form "
    "submission, and the server accepts exactly one response per request."
)

#: The capture server's own page metadata.
_CAPTURE_SERVER_TITLE = "DHIS2 capture server"
_CAPTURE_SERVER_DESCRIPTION = (
    "The interactions a server capturing DHIS2 data as QuestionnaireResponses supports: one "
    "response created per request, against the aggregate or the event response profile, plus "
    "read and search over the definitional resources a capture client resolves a form from."
)

_ENVIRONMENT = Environment(
    loader=PackageLoader("dhis2w_fhir.foundation", "templates"),
    autoescape=select_autoescape(default=False),
    undefined=StrictUndefined,
    keep_trailing_newline=True,
    trim_blocks=True,
    lstrip_blocks=True,
)


def build_foundation_artifacts(config: GenerateConfig, *, ig_status: IgStatus) -> list[FshArtifact]:
    """Build the `foundation/` artifacts: the DHIS2 identifier systems and the D2Period extension."""
    names = FoundationNaming.from_naming(config.naming)
    experimental = experimental_for_status(ig_status)
    aliases = _ENVIRONMENT.get_template("d2-aliases.fsh.jinja").render(
        identifier_system_base=config.identifier_system_base
    )
    naming_systems = _ENVIRONMENT.get_template("d2-naming-systems.fsh.jinja").render(
        naming_systems=build_naming_system_declarations(config),
        declared_date=_IDENTIFIER_SYSTEM_DECLARED_DATE,
        ig_status=ig_status,
    )
    period = _ENVIRONMENT.get_template("d2-period.fsh.jinja").render(
        names=names, period_types=PERIOD_TYPE_DEFINITIONS, ig_status=ig_status, experimental=experimental
    )
    form_type = _ENVIRONMENT.get_template("d2-form-type.fsh.jinja").render(
        names=names, form_types=FORM_TYPE_DEFINITIONS, ig_status=ig_status, experimental=experimental
    )
    responses = _ENVIRONMENT.get_template("d2-responses.fsh.jinja").render(
        names=names,
        profiles=build_response_profile_declarations(config),
        location_profile=OrganisationUnitNaming.from_naming(config.naming).location_profile,
        ig_status=ig_status,
        experimental=experimental,
    )
    capture_server = _ENVIRONMENT.get_template("d2-capture-server.fsh.jinja").render(
        names=names,
        title_literal=page_text(_CAPTURE_SERVER_TITLE),
        description_literal=page_text(_CAPTURE_SERVER_DESCRIPTION),
        rest_documentation=_CAPTURE_SERVER_REST_DOCUMENTATION,
        read_resource_types=CAPTURE_SERVER_READ_RESOURCE_TYPES,
        declared_date=_CAPTURE_SERVER_DECLARED_DATE,
        ig_status=ig_status,
        experimental=experimental,
    )
    return [
        FshArtifact(
            relative_path="foundation/d2-aliases.fsh",
            kind="aliases",
            fsh_name="DHIS2 identifier aliases",
            content=aliases,
        ),
        FshArtifact(
            relative_path="foundation/d2-naming-systems.fsh",
            kind="instances",
            fsh_name="DHIS2 identifier systems",
            content=naming_systems,
        ),
        FshArtifact(
            relative_path="foundation/d2-period.fsh",
            kind="extension",
            fsh_name=names.period_extension,
            content=period,
        ),
        FshArtifact(
            relative_path="foundation/d2-form-type.fsh",
            kind="extension",
            fsh_name=names.form_type_extension,
            content=form_type,
        ),
        FshArtifact(
            relative_path="foundation/d2-responses.fsh",
            kind="profile",
            fsh_name=names.aggregate_response_profile,
            content=responses,
        ),
        FshArtifact(
            relative_path="foundation/d2-capture-server.fsh",
            kind="instances",
            fsh_name=names.capture_server,
            content=capture_server,
        ),
    ]


def build_response_profile_declarations(config: GenerateConfig) -> list[ResponseProfileDeclaration]:
    """Declare the QuestionnaireResponse contract per form kind: the aggregate one, then the event one."""
    names = FoundationNaming.from_naming(config.naming)
    return [
        ResponseProfileDeclaration(
            name=names.aggregate_response_profile,
            profile_id=names.aggregate_response_profile_id,
            form_type_code="aggregate",
            title="DHIS2 aggregate response",
            description=(
                "One submission of a DHIS2 data set form: the values captured for one organisation unit "
                "and one reporting period, answered on the linkIds of the data set's Questionnaire."
            ),
            period_required=True,
        ),
        ResponseProfileDeclaration(
            name=names.event_response_profile,
            profile_id=names.event_response_profile_id,
            form_type_code="event",
            title="DHIS2 event response",
            description=(
                "One submission of a DHIS2 event program form: the values captured for one event at one "
                "organisation unit, answered on the linkIds of the event program's Questionnaire."
            ),
            authored_required=True,
        ),
    ]


def build_naming_system_declarations(config: GenerateConfig) -> list[NamingSystemDeclaration]:
    """Declare every DHIS2 identifier system: a UID system and a code system per object kind."""
    prefix = FoundationNaming.from_naming(config.naming).definition_prefix
    base = config.identifier_system_base
    declarations: list[NamingSystemDeclaration] = []
    for subject in IDENTIFIER_SYSTEM_SUBJECTS:
        declarations.append(
            NamingSystemDeclaration(
                name=f"{prefix}{subject.token}IdentifierSystem",
                title=f"DHIS2 {subject.label} UIDs",
                description=(
                    f"The identifier system for DHIS2 {subject.label} UIDs. Every generated artifact "
                    f"representing a DHIS2 {subject.label} carries the source object's UID under this system."
                ),
                url=f"{base}/id/{subject.segment}",
            )
        )
        declarations.append(
            NamingSystemDeclaration(
                name=f"{prefix}{subject.token}CodeIdentifierSystem",
                title=f"DHIS2 {subject.label} codes",
                description=(
                    f"The identifier system for DHIS2 {subject.label} codes. DHIS2 codes are optional, so this "
                    f"slot repeats the UID whenever the {subject.label} has no code or its code is not a valid "
                    "FHIR code."
                ),
                url=f"{base}/id/{subject.segment}-code",
            )
        )
    return declarations
