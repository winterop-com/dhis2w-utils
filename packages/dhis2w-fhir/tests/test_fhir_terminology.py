"""Golden tests for the pre-built option-set CodeSystem/ValueSet JSON, and the names the other targets read."""

import json
import re
from typing import Any

from dhis2w_fhir.attributes import AttributeCodeIndex
from dhis2w_fhir.config import GenerateConfig, NamingConfig
from dhis2w_fhir.i18n import TranslationIn
from dhis2w_fhir.period import parse_period
from dhis2w_fhir.resources.examples import build_example_artifacts
from dhis2w_fhir.resources.examples.schemas import ExampleAnswerIn, ExampleResponseIn
from dhis2w_fhir.resources.option_sets import build_option_set_artifacts, option_set_identities
from dhis2w_fhir.resources.option_sets.schemas import OptionIn, OptionSetIdentityPlan, OptionSetIn
from dhis2w_fhir.resources.questionnaires import build_questionnaire_artifacts
from dhis2w_fhir.resources.questionnaires.schemas import QuestionnaireItemIn, QuestionnaireSourceIn
from dhis2w_fhir.status import IgStatus
from dhis2w_fhir.writer import FshBuild, JsonBuild

_NAME_SOURCE = GenerateConfig(naming=NamingConfig(source="name"))
_CANONICAL = "http://example.org/fhir"

#: The closed key set of an emitted CodeSystem, in the order the documents carry it.
_CODE_SYSTEM_KEYS = [
    "resourceType",
    "id",
    "url",
    "identifier",
    "name",
    "title",
    "_title",
    "description",
    "status",
    "experimental",
    "caseSensitive",
    "content",
    "count",
    "valueSet",
    "property",
    "concept",
]

#: The closed key set of an emitted ValueSet - it composes the whole CodeSystem and declares nothing else.
_VALUE_SET_KEYS = [
    "resourceType",
    "id",
    "url",
    "identifier",
    "name",
    "title",
    "_title",
    "description",
    "status",
    "experimental",
    "compose",
]

_BIRTH_TYPE = OptionSetIn(
    uid="Xa1b2c3d4e5",
    name="Birth type",
    options=[
        OptionIn(uid="EBE0c8sZazS", code="CS", name="Scheduled Cesarean", sort_order=2),
        OptionIn(uid="kRRUtYaGett", code="NB", name="Natural Birth", sort_order=1),
        OptionIn(uid="GVcG84DTFOB", code=None, name="Unplanned Cesarean", sort_order=3),
    ],
)

_EXPECTED_UID_SOURCE_CODE_SYSTEM = {
    "resourceType": "CodeSystem",
    "id": "d2-os-birth-type-cs",
    "url": "http://example.org/fhir/CodeSystem/d2-os-birth-type-cs",
    "identifier": [
        {"system": "http://dhis2.org/fhir/id/option-set", "value": "Xa1b2c3d4e5"},
        {"system": "http://dhis2.org/fhir/id/option-set-code", "value": "Xa1b2c3d4e5"},
    ],
    "name": "D2OS_BirthType_CS",
    "title": "Birth type",
    "description": "DHIS2 option set Birth type (Xa1b2c3d4e5). Concept codes are DHIS2 option UIDs.",
    "status": "draft",
    "experimental": True,
    "caseSensitive": True,
    "content": "complete",
    "count": 3,
    "valueSet": "http://example.org/fhir/ValueSet/d2-os-birth-type-vs",
    "property": [
        {
            "code": "dhis2-code",
            "uri": "http://dhis2.org/fhir/property/dhis2-code",
            "description": "DHIS2 option code.",
            "type": "string",
        }
    ],
    "concept": [
        {
            "code": "kRRUtYaGett",
            "display": "Natural Birth",
            "property": [{"code": "dhis2-code", "valueString": "NB"}],
        },
        {
            "code": "EBE0c8sZazS",
            "display": "Scheduled Cesarean",
            "property": [{"code": "dhis2-code", "valueString": "CS"}],
        },
        {
            "code": "GVcG84DTFOB",
            "display": "Unplanned Cesarean",
            "property": [{"code": "dhis2-code", "valueString": "GVcG84DTFOB"}],
        },
    ],
}

_EXPECTED_UID_SOURCE_VALUE_SET = {
    "resourceType": "ValueSet",
    "id": "d2-os-birth-type-vs",
    "url": "http://example.org/fhir/ValueSet/d2-os-birth-type-vs",
    "identifier": [
        {"system": "http://dhis2.org/fhir/id/option-set", "value": "Xa1b2c3d4e5"},
        {"system": "http://dhis2.org/fhir/id/option-set-code", "value": "Xa1b2c3d4e5"},
    ],
    "name": "D2OS_BirthType_VS",
    "title": "Birth type",
    "description": "DHIS2 option set Birth type (Xa1b2c3d4e5). Concept codes are DHIS2 option UIDs.",
    "status": "draft",
    "experimental": True,
    "compose": {"include": [{"system": "http://example.org/fhir/CodeSystem/d2-os-birth-type-cs"}]},
}


def _build(option_sets: list[OptionSetIn], config: GenerateConfig, ig_status: IgStatus = "draft") -> JsonBuild:
    """Build the option-set terminology for one selection against the test canonical."""
    return build_option_set_artifacts(
        option_sets, config, _CANONICAL, ig_status=ig_status, attribute_codes=AttributeCodeIndex()
    )


def _documents(build: JsonBuild) -> dict[str, dict[str, Any]]:
    """Every emitted file, keyed by its relative path, parsed back into a plain JSON document."""
    return {artifact.relative_path: json.loads(artifact.content) for artifact in build.artifacts}


def _code_systems(build: JsonBuild) -> list[dict[str, Any]]:
    """The emitted CodeSystem documents alone, in emission order."""
    return [
        json.loads(artifact.content)
        for artifact in build.artifacts
        if artifact.relative_path.startswith("terminology/CodeSystem-")
    ]


def _concept_codes(document: dict[str, Any]) -> list[str]:
    """The concept codes one CodeSystem document carries, in emission order."""
    return [concept["code"] for concept in document.get("concept", [])]


def _displays(document: dict[str, Any]) -> list[str]:
    """The concept displays one CodeSystem document carries, in emission order."""
    return [concept["display"] for concept in document.get("concept", [])]


def test_name_source_golden() -> None:
    """Name-sourced emission: UID concept codes, DHIS2 codes as dhis2-code properties, sortOrder ordering."""
    build = _build([_BIRTH_TYPE], _NAME_SOURCE)
    assert [artifact.relative_path for artifact in build.artifacts] == [
        "terminology/CodeSystem-d2-os-birth-type-cs.json",
        "terminology/ValueSet-d2-os-birth-type-vs.json",
    ]
    documents = _documents(build)
    assert documents["terminology/CodeSystem-d2-os-birth-type-cs.json"] == _EXPECTED_UID_SOURCE_CODE_SYSTEM
    assert documents["terminology/ValueSet-d2-os-birth-type-vs.json"] == _EXPECTED_UID_SOURCE_VALUE_SET
    assert build.notes == []


def test_every_artifact_is_indented_json_ending_in_a_newline() -> None:
    """The terminology files are written as they are read: two-space indented JSON, one trailing newline."""
    artifact = _build([_BIRTH_TYPE], _NAME_SOURCE).artifacts[0]
    assert artifact.content.endswith("}\n")
    assert '\n  "id": "d2-os-birth-type-cs",' in artifact.content


def test_uid_source_is_default() -> None:
    """Default naming source is uid: file, id, and computational name all derive from the option set UID."""
    documents = _documents(_build([_BIRTH_TYPE], GenerateConfig()))
    code_system = documents["terminology/CodeSystem-d2-os-Xa1b2c3d4e5-cs.json"]
    value_set = documents["terminology/ValueSet-d2-os-Xa1b2c3d4e5-vs.json"]
    assert code_system["name"] == "D2OS_Xa1b2c3d4e5_CS"
    assert code_system["id"] == "d2-os-Xa1b2c3d4e5-cs"
    assert code_system["title"] == "Birth type"
    assert value_set["name"] == "D2OS_Xa1b2c3d4e5_VS"


def test_the_value_set_name_is_the_name_a_questionnaire_canonical_resolves_against() -> None:
    """SUSHI fishes a predefined resource by `name`, so the emitted name is the FSH name Canonical() names."""
    plan = option_set_identities([_BIRTH_TYPE], GenerateConfig())
    identity = plan.identities[0]
    documents = _documents(_build([_BIRTH_TYPE], GenerateConfig()))
    assert identity.value_set_name == "D2OS_Xa1b2c3d4e5_VS"
    assert documents["terminology/ValueSet-d2-os-Xa1b2c3d4e5-vs.json"]["name"] == identity.value_set_name
    assert documents["terminology/CodeSystem-d2-os-Xa1b2c3d4e5-cs.json"]["name"] == identity.code_system_name


def test_code_source_uses_codes_with_uid_property() -> None:
    """concept_code_source="code": valid codes become concept codes, UIDs become dhis2-id properties."""
    build = _build([_BIRTH_TYPE], GenerateConfig(concept_code_source="code"))
    code_system = _code_systems(build)[0]
    assert code_system["concept"][0] == {
        "code": "NB",
        "display": "Natural Birth",
        "property": [{"code": "dhis2-id", "valueCode": "kRRUtYaGett"}],
    }
    assert code_system["description"].endswith("Concept codes are DHIS2 option codes.")
    assert "GVcG84DTFOB" in _concept_codes(code_system)
    assert any("has no code" in note for note in build.notes)


def test_option_set_business_identifiers_carry_both_dhis2_systems() -> None:
    """The CS/VS pair carries both DHIS2 identifiers of the source set under the $DHIS2-OS alias systems."""
    coded = OptionSetIn(uid="Ys9d8f7g6h5", code="BIRTH", name="Sample", options=[])
    for document in _documents(_build([coded], GenerateConfig())).values():
        assert document["identifier"] == [
            {"system": "http://dhis2.org/fhir/id/option-set", "value": "Ys9d8f7g6h5"},
            {"system": "http://dhis2.org/fhir/id/option-set-code", "value": "BIRTH"},
        ]


def test_concept_property_declarations_carry_the_configured_uri() -> None:
    """Each concept property declares a URI under the configured identifier base, not a bare code."""
    config = GenerateConfig(identifier_system_base="https://example.org/dhis2/")
    code_system = _code_systems(_build([_BIRTH_TYPE], config))[0]
    assert code_system["property"] == [
        {
            "code": "dhis2-code",
            "uri": "https://example.org/dhis2/property/dhis2-code",
            "description": "DHIS2 option code.",
            "type": "string",
        }
    ]


def test_urls_follow_the_ig_canonical() -> None:
    """The pair's own URLs and the ValueSet the CodeSystem points at are the IG canonical, not the identifier base."""
    build = build_option_set_artifacts(
        [_BIRTH_TYPE],
        GenerateConfig(),
        "https://ig.example/fhir",
        ig_status="draft",
        attribute_codes=AttributeCodeIndex(),
    )
    documents = _documents(build)
    code_system = documents["terminology/CodeSystem-d2-os-Xa1b2c3d4e5-cs.json"]
    value_set = documents["terminology/ValueSet-d2-os-Xa1b2c3d4e5-vs.json"]
    assert code_system["url"] == "https://ig.example/fhir/CodeSystem/d2-os-Xa1b2c3d4e5-cs"
    assert code_system["valueSet"] == "https://ig.example/fhir/ValueSet/d2-os-Xa1b2c3d4e5-vs"
    assert value_set["url"] == "https://ig.example/fhir/ValueSet/d2-os-Xa1b2c3d4e5-vs"
    assert value_set["compose"]["include"] == [{"system": "https://ig.example/fhir/CodeSystem/d2-os-Xa1b2c3d4e5-cs"}]


def test_generated_terminology_derives_its_publication_state_from_the_ig_status() -> None:
    """Both halves carry status and experimental (the Shareable profiles require the flag), draft only while draft."""
    for document in _documents(_build([_BIRTH_TYPE], GenerateConfig())).values():
        assert document["status"] == "draft"
        assert document["experimental"] is True
    for document in _documents(_build([_BIRTH_TYPE], GenerateConfig(), "active")).values():
        assert document["status"] == "active"
        assert document["experimental"] is False


def test_every_concept_carries_the_complementary_identifier() -> None:
    """No concept goes without the pair: id mode adds dhis2-code, code mode adds dhis2-id."""
    uid_mode = _code_systems(_build([_BIRTH_TYPE], GenerateConfig()))[0]
    assert [concept["property"][0]["code"] for concept in uid_mode["concept"]] == ["dhis2-code"] * 3
    code_mode = _code_systems(_build([_BIRTH_TYPE], GenerateConfig(concept_code_source="code")))[0]
    assert [concept["property"][0]["code"] for concept in code_mode["concept"]] == ["dhis2-id"] * 3


def test_the_property_declaration_covers_exactly_the_property_the_concepts_carry() -> None:
    """One declaration per property really used - the other mode's declaration is not emitted alongside it."""
    uid_mode = _code_systems(_build([_BIRTH_TYPE], GenerateConfig()))[0]
    assert [declaration["code"] for declaration in uid_mode["property"]] == ["dhis2-code"]
    code_mode = _code_systems(_build([_BIRTH_TYPE], GenerateConfig(concept_code_source="code")))[0]
    assert [declaration["code"] for declaration in code_mode["property"]] == ["dhis2-id"]


def test_a_set_without_options_omits_the_concept_and_property_keys() -> None:
    """An empty option set counts zero concepts and declares no property rather than emitting empty arrays."""
    empty = OptionSetIn(uid="Ys9d8f7g6h5", name="Sample", options=[])
    code_system = _code_systems(_build([empty], GenerateConfig()))[0]
    assert code_system["count"] == 0
    assert "concept" not in code_system
    assert "property" not in code_system


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
    build = _build([option_set], GenerateConfig(concept_code_source="code"))
    code_system = _code_systems(build)[0]
    assert _concept_codes(code_system) == ["X", "Op2aaaaaaaa"]
    assert _displays(code_system) == ["One", "Two"]
    assert any("1 option codes collided; fell back to the UID: X (Op2aaaaaaaa)" in note for note in build.notes)


def test_code_source_rejects_invalid_fhir_codes() -> None:
    """An option code that is not a valid FHIR code falls back to the UID with a note."""
    option_set = OptionSetIn(
        uid="Ys9d8f7g6h5",
        name="Sample",
        options=[OptionIn(uid="AcdAzPoqdtd", code=" bad code ", name="Bad", sort_order=1)],
    )
    build = _build([option_set], GenerateConfig(concept_code_source="code"))
    assert _concept_codes(_code_systems(build)[0]) == ["AcdAzPoqdtd"]
    assert any("not a valid FHIR code" in note for note in build.notes)


def test_a_spaced_code_is_carried_verbatim() -> None:
    """A valid FHIR code containing a space is a concept code as it stands - JSON needs no quoting form."""
    option_set = OptionSetIn(
        uid="Ys9d8f7g6h5",
        name="Sample",
        options=[OptionIn(uid="AcdAzPoqdtd", code="two words", name="Spaced", sort_order=1)],
    )
    build = _build([option_set], GenerateConfig(concept_code_source="code"))
    assert _concept_codes(_code_systems(build)[0]) == ["two words"]


def test_slug_collision_gets_uid_suffix() -> None:
    """Two sets kebab-ing to the same slug: the later one in (name, uid) order gets a UID suffix."""
    first = OptionSetIn(uid="Aa1aaaaaaaa", name="Sex", options=[])
    second = OptionSetIn(uid="Bb2bbbbbbbb", name="SEX", options=[])
    build = _build([first, second], _NAME_SOURCE)
    documents = _documents(build)
    assert "terminology/CodeSystem-d2-os-sex-cs.json" in documents
    assert "terminology/CodeSystem-d2-os-sex-aa1aaaaaaaa-cs.json" in documents
    assert documents["terminology/CodeSystem-d2-os-sex-aa1aaaaaaaa-cs.json"]["name"] == "D2OS_Sex_Aa1aaaaaaaa_CS"
    assert documents["terminology/ValueSet-d2-os-sex-aa1aaaaaaaa-vs.json"]["name"] == "D2OS_Sex_Aa1aaaaaaaa_VS"
    assert any("not unique" in note for note in build.notes)


def test_long_name_slug_is_bounded_to_fhir_id_limit() -> None:
    """A very long option-set name yields ids within FHIR's 64-character limit, disambiguated by UID."""
    long_name = "Residence of the malaria case/s that prompted foci investigation"
    option_set = OptionSetIn(uid="Cc3cccccccc", name=long_name, options=[])
    build = _build([option_set], _NAME_SOURCE)
    for path, document in _documents(build).items():
        assert len(document["id"]) <= 64, document["id"]
        assert "cc3cccccccc" in path
    assert any("exceed the FHIR id length" in note for note in build.notes)


def test_sets_sorted_by_name() -> None:
    """Output artifacts come in (name, uid) order regardless of input order, CodeSystem before ValueSet."""
    build = _build(
        [
            OptionSetIn(uid="Bb2bbbbbbbb", name="Zulu", options=[]),
            OptionSetIn(uid="Aa1aaaaaaaa", name="Alpha", options=[]),
        ],
        _NAME_SOURCE,
    )
    assert [artifact.relative_path for artifact in build.artifacts] == [
        "terminology/CodeSystem-d2-os-alpha-cs.json",
        "terminology/ValueSet-d2-os-alpha-vs.json",
        "terminology/CodeSystem-d2-os-zulu-cs.json",
        "terminology/ValueSet-d2-os-zulu-vs.json",
    ]


def test_naming_tokens_flow_into_option_set_artifacts() -> None:
    """Custom prefix / option_set tokens rename artifacts; empty tokens drop out of names and ids."""
    config = GenerateConfig(naming=NamingConfig(source="name", prefix="Dhis2", option_set=""))
    code_system = _code_systems(_build([_BIRTH_TYPE], config))[0]
    assert code_system["name"] == "Dhis2_BirthType_CS"
    assert code_system["id"] == "dhis2-birth-type-cs"
    bare = GenerateConfig(naming=NamingConfig(source="name", prefix="", option_set=""))
    code_system = _code_systems(_build([_BIRTH_TYPE], bare))[0]
    assert code_system["name"] == "BirthType_CS"
    assert code_system["id"] == "birth-type-cs"


#: One option set with every optional field populated, so both documents reach their full key set.
_RICHEST = OptionSetIn(
    uid="b4P0xzW5wcD",
    code="8p",
    name="8p: 8programs",
    options=[
        OptionIn(
            uid="s6eRzXxw4Rq",
            code="1.0.0.0",
            name="I. Hygiene and health Promotion",
            sort_order=1,
            translations=[TranslationIn(locale="lo", property="NAME", value="I. Hygiene")],
        )
    ],
    translations=[TranslationIn(locale="lo", property="NAME", value="8p: 8 programs")],
)


def test_the_richest_option_set_emits_exactly_the_closed_key_sets() -> None:
    """Every optional field populated fills the closed key set of each document - and nothing beyond it."""
    documents = _documents(_build([_RICHEST], GenerateConfig()))
    code_system = documents["terminology/CodeSystem-d2-os-b4P0xzW5wcD-cs.json"]
    value_set = documents["terminology/ValueSet-d2-os-b4P0xzW5wcD-vs.json"]
    assert list(code_system) == _CODE_SYSTEM_KEYS
    assert list(value_set) == _VALUE_SET_KEYS
    assert value_set["name"] == "D2OS_b4P0xzW5wcD_VS"


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


def test_a_uid_fallback_that_is_itself_taken_skips_the_option() -> None:
    """A concept code is unique within a set, so an option with no code left to take is skipped, not repeated."""
    build = _build([_UNRESOLVABLE], GenerateConfig(concept_code_source="code"))
    code_system = _code_systems(build)[0]
    assert _concept_codes(code_system) == ["Op2aaaaaaaa", "DUP"]
    assert _displays(code_system) == ["One", "Two"]
    assert build.notes == ["1 options could not receive a unique concept code; skipped: DUP (Op2aaaaaaaa)"]


def test_a_skipped_option_leaves_the_value_set_consistent_with_the_emitted_concepts() -> None:
    """The ValueSet takes the whole CodeSystem, so the pair covers exactly the concepts that were emitted."""
    documents = _documents(_build([_UNRESOLVABLE], GenerateConfig(concept_code_source="code")))
    code_system = documents["terminology/CodeSystem-d2-os-Ys9d8f7g6h5-cs.json"]
    value_set = documents["terminology/ValueSet-d2-os-Ys9d8f7g6h5-vs.json"]
    assert _concept_codes(code_system) == ["Op2aaaaaaaa", "DUP"]
    assert code_system["count"] == 2
    assert value_set["compose"] == {"include": [{"system": code_system["url"]}]}


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
    documents = _documents(_build([_SEX, _SEX_PEER], _NAME_SOURCE))
    identity = next(item for item in plan.identities if item.uid == "Aa1aaaaaaaa")
    assert identity.value_set_name == "D2OS_Sex_Aa1aaaaaaaa_VS"
    assert documents[f"terminology/CodeSystem-{identity.code_system_id}.json"]["name"] == identity.code_system_name
    assert documents[f"terminology/ValueSet-{identity.value_set_id}.json"]["name"] == identity.value_set_name

    questionnaire = _option_bound_questionnaire(plan)
    assert f"* item[=].answerValueSet = Canonical({identity.value_set_name})" in questionnaire
    assert "D2OS_Aa1aaaaaaaa_VS" not in questionnaire

    example = _option_bound_example(plan)
    assert f'* item[=].answer[+].valueCoding = {identity.code_system_name}#Op1aaaaaaaa "Female"' in example
    assert "D2OS_Aa1aaaaaaaa_CS" not in example


def _option_bound_questionnaire(plan: OptionSetIdentityPlan) -> str:
    """The name-sourced Questionnaire FSH of the option-bound fixture form."""
    build = build_questionnaire_artifacts(
        [_BOUND_FORM],
        _NAME_SOURCE,
        _CANONICAL,
        ig_status="draft",
        option_set_plan=plan,
        attribute_codes=AttributeCodeIndex(),
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
        _CANONICAL,
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
        _CANONICAL,
        option_set_plan=option_set_identities([option_set], _CODE_SOURCE),
    )


def _emitted_concept_codes(option_set: OptionSetIn) -> list[str]:
    """The concept codes the code-sourced CodeSystem of one set really carries, in emission order."""
    return _concept_codes(_code_systems(_build([option_set], _CODE_SOURCE))[0])


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
    code_system = _code_systems(_build([_UNCODABLE], _CODE_SOURCE))[0]
    assert _concept_codes(code_system) == ["Op3aaaaaaaa", "SHARED"]
    assert _displays(code_system) == ["First", "Second"]


def test_page_furniture_escapes_the_markup_characters_the_publisher_parses() -> None:
    """A name holding `<` aborts the IG publisher: `fhir2.base.template` pastes the title into HTML raw."""
    hostile = OptionSetIn(
        uid="Xa1b2c3d4e5",
        code="AGE",
        name="HIV: Age (<5 - 49) & over",
        options=[OptionIn(uid="Op1aaaaaaaa", code="LT5", name="<5", sort_order=1)],
    )
    build = build_option_set_artifacts(
        [hostile],
        GenerateConfig(),
        "http://example.org/fhir",
        ig_status="draft",
        attribute_codes=AttributeCodeIndex(),
    )
    code_system = json.loads(next(a.content for a in build.artifacts if "CodeSystem" in a.relative_path))
    assert code_system["title"] == "HIV: Age (&lt;5 - 49) &amp; over"
    assert "&lt;5" in code_system["description"]
    for character in "<>":
        assert character not in code_system["title"]
        assert character not in code_system["description"]
    # The other half of the rule: a concept display is data a consumer reads back, not page
    # furniture, so it carries the DHIS2 text verbatim.
    assert _displays(code_system) == ["<5"]
