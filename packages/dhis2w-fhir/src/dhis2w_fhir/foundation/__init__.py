"""FSH emission for the foundation layer: the DHIS2 identifier systems and the D2Period extension.

These artifacts depend on `fhir.toml` alone, never on a DHIS2 instance. `d2-aliases.fsh`
turns `[generate] identifier_system_base` into the `$DHIS2-*` aliases every instance file
references; `d2-naming-systems.fsh` declares each of those URLs as a NamingSystem, so a
consumer meeting a DHIS2 identifier can resolve what it means; `d2-period.fsh` defines the
reporting-period Extension plus the period-type CodeSystem/ValueSet backing its required
binding.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from jinja2 import Environment, PackageLoader, StrictUndefined, select_autoescape

from dhis2w_fhir.foundation.schemas import (
    IDENTIFIER_SYSTEM_SUBJECTS,
    FoundationNaming,
    NamingSystemDeclaration,
)
from dhis2w_fhir.period.schemas import PERIOD_TYPE_DEFINITIONS
from dhis2w_fhir.writer import FshArtifact

if TYPE_CHECKING:
    from dhis2w_fhir.config import GenerateConfig

__all__ = ["FoundationNaming", "NamingSystemDeclaration", "build_foundation_artifacts"]

#: The `NamingSystem.date` every declaration carries. R4 makes the element mandatory, and a
#: generated timestamp would rewrite the file on every run - this is the date the DHIS2
#: identifier-system convention was fixed, so regeneration stays byte-stable.
_IDENTIFIER_SYSTEM_DECLARED_DATE = "2026-08-01"

_ENVIRONMENT = Environment(
    loader=PackageLoader("dhis2w_fhir.foundation", "templates"),
    autoescape=select_autoescape(default=False),
    undefined=StrictUndefined,
    keep_trailing_newline=True,
    trim_blocks=True,
    lstrip_blocks=True,
)


def build_foundation_artifacts(config: GenerateConfig) -> list[FshArtifact]:
    """Build the `foundation/` artifacts: the DHIS2 identifier systems and the D2Period extension."""
    names = FoundationNaming.from_naming(config.naming)
    aliases = _ENVIRONMENT.get_template("d2-aliases.fsh.jinja").render(
        identifier_system_base=config.identifier_system_base
    )
    naming_systems = _ENVIRONMENT.get_template("d2-naming-systems.fsh.jinja").render(
        naming_systems=build_naming_system_declarations(config),
        declared_date=_IDENTIFIER_SYSTEM_DECLARED_DATE,
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
    ]


def build_naming_system_declarations(config: GenerateConfig) -> list[NamingSystemDeclaration]:
    """Declare every DHIS2 identifier system: a UID system and a code system per object kind."""
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
