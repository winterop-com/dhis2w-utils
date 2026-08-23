"""The URLs and identifier systems one project's capture contract is written in.

Every name here is derived from `fhir.toml` - the IG canonical for the extensions the profiles
pin, and `[generate] identifier_system_base` for the DHIS2 identifier systems a response names
its tracked entity, its enrollment, and its program under. Nothing is hard-coded: a project that
renames its prefix token renames its extensions, and the capture path follows without an edit.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from dhis2w_fhir.foundation.schemas import IDENTIFIER_SYSTEM_SUBJECTS, FoundationNaming
from dhis2w_fhir.names import join_id_tokens
from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from dhis2w_fhir.config import FhirProject
    from dhis2w_fhir.resources.questionnaires.schemas import FormKind

#: The sub-extension urls D2Period slices its three facts under, as `d2-period.fsh.jinja` names them.
PERIOD_ISO_SUB_EXTENSION = "iso"
PERIOD_TYPE_SUB_EXTENSION = "type"
PERIOD_RANGE_SUB_EXTENSION = "period"

#: The identifier-system segment of each DHIS2 object kind a captured response names, by subject token.
_SEGMENTS_BY_TOKEN = {subject.token: subject.segment for subject in IDENTIFIER_SYSTEM_SUBJECTS}

#: The path segment under the IG canonical that a `$generate` seed is stated as an identifier under.
#: It hangs off the canonical rather than off `identifier_system_base`, because a seed is a fact
#: about this server's operation, not a DHIS2 object identifier.
GENERATE_SEED_IDENTIFIER_SEGMENT = "id/generate-seed"


class CaptureNaming(BaseModel):
    """What a QuestionnaireResponse is read against here: the extension urls, identifier systems, and profiles."""

    model_config = ConfigDict(frozen=True)

    form_type_url: str
    period_url: str
    organisation_unit_url: str
    organisation_unit_assignment_url: str
    attribute_option_combos_url: str
    """Extension url a Questionnaire declares the attribute-option-combo ValueSet its responses key from."""

    attribute_option_combo_url: str
    """Extension url a QuestionnaireResponse names the attribute option combo its values are keyed under."""

    tracker_enrollment_url: str
    enrolled_at_url: str
    """Extension url a registration response dates the enrollment it mints from."""

    incident_at_url: str
    """Extension url a registration response dates the incident that enrollment follows."""

    collects_incident_date_url: str
    """Extension url a registration form declares whether its program collects an incident date on."""

    program_rule_url: str
    """Extension url a form lists the DHIS2 program rules its instance enforces on import under, one repeat per rule."""

    subject_exists_url: str
    """Extension url a registration response states that the person it is subject to is already held on."""

    tracked_entity_system: str
    tracker_enrollment_system: str
    program_identifier_system: str
    program_stage_identifier_system: str
    """Identifier system a served Questionnaire names the DHIS2 program stage it was generated from under.

    What finds the form one recorded event answers: an event states its stage's UID, and the stage's
    form is the served Questionnaire carrying that UID under this system. The join is by identifier
    rather than by canonical, because what a form is called follows `[generate.naming] source` and
    what it is about does not.
    """

    generate_seed_system: str
    """Identifier system the seed a `$generate` response was drawn from is stated under."""

    aggregate_response_profile_url: str
    event_response_profile_url: str
    tracker_registration_response_profile_url: str
    tracker_event_response_profile_url: str
    tracked_entity_response_profile_url: str

    @classmethod
    def from_project(cls, project: FhirProject) -> CaptureNaming:
        """Derive every capture name from the project's canonical, naming tokens, and identifier base."""
        names = FoundationNaming.from_naming(project.config.generate.naming)
        canonical = project.config.ig.canonical
        base = project.config.generate.identifier_system_base
        return cls(
            form_type_url=_definition_url(canonical, names.form_type_extension_id),
            period_url=_definition_url(canonical, names.period_extension_id),
            organisation_unit_url=_definition_url(canonical, names.organisation_unit_extension_id),
            organisation_unit_assignment_url=_definition_url(
                canonical, names.organisation_unit_assignment_extension_id
            ),
            attribute_option_combos_url=_definition_url(canonical, names.attribute_option_combos_extension_id),
            attribute_option_combo_url=_definition_url(canonical, names.attribute_option_combo_extension_id),
            tracker_enrollment_url=_definition_url(canonical, names.tracker_enrollment_extension_id),
            enrolled_at_url=_definition_url(canonical, names.enrolled_at_extension_id),
            incident_at_url=_definition_url(canonical, names.incident_at_extension_id),
            collects_incident_date_url=_definition_url(canonical, names.collects_incident_date_extension_id),
            program_rule_url=_definition_url(canonical, join_id_tokens(names.definition_prefix, "program", "rule")),
            subject_exists_url=_definition_url(canonical, names.subject_exists_extension_id),
            tracked_entity_system=_identifier_system(base, "TrackedEntity"),
            tracker_enrollment_system=_identifier_system(base, "TrackerEnrollment"),
            program_identifier_system=_identifier_system(base, "Program"),
            program_stage_identifier_system=_identifier_system(base, "ProgramStage"),
            generate_seed_system=f"{canonical}/{GENERATE_SEED_IDENTIFIER_SEGMENT}",
            aggregate_response_profile_url=_definition_url(canonical, names.aggregate_response_profile_id),
            event_response_profile_url=_definition_url(canonical, names.event_response_profile_id),
            tracker_registration_response_profile_url=_definition_url(
                canonical, names.tracker_registration_response_profile_id
            ),
            tracker_event_response_profile_url=_definition_url(canonical, names.tracker_event_response_profile_id),
            tracked_entity_response_profile_url=_definition_url(canonical, names.tracked_entity_response_profile_id),
        )

    def response_profile_url(self, form_kind: FormKind) -> str:
        """The QuestionnaireResponse profile one DHIS2 form kind's complete response declares."""
        if form_kind == "aggregate":
            return self.aggregate_response_profile_url
        if form_kind == "tracker":
            return self.tracker_registration_response_profile_url
        if form_kind == "tracker-event":
            return self.tracker_event_response_profile_url
        if form_kind == "tracked-entity":
            return self.tracked_entity_response_profile_url
        return self.event_response_profile_url


def _definition_url(canonical: str, definition_id: str) -> str:
    """The canonical url one StructureDefinition is published at, as SUSHI resolves `Canonical(...)`."""
    return f"{canonical}/StructureDefinition/{definition_id}"


def _identifier_system(base: str, token: str) -> str:
    """The DHIS2 identifier system one object kind is named under, as `d2-aliases.fsh` declares it."""
    return f"{base}/id/{_SEGMENTS_BY_TOKEN[token]}"
