"""The tracker registration form: the projection it is fetched as, the two artifacts it emits, and their parity.

A tracker program's registration is the form a person is enrolled through, so it maps onto a
`Questionnaire` the same way every other DHIS2 form does - what differs is the object its
questions come from. These tests hold that: the questions are the program's tracked entity
attributes in DHIS2 sort order, an option-set-bound attribute binds the very ValueSet a
data element would, and both emitters say the same thing about all of it.

The SUSHI goldens under `tests/data/r4/` were harvested the way the ConceptMap family's were:
the emitted FSH of `_REGISTRATION` compiled by SUSHI, written back byte for byte. They are never
edited by hand - when the parity test fails, the builder is what changed.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from dhis2w_fhir import (
    AttributeCodeIndex,
    GenerateConfig,
    OptionSetIn,
    build_data_dictionary_documents,
    build_questionnaire_artifacts,
    build_questionnaire_documents,
    option_set_identities,
)
from dhis2w_fhir.r4 import FhirBase
from dhis2w_fhir.resources.questionnaires import (
    REGISTRATION_FILE_STEM,
    bound_option_set_uids,
    grouping_identifiers,
    question_code_system,
)
from dhis2w_fhir.resources.questionnaires.assignments import assignment_container, assignment_container_uid
from dhis2w_fhir.resources.questionnaires.schemas import (
    CAPTURED_FORM_KINDS,
    FORM_KIND_PROFILES,
    ProgramContextIn,
    QuestionnaireItemIn,
    QuestionnaireNaming,
    QuestionnaireSourceIn,
    plan_questionnaire_stems,
)

_GOLDEN_DIRECTORY = Path(__file__).parent / "data" / "r4"

#: The IG the goldens were compiled for - `[ig] canonical` and `[ig] status` of its `fhir.toml`.
_CANONICAL = "http://example.org/fhir"

#: The option set only a tracked entity attribute binds, which is what makes the closure's reach visible.
_MARITAL_STATUS = OptionSetIn(uid="Os3aaaaaaaa", name="Marital status")

#: The registration form the goldens were compiled from: one unique coded attribute, one bound to
#: an option set. `form_name` differs from `name` on the first, so the question text and the concept
#: display are visibly drawn from different fields.
_REGISTRATION = QuestionnaireSourceIn(
    uid="Trk1aaaaaaa",
    name="Child Programme",
    code="PR_CHILD",
    kind="tracker",
    tracked_entity_type_uid="Tet1aaaaaaa",
    displays_incident_date=True,
    flat_items=[
        QuestionnaireItemIn(
            uid="Tea1aaaaaaa",
            name="National identifier",
            code="TEA_NATIONAL_ID",
            form_name="National id",
            value_type="TEXT",
            compulsory=True,
            unique=True,
        ),
        QuestionnaireItemIn(uid="Tea2aaaaaaa", name="Marital status", value_type="TEXT", option_set_uid="Os3aaaaaaaa"),
    ],
)

#: One stage of the same program, which shares its assignment container and its directory.
_BIRTH_STAGE = QuestionnaireSourceIn(
    uid="Stg1aaaaaaa",
    name="Birth",
    kind="tracker-event",
    program=ProgramContextIn(uid="Trk1aaaaaaa", name="Child Programme", code="PR_CHILD"),
    flat_items=[QuestionnaireItemIn(uid="De1aaaaaaaa", name="Apgar Score", value_type="INTEGER")],
)


def _plan() -> Any:
    """The option-set identity plan the emitters name an `answerValueSet` from."""
    return option_set_identities([_MARITAL_STATUS], GenerateConfig())


def _fsh(sources: list[QuestionnaireSourceIn] | None = None) -> dict[str, str]:
    """Build the FSH artifacts of the registration fixture and index them by relative path."""
    build = build_questionnaire_artifacts(
        sources or [_REGISTRATION],
        GenerateConfig(),
        _CANONICAL,
        ig_status="draft",
        option_set_plan=_plan(),
        attribute_codes=AttributeCodeIndex(),
    )
    return {artifact.relative_path: artifact.content for artifact in build.artifacts}


def _document(source: QuestionnaireSourceIn = _REGISTRATION) -> dict[str, Any]:
    """The built Questionnaire document, serialised the way the emitter writes it and parsed back."""
    build = build_questionnaire_documents(
        [source],
        GenerateConfig(),
        _CANONICAL,
        ig_status="draft",
        option_set_plan=_plan(),
        attribute_codes=AttributeCodeIndex(),
    )
    return _dumped(build.questionnaires[0])


def _dumped(resource: FhirBase) -> dict[str, Any]:
    """One built resource as the JSON object the writer serialises it to."""
    body: dict[str, Any] = json.loads(resource.model_dump_json(exclude_none=True, by_alias=True))
    return body


def _golden(stem: str) -> Any:
    """One SUSHI-compiled golden, parsed."""
    return json.loads((_GOLDEN_DIRECTORY / f"{stem}.json").read_text(encoding="utf-8"))


def test_the_registration_form_is_filed_beside_its_programs_stages() -> None:
    """A tracker program's whole capture surface is one directory: `registration.fsh` plus a file per stage."""
    artifacts = _fsh([_REGISTRATION, _BIRTH_STAGE])
    assert f"tracker-programs/Trk1aaaaaaa/{REGISTRATION_FILE_STEM}.fsh" in artifacts
    assert "tracker-programs/Trk1aaaaaaa/Stg1aaaaaaa.fsh" in artifacts


def test_the_registration_form_carries_the_programs_own_identity() -> None:
    """The form is the program, so it rides the program's identifier systems and its stem."""
    content = _fsh()[f"tracker-programs/Trk1aaaaaaa/{REGISTRATION_FILE_STEM}.fsh"]
    assert "Instance: Questionnaire-Trk1aaaaaaa" in content
    assert '* id = "Trk1aaaaaaa"' in content
    assert '* name = "D2PR_Trk1aaaaaaa"' in content
    assert '* url = "http://example.org/fhir/Questionnaire/Trk1aaaaaaa"' in content
    assert '* identifier[+].system = $DHIS2-PROGRAM\n* identifier[=].value = "Trk1aaaaaaa"' in content
    assert '* identifier[+].system = $DHIS2-PROGRAM-CODE\n* identifier[=].value = "PR_CHILD"' in content


def test_the_registration_form_declares_the_tracker_form_kind_and_a_patient_subject() -> None:
    """The form type is stated twice, and the subject of a registration is the person it enrols."""
    content = _fsh()[f"tracker-programs/Trk1aaaaaaa/{REGISTRATION_FILE_STEM}.fsh"]
    assert "* extension[D2FormType].valueCode = #tracker" in content
    assert "* code = D2FormType_CS#tracker" in content
    assert "* subjectType = #Patient" in content


def test_the_registration_form_names_the_tracked_entity_type_it_enrols() -> None:
    """A client has to know what kind of person the response creates, so the type rides as an identifier."""
    content = _fsh()[f"tracker-programs/Trk1aaaaaaa/{REGISTRATION_FILE_STEM}.fsh"]
    assert '* identifier[+].system = $DHIS2-TET\n* identifier[=].value = "Tet1aaaaaaa"' in content
    assert {"system": "http://dhis2.org/fhir/id/tracked-entity-type", "value": "Tet1aaaaaaa"} in _document()[
        "identifier"
    ]


def test_a_registration_form_the_instance_typed_nothing_for_names_no_tracked_entity_type() -> None:
    """An instance that sent no trackedEntityType leaves the identifier off rather than inventing one."""
    untyped = _REGISTRATION.model_copy(update={"tracked_entity_type_uid": None})
    assert grouping_identifiers(untyped) == []
    assert "$DHIS2-TET" not in _fsh([untyped])[f"tracker-programs/Trk1aaaaaaa/{REGISTRATION_FILE_STEM}.fsh"]


def test_attributes_become_questions_the_way_data_elements_do() -> None:
    """Sort order, mandatory, form name, value type, and the option-set binding all read the same."""
    content = _fsh()[f"tracker-programs/Trk1aaaaaaa/{REGISTRATION_FILE_STEM}.fsh"]
    assert content.index('"Tea1aaaaaaa"') < content.index('"Tea2aaaaaaa"')
    assert '* item[=].text = "National id"' in content
    assert "* item[=].required = true" in content
    assert "* item[=].answerValueSet = Canonical(D2OS_Os3aaaaaaaa_VS)" in content
    items = _document()["item"]
    assert [item["linkId"] for item in items] == ["Tea1aaaaaaa", "Tea2aaaaaaa"]
    assert items[0]["required"] is True
    assert items[1]["type"] == "choice"
    assert items[1]["answerValueSet"] == "http://example.org/fhir/ValueSet/d2-os-Os3aaaaaaaa-vs"
    assert "required" not in items[1]


def test_a_registration_question_is_coded_from_the_attribute_vocabulary() -> None:
    """A registration form asks tracked entity attributes, so its item codes name `D2TEA_CS`, never `D2DE_CS`."""
    naming = QuestionnaireNaming.from_naming(GenerateConfig().naming)
    assert question_code_system("tracker", naming) == "D2TEA_CS"
    assert question_code_system("tracker-event", naming) == "D2DE_CS"
    content = _fsh()[f"tracker-programs/Trk1aaaaaaa/{REGISTRATION_FILE_STEM}.fsh"]
    assert '* item[=].code = D2TEA_CS#Tea1aaaaaaa "National identifier"' in content
    assert "D2DE_CS" not in content
    codings = [item["code"][0]["system"] for item in _document()["item"]]
    assert codings == ["http://example.org/fhir/CodeSystem/d2-tea-cs"] * 2


def test_the_attribute_vocabulary_is_its_own_data_dictionary_pair() -> None:
    """The attributes land in `D2TEA_CS`, and a run whose forms ask none of them writes no such file."""
    artifacts = _fsh([_REGISTRATION, _BIRTH_STAGE])
    assert "data-dictionary/tracked-entity-attributes.fsh" in artifacts
    assert "data-dictionary/data-elements.fsh" in artifacts
    assert "Tea1aaaaaaa" not in artifacts["data-dictionary/data-elements.fsh"]
    assert "De1aaaaaaaa" not in artifacts["data-dictionary/tracked-entity-attributes.fsh"]
    assert "data-dictionary/tracked-entity-attributes.fsh" not in _fsh([_BIRTH_STAGE])


def test_the_attribute_vocabulary_states_the_code_the_value_type_and_the_uniqueness() -> None:
    """A consumer reading the vocabulary can tell which questions identify the person from which describe them."""
    content = _fsh()["data-dictionary/tracked-entity-attributes.fsh"]
    assert '* ^property[=].description = "DHIS2 tracked entity attribute value type."' in content
    assert '* #Tea1aaaaaaa ^property[=].valueString = "TEA_NATIONAL_ID"' in content
    assert "* #Tea1aaaaaaa ^property[=].valueBoolean = true" in content
    assert "* #Tea2aaaaaaa ^property[=].valueBoolean = false" in content
    assert '* #Tea2aaaaaaa ^property[=].valueString = "Tea2aaaaaaa"' in content


def test_the_data_element_vocabulary_keeps_its_own_property_prose() -> None:
    """Each pair describes the object it is about, so the value-type property is not shared wording."""
    content = _fsh([_BIRTH_STAGE])["data-dictionary/data-elements.fsh"]
    assert '* ^property[=].description = "DHIS2 data element value type."' in content
    assert "unique" not in content


@pytest.mark.parametrize(
    ("source", "stem"),
    [
        (_REGISTRATION, "Questionnaire-Trk1aaaaaaa"),
    ],
)
def test_the_built_registration_equals_what_sushi_compiled(source: QuestionnaireSourceIn, stem: str) -> None:
    """The JSON emitter writes the document SUSHI compiles from the FSH emitter's own output."""
    assert _document(source) == _golden(stem)


def test_the_built_attribute_vocabulary_equals_what_sushi_compiled() -> None:
    """The support pair keeps the same parity bar the questionnaires do, against its own goldens."""
    build = build_data_dictionary_documents([_REGISTRATION], GenerateConfig(), _CANONICAL, ig_status="draft")
    assert _dumped(build.code_systems[0]) == _golden("CodeSystem-d2-tea-cs")
    assert _dumped(build.value_sets[0]) == _golden("ValueSet-d2-tea-vs")


def test_the_registration_form_shares_its_programs_assignment_container() -> None:
    """DHIS2 hangs the assignment on the program, so its registration and its stages name one List."""
    plan = plan_questionnaire_stems([_REGISTRATION, _BIRTH_STAGE], "id")
    assert assignment_container_uid(_REGISTRATION) == assignment_container_uid(_BIRTH_STAGE) == "Trk1aaaaaaa"
    registration_container = assignment_container(_REGISTRATION, plan)
    stage_container = assignment_container(_BIRTH_STAGE, plan)
    assert registration_container.kind == stage_container.kind == "program"
    assert registration_container.stem == stage_container.stem


def test_a_registration_form_publishes_no_attribute_option_combo_vocabulary() -> None:
    """Tracker capture has no attribute option combo, so the form declares none whatever the plan holds."""
    content = _fsh()[f"tracker-programs/Trk1aaaaaaa/{REGISTRATION_FILE_STEM}.fsh"]
    assert "D2AttributeOptionCombos" not in content
    assert all(extension["url"].endswith("d2-form-type") for extension in _document()["extension"])


def test_the_registration_kind_is_published_but_not_yet_captured() -> None:
    """The form kind is generated and served; nothing translates a response against it into DHIS2 yet."""
    assert "tracker" in FORM_KIND_PROFILES
    assert "tracker" not in CAPTURED_FORM_KINDS
    assert set(CAPTURED_FORM_KINDS) < set(FORM_KIND_PROFILES)


def test_the_option_set_closure_reaches_the_sets_only_an_attribute_binds() -> None:
    """A registration form's questions are questions, so the sets they bind join the selection like any other."""
    assert sorted(bound_option_set_uids([_REGISTRATION, _BIRTH_STAGE])) == ["Os3aaaaaaaa"]


def test_a_registration_form_registers_its_program_on_the_stem_plan() -> None:
    """A tracker program with no stage at all still has a directory to file its registration under."""
    plan = plan_questionnaire_stems([_REGISTRATION], "id")
    assert plan.programs.stem_for("Trk1aaaaaaa") == "Trk1aaaaaaa"
    assert plan.targets.stem_for("Trk1aaaaaaa") == "Trk1aaaaaaa"
