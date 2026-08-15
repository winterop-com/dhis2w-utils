"""Reading a compiled Questionnaire into the index a received answer is checked against."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from dhis2w_fhir.r4 import QuestionnaireResponseAnswer
from dhis2w_fhir_serve.capture import (
    CaptureIndexCache,
    CaptureNaming,
    UnreadableQuestionnaireError,
    build_capture_index,
)
from dhis2w_fhir_serve.capture.index import asked_link_ids
from dhis2w_fhir_serve.store import ResourceStore
from fixture_project import (
    COLLECTS_INCIDENT_DATE_EXTENSION,
    COVERAGE_LINK_THRESHOLD,
    HAEMOGLOBIN_RULE_CONDITION,
    HAEMOGLOBIN_RULE_DESCRIPTION,
    HAEMOGLOBIN_RULE_NAME,
    HAEMOGLOBIN_RULE_UID,
    OUTBREAK_FIRST_DAY,
    OUTBREAK_LAST_DAY,
    PROGRAM_RULE_EXTENSION,
    REGISTRATION_GENERATED_ATTRIBUTE,
    REGISTRATION_QUESTIONNAIRE_BODY,
    REGISTRATION_UNIQUE_ATTRIBUTE,
    VISIT_ORDER_RULE_UID,
)

#: The canonical the dhis2w-fhir goldens were compiled under, as `capture_project` serves them.
CANONICAL = "http://localhost:8080/fhir"

AGGREGATE_QUESTIONNAIRE = f"{CANONICAL}/Questionnaire/BfMAe6Itzgt"
EVENT_QUESTIONNAIRE = f"{CANONICAL}/Questionnaire/EVTsupVis01"
TRACKER_QUESTIONNAIRE = f"{CANONICAL}/Questionnaire/ZzYYXq4fJie"
ANC_QUESTIONNAIRE = f"{CANONICAL}/Questionnaire/PsAncVisit1"
TEMPORAL_QUESTIONNAIRE = f"{CANONICAL}/Questionnaire/PrTemporal1"
INFANT_FEEDING_CODE_SYSTEM = f"{CANONICAL}/CodeSystem/d2-os-x31y45jvIQL-cs"

Golden = Callable[[str], dict[str, Any]]


def _index(canonical: str, indexes: CaptureIndexCache, naming: CaptureNaming, store: ResourceStore) -> Any:
    """The index of one served questionnaire."""
    return indexes.resolve(canonical, naming, store)


def test_an_aggregate_form_indexes_its_sections_and_its_cells(
    capture_indexes: CaptureIndexCache, capture_naming: CaptureNaming, capture_store: ResourceStore
) -> None:
    index = _index(AGGREGATE_QUESTIONNAIRE, capture_indexes, capture_naming, capture_store)

    assert index.form_kind == "aggregate"
    assert index.target_uid == "BfMAe6Itzgt"
    assert index.program_uid is None
    assert "Y2rk0vzgvAx" in index.group_link_ids
    assert "s46m5MS0hxu" in index.group_link_ids
    assert "s46m5MS0hxu" not in index.questions


def test_a_cell_carries_its_data_element_and_its_category_option_combo(
    capture_indexes: CaptureIndexCache, capture_naming: CaptureNaming, capture_store: ResourceStore
) -> None:
    index = _index(AGGREGATE_QUESTIONNAIRE, capture_indexes, capture_naming, capture_store)

    cell = index.questions["s46m5MS0hxu.Prlt0C1RF0s"]

    assert cell.kind == "cell"
    assert cell.data_element_uid == "s46m5MS0hxu"
    assert cell.category_option_combo_uid == "Prlt0C1RF0s"
    assert cell.item_type == "integer"
    assert cell.answer_element == "valueInteger"


def test_an_event_form_is_flat_and_names_its_program(
    capture_indexes: CaptureIndexCache, capture_naming: CaptureNaming, capture_store: ResourceStore
) -> None:
    index = _index(EVENT_QUESTIONNAIRE, capture_indexes, capture_naming, capture_store)

    assert index.form_kind == "event"
    assert index.program_uid == "EVTsupVis01"
    assert index.group_link_ids == frozenset()
    assert index.questions["YtbsuPPo010"].kind == "plain"
    assert index.questions["YtbsuPPo010"].category_option_combo_uid is None
    assert index.questions["YtbsuPPo010"].answer_element == "valueDecimal"


def test_a_tracker_stage_names_the_program_it_belongs_to(
    capture_indexes: CaptureIndexCache, capture_naming: CaptureNaming, capture_store: ResourceStore
) -> None:
    index = _index(TRACKER_QUESTIONNAIRE, capture_indexes, capture_naming, capture_store)

    assert index.form_kind == "tracker-event"
    assert index.target_uid == "ZzYYXq4fJie"
    assert index.program_uid == "IpHINAT79UW"


@pytest.mark.parametrize(
    ("link_id", "answer_element"),
    [
        ("GQY2lXrypjO", "valueDecimal"),
        ("FqlgKAG8HOu", "valueBoolean"),
        ("X8zyunlgUfM", "valueCoding"),
        ("OuJ6sgPyAbC", "valueString"),
    ],
)
def test_each_item_type_indexes_the_element_its_answer_carries(
    link_id: str,
    answer_element: str,
    capture_indexes: CaptureIndexCache,
    capture_naming: CaptureNaming,
    capture_store: ResourceStore,
) -> None:
    index = _index(TRACKER_QUESTIONNAIRE, capture_indexes, capture_naming, capture_store)

    assert index.questions[link_id].answer_element == answer_element


def test_a_bound_question_resolves_the_code_system_behind_its_value_set(
    capture_indexes: CaptureIndexCache, capture_naming: CaptureNaming, capture_store: ResourceStore
) -> None:
    index = _index(TRACKER_QUESTIONNAIRE, capture_indexes, capture_naming, capture_store)

    assert index.questions["X8zyunlgUfM"].option_system == INFANT_FEEDING_CODE_SYSTEM
    assert index.questions["GQY2lXrypjO"].option_system is None


def test_a_value_set_the_facade_does_not_serve_leaves_the_binding_open(
    capture_naming: CaptureNaming, capture_store: ResourceStore, load_golden: Golden
) -> None:
    body = load_golden("Questionnaire-ZzYYXq4fJie.json")
    body["item"][1]["answerValueSet"] = f"{CANONICAL}/ValueSet/d2-os-never-published-vs"

    index = build_capture_index(body, capture_naming, capture_store)

    assert index.questions["X8zyunlgUfM"].option_system is None


def test_required_questions_and_their_bounds_are_indexed(
    capture_indexes: CaptureIndexCache, capture_naming: CaptureNaming, capture_store: ResourceStore
) -> None:
    index = _index(ANC_QUESTIONNAIRE, capture_indexes, capture_naming, capture_store)

    visit_number = index.questions["DeAncVisNo1"]

    assert visit_number.required is True
    assert visit_number.bounds is not None
    assert visit_number.bounds.minimum is not None
    assert visit_number.bounds.minimum.integer == 1
    assert visit_number.bounds.minimum.number == 1.0
    assert visit_number.bounds.minimum.stated == "1"
    assert visit_number.bounds.maximum is None
    assert index.questions["DeAncBpSys1"].required is False
    assert index.questions["DeAncBpSys1"].bounds is None


def test_a_date_bound_is_indexed_as_a_calendar_day_rather_than_a_number(
    capture_indexes: CaptureIndexCache, capture_naming: CaptureNaming, capture_store: ResourceStore
) -> None:
    """No DHIS2 value type states a range of days, so a date bound stays a date all the way through."""
    index = _index(TEMPORAL_QUESTIONNAIRE, capture_indexes, capture_naming, capture_store)

    bounds = index.questions["DeVisitDate1"].bounds

    assert bounds is not None
    assert bounds.minimum is not None
    assert bounds.maximum is not None
    assert bounds.minimum.date == OUTBREAK_FIRST_DAY
    assert bounds.maximum.date == OUTBREAK_LAST_DAY
    assert bounds.minimum.number is None
    assert bounds.maximum.stated == OUTBREAK_LAST_DAY


def test_a_decimal_bound_keeps_the_places_the_form_wrote(
    capture_indexes: CaptureIndexCache, capture_naming: CaptureNaming, capture_store: ResourceStore
) -> None:
    index = _index(TEMPORAL_QUESTIONNAIRE, capture_indexes, capture_naming, capture_store)

    bounds = index.questions["DeCoverage01"].bounds

    assert bounds is not None
    assert bounds.minimum is not None
    assert bounds.maximum is not None
    assert bounds.minimum.number == 0.0
    assert bounds.maximum.number == 100.0


def test_every_item_of_a_form_carries_a_gate_naming_where_it_sits(
    capture_indexes: CaptureIndexCache, capture_naming: CaptureNaming, capture_store: ResourceStore
) -> None:
    """A group's conditions decide every question under it, so the gates cover groups as well as questions."""
    index = _index(AGGREGATE_QUESTIONNAIRE, capture_indexes, capture_naming, capture_store)

    assert set(index.gates) == set(index.questions) | set(index.group_link_ids)
    assert set(index.item_link_ids) == set(index.gates)
    cell = index.gates["s46m5MS0hxu.Prlt0C1RF0s"]
    assert cell.parent_link_id is not None
    assert cell.conditions == ()
    assert index.item_link_ids.index(cell.parent_link_id) < index.item_link_ids.index(cell.link_id)


def test_an_items_enable_when_is_indexed_with_the_behaviour_it_combines_under(
    capture_indexes: CaptureIndexCache, capture_naming: CaptureNaming, capture_store: ResourceStore
) -> None:
    index = _index(TEMPORAL_QUESTIONNAIRE, capture_indexes, capture_naming, capture_store)

    gate = index.gates["DeVisitLink1"]

    assert gate.behavior == "all"
    assert len(gate.conditions) == 1
    assert gate.conditions[0].question == "DeCoverage01"
    assert gate.conditions[0].operator == ">="
    assert gate.conditions[0].answerDecimal == COVERAGE_LINK_THRESHOLD


@pytest.mark.parametrize(
    ("coverage", "asks_the_link"),
    [(COVERAGE_LINK_THRESHOLD + 10, True), (COVERAGE_LINK_THRESHOLD - 10, False), (None, False)],
)
def test_a_condition_is_false_against_a_question_nobody_answered(
    coverage: float | None,
    asks_the_link: bool,
    capture_indexes: CaptureIndexCache,
    capture_naming: CaptureNaming,
    capture_store: ResourceStore,
) -> None:
    """R4: nothing to compare is not a comparison that holds, so an unanswered question closes what it gates."""
    index = _index(TEMPORAL_QUESTIONNAIRE, capture_indexes, capture_naming, capture_store)
    answers = {} if coverage is None else {"DeCoverage01": [QuestionnaireResponseAnswer(valueDecimal=coverage)]}

    asked = asked_link_ids(index, answers)

    assert ("DeVisitLink1" in asked) is asks_the_link
    assert "DeVisitDate1" in asked


def test_a_form_lists_the_program_rules_its_instance_enforces(
    capture_indexes: CaptureIndexCache, capture_naming: CaptureNaming, capture_store: ResourceStore
) -> None:
    """The rules are read for naming rather than for evaluating - DHIS2 evaluates its own on import."""
    index = _index(ANC_QUESTIONNAIRE, capture_indexes, capture_naming, capture_store)

    assert [rule.rule_uid for rule in index.program_rules] == [HAEMOGLOBIN_RULE_UID, VISIT_ORDER_RULE_UID]
    haemoglobin = index.program_rules[0]
    assert haemoglobin.name == HAEMOGLOBIN_RULE_NAME
    assert haemoglobin.description == HAEMOGLOBIN_RULE_DESCRIPTION
    assert haemoglobin.condition == HAEMOGLOBIN_RULE_CONDITION
    assert haemoglobin.action == "SHOWERROR"
    # A rule DHIS2 holds no description for states none, which is what most rules are.
    assert index.program_rules[1].description is None


def test_a_form_declaring_no_program_rules_lists_none(
    capture_indexes: CaptureIndexCache, capture_naming: CaptureNaming, capture_store: ResourceStore
) -> None:
    index = _index(TEMPORAL_QUESTIONNAIRE, capture_indexes, capture_naming, capture_store)

    assert index.program_rules == ()


def test_a_program_rule_missing_its_uid_name_or_condition_is_passed_over(
    capture_naming: CaptureNaming, capture_store: ResourceStore
) -> None:
    """Three sub-extensions make a rule nameable; a repeat without them says less than nothing."""
    body = {
        **REGISTRATION_QUESTIONNAIRE_BODY,
        "extension": [
            *REGISTRATION_QUESTIONNAIRE_BODY["extension"],
            {"url": PROGRAM_RULE_EXTENSION, "extension": [{"url": "name", "valueString": "A rule with no uid"}]},
        ],
    }

    index = build_capture_index(body, capture_naming, capture_store)

    assert index.program_rules == ()


def test_a_read_only_question_is_indexed_as_one(capture_naming: CaptureNaming, capture_store: ResourceStore) -> None:
    """`item.readOnly` is how a generated tracked entity attribute reaches a client, so the index carries it.

    DHIS2 mints the value on import, which is what makes it the one kind of question this server
    neither draws an answer for nor waits on - both rules read this flag.
    """
    index = build_capture_index(REGISTRATION_QUESTIONNAIRE_BODY, capture_naming, capture_store)

    generated = index.questions[REGISTRATION_GENERATED_ATTRIBUTE]

    assert generated.read_only is True
    assert generated.required is True
    assert index.questions[REGISTRATION_UNIQUE_ATTRIBUTE].read_only is False


def test_the_index_reads_the_incident_date_off_the_forms_own_declaration(
    capture_indexes: CaptureIndexCache,
    capture_naming: CaptureNaming,
    capture_store: ResourceStore,
    load_golden: Golden,
) -> None:
    """One declared fact, read the same way whichever store serves the form - no example is consulted."""
    declared = build_capture_index(_registration_declaring(True, load_golden), capture_naming, capture_store)
    disclaimed = build_capture_index(_registration_declaring(False, load_golden), capture_naming, capture_store)

    assert declared.collects_incident_date is True
    assert disclaimed.collects_incident_date is False
    assert _index(ANC_QUESTIONNAIRE, capture_indexes, capture_naming, capture_store).collects_incident_date is False


def test_a_form_declaring_nothing_collects_no_incident_date(
    capture_naming: CaptureNaming, capture_store: ResourceStore, load_golden: Golden
) -> None:
    """A response leaving D2IncidentAt off is complete, so silence and an explicit false mean one thing."""
    body = _registration_declaring(True, load_golden)
    body["extension"] = [
        extension for extension in body["extension"] if extension["url"] != COLLECTS_INCIDENT_DATE_EXTENSION
    ]

    assert build_capture_index(body, capture_naming, capture_store).collects_incident_date is False


def _registration_declaring(collects: bool, load_golden: Golden) -> dict[str, Any]:  # noqa: FBT001
    """The stage golden retyped as a registration form declaring one answer about its program's incident date."""
    body = load_golden("Questionnaire-PsAncVisit1.json")
    body["extension"] = [
        {"url": f"{CANONICAL}/StructureDefinition/d2-form-type", "valueCode": "tracker"},
        {"url": COLLECTS_INCIDENT_DATE_EXTENSION, "valueBoolean": collects},
    ]
    return body


def test_an_index_is_built_once_and_then_read_from_the_cache(
    capture_indexes: CaptureIndexCache, capture_naming: CaptureNaming, capture_store: ResourceStore
) -> None:
    first = _index(EVENT_QUESTIONNAIRE, capture_indexes, capture_naming, capture_store)
    second = _index(EVENT_QUESTIONNAIRE, capture_indexes, capture_naming, capture_store)

    assert first is second
    assert capture_indexes.count() == 1


def test_a_canonical_the_facade_does_not_serve_is_refused(
    capture_indexes: CaptureIndexCache, capture_naming: CaptureNaming, capture_store: ResourceStore
) -> None:
    with pytest.raises(UnreadableQuestionnaireError, match="is served here"):
        capture_indexes.resolve(f"{CANONICAL}/Questionnaire/nope", capture_naming, capture_store)


def test_a_canonical_resolving_to_another_resource_type_is_refused(
    capture_indexes: CaptureIndexCache, capture_naming: CaptureNaming, capture_store: ResourceStore
) -> None:
    with pytest.raises(UnreadableQuestionnaireError, match="not a Questionnaire"):
        capture_indexes.resolve(f"{CANONICAL}/CodeSystem/d2-de-cs", capture_naming, capture_store)


def test_a_questionnaire_declaring_no_form_kind_is_refused(
    capture_naming: CaptureNaming, capture_store: ResourceStore, load_golden: Golden
) -> None:
    body = load_golden("Questionnaire-EVTsupVis01.json")
    body["extension"] = [{"url": capture_naming.form_type_url, "valueCode": "made-up"}]

    with pytest.raises(UnreadableQuestionnaireError, match="no DHIS2 form kind this server captures"):
        build_capture_index(body, capture_naming, capture_store)


def test_a_questionnaire_with_no_canonical_is_refused(
    capture_naming: CaptureNaming, capture_store: ResourceStore, load_golden: Golden
) -> None:
    body = load_golden("Questionnaire-EVTsupVis01.json")
    del body["url"]

    with pytest.raises(UnreadableQuestionnaireError, match="no canonical url"):
        build_capture_index(body, capture_naming, capture_store)


def test_an_item_answering_as_a_type_with_no_capture_element_is_refused(
    capture_naming: CaptureNaming, capture_store: ResourceStore, load_golden: Golden
) -> None:
    body = load_golden("Questionnaire-EVTsupVis01.json")
    body["item"][0]["type"] = "quantity"

    with pytest.raises(UnreadableQuestionnaireError, match="carries no capture element"):
        build_capture_index(body, capture_naming, capture_store)


def test_a_body_that_is_not_a_readable_questionnaire_is_refused(
    capture_naming: CaptureNaming, capture_store: ResourceStore
) -> None:
    with pytest.raises(UnreadableQuestionnaireError, match="could not be read"):
        build_capture_index({"resourceType": "Questionnaire", "item": "not a list"}, capture_naming, capture_store)
