"""FSH emission for the foundation layer: the DHIS2 identifier aliases and the D2Period extension.

These artifacts depend on `fhir.toml` alone, never on a DHIS2 instance. `d2-aliases.fsh`
turns `[generate] identifier_system_base` into the `$DHIS2-*` aliases every instance file
references; `d2-period.fsh` defines the reporting-period Extension plus the period-type
CodeSystem/ValueSet backing its required binding.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from jinja2 import Environment, PackageLoader, StrictUndefined, select_autoescape

from dhis2w_fhir.foundation.schemas import FoundationNaming
from dhis2w_fhir.period.schemas import PERIOD_TYPE_DEFINITIONS
from dhis2w_fhir.writer import FshArtifact

if TYPE_CHECKING:
    from dhis2w_fhir.config import GenerateConfig

__all__ = ["FoundationNaming", "build_foundation_artifacts"]

_ENVIRONMENT = Environment(
    loader=PackageLoader("dhis2w_fhir.foundation", "templates"),
    autoescape=select_autoescape(default=False),
    undefined=StrictUndefined,
    keep_trailing_newline=True,
    trim_blocks=True,
    lstrip_blocks=True,
)


def build_foundation_artifacts(config: GenerateConfig) -> list[FshArtifact]:
    """Build the `foundation/` artifacts: the DHIS2 identifier aliases and the D2Period extension."""
    names = FoundationNaming.from_naming(config.naming)
    aliases = _ENVIRONMENT.get_template("d2-aliases.fsh.jinja").render(
        identifier_system_base=config.identifier_system_base
    )
    period = _ENVIRONMENT.get_template("d2-period.fsh.jinja").render(names=names, period_types=PERIOD_TYPE_DEFINITIONS)
    return [
        FshArtifact(
            relative_path="foundation/d2-aliases.fsh",
            kind="aliases",
            fsh_name="DHIS2 identifier aliases",
            content=aliases,
        ),
        FshArtifact(
            relative_path="foundation/d2-period.fsh",
            kind="extension",
            fsh_name=names.period_extension,
            content=period,
        ),
    ]
