"""Parity between the two example emitters: the built responses equal what SUSHI compiles.

`tests/data/questionnaire-sources/` holds the projections one generate run of the local DHIS2
stack fetched, and `tests/data/r4/` holds the resources SUSHI compiled from the FSH that same run
wrote. Rebuilding the documents from the sources and comparing them to the compiled output is what
pins the JSON emitter to the FSH one: an element the two paths disagree about fails here.

Regenerating the source fixtures, against a local stack holding the DHIS2 demo database plus the
seeded FHIR metadata (`make dhis2-up`, profile `local_basic`):

1. Read `sources` and the option-set identity projection the way `service.generate_questionnaires`
   does, plus the fuller `example-option-sets` projection `service._fetch_example_option_sets`
   reads - the examples target codes its answers off the options, which `option-sets.json` omits.
2. Dump each to `sources.json`, `option-sets.json`, and `example-option-sets.json` with
   `model_dump_json(exclude_none=True)`.
3. Run `d2w fhir generate examples` in the IG project the goldens came from, compile it with
   SUSHI, and copy the emitted `fsh-generated/resources/QuestionnaireResponse-*.json` into
   `tests/data/r4/`.

The synthetic values are seeded from the target UID, so the only thing that moves with the
calendar is what the reporting period and the occurrence window are anchored to - which is why
`_REFERENCE_DATE` pins the day the goldens were harvested on. The goldens are SUSHI's own output
and are never edited by hand: when this test fails, the builder is what changed.
"""

from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Any

import pytest
from dhis2w_fhir import (
    GenerateConfig,
    OptionSetIn,
    QuestionnaireSourceIn,
    build_example_documents,
    build_synthetic_responses,
    option_set_identities,
)
from dhis2w_fhir.r4 import FhirBase, QuestionnaireResponse
from dhis2w_fhir.resources.option_sets.schemas import OptionIn
from dhis2w_fhir.resources.questionnaires.schemas import (
    CategoryComboIn,
    CategoryOptionComboIn,
    ProgramContextIn,
    QuestionnaireItemIn,
    QuestionnaireSectionIn,
)

_SOURCE_DIRECTORY = Path(__file__).parent / "data" / "questionnaire-sources"
_GOLDEN_DIRECTORY = Path(__file__).parent / "data" / "r4"

#: The IG the goldens were compiled for - `[ig] canonical` of its `fhir.toml`.
_CANONICAL = "http://localhost:8080/fhir"

#: The day the goldens were harvested on, which the period-anchored synthetic values follow.
_REFERENCE_DATE = datetime.date(2026, 8, 8)

#: The instance's root organisation unit - the one every synthetic example is subject to.
_ROOT_ORG_UNIT = "ImspTQPwCqd"

#: Every example response the run compiled: two data sets, two event programs, three tracker stages.
_EXAMPLE_IDS = [
    "A03MvHHogjR-example-1",
    "BfMAe6Itzgt-example-1",
    "EVTsupVis01-example-1",
    "PsAncVisit1-example-1",
    "TuL8IOPzpHh-example-1",
    "ZzYYXq4fJie-example-1",
    "lxAQ7Zs9VYR-example-1",
]

_UNIT_CANONICAL = "http://example.org/fhir"
_UNIT_TODAY = datetime.date(2026, 8, 2)


def _fixture(name: str) -> Any:
    """Read one committed source fixture."""
    return json.loads((_SOURCE_DIRECTORY / f"{name}.json").read_text(encoding="utf-8"))


def _sources() -> list[QuestionnaireSourceIn]:
    """The forms the run fetched, as the emitter projection."""
    return [QuestionnaireSourceIn.model_validate(entry) for entry in _fixture("sources")]


def _emitted(resource: FhirBase) -> Any:
    """One built resource as the JSON document it is served as."""
    return json.loads(resource.model_dump_json(exclude_none=True, by_alias=True))


def _golden(stem: str) -> Any:
    """One resource SUSHI compiled from the FSH the same run wrote."""
    return json.loads((_GOLDEN_DIRECTORY / f"{stem}.json").read_text(encoding="utf-8"))


def _built_responses() -> dict[str, Any]:
    """Build the run's synthetic example responses and index the emitted JSON by resource id."""
    sources = _sources()
    config = GenerateConfig()
    option_sets = [OptionSetIn.model_validate(entry) for entry in _fixture("example-option-sets")]
    plan_sets = [OptionSetIn.model_validate(entry) for entry in _fixture("option-sets")]
    synthetic = build_synthetic_responses(sources, option_sets, 1, _ROOT_ORG_UNIT, _REFERENCE_DATE)
    build = build_example_documents(
        sources,
        synthetic.responses,
        option_sets,
        config,
        _CANONICAL,
        option_set_plan=option_set_identities(plan_sets, config),
    )
    assert build.notes == []
    return {str(response.id): _emitted(response) for response in build.responses}


@pytest.mark.parametrize("instance_id", _EXAMPLE_IDS)
def test_a_built_example_equals_the_one_sushi_compiled(instance_id: str) -> None:
    """Every element SUSHI resolved from the FSH is on the built document, and nothing else is."""
    assert _built_responses()[instance_id] == _golden(f"QuestionnaireResponse-{instance_id}")


def test_the_run_builds_exactly_the_examples_it_compiled() -> None:
    """No example is silently dropped from - or added to - the document build."""
    assert sorted(_built_responses()) == sorted(_EXAMPLE_IDS)


def test_building_twice_yields_the_identical_documents() -> None:
    """The build is a pure function of its inputs, so a load set reruns byte-identical."""
    assert _built_responses() == _built_responses()


_DEFAULT_COMBO = CategoryComboIn(uid="bjDvmb4bfuf", name="default", is_default=True)
_AGE_COMBO = CategoryComboIn(
    uid="CcAaBbCcDdE",
    name="EPI/nutrition age",
    option_combos=[
        CategoryOptionComboIn(uid="Coc1aaaaaaa", name="<1y", code="U1"),
        CategoryOptionComboIn(uid="Coc2aaaaaaa", name=">1y"),
    ],
)

_GENDER_SET = OptionSetIn(
    uid="Os1aaaaaaaa",
    name="Gender",
    options=[
        OptionIn(uid="Op1aaaaaaaa", code="F", name="Female", sort_order=1),
        OptionIn(uid="Op2aaaaaaaa", code="M", name="Male", sort_order=2),
    ],
)

_SYMPTOM_SET = OptionSetIn(
    uid="Os2aaaaaaaa",
    name="Symptoms",
    options=[
        OptionIn(uid="Op3aaaaaaaa", code="FEV", name="Fever", sort_order=1),
        OptionIn(uid="Op4aaaaaaaa", code="CGH", name="Cough", sort_order=2),
        OptionIn(uid="Op5aaaaaaaa", code="RSH", name="Rash", sort_order=3),
    ],
)

_DATA_SET = QuestionnaireSourceIn(
    uid="BfMAe6Itzgt",
    name="Child Health",
    kind="aggregate",
    period_type="Monthly",
    sections=[
        QuestionnaireSectionIn(
            uid="Sec1aaaaaaa",
            name="Immunization",
            items=[
                QuestionnaireItemIn(
                    uid="De2aaaaaaaa", name="Measles doses given", value_type="INTEGER", category_combo=_AGE_COMBO
                ),
                QuestionnaireItemIn(
                    uid="De3aaaaaaaa",
                    name="Gender",
                    value_type="TEXT",
                    option_set_uid="Os1aaaaaaaa",
                    category_combo=_DEFAULT_COMBO,
                ),
            ],
        )
    ],
)

_EVENT_PROGRAM = QuestionnaireSourceIn(
    uid="VBqh0ynB2wv",
    name="Malaria case registration",
    kind="event",
    flat_items=[
        QuestionnaireItemIn(uid="qrur9Dvnyt5", name="Age in years", value_type="INTEGER"),
        QuestionnaireItemIn(uid="De9aaaaaaaa", name="Seen at", value_type="DATETIME"),
    ],
)

#: An event program whose question carries a real category combo - the shape the questionnaire
#: emitter asks flat, because an event data value has no categoryOptionCombo slot on the wire.
_CATEGORISED_EVENT_PROGRAM = QuestionnaireSourceIn(
    uid="VBqh0ynB2wx",
    name="Supervision visit",
    kind="event",
    flat_items=[
        QuestionnaireItemIn(
            uid="De2aaaaaaaa", name="Measles doses given", value_type="INTEGER", category_combo=_AGE_COMBO
        )
    ],
)

_MULTI_TEXT_PROGRAM = QuestionnaireSourceIn(
    uid="VBqh0ynB2wy",
    name="Symptom screening",
    kind="event",
    flat_items=[
        QuestionnaireItemIn(uid="De4aaaaaaaa", name="Symptoms", value_type="MULTI_TEXT", option_set_uid="Os2aaaaaaaa")
    ],
)

_BIRTH_STAGE = QuestionnaireSourceIn(
    uid="A03MvHHogjR",
    name="Birth",
    kind="tracker-event",
    program=ProgramContextIn(uid="IpHINAT79UW", name="Child Programme"),
    flat_items=[QuestionnaireItemIn(uid="a3kGcGDCuk6", name="Apgar Score", value_type="INTEGER")],
)


def _documents(
    sources: list[QuestionnaireSourceIn],
    option_sets: list[OptionSetIn] | None = None,
    *,
    per_target: int = 1,
    today: datetime.date = _UNIT_TODAY,
) -> dict[str, QuestionnaireResponse]:
    """Build the synthetic documents for `sources` and index them by resource id."""
    resolved = [_GENDER_SET, _SYMPTOM_SET] if option_sets is None else option_sets
    config = GenerateConfig()
    synthetic = build_synthetic_responses(sources, resolved, per_target, _ROOT_ORG_UNIT, today)
    build = build_example_documents(
        sources,
        synthetic.responses,
        resolved,
        config,
        _UNIT_CANONICAL,
        option_set_plan=option_set_identities(resolved, config),
    )
    return {str(response.id): response for response in build.responses}


def _extension_urls(response: QuestionnaireResponse) -> list[str]:
    """The extension URLs one response carries, in emission order."""
    return [extension.url for extension in response.extension or []]


def test_an_aggregate_response_leads_with_its_reporting_period() -> None:
    """A data set's response declares D2Period before D2FormType, as its profile slices them."""
    response = _documents([_DATA_SET])["BfMAe6Itzgt-example-1"]
    assert _extension_urls(response) == [
        f"{_UNIT_CANONICAL}/StructureDefinition/d2-period",
        f"{_UNIT_CANONICAL}/StructureDefinition/d2-form-type",
    ]


def test_an_aggregate_response_carries_the_period_facts_in_order() -> None:
    """D2Period nests the ISO identifier, the period type, and the range it resolves to."""
    response = _documents([_DATA_SET])["BfMAe6Itzgt-example-1"]
    period = (response.extension or [])[0]
    assert [sub.url for sub in period.extension or []] == ["iso", "type", "period"]
    assert (period.extension or [])[0].valueString == "202607"
    assert (period.extension or [])[1].valueCode == "Monthly"
    range_value = (period.extension or [])[2].valuePeriod
    assert range_value is not None
    assert (range_value.start, range_value.end) == ("2026-07-01", "2026-07-31")


def test_an_aggregate_response_is_subject_to_its_organisation_unit() -> None:
    """A data set reports for a place, so its subject is that unit's Location."""
    response = _documents([_DATA_SET])["BfMAe6Itzgt-example-1"]
    assert response.subject is not None
    assert response.subject.reference == f"Location/{_ROOT_ORG_UNIT}"


def test_an_event_response_declares_the_form_type_alone() -> None:
    """An event program's response carries no period and no tracker context."""
    response = _documents([_EVENT_PROGRAM])["VBqh0ynB2wv-example-1"]
    assert _extension_urls(response) == [f"{_UNIT_CANONICAL}/StructureDefinition/d2-form-type"]


def test_a_tracker_event_response_leads_with_its_unit_then_its_enrollment() -> None:
    """A stage's response declares D2OrganisationUnit, D2TrackerEnrollment, then D2FormType."""
    response = _documents([_BIRTH_STAGE])["A03MvHHogjR-example-1"]
    assert _extension_urls(response) == [
        f"{_UNIT_CANONICAL}/StructureDefinition/d2-organisation-unit",
        f"{_UNIT_CANONICAL}/StructureDefinition/d2-tracker-enrollment",
        f"{_UNIT_CANONICAL}/StructureDefinition/d2-form-type",
    ]


def test_a_tracker_event_response_names_its_subject_by_tracked_entity_identifier() -> None:
    """A tracker event is captured for a person, so its subject is a Patient named by UID."""
    response = _documents([_BIRTH_STAGE])["A03MvHHogjR-example-1"]
    assert response.subject is not None
    assert response.subject.reference is None
    assert response.subject.type == "Patient"
    assert response.subject.identifier is not None
    assert response.subject.identifier.system == "http://dhis2.org/fhir/id/tracked-entity"


def test_a_tracker_event_response_names_its_enrollment_under_the_enrollment_system() -> None:
    """The enrollment extension carries the UID under the DHIS2 tracker-enrollment identifier system."""
    response = _documents([_BIRTH_STAGE])["A03MvHHogjR-example-1"]
    enrollment = (response.extension or [])[1]
    assert enrollment.valueIdentifier is not None
    assert enrollment.valueIdentifier.system == "http://dhis2.org/fhir/id/tracker-enrollment"


@pytest.mark.parametrize(
    ("source", "instance_id", "profile_id"),
    [
        (_DATA_SET, "BfMAe6Itzgt-example-1", "d2-aggregate-response"),
        (_EVENT_PROGRAM, "VBqh0ynB2wv-example-1", "d2-event-response"),
        (_BIRTH_STAGE, "A03MvHHogjR-example-1", "d2-tracker-event-response"),
    ],
)
def test_a_complete_response_claims_its_form_kinds_profile(
    source: QuestionnaireSourceIn, instance_id: str, profile_id: str
) -> None:
    """A response carrying every 1..1 element its profile requires declares that profile."""
    response = _documents([source])[instance_id]
    assert response.meta is not None
    assert response.meta.profile == [f"{_UNIT_CANONICAL}/StructureDefinition/{profile_id}"]


def test_a_periodless_data_set_response_claims_no_profile() -> None:
    """A data set with no resolvable period cannot conform to the aggregate profile, so it claims none."""
    periodless = _DATA_SET.model_copy(update={"uid": "BfMAe6Itzgu", "period_type": None})
    response = _documents([periodless])["BfMAe6Itzgu-example-1"]
    assert response.meta is None


def test_an_option_set_answer_codes_into_the_published_code_system() -> None:
    """A coded answer names the CodeSystem the same run publishes, at the URL it is published at."""
    response = _documents([_DATA_SET])["BfMAe6Itzgt-example-1"]
    section = (response.item or [])[0]
    answered = [child for child in section.item or [] if child.linkId == "De3aaaaaaaa"]
    coding = (answered[0].answer or [])[0].valueCoding
    assert coding is not None
    assert coding.system == f"{_UNIT_CANONICAL}/CodeSystem/d2-os-Os1aaaaaaaa-cs"
    assert coding.code in {"Op1aaaaaaaa", "Op2aaaaaaaa"}
    assert coding.display in {"Female", "Male"}


def test_a_multi_text_answer_repeats_one_coding_per_selected_option() -> None:
    """DHIS2 joins a MULTI_TEXT value's codes with commas; FHIR answers one coding each."""
    response = _documents([_MULTI_TEXT_PROGRAM])["VBqh0ynB2wy-example-1"]
    answers = (response.item or [])[0].answer or []
    codes = [answer.valueCoding.code for answer in answers if answer.valueCoding is not None]
    assert len(codes) == 2
    assert len(set(codes)) == 2


def test_an_aggregate_question_splits_into_one_cell_per_option_combo() -> None:
    """A data set disaggregated by a real category combo answers `<deUid>.<cocUid>`, as its form asks."""
    response = _documents([_DATA_SET])["BfMAe6Itzgt-example-1"]
    section = (response.item or [])[0]
    group = (section.item or [])[0]
    assert group.linkId == "De2aaaaaaaa"
    assert [cell.linkId for cell in group.item or []] == ["De2aaaaaaaa.Coc1aaaaaaa", "De2aaaaaaaa.Coc2aaaaaaa"]


def test_an_event_question_answers_the_flat_link_id_its_form_asks() -> None:
    """An event data value carries no category option combo, so its response answers `<deUid>` alone."""
    response = _documents([_CATEGORISED_EVENT_PROGRAM])["VBqh0ynB2wx-example-1"]
    items = response.item or []
    assert [item.linkId for item in items] == ["De2aaaaaaaa"]
    assert items[0].item is None
    assert len(items[0].answer or []) == 1


def test_an_integer_answer_lands_on_value_integer() -> None:
    """An INTEGER question answers as a FHIR integer, not as the string DHIS2 stores."""
    response = _documents([_EVENT_PROGRAM])["VBqh0ynB2wv-example-1"]
    answer = ((response.item or [])[0].answer or [])[0]
    assert isinstance(answer.valueInteger, int)
    assert answer.valueString is None


def test_a_datetime_answer_lands_on_value_date_time() -> None:
    """A DATETIME question answers as a zoned R4 dateTime."""
    response = _documents([_EVENT_PROGRAM])["VBqh0ynB2wv-example-1"]
    answer = ((response.item or [])[1].answer or [])[0]
    assert answer.valueDateTime is not None
    assert answer.valueDateTime.endswith("Z")


def test_each_example_of_a_target_gets_its_own_document() -> None:
    """Asking for several examples per target yields several ids, each answering differently."""
    documents = _documents([_EVENT_PROGRAM], per_target=3)
    assert sorted(documents) == [
        "VBqh0ynB2wv-example-1",
        "VBqh0ynB2wv-example-2",
        "VBqh0ynB2wv-example-3",
    ]


def test_a_response_whose_target_is_absent_is_skipped() -> None:
    """A response naming a form the run does not build gets no document, as the FSH path skips it."""
    synthetic = build_synthetic_responses([_EVENT_PROGRAM], [], 1, _ROOT_ORG_UNIT, _UNIT_TODAY)
    config = GenerateConfig()
    build = build_example_documents(
        [_DATA_SET], synthetic.responses, [], config, _UNIT_CANONICAL, option_set_plan=option_set_identities([], config)
    )
    assert build.responses == []
