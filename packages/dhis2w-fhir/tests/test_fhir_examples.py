"""Tests for the example target: synthetic and instance-sourced QuestionnaireResponses.

The synthetic goldens are full-text assertions. They can be, because the values are seeded
from a SHA-256 of the target UID rather than from `hash()` - the only thing that moves with
the calendar is the reporting period the example is anchored to, which the fixtures pin by
passing an explicit `today`.
"""

from __future__ import annotations

import datetime
import re
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest
import respx
from dhis2w_cli.main import build_app
from dhis2w_core.profile import resolve_profile
from dhis2w_fhir import (
    ExampleSelection,
    GenerateConfig,
    InitOptions,
    NamingConfig,
    build_example_artifacts,
    build_synthetic_responses,
    load_project,
    service,
)
from dhis2w_fhir.period import parse_period
from dhis2w_fhir.resources.examples import (
    EXAMPLES_DIRECTORY,
    _is_fhir_date,
    _is_fhir_date_time,
    _is_fhir_time,
    response_status_code,
    zoned_date_time,
)
from dhis2w_fhir.resources.examples.schemas import ExampleAnswerIn, ExampleResponseIn
from dhis2w_fhir.resources.option_sets import option_set_identities
from dhis2w_fhir.resources.option_sets.schemas import OptionIn, OptionSetIdentityPlan, OptionSetIn
from dhis2w_fhir.resources.questionnaires.schemas import (
    CategoryComboIn,
    CategoryOptionComboIn,
    QuestionnaireItemIn,
    QuestionnaireSectionIn,
    QuestionnaireSourceIn,
)
from typer.testing import CliRunner

_HOST = "https://dhis2.example"
_CANONICAL = "http://example.org/fhir"
_TODAY = datetime.date(2026, 8, 2)
_ROOT_ORG_UNIT = "ImspTQPwCqd"

_DEFAULT_COMBO = CategoryComboIn(uid="bjDvmb4bfuf", name="default", is_default=True)
_AGE_COMBO = CategoryComboIn(
    uid="CcAaBbCcDdE",
    name="EPI/nutrition age",
    option_combos=[
        CategoryOptionComboIn(uid="Coc1aaaaaaa", name="<1y", code="U1"),
        CategoryOptionComboIn(uid="Coc2aaaaaaa", name=">1y"),
    ],
)

_DATA_SET = QuestionnaireSourceIn(
    uid="BfMAe6Itzgt",
    name="Child Health",
    code="DS_359711",
    kind="aggregate",
    period_type="Monthly",
    sections=[
        QuestionnaireSectionIn(
            uid="Sec1aaaaaaa",
            name="Immunization",
            items=[
                QuestionnaireItemIn(
                    uid="De1aaaaaaaa",
                    name="BCG doses given",
                    form_name="BCG",
                    value_type="INTEGER_ZERO_OR_POSITIVE",
                    category_combo=_DEFAULT_COMBO,
                ),
                QuestionnaireItemIn(
                    uid="De2aaaaaaaa", name="Measles doses given", value_type="INTEGER", category_combo=_AGE_COMBO
                ),
            ],
        ),
        QuestionnaireSectionIn(
            uid="Sec2aaaaaaa",
            name="Demographics",
            items=[
                QuestionnaireItemIn(uid="De3aaaaaaaa", name="Gender", value_type="TEXT", option_set_uid="Os1aaaaaaaa"),
                QuestionnaireItemIn(uid="De4aaaaaaaa", name="Coverage", value_type="PERCENTAGE"),
                QuestionnaireItemIn(uid="De5aaaaaaaa", name="Visit date", value_type="DATE"),
                QuestionnaireItemIn(uid="De6aaaaaaaa", name="Reported", value_type="TRUE_ONLY"),
                QuestionnaireItemIn(uid="De7aaaaaaaa", name="Comment", value_type="LONG_TEXT"),
            ],
        ),
    ],
)

_EVENT_PROGRAM = QuestionnaireSourceIn(
    uid="VBqh0ynB2wv",
    name="Malaria case registration",
    kind="event",
    flat_items=[
        QuestionnaireItemIn(uid="qrur9Dvnyt5", name="Age in years", value_type="INTEGER", compulsory=True),
        QuestionnaireItemIn(uid="De8aaaaaaaa", name="Severity", value_type="UNIT_INTERVAL"),
        QuestionnaireItemIn(uid="De9aaaaaaaa", name="Seen at", value_type="DATETIME"),
    ],
)

_OPTION_SETS = [
    OptionSetIn(
        uid="Os1aaaaaaaa",
        name="Gender",
        options=[
            OptionIn(uid="Op1aaaaaaaa", code="F", name="Female", sort_order=1),
            OptionIn(uid="Op2aaaaaaaa", code="M", name="Male", sort_order=2),
        ],
    )
]

_SYNTHETIC_DATA_SET_GOLDEN = """Instance: QuestionnaireResponse-BfMAe6Itzgt-example-1
InstanceOf: D2AggregateResponse
Title: "Example response - Child Health"
Description: "Example QuestionnaireResponse against the DHIS2 data set Child Health (BfMAe6Itzgt)."
Usage: #example
* id = "BfMAe6Itzgt-example-1"
* extension[D2FormType].valueCode = #aggregate
* extension[D2Period].extension[iso].valueString = "202607"
* extension[D2Period].extension[type].valueCode = #Monthly
* extension[D2Period].extension[period].valuePeriod.start = "2026-07-01"
* extension[D2Period].extension[period].valuePeriod.end = "2026-07-31"
* questionnaire = "http://example.org/fhir/Questionnaire/BfMAe6Itzgt"
* status = #completed
* subject = Reference(Location/ImspTQPwCqd)
* item[+].linkId = "Sec1aaaaaaa"
* item[=].item[+].linkId = "De1aaaaaaaa"
* item[=].item[=].answer[+].valueInteger = 12
* item[=].item[+].linkId = "De2aaaaaaaa"
* item[=].item[=].item[+].linkId = "De2aaaaaaaa.Coc1aaaaaaa"
* item[=].item[=].item[=].answer[+].valueInteger = 941
* item[=].item[=].item[+].linkId = "De2aaaaaaaa.Coc2aaaaaaa"
* item[=].item[=].item[=].answer[+].valueInteger = 658
* item[+].linkId = "Sec2aaaaaaa"
* item[=].item[+].linkId = "De3aaaaaaaa"
* item[=].item[=].answer[+].valueCoding = D2OS_Os1aaaaaaaa_CS#Op2aaaaaaaa "Male"
* item[=].item[+].linkId = "De4aaaaaaaa"
* item[=].item[=].answer[+].valueDecimal = 41.2
* item[=].item[+].linkId = "De5aaaaaaaa"
* item[=].item[=].answer[+].valueDate = "2026-07-12"
* item[=].item[+].linkId = "De6aaaaaaaa"
* item[=].item[=].answer[+].valueBoolean = true
* item[=].item[+].linkId = "De7aaaaaaaa"
* item[=].item[=].answer[+].valueString = "Example Comment"
"""

_SYNTHETIC_EVENT_GOLDEN = """Instance: QuestionnaireResponse-VBqh0ynB2wv-example-1
InstanceOf: D2EventResponse
Title: "Example response - Malaria case registration"
Description: "Example QuestionnaireResponse against the DHIS2 event program Malaria case registration (VBqh0ynB2wv)."
Usage: #example
* id = "VBqh0ynB2wv-example-1"
* extension[D2FormType].valueCode = #event
* questionnaire = "http://example.org/fhir/Questionnaire/VBqh0ynB2wv"
* status = #completed
* subject = Reference(Location/ImspTQPwCqd)
* authored = "2026-07-30T14:00:00Z"
* item[+].linkId = "qrur9Dvnyt5"
* item[=].answer[+].valueInteger = 905
* item[+].linkId = "De8aaaaaaaa"
* item[=].answer[+].valueDecimal = 0.7
* item[+].linkId = "De9aaaaaaaa"
* item[=].answer[+].valueDateTime = "2026-07-26T05:00:00Z"
"""

_DATA_SETS_PAYLOAD = {
    "dataSets": [
        {
            "id": "BfMAe6Itzgt",
            "name": "Child Health",
            "code": "DS_359711",
            "periodType": "Monthly",
            "sections": [
                {"id": "Sec1aaaaaaa", "name": "Immunization", "dataElements": [{"id": "De1aaaaaaaa"}]},
                {"id": "Sec2aaaaaaa", "name": "Demographics", "dataElements": [{"id": "De3aaaaaaaa"}]},
            ],
            "dataSetElements": [
                {
                    "dataElement": {
                        "id": "De1aaaaaaaa",
                        "name": "BCG doses given",
                        "formName": "BCG",
                        "valueType": "INTEGER_ZERO_OR_POSITIVE",
                        "categoryCombo": {
                            "id": "CcAaBbCcDdE",
                            "name": "EPI/nutrition age",
                            "isDefault": False,
                            "categoryOptionCombos": [
                                {"id": "Coc1aaaaaaa", "name": "<1y", "code": "U1"},
                                {"id": "Coc2aaaaaaa", "name": ">1y"},
                            ],
                        },
                    }
                },
                {
                    "dataElement": {
                        "id": "De3aaaaaaaa",
                        "name": "Gender",
                        "valueType": "TEXT",
                        "optionSet": {"id": "Os1aaaaaaaa"},
                        "categoryCombo": {"id": "bjDvmb4bfuf", "name": "default", "isDefault": True},
                    }
                },
            ],
        }
    ]
}

_PROGRAMS_PAYLOAD = {
    "programs": [
        {
            "id": "VBqh0ynB2wv",
            "name": "Malaria case registration",
            "programType": "WITHOUT_REGISTRATION",
            "programStages": [
                {
                    "id": "pTo4uMt3xur",
                    "programStageSections": [],
                    "programStageDataElements": [
                        {
                            "compulsory": True,
                            "dataElement": {"id": "qrur9Dvnyt5", "name": "Age in years", "valueType": "INTEGER"},
                        },
                        {
                            "compulsory": False,
                            "dataElement": {
                                "id": "De3aaaaaaaa",
                                "name": "Gender",
                                "valueType": "TEXT",
                                "optionSet": {"id": "Os1aaaaaaaa"},
                            },
                        },
                    ],
                }
            ],
        }
    ]
}

_OPTION_SETS_PAYLOAD = {
    "optionSets": [
        {
            "id": "Os1aaaaaaaa",
            "options": [
                {"id": "Op1aaaaaaaa", "code": "F", "name": "Female"},
                {"id": "Op2aaaaaaaa", "code": "M", "name": "Male"},
            ],
        }
    ]
}

_ROOT_PAYLOAD = {"organisationUnits": [{"id": _ROOT_ORG_UNIT}]}

_EMPTY_DATA_VALUE_SET = {"dataSet": "BfMAe6Itzgt", "dataValues": []}

_DATA_VALUE_SET = {
    "dataSet": "BfMAe6Itzgt",
    "period": "202606",
    "dataValues": [
        {
            "dataElement": "De1aaaaaaaa",
            "period": "202606",
            "orgUnit": "Ou1aaaaaaaa",
            "categoryOptionCombo": "Coc1aaaaaaa",
            "attributeOptionCombo": "HllvX50cXC0",
            "value": "11",
        },
        {
            "dataElement": "De1aaaaaaaa",
            "period": "202606",
            "orgUnit": "Ou1aaaaaaaa",
            "categoryOptionCombo": "Coc2aaaaaaa",
            "attributeOptionCombo": "HllvX50cXC0",
            "value": "22",
        },
        {
            "dataElement": "De3aaaaaaaa",
            "period": "202606",
            "orgUnit": "Ou1aaaaaaaa",
            "categoryOptionCombo": "bjDvmb4bfuf",
            "attributeOptionCombo": "HllvX50cXC0",
            "value": "F",
        },
        {
            "dataElement": "Dexaaaaaaaa",
            "period": "202606",
            "orgUnit": "Ou1aaaaaaaa",
            "categoryOptionCombo": "bjDvmb4bfuf",
            "attributeOptionCombo": "HllvX50cXC0",
            "value": "stray",
        },
        {
            "dataElement": "De1aaaaaaaa",
            "period": "202606",
            "orgUnit": "Ou2aaaaaaaa",
            "categoryOptionCombo": "Coc1aaaaaaa",
            "attributeOptionCombo": "HllvX50cXC0",
            "value": "3",
        },
    ],
}

_EVENTS_PAYLOAD = {
    "instances": [
        {
            "event": "Ev1aaaaaaaa",
            "orgUnit": "Ou1aaaaaaaa",
            "occurredAt": "2026-07-15T10:30:00.000",
            "status": "COMPLETED",
            "dataValues": [
                {"dataElement": "qrur9Dvnyt5", "value": "42"},
                {"dataElement": "De3aaaaaaaa", "value": "M"},
            ],
        }
    ]
}

_runner = CliRunner()


def _plan(option_sets: list[OptionSetIn], config: GenerateConfig | None = None) -> OptionSetIdentityPlan:
    """The identity plan the service hands the emitter: the fetched option sets, named by their UIDs."""
    return option_set_identities(
        [OptionSetIn(uid=option_set.uid, name=option_set.uid) for option_set in option_sets],
        config or GenerateConfig(),
    )


def _synthetic(
    sources: list[QuestionnaireSourceIn],
    option_sets: list[OptionSetIn] | None = None,
    per_target: int = 1,
    config: GenerateConfig | None = None,
) -> dict[str, str]:
    """Build the synthetic example artifacts for `sources` and index them by relative path."""
    resolved_option_sets = _OPTION_SETS if option_sets is None else option_sets
    resolved_config = config or GenerateConfig()
    synthetic = build_synthetic_responses(sources, resolved_option_sets, per_target, _ROOT_ORG_UNIT, _TODAY)
    build = build_example_artifacts(
        sources,
        synthetic.responses,
        resolved_option_sets,
        resolved_config,
        _CANONICAL,
        option_set_plan=_plan(resolved_option_sets, resolved_config),
    )
    return {artifact.relative_path: artifact.content for artifact in build.artifacts}


def _aggregate_response(answers: list[ExampleAnswerIn]) -> ExampleResponseIn:
    """One hand-built data-set response, period included so only the assertion's own note can fire."""
    return ExampleResponseIn(
        instance_id="BfMAe6Itzgt-202606-Ou1aaaaaaaa",
        target_uid="BfMAe6Itzgt",
        kind="aggregate",
        organisation_unit_uid="Ou1aaaaaaaa",
        status_code="completed",
        period=parse_period("202606"),
        answers=answers,
    )


def test_synthetic_data_set_example_is_a_stable_golden() -> None:
    """A sectioned, disaggregated, option-set-bound data set answers every question deterministically."""
    assert _synthetic([_DATA_SET])[f"{EXAMPLES_DIRECTORY}/BfMAe6Itzgt-1.fsh"] == _SYNTHETIC_DATA_SET_GOLDEN


def test_synthetic_event_example_is_a_stable_golden() -> None:
    """An event program carries `authored` and no D2Period, and answers its flat questions."""
    assert _synthetic([_EVENT_PROGRAM])[f"{EXAMPLES_DIRECTORY}/VBqh0ynB2wv-1.fsh"] == _SYNTHETIC_EVENT_GOLDEN


def test_each_example_declares_the_response_profile_of_its_form_kind() -> None:
    """An example is a contract check: it declares the profile its form kind's responses have to meet."""
    artifacts = _synthetic([_DATA_SET, _EVENT_PROGRAM])
    assert "InstanceOf: D2AggregateResponse" in artifacts[f"{EXAMPLES_DIRECTORY}/BfMAe6Itzgt-1.fsh"]
    assert "InstanceOf: D2EventResponse" in artifacts[f"{EXAMPLES_DIRECTORY}/VBqh0ynB2wv-1.fsh"]
    assert not any("InstanceOf: QuestionnaireResponse" in content for content in artifacts.values())


def test_the_declared_response_profile_follows_the_naming_prefix() -> None:
    """A renamed prefix renames the profiles, so the examples have to follow it or stop validating."""
    config = GenerateConfig(naming=NamingConfig(prefix="Dhis2"))
    artifacts = _synthetic([_DATA_SET, _EVENT_PROGRAM], config=config)
    assert "InstanceOf: Dhis2AggregateResponse" in artifacts[f"{EXAMPLES_DIRECTORY}/BfMAe6Itzgt-1.fsh"]
    assert "InstanceOf: Dhis2EventResponse" in artifacts[f"{EXAMPLES_DIRECTORY}/VBqh0ynB2wv-1.fsh"]


def test_example_page_titles_escape_markup() -> None:
    """An example against a `<`-bearing form carries entities in its page metadata (the breadcrumb is raw HTML)."""
    source = _DATA_SET.model_copy(update={"name": "Mortality < 5 years by gender"})
    content = _synthetic([source])[f"{EXAMPLES_DIRECTORY}/BfMAe6Itzgt-1.fsh"]
    assert 'Title: "Example response - Mortality &lt; 5 years by gender"' in content
    assert "Mortality &lt; 5 years by gender (BfMAe6Itzgt)" in content


def test_synthetic_values_are_stable_across_runs() -> None:
    """Two builds of the same target on the same day are byte-identical - the seed is not salted."""
    assert _synthetic([_DATA_SET, _EVENT_PROGRAM]) == _synthetic([_DATA_SET, _EVENT_PROGRAM])


def test_each_example_of_a_target_differs_and_gets_its_own_file() -> None:
    """`per_target` examples are numbered per target and seeded apart, so they are not copies."""
    artifacts = _synthetic([_DATA_SET], per_target=3)
    assert sorted(artifacts) == [
        f"{EXAMPLES_DIRECTORY}/BfMAe6Itzgt-1.fsh",
        f"{EXAMPLES_DIRECTORY}/BfMAe6Itzgt-2.fsh",
        f"{EXAMPLES_DIRECTORY}/BfMAe6Itzgt-3.fsh",
    ]
    assert len(set(artifacts.values())) == 3
    assert '* id = "BfMAe6Itzgt-example-3"' in artifacts[f"{EXAMPLES_DIRECTORY}/BfMAe6Itzgt-3.fsh"]


def test_a_true_only_question_is_always_answered_true() -> None:
    """TRUE_ONLY has no false value in DHIS2, so no seed may produce one."""
    source = QuestionnaireSourceIn(
        uid="Ds9aaaaaaaa",
        name="Flags",
        kind="aggregate",
        period_type="Monthly",
        flat_items=[QuestionnaireItemIn(uid="De9aaaaaaaa", name="Reported", value_type="TRUE_ONLY")],
    )
    artifacts = _synthetic([source], per_target=10)
    assert all("answer[+].valueBoolean = true" in content for content in artifacts.values())
    assert not any("answer[+].valueBoolean = false" in content for content in artifacts.values())


def test_every_category_option_combo_child_is_answered() -> None:
    """A disaggregated question fills each option combo, so the grid is complete rather than sampled."""
    content = _synthetic([_DATA_SET])[f"{EXAMPLES_DIRECTORY}/BfMAe6Itzgt-1.fsh"]
    assert '* item[=].item[=].item[+].linkId = "De2aaaaaaaa.Coc1aaaaaaa"' in content
    assert '* item[=].item[=].item[+].linkId = "De2aaaaaaaa.Coc2aaaaaaa"' in content
    assert content.count("* item[=].item[=].item[=].answer[+].valueInteger = ") == 2


@pytest.mark.parametrize(
    ("code_source", "coding"),
    [
        ("id", 'D2OS_Os1aaaaaaaa_CS#Op1aaaaaaaa "Female"'),
        ("code", 'D2OS_Os1aaaaaaaa_CS#F "Female"'),
    ],
)
def test_an_option_value_answers_as_the_configured_concept_code(code_source: str, coding: str) -> None:
    """The stored DHIS2 option code resolves to whichever concept code the option-set terminology emits."""
    config = GenerateConfig.model_validate({"concept_code_source": code_source})
    response = _aggregate_response([ExampleAnswerIn(data_element_uid="De3aaaaaaaa", value="F")])
    build = build_example_artifacts(
        [_DATA_SET], [response], _OPTION_SETS, config, _CANONICAL, option_set_plan=_plan(_OPTION_SETS, config)
    )
    assert f"* item[=].item[=].answer[+].valueCoding = {coding}" in build.artifacts[0].content
    assert build.notes == []


def test_an_unmappable_option_value_falls_back_to_a_string_with_one_note() -> None:
    """A stored value no option carries is answered as a string, and the run says how many did that."""
    response = _aggregate_response([ExampleAnswerIn(data_element_uid="De3aaaaaaaa", value="X")])
    build = build_example_artifacts(
        [_DATA_SET], [response], _OPTION_SETS, GenerateConfig(), _CANONICAL, option_set_plan=_plan(_OPTION_SETS)
    )
    assert '* item[=].item[=].answer[+].valueString = "X"' in build.artifacts[0].content
    assert build.notes == [
        "1 example answers could not be cast to their FHIR type; answered as strings: Gender (De3aaaaaaaa) = 'X'"
    ]


@pytest.mark.parametrize(
    ("data_element_uid", "value", "expected"),
    [
        ("De1aaaaaaaa", "not-a-number", '* item[=].item[=].answer[+].valueString = "not-a-number"'),
        ("De4aaaaaaaa", "12,5", '* item[=].item[=].answer[+].valueString = "12,5"'),
        ("De6aaaaaaaa", "yes", '* item[=].item[=].answer[+].valueString = "yes"'),
        ("De5aaaaaaaa", "last tuesday", '* item[=].item[=].answer[+].valueString = "last tuesday"'),
        ("De5aaaaaaaa", "2026-99-99", '* item[=].item[=].answer[+].valueString = "2026-99-99"'),
        ("De5aaaaaaaa", "2026-02-30", '* item[=].item[=].answer[+].valueString = "2026-02-30"'),
        ("De1aaaaaaaa", "7", "* item[=].item[=].answer[+].valueInteger = 7"),
        ("De4aaaaaaaa", "12.50", "* item[=].item[=].answer[+].valueDecimal = 12.50"),
        ("De6aaaaaaaa", "1", "* item[=].item[=].answer[+].valueBoolean = true"),
        ("De5aaaaaaaa", "2024-02-29T00:00:00.000", '* item[=].item[=].answer[+].valueDate = "2024-02-29"'),
    ],
)
def test_a_value_that_will_not_cast_is_answered_as_a_string(data_element_uid: str, value: str, expected: str) -> None:
    """Numerics, booleans, and temporals cast where they can and fall back to a string where they cannot."""
    response = _aggregate_response(
        [
            ExampleAnswerIn(
                data_element_uid=data_element_uid,
                category_option_combo_uid="Coc1aaaaaaa" if data_element_uid == "De1aaaaaaaa" else None,
                value=value,
            )
        ]
    )
    build = build_example_artifacts(
        [_DATA_SET], [response], _OPTION_SETS, GenerateConfig(), _CANONICAL, option_set_plan=_plan(_OPTION_SETS)
    )
    content = build.artifacts[0].content
    assert expected in content or expected.replace("item[=].item[=]", "item[=].item[=].item[=]") in content


def test_a_value_for_a_data_element_outside_the_form_is_skipped_with_a_note() -> None:
    """A captured value the questionnaire does not ask for is dropped, counted, and named."""
    response = _aggregate_response(
        [
            ExampleAnswerIn(data_element_uid="Dexaaaaaaaa", value="stray"),
            ExampleAnswerIn(data_element_uid="De7aaaaaaaa", value="kept"),
        ]
    )
    build = build_example_artifacts(
        [_DATA_SET], [response], _OPTION_SETS, GenerateConfig(), _CANONICAL, option_set_plan=_plan(_OPTION_SETS)
    )
    assert "Dexaaaaaaaa" not in build.artifacts[0].content
    assert '* item[=].item[=].answer[+].valueString = "kept"' in build.artifacts[0].content
    assert build.notes == [
        "1 captured values reference data elements the questionnaire does not ask for; skipped: "
        "Dexaaaaaaaa in BfMAe6Itzgt-202606-Ou1aaaaaaaa"
    ]


@pytest.mark.parametrize(
    ("event_status", "response_status"),
    [
        ("COMPLETED", "completed"),
        ("ACTIVE", "in-progress"),
        ("SKIPPED", "stopped"),
        ("SCHEDULE", "completed"),
        ("OVERDUE", "completed"),
        ("VISITED", "completed"),
        (None, "completed"),
        ("SOMETHING_NEW", "completed"),
    ],
)
def test_event_status_maps_onto_the_response_status(event_status: str | None, response_status: str) -> None:
    """Every DHIS2 event status reads as a QuestionnaireResponse status, unknown ones as completed."""
    assert response_status_code(event_status) == response_status


@pytest.mark.parametrize(
    ("stored", "expected"),
    [
        ("2025-12-30T00:00:00.000", "2025-12-30T00:00:00.000Z"),
        ("2025-12-30T00:00:00Z", "2025-12-30T00:00:00Z"),
        ("2025-12-30T00:00:00+02:00", "2025-12-30T00:00:00+02:00"),
        ("2025-12-30", "2025-12-30"),
    ],
)
def test_a_zoneless_dhis2_timestamp_gains_the_utc_zone_fhir_requires(stored: str, expected: str) -> None:
    """DHIS2 serves zone-less local timestamps; an R4 dateTime carrying a time must carry a zone (BUGS.md #62)."""
    assert zoned_date_time(stored) == expected


def test_a_zoneless_occurrence_is_zoned_rather_than_emitted_invalid() -> None:
    """The event's occurredAt lands as a valid dateTime instead of failing SUSHI's primitive check."""
    response = ExampleResponseIn(
        instance_id="Ev1aaaaaaaa",
        target_uid="VBqh0ynB2wv",
        kind="event",
        organisation_unit_uid="Ou1aaaaaaaa",
        status_code="completed",
        authored="2025-12-30T00:00:00.000",
    )
    build = build_example_artifacts(
        [_EVENT_PROGRAM], [response], _OPTION_SETS, GenerateConfig(), _CANONICAL, option_set_plan=_plan(_OPTION_SETS)
    )
    assert '* authored = "2025-12-30T00:00:00.000Z"' in build.artifacts[0].content


def test_an_unusable_occurrence_is_dropped_with_a_note() -> None:
    """An occurrence FHIR cannot express is omitted rather than emitted, and the run says so."""
    response = ExampleResponseIn(
        instance_id="Ev1aaaaaaaa",
        target_uid="VBqh0ynB2wv",
        kind="event",
        organisation_unit_uid="Ou1aaaaaaaa",
        status_code="completed",
        authored="last tuesday",
    )
    build = build_example_artifacts(
        [_EVENT_PROGRAM], [response], _OPTION_SETS, GenerateConfig(), _CANONICAL, option_set_plan=_plan(_OPTION_SETS)
    )
    assert "* authored" not in build.artifacts[0].content
    assert "InstanceOf: QuestionnaireResponse\n" in build.artifacts[0].content
    assert "InstanceOf: D2EventResponse" not in build.artifacts[0].content
    assert any("base QuestionnaireResponse declared" in note for note in build.notes)


def test_a_data_set_without_a_period_type_carries_no_period_extension() -> None:
    """A data set whose period type does not resolve still gets an example, with one note explaining the gap."""
    source = QuestionnaireSourceIn(
        uid="Ds8aaaaaaaa",
        name="Periodless",
        kind="aggregate",
        flat_items=[QuestionnaireItemIn(uid="De9aaaaaaaa", name="Count", value_type="INTEGER")],
    )
    synthetic = build_synthetic_responses([source], [], 1, _ROOT_ORG_UNIT, _TODAY)
    build = build_example_artifacts(
        [source], synthetic.responses, [], GenerateConfig(), _CANONICAL, option_set_plan=_plan([])
    )
    assert "D2Period" not in build.artifacts[0].content
    assert "InstanceOf: QuestionnaireResponse\n" in build.artifacts[0].content
    assert "InstanceOf: D2AggregateResponse" not in build.artifacts[0].content
    assert any("base QuestionnaireResponse instead of the aggregate response profile" in note for note in build.notes)


def test_config_defaults_to_one_synthetic_example_per_target() -> None:
    """The example selection ships enabled and safe: one example each, generated rather than fetched."""
    selection = GenerateConfig().examples
    assert selection.per_target == 1
    assert selection.source == "synthetic"


@pytest.mark.parametrize("per_target", [-1, 11])
def test_the_example_count_is_bounded(per_target: int) -> None:
    """Past a handful examples stop illustrating, and a negative count is meaningless."""
    with pytest.raises(ValueError, match="per_target"):
        ExampleSelection(per_target=per_target)


async def _scaffold_project(directory: Path, **generate_lines: str) -> None:
    """Scaffold a project, seeding both questionnaire targets and any extra generate tables."""
    options = InitOptions(
        ig_id="dhis2.fhir.examples",
        canonical=_CANONICAL,
        name="Dhis2FhirExamples",
        title="Example IG",
        publisher="Example Org",
        data_set_ids=["BfMAe6Itzgt"],
        event_program_ids=["VBqh0ynB2wv"],
    )
    await service.init_project(directory, options)
    config_path = directory / "fhir.toml"
    body = config_path.read_text(encoding="utf-8")
    for table, entries in generate_lines.items():
        body += f"\n[generate.{table}]\n{entries}\n"
    config_path.write_text(body, encoding="utf-8")


def _mock_metadata() -> None:
    """Mock the metadata endpoints every example run reads before it looks at any data."""
    respx.get(f"{_HOST}/api/dataSets").mock(return_value=httpx.Response(200, json=_DATA_SETS_PAYLOAD))
    respx.get(f"{_HOST}/api/programs").mock(return_value=httpx.Response(200, json=_PROGRAMS_PAYLOAD))
    respx.get(f"{_HOST}/api/optionSets").mock(return_value=httpx.Response(200, json=_OPTION_SETS_PAYLOAD))
    respx.get(f"{_HOST}/api/organisationUnits").mock(return_value=httpx.Response(200, json=_ROOT_PAYLOAD))


@respx.mock
async def test_instance_mode_walks_back_to_the_newest_period_holding_data(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    tmp_path: Path,
) -> None:
    """Discovery tries completed periods newest-first and stops at the first one carrying data values."""
    mock_system_info("v42")
    await _scaffold_project(tmp_path, examples='per_target = 1\nsource = "instance"')
    _mock_metadata()
    attempts: list[str] = []

    def _data_value_sets(request: httpx.Request) -> httpx.Response:
        """Answer nothing for the first period tried, then the fixture data value set."""
        period = request.url.params["period"]
        attempts.append(period)
        empty = len(attempts) == 1
        return httpx.Response(200, json=_EMPTY_DATA_VALUE_SET if empty else _DATA_VALUE_SET)

    data_value_sets = respx.get(f"{_HOST}/api/dataValueSets").mock(side_effect=_data_value_sets)
    respx.get(f"{_HOST}/api/tracker/events").mock(return_value=httpx.Response(200, json={"instances": []}))

    report = await service.generate_examples(resolve_profile("probe"), load_project(tmp_path))

    assert data_value_sets.calls.call_count == 2
    assert attempts[0] > attempts[1]
    first = data_value_sets.calls[0].request.url.params
    assert first["dataSet"] == "BfMAe6Itzgt"
    assert first["orgUnit"] == _ROOT_ORG_UNIT
    assert first["children"] == "true"
    assert report.example_count == 1
    assert report.written_files == [f"{EXAMPLES_DIRECTORY}/BfMAe6Itzgt-1.fsh"]
    content = (tmp_path / "ig" / "input" / "fsh" / EXAMPLES_DIRECTORY / "BfMAe6Itzgt-1.fsh").read_text(encoding="utf-8")
    assert "Instance: QuestionnaireResponse-BfMAe6Itzgt-202606-Ou1aaaaaaaa" in content
    assert '* extension[D2Period].extension[iso].valueString = "202606"' in content
    assert '* extension[D2Period].extension[period].valuePeriod.end = "2026-06-30"' in content
    assert "* subject = Reference(Location/Ou1aaaaaaaa)" in content
    assert '* item[=].item[=].item[+].linkId = "De1aaaaaaaa.Coc1aaaaaaa"' in content
    assert "* item[=].item[=].item[=].answer[+].valueInteger = 11" in content
    assert '* item[=].item[=].answer[+].valueCoding = D2OS_Os1aaaaaaaa_CS#Op1aaaaaaaa "Female"' in content
    assert any("Dexaaaaaaaa" in note for note in report.notes)


@respx.mock
@pytest.mark.parametrize("envelope", ["instances", "events"])
async def test_instance_mode_reads_events_under_either_envelope_key(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    tmp_path: Path,
    envelope: str,
) -> None:
    """Each recent event becomes one example keyed by its own UID, whichever envelope the server used."""
    mock_system_info("v42")
    await _scaffold_project(tmp_path, examples='per_target = 2\nsource = "instance"')
    _mock_metadata()
    respx.get(f"{_HOST}/api/dataValueSets").mock(return_value=httpx.Response(200, json=_EMPTY_DATA_VALUE_SET))
    events = respx.get(f"{_HOST}/api/tracker/events").mock(
        return_value=httpx.Response(200, json={envelope: _EVENTS_PAYLOAD["instances"]})
    )

    report = await service.generate_examples(resolve_profile("probe"), load_project(tmp_path))

    params = events.calls.last.request.url.params
    assert params["program"] == "VBqh0ynB2wv"
    assert params["pageSize"] == "2"
    assert params["order"] == "occurredAt:desc"
    assert params["fields"] == "event,orgUnit,occurredAt,status,dataValues[dataElement,value]"
    assert report.example_count == 1
    content = (tmp_path / "ig" / "input" / "fsh" / EXAMPLES_DIRECTORY / "VBqh0ynB2wv-1.fsh").read_text(encoding="utf-8")
    assert "Instance: QuestionnaireResponse-Ev1aaaaaaaa" in content
    assert '* id = "Ev1aaaaaaaa"' in content
    assert "* status = #completed" in content
    assert '* authored = "2026-07-15T10:30:00.000Z"' in content
    assert "D2Period" not in content
    assert "* item[=].answer[+].valueInteger = 42" in content


@respx.mock
async def test_a_target_with_no_data_is_one_note_rather_than_a_failure(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    tmp_path: Path,
) -> None:
    """An instance holding nothing for the selected forms still completes, naming every empty target."""
    mock_system_info("v42")
    await _scaffold_project(tmp_path, examples='per_target = 1\nsource = "instance"')
    _mock_metadata()
    respx.get(f"{_HOST}/api/dataValueSets").mock(return_value=httpx.Response(200, json=_EMPTY_DATA_VALUE_SET))
    respx.get(f"{_HOST}/api/tracker/events").mock(return_value=httpx.Response(200, json={"instances": []}))

    report = await service.generate_examples(resolve_profile("probe"), load_project(tmp_path))

    assert report.example_count == 0
    assert report.written_files == []
    assert report.notes == [
        "2 questionnaire targets hold no data on the instance; no examples emitted: "
        "Child Health (BfMAe6Itzgt), Malaria case registration (VBqh0ynB2wv)"
    ]


@respx.mock
async def test_synthetic_mode_calls_no_data_endpoint(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    tmp_path: Path,
) -> None:
    """The default source publishes nothing off the instance, so neither data endpoint is touched."""
    mock_system_info("v42")
    await _scaffold_project(tmp_path)
    _mock_metadata()
    data_value_sets = respx.get(f"{_HOST}/api/dataValueSets").mock(return_value=httpx.Response(200, json={}))
    events = respx.get(f"{_HOST}/api/tracker/events").mock(return_value=httpx.Response(200, json={}))

    report = await service.generate_examples(resolve_profile("probe"), load_project(tmp_path))

    assert not data_value_sets.called
    assert not events.called
    assert report.example_count == 2
    assert report.target_directory == EXAMPLES_DIRECTORY
    assert sorted(report.written_files) == [
        f"{EXAMPLES_DIRECTORY}/BfMAe6Itzgt-1.fsh",
        f"{EXAMPLES_DIRECTORY}/VBqh0ynB2wv-1.fsh",
    ]


@respx.mock
async def test_per_target_zero_disables_the_target_and_sweeps_its_directory(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    tmp_path: Path,
) -> None:
    """`per_target = 0` fetches nothing at all and deletes the examples a previous run left behind."""
    mock_system_info("v42")
    await _scaffold_project(tmp_path)
    _mock_metadata()
    await service.generate_examples(resolve_profile("probe"), load_project(tmp_path))
    await _scaffold_project(tmp_path, examples="per_target = 0")
    before = respx.calls.call_count

    report = await service.generate_examples(resolve_profile("probe"), load_project(tmp_path))

    assert respx.calls.call_count == before
    assert report.example_count == 0
    assert report.written_files == []
    assert sorted(report.deleted_files) == ["BfMAe6Itzgt-1.fsh", "VBqh0ynB2wv-1.fsh"]
    assert not list((tmp_path / "ig" / "input" / "fsh" / EXAMPLES_DIRECTORY).glob("*.fsh"))


@respx.mock
async def test_generate_all_runs_the_example_target_after_the_questionnaires(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    mock_attributes: Callable[..., None],
    tmp_path: Path,
) -> None:
    """`generate all` carries an example report whose responses answer the questionnaires it just wrote."""
    mock_system_info("v42")
    mock_attributes()
    await _scaffold_project(tmp_path)
    _mock_metadata()

    report = await service.generate_all(resolve_profile("probe"), load_project(tmp_path))

    assert report.questionnaires.questionnaire_count == 2
    assert report.examples.example_count == 2
    assert report.examples.target_directory == EXAMPLES_DIRECTORY
    fsh = tmp_path / "ig" / "input" / "fsh"
    assert (fsh / "data-sets" / "BfMAe6Itzgt.fsh").exists()
    assert (fsh / EXAMPLES_DIRECTORY / "BfMAe6Itzgt-1.fsh").exists()


def test_generate_examples_cli_renders_the_count(fhir_example_project: Path) -> None:  # noqa: ARG001
    """`d2w fhir generate examples` renders the example count from the service report."""
    from unittest.mock import AsyncMock, patch

    from dhis2w_fhir import GenerateReport

    report = GenerateReport(
        project_root=Path("/project"),
        target_directory=EXAMPLES_DIRECTORY,
        written_files=[f"{EXAMPLES_DIRECTORY}/BfMAe6Itzgt-1.fsh"],
        example_count=4,
    )
    with patch("dhis2w_fhir.service.generate_examples", new=AsyncMock(return_value=report)):
        result = _runner.invoke(build_app(), ["fhir", "generate", "examples"])

    assert result.exit_code == 0, result.output
    assert "examples" in result.output
    assert "4" in result.output


@pytest.fixture
def fhir_example_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A working directory holding a fhir.toml and a default profile for CLI tests."""
    config_dir = tmp_path / ".config" / "dhis2"
    config_dir.mkdir(parents=True)
    (config_dir / "profiles.toml").write_text(
        '\ndefault = "probe"\n\n[profiles.probe]\n'
        'base_url = "https://dhis2.example"\nauth = "pat"\ntoken = "d2p_test"\n'
    )
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_dir.parent))
    monkeypatch.delenv("DHIS2_PROFILE", raising=False)
    (tmp_path / "fhir.toml").write_text(
        '[ig]\nid = "dhis2.fhir.test"\ncanonical = "http://example.org/fhir"\nname = "Dhis2FhirTest"\n'
        'title = "DHIS2 FHIR Test IG"\npublisher = "Test Organisation"\n',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    return tmp_path


_WIDE_OPTION_SET = OptionSetIn(
    uid="Os1aaaaaaaa",
    name="Gender",
    options=[
        OptionIn(uid="Op1aaaaaaaa", code="F", name="Female", sort_order=1),
        OptionIn(uid="Op2aaaaaaaa", code="M", name="Male", sort_order=2),
        OptionIn(uid="Op3aaaaaaaa", code="O", name="Other", sort_order=3),
    ],
)

#: One data set covering the value types the synthesizer treats specially.
_WIDE_TYPES = QuestionnaireSourceIn(
    uid="Ds7aaaaaaaa",
    name="Wide types",
    kind="aggregate",
    period_type="Monthly",
    flat_items=[
        QuestionnaireItemIn(uid="Deurl000000", name="Case file link", value_type="URL"),
        QuestionnaireItemIn(uid="Deage000000", name="Age at visit", value_type="AGE"),
        QuestionnaireItemIn(uid="Decoord0000", name="Where", value_type="COORDINATE"),
        QuestionnaireItemIn(uid="Demulti0000", name="Symptoms", value_type="MULTI_TEXT", option_set_uid="Os1aaaaaaaa"),
        QuestionnaireItemIn(uid="Defile00000", name="Scan", value_type="FILE_RESOURCE"),
        QuestionnaireItemIn(uid="Deimage0000", name="Photo", value_type="IMAGE"),
        QuestionnaireItemIn(uid="Degeo000000", name="Catchment", value_type="GEOJSON"),
        QuestionnaireItemIn(uid="Deorg000000", name="Reporting unit", value_type="ORGANISATION_UNIT"),
        QuestionnaireItemIn(uid="Deref000000", name="Related object", value_type="REFERENCE"),
        QuestionnaireItemIn(uid="Detrk000000", name="Linked case", value_type="TRACKER_ASSOCIATE"),
    ],
)


def _wide_content() -> str:
    """The synthetic example for the wide-value-type fixture."""
    return _synthetic([_WIDE_TYPES], [_WIDE_OPTION_SET])[f"{EXAMPLES_DIRECTORY}/Ds7aaaaaaaa-1.fsh"]


def test_a_url_question_answers_as_a_uri_naming_the_example() -> None:
    """A synthetic URL points at the RFC 2606 `.invalid` host, so nothing resolves anywhere real."""
    assert '* item[=].answer[+].valueUri = "https://example.invalid/Ds7aaaaaaaa-example-1"' in _wide_content()


def test_an_age_question_answers_as_a_date_of_birth() -> None:
    """DHIS2 stores a date behind AGE, so the answer is a date inside the seeded birth window."""
    content = _wide_content()
    answered = re.search(r'\* item\[=\]\.answer\[\+\]\.valueDate = "(\d{4}-\d{2}-\d{2})"', content)
    assert answered is not None
    born = datetime.date.fromisoformat(answered.group(1))
    assert datetime.date(1950, 1, 1) <= born <= datetime.date(2015, 12, 31)


def test_a_coordinate_question_answers_as_the_dhis2_longitude_latitude_string() -> None:
    """COORDINATE has no R4 item type, so it stays the `[lon,lat]` string DHIS2 stores, inside real bounds."""
    content = _wide_content()
    answered = re.search(r'valueString = "\[(-?[\d.]+),(-?[\d.]+)\]"', content)
    assert answered is not None
    longitude, latitude = float(answered.group(1)), float(answered.group(2))
    assert -180 <= longitude <= 180
    assert -90 <= latitude <= 90


def test_a_multi_text_question_answers_with_two_distinct_concepts() -> None:
    """MULTI_TEXT captures several selections, so the synthetic answer repeats over distinct options."""
    content = _wide_content()
    codings = re.findall(r"\* item\[=\]\.answer\[\+\]\.valueCoding = (\S+#\S+)", content)
    assert len(codings) == 2
    assert len(set(codings)) == 2


def test_a_stored_multi_text_value_splits_into_one_coding_per_option() -> None:
    """DHIS2 stores MULTI_TEXT as comma-joined option codes, so an instance value answers once per code."""
    response = ExampleResponseIn(
        instance_id="Ds7aaaaaaaa-202606-Ou1aaaaaaaa",
        target_uid="Ds7aaaaaaaa",
        kind="aggregate",
        organisation_unit_uid="Ou1aaaaaaaa",
        status_code="completed",
        period=parse_period("202606"),
        answers=[ExampleAnswerIn(data_element_uid="Demulti0000", value="F,O")],
    )
    build = build_example_artifacts(
        [_WIDE_TYPES],
        [response],
        [_WIDE_OPTION_SET],
        GenerateConfig(),
        _CANONICAL,
        option_set_plan=_plan([_WIDE_OPTION_SET]),
    )
    content = build.artifacts[0].content
    assert '* item[=].answer[+].valueCoding = D2OS_Os1aaaaaaaa_CS#Op1aaaaaaaa "Female"' in content
    assert '* item[=].answer[+].valueCoding = D2OS_Os1aaaaaaaa_CS#Op3aaaaaaaa "Other"' in content
    assert build.notes == []


def test_unanswerable_questions_are_left_unanswered_with_one_note() -> None:
    """An invented attachment, catchment polygon, or DHIS2 object reference misrepresents the form."""
    synthetic = build_synthetic_responses([_WIDE_TYPES], [_WIDE_OPTION_SET], 1, _ROOT_ORG_UNIT, _TODAY)
    content = _wide_content()
    for uid in ("Defile00000", "Deimage0000", "Degeo000000", "Deref000000", "Detrk000000"):
        assert uid not in content
    assert synthetic.notes == [
        "5 questions take an attachment, a geometry document, or a reference to a DHIS2 object the IG does "
        "not publish; left unanswered in the synthetic examples: Catchment (Degeo000000), "
        "Linked case (Detrk000000), Photo (Deimage0000), Related object (Deref000000), Scan (Defile00000)"
    ]


def test_an_organisation_unit_question_answers_as_a_location_reference() -> None:
    """An ORGANISATION_UNIT item is `#reference` in the questionnaire, so its answer is a Reference."""
    content = _wide_content()
    assert '* item[+].linkId = "Deorg000000"' in content
    assert f"* item[=].answer[+].valueReference = Reference(Location/{_ROOT_ORG_UNIT})" in content
    assert f"* subject = Reference(Location/{_ROOT_ORG_UNIT})" in content


def test_every_location_reference_is_a_relative_reference_rather_than_an_instance_name() -> None:
    """A reference reads `Location/<uid>`, the wire form, so it stands on its own once the Locations ship as JSON."""
    content = _wide_content()
    targets = re.findall(r"Reference\((Location[^)]*)\)", content)
    assert targets
    assert all(target.startswith("Location/") for target in targets)
    assert f"Reference(Location-{_ROOT_ORG_UNIT})" not in content
    assert "Location-" not in content


def test_a_captured_organisation_unit_value_answers_as_that_units_location() -> None:
    """An instance-sourced ORGANISATION_UNIT value names the Location of the unit it stored."""
    response = ExampleResponseIn(
        instance_id="Ds7aaaaaaaa-202606-Ou1aaaaaaaa",
        target_uid="Ds7aaaaaaaa",
        kind="aggregate",
        organisation_unit_uid="Ou1aaaaaaaa",
        status_code="completed",
        period=parse_period("202606"),
        answers=[ExampleAnswerIn(data_element_uid="Deorg000000", value="Ou2aaaaaaaa")],
    )
    build = build_example_artifacts(
        [_WIDE_TYPES],
        [response],
        [_WIDE_OPTION_SET],
        GenerateConfig(),
        _CANONICAL,
        option_set_plan=_plan([_WIDE_OPTION_SET]),
    )
    assert "* item[=].answer[+].valueReference = Reference(Location/Ou2aaaaaaaa)" in build.artifacts[0].content
    assert build.notes == []


#: One category combo's option combos, deliberately not in (name, uid) order on the wire.
_SHUFFLED_OPTION_COMBOS = [
    {"id": "Cocczzzzzzz", "name": "Zebra"},
    {"id": "Cocazzzzzzz", "name": "Antelope", "code": "ANT"},
    {"id": "Cocbzzzzzzz", "name": "Marmot"},
]


def _disaggregated_payload(option_combos: list[dict[str, str]]) -> dict[str, object]:
    """One data set whose single data element disaggregates by the given option combos."""
    return {
        "dataSets": [
            {
                "id": "BfMAe6Itzgt",
                "name": "Species survey",
                "periodType": "Monthly",
                "sections": [],
                "dataSetElements": [
                    {
                        "dataElement": {
                            "id": "Deazzzzzzzz",
                            "name": "Sightings",
                            "valueType": "INTEGER",
                            "categoryCombo": {
                                "id": "CcAaBbCcDdE",
                                "name": "Species",
                                "isDefault": False,
                                "categoryOptionCombos": option_combos,
                            },
                        }
                    }
                ],
            }
        ]
    }


@respx.mock
async def test_example_answers_follow_the_questionnaires_option_combo_order(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    tmp_path: Path,
) -> None:
    """DHIS2 shuffles `categoryOptionCombos` per request (BUGS.md #64), so both fetches read one order."""
    mock_system_info("v42")
    await _scaffold_project(tmp_path)
    respx.get(f"{_HOST}/api/programs").mock(return_value=httpx.Response(200, json={"programs": []}))
    respx.get(f"{_HOST}/api/optionSets").mock(return_value=httpx.Response(200, json={"optionSets": []}))
    respx.get(f"{_HOST}/api/organisationUnits").mock(return_value=httpx.Response(200, json=_ROOT_PAYLOAD))
    respx.get(f"{_HOST}/api/dataSets").mock(
        return_value=httpx.Response(200, json=_disaggregated_payload(_SHUFFLED_OPTION_COMBOS))
    )
    await service.generate_examples(resolve_profile("probe"), load_project(tmp_path))
    example = tmp_path / "ig" / "input" / "fsh" / EXAMPLES_DIRECTORY / "BfMAe6Itzgt-1.fsh"
    first = example.read_text(encoding="utf-8")
    respx.get(f"{_HOST}/api/dataSets").mock(
        return_value=httpx.Response(200, json=_disaggregated_payload(_SHUFFLED_OPTION_COMBOS[::-1]))
    )

    report = await service.generate_examples(resolve_profile("probe"), load_project(tmp_path))

    assert report.written_files == []
    assert example.read_text(encoding="utf-8") == first
    assert first.index("Cocazzzzzzz") < first.index("Cocbzzzzzzz") < first.index("Cocczzzzzzz")


def _answered(data_element_uid: str, value: str) -> str:
    """The FSH of one hand-built data-set response answering a single question."""
    response = _aggregate_response([ExampleAnswerIn(data_element_uid=data_element_uid, value=value)])
    build = build_example_artifacts(
        [_DATA_SET], [response], _OPTION_SETS, GenerateConfig(), _CANONICAL, option_set_plan=_plan(_OPTION_SETS)
    )
    return build.artifacts[0].content


@pytest.mark.parametrize(
    ("value", "literal"),
    [
        ("-3", "-3"),
        ("0", "0"),
        ("19.5", "19.5"),
        ("0.25", "0.25"),
        ("12.50", "12.50"),
    ],
)
def test_a_plain_decimal_is_answered_at_its_stored_precision(value: str, literal: str) -> None:
    """An R4 decimal is written unquoted, so a stored value that already is one is carried through verbatim."""
    assert f"* item[=].item[=].answer[+].valueDecimal = {literal}" in _answered("De4aaaaaaaa", value)


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity", "1e3", "+1", "01.5", "1_0", ".5", "5."])
def test_a_decimal_form_r4_cannot_carry_is_answered_as_a_string(value: str) -> None:
    """`float()` reads all of these; none of them is a decimal literal FHIR admits, so they stay text."""
    content = _answered("De4aaaaaaaa", value)
    assert f'* item[=].item[=].answer[+].valueString = "{value}"' in content
    assert "valueDecimal" not in content


@pytest.mark.parametrize(("value", "literal"), [("-3", "-3"), ("0", "0"), ("42", "42")])
def test_a_plain_integer_is_answered_as_a_number(value: str, literal: str) -> None:
    """A stored integer answers as one, in the canonical form."""
    assert f"* item[=].item[=].answer[+].valueInteger = {literal}" in _answered("De1aaaaaaaa", value)


@pytest.mark.parametrize("value", ["1_0", "+1", "01", " 1 0", "1e3", "NaN", "19.5"])
def test_an_integer_form_r4_cannot_carry_is_answered_as_a_string(value: str) -> None:
    """`int()` reads underscores and edge whitespace as digits, which is not a lexical form FHIR admits."""
    content = _answered("De1aaaaaaaa", value)
    assert "valueInteger" not in content
    assert "answer[+].valueString" in content


@pytest.mark.parametrize(
    ("value", "valid"),
    [
        ("2026", True),
        ("2026-12", True),
        ("2026-02-28", True),
        ("2024-02-29", True),
        ("2026-13", False),
        ("2026-00", False),
        ("2026-02-30", False),
        ("2026-99-99", False),
        ("26-01-01", False),
    ],
)
def test_an_r4_date_must_be_a_real_date(value: str, valid: bool) -> None:
    """The lexical shape is not enough: a date answer names a day the calendar actually has."""
    assert _is_fhir_date(value) is valid


@pytest.mark.parametrize(
    ("value", "valid"),
    [
        ("23:59:59", True),
        ("00:00:00", True),
        ("12:00:00.500", True),
        ("24:00:00", False),
        ("25:99:99", False),
        ("12:60:00", False),
    ],
)
def test_an_r4_time_must_be_a_real_time(value: str, valid: bool) -> None:
    """The lexical shape is not enough: a time answer names a reading the clock actually shows."""
    assert _is_fhir_time(value) is valid


@pytest.mark.parametrize(
    ("value", "valid"),
    [
        ("2026", True),
        ("2026-12", True),
        ("2026-01-01", True),
        ("2026-01-01T12:00:00Z", True),
        ("2026-01-01T12:00:00.000Z", True),
        ("2026-01-01T12:00:00+14:00", True),
        ("2026-01-01T12:00:00-12:00", True),
        ("2026-13", False),
        ("2026-02-30", False),
        ("2026-99-99", False),
        ("2026-99-99T25:99:99+99:00", False),
        ("2026-01-01T25:00:00Z", False),
        ("2026-01-01T12:00:00+99:00", False),
        ("2026-01-01T12:00:00+14:30", False),
        ("2026-01-01T12:00:00-13:00", False),
    ],
)
def test_an_r4_date_time_must_be_a_real_instant_in_a_real_zone(value: str, valid: bool) -> None:
    """A dateTime clears the calendar, the clock, and an offset no zone on earth sits outside of."""
    assert _is_fhir_date_time(value) is valid


def test_an_occurrence_in_an_impossible_zone_is_dropped_with_a_note() -> None:
    """An offset outside the inhabited range is no dateTime, so the occurrence is omitted rather than emitted."""
    response = ExampleResponseIn(
        instance_id="Ev1aaaaaaaa",
        target_uid="VBqh0ynB2wv",
        kind="event",
        organisation_unit_uid="Ou1aaaaaaaa",
        status_code="completed",
        authored="2026-01-01T12:00:00+14:30",
    )
    build = build_example_artifacts(
        [_EVENT_PROGRAM], [response], _OPTION_SETS, GenerateConfig(), _CANONICAL, option_set_plan=_plan(_OPTION_SETS)
    )
    assert "* authored" not in build.artifacts[0].content
    assert any("base QuestionnaireResponse declared" in note for note in build.notes)
