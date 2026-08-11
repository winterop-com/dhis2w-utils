"""JSON emission for the organisation-unit terminology: the level pair and the whole-selection pair.

The twin of `organization/org-unit-levels.fsh` and `organization/org-units-terminology.fsh`. Both
builders read the very inputs the FSH emitters read - the levels the selection reaches, and the
selection itself in `ordered_organisation_units` order - and publish the prose and the concept
properties `schemas.py` states once for both paths, so a served pair and a compiled pair agree
concept for concept.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

from dhis2w_fhir.foundation.documents import build_terminology_pair
from dhis2w_fhir.i18n import name_translations
from dhis2w_fhir.names import flatten_whitespace
from dhis2w_fhir.r4 import (
    CodeSystem,
    CodeSystemConcept,
    CodeSystemConceptDesignation,
    CodeSystemConceptProperty,
    CodeSystemProperty,
    ValueSet,
)
from dhis2w_fhir.resources.organisation_units.naming import OrganisationUnitNaming
from dhis2w_fhir.resources.organisation_units.schemas import (
    ORGANISATION_UNIT_CONCEPT_PROPERTIES,
    ORGANISATION_UNIT_LEVEL_TERMINOLOGY,
    ORGANISATION_UNIT_TERMINOLOGY,
    OrganisationUnitIn,
    ordered_organisation_units,
)
from dhis2w_fhir.status import IgStatus

if TYPE_CHECKING:
    from dhis2w_fhir.config import GenerateConfig

#: The concept property carrying the hierarchy level of one organisation unit.
_LEVEL_PROPERTY = "level"

#: The concept property carrying the UID of the organisation unit one sits under.
_PARENT_PROPERTY = "parent"

#: The concept property carrying the DHIS2 code of one organisation unit.
_CODE_PROPERTY = "dhis2-code"


class OrganisationUnitTerminologyBuild(BaseModel):
    """The organisation-unit vocabularies as served documents, in the order the guide publishes them."""

    model_config = ConfigDict(frozen=True)

    code_systems: list[CodeSystem] = Field(default_factory=list)
    value_sets: list[ValueSet] = Field(default_factory=list)


def build_organisation_unit_level_terminology_documents(
    levels: list[int], config: GenerateConfig, canonical: str, *, ig_status: IgStatus
) -> OrganisationUnitTerminologyBuild:
    """Build the level pair over the levels the selection reaches - the vocabulary `Organization.type` binds."""
    names = OrganisationUnitNaming.from_naming(config.naming)
    pair = build_terminology_pair(
        [CodeSystemConcept(code=f"level-{level}", display=f"Level {level}") for level in sorted(set(levels))],
        ORGANISATION_UNIT_LEVEL_TERMINOLOGY,
        canonical,
        code_system_name=names.level_code_system,
        code_system_id=names.terminology_id("level", "cs"),
        value_set_name=names.level_value_set,
        value_set_id=names.terminology_id("level", "vs"),
        ig_status=ig_status,
    )
    return OrganisationUnitTerminologyBuild(code_systems=[pair.code_system], value_sets=[pair.value_set])


def build_organisation_unit_terminology_documents(
    organisation_units: list[OrganisationUnitIn], config: GenerateConfig, canonical: str, *, ig_status: IgStatus
) -> OrganisationUnitTerminologyBuild:
    """Build the whole-selection pair, one concept per organisation unit keyed by its DHIS2 UID."""
    names = OrganisationUnitNaming.from_naming(config.naming)
    property_base = f"{config.identifier_system_base}/property"
    pair = build_terminology_pair(
        [_concept(organisation_unit, config) for organisation_unit in ordered_organisation_units(organisation_units)],
        ORGANISATION_UNIT_TERMINOLOGY,
        canonical,
        code_system_name=names.organisation_unit_code_system,
        code_system_id=names.terminology_id("cs"),
        value_set_name=names.organisation_unit_value_set,
        value_set_id=names.terminology_id("vs"),
        ig_status=ig_status,
        properties=[
            CodeSystemProperty(
                code=declaration.code,
                uri=f"{property_base}/{declaration.code}",
                description=declaration.description,
                type=declaration.type,
            )
            for declaration in ORGANISATION_UNIT_CONCEPT_PROPERTIES
        ],
    )
    return OrganisationUnitTerminologyBuild(code_systems=[pair.code_system], value_sets=[pair.value_set])


def _concept(organisation_unit: OrganisationUnitIn, config: GenerateConfig) -> CodeSystemConcept:
    """One organisation unit as a concept: its level always, then its parent and its DHIS2 code where it has them."""
    properties = [CodeSystemConceptProperty(code=_LEVEL_PROPERTY, valueInteger=organisation_unit.level)]
    if organisation_unit.parent_uid is not None:
        properties.append(CodeSystemConceptProperty(code=_PARENT_PROPERTY, valueCode=organisation_unit.parent_uid))
    if organisation_unit.code is not None:
        properties.append(
            CodeSystemConceptProperty(code=_CODE_PROPERTY, valueString=flatten_whitespace(organisation_unit.code))
        )
    designations = [
        CodeSystemConceptDesignation(language=translation.locale, value=flatten_whitespace(translation.value))
        for translation in name_translations(organisation_unit.translations, config.locales)
    ]
    return CodeSystemConcept(
        code=organisation_unit.uid,
        display=flatten_whitespace(organisation_unit.name),
        property=properties,
        designation=designations or None,
    )
