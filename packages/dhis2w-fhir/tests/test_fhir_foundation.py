"""Golden tests for the foundation artifacts: the DHIS2 identifier aliases and the D2Period extension."""

from dhis2w_fhir.config import GenerateConfig, NamingConfig
from dhis2w_fhir.foundation import build_foundation_artifacts
from dhis2w_fhir.period import PERIOD_TYPE_DEFINITIONS


def _by_path(config: GenerateConfig) -> dict[str, str]:
    """Build the foundation artifacts and index them by relative path."""
    return {artifact.relative_path: artifact.content for artifact in build_foundation_artifacts(config)}


def test_foundation_covers_expected_files() -> None:
    """The target emits the aliases, the NamingSystem declarations, and the period extension."""
    assert set(_by_path(GenerateConfig())) == {
        "foundation/d2-aliases.fsh",
        "foundation/d2-naming-systems.fsh",
        "foundation/d2-period.fsh",
    }


def test_aliases_come_from_the_configured_identifier_base() -> None:
    """The DHIS2 identifier aliases are derived from `[generate] identifier_system_base`."""
    default = _by_path(GenerateConfig())["foundation/d2-aliases.fsh"]
    assert "Alias: $DHIS2-OU = http://dhis2.org/fhir/id/org-unit" in default
    assert "Alias: $DHIS2-OU-CODE = http://dhis2.org/fhir/id/org-unit-code" in default
    assert "Alias: $DHIS2-OS = http://dhis2.org/fhir/id/option-set" in default
    assert "Alias: $DHIS2-OS-CODE = http://dhis2.org/fhir/id/option-set-code" in default
    custom = _by_path(GenerateConfig(identifier_system_base="https://example.org/dhis2/"))
    aliases = custom["foundation/d2-aliases.fsh"]
    assert "Alias: $DHIS2-OU = https://example.org/dhis2/id/org-unit" in aliases
    assert "Alias: $DHIS2-OU-CODE = https://example.org/dhis2/id/org-unit-code" in aliases
    assert "Alias: $DHIS2-OS = https://example.org/dhis2/id/option-set" in aliases


def test_naming_systems_declare_every_identifier_system() -> None:
    """Each `$DHIS2-*` alias URL is declared by a NamingSystem, so consumers can resolve what it means."""
    content = _by_path(GenerateConfig())["foundation/d2-naming-systems.fsh"]
    assert content.count("InstanceOf: NamingSystem") == 4
    assert content.count("* kind = #identifier") == 4
    assert content.count("* uniqueId[0].preferred = true") == 4
    assert "Instance: D2OrgUnitIdentifierSystem" in content
    assert "Instance: D2OrgUnitCodeIdentifierSystem" in content
    assert "Instance: D2OptionSetIdentifierSystem" in content
    assert "Instance: D2OptionSetCodeIdentifierSystem" in content
    assert '* uniqueId[0].value = "http://dhis2.org/fhir/id/org-unit"' in content
    assert '* uniqueId[0].value = "http://dhis2.org/fhir/id/option-set-code"' in content
    assert "this slot repeats the UID" in content


def test_naming_system_date_is_fixed_so_regeneration_is_byte_stable() -> None:
    """R4 makes NamingSystem.date mandatory; a pinned date keeps a no-op regenerate from rewriting the file."""
    first = _by_path(GenerateConfig())["foundation/d2-naming-systems.fsh"]
    second = _by_path(GenerateConfig())["foundation/d2-naming-systems.fsh"]
    assert first == second
    assert first.count('* date = "2026-08-01"') == 4


def test_period_terminology_is_marked_experimental() -> None:
    """The period-type pair carries ^experimental, which ShareableCodeSystem/ValueSet require."""
    assert _by_path(GenerateConfig())["foundation/d2-period.fsh"].count("* ^experimental = true") == 2


def test_period_extension_shape() -> None:
    """D2Period is element-scoped with the iso/type/period sub-extensions and a required type binding."""
    period = _by_path(GenerateConfig())["foundation/d2-period.fsh"]
    assert "Extension: D2Period" in period
    assert "Id: d2-period" in period
    assert 'Title: "DHIS2 reporting period"' in period
    assert "* ^context[+].type = #element" in period
    assert '* ^context[=].expression = "Element"' in period
    assert "    iso 1..1 and" in period
    assert "    type 1..1 and" in period
    assert "    period 0..1" in period
    assert "* extension[iso].value[x] only string" in period
    assert "* extension[type].valueCode from D2PeriodTypeVS (required)" in period
    assert "* extension[period].value[x] only Period" in period


def test_period_type_terminology_lists_every_type() -> None:
    """The period-type CodeSystem publishes every registered type and points back at its ValueSet."""
    period = _by_path(GenerateConfig())["foundation/d2-period.fsh"]
    assert "CodeSystem: D2PeriodTypeCS" in period
    assert "Id: d2-period-type-cs" in period
    assert "* ^valueSet = Canonical(D2PeriodTypeVS)" in period
    assert "ValueSet: D2PeriodTypeVS" in period
    assert "Id: d2-period-type-vs" in period
    for definition in PERIOD_TYPE_DEFINITIONS:
        assert f'* #{definition.name} "{definition.display}"' in period
    assert "* ^identifier[" not in period


def test_prefix_token_flows_into_the_foundation_names() -> None:
    """A custom prefix renames the artifacts; an empty prefix keeps the D2 token (Period is a core name)."""
    custom = _by_path(GenerateConfig(naming=NamingConfig(prefix="Dhis2")))["foundation/d2-period.fsh"]
    assert "Extension: Dhis2Period" in custom
    assert "Id: dhis2-period" in custom
    assert "CodeSystem: Dhis2PeriodTypeCS" in custom
    assert (
        "Instance: Dhis2OrgUnitIdentifierSystem"
        in (_by_path(GenerateConfig(naming=NamingConfig(prefix="Dhis2")))["foundation/d2-naming-systems.fsh"])
    )
    bare = _by_path(GenerateConfig(naming=NamingConfig(prefix="")))["foundation/d2-period.fsh"]
    assert "Extension: D2Period" in bare
    assert "Id: d2-period" in bare
