"""The fidelity carriers a form publishes beside its questions, held from both emitters at once.

Every one of these is a fact the DHIS2 data-entry app renders and a generated form used to drop:
the reporting frequency a data set is captured under, the words the instance puts on the dates a
form captures, whether a tracker stage repeats, the free text a question is described by, the
questions DHIS2 writes itself, and the disaggregated cells a data set never captures at all.

The FSH string and the JSON document are asserted side by side in each test, because the two
emitters agreeing is the whole contract - the compiled goldens in the parity suites pin that they
agree with SUSHI, and these pin what they agree about.
"""

from __future__ import annotations

import json
from typing import Any

from dhis2w_client.generated.v42.schemas import DataSet
from dhis2w_fhir import (
    AttributeCodeIndex,
    CategoryAxisIn,
    CategoryComboIn,
    CategoryOptionComboIn,
    GenerateConfig,
    ProgramContextIn,
    QuestionnaireItemIn,
    QuestionnaireSectionIn,
    QuestionnaireSourceIn,
    build_data_dictionary_documents,
    build_questionnaire_artifacts,
    build_questionnaire_documents,
    form_date_labels,
    form_period_type,
    form_repeatable,
    option_set_identities,
    ordered_option_combos,
    question_read_only,
)
from dhis2w_fhir.notes import GenerateNote
from dhis2w_fhir.r4 import FhirBase
from dhis2w_fhir.service import _data_set_source

_CANONICAL = "http://example.org/fhir"


def _definition(segment: str) -> str:
    """The absolute URL one foundation extension is published at."""
    return f"{_CANONICAL}/StructureDefinition/{segment}"


#: The two axes of the demo instance's location-by-age disaggregation, in the order DHIS2 declares
#: them: location first, age group second, and each axis's options in the instance's own order.
_LOCATION_AND_AGE = CategoryComboIn(
    uid="dzjKKQq0cSO",
    name="Location and age group",
    categories=[
        CategoryAxisIn(uid="fMZEcRHuamy", option_uids=["qkPbeWaFsnU", "wbrDrL2aYEc"]),
        CategoryAxisIn(uid="YNZyaJHiHYq", option_uids=["btOyqprQ9e8", "GEqzEKCHoGA"]),
    ],
    option_combos=[
        CategoryOptionComboIn(
            uid="Coc1aaaaaaa", name="Outreach, >1y", category_option_uids=["GEqzEKCHoGA", "wbrDrL2aYEc"]
        ),
        CategoryOptionComboIn(
            uid="Coc2aaaaaaa", name="Fixed, <1y", category_option_uids=["btOyqprQ9e8", "qkPbeWaFsnU"]
        ),
        CategoryOptionComboIn(
            uid="Coc3aaaaaaa", name="Outreach, <1y", category_option_uids=["btOyqprQ9e8", "wbrDrL2aYEc"]
        ),
        CategoryOptionComboIn(
            uid="Coc4aaaaaaa", name="Fixed, >1y", category_option_uids=["GEqzEKCHoGA", "qkPbeWaFsnU"]
        ),
    ],
)

_DISAGGREGATED = QuestionnaireItemIn(
    uid="De1aaaaaaaa",
    name="BCG doses given",
    value_type="INTEGER",
    description="Doses of BCG administered, counted at the point of service.",
    category_combo=_LOCATION_AND_AGE,
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
            description="Vaccines given at this visit.",
            items=[_DISAGGREGATED],
        )
    ],
)

_STAGE = QuestionnaireSourceIn(
    uid="PsAncVisit1",
    name="ANC visit",
    kind="tracker-event",
    program=ProgramContextIn(uid="PrAncCare01", name="ANC follow-up"),
    repeatable=True,
    event_date_label="Visit date",
    flat_items=[QuestionnaireItemIn(uid="De2aaaaaaaa", name="Weight", value_type="NUMBER")],
)

_GENERATED_ATTRIBUTE = QuestionnaireItemIn(
    uid="Tea1aaaaaaa",
    name="Unique ID",
    value_type="TEXT",
    unique=True,
    generated=True,
    pattern="RANDOM(#######)",
    display_in_list=True,
    entity_level=True,
)

_REGISTRATION = QuestionnaireSourceIn(
    uid="IpHINAT79UW",
    name="Child Programme",
    kind="tracker",
    tracked_entity_type_uid="nEenWmSyUEp",
    enrollment_date_label="Date of enrollment",
    incident_date_label="Date of birth",
    flat_items=[_GENERATED_ATTRIBUTE],
)


def _fsh(sources: list[QuestionnaireSourceIn]) -> dict[str, str]:
    """The FSH artifacts of one selection, indexed by relative path."""
    build = build_questionnaire_artifacts(
        sources,
        GenerateConfig(),
        _CANONICAL,
        ig_status="draft",
        option_set_plan=option_set_identities([], GenerateConfig()),
        attribute_codes=AttributeCodeIndex(),
    )
    return {artifact.relative_path: artifact.content for artifact in build.artifacts}


def _document(source: QuestionnaireSourceIn) -> dict[str, Any]:
    """The built Questionnaire document of one form, parsed back from the JSON the writer emits."""
    build = build_questionnaire_documents(
        [source],
        GenerateConfig(),
        _CANONICAL,
        ig_status="draft",
        option_set_plan=option_set_identities([], GenerateConfig()),
        attribute_codes=AttributeCodeIndex(),
    )
    return _dumped(build.questionnaires[0])


def _dumped(resource: FhirBase) -> dict[str, Any]:
    """One built resource as the JSON object the writer serialises it to."""
    body: dict[str, Any] = json.loads(resource.model_dump_json(exclude_none=True, by_alias=True))
    return body


def _extension(document: dict[str, Any], segment: str) -> dict[str, Any] | None:
    """One extension of a built document, by the last segment of its definition URL."""
    return next(
        (entry for entry in document.get("extension", []) if entry["url"] == _definition(segment)),
        None,
    )


def test_an_aggregate_form_declares_the_period_type_its_responses_report_under() -> None:
    """The reporting frequency is a fact about the data set, so the form states it rather than an example."""
    assert form_period_type(_DATA_SET) == "Monthly"
    assert "* extension[D2PeriodType].valueCode = #Monthly" in _fsh([_DATA_SET])["data-sets/BfMAe6Itzgt.fsh"]
    assert _extension(_document(_DATA_SET), "d2-period-type") == {
        "url": _definition("d2-period-type"),
        "valueCode": "Monthly",
    }


def test_a_form_of_any_other_kind_declares_no_period_type() -> None:
    """Only a data set has a reporting frequency, so no other kind invents one."""
    assert form_period_type(_STAGE) is None
    assert form_period_type(_REGISTRATION) is None
    assert _extension(_document(_STAGE), "d2-period-type") is None


def test_a_data_set_the_instance_left_unfrequented_declares_nothing() -> None:
    """An absent period type is stated as absence, never guessed at."""
    unfrequented = _DATA_SET.model_copy(update={"period_type": None})
    assert form_period_type(unfrequented) is None
    assert "D2PeriodType" not in _fsh([unfrequented])["data-sets/BfMAe6Itzgt.fsh"]


def test_a_tracker_stage_declares_whether_it_repeats_either_way() -> None:
    """A client offering to add a second event has to know, so the fact is published true and false alike."""
    assert form_repeatable(_STAGE) is True
    assert form_repeatable(_STAGE.model_copy(update={"repeatable": False})) is False
    content = _fsh([_STAGE])["tracker-programs/PrAncCare01/PsAncVisit1.fsh"]
    assert "* extension[D2Repeatable].valueBoolean = true" in content
    assert _extension(_document(_STAGE), "d2-repeatable") == {
        "url": _definition("d2-repeatable"),
        "valueBoolean": True,
    }


def test_no_other_form_kind_declares_repeatability() -> None:
    """An aggregate form is keyed by its period and a registration is answered once, so neither states it."""
    assert form_repeatable(_DATA_SET) is None
    assert form_repeatable(_REGISTRATION) is None
    assert _extension(_document(_DATA_SET), "d2-repeatable") is None


def test_a_registration_form_carries_the_words_the_instance_puts_on_its_enrollment_dates() -> None:
    """Both labels ride one complex extension, each in its own slice, exactly as DHIS2 states them."""
    labels = form_date_labels(_REGISTRATION, [])
    assert labels.enrollment_date is not None
    assert labels.enrollment_date.value == "Date of enrollment"
    assert labels.incident_date is not None
    assert labels.incident_date.value == "Date of birth"
    assert labels.event_date is None
    content = _fsh([_REGISTRATION])["tracker-programs/IpHINAT79UW/registration.fsh"]
    assert '* extension[D2DateLabels].extension[enrollmentDate].valueString = "Date of enrollment"' in content
    assert '* extension[D2DateLabels].extension[incidentDate].valueString = "Date of birth"' in content
    assert _extension(_document(_REGISTRATION), "d2-date-labels") == {
        "url": _definition("d2-date-labels"),
        "extension": [
            {"url": "enrollmentDate", "valueString": "Date of enrollment"},
            {"url": "incidentDate", "valueString": "Date of birth"},
        ],
    }


def test_a_stage_form_carries_the_words_the_instance_puts_on_its_event_date() -> None:
    """A stage captures an event, so the one slice it states is the event date."""
    labels = form_date_labels(_STAGE, [])
    assert labels.event_date is not None
    assert labels.event_date.value == "Visit date"
    assert labels.enrollment_date is None
    assert _extension(_document(_STAGE), "d2-date-labels") == {
        "url": _definition("d2-date-labels"),
        "extension": [{"url": "eventDate", "valueString": "Visit date"}],
    }


def test_a_form_the_instance_labelled_nothing_on_carries_no_date_labels_at_all() -> None:
    """Absence is the honest answer: a capture client then uses its own wording."""
    unlabelled = _STAGE.model_copy(update={"event_date_label": None})
    assert form_date_labels(unlabelled, []).stated is False
    assert "D2DateLabels" not in _fsh([unlabelled])["tracker-programs/PrAncCare01/PsAncVisit1.fsh"]
    assert _extension(_document(unlabelled), "d2-date-labels") is None


def test_a_question_carries_the_dhis2_free_text_about_the_object_it_asks() -> None:
    """The description is guidance for the person filling the form, so it rides the item, not its text."""
    content = _fsh([_DATA_SET])["data-sets/BfMAe6Itzgt.fsh"]
    assert f'* item[=].item[=].extension[+].url = "{_definition("d2-description")}"' in content
    assert (
        '* item[=].item[=].extension[=].valueString = "Doses of BCG administered, counted at the point of service."'
        in content
    )
    question = _document(_DATA_SET)["item"][0]["item"][0]
    assert question["extension"] == [
        {
            "url": _definition("d2-description"),
            "valueString": "Doses of BCG administered, counted at the point of service.",
        }
    ]


def test_a_section_group_carries_its_own_description_beside_the_grid_control() -> None:
    """A section is described the way a question is, and the item control still closes the list."""
    section = _document(_DATA_SET)["item"][0]
    assert section["extension"][0] == {
        "url": _definition("d2-description"),
        "valueString": "Vaccines given at this visit.",
    }
    assert section["extension"][1]["url"].endswith("questionnaire-itemControl")


def test_an_object_the_instance_describes_nothing_about_carries_no_description() -> None:
    """The extension states a description DHIS2 holds, never an empty one."""
    plain = _STAGE
    assert "d2-description" not in _fsh([plain])["tracker-programs/PrAncCare01/PsAncVisit1.fsh"]
    assert "extension" not in _document(plain)["item"][0]


def test_a_generated_attribute_is_published_as_a_read_only_question() -> None:
    """DHIS2 mints the value off its own pattern, so the form must not invite anyone to type one."""
    assert question_read_only(_GENERATED_ATTRIBUTE, "tracker") is True
    content = _fsh([_REGISTRATION])["tracker-programs/IpHINAT79UW/registration.fsh"]
    assert "* item[=].readOnly = true" in content
    assert _document(_REGISTRATION)["item"][0]["readOnly"] is True


def test_a_question_anyone_answers_states_no_read_only_at_all() -> None:
    """An absent element already means false, so writing it would say nothing twice."""
    typed = _GENERATED_ATTRIBUTE.model_copy(update={"generated": False, "pattern": None})
    assert question_read_only(typed, "tracker") is None
    assert question_read_only(_DISAGGREGATED, "aggregate") is None
    registration = _REGISTRATION.model_copy(update={"flat_items": [typed]})
    assert "readOnly" not in _fsh([registration])["tracker-programs/IpHINAT79UW/registration.fsh"]
    assert "readOnly" not in _document(registration)["item"][0]


def test_the_attribute_vocabulary_states_who_writes_the_value_and_from_what_pattern() -> None:
    """`generated` and `pattern` are facts about the attribute, so they ride its concept."""
    build = build_data_dictionary_documents([_REGISTRATION], GenerateConfig(), _CANONICAL, ig_status="draft")
    concept = _dumped(build.code_systems[0])["concept"][0]
    carried = {entry["code"]: entry.get("valueBoolean", entry.get("valueString")) for entry in concept["property"]}
    assert carried["generated"] is True
    assert carried["pattern"] == "RANDOM(#######)"
    assert carried["display-in-list"] is True


def test_an_attribute_dhis2_generates_nothing_for_states_no_pattern() -> None:
    """DHIS2 sends an empty pattern for an ungenerated attribute, and an empty string states nothing."""
    typed = _GENERATED_ATTRIBUTE.model_copy(update={"generated": False, "pattern": None, "display_in_list": False})
    build = build_data_dictionary_documents(
        [_REGISTRATION.model_copy(update={"flat_items": [typed]})],
        GenerateConfig(),
        _CANONICAL,
        ig_status="draft",
    )
    concept = _dumped(build.code_systems[0])["concept"][0]
    carried = {entry["code"] for entry in concept["property"]}
    assert "pattern" not in carried
    assert carried >= {"generated", "display-in-list"}


def test_disaggregated_cells_follow_the_declared_axis_order_rather_than_their_names() -> None:
    """DHIS2 declares its categories and their options in order, and that order is the grid the app renders."""
    assert [combo.name for combo in ordered_option_combos(_LOCATION_AND_AGE)] == [
        "Fixed, <1y",
        "Fixed, >1y",
        "Outreach, <1y",
        "Outreach, >1y",
    ]


def test_a_cell_no_declared_axis_places_falls_back_to_its_name_and_uid() -> None:
    """The order stays total whatever the instance leaves unstated, so regeneration is byte-stable."""
    unplaced = _LOCATION_AND_AGE.model_copy(update={"categories": []})
    assert [combo.uid for combo in ordered_option_combos(unplaced)] == [
        "Coc2aaaaaaa",
        "Coc4aaaaaaa",
        "Coc3aaaaaaa",
        "Coc1aaaaaaa",
    ]


#: One data set as DHIS2 sends it: two cells of a two-cell disaggregation greyed out by its section.
_GREYED_WIRE_DATA_SET: dict[str, Any] = {
    "id": "BfMAe6Itzgt",
    "name": "Child Health",
    "periodType": "Monthly",
    "sections": [
        {
            "id": "Sec1aaaaaaa",
            "name": "Nutrition",
            "dataElements": [{"id": "De1aaaaaaaa"}, {"id": "De2aaaaaaaa"}],
            "greyedFields": [
                {"dataElement": {"id": "De1aaaaaaaa"}, "categoryOptionCombo": {"id": "Coc2aaaaaaa"}},
                {"dataElement": {"id": "De2aaaaaaaa"}, "categoryOptionCombo": {"id": "Coc1aaaaaaa"}},
                {"dataElement": {"id": "De2aaaaaaaa"}, "categoryOptionCombo": {"id": "Coc2aaaaaaa"}},
            ],
        }
    ],
    "dataSetElements": [
        {
            "dataElement": {
                "id": uid,
                "name": name,
                "valueType": "INTEGER",
                "categoryCombo": {
                    "id": "CcAaBbCcDdE",
                    "name": "EPI/nutrition age",
                    "isDefault": False,
                    "categories": [{"id": "YNZyaJHiHYq", "categoryOptions": [{"id": "Opt1"}, {"id": "Opt2"}]}],
                    "categoryOptionCombos": [
                        {"id": "Coc1aaaaaaa", "name": "<1y", "categoryOptions": [{"id": "Opt1"}]},
                        {"id": "Coc2aaaaaaa", "name": ">1y", "categoryOptions": [{"id": "Opt2"}]},
                    ],
                },
            }
        }
        for uid, name in (("De1aaaaaaaa", "BCG doses given"), ("De2aaaaaaaa", "Measles doses given"))
    ],
}


def _greyed_source() -> tuple[QuestionnaireSourceIn, list[GenerateNote]]:
    """The projection of the greyed data set, with whatever notes reading it raised."""
    notes: list[GenerateNote] = []
    source = _data_set_source(DataSet.model_validate(_GREYED_WIRE_DATA_SET), notes)
    return source, notes


def test_a_greyed_cell_is_not_published_and_the_run_says_how_many_were_dropped() -> None:
    """DHIS2 refuses input on a greyed cell, so a form asking it would ask a question with no answer."""
    source, notes = _greyed_source()
    published = {
        item.uid: [combo.uid for combo in (item.category_combo.option_combos if item.category_combo else [])]
        for item in source.sections[0].items
    }
    assert published == {"De1aaaaaaaa": ["Coc1aaaaaaa"]}
    assert len(notes) == 1
    assert "greys out 3 disaggregated cells" in notes[0].message
    assert "Child Health" in notes[0].message


def test_a_question_whose_every_cell_is_greyed_is_dropped_whole() -> None:
    """A group with no children is a question nobody can answer, so the data element goes with its cells."""
    source, _ = _greyed_source()
    assert [item.uid for item in source.sections[0].items] == ["De1aaaaaaaa"]
    assert source.flat_items == []


def test_a_data_set_that_greys_nothing_raises_no_note_and_keeps_every_cell() -> None:
    """The note is about the cells that went missing, so a form that lost none says nothing."""
    section: dict[str, Any] = {**_GREYED_WIRE_DATA_SET["sections"][0], "greyedFields": []}
    ungreyed: dict[str, Any] = {**_GREYED_WIRE_DATA_SET, "sections": [section]}
    notes: list[GenerateNote] = []
    source = _data_set_source(DataSet.model_validate(ungreyed), notes)
    assert notes == []
    assert [len(item.category_combo.option_combos) for item in source.sections[0].items if item.category_combo] == [
        2,
        2,
    ]
