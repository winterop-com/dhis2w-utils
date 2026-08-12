"""Golden round trip: every example response of a whole generate run translates back to what it came from.

`tests/data/questionnaire-sources/` holds the projections one generate run of the local DHIS2 stack
fetched - two data sets, two event programs, three tracker stages, and the option sets they bind.
This suite builds the synthetic example responses from them exactly as `d2w fhir generate examples`
does, publishes the QuestionnaireResponse documents, and translates each document back into the
DHIS2 import payload it reports.

The assertion is an identity: every data value the translator writes equals the DHIS2 value the
example was built from, cell for cell, including the 124 disaggregated cells of the larger data set.
DHIS2 -> QR and QR -> DHIS2 are two independently written paths over one contract, and this is the
gate that fails when they stop agreeing.

The run itself is `conversion_corpus.py`, shared with the contract gate that holds the same
payloads against the published logical model. `test_fhir_conversion.py` covers the value types,
dials, and refusals these fixtures do not reach.
"""

from __future__ import annotations

import datetime

import pytest
from conversion_corpus import (
    AGGREGATE_IDS,
    EVENT_IDS,
    EXAMPLE_IDS,
    TRACKER_EVENT_IDS,
    captured,
    report,
)
from dhis2w_fhir import GenerateConfig
from dhis2w_fhir.conversion import ConversionResult
from dhis2w_fhir.resources.examples.schemas import ExampleResponseIn

#: The IANA zone one run states its instance's zone-less timestamps are wall-clock readings in.
_ZONE = "Asia/Vientiane"


def _results() -> dict[str, ConversionResult]:
    """Every translated result of the default run, keyed by the response id it came from."""
    return {str(result.response_id): result for result in report().results}


def _captures() -> dict[str, ExampleResponseIn]:
    """Every DHIS2-side capture of the default run, keyed by the response id built from it."""
    return {capture.instance_id: capture for capture in captured()}


def _translated_values(result: ConversionResult) -> dict[tuple[str, str | None], str | None]:
    """The data values one payload carries, keyed the way DHIS2 keys them."""
    if result.data_value_set is not None:
        return {
            (value.dataElement or "", value.categoryOptionCombo): value.value
            for value in result.data_value_set.dataValues or []
        }
    assert result.event is not None
    return {(value.dataElement or "", None): value.value for value in result.event.dataValues or []}


def _captured_values(capture: ExampleResponseIn) -> dict[tuple[str, str | None], str | None]:
    """The DHIS2 values the capture held, keyed the same way, so the two sides compare directly."""
    return {
        (
            answer.data_element_uid,
            answer.category_option_combo_uid if capture.kind == "aggregate" else None,
        ): answer.value
        for answer in capture.answers
    }


def test_the_run_translates_every_example_it_published() -> None:
    """No response is silently dropped from - or added to - the batch the translator drains."""
    assert sorted(_results()) == EXAMPLE_IDS


def test_no_example_of_the_run_refuses_to_translate() -> None:
    """The examples target publishes what the capture contract admits, so all of it is translatable."""
    refused = {response_id: result.refusals for response_id, result in _results().items() if result.is_refused}
    assert refused == {}


@pytest.mark.parametrize("response_id", EXAMPLE_IDS)
def test_every_data_value_comes_back_to_what_the_example_was_built_from(response_id: str) -> None:
    """QR -> DHIS2 inverts DHIS2 -> QR: same data elements, same option combos, same wire values."""
    assert _translated_values(_results()[response_id]) == _captured_values(_captures()[response_id])


@pytest.mark.parametrize("response_id", AGGREGATE_IDS)
def test_an_aggregate_example_reports_for_the_data_set_period_and_unit_it_was_captured_for(response_id: str) -> None:
    """The envelope's keys come back off the form identifier, D2Period, the subject, and D2AttributeOptionCombo."""
    result = _results()[response_id]
    capture = _captures()[response_id]
    assert result.data_value_set is not None
    assert capture.period is not None
    assert result.data_value_set.dataSet == capture.target_uid
    assert result.data_value_set.period == capture.period.iso
    assert result.data_value_set.orgUnit == capture.organisation_unit_uid
    assert result.data_value_set.attributeOptionCombo == capture.attribute_option_combo_uid


def test_a_non_default_data_set_comes_back_keyed_to_the_attribute_option_combo_it_was_built_from() -> None:
    """The one selected data set on a non-default category combo names its third key, and the default one does not."""
    results = _results()
    captures = _captures()
    non_default = "TuL8IOPzpHh-example-1"
    default = "BfMAe6Itzgt-example-1"
    assert captures[non_default].attribute_option_combo_uid is not None
    assert results[non_default].data_value_set is not None
    assert (
        results[non_default].data_value_set.attributeOptionCombo == captures[non_default].attribute_option_combo_uid  # type: ignore[union-attr]
    )
    assert captures[default].attribute_option_combo_uid is None
    assert results[default].data_value_set is not None
    assert results[default].data_value_set.attributeOptionCombo is None  # type: ignore[union-attr]


@pytest.mark.parametrize("response_id", EVENT_IDS)
def test_an_event_example_reports_the_program_and_unit_it_was_captured_at(response_id: str) -> None:
    """An event program's response names its program and no stage; the unit rides on the Location subject."""
    result = _results()[response_id]
    capture = _captures()[response_id]
    assert result.event is not None
    assert result.event.program == capture.target_uid
    assert result.event.programStage is None
    assert result.event.orgUnit == capture.organisation_unit_uid
    assert result.event.status is not None
    assert result.event.status.value == "COMPLETED"


@pytest.mark.parametrize("response_id", TRACKER_EVENT_IDS)
def test_a_tracker_event_example_reports_its_stage_entity_and_enrollment(response_id: str) -> None:
    """A stage response names the stage it reports, the person it is about, and the enrollment it sits on."""
    result = _results()[response_id]
    capture = _captures()[response_id]
    assert result.event is not None
    assert result.event.programStage == capture.target_uid
    assert result.event.program is not None
    assert result.event.trackedEntity == capture.tracked_entity_uid
    assert result.event.enrollment == capture.enrollment_uid
    assert result.event.orgUnit == capture.organisation_unit_uid


def test_the_batch_report_splits_the_run_into_the_two_dhis2_endpoints_it_posts_to() -> None:
    """Two data sets go to `/api/dataValueSets`, five program forms go to `/api/tracker`."""
    translated = report()
    assert len(translated.results) == len(EXAMPLE_IDS)
    assert len(translated.data_value_sets) == len(AGGREGATE_IDS)
    assert len(translated.events) == len(EVENT_IDS) + len(TRACKER_EVENT_IDS)
    assert translated.refused == ()


def test_an_events_occurrence_is_written_as_the_wall_clock_the_project_zone_reads() -> None:
    """The same UTC instant reads seven hours later in `Asia/Vientiane`, and DHIS2 stores the local clock."""
    utc = {str(result.response_id): result for result in report().results}
    zoned = {str(result.response_id): result for result in report(GenerateConfig(timezone=_ZONE)).results}
    for response_id in EVENT_IDS + TRACKER_EVENT_IDS:
        in_utc = utc[response_id].event
        in_zone = zoned[response_id].event
        assert in_utc is not None
        assert in_zone is not None
        # `TrackerEvent.occurredAt` is the generated `Instant`, which R4's own OpenAPI types as
        # `datetime | int`; the translator only ever writes the zone-less datetime half of it.
        assert isinstance(in_utc.occurredAt, datetime.datetime)
        assert isinstance(in_zone.occurredAt, datetime.datetime)
        assert in_zone.occurredAt - in_utc.occurredAt == datetime.timedelta(hours=7)
        assert in_zone.occurredAt.tzinfo is None


def test_translating_twice_yields_the_identical_payloads() -> None:
    """Translation is a pure function of the response and the context, so a drained spool replays."""
    first = report().model_dump_json(exclude_none=True)
    second = report().model_dump_json(exclude_none=True)
    assert first == second
