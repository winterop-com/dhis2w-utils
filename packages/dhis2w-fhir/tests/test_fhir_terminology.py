"""Golden tests for option-set CodeSystem/ValueSet FSH emission, and the names the other targets read."""

import re

from dhis2w_fhir.config import GenerateConfig, NamingConfig
from dhis2w_fhir.period import parse_period
from dhis2w_fhir.resources.examples import build_example_artifacts
from dhis2w_fhir.resources.examples.schemas import ExampleAnswerIn, ExampleResponseIn
from dhis2w_fhir.resources.option_sets import build_option_set_artifacts, option_set_identities
from dhis2w_fhir.resources.option_sets.schemas import OptionIn, OptionSetIdentityPlan, OptionSetIn
from dhis2w_fhir.resources.questionnaires import build_questionnaire_artifacts
from dhis2w_fhir.resources.questionnaires.schemas import QuestionnaireItemIn, QuestionnaireSourceIn
from dhis2w_fhir.writer import FshBuild

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
* ^status = #draft
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
* ^status = #draft
* ^experimental = true
* include codes from system D2OS_BirthType_CS
"""


def test_name_source_golden() -> None:
    """Name-sourced emission: UID concept codes, DHIS2 codes as dhis2-code properties, sortOrder ordering."""
    build = build_option_set_artifacts([_BIRTH_TYPE], _NAME_SOURCE, ig_status="draft")
    assert len(build.artifacts) == 1
    artifact = build.artifacts[0]
    assert artifact.relative_path == "terminology/birth-type.fsh"
    assert artifact.fsh_name == "D2OS_BirthType"
    assert artifact.content == _EXPECTED_UID_SOURCE
    assert build.notes == []


def test_uid_source_is_default() -> None:
    """Default naming source is uid: file, id, and FSH name all derive from the option set UID."""
    build = build_option_set_artifacts([_BIRTH_TYPE], GenerateConfig(), ig_status="draft")
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
    build = build_option_set_artifacts([_BIRTH_TYPE], config, ig_status="draft")
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
    content = build_option_set_artifacts([coded], GenerateConfig(), ig_status="draft").artifacts[0].content
    assert content.count("* ^identifier[+].system = $DHIS2-OS\n") == 2
    assert content.count("* ^identifier[+].system = $DHIS2-OS-CODE\n") == 2
    assert content.count('* ^identifier[=].value = "Ys9d8f7g6h5"') == 2
    assert content.count('* ^identifier[=].value = "BIRTH"') == 2


def test_concept_property_declarations_carry_the_configured_uri() -> None:
    """Each concept property declares a URI under the configured identifier base, not a bare code."""
    config = GenerateConfig(identifier_system_base="https://example.org/dhis2/")
    content = build_option_set_artifacts([_BIRTH_TYPE], config, ig_status="draft").artifacts[0].content
    assert '* ^property[=].uri = "https://example.org/dhis2/property/dhis2-code"' in content


def test_generated_terminology_derives_its_publication_state_from_the_ig_status() -> None:
    """Both halves carry ^status and ^experimental (the Shareable profiles require the flag), draft only while draft."""
    draft = build_option_set_artifacts([_BIRTH_TYPE], GenerateConfig(), ig_status="draft").artifacts[0].content
    assert draft.count("* ^status = #draft") == 2
    assert draft.count("* ^experimental = true") == 2
    active = build_option_set_artifacts([_BIRTH_TYPE], GenerateConfig(), ig_status="active").artifacts[0].content
    assert active.count("* ^status = #active") == 2
    assert active.count("* ^experimental = false") == 2
    assert "* ^status = #draft" not in active
    assert "* ^experimental = true" not in active


def test_every_concept_carries_the_complementary_identifier() -> None:
    """No concept goes without the pair: id mode adds dhis2-code, code mode adds dhis2-id."""
    uid_mode = build_option_set_artifacts([_BIRTH_TYPE], GenerateConfig(), ig_status="draft").artifacts[0].content
    assert uid_mode.count("^property[+].code = #dhis2-code") == 4
    code_mode = build_option_set_artifacts([_BIRTH_TYPE], GenerateConfig(concept_code_source="code"), ig_status="draft")
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
    build = build_option_set_artifacts([option_set], GenerateConfig(concept_code_source="code"), ig_status="draft")
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
    build = build_option_set_artifacts([option_set], GenerateConfig(concept_code_source="code"), ig_status="draft")
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
    build = build_option_set_artifacts([option_set], GenerateConfig(concept_code_source="code"), ig_status="draft")
    assert '* #"two words" "Spaced"' in build.artifacts[0].content


def test_slug_collision_gets_uid_suffix() -> None:
    """Two sets kebab-ing to the same slug: the later one in (name, uid) order gets a UID suffix."""
    first = OptionSetIn(uid="Aa1aaaaaaaa", name="Sex", options=[])
    second = OptionSetIn(uid="Bb2bbbbbbbb", name="SEX", options=[])
    build = build_option_set_artifacts([first, second], _NAME_SOURCE, ig_status="draft")
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
    build = build_option_set_artifacts([option_set], _NAME_SOURCE, ig_status="draft")
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
        ig_status="draft",
    )
    assert [artifact.relative_path for artifact in build.artifacts] == [
        "terminology/alpha.fsh",
        "terminology/zulu.fsh",
    ]


def test_naming_tokens_flow_into_option_set_artifacts() -> None:
    """Custom prefix / option_set tokens rename artifacts; empty tokens drop out of names and ids."""
    config = GenerateConfig(naming=NamingConfig(source="name", prefix="Dhis2", option_set=""))
    build = build_option_set_artifacts([_BIRTH_TYPE], config, ig_status="draft")
    content = build.artifacts[0].content
    assert "CodeSystem: Dhis2_BirthType_CS" in content
    assert "Id: dhis2-birth-type-cs" in content
    bare = GenerateConfig(naming=NamingConfig(source="name", prefix="", option_set=""))
    content = build_option_set_artifacts([_BIRTH_TYPE], bare, ig_status="draft").artifacts[0].content
    assert "CodeSystem: BirthType_CS" in content
    assert "Id: birth-type-cs" in content


#: Three options whose codes force the collision fall-back to collide too: the first takes the UID
#: of the third as its DHIS2 code, and the third's own code is already taken by the second.
_UNRESOLVABLE = OptionSetIn(
    uid="Ys9d8f7g6h5",
    name="Dup",
    options=[
        OptionIn(uid="Op1aaaaaaaa", code="Op2aaaaaaaa", name="One", sort_order=1),
        OptionIn(uid="Op3aaaaaaaa", code="DUP", name="Two", sort_order=2),
        OptionIn(uid="Op2aaaaaaaa", code="DUP", name="Three", sort_order=3),
    ],
)


def _declared_concepts(content: str) -> list[str]:
    """The concept declaration lines of one CodeSystem - the `* #<code> "<display>"` lines alone."""
    return [line for line in content.splitlines() if re.match(r'^\* #\S+ "', line)]


def test_a_uid_fallback_that_is_itself_taken_skips_the_option() -> None:
    """A concept code is unique within a set, so an option with no code left to take is skipped, not repeated."""
    build = build_option_set_artifacts([_UNRESOLVABLE], GenerateConfig(concept_code_source="code"), ig_status="draft")
    content = build.artifacts[0].content
    assert content.count('* #Op2aaaaaaaa "') == 1
    assert '* #Op2aaaaaaaa "One"' in content
    assert '"Three"' not in content
    assert build.notes == ["1 options could not receive a unique concept code; skipped: DUP (Op2aaaaaaaa)"]


def test_a_skipped_option_leaves_the_value_set_consistent_with_the_emitted_concepts() -> None:
    """The ValueSet takes the whole CodeSystem, so the pair covers exactly the concepts that were emitted."""
    content = (
        build_option_set_artifacts([_UNRESOLVABLE], GenerateConfig(concept_code_source="code"), ig_status="draft")
        .artifacts[0]
        .content
    )
    code_system, _, value_set = content.partition("\nValueSet: ")
    assert _declared_concepts(code_system) == ['* #Op2aaaaaaaa "One"', '* #DUP "Two"']
    assert _declared_concepts(value_set) == []
    assert "* include codes from system D2OS_Ys9d8f7g6h5_CS" in value_set


#: Two option sets whose names kebab to the same slug, so the later one takes a UID suffix - the
#: case that proves a bound question reads the plan rather than pascal-casing the name itself.
_SEX_PEER = OptionSetIn(uid="Bb2bbbbbbbb", name="SEX", options=[OptionIn(uid="Op2aaaaaaaa", code="M", name="Male")])
_SEX = OptionSetIn(uid="Aa1aaaaaaaa", name="Sex", options=[OptionIn(uid="Op1aaaaaaaa", code="F", name="Female")])

_BOUND_FORM = QuestionnaireSourceIn(
    uid="Ds1aaaaaaaa",
    name="Demographics",
    kind="aggregate",
    flat_items=[QuestionnaireItemIn(uid="De1aaaaaaaa", name="Gender", value_type="TEXT", option_set_uid="Aa1aaaaaaaa")],
)

_BOUND_RESPONSE = ExampleResponseIn(
    instance_id="Ds1aaaaaaaa-1",
    target_uid="Ds1aaaaaaaa",
    kind="aggregate",
    organisation_unit_uid="Ou1aaaaaaaa",
    status_code="completed",
    period=parse_period("202606"),
    answers=[ExampleAnswerIn(data_element_uid="De1aaaaaaaa", value="F")],
)


def test_name_sourced_option_set_names_are_read_by_the_questionnaire_and_the_example() -> None:
    """An option set is named once, over the whole selection: the bound question and the coded answer read it."""
    plan = option_set_identities([_SEX, _SEX_PEER], _NAME_SOURCE)
    terminology = build_option_set_artifacts([_SEX, _SEX_PEER], _NAME_SOURCE, ig_status="draft")
    identity = next(item for item in plan.identities if item.uid == "Aa1aaaaaaaa")
    emitted = "\n".join(artifact.content for artifact in terminology.artifacts)
    assert identity.value_set_name == "D2OS_Sex_Aa1aaaaaaaa_VS"
    assert f"CodeSystem: {identity.code_system_name}\n" in emitted
    assert f"ValueSet: {identity.value_set_name}\n" in emitted

    questionnaire = _option_bound_questionnaire(plan)
    assert f"* item[=].answerValueSet = Canonical({identity.value_set_name})" in questionnaire
    assert "D2OS_Aa1aaaaaaaa_VS" not in questionnaire

    example = _option_bound_example(plan)
    assert f'* item[=].answer[+].valueCoding = {identity.code_system_name}#Op1aaaaaaaa "Female"' in example
    assert "D2OS_Aa1aaaaaaaa_CS" not in example


def _option_bound_questionnaire(plan: OptionSetIdentityPlan) -> str:
    """The name-sourced Questionnaire FSH of the option-bound fixture form."""
    build = build_questionnaire_artifacts(
        [_BOUND_FORM], _NAME_SOURCE, "http://example.org/fhir", ig_status="draft", option_set_plan=plan
    )
    assert build.notes == []
    return next(artifact.content for artifact in build.artifacts if artifact.relative_path.endswith("Ds1aaaaaaaa.fsh"))


def _option_bound_example(plan: OptionSetIdentityPlan) -> str:
    """The name-sourced QuestionnaireResponse FSH answering the option-bound fixture question."""
    build = build_example_artifacts(
        [_BOUND_FORM],
        [_BOUND_RESPONSE],
        [_SEX],
        _NAME_SOURCE,
        "http://example.org/fhir",
        option_set_plan=plan,
    )
    assert build.notes == []
    return build.artifacts[0].content


#: One option whose DHIS2 code is present but carries a double space, which R4 `code` forbids.
_INVALID_CODE = OptionSetIn(
    uid="Cc3cccccccc",
    name="Sex",
    options=[OptionIn(uid="Op1aaaaaaaa", code="M  F", name="Either", sort_order=1)],
)

#: Two options asking for the same code, so the second takes its UID and the first keeps the code.
_COLLIDING = OptionSetIn(
    uid="Dd4dddddddd",
    name="Outcome",
    options=[
        OptionIn(uid="Op1aaaaaaaa", code="DUP", name="One", sort_order=1),
        OptionIn(uid="Op2aaaaaaaa", code="DUP", name="Two", sort_order=2),
    ],
)

#: An option whose UID fall-back is taken by a peer's DHIS2 code, so it receives no concept code
#: at all. It leads the fetched order and trails the sort order, which is how an answer reaches it.
_UNCODABLE = OptionSetIn(
    uid="Ee5eeeeeeee",
    name="Referral",
    options=[
        OptionIn(uid="Op3aaaaaaaa", code="SHARED", name="Third", sort_order=3),
        OptionIn(uid="Op1aaaaaaaa", code="Op3aaaaaaaa", name="First", sort_order=1),
        OptionIn(uid="Op2aaaaaaaa", code="SHARED", name="Second", sort_order=2),
    ],
)

_CODE_SOURCE = GenerateConfig(concept_code_source="code")

_CODED_FORM = QuestionnaireSourceIn(
    uid="Ds2aaaaaaaa",
    name="Referrals",
    kind="aggregate",
    flat_items=[QuestionnaireItemIn(uid="De1aaaaaaaa", name="Outcome", value_type="TEXT", option_set_uid="")],
)

_ANSWER_CODING_PATTERN = re.compile(r'valueCoding = \w+#(\S+) "')


def _coded_example(option_set: OptionSetIn, value: str) -> FshBuild:
    """The code-sourced example build answering one question bound to `option_set` with the stored `value`."""
    form = _CODED_FORM.model_copy(
        update={"flat_items": [_CODED_FORM.flat_items[0].model_copy(update={"option_set_uid": option_set.uid})]}
    )
    response = ExampleResponseIn(
        instance_id=f"{form.uid}-1",
        target_uid=form.uid,
        kind="aggregate",
        organisation_unit_uid="Ou1aaaaaaaa",
        status_code="completed",
        period=parse_period("202606"),
        answers=[ExampleAnswerIn(data_element_uid="De1aaaaaaaa", value=value)],
    )
    return build_example_artifacts(
        [form],
        [response],
        [option_set],
        _CODE_SOURCE,
        "http://example.org/fhir",
        option_set_plan=option_set_identities([option_set], _CODE_SOURCE),
    )


def _emitted_concept_codes(option_set: OptionSetIn) -> list[str]:
    """The concept codes the code-sourced CodeSystem of one set really carries, in emission order."""
    content = build_option_set_artifacts([option_set], _CODE_SOURCE, ig_status="draft").artifacts[0].content
    return [line.split(" ")[1].removeprefix("#") for line in _declared_concepts(content)]


def test_a_code_mode_example_codes_an_unusable_code_as_the_uid_the_code_system_carries() -> None:
    """An option whose DHIS2 code is no FHIR code is a concept under its UID, and the answer says so."""
    build = _coded_example(_INVALID_CODE, "M  F")
    assert build.notes == []
    codings = _ANSWER_CODING_PATTERN.findall(build.artifacts[0].content)
    assert codings == ["Op1aaaaaaaa"]
    assert set(codings) <= set(_emitted_concept_codes(_INVALID_CODE))


def test_a_code_mode_example_reads_the_uid_a_collided_option_fell_back_to() -> None:
    """The second option of a code collision is a concept under its UID, so the answer codes the UID too."""
    build = _coded_example(_COLLIDING, "Op2aaaaaaaa")
    assert build.notes == []
    codings = _ANSWER_CODING_PATTERN.findall(build.artifacts[0].content)
    assert codings == ["Op2aaaaaaaa"]
    assert _emitted_concept_codes(_COLLIDING) == ["DUP", "Op2aaaaaaaa"]
    assert set(codings) <= set(_emitted_concept_codes(_COLLIDING))


def test_an_answer_selecting_an_option_with_no_concept_code_is_left_unanswered() -> None:
    """No concept was written for the option, so the example says nothing rather than name a stranger's code."""
    build = _coded_example(_UNCODABLE, "SHARED")
    content = build.artifacts[0].content
    assert _ANSWER_CODING_PATTERN.findall(content) == []
    assert "answer[" not in content
    assert build.notes == [
        "1 example answers select an option the CodeSystem holds no concept for; left unanswered: "
        "Op3aaaaaaaa in Referral (Ee5eeeeeeee)"
    ]
    terminology = build_option_set_artifacts([_UNCODABLE], _CODE_SOURCE, ig_status="draft").artifacts[0].content
    assert _declared_concepts(terminology) == ['* #Op3aaaaaaaa "First"', '* #SHARED "Second"']
    assert '"Third"' not in terminology
