"""The person-only registration form: the kind that creates a person and enrols them in nothing.

A tracked entity type is a form in its own right. DHIS2 accepts a bare `trackedEntities` import
under plain CREATE and the person it creates is findable without a program, so the guide publishes
one `Questionnaire` per type: the attributes the type itself collects, every one of them at the
entity level because there is no enrollment for an answer to land on.

These tests hold the shape from both ends - the FSH the compiler reads and the JSON the facade
serves - plus the searchability provenance the attribute dictionary now publishes, which is what
makes two contexts asking one attribute readable rather than reduced to a single boolean.

The SUSHI goldens under `tests/data/r4/` were harvested the registration family's way: the emitted
FSH of `_TRACKED_ENTITY` beside `_REGISTRATION`, compiled by SUSHI, written back byte for byte.
They are never edited by hand - when the parity test fails, the builder is what changed.
"""

from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Any

from dhis2w_fhir import (
    AttributeCodeIndex,
    GenerateConfig,
    OptionSetIn,
    build_data_dictionary_documents,
    build_questionnaire_artifacts,
    build_questionnaire_documents,
    option_set_identities,
)
from dhis2w_fhir.config import FhirProjectConfig, IgConfig
from dhis2w_fhir.foundation import FoundationNaming, build_response_profile_declarations
from dhis2w_fhir.r4 import FhirBase
from dhis2w_fhir.resources.examples import build_synthetic_responses
from dhis2w_fhir.resources.questionnaires import (
    TRACKED_ENTITY_TYPE_DIRECTORY,
    collect_referenced_objects,
    question_code_system,
    question_entity_level,
    search_context_declarations,
)
from dhis2w_fhir.resources.questionnaires.assignments import AssignmentPlan
from dhis2w_fhir.resources.questionnaires.schemas import (
    CAPTURED_FORM_KINDS,
    FORM_KIND_PROFILES,
    ProgramContextIn,
    QuestionnaireItemIn,
    QuestionnaireNaming,
    QuestionnaireSourceIn,
    ReferencedObjects,
)

_GOLDEN_DIRECTORY = Path(__file__).parent / "data" / "r4"

#: The IG the goldens were compiled for - `[ig] canonical` and `[ig] status` of its `fhir.toml`.
_CANONICAL = "http://example.org/fhir"

#: The option set a tracked entity attribute binds, which both contexts of the fixture share.
_MARITAL_STATUS = OptionSetIn(uid="Os3aaaaaaaa", name="Marital status")

#: The tracker program that registers the same person, which is what makes the searchability
#: provenance visible: it declares the national identifier searchable, and the type does not.
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
            searchable=True,
            entity_level=True,
        ),
        QuestionnaireItemIn(
            uid="Tea2aaaaaaa",
            name="Marital status",
            value_type="TEXT",
            option_set_uid="Os3aaaaaaaa",
            entity_level=True,
        ),
        QuestionnaireItemIn(
            uid="Tea3aaaaaaa",
            name="Household size",
            code="TEA_HOUSEHOLD_SIZE",
            value_type="INTEGER_POSITIVE",
            entity_level=False,
        ),
    ],
)

#: The person-only form of the type that program registers: the type's own attributes, and the
#: opposite searchability answer on the one attribute the two contexts share.
_TRACKED_ENTITY = QuestionnaireSourceIn(
    uid="Tet1aaaaaaa",
    name="Person",
    code="TET_PERSON",
    kind="tracked-entity",
    tracked_entity_type_uid="Tet1aaaaaaa",
    flat_items=[
        QuestionnaireItemIn(
            uid="Tea1aaaaaaa",
            name="National identifier",
            code="TEA_NATIONAL_ID",
            form_name="National id",
            value_type="TEXT",
            compulsory=True,
            unique=True,
            searchable=False,
            entity_level=True,
        ),
        QuestionnaireItemIn(
            uid="Tea2aaaaaaa",
            name="Marital status",
            value_type="TEXT",
            option_set_uid="Os3aaaaaaaa",
            searchable=True,
            entity_level=True,
        ),
    ],
)


def _plan() -> Any:
    """The option-set identity plan the emitters name an `answerValueSet` from."""
    return option_set_identities([_MARITAL_STATUS], GenerateConfig())


def _fsh(sources: list[QuestionnaireSourceIn] | None = None) -> dict[str, str]:
    """Build the FSH artifacts of the person-only fixture and index them by relative path."""
    build = build_questionnaire_artifacts(
        sources or [_TRACKED_ENTITY],
        GenerateConfig(),
        _CANONICAL,
        ig_status="draft",
        option_set_plan=_plan(),
        attribute_codes=AttributeCodeIndex(),
    )
    return {artifact.relative_path: artifact.content for artifact in build.artifacts}


def _document(source: QuestionnaireSourceIn = _TRACKED_ENTITY) -> dict[str, Any]:
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


_FILE = f"{TRACKED_ENTITY_TYPE_DIRECTORY}/Tet1aaaaaaa.fsh"


def test_a_tracked_entity_type_publishes_a_form_of_its_own() -> None:
    """The form is filed under the tracked entity types rather than under any program's directory."""
    artifacts = _fsh([_TRACKED_ENTITY, _REGISTRATION])
    assert _FILE in artifacts
    assert "tracker-programs/Trk1aaaaaaa/registration.fsh" in artifacts


def test_the_person_only_form_carries_the_tracked_entity_types_own_identity() -> None:
    """The form is the type, so it rides the type's identifier systems and its naming token."""
    content = _fsh()[_FILE]
    assert "Instance: Questionnaire-Tet1aaaaaaa" in content
    assert '* id = "Tet1aaaaaaa"' in content
    assert '* name = "D2TET_Tet1aaaaaaa"' in content
    assert '* url = "http://example.org/fhir/Questionnaire/Tet1aaaaaaa"' in content
    assert '* identifier[+].system = $DHIS2-TET\n* identifier[=].value = "Tet1aaaaaaa"' in content
    assert '* identifier[+].system = $DHIS2-TET-CODE\n* identifier[=].value = "TET_PERSON"' in content


def test_the_person_only_form_declares_its_own_form_kind_and_a_patient_subject() -> None:
    """The form kind is stated twice, and the subject is the person the response creates."""
    content = _fsh()[_FILE]
    assert "* extension[D2FormType].valueCode = #tracked-entity" in content
    assert "* code = D2FormType_CS#tracked-entity" in content
    assert "* subjectType = #Patient" in content


def test_the_person_only_form_describes_itself_as_enrolling_nobody() -> None:
    """The prose says what the kind is for: a person registered without joining a program."""
    assert "without being enrolled in any program" in _fsh()[_FILE]


def test_the_subject_type_follows_the_configured_tracked_entity_type() -> None:
    """A project tracking herds publishes a person-only form that says so."""
    build = build_questionnaire_documents(
        [_TRACKED_ENTITY],
        GenerateConfig(tracked_entity_types={"Tet1aaaaaaa": "Group"}),
        _CANONICAL,
        ig_status="draft",
        option_set_plan=_plan(),
        attribute_codes=AttributeCodeIndex(),
    )
    assert build.questionnaires[0].subjectType == ["Group"]


def test_every_person_only_question_is_stated_at_the_entity_level() -> None:
    """The type's own attributes are entity-level by definition, so every item says so."""
    content = _fsh()[_FILE]
    assert content.count("* item[=].extension[=].valueBoolean = true") == 2
    assert "* item[=].extension[=].valueBoolean = false" not in content
    levels = {
        item["linkId"]: extension["valueBoolean"]
        for item in _document()["item"]
        for extension in item.get("extension", [])
        if extension["url"] == f"{_CANONICAL}/StructureDefinition/d2-entity-level"
    }
    assert levels == {"Tea1aaaaaaa": True, "Tea2aaaaaaa": True}
    assert all(question_entity_level(item, "tracked-entity") is True for item in _TRACKED_ENTITY.flat_items)


def test_a_person_only_question_is_coded_from_the_attribute_vocabulary() -> None:
    """It asks tracked entity attributes, so its item codes name `D2TEA_CS` and never `D2DE_CS`."""
    naming = QuestionnaireNaming.from_naming(GenerateConfig().naming)
    assert question_code_system("tracked-entity", naming) == "D2TEA_CS"
    content = _fsh()[_FILE]
    assert '* item[=].code = D2TEA_CS#Tea1aaaaaaa "National identifier"' in content
    assert "D2DE_CS" not in content


def test_a_person_only_form_publishes_no_organisation_unit_assignment() -> None:
    """DHIS2 hangs no assignment on a tracked entity type, so every published unit may register one."""
    assert FORM_KIND_PROFILES["tracked-entity"].assigned is False
    assert AssignmentPlan(list_ids={"Tet1aaaaaaa": "d2-tet-Tet1aaaaaaa-org-units"}).reference_for(_TRACKED_ENTITY) is (
        None
    )
    assert "D2OrganisationUnitAssignment" not in _fsh()[_FILE]


def test_the_attribute_dictionary_states_searchability_once_per_context() -> None:
    """Two contexts disagreeing about one attribute publish two answers rather than one averaged boolean."""
    content = _fsh([_TRACKED_ENTITY, _REGISTRATION])["data-dictionary/tracked-entity-attributes.fsh"]
    assert "* ^property[+].code = #searchable-Trk1aaaaaaa" in content
    assert "* ^property[+].code = #searchable-Tet1aaaaaaa" in content
    assert (
        '* ^property[=].description = "Whether DHIS2 declares the tracked entity attribute searchable in '
        'tracked entity type Person (Tet1aaaaaaa)."' in content
    )


def test_the_searchable_roll_up_is_true_where_any_context_says_so() -> None:
    """`searchable` answers the question a consumer actually asks, and the per-context properties say where."""
    referenced = ReferencedObjects()
    collect_referenced_objects(_TRACKED_ENTITY, referenced)
    collect_referenced_objects(_REGISTRATION, referenced)
    assert referenced.searchable_anywhere("Tea1aaaaaaa") is True
    assert referenced.searchable_anywhere("Tea3aaaaaaa") is False
    assert [context.context_uid for context in referenced.contexts_for("Tea1aaaaaaa")] == [
        "Tet1aaaaaaa",
        "Trk1aaaaaaa",
    ]
    assert [context.searchable for context in referenced.contexts_for("Tea1aaaaaaa")] == [False, True]
    assert [context.context_uid for context in search_context_declarations(referenced)] == [
        "Tet1aaaaaaa",
        "Trk1aaaaaaa",
    ]


def test_a_context_declares_its_property_once_however_many_attributes_it_asks() -> None:
    """The property is what the CodeSystem declares; the concepts are what carry a value for it."""
    content = _fsh([_TRACKED_ENTITY])["data-dictionary/tracked-entity-attributes.fsh"]
    assert content.count("* ^property[+].code = #searchable-Tet1aaaaaaa") == 1
    assert content.count("^property[+].code = #searchable-Tet1aaaaaaa") == 3


def test_only_an_attribute_asking_form_carries_searchability() -> None:
    """A data element has no such flag, so the data-element dictionary declares no searchable property."""
    stage = QuestionnaireSourceIn(
        uid="Stg1aaaaaaa",
        name="Birth",
        kind="tracker-event",
        program=ProgramContextIn(uid="Trk1aaaaaaa", name="Child Programme"),
        flat_items=[QuestionnaireItemIn(uid="De1aaaaaaaa", name="Apgar Score", value_type="INTEGER")],
    )
    assert "searchable" not in _fsh([stage])["data-dictionary/data-elements.fsh"]


def test_the_built_person_only_form_equals_what_sushi_compiled() -> None:
    """The JSON emitter writes the document SUSHI compiles from the FSH emitter's own output."""
    assert _document() == _golden("Questionnaire-Tet1aaaaaaa")


def test_the_two_context_attribute_dictionary_equals_what_sushi_compiled() -> None:
    """The searchability provenance keeps the same parity bar every other emitted element does."""
    build = build_data_dictionary_documents(
        [_TRACKED_ENTITY, _REGISTRATION], GenerateConfig(), _CANONICAL, ig_status="draft"
    )
    assert _dumped(build.code_systems[0]) == _golden("CodeSystem-d2-tea-two-contexts-cs")


def test_the_kind_is_captured_and_has_a_response_profile_of_its_own() -> None:
    """The capture contract states what a person-only submission carries: a person, and no enrollment."""
    assert "tracked-entity" in CAPTURED_FORM_KINDS
    declaration = next(
        item
        for item in build_response_profile_declarations(FhirProjectConfig(ig=_IG).generate)
        if item.form_type_code == "tracked-entity"
    )
    assert declaration.name == "D2TrackedEntityResponse"
    assert declaration.profile_id == "d2-tracked-entity-response"
    assert declaration.entity_context_required is True
    assert declaration.registration_context_required is False
    assert declaration.tracker_context_required is False
    assert declaration.authored_required is True
    assert FoundationNaming(prefix="D2").tracked_entity_response_profile == "D2TrackedEntityResponse"


def test_a_synthetic_person_only_response_mints_a_person_and_no_enrollment() -> None:
    """`$generate` and the example corpus both answer the form the profile describes, and nothing more."""
    build = build_synthetic_responses(
        [_TRACKED_ENTITY], [_MARITAL_STATUS], 1, "OrgUnit1aaa", datetime.date(2026, 1, 15)
    )
    response = build.responses[0]
    assert response.kind == "tracked-entity"
    assert response.tracked_entity_uid is not None
    assert response.enrollment_uid is None
    assert response.enrolled_at is None
    assert response.incident_at is None
    assert response.authored is not None


#: A minimal IG identity, so the response-profile declarations can be built without a project on disk.
_IG = IgConfig(
    id="fixture.ig",
    canonical=_CANONICAL,
    name="FixtureIg",
    title="Fixture IG",
    publisher="Fixture",
)
