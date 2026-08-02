"""Golden tests for DHIS2 translations flowing into designations and FHIR translation extensions."""

import pytest
from dhis2w_fhir.config import GenerateConfig, NamingConfig
from dhis2w_fhir.i18n import TranslationIn, name_translations, normalize_locale
from dhis2w_fhir.resources.option_sets import build_option_set_artifacts
from dhis2w_fhir.resources.option_sets.schemas import OptionIn, OptionSetIn
from dhis2w_fhir.resources.organisation_units import (
    build_organisation_unit_instances,
    build_organisation_unit_terminology,
)
from dhis2w_fhir.resources.organisation_units.schemas import OrganisationUnitIn
from dhis2w_fhir.validation import build_code_validation

_LAO_BIRTH_TYPE = "ປະເພດການເກີດ"
_KHMER_BIRTH_TYPE = "ប្រភេទកំណើត"
_LAO_NATURAL_BIRTH = "ການເກີດແບບທຳມະຊາດ"
_KHMER_NATURAL_BIRTH = "កំណើតធម្មជាតិ"
_LAO_BO = "ບໍ"
_KHMER_BO = "បូ"

_NAME_SOURCE = GenerateConfig(naming=NamingConfig(source="name"))
_LAO_ONLY = GenerateConfig(naming=NamingConfig(source="name"), locales=["lo"])

_BIRTH_TYPE = OptionSetIn(
    uid="Xa1b2c3d4e5",
    name="Birth type",
    translations=[
        TranslationIn(locale="lo", property="NAME", value=_LAO_BIRTH_TYPE),
        TranslationIn(locale="km", property="NAME", value=_KHMER_BIRTH_TYPE),
        TranslationIn(locale="lo", property="SHORT_NAME", value="ປະເພດ"),
        TranslationIn(locale="lo", property="DESCRIPTION", value="ຄຳອະທິບາຍ"),
    ],
    options=[
        OptionIn(
            uid="kRRUtYaGett",
            code="NB",
            name="Natural Birth",
            sort_order=1,
            translations=[
                TranslationIn(locale="km", property="NAME", value=_KHMER_NATURAL_BIRTH),
                TranslationIn(locale="lo", property="NAME", value=_LAO_NATURAL_BIRTH),
                TranslationIn(locale="lo", property="SHORT_NAME", value="ທຳມະຊາດ"),
            ],
        )
    ],
)

_BO = OrganisationUnitIn(
    uid="O6uvpzGd5pu",
    name="Bo",
    level=2,
    path="/ImspTQPwCqd/O6uvpzGd5pu",
    translations=[
        TranslationIn(locale="lo", property="NAME", value=_LAO_BO),
        TranslationIn(locale="km", property="NAME", value=_KHMER_BO),
        TranslationIn(locale="km", property="SHORT_NAME", value="បូ."),
    ],
)

_EXPECTED_CONCEPT_DESIGNATIONS = f"""* #kRRUtYaGett "Natural Birth"
* #kRRUtYaGett ^property[+].code = #dhis2-code
* #kRRUtYaGett ^property[=].valueString = "NB"
* #kRRUtYaGett ^designation[+].language = #km
* #kRRUtYaGett ^designation[=].value = "{_KHMER_NATURAL_BIRTH}"
* #kRRUtYaGett ^designation[+].language = #lo
* #kRRUtYaGett ^designation[=].value = "{_LAO_NATURAL_BIRTH}"
"""

_EXPECTED_TITLE_EXTENSIONS = f"""* ^title.extension[+].url = "http://hl7.org/fhir/StructureDefinition/translation"
* ^title.extension[=].extension[+].url = "lang"
* ^title.extension[=].extension[=].valueCode = #km
* ^title.extension[=].extension[+].url = "content"
* ^title.extension[=].extension[=].valueString = "{_KHMER_BIRTH_TYPE}"
* ^title.extension[+].url = "http://hl7.org/fhir/StructureDefinition/translation"
* ^title.extension[=].extension[+].url = "lang"
* ^title.extension[=].extension[=].valueCode = #lo
* ^title.extension[=].extension[+].url = "content"
* ^title.extension[=].extension[=].valueString = "{_LAO_BIRTH_TYPE}"
"""

_EXPECTED_NAME_EXTENSIONS = f"""* name = "Bo"
* name.extension[+].url = "http://hl7.org/fhir/StructureDefinition/translation"
* name.extension[=].extension[+].url = "lang"
* name.extension[=].extension[=].valueCode = #km
* name.extension[=].extension[+].url = "content"
* name.extension[=].extension[=].valueString = "{_KHMER_BO}"
* name.extension[+].url = "http://hl7.org/fhir/StructureDefinition/translation"
* name.extension[=].extension[+].url = "lang"
* name.extension[=].extension[=].valueCode = #lo
* name.extension[=].extension[+].url = "content"
* name.extension[=].extension[=].valueString = "{_LAO_BO}"
"""

_EXPECTED_TERMINOLOGY_DESIGNATIONS = f"""* #O6uvpzGd5pu ^designation[+].language = #km
* #O6uvpzGd5pu ^designation[=].value = "{_KHMER_BO}"
* #O6uvpzGd5pu ^designation[+].language = #lo
* #O6uvpzGd5pu ^designation[=].value = "{_LAO_BO}"
"""


@pytest.mark.parametrize(
    ("java_tag", "expected"),
    [
        ("lo", "lo"),
        ("LO", "lo"),
        ("km", "km"),
        ("pt_BR", "pt-BR"),
        ("pt_br", "pt-BR"),
        ("PT-br", "pt-BR"),
        ("en_GB", "en-GB"),
        ("zh_Hant_TW", "zh-Hant-TW"),
        ("fr", "fr"),
    ],
)
def test_normalize_locale(java_tag: str, expected: str) -> None:
    """Java-style DHIS2 locale tags render as BCP-47: hyphenated, lowercase language, uppercase region."""
    assert normalize_locale(java_tag) == expected


def test_name_translations_keeps_only_name_property_sorted_by_locale() -> None:
    """Only NAME translations survive, locale-normalised and sorted by the normalised tag."""
    selected = name_translations(
        [
            TranslationIn(locale="pt_BR", property="NAME", value="Tipo"),
            TranslationIn(locale="LO", property="NAME", value=_LAO_BIRTH_TYPE),
            TranslationIn(locale="lo", property="SHORT_NAME", value="ປະເພດ"),
            TranslationIn(locale="km", property="DESCRIPTION", value="ការពិពណ៌នា"),
        ],
        [],
    )
    assert [(item.locale, item.value) for item in selected] == [("lo", _LAO_BIRTH_TYPE), ("pt-BR", "Tipo")]


def test_name_translations_filters_to_configured_locales() -> None:
    """A configured locale list drops every other locale, comparing in normalised form."""
    selected = name_translations(
        [
            TranslationIn(locale="lo", property="NAME", value=_LAO_BIRTH_TYPE),
            TranslationIn(locale="km", property="NAME", value=_KHMER_BIRTH_TYPE),
        ],
        ["LO"],
    )
    assert [(item.locale, item.value) for item in selected] == [("lo", _LAO_BIRTH_TYPE)]


def test_name_translations_deduplicates_by_locale_keeping_the_first() -> None:
    """Two entries normalising to one locale collapse to the first one seen."""
    selected = name_translations(
        [
            TranslationIn(locale="pt_BR", property="NAME", value="Primeiro"),
            TranslationIn(locale="pt-br", property="NAME", value="Segundo"),
        ],
        [],
    )
    assert [(item.locale, item.value) for item in selected] == [("pt-BR", "Primeiro")]


def test_option_concepts_carry_name_designations() -> None:
    """Each option's NAME translations follow its property lines as CodeSystem concept designations."""
    content = build_option_set_artifacts([_BIRTH_TYPE], _NAME_SOURCE, experimental=True).artifacts[0].content
    assert _EXPECTED_CONCEPT_DESIGNATIONS in content


def test_option_set_titles_carry_translation_extensions_on_both_artifacts() -> None:
    """The set's NAME translations follow the Description line on the CodeSystem and the ValueSet alike."""
    content = build_option_set_artifacts([_BIRTH_TYPE], _NAME_SOURCE, experimental=True).artifacts[0].content
    assert content.count(_EXPECTED_TITLE_EXTENSIONS) == 2
    code_system, value_set = content.split("\nValueSet: ", maxsplit=1)
    assert _EXPECTED_TITLE_EXTENSIONS in code_system
    assert _EXPECTED_TITLE_EXTENSIONS in value_set


def test_configured_locales_filter_the_emitted_translations() -> None:
    """With `locales = ["lo"]` the Khmer designations and title extensions drop out."""
    content = build_option_set_artifacts([_BIRTH_TYPE], _LAO_ONLY, experimental=True).artifacts[0].content
    assert _LAO_BIRTH_TYPE in content
    assert _KHMER_BIRTH_TYPE not in content
    assert _LAO_NATURAL_BIRTH in content
    assert _KHMER_NATURAL_BIRTH not in content


def test_short_name_and_description_translations_are_not_emitted() -> None:
    """Only NAME translations reach the artifacts in this batch."""
    content = build_option_set_artifacts([_BIRTH_TYPE], _NAME_SOURCE, experimental=True).artifacts[0].content
    assert 'ປະເພດ"' not in content
    assert "ຄຳອະທິບາຍ" not in content


def test_instances_carry_name_translation_extensions() -> None:
    """Both the Organization and the Location name gain one translation extension per NAME translation."""
    content = build_organisation_unit_instances([_BO], GenerateConfig()).artifacts[0].content
    assert content.count(_EXPECTED_NAME_EXTENSIONS) == 2
    organization, location = content.split("\nInstance: Location-", maxsplit=1)
    assert _EXPECTED_NAME_EXTENSIONS in organization
    assert _EXPECTED_NAME_EXTENSIONS in location


def test_organisation_unit_terminology_concepts_carry_designations() -> None:
    """The whole-selection CodeSystem carries each unit's NAME translations as concept designations."""
    content = build_organisation_unit_terminology([_BO], GenerateConfig(), experimental=True).content
    assert _EXPECTED_TERMINOLOGY_DESIGNATIONS in content


def test_validation_suffixes_finding_names_with_the_first_translation() -> None:
    """The deep option-set pass shows the local-language name next to the primary one."""
    option_set = OptionSetIn(
        uid="Xa1b2c3d4e5",
        name="Birth type",
        translations=[TranslationIn(locale="lo", property="NAME", value=_LAO_BIRTH_TYPE)],
        options=[
            OptionIn(
                uid="AcdAzPoqdtd",
                code=" bad ",
                name="Natural Birth",
                sort_order=1,
                translations=[
                    TranslationIn(locale="km", property="NAME", value=_KHMER_NATURAL_BIRTH),
                    TranslationIn(locale="lo", property="NAME", value=_LAO_NATURAL_BIRTH),
                ],
            )
        ],
    )
    report = build_code_validation([option_set], [], GenerateConfig(), "code")
    assert [finding.name for finding in report.findings] == [f"Natural Birth [in Birth type] / {_KHMER_NATURAL_BIRTH}"]

    lao_only = build_code_validation([option_set], [], GenerateConfig(locales=["lo"]), "code")
    assert [finding.name for finding in lao_only.findings] == [f"Natural Birth [in Birth type] / {_LAO_NATURAL_BIRTH}"]


def test_validation_suffixes_option_set_findings() -> None:
    """An option-set-level finding carries the set's own first name translation."""
    long_name = "Residence of the malaria case/s that prompted foci investigation"
    option_set = OptionSetIn(
        uid="Cc3cccccccc",
        name=long_name,
        translations=[TranslationIn(locale="lo", property="NAME", value=_LAO_BIRTH_TYPE)],
    )
    report = build_code_validation([option_set], [], _NAME_SOURCE)
    assert [finding.name for finding in report.findings] == [f"{long_name} / {_LAO_BIRTH_TYPE}"]


def test_findings_without_translations_keep_the_plain_name() -> None:
    """No translations means no suffix - the finding name is byte-identical to the untranslated run."""
    option_set = OptionSetIn(
        uid="Xa1b2c3d4e5",
        name="Birth type",
        options=[OptionIn(uid="AcdAzPoqdtd", code=" bad ", name="Bad", sort_order=1)],
    )
    report = build_code_validation([option_set], [], GenerateConfig(), "code")
    assert [finding.name for finding in report.findings] == ["Bad [in Birth type]"]
