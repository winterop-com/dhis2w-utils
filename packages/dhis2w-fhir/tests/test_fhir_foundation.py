"""Golden tests for the foundation artifacts: the DHIS2 identifier aliases and the D2Period extension."""

from dhis2w_fhir.config import GenerateConfig, NamingConfig
from dhis2w_fhir.foundation import build_foundation_artifacts
from dhis2w_fhir.period import PERIOD_TYPE_DEFINITIONS


def _by_path(config: GenerateConfig, *, experimental: bool = True) -> dict[str, str]:
    """Build the foundation artifacts and index them by relative path."""
    artifacts = build_foundation_artifacts(config, experimental=experimental)
    return {artifact.relative_path: artifact.content for artifact in artifacts}


#: The DHIS2 object kinds that carry an identifier system, each yielding a UID and a code declaration.
_IDENTIFIER_SYSTEM_COUNT = 12


def test_foundation_covers_expected_files() -> None:
    """The target emits the aliases, the NamingSystems, and the period and form-type extensions."""
    assert set(_by_path(GenerateConfig())) == {
        "foundation/d2-aliases.fsh",
        "foundation/d2-naming-systems.fsh",
        "foundation/d2-period.fsh",
        "foundation/d2-form-type.fsh",
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


def test_data_definition_aliases_are_emitted() -> None:
    """The questionnaire target's identifier systems are aliased alongside the terminology ones."""
    aliases = _by_path(GenerateConfig())["foundation/d2-aliases.fsh"]
    assert "Alias: $DHIS2-DS = http://dhis2.org/fhir/id/data-set" in aliases
    assert "Alias: $DHIS2-DS-CODE = http://dhis2.org/fhir/id/data-set-code" in aliases
    assert "Alias: $DHIS2-PROGRAM = http://dhis2.org/fhir/id/program" in aliases
    assert "Alias: $DHIS2-PROGRAM-CODE = http://dhis2.org/fhir/id/program-code" in aliases
    assert "Alias: $DHIS2-DE = http://dhis2.org/fhir/id/data-element" in aliases
    assert "Alias: $DHIS2-COC = http://dhis2.org/fhir/id/category-option-combo" in aliases


def test_naming_systems_declare_every_identifier_system() -> None:
    """Each `$DHIS2-*` alias URL is declared by a NamingSystem, so consumers can resolve what it means."""
    content = _by_path(GenerateConfig())["foundation/d2-naming-systems.fsh"]
    assert content.count("InstanceOf: NamingSystem") == _IDENTIFIER_SYSTEM_COUNT
    assert content.count("* kind = #identifier") == _IDENTIFIER_SYSTEM_COUNT
    assert content.count("* uniqueId[0].preferred = true") == _IDENTIFIER_SYSTEM_COUNT
    assert "Instance: D2OrgUnitIdentifierSystem" in content
    assert "Instance: D2OrgUnitCodeIdentifierSystem" in content
    assert "Instance: D2OptionSetIdentifierSystem" in content
    assert "Instance: D2OptionSetCodeIdentifierSystem" in content
    assert "Instance: D2DataSetIdentifierSystem" in content
    assert "Instance: D2ProgramCodeIdentifierSystem" in content
    assert "Instance: D2DataElementIdentifierSystem" in content
    assert "Instance: D2CategoryOptionComboIdentifierSystem" in content
    assert '* uniqueId[0].value = "http://dhis2.org/fhir/id/org-unit"' in content
    assert '* uniqueId[0].value = "http://dhis2.org/fhir/id/option-set-code"' in content
    assert '* uniqueId[0].value = "http://dhis2.org/fhir/id/data-set"' in content
    assert '* uniqueId[0].value = "http://dhis2.org/fhir/id/category-option-combo"' in content
    assert "this slot repeats the UID" in content


def test_naming_system_date_is_fixed_so_regeneration_is_byte_stable() -> None:
    """R4 makes NamingSystem.date mandatory; a pinned date keeps a no-op regenerate from rewriting the file."""
    first = _by_path(GenerateConfig())["foundation/d2-naming-systems.fsh"]
    second = _by_path(GenerateConfig())["foundation/d2-naming-systems.fsh"]
    assert first == second
    assert first.count('* date = "2026-08-01"') == _IDENTIFIER_SYSTEM_COUNT


def test_form_type_extension_binds_both_questionnaire_resources() -> None:
    """D2FormType is contexted on Questionnaire and QuestionnaireResponse with a required code binding."""
    form_type = _by_path(GenerateConfig())["foundation/d2-form-type.fsh"]
    assert "Extension: D2FormType" in form_type
    assert "Id: d2-form-type" in form_type
    assert '* ^context[=].expression = "Questionnaire"' in form_type
    assert '* ^context[=].expression = "QuestionnaireResponse"' in form_type
    assert form_type.count("* ^context[+].type = #element") == 2
    assert "* value[x] only code" in form_type
    assert "* valueCode 1..1" in form_type
    assert "* valueCode from D2FormType_VS (required)" in form_type


def test_form_type_terminology_covers_every_form_kind() -> None:
    """The form-type pair publishes all four DHIS2 form kinds and points back at its ValueSet."""
    form_type = _by_path(GenerateConfig())["foundation/d2-form-type.fsh"]
    assert "CodeSystem: D2FormType_CS" in form_type
    assert "Id: d2-form-type-cs" in form_type
    assert "* ^valueSet = Canonical(D2FormType_VS)" in form_type
    assert form_type.count("* ^experimental = true") == 3
    assert '* #aggregate "Aggregate data set form"' in form_type
    assert '* #event "Event program form"' in form_type
    assert '* #tracker "Tracker registration form"' in form_type
    assert '* #tracker-event "Tracker program stage form"' in form_type
    assert "ValueSet: D2FormType_VS" in form_type
    assert "Id: d2-form-type-vs" in form_type
    assert "* include codes from system D2FormType_CS" in form_type


def test_period_artifacts_derive_experimental_from_the_ig_status() -> None:
    """The extension and its period-type pair all carry ^experimental: true while draft, false once active."""
    draft = _by_path(GenerateConfig())["foundation/d2-period.fsh"]
    assert draft.count("* ^experimental = true") == 3
    active = _by_path(GenerateConfig(), experimental=False)["foundation/d2-period.fsh"]
    assert active.count("* ^experimental = false") == 3
    assert "* ^experimental = true" not in active


def test_form_type_artifacts_derive_experimental_from_the_ig_status() -> None:
    """The form-type extension and its pair follow the same derivation."""
    active = _by_path(GenerateConfig(), experimental=False)["foundation/d2-form-type.fsh"]
    assert active.count("* ^experimental = false") == 3


def test_naming_systems_carry_no_experimental_element() -> None:
    """R4 NamingSystem has no experimental element, so the declarations must not grow one."""
    assert "experimental" not in _by_path(GenerateConfig())["foundation/d2-naming-systems.fsh"]


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
    assert "* extension[type].valueCode from D2PeriodType_VS (required)" in period
    assert "* extension[period].value[x] only Period" in period


def test_period_type_terminology_lists_every_type() -> None:
    """The period-type CodeSystem publishes every registered type and points back at its ValueSet."""
    period = _by_path(GenerateConfig())["foundation/d2-period.fsh"]
    assert "CodeSystem: D2PeriodType_CS" in period
    assert "Id: d2-period-type-cs" in period
    assert "* ^valueSet = Canonical(D2PeriodType_VS)" in period
    assert "ValueSet: D2PeriodType_VS" in period
    assert "Id: d2-period-type-vs" in period
    for definition in PERIOD_TYPE_DEFINITIONS:
        assert f'* #{definition.name} "{definition.display}"' in period
    assert "* ^identifier[" not in period


def test_prefix_token_flows_into_the_foundation_names() -> None:
    """A custom prefix renames the artifacts; an empty prefix keeps the D2 token (Period is a core name)."""
    custom = _by_path(GenerateConfig(naming=NamingConfig(prefix="Dhis2")))["foundation/d2-period.fsh"]
    assert "Extension: Dhis2Period" in custom
    assert "Id: dhis2-period" in custom
    assert "CodeSystem: Dhis2PeriodType_CS" in custom
    assert (
        "Instance: Dhis2OrgUnitIdentifierSystem"
        in (_by_path(GenerateConfig(naming=NamingConfig(prefix="Dhis2")))["foundation/d2-naming-systems.fsh"])
    )
    bare = _by_path(GenerateConfig(naming=NamingConfig(prefix="")))["foundation/d2-period.fsh"]
    assert "Extension: D2Period" in bare
    assert "Id: d2-period" in bare
    bare_form_type = _by_path(GenerateConfig(naming=NamingConfig(prefix="")))["foundation/d2-form-type.fsh"]
    assert "Extension: D2FormType" in bare_form_type
