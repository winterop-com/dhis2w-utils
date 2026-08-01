"""Derived FSH names and ids for organisation-unit artifacts under the configurable naming tokens."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

from dhis2w_fhir.names import join_id_tokens

if TYPE_CHECKING:
    from dhis2w_fhir.config import NamingConfig

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
        """FSH name of the org-unit-level CodeSystem (e.g. `D2OrgUnitLevelCS`, `D2OULevelCS`)."""
        return f"{self.prefix}{self.organisation_unit}LevelCS"

    @property
    def level_value_set(self) -> str:
        """FSH name of the org-unit-level ValueSet."""
        return f"{self.prefix}{self.organisation_unit}LevelVS"

    @property
    def organisation_unit_code_system(self) -> str:
        """FSH name of the optional whole-selection CodeSystem."""
        return f"{self.prefix}{self.organisation_unit}CS"

    @property
    def organisation_unit_value_set(self) -> str:
        """FSH name of the optional whole-selection ValueSet."""
        return f"{self.prefix}{self.organisation_unit}VS"

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
