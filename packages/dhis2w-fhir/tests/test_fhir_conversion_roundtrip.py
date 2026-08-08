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

`test_fhir_conversion.py` covers the value types, dials, and refusals these fixtures do not reach.
"""

from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Any

import pytest
from dhis2w_fhir import (
    AttributeCodeIndex,
    GenerateConfig,
    OptionSetIn,
    QuestionnaireSourceIn,
    build_example_documents,
    build_questionnaire_documents,
    build_synthetic_responses,
    option_set_identities,
)
from dhis2w_fhir.conversion import (
    ConversionContext,
    ConversionNaming,
    ConversionReport,
    ConversionResult,
    build_conversion_context,
    translate_responses,
)
from dhis2w_fhir.r4 import CodeSystem, Identifier, Location, ValueSet
from dhis2w_fhir.resources.examples.schemas import ExampleResponseIn
from dhis2w_fhir.resources.option_sets import build_option_set_artifacts, build_option_set_concept_maps
from dhis2w_fhir.resources.questionnaires import source_items

_SOURCE_DIRECTORY = Path(__file__).parent / "data" / "questionnaire-sources"

#: The IG the fixtures were fetched for - `[ig] canonical` of its `fhir.toml`.
_CANONICAL = "http://localhost:8080/fhir"

#: The instance's root organisation unit - the one every synthetic example is subject to.
_ROOT_ORG_UNIT = "ImspTQPwCqd"

#: The day the synthetic values are anchored on, which decides the reporting period each data set gets.
_REFERENCE_DATE = datetime.date(2026, 8, 8)

#: The IANA zone one run states its instance's zone-less timestamps are wall-clock readings in.
_ZONE = "Asia/Vientiane"

#: Every example the run builds, and which DHIS2 payload each one reports as.
_AGGREGATE_IDS = ["BfMAe6Itzgt-example-1", "TuL8IOPzpHh-example-1"]
_EVENT_IDS = ["EVTsupVis01-example-1", "lxAQ7Zs9VYR-example-1"]
_TRACKER_EVENT_IDS = ["A03MvHHogjR-example-1", "PsAncVisit1-example-1", "ZzYYXq4fJie-example-1"]
_EXAMPLE_IDS = sorted([*_AGGREGATE_IDS, *_EVENT_IDS, *_TRACKER_EVENT_IDS])


def _fixture(name: str) -> Any:
    """Read one committed source fixture."""
    return json.loads((_SOURCE_DIRECTORY / f"{name}.json").read_text(encoding="utf-8"))


def _sources() -> list[QuestionnaireSourceIn]:
    """The forms the run fetched, as the emitter projection."""
    return [QuestionnaireSourceIn.model_validate(entry) for entry in _fixture("sources")]


def _option_sets() -> list[OptionSetIn]:
    """The option sets the run's answers are coded from, options included."""
    return [OptionSetIn.model_validate(entry) for entry in _fixture("example-option-sets")]


def _plan_sets() -> list[OptionSetIn]:
    """The option-set selection the terminology target plans its identities over."""
    return [OptionSetIn.model_validate(entry) for entry in _fixture("option-sets")]


def _captured() -> list[ExampleResponseIn]:
    """The DHIS2-side captures the run invents - the values the round trip has to come back to."""
    return build_synthetic_responses(_sources(), _option_sets(), 1, _ROOT_ORG_UNIT, _REFERENCE_DATE).responses


def _context(config: GenerateConfig) -> ConversionContext:
    """The translation context, assembled from the artifacts the same run publishes."""
    sources = _sources()
    plan = option_set_identities(_plan_sets(), config)
    questionnaires = build_questionnaire_documents(
        sources,
        config,
        _CANONICAL,
        ig_status="draft",
        option_set_plan=plan,
        attribute_codes=AttributeCodeIndex(),
    ).questionnaires
    terminology = build_option_set_artifacts(
        _option_sets(), config, _CANONICAL, ig_status="draft", attribute_codes=AttributeCodeIndex()
    )
    code_systems: list[CodeSystem] = []
    value_sets: list[ValueSet] = []
    for artifact in terminology.artifacts:
        name = artifact.relative_path.rsplit("/", 1)[-1]
        if name.startswith("CodeSystem-"):
            code_systems.append(CodeSystem.model_validate_json(artifact.content))
        elif name.startswith("ValueSet-"):
            value_sets.append(ValueSet.model_validate_json(artifact.content))
    naming = ConversionNaming.from_config(config, _CANONICAL)
    return build_conversion_context(
        naming,
        questionnaires,
        code_systems=code_systems,
        value_sets=value_sets,
        concept_maps=build_option_set_concept_maps(_option_sets(), config, _CANONICAL, ig_status="draft"),
        locations=[
            Location(
                id=_ROOT_ORG_UNIT, identifier=[Identifier(system=naming.organisation_unit_system, value=_ROOT_ORG_UNIT)]
            )
        ],
        value_types_by_data_element={
            item.uid: item.value_type for source in _sources() for item in source_items(source)
        },
        timezone=config.timezone,
    )


def _report(config: GenerateConfig | None = None) -> ConversionReport:
    """Publish the run's example responses and translate every one of them back."""
    resolved = config if config is not None else GenerateConfig()
    documents = build_example_documents(
        _sources(),
        _captured(),
        _option_sets(),
        resolved,
        _CANONICAL,
        option_set_plan=option_set_identities(_plan_sets(), resolved),
    )
    return translate_responses(documents.responses, _context(resolved))


def _results() -> dict[str, ConversionResult]:
    """Every translated result of the default run, keyed by the response id it came from."""
    return {str(result.response_id): result for result in _report().results}


def _captures() -> dict[str, ExampleResponseIn]:
    """Every DHIS2-side capture of the default run, keyed by the response id built from it."""
    return {capture.instance_id: capture for capture in _captured()}


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
    assert sorted(_results()) == _EXAMPLE_IDS


def test_no_example_of_the_run_refuses_to_translate() -> None:
    """The examples target publishes what the capture contract admits, so all of it is translatable."""
    refused = {response_id: result.refusals for response_id, result in _results().items() if result.is_refused}
    assert refused == {}


@pytest.mark.parametrize("response_id", _EXAMPLE_IDS)
def test_every_data_value_comes_back_to_what_the_example_was_built_from(response_id: str) -> None:
    """QR -> DHIS2 inverts DHIS2 -> QR: same data elements, same option combos, same wire values."""
    assert _translated_values(_results()[response_id]) == _captured_values(_captures()[response_id])


@pytest.mark.parametrize("response_id", _AGGREGATE_IDS)
def test_an_aggregate_example_reports_for_the_data_set_period_and_unit_it_was_captured_for(response_id: str) -> None:
    """The envelope's three keys come back off the form identifier, the D2Period extension, and the subject."""
    result = _results()[response_id]
    capture = _captures()[response_id]
    assert result.data_value_set is not None
    assert capture.period is not None
    assert result.data_value_set.dataSet == capture.target_uid
    assert result.data_value_set.period == capture.period.iso
    assert result.data_value_set.orgUnit == capture.organisation_unit_uid


@pytest.mark.parametrize("response_id", _EVENT_IDS)
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


@pytest.mark.parametrize("response_id", _TRACKER_EVENT_IDS)
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
    report = _report()
    assert len(report.results) == len(_EXAMPLE_IDS)
    assert len(report.data_value_sets) == len(_AGGREGATE_IDS)
    assert len(report.events) == len(_EVENT_IDS) + len(_TRACKER_EVENT_IDS)
    assert report.refused == ()


def test_an_events_occurrence_is_written_as_the_wall_clock_the_project_zone_reads() -> None:
    """The same UTC instant reads seven hours later in `Asia/Vientiane`, and DHIS2 stores the local clock."""
    utc = {str(result.response_id): result for result in _report().results}
    zoned = {str(result.response_id): result for result in _report(GenerateConfig(timezone=_ZONE)).results}
    for response_id in _EVENT_IDS + _TRACKER_EVENT_IDS:
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
    first = _report().model_dump_json(exclude_none=True)
    second = _report().model_dump_json(exclude_none=True)
    assert first == second
