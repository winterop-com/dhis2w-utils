"""FSH terminology for organisation units: the level CodeSystem/ValueSet and the whole-selection pair.

The level pair backs the required `Organization.type` binding. The optional
whole-selection pair carries `level`, `parent`, and `dhis2-code` concept
properties so the DHIS2 hierarchy survives as terminology.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from jinja2 import Environment, PackageLoader, StrictUndefined, select_autoescape
from pydantic import BaseModel, ConfigDict

from dhis2w_fhir.names import quote
from dhis2w_fhir.resources.organisation_units.naming import OrganisationUnitNaming
from dhis2w_fhir.resources.organisation_units.schemas import OrganisationUnitIn
from dhis2w_fhir.writer import FshArtifact

if TYPE_CHECKING:
    from dhis2w_fhir.config import GenerateConfig

_ENVIRONMENT = Environment(
    loader=PackageLoader("dhis2w_fhir.resources.organisation_units", "templates"),
    autoescape=select_autoescape(default=False),
    undefined=StrictUndefined,
    keep_trailing_newline=True,
    trim_blocks=True,
    lstrip_blocks=True,
)


class _OrganisationUnitConcept(BaseModel):
    """One organisation unit as a concept of the whole-selection CodeSystem."""

    model_config = ConfigDict(frozen=True)

    uid: str
    display_literal: str
    level: int
    parent_uid: str | None = None
    code_literal: str | None = None


def build_organisation_unit_level_terminology(levels: list[int], config: GenerateConfig) -> FshArtifact:
    """Build `organization/org-unit-levels.fsh` covering the levels observed in the selection."""
    names = OrganisationUnitNaming.from_naming(config.naming)
    content = _ENVIRONMENT.get_template("org-unit-levels.fsh.jinja").render(names=names, levels=sorted(set(levels)))
    return FshArtifact(
        relative_path="organization/org-unit-levels.fsh",
        kind="terminology-pair",
        fsh_name=names.level_code_system,
        content=content,
    )


def build_organisation_unit_terminology(
    organisation_units: list[OrganisationUnitIn], config: GenerateConfig
) -> FshArtifact:
    """Build the optional `organization/org-units-terminology.fsh` CodeSystem/ValueSet over the selection."""
    names = OrganisationUnitNaming.from_naming(config.naming)
    concepts = [
        _OrganisationUnitConcept(
            uid=organisation_unit.uid,
            display_literal=quote(organisation_unit.name),
            level=organisation_unit.level,
            parent_uid=organisation_unit.parent_uid,
            code_literal=quote(organisation_unit.code) if organisation_unit.code is not None else None,
        )
        for organisation_unit in sorted(organisation_units, key=lambda item: (item.path, item.uid))
    ]
    content = _ENVIRONMENT.get_template("org-units-terminology.fsh.jinja").render(names=names, concepts=concepts)
    return FshArtifact(
        relative_path="organization/org-units-terminology.fsh",
        kind="terminology-pair",
        fsh_name=names.organisation_unit_code_system,
        content=content,
    )
