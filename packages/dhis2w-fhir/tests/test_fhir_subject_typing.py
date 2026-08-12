"""What a tracker form is answered about: the tracked entity type map, and every artifact that reads it.

A DHIS2 tracked entity type is not always a person. A project tracks households, water points,
herds, and equipment through the very same registration-and-stages shape it tracks patients
through, so `[generate.tracked_entity_types]` maps a type's UID onto the FHIR resource type it
really is and one resolution feeds every consumer: the `subjectType` of the registration form and
of every stage form of that program, the `subject.type` of the examples, and the reference targets
the response profiles admit.

The whole of the default is here too, and it is what most of these tests are about: a project that
maps nothing emits exactly what it emitted before the table existed - `Patient` on both tracker
kinds, `Reference(Patient)` on both tracker profiles - so a person-tracking project configures
nothing and nothing moves.
"""

from __future__ import annotations

import datetime
import json
from typing import Any

import pytest
from dhis2w_fhir import (
    AttributeCodeIndex,
    GenerateConfig,
    build_example_artifacts,
    build_foundation_artifacts,
    build_questionnaire_artifacts,
    build_questionnaire_documents,
    build_synthetic_responses,
    option_set_identities,
)
from dhis2w_fhir.foundation.schemas import TrackerSubjectTypes
from dhis2w_fhir.r4 import DEFAULT_SUBJECT_RESOURCE_TYPE, SUBJECT_RESOURCE_TYPES
from dhis2w_fhir.resources.examples import EXAMPLES_DIRECTORY
from dhis2w_fhir.resources.examples.documents import build_example_documents
from dhis2w_fhir.resources.questionnaires import REGISTRATION_FILE_STEM
from dhis2w_fhir.resources.questionnaires.schemas import (
    ProgramContextIn,
    QuestionnaireItemIn,
    QuestionnaireSourceIn,
    form_subject_type,
    form_tracked_entity_type_uid,
)
from pydantic import ValidationError

_CANONICAL = "http://example.org/fhir"
_TODAY = datetime.date(2026, 8, 2)
_ROOT_ORG_UNIT = "ImspTQPwCqd"

#: The tracked entity type a project tracks that is plainly not a person - a herd under vaccination.
_HERD_TYPE = "TetHerd0001"

#: A second non-person type, so the union the response profiles publish is visibly more than one.
_WATER_POINT_TYPE = "TetWater001"

#: The type the fixtures leave unmapped, which is what proves an unmapped type stays a `Patient`.
_PERSON_TYPE = "TetPerson01"

_VACCINATION = QuestionnaireSourceIn(
    uid="PrVaccine01",
    name="Herd vaccination",
    kind="tracker",
    tracked_entity_type_uid=_HERD_TYPE,
    flat_items=[QuestionnaireItemIn(uid="TeaHerdTag1", name="Herd tag", value_type="TEXT")],
)

_VACCINATION_ROUND = QuestionnaireSourceIn(
    uid="PsVaccine01",
    name="Vaccination round",
    kind="tracker-event",
    program=ProgramContextIn(uid="PrVaccine01", name="Herd vaccination", tracked_entity_type_uid=_HERD_TYPE),
    flat_items=[QuestionnaireItemIn(uid="DeDoseCount", name="Doses given", value_type="INTEGER")],
)

#: A second program over the same herds: the type owns the nature, so the two programs cannot disagree.
_HERD_CENSUS = QuestionnaireSourceIn(
    uid="PrCensus001",
    name="Herd census",
    kind="tracker",
    tracked_entity_type_uid=_HERD_TYPE,
    flat_items=[QuestionnaireItemIn(uid="TeaHerdSize", name="Herd size", value_type="INTEGER")],
)

#: A person-tracking program in the same project, whose type the table never mentions.
_ANTENATAL = QuestionnaireSourceIn(
    uid="PrAntenat01",
    name="Antenatal care",
    kind="tracker",
    tracked_entity_type_uid=_PERSON_TYPE,
    flat_items=[QuestionnaireItemIn(uid="TeaMotherId", name="Mother id", value_type="TEXT")],
)

_ALL_SOURCES = [_VACCINATION, _VACCINATION_ROUND, _HERD_CENSUS, _ANTENATAL]

#: The project that says what its herds are, and nothing about its people.
_MAPPED = GenerateConfig(tracked_entity_types={_HERD_TYPE: "Group"})

_REGISTRATION_FILE = f"tracker-programs/PrVaccine01/{REGISTRATION_FILE_STEM}.fsh"
_STAGE_FILE = "tracker-programs/PrVaccine01/PsVaccine01.fsh"


def _plan(config: GenerateConfig) -> Any:
    """The option-set identity plan the emitters name an `answerValueSet` from - empty here."""
    return option_set_identities([], config)


def _fsh(sources: list[QuestionnaireSourceIn], config: GenerateConfig) -> dict[str, str]:
    """Build the FSH questionnaires of `sources` and index them by relative path."""
    build = build_questionnaire_artifacts(
        sources,
        config,
        _CANONICAL,
        ig_status="draft",
        option_set_plan=_plan(config),
        attribute_codes=AttributeCodeIndex(),
    )
    return {artifact.relative_path: artifact.content for artifact in build.artifacts}


def _documents(sources: list[QuestionnaireSourceIn], config: GenerateConfig) -> dict[str, Any]:
    """Build the Questionnaire documents of `sources`, serialised the way the writer writes them."""
    build = build_questionnaire_documents(
        sources,
        config,
        _CANONICAL,
        ig_status="draft",
        option_set_plan=_plan(config),
        attribute_codes=AttributeCodeIndex(),
    )
    return {
        questionnaire.id or "": json.loads(questionnaire.model_dump_json(exclude_none=True, by_alias=True))
        for questionnaire in build.questionnaires
    }


def _examples(sources: list[QuestionnaireSourceIn], config: GenerateConfig) -> dict[str, str]:
    """Build one synthetic example per source, as the FSH the examples target writes."""
    synthetic = build_synthetic_responses(sources, [], 1, _ROOT_ORG_UNIT, _TODAY)
    build = build_example_artifacts(
        sources,
        synthetic.responses,
        [],
        config,
        _CANONICAL,
        option_set_plan=_plan(config),
    )
    return {artifact.relative_path: artifact.content for artifact in build.artifacts}


def _example_documents(sources: list[QuestionnaireSourceIn], config: GenerateConfig) -> dict[str, Any]:
    """The same examples as built documents, keyed by the id the FSH path declares."""
    synthetic = build_synthetic_responses(sources, [], 1, _ROOT_ORG_UNIT, _TODAY)
    build = build_example_documents(
        sources,
        synthetic.responses,
        [],
        config,
        _CANONICAL,
        option_set_plan=_plan(config),
    )
    return {
        response.id or "": json.loads(response.model_dump_json(exclude_none=True, by_alias=True))
        for response in build.responses
    }


def _responses_fsh(config: GenerateConfig) -> str:
    """The `foundation/d2-responses.fsh` artifact one project publishes."""
    artifacts = {
        artifact.relative_path: artifact.content
        for artifact in build_foundation_artifacts(config, _CANONICAL, ig_status="draft")
    }
    return artifacts["foundation/d2-responses.fsh"]


def test_a_project_that_maps_nothing_emits_what_it_always_did() -> None:
    """The default is the whole of a person-tracking project's configuration: `Patient`, everywhere it says so."""
    artifacts = _fsh(_ALL_SOURCES, GenerateConfig())

    assert "* subjectType = #Patient" in artifacts[_REGISTRATION_FILE]
    assert "* subjectType = #Patient" in artifacts[_STAGE_FILE]
    assert [document["subjectType"] for document in _documents(_ALL_SOURCES, GenerateConfig()).values()] == [
        ["Patient"]
    ] * 4


def test_mapping_a_type_moves_nothing_of_the_programs_that_do_not_track_it() -> None:
    """Naming one type is not a project-wide edit: every other form is byte-identical to the unmapped run."""
    unmapped = _fsh(_ALL_SOURCES, GenerateConfig())
    mapped = _fsh(_ALL_SOURCES, _MAPPED)

    assert (
        mapped[f"tracker-programs/PrAntenat01/{REGISTRATION_FILE_STEM}.fsh"]
        == (unmapped[f"tracker-programs/PrAntenat01/{REGISTRATION_FILE_STEM}.fsh"])
    )
    assert _documents([_ANTENATAL], _MAPPED) == _documents([_ANTENATAL], GenerateConfig())


def test_a_mapped_type_types_the_registration_form_on_both_paths() -> None:
    """One map entry, and the form the herd is registered through says it is answered about a Group."""
    assert "* subjectType = #Group" in _fsh(_ALL_SOURCES, _MAPPED)[_REGISTRATION_FILE]
    assert _documents(_ALL_SOURCES, _MAPPED)["PrVaccine01"]["subjectType"] == ["Group"]


def test_every_stage_of_the_program_states_the_subject_its_registration_does() -> None:
    """A stage captures a visit by the very entity the registration enrolled, so the two cannot disagree."""
    artifacts = _fsh(_ALL_SOURCES, _MAPPED)
    documents = _documents(_ALL_SOURCES, _MAPPED)

    assert "* subjectType = #Group" in artifacts[_STAGE_FILE]
    assert documents["PsVaccine01"]["subjectType"] == documents["PrVaccine01"]["subjectType"] == ["Group"]


def test_two_programs_tracking_one_type_agree_by_construction() -> None:
    """The map is keyed by tracked entity type because the type is what owns the nature of the thing."""
    documents = _documents(_ALL_SOURCES, _MAPPED)

    assert documents["PrCensus001"]["subjectType"] == documents["PrVaccine01"]["subjectType"] == ["Group"]


def test_a_type_the_table_never_mentions_is_a_patient() -> None:
    """A project mapping its herds says nothing about its mothers, and its antenatal forms stay as they were."""
    assert _documents(_ALL_SOURCES, _MAPPED)["PrAntenat01"]["subjectType"] == ["Patient"]
    assert form_subject_type(_ANTENATAL, _MAPPED.tracked_entity_types) == DEFAULT_SUBJECT_RESOURCE_TYPE


def test_the_form_reads_its_type_off_the_program_whichever_kind_it_is() -> None:
    """A registration form carries the type; a stage form carries the program that carries it."""
    assert form_tracked_entity_type_uid(_VACCINATION) == _HERD_TYPE
    assert form_tracked_entity_type_uid(_VACCINATION_ROUND) == _HERD_TYPE
    assert form_tracked_entity_type_uid(_VACCINATION_ROUND.model_copy(update={"program": None})) is None


def test_an_organisation_unit_form_is_answered_about_its_location_whatever_the_map_says() -> None:
    """Only the tracker kinds have a tracked entity type, so an aggregate or event form is untouched."""
    data_set = QuestionnaireSourceIn(uid="DsMonthly01", name="Monthly", kind="aggregate")

    assert form_subject_type(data_set, {_HERD_TYPE: "Group"}) == "Location"


def test_an_example_types_its_subject_as_the_form_it_answers_does() -> None:
    """A response naming a Group by identifier types it as one, on both emission paths."""
    examples = _examples([_VACCINATION], _MAPPED)
    documents = _example_documents([_VACCINATION], _MAPPED)
    content = examples[f"{EXAMPLES_DIRECTORY}/PrVaccine01-1.fsh"]

    assert '* subject.type = "Group"' in content
    assert next(iter(documents.values()))["subject"]["type"] == "Group"
    assert (
        '* subject.type = "Patient"'
        in _examples([_VACCINATION], GenerateConfig())[f"{EXAMPLES_DIRECTORY}/PrVaccine01-1.fsh"]
    )


def test_the_response_profiles_of_an_unmapped_project_admit_a_patient_alone() -> None:
    """The published contract stays as tight as the project is: one type configured, one type admitted."""
    content = _responses_fsh(GenerateConfig())

    assert "* subject only Reference(Patient)" in content
    assert "this guide publishes no Patient resource, so the identifier is the person" in content


def test_the_response_profiles_admit_every_type_the_project_configured() -> None:
    """One profile is published for the whole project, so it admits the union rather than pinning one type."""
    content = _responses_fsh(GenerateConfig(tracked_entity_types={_HERD_TYPE: "Group", _WATER_POINT_TYPE: "Location"}))

    assert content.count("* subject only Reference(Patient or Group or Location)") == 3
    assert "so the identifier is the tracked entity" in content


def test_the_admitted_set_is_ordered_by_the_registry_not_by_the_config_file() -> None:
    """Two projects that configure the same types publish the same constraint, however they wrote it."""
    forwards = TrackerSubjectTypes.of_mapping({"a": "Device", "b": "Group"})
    backwards = TrackerSubjectTypes.of_mapping({"b": "Group", "a": "Device"})

    assert forwards == backwards
    assert forwards.reference_targets == "Patient or Group or Device"


def test_the_config_refuses_a_resource_type_that_is_not_one() -> None:
    """A typo here would mis-type every form of every program tracking that type, so it is refused at load."""
    with pytest.raises(ValidationError) as error:
        GenerateConfig(tracked_entity_types={_HERD_TYPE: "Herd"})

    message = str(error.value)
    assert "TetHerd0001" in message
    assert "'Herd'" in message
    assert "Patient, Person, Practitioner" in message


def test_the_default_is_one_of_the_types_the_config_admits() -> None:
    """The fall-back has to be nameable: a project can state what it gets by saying nothing."""
    assert DEFAULT_SUBJECT_RESOURCE_TYPE in SUBJECT_RESOURCE_TYPES
    assert SUBJECT_RESOURCE_TYPES[0] == DEFAULT_SUBJECT_RESOURCE_TYPE
