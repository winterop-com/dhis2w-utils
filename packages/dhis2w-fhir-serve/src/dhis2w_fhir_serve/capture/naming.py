"""The URLs and identifier systems one project's capture contract is written in.

Every name here is derived from `fhir.toml` - the IG canonical for the extensions the profiles
pin, and `[generate] identifier_system_base` for the DHIS2 identifier systems a response names
its tracked entity, its enrollment, and its program under. Nothing is hard-coded: a project that
renames its prefix token renames its extensions, and the capture path follows without an edit.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from dhis2w_fhir.foundation.schemas import IDENTIFIER_SYSTEM_SUBJECTS, FoundationNaming
from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from dhis2w_fhir.config import FhirProject

#: The sub-extension urls D2Period slices its three facts under, as `d2-period.fsh.jinja` names them.
PERIOD_ISO_SUB_EXTENSION = "iso"
PERIOD_TYPE_SUB_EXTENSION = "type"
PERIOD_RANGE_SUB_EXTENSION = "period"

#: The identifier-system segment of each DHIS2 object kind a captured response names, by subject token.
_SEGMENTS_BY_TOKEN = {subject.token: subject.segment for subject in IDENTIFIER_SYSTEM_SUBJECTS}


class CaptureNaming(BaseModel):
    """What a received QuestionnaireResponse is read against: four extension urls and three identifier systems."""

    model_config = ConfigDict(frozen=True)

    form_type_url: str
    period_url: str
    organisation_unit_url: str
    tracker_enrollment_url: str
    tracked_entity_system: str
    tracker_enrollment_system: str
    program_identifier_system: str

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
            tracker_enrollment_url=_definition_url(canonical, names.tracker_enrollment_extension_id),
            tracked_entity_system=_identifier_system(base, "TrackedEntity"),
            tracker_enrollment_system=_identifier_system(base, "TrackerEnrollment"),
            program_identifier_system=_identifier_system(base, "Program"),
        )


def _definition_url(canonical: str, definition_id: str) -> str:
    """The canonical url one StructureDefinition is published at, as SUSHI resolves `Canonical(...)`."""
    return f"{canonical}/StructureDefinition/{definition_id}"


def _identifier_system(base: str, token: str) -> str:
    """The DHIS2 identifier system one object kind is named under, as `d2-aliases.fsh` declares it."""
    return f"{base}/id/{_SEGMENTS_BY_TOKEN[token]}"
