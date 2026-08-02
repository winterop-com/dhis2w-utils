"""Golden tests for option-set CodeSystem/ValueSet FSH emission."""

from dhis2w_fhir.config import GenerateConfig, NamingConfig
from dhis2w_fhir.resources.option_sets import build_option_set_artifacts
from dhis2w_fhir.resources.option_sets.schemas import OptionIn, OptionSetIn

_NAME_SOURCE = GenerateConfig(naming=NamingConfig(source="name"))

_BIRTH_TYPE = OptionSetIn(
    uid="Xa1b2c3d4e5",
    name="Birth type",
    options=[
        OptionIn(uid="EBE0c8sZazS", code="CS", name="Scheduled Cesarean", sort_order=2),
        OptionIn(uid="kRRUtYaGett", code="NB", name="Natural Birth", sort_order=1),
        OptionIn(uid="GVcG84DTFOB", code=None, name="Unplanned Cesarean", sort_order=3),
    ],
)

_EXPECTED_UID_SOURCE = """CodeSystem: D2OS_BirthType_CS
Id: d2-os-birth-type-cs
Title: "Birth type"
Description: "DHIS2 option set Birth type (Xa1b2c3d4e5). Concept codes are DHIS2 option UIDs."
* ^identifier[+].system = $DHIS2-OS
* ^identifier[=].value = "Xa1b2c3d4e5"
* ^identifier[+].system = $DHIS2-OS-CODE
* ^identifier[=].value = "Xa1b2c3d4e5"
* ^status = #active
* ^experimental = true
* ^content = #complete
* ^caseSensitive = true
* ^valueSet = Canonical(D2OS_BirthType_VS)
* ^property[+].code = #dhis2-code
* ^property[=].uri = "http://dhis2.org/fhir/property/dhis2-code"
* ^property[=].description = "DHIS2 option code."
* ^property[=].type = #string
* #kRRUtYaGett "Natural Birth"
* #kRRUtYaGett ^property[+].code = #dhis2-code
* #kRRUtYaGett ^property[=].valueString = "NB"
* #EBE0c8sZazS "Scheduled Cesarean"
* #EBE0c8sZazS ^property[+].code = #dhis2-code
* #EBE0c8sZazS ^property[=].valueString = "CS"
* #GVcG84DTFOB "Unplanned Cesarean"
* #GVcG84DTFOB ^property[+].code = #dhis2-code
* #GVcG84DTFOB ^property[=].valueString = "GVcG84DTFOB"

ValueSet: D2OS_BirthType_VS
Id: d2-os-birth-type-vs
Title: "Birth type"
Description: "DHIS2 option set Birth type (Xa1b2c3d4e5). Concept codes are DHIS2 option UIDs."
* ^identifier[+].system = $DHIS2-OS
* ^identifier[=].value = "Xa1b2c3d4e5"
* ^identifier[+].system = $DHIS2-OS-CODE
* ^identifier[=].value = "Xa1b2c3d4e5"
* ^status = #active
* ^experimental = true
* include codes from system D2OS_BirthType_CS
"""


def test_name_source_golden() -> None:
    """Name-sourced emission: UID concept codes, DHIS2 codes as dhis2-code properties, sortOrder ordering."""
    build = build_option_set_artifacts([_BIRTH_TYPE], _NAME_SOURCE, experimental=True)
    assert len(build.artifacts) == 1
    artifact = build.artifacts[0]
    assert artifact.relative_path == "terminology/birth-type.fsh"
    assert artifact.fsh_name == "D2OS_BirthType"
    assert artifact.content == _EXPECTED_UID_SOURCE
    assert build.notes == []


def test_uid_source_is_default() -> None:
    """Default naming source is uid: file, id, and FSH name all derive from the option set UID."""
    build = build_option_set_artifacts([_BIRTH_TYPE], GenerateConfig(), experimental=True)
    artifact = build.artifacts[0]
    assert artifact.relative_path == "terminology/Xa1b2c3d4e5.fsh"
    assert artifact.fsh_name == "D2OS_Xa1b2c3d4e5"
    assert "CodeSystem: D2OS_Xa1b2c3d4e5_CS" in artifact.content
    assert "Id: d2-os-Xa1b2c3d4e5-cs" in artifact.content
    assert 'Title: "Birth type"' in artifact.content
    assert build.notes == []


def test_code_source_uses_codes_with_uid_property() -> None:
    """concept_code_source="code": valid codes become concept codes, UIDs become dhis2-id properties."""
    config = GenerateConfig(concept_code_source="code")
    build = build_option_set_artifacts([_BIRTH_TYPE], config, experimental=True)
    content = build.artifacts[0].content
    assert '* #NB "Natural Birth"' in content
    assert "* #NB ^property[+].code = #dhis2-id" in content
    assert "* #NB ^property[=].valueCode = #kRRUtYaGett" in content
    assert "Concept codes are DHIS2 option codes." in content
    assert '* #GVcG84DTFOB "Unplanned Cesarean"' in content
    assert any("has no code" in note for note in build.notes)


def test_option_set_business_identifiers_use_the_foundation_aliases() -> None:
    """The CS/VS pair carries both DHIS2 identifiers of the source set through the $DHIS2-OS aliases."""
    coded = OptionSetIn(uid="Ys9d8f7g6h5", code="BIRTH", name="Sample", options=[])
    content = build_option_set_artifacts([coded], GenerateConfig(), experimental=True).artifacts[0].content
    assert content.count("* ^identifier[+].system = $DHIS2-OS\n") == 2
    assert content.count("* ^identifier[+].system = $DHIS2-OS-CODE\n") == 2
    assert content.count('* ^identifier[=].value = "Ys9d8f7g6h5"') == 2
    assert content.count('* ^identifier[=].value = "BIRTH"') == 2


def test_concept_property_declarations_carry_the_configured_uri() -> None:
    """Each concept property declares a URI under the configured identifier base, not a bare code."""
    config = GenerateConfig(identifier_system_base="https://example.org/dhis2/")
    content = build_option_set_artifacts([_BIRTH_TYPE], config, experimental=True).artifacts[0].content
    assert '* ^property[=].uri = "https://example.org/dhis2/property/dhis2-code"' in content


def test_generated_terminology_derives_experimental_from_the_ig_status() -> None:
    """Both halves carry ^experimental (ShareableCodeSystem/ValueSet require it), true only while draft."""
    draft = build_option_set_artifacts([_BIRTH_TYPE], GenerateConfig(), experimental=True).artifacts[0].content
    assert draft.count("* ^experimental = true") == 2
    active = build_option_set_artifacts([_BIRTH_TYPE], GenerateConfig(), experimental=False).artifacts[0].content
    assert active.count("* ^experimental = false") == 2
    assert "* ^experimental = true" not in active


def test_every_concept_carries_the_complementary_identifier() -> None:
    """No concept goes without the pair: id mode adds dhis2-code, code mode adds dhis2-id."""
    uid_mode = build_option_set_artifacts([_BIRTH_TYPE], GenerateConfig(), experimental=True).artifacts[0].content
    assert uid_mode.count("^property[+].code = #dhis2-code") == 4
    code_mode = build_option_set_artifacts([_BIRTH_TYPE], GenerateConfig(concept_code_source="code"), experimental=True)
    assert code_mode.artifacts[0].content.count("^property[+].code = #dhis2-id") == 4


def test_colliding_concept_codes_fall_back_to_the_uid() -> None:
    """Two options sharing one DHIS2 code cannot repeat a concept code, so the later one uses its UID."""
    option_set = OptionSetIn(
        uid="Ys9d8f7g6h5",
        name="Dup",
        options=[
            OptionIn(uid="Op1aaaaaaaa", code="X", name="One", sort_order=1),
            OptionIn(uid="Op2aaaaaaaa", code="X", name="Two", sort_order=2),
        ],
    )
    build = build_option_set_artifacts([option_set], GenerateConfig(concept_code_source="code"), experimental=True)
    content = build.artifacts[0].content
    assert '* #X "One"' in content
    assert '* #Op2aaaaaaaa "Two"' in content
    assert any("1 option codes collided; fell back to the UID: X (Op2aaaaaaaa)" in note for note in build.notes)


def test_code_source_rejects_invalid_fhir_codes() -> None:
    """An option code that is not a valid FHIR code falls back to the UID with a note."""
    option_set = OptionSetIn(
        uid="Ys9d8f7g6h5",
        name="Sample",
        options=[OptionIn(uid="AcdAzPoqdtd", code=" bad code ", name="Bad", sort_order=1)],
    )
    build = build_option_set_artifacts([option_set], GenerateConfig(concept_code_source="code"), experimental=True)
    content = build.artifacts[0].content
    assert '* #AcdAzPoqdtd "Bad"' in content
    assert any("not a valid FHIR code" in note for note in build.notes)


def test_spaced_code_uses_quoted_form() -> None:
    """A valid FHIR code containing a space is emitted with the quoted #"..." form."""
    option_set = OptionSetIn(
        uid="Ys9d8f7g6h5",
        name="Sample",
        options=[OptionIn(uid="AcdAzPoqdtd", code="two words", name="Spaced", sort_order=1)],
    )
    build = build_option_set_artifacts([option_set], GenerateConfig(concept_code_source="code"), experimental=True)
    assert '* #"two words" "Spaced"' in build.artifacts[0].content


def test_slug_collision_gets_uid_suffix() -> None:
    """Two sets kebab-ing to the same slug: the later one in (name, uid) order gets a UID suffix."""
    first = OptionSetIn(uid="Aa1aaaaaaaa", name="Sex", options=[])
    second = OptionSetIn(uid="Bb2bbbbbbbb", name="SEX", options=[])
    build = build_option_set_artifacts([first, second], _NAME_SOURCE, experimental=True)
    paths = [artifact.relative_path for artifact in build.artifacts]
    assert "terminology/sex.fsh" in paths
    assert "terminology/sex-aa1aaaaaaaa.fsh" in paths
    disambiguated = next(artifact for artifact in build.artifacts if artifact.fsh_name.endswith("Aa1aaaaaaaa"))
    assert disambiguated.fsh_name == "D2OS_Sex_Aa1aaaaaaaa"
    assert "CodeSystem: D2OS_Sex_Aa1aaaaaaaa_CS" in disambiguated.content
    assert any("not unique" in note for note in build.notes)


def test_long_name_slug_is_bounded_to_fhir_id_limit() -> None:
    """A very long option-set name yields ids within FHIR's 64-character limit, disambiguated by UID."""
    long_name = "Residence of the malaria case/s that prompted foci investigation"
    option_set = OptionSetIn(uid="Cc3cccccccc", name=long_name, options=[])
    build = build_option_set_artifacts([option_set], _NAME_SOURCE, experimental=True)
    artifact = build.artifacts[0]
    for line in artifact.content.splitlines():
        if line.startswith("Id: "):
            assert len(line.removeprefix("Id: ")) <= 64, line
    assert "cc3cccccccc" in artifact.relative_path
    assert any("exceed the FHIR id length" in note for note in build.notes)


def test_sets_sorted_by_name() -> None:
    """Output artifacts come in (name, uid) order regardless of input order."""
    build = build_option_set_artifacts(
        [
            OptionSetIn(uid="Bb2bbbbbbbb", name="Zulu", options=[]),
            OptionSetIn(uid="Aa1aaaaaaaa", name="Alpha", options=[]),
        ],
        _NAME_SOURCE,
        experimental=True,
    )
    assert [artifact.relative_path for artifact in build.artifacts] == [
        "terminology/alpha.fsh",
        "terminology/zulu.fsh",
    ]


def test_naming_tokens_flow_into_option_set_artifacts() -> None:
    """Custom prefix / option_set tokens rename artifacts; empty tokens drop out of names and ids."""
    config = GenerateConfig(naming=NamingConfig(source="name", prefix="Dhis2", option_set=""))
    build = build_option_set_artifacts([_BIRTH_TYPE], config, experimental=True)
    content = build.artifacts[0].content
    assert "CodeSystem: Dhis2_BirthType_CS" in content
    assert "Id: dhis2-birth-type-cs" in content
    bare = GenerateConfig(naming=NamingConfig(source="name", prefix="", option_set=""))
    content = build_option_set_artifacts([_BIRTH_TYPE], bare, experimental=True).artifacts[0].content
    assert "CodeSystem: BirthType_CS" in content
    assert "Id: birth-type-cs" in content
