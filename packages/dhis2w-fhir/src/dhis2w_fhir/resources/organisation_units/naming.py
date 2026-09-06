"""Derived FSH names, ids, and absolute URLs for organisation-unit artifacts under the naming tokens."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

from dhis2w_fhir.foundation.schemas import FoundationNaming
from dhis2w_fhir.names import join_id_tokens
from dhis2w_fhir.r4 import Coding
from dhis2w_fhir.resources.organisation_units.schemas import OrganisationUnitLevelNames

if TYPE_CHECKING:
    from dhis2w_fhir.config import GenerateConfig, NamingConfig

_PROFILE_FALLBACK_PREFIX = "D2"


class OrganisationUnitNaming(BaseModel):
    """Derived FSH names and ids for org-unit artifacts under the configurable naming tokens.

    Holds the two tokens it needs rather than the whole `[generate.naming]` table, so the
    emitters stay a leaf of the config document instead of a dependency of it.
    """

    model_config = ConfigDict(frozen=True)

    prefix: str
    organisation_unit: str

    @classmethod
    def from_naming(cls, naming: NamingConfig) -> OrganisationUnitNaming:
        """Project the `[generate.naming]` table onto the tokens organisation-unit artifacts use."""
        return cls(prefix=naming.prefix, organisation_unit=naming.organisation_unit)

    @property
    def profile_prefix(self) -> str:
        """Token for profile names - never empty, a profile cannot shadow its parent resource name."""
        return self.prefix or _PROFILE_FALLBACK_PREFIX

    @property
    def organization_profile(self) -> str:
        """FSH name of the Organization profile."""
        return f"{self.profile_prefix}Organization"

    @property
    def location_profile(self) -> str:
        """FSH name of the Location profile."""
        return f"{self.profile_prefix}Location"

    @property
    def level_code_system(self) -> str:
        """FSH name of the org-unit-level CodeSystem (e.g. `D2OrgUnit_Level_CS`, `D2OU_Level_CS`)."""
        return f"{self.prefix}{self.organisation_unit}_Level_CS"

    @property
    def level_value_set(self) -> str:
        """FSH name of the org-unit-level ValueSet (e.g. `D2OU_Level_VS`)."""
        return f"{self.prefix}{self.organisation_unit}_Level_VS"

    @property
    def organisation_unit_code_system(self) -> str:
        """FSH name of the optional whole-selection CodeSystem (e.g. `D2OU_CS`)."""
        return f"{self.prefix}{self.organisation_unit}_CS"

    @property
    def organisation_unit_value_set(self) -> str:
        """FSH name of the optional whole-selection ValueSet (e.g. `D2OU_VS`)."""
        return f"{self.prefix}{self.organisation_unit}_VS"

    @property
    def organization_profile_id(self) -> str:
        """FHIR id of the Organization profile (e.g. `d2-organization`)."""
        return join_id_tokens(self.profile_prefix, "organization")

    @property
    def location_profile_id(self) -> str:
        """FHIR id of the Location profile (e.g. `d2-location`)."""
        return join_id_tokens(self.profile_prefix, "location")

    def terminology_id(self, *suffix_tokens: str) -> str:
        """FHIR id for an org-unit terminology artifact (e.g. `d2-org-unit-level-cs`, `d2-ou-cs`)."""
        return join_id_tokens(self.prefix, self.organisation_unit, *suffix_tokens)


class OrganisationUnitInstanceUrls(BaseModel):
    """The absolute URLs a pre-built Organization/Location references: its profile, level codes, identifiers.

    A pre-built resource carries what FSH resolves through `InstanceOf`, `$DHIS2-OU`, and a
    CodeSystem name, so the canonical of the IG and the configured identifier system base are
    resolved once here and read straight off the model by both emitters.
    """

    model_config = ConfigDict(frozen=True)

    organization_profile: str
    location_profile: str
    level_code_system: str
    level_extension: str
    """Canonical of the D2OrganisationUnitLevel Extension every published Location states its level on."""
    identifier_system: str
    code_identifier_system: str
    identifier_system_base: str
    """The `[generate] identifier_system_base`, from which a unique attribute's own namespace is derived."""

    @classmethod
    def from_config(cls, config: GenerateConfig, canonical: str) -> OrganisationUnitInstanceUrls:
        """Derive the instance URLs from the IG canonical plus the `[generate]` identifier system base."""
        names = OrganisationUnitNaming.from_naming(config.naming)
        foundation = FoundationNaming.from_naming(config.naming)
        identifier_base = config.identifier_system_base
        return cls(
            organization_profile=f"{canonical}/StructureDefinition/{names.organization_profile_id}",
            location_profile=f"{canonical}/StructureDefinition/{names.location_profile_id}",
            level_code_system=f"{canonical}/CodeSystem/{names.terminology_id('level', 'cs')}",
            level_extension=f"{canonical}/StructureDefinition/{foundation.organisation_unit_level_extension_id}",
            identifier_system=f"{identifier_base}/id/org-unit",
            code_identifier_system=f"{identifier_base}/id/org-unit-code",
            identifier_system_base=identifier_base,
        )


def organisation_unit_level_coding(
    level: int, urls: OrganisationUnitInstanceUrls, level_names: OrganisationUnitLevelNames
) -> Coding:
    """The published level coding of one depth - stable `level-<n>` code, the instance's own name as display.

    Read by both resources of a unit: `Organization.type` and the D2OrganisationUnitLevel extension
    a Location carries. One helper keeps the two spellings of the same fact identical.
    """
    return Coding(system=urls.level_code_system, code=f"level-{level}", display=level_names.display(level))
