"""FSH emission for the foundation layer: the DHIS2 identifier systems, D2Period, and the capture contract.

These artifacts depend on `fhir.toml` alone, never on a DHIS2 instance. `d2-aliases.fsh`
turns `[generate] identifier_system_base` into the `$DHIS2-*` aliases every instance file
references; `d2-naming-systems.fsh` declares each of those URLs as a NamingSystem, so a
consumer meeting a DHIS2 identifier can resolve what it means; `d2-period.fsh` defines the
reporting-period Extension plus the period-type CodeSystem/ValueSet backing its required
binding; `d2-form-type.fsh` defines the form-type Extension every generated Questionnaire
carries, plus its own CodeSystem/ValueSet pair; `d2-attribute-value.fsh` defines the complex
Extension that carries a DHIS2 attribute value onto every resource that can hold one;
`d2-organisation-unit.fsh` defines the Extension pointing a response at the Location of the
organisation unit it was captured at, `d2-organisation-unit-assignment.fsh` the Extension
naming the List of Locations a form may be captured against, `d2-organisation-unit-level.fsh`
the Extension stating the hierarchy level a published Location sits at,
`d2-attribute-option-combos.fsh` the Extension naming the ValueSet of attribute option combos
a form's responses may be keyed under, `d2-attribute-option-combo.fsh` the Extension carrying
the one an aggregate response was captured under, `d2-tracker-enrollment.fsh` the Extension
carrying the DHIS2 tracker enrollment a response belongs to, and `d2-enrollment-dates.fsh` the
two Extensions dating that enrollment - when it began, and when the incident it follows occurred.

Three more artifacts turn that vocabulary into a capture contract a third party can build
against without reading DHIS2: `d2-responses.fsh` profiles the QuestionnaireResponse a
capture client sends - one profile per form kind, each pinning the context the response has
to carry - `d2-capture-server.fsh` states the interactions a server accepting those
responses supports, and `d2-generate-operation.fsh` defines `$generate`, the instance-level
operation that answers a served Questionnaire with a synthetic response postable straight back.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from jinja2 import Environment, PackageLoader, StrictUndefined, select_autoescape

from dhis2w_fhir.foundation.attribute_values import (
    ATTRIBUTE_CODE_SUB_EXTENSION,
    ATTRIBUTE_ID_SUB_EXTENSION,
    ATTRIBUTE_VALUE_CONTEXT_RESOURCE_TYPES,
    ATTRIBUTE_VALUE_SUB_EXTENSION,
    attribute_value_extension_url,
    attribute_value_extensions,
)
from dhis2w_fhir.foundation.schemas import (
    FORM_TYPE_DEFINITIONS,
    GENERATE_OPERATION_CODE,
    GENERATE_SEED_PARAMETER,
    IDENTIFIER_SYSTEM_SUBJECTS,
    FormTypeDefinition,
    FoundationNaming,
    NamingSystemDeclaration,
    ResponseProfileDeclaration,
)
from dhis2w_fhir.names import page_text
from dhis2w_fhir.period.schemas import PERIOD_TYPE_DEFINITIONS
from dhis2w_fhir.resources.organisation_units.naming import OrganisationUnitNaming
from dhis2w_fhir.resources.questionnaires.schemas import CAPTURED_FORM_KINDS
from dhis2w_fhir.status import IgStatus, experimental_for_status
from dhis2w_fhir.writer import FshArtifact

if TYPE_CHECKING:
    from dhis2w_fhir.config import GenerateConfig

__all__ = [
    "ATTRIBUTE_CODE_SUB_EXTENSION",
    "ATTRIBUTE_ID_SUB_EXTENSION",
    "ATTRIBUTE_VALUE_CONTEXT_RESOURCE_TYPES",
    "ATTRIBUTE_VALUE_SUB_EXTENSION",
    "CAPTURE_SERVER_READ_RESOURCE_TYPES",
    "FORM_TYPE_DEFINITIONS",
    "GENERATE_OPERATION_CODE",
    "GENERATE_SEED_PARAMETER",
    "FormTypeDefinition",
    "FoundationNaming",
    "NamingSystemDeclaration",
    "ResponseProfileDeclaration",
    "attribute_value_extension_url",
    "attribute_value_extensions",
    "build_captured_response_profile_declarations",
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

#: The resources a capture client reads to build a response, each supporting read and search. `List`
#: is where a form's organisation-unit assignment is published, so a client constrains its Location
#: picker by reading the List the form's `D2OrganisationUnitAssignment` extension names.
CAPTURE_SERVER_READ_RESOURCE_TYPES = (
    "Questionnaire",
    "CodeSystem",
    "ValueSet",
    "Location",
    "Organization",
    "List",
)

#: What `CapabilityStatement.rest.documentation` states about the shape of one capture request.
_CAPTURE_SERVER_REST_DOCUMENTATION = (
    "One QuestionnaireResponse per request: a capture client posts a single response per form "
    "submission, and the server accepts exactly one response per request."
)

#: The `OperationDefinition.date` the `$generate` operation carries, pinned for the same
#: byte-stability reason the NamingSystem declarations and the capture server pin theirs.
_GENERATE_OPERATION_DECLARED_DATE = "2026-08-01"

#: The `$generate` operation's own page metadata.
_GENERATE_OPERATION_TITLE = "Generate a synthetic response"
_GENERATE_OPERATION_DESCRIPTION = (
    "Generate one synthetic QuestionnaireResponse against a served Questionnaire: every question "
    "answered with a value its own type, bounds, and terminology binding admit, in the context its "
    "form kind's response profile requires. The generated response is immediately postable to the "
    "same server's QuestionnaireResponse endpoint, which is what a capture client's fill-with-test-data "
    "button and an API-driven stress corpus both need."
)
_GENERATE_OPERATION_COMMENT = (
    "This is a custom operation, not SDC's $populate. $populate means fill this form from real "
    "context about a real subject; $generate invents data, and the two must never be confused."
)
_GENERATE_SEED_DOCUMENTATION = (
    "The seed the generated values are drawn from. The same seed against the same served form "
    "returns the same response, so a client can reproduce a submission by naming its seed. Absent, "
    "the server draws one and states it on the generated response's identifier."
)
_GENERATE_RETURN_DOCUMENTATION = (
    "The generated QuestionnaireResponse, declaring the response profile of the form's own DHIS2 "
    "form kind and identified by the seed it was generated from."
)

#: The capture server's own page metadata.
_CAPTURE_SERVER_TITLE = "DHIS2 capture server"
_CAPTURE_SERVER_DESCRIPTION = (
    "The interactions a server capturing DHIS2 data as QuestionnaireResponses supports: one "
    "response created per request, against the aggregate, event, or tracker event response "
    "profile, plus read and search over the definitional resources a capture client resolves "
    "a form from."
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
    organisation_unit_naming = OrganisationUnitNaming.from_naming(config.naming)
    location_profile = organisation_unit_naming.location_profile
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
    attribute_value = _ENVIRONMENT.get_template("d2-attribute-value.fsh.jinja").render(
        names=names,
        context_resource_types=ATTRIBUTE_VALUE_CONTEXT_RESOURCE_TYPES,
        attribute_id_sub_extension=ATTRIBUTE_ID_SUB_EXTENSION,
        attribute_code_sub_extension=ATTRIBUTE_CODE_SUB_EXTENSION,
        attribute_value_sub_extension=ATTRIBUTE_VALUE_SUB_EXTENSION,
        ig_status=ig_status,
        experimental=experimental,
    )
    organisation_unit = _ENVIRONMENT.get_template("d2-organisation-unit.fsh.jinja").render(
        names=names,
        location_profile=location_profile,
        ig_status=ig_status,
        experimental=experimental,
    )
    organisation_unit_assignment = _ENVIRONMENT.get_template("d2-organisation-unit-assignment.fsh.jinja").render(
        names=names,
        ig_status=ig_status,
        experimental=experimental,
    )
    attribute_option_combo = _ENVIRONMENT.get_template("d2-attribute-option-combo.fsh.jinja").render(
        names=names,
        ig_status=ig_status,
        experimental=experimental,
    )
    attribute_option_combos = _ENVIRONMENT.get_template("d2-attribute-option-combos.fsh.jinja").render(
        names=names,
        ig_status=ig_status,
        experimental=experimental,
    )
    organisation_unit_level = _ENVIRONMENT.get_template("d2-organisation-unit-level.fsh.jinja").render(
        names=names,
        level_value_set=organisation_unit_naming.level_value_set,
        ig_status=ig_status,
        experimental=experimental,
    )
    tracker_enrollment = _ENVIRONMENT.get_template("d2-tracker-enrollment.fsh.jinja").render(
        names=names,
        enrollment_system=f"{config.identifier_system_base}/id/tracker-enrollment",
        ig_status=ig_status,
        experimental=experimental,
    )
    enrollment_dates = _ENVIRONMENT.get_template("d2-enrollment-dates.fsh.jinja").render(
        names=names,
        ig_status=ig_status,
        experimental=experimental,
    )
    responses = _ENVIRONMENT.get_template("d2-responses.fsh.jinja").render(
        names=names,
        profiles=build_response_profile_declarations(config),
        location_profile=location_profile,
        tracked_entity_system=f"{config.identifier_system_base}/id/tracked-entity",
        ig_status=ig_status,
        experimental=experimental,
    )
    generate_operation = _ENVIRONMENT.get_template("d2-generate-operation.fsh.jinja").render(
        names=names,
        title_literal=page_text(_GENERATE_OPERATION_TITLE),
        description_literal=page_text(_GENERATE_OPERATION_DESCRIPTION),
        comment=_GENERATE_OPERATION_COMMENT,
        operation_code=GENERATE_OPERATION_CODE,
        seed_parameter=GENERATE_SEED_PARAMETER,
        seed_documentation=_GENERATE_SEED_DOCUMENTATION,
        return_documentation=_GENERATE_RETURN_DOCUMENTATION,
        declared_date=_GENERATE_OPERATION_DECLARED_DATE,
        ig_status=ig_status,
        experimental=experimental,
    )
    capture_server = _ENVIRONMENT.get_template("d2-capture-server.fsh.jinja").render(
        names=names,
        profiles=build_captured_response_profile_declarations(config),
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
            relative_path="foundation/d2-attribute-value.fsh",
            kind="extension",
            fsh_name=names.attribute_value_extension,
            content=attribute_value,
        ),
        FshArtifact(
            relative_path="foundation/d2-organisation-unit.fsh",
            kind="extension",
            fsh_name=names.organisation_unit_extension,
            content=organisation_unit,
        ),
        FshArtifact(
            relative_path="foundation/d2-organisation-unit-assignment.fsh",
            kind="extension",
            fsh_name=names.organisation_unit_assignment_extension,
            content=organisation_unit_assignment,
        ),
        FshArtifact(
            relative_path="foundation/d2-attribute-option-combo.fsh",
            kind="extension",
            fsh_name=names.attribute_option_combo_extension,
            content=attribute_option_combo,
        ),
        FshArtifact(
            relative_path="foundation/d2-attribute-option-combos.fsh",
            kind="extension",
            fsh_name=names.attribute_option_combos_extension,
            content=attribute_option_combos,
        ),
        FshArtifact(
            relative_path="foundation/d2-organisation-unit-level.fsh",
            kind="extension",
            fsh_name=names.organisation_unit_level_extension,
            content=organisation_unit_level,
        ),
        FshArtifact(
            relative_path="foundation/d2-tracker-enrollment.fsh",
            kind="extension",
            fsh_name=names.tracker_enrollment_extension,
            content=tracker_enrollment,
        ),
        FshArtifact(
            relative_path="foundation/d2-enrollment-dates.fsh",
            kind="extension",
            fsh_name=names.enrolled_at_extension,
            content=enrollment_dates,
        ),
        FshArtifact(
            relative_path="foundation/d2-responses.fsh",
            kind="profile",
            fsh_name=names.aggregate_response_profile,
            content=responses,
        ),
        FshArtifact(
            relative_path="foundation/d2-generate-operation.fsh",
            kind="instances",
            fsh_name=names.generate_operation,
            content=generate_operation,
        ),
        FshArtifact(
            relative_path="foundation/d2-capture-server.fsh",
            kind="instances",
            fsh_name=names.capture_server,
            content=capture_server,
        ),
    ]


def build_response_profile_declarations(config: GenerateConfig) -> list[ResponseProfileDeclaration]:
    """Declare the QuestionnaireResponse contract per form kind, in the order D2FormType_CS lists them."""
    names = FoundationNaming.from_naming(config.naming)
    return [
        ResponseProfileDeclaration(
            name=names.aggregate_response_profile,
            profile_id=names.aggregate_response_profile_id,
            form_type_code="aggregate",
            title="DHIS2 aggregate response",
            description=(
                "One submission of a DHIS2 data set form: the values captured for one organisation unit, "
                "one reporting period, and one attribute option combo, answered on the linkIds of the data "
                "set's Questionnaire."
            ),
            period_required=True,
            attribute_option_combo_allowed=True,
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
        ResponseProfileDeclaration(
            name=names.tracker_registration_response_profile,
            profile_id=names.tracker_registration_response_profile_id,
            form_type_code="tracker",
            title="DHIS2 tracker registration response",
            description=(
                "One submission of a DHIS2 tracker program's registration form: the tracked entity attributes "
                "captured when a person is enrolled, answered on the linkIds of the program's Questionnaire. "
                "The response mints both DHIS2 identities it creates - the tracked entity it is subject to and "
                "the enrollment its extension names - so a client can capture the enrollment's first stage "
                "events in the same breath, before either identity exists on the instance."
            ),
            authored_required=True,
            registration_context_required=True,
        ),
        ResponseProfileDeclaration(
            name=names.tracker_event_response_profile,
            profile_id=names.tracker_event_response_profile_id,
            form_type_code="tracker-event",
            title="DHIS2 tracker event response",
            description=(
                "One submission of a DHIS2 tracker program stage form: the values captured for one event of "
                "one enrollment, answered on the linkIds of the stage's Questionnaire and subject to the "
                "tracked entity by identifier."
            ),
            authored_required=True,
            tracker_context_required=True,
        ),
    ]


def build_captured_response_profile_declarations(config: GenerateConfig) -> list[ResponseProfileDeclaration]:
    """The response contracts a capture server states support for - the ones it can translate into DHIS2 today.

    Narrower than `build_response_profile_declarations` for the reason `CAPTURED_FORM_KINDS` is
    narrower than `FORM_KIND_PROFILES`: the registration contract is published so a client can
    build against it, and a CapabilityStatement claiming an interaction no server performs would
    be a lie about the running facade.
    """
    return [
        declaration
        for declaration in build_response_profile_declarations(config)
        if declaration.form_type_code in CAPTURED_FORM_KINDS
    ]


def build_naming_system_declarations(config: GenerateConfig) -> list[NamingSystemDeclaration]:
    """Declare every DHIS2 identifier system: a UID system per object kind, plus a code system where one exists."""
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
        if not subject.has_code:
            continue
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
