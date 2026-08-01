"""Foundation schemas: the derived FSH names and ids for the shared aliases and D2Period artifacts."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

from dhis2w_fhir.names import join_id_tokens

if TYPE_CHECKING:
    from dhis2w_fhir.config import NamingConfig

_DEFINITION_FALLBACK_PREFIX = "D2"


class FoundationNaming(BaseModel):
    """Derived FSH names and ids for the foundation artifacts under the configurable prefix token.

    The foundation artifacts take the `[generate.naming]` prefix and no token of their own.
    An empty prefix falls back to `D2` for the same reason the profiles do: `Period` is a core
    FHIR datatype name, and an Extension cannot shadow it.
    """

    model_config = ConfigDict(frozen=True)

    prefix: str

    @classmethod
    def from_naming(cls, naming: NamingConfig) -> FoundationNaming:
        """Project the `[generate.naming]` table onto the token the foundation artifacts use."""
        return cls(prefix=naming.prefix)

    @property
    def definition_prefix(self) -> str:
        """Token for definitional names - never empty, a definition cannot shadow a core FHIR name."""
        return self.prefix or _DEFINITION_FALLBACK_PREFIX

    @property
    def period_extension(self) -> str:
        """FSH name of the reporting-period Extension (e.g. `D2Period`)."""
        return f"{self.definition_prefix}Period"

    @property
    def period_extension_id(self) -> str:
        """FHIR id of the reporting-period Extension (e.g. `d2-period`)."""
        return join_id_tokens(self.definition_prefix, "period")

    @property
    def period_type_code_system(self) -> str:
        """FSH name of the period-type CodeSystem (e.g. `D2PeriodTypeCS`)."""
        return f"{self.definition_prefix}PeriodTypeCS"

    @property
    def period_type_code_system_id(self) -> str:
        """FHIR id of the period-type CodeSystem (e.g. `d2-period-type-cs`)."""
        return join_id_tokens(self.definition_prefix, "period", "type", "cs")

    @property
    def period_type_value_set(self) -> str:
        """FSH name of the period-type ValueSet (e.g. `D2PeriodTypeVS`)."""
        return f"{self.definition_prefix}PeriodTypeVS"

    @property
    def period_type_value_set_id(self) -> str:
        """FHIR id of the period-type ValueSet (e.g. `d2-period-type-vs`)."""
        return join_id_tokens(self.definition_prefix, "period", "type", "vs")
