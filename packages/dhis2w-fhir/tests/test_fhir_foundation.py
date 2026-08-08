"""Golden tests for the foundation artifacts: the DHIS2 identifier aliases and the D2Period extension."""

from dhis2w_fhir.config import GenerateConfig, NamingConfig
from dhis2w_fhir.foundation import CAPTURE_SERVER_READ_RESOURCE_TYPES, FoundationNaming, build_foundation_artifacts
from dhis2w_fhir.period import PERIOD_TYPE_DEFINITIONS
from dhis2w_fhir.status import IgStatus


def _by_path(config: GenerateConfig, *, ig_status: IgStatus = "draft") -> dict[str, str]:
    """Build the foundation artifacts and index them by relative path."""
    artifacts = build_foundation_artifacts(config, ig_status=ig_status)
    return {artifact.relative_path: artifact.content for artifact in artifacts}


#: The DHIS2 identifier systems declared: a UID system per object kind, plus a code system for the
#: nine kinds that carry a DHIS2 code.
_IDENTIFIER_SYSTEM_COUNT = 20


def test_foundation_covers_expected_files() -> None:
    """The target emits the aliases, the NamingSystems, the five extensions, and the capture contract."""
    assert set(_by_path(GenerateConfig())) == {
        "foundation/d2-aliases.fsh",
        "foundation/d2-naming-systems.fsh",
        "foundation/d2-period.fsh",
        "foundation/d2-form-type.fsh",
        "foundation/d2-attribute-value.fsh",
        "foundation/d2-organisation-unit.fsh",
        "foundation/d2-tracker-enrollment.fsh",
        "foundation/d2-responses.fsh",
        "foundation/d2-capture-server.fsh",
    }


def test_aliases_come_from_the_configured_identifier_base() -> None:
    """The DHIS2 identifier aliases are derived from `[generate] identifier_system_base`."""
    default = _by_path(GenerateConfig())["foundation/d2-aliases.fsh"]
    assert "Alias: $DHIS2-OU = http://dhis2.org/fhir/id/org-unit" in default
    assert "Alias: $DHIS2-OU-CODE = http://dhis2.org/fhir/id/org-unit-code" in default
    assert "Alias: $DHIS2-OS = http://dhis2.org/fhir/id/option-set" in default
    assert "Alias: $DHIS2-OS-CODE = http://dhis2.org/fhir/id/option-set-code" in default
    assert "Alias: $DHIS2-OPTION = http://dhis2.org/fhir/id/option" in default
    assert "Alias: $DHIS2-OPTION-CODE = http://dhis2.org/fhir/id/option-code" in default
    custom = _by_path(GenerateConfig(identifier_system_base="https://example.org/dhis2/"))
    aliases = custom["foundation/d2-aliases.fsh"]
    assert "Alias: $DHIS2-OU = https://example.org/dhis2/id/org-unit" in aliases
    assert "Alias: $DHIS2-OU-CODE = https://example.org/dhis2/id/org-unit-code" in aliases
    assert "Alias: $DHIS2-OS = https://example.org/dhis2/id/option-set" in aliases


def test_data_definition_aliases_are_emitted() -> None:
    """The questionnaire target's identifier systems are aliased alongside the terminology ones."""
    aliases = _by_path(GenerateConfig())["foundation/d2-aliases.fsh"]
    assert "Alias: $DHIS2-DS = http://dhis2.org/fhir/id/data-set" in aliases
    assert "Alias: $DHIS2-DS-CODE = http://dhis2.org/fhir/id/data-set-code" in aliases
    assert "Alias: $DHIS2-PROGRAM = http://dhis2.org/fhir/id/program" in aliases
    assert "Alias: $DHIS2-PROGRAM-CODE = http://dhis2.org/fhir/id/program-code" in aliases
    assert "Alias: $DHIS2-DE = http://dhis2.org/fhir/id/data-element" in aliases
    assert "Alias: $DHIS2-COC = http://dhis2.org/fhir/id/category-option-combo" in aliases


def test_tracker_aliases_are_emitted() -> None:
    """The tracker capture contract's identifier systems are aliased alongside the aggregate ones."""
    aliases = _by_path(GenerateConfig())["foundation/d2-aliases.fsh"]
    assert "Alias: $DHIS2-PS = http://dhis2.org/fhir/id/program-stage" in aliases
    assert "Alias: $DHIS2-PS-CODE = http://dhis2.org/fhir/id/program-stage-code" in aliases
    assert "Alias: $DHIS2-TE = http://dhis2.org/fhir/id/tracked-entity" in aliases
    assert "Alias: $DHIS2-TRACKER-ENROLLMENT = http://dhis2.org/fhir/id/tracker-enrollment" in aliases


def test_naming_systems_declare_every_identifier_system() -> None:
    """Each `$DHIS2-*` alias URL is declared by a NamingSystem, so consumers can resolve what it means."""
    content = _by_path(GenerateConfig())["foundation/d2-naming-systems.fsh"]
    assert content.count("InstanceOf: NamingSystem") == _IDENTIFIER_SYSTEM_COUNT
    assert content.count("* kind = #identifier") == _IDENTIFIER_SYSTEM_COUNT
    assert content.count("* uniqueId[0].preferred = true") == _IDENTIFIER_SYSTEM_COUNT
    assert "Instance: D2OrgUnitIdentifierSystem" in content
    assert "Instance: D2OrgUnitCodeIdentifierSystem" in content
    assert "Instance: D2OptionSetIdentifierSystem" in content
    assert "Instance: D2OptionSetCodeIdentifierSystem" in content
    assert "Instance: D2OptionIdentifierSystem" in content
    assert "Instance: D2OptionCodeIdentifierSystem" in content
    assert "Instance: D2DataSetIdentifierSystem" in content
    assert "Instance: D2ProgramCodeIdentifierSystem" in content
    assert "Instance: D2DataElementIdentifierSystem" in content
    assert "Instance: D2CategoryOptionComboIdentifierSystem" in content
    assert '* uniqueId[0].value = "http://dhis2.org/fhir/id/org-unit"' in content
    assert '* uniqueId[0].value = "http://dhis2.org/fhir/id/option-set-code"' in content
    assert '* uniqueId[0].value = "http://dhis2.org/fhir/id/option"' in content
    assert '* uniqueId[0].value = "http://dhis2.org/fhir/id/option-code"' in content
    assert '* uniqueId[0].value = "http://dhis2.org/fhir/id/data-set"' in content
    assert '* uniqueId[0].value = "http://dhis2.org/fhir/id/category-option-combo"' in content
    assert "this slot repeats the UID" in content


def test_naming_systems_declare_a_code_system_only_where_dhis2_has_one() -> None:
    """Metadata kinds get a UID and a code system; a tracked entity and a tracker enrollment get the UID alone."""
    content = _by_path(GenerateConfig())["foundation/d2-naming-systems.fsh"]
    assert "Instance: D2ProgramStageIdentifierSystem" in content
    assert "Instance: D2ProgramStageCodeIdentifierSystem" in content
    assert "Instance: D2TrackedEntityIdentifierSystem" in content
    assert "Instance: D2TrackerEnrollmentIdentifierSystem" in content
    assert "Instance: D2TrackedEntityCodeIdentifierSystem" not in content
    assert "Instance: D2TrackerEnrollmentCodeIdentifierSystem" not in content
    assert '* uniqueId[0].value = "http://dhis2.org/fhir/id/program-stage"' in content
    assert '* uniqueId[0].value = "http://dhis2.org/fhir/id/program-stage-code"' in content
    assert '* uniqueId[0].value = "http://dhis2.org/fhir/id/tracked-entity"' in content
    assert '* uniqueId[0].value = "http://dhis2.org/fhir/id/tracker-enrollment"' in content
    assert '* uniqueId[0].value = "http://dhis2.org/fhir/id/tracked-entity-code"' not in content
    assert '* uniqueId[0].value = "http://dhis2.org/fhir/id/tracker-enrollment-code"' not in content


def test_naming_system_date_is_fixed_so_regeneration_is_byte_stable() -> None:
    """R4 makes NamingSystem.date mandatory; a pinned date keeps a no-op regenerate from rewriting the file."""
    first = _by_path(GenerateConfig())["foundation/d2-naming-systems.fsh"]
    second = _by_path(GenerateConfig())["foundation/d2-naming-systems.fsh"]
    assert first == second
    assert first.count('* date = "2026-08-01"') == _IDENTIFIER_SYSTEM_COUNT


def test_form_type_extension_binds_both_questionnaire_resources() -> None:
    """D2FormType is contexted on Questionnaire and QuestionnaireResponse with a required code binding."""
    form_type = _by_path(GenerateConfig())["foundation/d2-form-type.fsh"]
    assert "Extension: D2FormType" in form_type
    assert "Id: d2-form-type" in form_type
    assert '* ^context[=].expression = "Questionnaire"' in form_type
    assert '* ^context[=].expression = "QuestionnaireResponse"' in form_type
    assert form_type.count("* ^context[+].type = #element") == 2
    assert "* value[x] only code" in form_type
    assert "* valueCode 1..1" in form_type
    assert "* valueCode from D2FormType_VS (required)" in form_type


def test_form_type_terminology_covers_every_form_kind() -> None:
    """The form-type pair publishes all four DHIS2 form kinds and points back at its ValueSet."""
    form_type = _by_path(GenerateConfig())["foundation/d2-form-type.fsh"]
    assert "CodeSystem: D2FormType_CS" in form_type
    assert "Id: d2-form-type-cs" in form_type
    assert "* ^valueSet = Canonical(D2FormType_VS)" in form_type
    assert form_type.count("* ^experimental = true") == 3
    assert '* #aggregate "Aggregate data set form"' in form_type
    assert '* #event "Event program form"' in form_type
    assert '* #tracker "Tracker registration form"' in form_type
    assert '* #tracker-event "Tracker program stage form"' in form_type
    assert "ValueSet: D2FormType_VS" in form_type
    assert "Id: d2-form-type-vs" in form_type
    assert "* include codes from system D2FormType_CS" in form_type


def test_period_artifacts_derive_their_publication_state_from_the_ig_status() -> None:
    """The extension and its period-type pair carry ^status and ^experimental straight off `[ig] status`."""
    draft = _by_path(GenerateConfig())["foundation/d2-period.fsh"]
    assert draft.count("* ^status = #draft") == 3
    assert draft.count("* ^experimental = true") == 3
    active = _by_path(GenerateConfig(), ig_status="active")["foundation/d2-period.fsh"]
    assert active.count("* ^status = #active") == 3
    assert active.count("* ^experimental = false") == 3
    assert "* ^status = #draft" not in active
    assert "* ^experimental = true" not in active


def test_form_type_artifacts_derive_their_publication_state_from_the_ig_status() -> None:
    """The form-type extension and its pair follow the same derivation."""
    draft = _by_path(GenerateConfig())["foundation/d2-form-type.fsh"]
    assert draft.count("* ^status = #draft") == 3
    assert draft.count("* ^experimental = true") == 3
    active = _by_path(GenerateConfig(), ig_status="active")["foundation/d2-form-type.fsh"]
    assert active.count("* ^status = #active") == 3
    assert active.count("* ^experimental = false") == 3


def test_naming_systems_derive_their_status_from_the_ig_status() -> None:
    """NamingSystem.status shares the publication-status codes, so it follows `[ig] status` too."""
    draft = _by_path(GenerateConfig())["foundation/d2-naming-systems.fsh"]
    assert draft.count("* status = #draft") == _IDENTIFIER_SYSTEM_COUNT
    active = _by_path(GenerateConfig(), ig_status="active")["foundation/d2-naming-systems.fsh"]
    assert active.count("* status = #active") == _IDENTIFIER_SYSTEM_COUNT


def test_naming_systems_carry_no_experimental_element() -> None:
    """R4 NamingSystem has no experimental element, so the declarations must not grow one."""
    assert "experimental" not in _by_path(GenerateConfig())["foundation/d2-naming-systems.fsh"]


def test_period_extension_shape() -> None:
    """D2Period is contexted on the two resources that carry it, with iso/type/period and a required binding."""
    period = _by_path(GenerateConfig())["foundation/d2-period.fsh"]
    assert "Extension: D2Period" in period
    assert "Id: d2-period" in period
    assert 'Title: "DHIS2 reporting period"' in period
    assert period.count("* ^context[+].type = #element") == 2
    assert '* ^context[=].expression = "QuestionnaireResponse"' in period
    assert '* ^context[=].expression = "MeasureReport"' in period
    assert '* ^context[=].expression = "Element"' not in period
    assert "    iso 1..1 and" in period
    assert "    type 1..1 and" in period
    assert "    period 0..1" in period
    assert "* extension[iso].value[x] only string" in period
    assert "* extension[type].valueCode from D2PeriodType_VS (required)" in period
    assert "* extension[period].value[x] only Period" in period


def test_period_type_terminology_lists_every_type() -> None:
    """The period-type CodeSystem publishes every registered type and points back at its ValueSet."""
    period = _by_path(GenerateConfig())["foundation/d2-period.fsh"]
    assert "CodeSystem: D2PeriodType_CS" in period
    assert "Id: d2-period-type-cs" in period
    assert "* ^valueSet = Canonical(D2PeriodType_VS)" in period
    assert "ValueSet: D2PeriodType_VS" in period
    assert "Id: d2-period-type-vs" in period
    for definition in PERIOD_TYPE_DEFINITIONS:
        assert f'* #{definition.name} "{definition.display}"' in period
    assert "* ^identifier[" not in period


_AGGREGATE_RESPONSE_GOLDEN = """Profile: D2AggregateResponse
Parent: QuestionnaireResponse
Id: d2-aggregate-response
Title: "DHIS2 aggregate response"
Description: "One submission of a DHIS2 data set form: the values captured for one organisation \
unit and one reporting period, answered on the linkIds of the data set's Questionnaire."
* ^status = #draft
* ^experimental = true
* extension contains
    D2Period named D2Period 1..1 and
    D2FormType named D2FormType 1..1
* extension[D2Period] ^short = "The DHIS2 reporting period the values were captured for."
* extension[D2FormType] ^short = "The DHIS2 form kind this response answers."
* extension[D2FormType].valueCode = #aggregate (exactly)
* questionnaire 1..1
* subject 1..1
* subject only Reference(D2Location)
"""

_EVENT_RESPONSE_GOLDEN = """Profile: D2EventResponse
Parent: QuestionnaireResponse
Id: d2-event-response
Title: "DHIS2 event response"
Description: "One submission of a DHIS2 event program form: the values captured for one event \
at one organisation unit, answered on the linkIds of the event program's Questionnaire."
* ^status = #draft
* ^experimental = true
* extension contains D2FormType named D2FormType 1..1
* extension[D2FormType] ^short = "The DHIS2 form kind this response answers."
* extension[D2FormType].valueCode = #event (exactly)
* questionnaire 1..1
* subject 1..1
* subject only Reference(D2Location)
* authored 1..1
"""

_TRACKER_EVENT_RESPONSE_GOLDEN = """Profile: D2TrackerEventResponse
Parent: QuestionnaireResponse
Id: d2-tracker-event-response
Title: "DHIS2 tracker event response"
Description: "One submission of a DHIS2 tracker program stage form: the values captured for one event \
of one enrollment, answered on the linkIds of the stage's Questionnaire and subject to the tracked \
entity by identifier."
* ^status = #draft
* ^experimental = true
* extension contains
    D2OrganisationUnit named D2OrganisationUnit 1..1 and
    D2TrackerEnrollment named D2TrackerEnrollment 1..1 and
    D2FormType named D2FormType 1..1
* extension[D2OrganisationUnit] ^short = "The DHIS2 organisation unit the event was captured at."
* extension[D2TrackerEnrollment] ^short = "The DHIS2 tracker enrollment the event belongs to."
* extension[D2FormType] ^short = "The DHIS2 form kind this response answers."
* extension[D2FormType].valueCode = #tracker-event (exactly)
* questionnaire 1..1
* subject 1..1
* subject only Reference(Patient)
* subject.identifier 1..1
* subject.identifier.system 1..1
* subject.identifier.system = "http://dhis2.org/fhir/id/tracked-entity" (exactly)
* subject.identifier.value 1..1
* authored 1..1
"""


def test_the_three_response_profiles_are_stable_goldens() -> None:
    """All three halves of the capture contract are emitted verbatim into one foundation file."""
    responses = _by_path(GenerateConfig())["foundation/d2-responses.fsh"]
    assert responses == "\n".join((_AGGREGATE_RESPONSE_GOLDEN, _EVENT_RESPONSE_GOLDEN, _TRACKER_EVENT_RESPONSE_GOLDEN))


def test_the_response_profiles_pin_the_context_a_capture_client_has_to_send() -> None:
    """Each profile makes its own form kind's context mandatory and fixes the form-type code."""
    responses = _by_path(GenerateConfig())["foundation/d2-responses.fsh"]
    aggregate, _, rest = responses.partition("Profile: D2EventResponse")
    event, _, tracker_event = rest.partition("Profile: D2TrackerEventResponse")
    assert "D2Period named D2Period 1..1" in aggregate
    assert "* extension[D2FormType].valueCode = #aggregate (exactly)" in aggregate
    assert "* authored 1..1" not in aggregate
    assert "D2Period" not in event
    assert "* extension[D2FormType].valueCode = #event (exactly)" in event
    assert "* authored 1..1" in event
    assert "D2Period" not in tracker_event
    assert "D2OrganisationUnit named D2OrganisationUnit 1..1" in tracker_event
    assert "D2TrackerEnrollment named D2TrackerEnrollment 1..1" in tracker_event
    assert "* extension[D2FormType].valueCode = #tracker-event (exactly)" in tracker_event
    assert "* authored 1..1" in tracker_event
    assert responses.count("* subject only Reference(D2Location)") == 2
    assert responses.count("* questionnaire 1..1") == 3


def test_the_tracker_event_response_subjects_the_tracked_entity_by_identifier() -> None:
    """The tracker-event response points at a Patient the IG never defines, resolved by tracked-entity UID."""
    responses = _by_path(GenerateConfig())["foundation/d2-responses.fsh"]
    _, _, tracker_event = responses.partition("Profile: D2TrackerEventResponse")
    assert "* subject only Reference(Patient)" in tracker_event
    assert "* subject.identifier 1..1" in tracker_event
    assert '* subject.identifier.system = "http://dhis2.org/fhir/id/tracked-entity" (exactly)' in tracker_event
    assert "* subject.identifier.value 1..1" in tracker_event
    assert "* subject only Reference(D2Location)" not in tracker_event
    custom = _by_path(GenerateConfig(identifier_system_base="https://example.org/dhis2/"))
    assert (
        '* subject.identifier.system = "https://example.org/dhis2/id/tracked-entity" (exactly)'
        in custom["foundation/d2-responses.fsh"]
    )


def test_the_response_profiles_derive_their_publication_state_from_the_ig_status() -> None:
    """Every profile carries ^status and ^experimental straight off `[ig] status`."""
    draft = _by_path(GenerateConfig())["foundation/d2-responses.fsh"]
    assert draft.count("* ^status = #draft") == 3
    assert draft.count("* ^experimental = true") == 3
    active = _by_path(GenerateConfig(), ig_status="active")["foundation/d2-responses.fsh"]
    assert active.count("* ^status = #active") == 3
    assert active.count("* ^experimental = false") == 3
    assert "* ^status = #draft" not in active
    assert "* ^experimental = true" not in active


_TRACKER_ENROLLMENT_EXTENSION_GOLDEN = """Extension: D2TrackerEnrollment
Id: d2-tracker-enrollment
Title: "DHIS2 tracker enrollment"
Description: "The DHIS2 tracker enrollment an event was captured under, carried as the enrollment UID."
* ^status = #draft
* ^experimental = true
* ^context[+].type = #element
* ^context[=].expression = "QuestionnaireResponse"
* value[x] only Identifier
* valueIdentifier 1..1
* valueIdentifier.system 1..1
* valueIdentifier.system = "http://dhis2.org/fhir/id/tracker-enrollment" (exactly)
* valueIdentifier.value 1..1
"""


def test_the_tracker_enrollment_extension_is_a_stable_golden() -> None:
    """D2TrackerEnrollment carries the enrollment UID under the pinned DHIS2 tracker-enrollment system."""
    assert _by_path(GenerateConfig())["foundation/d2-tracker-enrollment.fsh"] == _TRACKER_ENROLLMENT_EXTENSION_GOLDEN


def test_the_tracker_enrollment_extension_system_follows_the_configured_identifier_base() -> None:
    """The exactly-bound system is derived from `[generate] identifier_system_base`, not hard-coded."""
    custom = _by_path(GenerateConfig(identifier_system_base="https://example.org/dhis2/"))
    assert (
        '* valueIdentifier.system = "https://example.org/dhis2/id/tracker-enrollment" (exactly)'
        in custom["foundation/d2-tracker-enrollment.fsh"]
    )


_ORGANISATION_UNIT_EXTENSION_GOLDEN = """Extension: D2OrganisationUnit
Id: d2-organisation-unit
Title: "DHIS2 organisation unit"
Description: "The DHIS2 organisation unit an event was captured at, as a reference to the unit's Location."
* ^status = #draft
* ^experimental = true
* ^context[+].type = #element
* ^context[=].expression = "QuestionnaireResponse"
* value[x] only Reference(D2Location)
* valueReference 1..1
"""


def test_the_organisation_unit_extension_is_a_stable_golden() -> None:
    """D2OrganisationUnit references the Location profile the org-unit target emits."""
    assert _by_path(GenerateConfig())["foundation/d2-organisation-unit.fsh"] == _ORGANISATION_UNIT_EXTENSION_GOLDEN


def test_the_new_extensions_derive_their_publication_state_from_the_ig_status() -> None:
    """The org-unit and tracker-enrollment extensions follow the same `[ig] status` dial every definition does."""
    active = _by_path(GenerateConfig(), ig_status="active")
    for path in ("foundation/d2-organisation-unit.fsh", "foundation/d2-tracker-enrollment.fsh"):
        assert "* ^status = #active" in active[path]
        assert "* ^experimental = false" in active[path]


_CAPTURE_SERVER_GOLDEN = """Instance: D2CaptureServer
InstanceOf: CapabilityStatement
Title: "DHIS2 capture server"
Description: "The interactions a server capturing DHIS2 data as QuestionnaireResponses supports: \
one response created per request, against the aggregate, event, or tracker event response profile, \
plus read and search over the definitional resources a capture client resolves a form from."
Usage: #definition
* id = "d2-capture-server"
* name = "D2CaptureServer"
* status = #draft
* experimental = true
// R4 makes CapabilityStatement.date mandatory. A generated timestamp would rewrite the file on
// every run, so the date is pinned and regeneration stays byte-stable.
* date = "2026-01-01"
* kind = #requirements
* fhirVersion = #4.0.1
* format[+] = #json
* rest.mode = #server
* rest.documentation = "One QuestionnaireResponse per request: a capture client posts a single \
response per form submission, and the server accepts exactly one response per request."
* rest.resource[+].type = #QuestionnaireResponse
* rest.resource[=].interaction[+].code = #create
* rest.resource[=].supportedProfile[+] = Canonical(D2AggregateResponse)
* rest.resource[=].supportedProfile[+] = Canonical(D2EventResponse)
* rest.resource[=].supportedProfile[+] = Canonical(D2TrackerEventResponse)
* rest.resource[+].type = #Questionnaire
* rest.resource[=].interaction[+].code = #read
* rest.resource[=].interaction[+].code = #search-type
* rest.resource[+].type = #CodeSystem
* rest.resource[=].interaction[+].code = #read
* rest.resource[=].interaction[+].code = #search-type
* rest.resource[+].type = #ValueSet
* rest.resource[=].interaction[+].code = #read
* rest.resource[=].interaction[+].code = #search-type
* rest.resource[+].type = #Location
* rest.resource[=].interaction[+].code = #read
* rest.resource[=].interaction[+].code = #search-type
* rest.resource[+].type = #Organization
* rest.resource[=].interaction[+].code = #read
* rest.resource[=].interaction[+].code = #search-type
"""


def test_the_capture_server_capability_statement_is_a_stable_golden() -> None:
    """The capture server states one create per response plus read/search over what a client resolves."""
    assert _by_path(GenerateConfig())["foundation/d2-capture-server.fsh"] == _CAPTURE_SERVER_GOLDEN


def test_the_capture_server_date_is_fixed_so_regeneration_is_byte_stable() -> None:
    """R4 makes CapabilityStatement.date mandatory; a pinned date keeps a no-op regenerate quiet."""
    first = _by_path(GenerateConfig())["foundation/d2-capture-server.fsh"]
    second = _by_path(GenerateConfig())["foundation/d2-capture-server.fsh"]
    assert first == second
    assert '* date = "2026-01-01"' in first


def test_the_capture_server_derives_its_publication_state_from_the_ig_status() -> None:
    """The CapabilityStatement follows the same `[ig] status` dial every definitional artifact does."""
    active = _by_path(GenerateConfig(), ig_status="active")["foundation/d2-capture-server.fsh"]
    assert "* status = #active" in active
    assert "* experimental = false" in active


def test_the_capture_server_reads_every_resource_a_client_resolves_a_form_from() -> None:
    """The read/search resources are exactly the declared list, so the page and the instance agree."""
    content = _by_path(GenerateConfig())["foundation/d2-capture-server.fsh"]
    for resource_type in CAPTURE_SERVER_READ_RESOURCE_TYPES:
        assert f"* rest.resource[+].type = #{resource_type}" in content
    assert content.count("* rest.resource[=].interaction[+].code = #read") == len(CAPTURE_SERVER_READ_RESOURCE_TYPES)
    assert content.count("* rest.resource[=].interaction[+].code = #search-type") == len(
        CAPTURE_SERVER_READ_RESOURCE_TYPES
    )
    assert content.count("* rest.resource[=].interaction[+].code = #create") == 1


def test_prefix_token_flows_into_the_foundation_names() -> None:
    """A custom prefix renames the artifacts; an empty prefix keeps the D2 token (Period is a core name)."""
    custom = _by_path(GenerateConfig(naming=NamingConfig(prefix="Dhis2")))["foundation/d2-period.fsh"]
    assert "Extension: Dhis2Period" in custom
    assert "Id: dhis2-period" in custom
    assert "CodeSystem: Dhis2PeriodType_CS" in custom
    assert (
        "Instance: Dhis2OrgUnitIdentifierSystem"
        in (_by_path(GenerateConfig(naming=NamingConfig(prefix="Dhis2")))["foundation/d2-naming-systems.fsh"])
    )
    bare = _by_path(GenerateConfig(naming=NamingConfig(prefix="")))["foundation/d2-period.fsh"]
    assert "Extension: D2Period" in bare
    assert "Id: d2-period" in bare
    bare_form_type = _by_path(GenerateConfig(naming=NamingConfig(prefix="")))["foundation/d2-form-type.fsh"]
    assert "Extension: D2FormType" in bare_form_type


def test_prefix_token_flows_into_the_capture_contract_names() -> None:
    """A custom prefix renames both response profiles, their extension slices, and the capture server."""
    custom = _by_path(GenerateConfig(naming=NamingConfig(prefix="Dhis2")))
    responses = custom["foundation/d2-responses.fsh"]
    assert "Profile: Dhis2AggregateResponse" in responses
    assert "Id: dhis2-aggregate-response" in responses
    assert "Profile: Dhis2EventResponse" in responses
    assert "Dhis2Period named Dhis2Period 1..1" in responses
    assert "* extension[Dhis2FormType].valueCode = #event (exactly)" in responses
    assert "* subject only Reference(Dhis2Location)" in responses
    assert "Profile: Dhis2TrackerEventResponse" in responses
    assert "Id: dhis2-tracker-event-response" in responses
    assert "Dhis2OrganisationUnit named Dhis2OrganisationUnit 1..1" in responses
    assert "Dhis2TrackerEnrollment named Dhis2TrackerEnrollment 1..1" in responses
    assert "Extension: Dhis2OrganisationUnit" in custom["foundation/d2-organisation-unit.fsh"]
    assert "Extension: Dhis2TrackerEnrollment" in custom["foundation/d2-tracker-enrollment.fsh"]
    capture_server = custom["foundation/d2-capture-server.fsh"]
    assert "Instance: Dhis2CaptureServer" in capture_server
    assert '* id = "dhis2-capture-server"' in capture_server
    assert "Canonical(Dhis2AggregateResponse)" in capture_server
    assert "Canonical(Dhis2TrackerEventResponse)" in capture_server


def test_the_tracker_capture_names_derive_from_the_prefix_token() -> None:
    """The three tracker-capture artifacts take the naming prefix, falling back to D2 when it is empty."""
    custom = FoundationNaming.from_naming(NamingConfig(prefix="Dhis2"))
    assert custom.organisation_unit_extension == "Dhis2OrganisationUnit"
    assert custom.organisation_unit_extension_id == "dhis2-organisation-unit"
    assert custom.tracker_enrollment_extension == "Dhis2TrackerEnrollment"
    assert custom.tracker_enrollment_extension_id == "dhis2-tracker-enrollment"
    assert custom.tracker_event_response_profile == "Dhis2TrackerEventResponse"
    assert custom.tracker_event_response_profile_id == "dhis2-tracker-event-response"
    bare = FoundationNaming.from_naming(NamingConfig(prefix=""))
    assert bare.organisation_unit_extension == "D2OrganisationUnit"
    assert bare.organisation_unit_extension_id == "d2-organisation-unit"
    assert bare.tracker_enrollment_extension == "D2TrackerEnrollment"
    assert bare.tracker_enrollment_extension_id == "d2-tracker-enrollment"
    assert bare.tracker_event_response_profile == "D2TrackerEventResponse"
    assert bare.tracker_event_response_profile_id == "d2-tracker-event-response"
