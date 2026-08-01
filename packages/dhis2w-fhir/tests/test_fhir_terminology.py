"""Golden tests for option-set CodeSystem/ValueSet FSH emission."""

from dhis2w_fhir.models import GenerateConfig, NamingConfig, OptionInput, OptionSetInput
from dhis2w_fhir.terminology import build_option_set_artifacts

_BIRTH_TYPE = OptionSetInput(
    uid="Xa1b2c3d4e5",
    name="Birth type",
    options=[
        OptionInput(uid="EBE0c8sZazS", code="CS", name="Scheduled Cesarean", sort_order=2),
        OptionInput(uid="kRRUtYaGett", code="NB", name="Natural Birth", sort_order=1),
        OptionInput(uid="GVcG84DTFOB", code=None, name="Unplanned Cesarean", sort_order=3),
    ],
)

_EXPECTED_UID_SOURCE = """CodeSystem: D2OSBirthTypeCS
Id: d2-os-birth-type-cs
Title: "Birth type"
Description: "DHIS2 option set Birth type (Xa1b2c3d4e5). Concept codes are DHIS2 option UIDs."
* ^status = #active
* ^content = #complete
* ^caseSensitive = true
* ^property[+].code = #dhis2-code
* ^property[=].description = "DHIS2 option code."
* ^property[=].type = #string
* #kRRUtYaGett "Natural Birth"
* #kRRUtYaGett ^property[+].code = #dhis2-code
* #kRRUtYaGett ^property[=].valueString = "NB"
* #EBE0c8sZazS "Scheduled Cesarean"
* #EBE0c8sZazS ^property[+].code = #dhis2-code
* #EBE0c8sZazS ^property[=].valueString = "CS"
* #GVcG84DTFOB "Unplanned Cesarean"

ValueSet: D2OSBirthTypeVS
Id: d2-os-birth-type-vs
Title: "Birth type"
Description: "DHIS2 option set Birth type (Xa1b2c3d4e5). Concept codes are DHIS2 option UIDs."
* ^status = #active
* include codes from system D2OSBirthTypeCS
"""


def test_uid_source_golden() -> None:
    """Default emission: UID concept codes, DHIS2 codes as dhis2-code properties, sortOrder ordering."""
    build = build_option_set_artifacts([_BIRTH_TYPE], GenerateConfig())
    assert len(build.artifacts) == 1
    artifact = build.artifacts[0]
    assert artifact.relative_path == "terminology/birth-type.fsh"
    assert artifact.fsh_name == "D2OSBirthType"
    assert artifact.content == _EXPECTED_UID_SOURCE
    assert build.notes == []


def test_code_source_uses_codes_with_uid_property() -> None:
    """concept_code_source="code": valid codes become concept codes, UIDs become dhis2-uid properties."""
    config = GenerateConfig(concept_code_source="code")
    build = build_option_set_artifacts([_BIRTH_TYPE], config)
    content = build.artifacts[0].content
    assert '* #NB "Natural Birth"' in content
    assert "* #NB ^property[+].code = #dhis2-uid" in content
    assert "* #NB ^property[=].valueCode = #kRRUtYaGett" in content
    assert "Concept codes are DHIS2 option codes." in content
    assert '* #GVcG84DTFOB "Unplanned Cesarean"' in content
    assert any("has no code" in note for note in build.notes)


def test_code_source_rejects_invalid_fhir_codes() -> None:
    """An option code that is not a valid FHIR code falls back to the UID with a note."""
    option_set = OptionSetInput(
        uid="Ys9d8f7g6h5",
        name="Sample",
        options=[OptionInput(uid="AcdAzPoqdtd", code=" bad code ", name="Bad", sort_order=1)],
    )
    build = build_option_set_artifacts([option_set], GenerateConfig(concept_code_source="code"))
    content = build.artifacts[0].content
    assert '* #AcdAzPoqdtd "Bad"' in content
    assert any("not a valid FHIR code" in note for note in build.notes)


def test_spaced_code_uses_quoted_form() -> None:
    """A valid FHIR code containing a space is emitted with the quoted #"..." form."""
    option_set = OptionSetInput(
        uid="Ys9d8f7g6h5",
        name="Sample",
        options=[OptionInput(uid="AcdAzPoqdtd", code="two words", name="Spaced", sort_order=1)],
    )
    build = build_option_set_artifacts([option_set], GenerateConfig(concept_code_source="code"))
    assert '* #"two words" "Spaced"' in build.artifacts[0].content


def test_slug_collision_gets_uid_suffix() -> None:
    """Two sets kebab-ing to the same slug: the later one in (name, uid) order gets a UID suffix."""
    first = OptionSetInput(uid="Aa1aaaaaaaa", name="Sex", options=[])
    second = OptionSetInput(uid="Bb2bbbbbbbb", name="SEX", options=[])
    build = build_option_set_artifacts([first, second], GenerateConfig())
    paths = [artifact.relative_path for artifact in build.artifacts]
    assert "terminology/sex.fsh" in paths
    assert "terminology/sex-aa1aaaaaaaa.fsh" in paths
    assert any("not unique" in note for note in build.notes)


def test_long_name_slug_is_bounded_to_fhir_id_limit() -> None:
    """A very long option-set name yields ids within FHIR's 64-character limit, disambiguated by UID."""
    long_name = "Residence of the malaria case/s that prompted foci investigation"
    option_set = OptionSetInput(uid="Cc3cccccccc", name=long_name, options=[])
    build = build_option_set_artifacts([option_set], GenerateConfig())
    artifact = build.artifacts[0]
    for line in artifact.content.splitlines():
        if line.startswith("Id: "):
            assert len(line.removeprefix("Id: ")) <= 64, line
    assert "cc3cccccccc" in artifact.relative_path
    assert any("exceeds the FHIR id length" in note for note in build.notes)


def test_sets_sorted_by_name() -> None:
    """Output artifacts come in (name, uid) order regardless of input order."""
    build = build_option_set_artifacts(
        [
            OptionSetInput(uid="Bb2bbbbbbbb", name="Zulu", options=[]),
            OptionSetInput(uid="Aa1aaaaaaaa", name="Alpha", options=[]),
        ],
        GenerateConfig(),
    )
    assert [artifact.relative_path for artifact in build.artifacts] == [
        "terminology/alpha.fsh",
        "terminology/zulu.fsh",
    ]


def test_naming_tokens_flow_into_option_set_artifacts() -> None:
    """Custom prefix / option_set tokens rename artifacts; empty tokens drop out of names and ids."""
    config = GenerateConfig(naming=NamingConfig(prefix="Dhis2", option_set=""))
    build = build_option_set_artifacts([_BIRTH_TYPE], config)
    content = build.artifacts[0].content
    assert "CodeSystem: Dhis2BirthTypeCS" in content
    assert "Id: dhis2-birth-type-cs" in content
    bare = GenerateConfig(naming=NamingConfig(prefix="", option_set=""))
    content = build_option_set_artifacts([_BIRTH_TYPE], bare).artifacts[0].content
    assert "CodeSystem: BirthTypeCS" in content
    assert "Id: birth-type-cs" in content
