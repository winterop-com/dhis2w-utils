"""Tests for the example target: synthetic and instance-sourced QuestionnaireResponses.

The synthetic goldens are full-text assertions. They can be, because the values are seeded
from a SHA-256 of the target UID rather than from `hash()` - the only thing that moves with
the calendar is the reporting period the example is anchored to, which the fixtures pin by
passing an explicit `today`.
"""

from __future__ import annotations

import datetime
import random
import re
from collections.abc import Callable
from copy import deepcopy
from pathlib import Path
from typing import Any

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
    response_status_code,
    synthetic_uid,
)
from dhis2w_fhir.resources.examples.schemas import ExampleAnswerIn, ExampleResponseIn
from dhis2w_fhir.resources.option_sets import option_set_identities
from dhis2w_fhir.resources.option_sets.schemas import OptionIn, OptionSetIdentityPlan, OptionSetIn
from dhis2w_fhir.resources.questionnaires.schemas import (
    CategoryComboIn,
    CategoryOptionComboIn,
    ProgramContextIn,
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

_CHILD_PROGRAMME = ProgramContextIn(uid="IpHINAT79UW", name="Child Programme")

_BIRTH_STAGE = QuestionnaireSourceIn(
    uid="A03MvHHogjR",
    name="Birth",
    code="PS_BIRTH",
    kind="tracker-event",
    program=_CHILD_PROGRAMME,
    sections=[
        QuestionnaireSectionIn(
            uid="Sec3aaaaaaa",
            name="Delivery",
            items=[QuestionnaireItemIn(uid="a3kGcGDCuk6", name="Apgar Score", value_type="INTEGER", compulsory=True)],
        )
    ],
    flat_items=[QuestionnaireItemIn(uid="De9aaaaaaaa", name="Seen at", value_type="DATETIME")],
)

_CHILD_REGISTRATION = QuestionnaireSourceIn(
    uid="IpHINAT79UW",
    name="Child Programme",
    code="PR_CHILD",
    kind="tracker",
    tracked_entity_type_uid="nEenWmSyUEp",
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
        QuestionnaireItemIn(uid="Tea2aaaaaaa", name="Date of birth", value_type="DATE"),
    ],
)

#: The same program with `displayIncidentDate` off, which is what makes D2IncidentAt disappear.
_CHILD_REGISTRATION_WITHOUT_INCIDENT = _CHILD_REGISTRATION.model_copy(update={"displays_incident_date": False})

_REFERRAL_PROGRAM = QuestionnaireSourceIn(
    uid="Pr1aaaaaaaa",
    name="Referral",
    kind="event",
    flat_items=[
        QuestionnaireItemIn(uid="Dea1aaaaaaa", name="Referred to", value_type="ORGANISATION_UNIT"),
        QuestionnaireItemIn(uid="Deb1aaaaaaa", name="Seen at", value_type="DATETIME"),
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

_SYNTHETIC_REGISTRATION_GOLDEN = (
    """Instance: QuestionnaireResponse-IpHINAT79UW-example-1
InstanceOf: D2TrackerRegistrationResponse
Title: "Example response - Child Programme"
Description: "Example QuestionnaireResponse against the DHIS2 tracker program registration """
    """Child Programme (IpHINAT79UW)."
Usage: #example
* id = "IpHINAT79UW-example-1"
* extension[D2FormType].valueCode = #tracker
* extension[D2TrackerEnrollment].valueIdentifier.system = $DHIS2-TRACKER-ENROLLMENT
* extension[D2TrackerEnrollment].valueIdentifier.value = "jvImhO30zrp"
* extension[D2OrganisationUnit].valueReference = Reference(Location/ImspTQPwCqd)
* extension[D2EnrolledAt].valueDateTime = "2026-07-15T08:00:00Z"
* extension[D2IncidentAt].valueDateTime = "2026-07-11T09:00:00Z"
* questionnaire = "http://example.org/fhir/Questionnaire/IpHINAT79UW"
* status = #completed
* subject.type = "Patient"
* subject.identifier.system = $DHIS2-TE
* subject.identifier.value = "ByaTNM2MoVs"
* authored = "2026-07-08T22:00:00Z"
* item[+].linkId = "Tea1aaaaaaa"
* item[=].answer[+].valueString = "National identifier ByaTNM2MoVs"
* item[+].linkId = "Tea2aaaaaaa"
* item[=].answer[+].valueDate = "2026-07-22"
"""
)

_SYNTHETIC_TRACKER_EVENT_GOLDEN = (
    """Instance: QuestionnaireResponse-A03MvHHogjR-example-1
InstanceOf: D2TrackerEventResponse
Title: "Example response - Child Programme - Birth"
Description: "Example QuestionnaireResponse against the DHIS2 tracker program stage """
    """Child Programme - Birth (A03MvHHogjR)."
Usage: #example
* id = "A03MvHHogjR-example-1"
* extension[D2FormType].valueCode = #tracker-event
* extension[D2TrackerEnrollment].valueIdentifier.system = $DHIS2-TRACKER-ENROLLMENT
* extension[D2TrackerEnrollment].valueIdentifier.value = "VJV3arKomV0"
* extension[D2OrganisationUnit].valueReference = Reference(Location/ImspTQPwCqd)
* questionnaire = "http://example.org/fhir/Questionnaire/A03MvHHogjR"
* status = #completed
* subject.type = "Patient"
* subject.identifier.system = $DHIS2-TE
* subject.identifier.value = "yhpvt4pX4xD"
* authored = "2026-07-30T12:00:00Z"
* item[+].linkId = "Sec3aaaaaaa"
* item[=].item[+].linkId = "a3kGcGDCuk6"
* item[=].item[=].answer[+].valueInteger = 238
* item[+].linkId = "De9aaaaaaaa"
* item[=].answer[+].valueDateTime = "2026-07-24T13:00:00Z"
"""
)

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

#: The one tracker program the instance-sourced tracker tests generate from: one stage, one question.
_TRACKER_PROGRAMS_PAYLOAD = {
    "programs": [
        {
            "id": "IpHINAT79UW",
            "name": "Child Programme",
            "programType": "WITH_REGISTRATION",
            "trackedEntityType": {"id": "nEenWmSyUEp"},
            "displayIncidentDate": True,
            "programTrackedEntityAttributes": [
                {
                    "mandatory": True,
                    "sortOrder": 1,
                    "trackedEntityAttribute": {
                        "id": "w75KJ2mc4zz",
                        "name": "First name",
                        "code": "first-name",
                        "valueType": "TEXT",
                        "unique": False,
                    },
                }
            ],
            "programStages": [
                {
                    "id": "A03MvHHogjR",
                    "name": "Birth",
                    "sortOrder": 1,
                    "programStageSections": [],
                    "programStageDataElements": [
                        {
                            "compulsory": True,
                            "sortOrder": 1,
                            "dataElement": {"id": "a3kGcGDCuk6", "name": "Apgar Score", "valueType": "INTEGER"},
                        }
                    ],
                }
            ],
        }
    ]
}

#: One person enrolled in that program, as `/api/tracker/trackedEntities?program=...` answers it.
_TRACKED_ENTITY = {
    "trackedEntity": "Te1aaaaaaaa",
    "attributes": [{"attribute": "w75KJ2mc4zz", "value": "Amara"}],
    "enrollments": [
        {
            "enrollment": "En1aaaaaaaa",
            "enrolledAt": "2026-07-01T09:00:00.000",
            "occurredAt": "2026-06-28T00:00:00.000",
            "orgUnit": "Ou1aaaaaaaa",
            "program": "IpHINAT79UW",
        }
    ],
}

#: One event of that stage, as `/api/tracker/events?programStage=...` answers it.
_TRACKER_EVENT = {
    "event": "Ev2aaaaaaaa",
    "orgUnit": "Ou1aaaaaaaa",
    "occurredAt": "2026-07-15T10:30:00.000",
    "status": "COMPLETED",
    "enrollment": "En1aaaaaaaa",
    "trackedEntity": "Te1aaaaaaaa",
    "dataValues": [{"dataElement": "a3kGcGDCuk6", "value": "9"}],
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


def _referral_response(answers: list[ExampleAnswerIn], authored: str | None = None) -> ExampleResponseIn:
    """One hand-built event response against the referral program, carrying whatever `authored` a test needs."""
    return ExampleResponseIn(
        instance_id="Pr1aaaaaaaa-202606-Ou1aaaaaaaa",
        target_uid="Pr1aaaaaaaa",
        kind="event",
        organisation_unit_uid="Ou1aaaaaaaa",
        status_code="completed",
        authored=authored,
        answers=answers,
    )


def _referral_build(
    response: ExampleResponseIn,
    config: GenerateConfig | None = None,
    published_organisation_unit_uids: frozenset[str] | None = None,
) -> tuple[str, list[str]]:
    """Emit one referral example and hand back its FSH content plus the notes the run raised."""
    resolved = config or GenerateConfig()
    build = build_example_artifacts(
        [_REFERRAL_PROGRAM],
        [response],
        [],
        resolved,
        _CANONICAL,
        option_set_plan=_plan([], resolved),
        published_organisation_unit_uids=published_organisation_unit_uids,
    )
    return build.artifacts[0].content, [note.message for note in build.notes]


def test_a_zoneless_timestamp_is_read_as_utc_when_the_project_names_no_zone() -> None:
    """The default keeps BUGS.md #62's UTC assumption, which is what every committed golden was emitted under."""
    content, notes = _referral_build(
        _referral_response(
            [ExampleAnswerIn(data_element_uid="Deb1aaaaaaa", value="2026-07-15T08:30:00.000")],
            authored="2026-07-15T08:30:00.000",
        )
    )
    assert '* authored = "2026-07-15T08:30:00.000Z"' in content
    assert '* item[=].answer[+].valueDateTime = "2026-07-15T08:30:00.000Z"' in content
    assert notes == []


@pytest.mark.parametrize(
    ("stored", "expected"),
    [
        ("2026-07-15T08:30:00.000", "2026-07-15T08:30:00.000+02:00"),
        ("2026-01-15T08:30:00.000", "2026-01-15T08:30:00.000+01:00"),
    ],
)
def test_a_configured_timezone_stamps_authored_and_datetime_answers_alike(stored: str, expected: str) -> None:
    """`[generate] timezone` names what the instance's wall clock means, and DST moves the offset with the date."""
    content, notes = _referral_build(
        _referral_response([ExampleAnswerIn(data_element_uid="Deb1aaaaaaa", value=stored)], authored=stored),
        GenerateConfig(timezone="Europe/Oslo"),
    )
    assert f'* authored = "{expected}"' in content
    assert f'* item[=].answer[+].valueDateTime = "{expected}"' in content
    assert notes == []


def test_an_organisation_unit_answer_is_emitted_when_the_selection_is_unknown_or_holds_it() -> None:
    """Without a published selection the answer is emitted unchecked; a selection holding it changes nothing."""
    response = _referral_response([ExampleAnswerIn(data_element_uid="Dea1aaaaaaa", value="Ou2aaaaaaaa")])
    unchecked, unchecked_notes = _referral_build(response)
    checked, checked_notes = _referral_build(response, published_organisation_unit_uids=frozenset({"Ou2aaaaaaaa"}))
    assert "* item[=].answer[+].valueReference = Reference(Location/Ou2aaaaaaaa)" in unchecked
    assert unchecked == checked
    assert unchecked_notes == checked_notes == []


def test_an_organisation_unit_answer_outside_the_selection_is_left_unanswered_with_a_note() -> None:
    """The IG publishes no Location for an unselected unit, so the answer would dangle; it is dropped and counted."""
    content, notes = _referral_build(
        _referral_response([ExampleAnswerIn(data_element_uid="Dea1aaaaaaa", value="Ou9aaaaaaaa")]),
        published_organisation_unit_uids=frozenset({"Ou1aaaaaaaa", "Ou2aaaaaaaa"}),
    )
    assert "Ou9aaaaaaaa" not in content
    assert "Dea1aaaaaaa" not in content
    assert notes == [
        "1 example answer references an organisation unit outside the org-unit selection, which the IG "
        "publishes no Location for; left unanswered: Referred to (Dea1aaaaaaa) = Ou9aaaaaaaa"
    ]


def test_synthetic_data_set_example_is_a_stable_golden() -> None:
    """A sectioned, disaggregated, option-set-bound data set answers every question deterministically."""
    assert _synthetic([_DATA_SET])[f"{EXAMPLES_DIRECTORY}/BfMAe6Itzgt-1.fsh"] == _SYNTHETIC_DATA_SET_GOLDEN


def test_synthetic_event_example_is_a_stable_golden() -> None:
    """An event program carries `authored` and no D2Period, and answers its flat questions."""
    assert _synthetic([_EVENT_PROGRAM])[f"{EXAMPLES_DIRECTORY}/VBqh0ynB2wv-1.fsh"] == _SYNTHETIC_EVENT_GOLDEN


def test_synthetic_registration_example_carries_the_whole_enrollment_envelope() -> None:
    """A registration mints both identities it creates, dates the enrollment, and answers its attributes."""
    artifacts = _synthetic([_CHILD_REGISTRATION], [])
    assert artifacts[f"{EXAMPLES_DIRECTORY}/IpHINAT79UW-1.fsh"] == _SYNTHETIC_REGISTRATION_GOLDEN


def test_synthetic_registration_identifiers_are_dhis2_shaped_and_distinct() -> None:
    """Both minted UIDs are the eleven characters DHIS2 accepts, and the person is not the enrollment."""
    build = build_synthetic_responses([_CHILD_REGISTRATION], [], 1, _ROOT_ORG_UNIT, _TODAY)
    response = build.responses[0]
    assert response.tracked_entity_uid is not None
    assert response.enrollment_uid is not None
    assert response.tracked_entity_uid != response.enrollment_uid
    for uid in (response.tracked_entity_uid, response.enrollment_uid):
        assert len(uid) == 11
        assert uid[0].isalpha()
        assert uid.isalnum()


def test_a_program_that_collects_no_incident_date_says_so_by_carrying_none() -> None:
    """D2IncidentAt is 0..1 because a DHIS2 program states whether it collects one at all."""
    content = _synthetic([_CHILD_REGISTRATION_WITHOUT_INCIDENT], [])[f"{EXAMPLES_DIRECTORY}/IpHINAT79UW-1.fsh"]
    assert "D2EnrolledAt" in content
    assert "D2IncidentAt" not in content


def test_synthetic_tracker_event_example_is_a_stable_golden() -> None:
    """A tracker program stage carries its enrollment, its org unit, and a tracked-entity subject."""
    artifacts = _synthetic([_BIRTH_STAGE], [])
    assert artifacts[f"{EXAMPLES_DIRECTORY}/A03MvHHogjR-1.fsh"] == _SYNTHETIC_TRACKER_EVENT_GOLDEN


def test_synthetic_tracker_event_values_are_stable_across_runs() -> None:
    """The tracked entity and the enrollment are drawn from the seeded RNG, so two builds agree."""
    assert _synthetic([_BIRTH_STAGE], []) == _synthetic([_BIRTH_STAGE], [])


def test_a_tracker_event_example_carries_no_reporting_period() -> None:
    """A tracker event happens at a moment, so it carries `authored` and no D2Period."""
    content = _synthetic([_BIRTH_STAGE], [])[f"{EXAMPLES_DIRECTORY}/A03MvHHogjR-1.fsh"]
    assert "D2Period" not in content
    assert "* authored = " in content


def test_a_tracker_event_example_names_its_subject_by_identifier_alone() -> None:
    """This guide publishes no Patient, so the subject is a logical reference rather than a Reference()."""
    content = _synthetic([_BIRTH_STAGE], [])[f"{EXAMPLES_DIRECTORY}/A03MvHHogjR-1.fsh"]
    assert '* subject.type = "Patient"' in content
    assert "* subject.identifier.system = $DHIS2-TE" in content
    assert "* subject.identifier.value = " in content
    assert "Reference(Patient" not in content
    assert "* subject = Reference(" not in content


def test_a_tracker_event_example_titles_itself_under_both_identities() -> None:
    """A stage name means little alone, so the example names the program the stage belongs to."""
    content = _synthetic([_BIRTH_STAGE], [])[f"{EXAMPLES_DIRECTORY}/A03MvHHogjR-1.fsh"]
    assert 'Title: "Example response - Child Programme - Birth"' in content
    assert "DHIS2 tracker program stage Child Programme - Birth (A03MvHHogjR)" in content


def test_a_synthetic_uid_has_the_shape_dhis2_gives_one() -> None:
    """A DHIS2 UID opens on a letter and runs to eleven alphanumeric places."""
    generator = random.Random(0)  # noqa: S311 - a test fixture, not a secret
    drawn = [synthetic_uid(generator) for _ in range(50)]
    for uid in drawn:
        assert len(uid) == 11
        assert uid[0].isascii() and uid[0].isalpha()
        assert uid.isalnum()
        assert uid.isascii()
    assert len(set(drawn)) == len(drawn)


def test_a_tracker_event_without_an_enrollment_declares_the_base_resource_with_a_note() -> None:
    """The enrollment is 1..1 on the profile, so an example missing it degrades rather than fails to validate."""
    response = ExampleResponseIn(
        instance_id="Ev1aaaaaaaa",
        target_uid="A03MvHHogjR",
        kind="tracker-event",
        organisation_unit_uid="Ou1aaaaaaaa",
        status_code="completed",
        authored="2026-07-15T10:30:00Z",
        tracked_entity_uid="Te1aaaaaaaa",
    )
    build = build_example_artifacts(
        [_BIRTH_STAGE], [response], _OPTION_SETS, GenerateConfig(), _CANONICAL, option_set_plan=_plan(_OPTION_SETS)
    )
    content = build.artifacts[0].content
    assert "InstanceOf: QuestionnaireResponse\n" in content
    assert "InstanceOf: D2TrackerEventResponse" not in content
    assert "D2TrackerEnrollment" not in content
    assert "* extension[D2OrganisationUnit].valueReference = Reference(Location/Ou1aaaaaaaa)" in content
    assert '* subject.identifier.value = "Te1aaaaaaaa"' in content
    assert [note.message for note in build.notes] == [
        "1 example lacks the enrollment or tracked entity a tracker event carries; the base "
        "QuestionnaireResponse is declared instead of the tracker event response profile: Ev1aaaaaaaa"
    ]


def test_each_example_declares_the_response_profile_of_its_form_kind() -> None:
    """An example is a contract check: it declares the profile its form kind's responses have to meet."""
    artifacts = _synthetic([_DATA_SET, _EVENT_PROGRAM, _BIRTH_STAGE])
    assert "InstanceOf: D2AggregateResponse" in artifacts[f"{EXAMPLES_DIRECTORY}/BfMAe6Itzgt-1.fsh"]
    assert "InstanceOf: D2EventResponse" in artifacts[f"{EXAMPLES_DIRECTORY}/VBqh0ynB2wv-1.fsh"]
    assert "InstanceOf: D2TrackerEventResponse" in artifacts[f"{EXAMPLES_DIRECTORY}/A03MvHHogjR-1.fsh"]
    assert not any("InstanceOf: QuestionnaireResponse" in content for content in artifacts.values())


def test_the_declared_response_profile_follows_the_naming_prefix() -> None:
    """A renamed prefix renames the profiles, so the examples have to follow it or stop validating."""
    config = GenerateConfig(naming=NamingConfig(prefix="Dhis2"))
    artifacts = _synthetic([_DATA_SET, _EVENT_PROGRAM, _BIRTH_STAGE], config=config)
    assert "InstanceOf: Dhis2AggregateResponse" in artifacts[f"{EXAMPLES_DIRECTORY}/BfMAe6Itzgt-1.fsh"]
    assert "InstanceOf: Dhis2EventResponse" in artifacts[f"{EXAMPLES_DIRECTORY}/VBqh0ynB2wv-1.fsh"]
    stage = artifacts[f"{EXAMPLES_DIRECTORY}/A03MvHHogjR-1.fsh"]
    assert "InstanceOf: Dhis2TrackerEventResponse" in stage
    assert "* extension[Dhis2TrackerEnrollment].valueIdentifier.system = $DHIS2-TRACKER-ENROLLMENT" in stage
    assert "* extension[Dhis2OrganisationUnit].valueReference = Reference(Location/ImspTQPwCqd)" in stage


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


def test_an_event_question_answers_flat_however_its_data_element_is_categorised() -> None:
    """An event data value carries no category option combo on the DHIS2 wire, so its form asks - and
    its example answers - the flat `<deUid>` alone. A cell `linkId` here would be an example no
    conformant server accepts, because the questionnaire the response names never defines it."""
    categorised = _EVENT_PROGRAM.model_copy(
        update={
            "flat_items": [
                QuestionnaireItemIn(
                    uid="De2aaaaaaaa", name="Measles doses given", value_type="INTEGER", category_combo=_AGE_COMBO
                )
            ]
        }
    )
    content = _synthetic([categorised])[f"{EXAMPLES_DIRECTORY}/VBqh0ynB2wv-1.fsh"]
    assert '* item[+].linkId = "De2aaaaaaaa"' in content
    assert "Coc1aaaaaaa" not in content
    assert "Coc2aaaaaaa" not in content
    assert content.count("answer[+].valueInteger = ") == 1


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
    assert [note.message for note in build.notes] == []


def test_an_unmappable_option_value_falls_back_to_a_string_with_one_note() -> None:
    """A stored value no option carries is answered as a string, and the run says how many did that."""
    response = _aggregate_response([ExampleAnswerIn(data_element_uid="De3aaaaaaaa", value="X")])
    build = build_example_artifacts(
        [_DATA_SET], [response], _OPTION_SETS, GenerateConfig(), _CANONICAL, option_set_plan=_plan(_OPTION_SETS)
    )
    assert '* item[=].item[=].answer[+].valueString = "X"' in build.artifacts[0].content
    assert [note.message for note in build.notes] == [
        "1 example answer could not be cast to the declared FHIR type; answered as text: Gender (De3aaaaaaaa) = 'X'"
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
    assert [note.message for note in build.notes] == [
        "1 captured value references a data element the questionnaire does not ask for; skipped: "
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
    assert any("base QuestionnaireResponse declared" in note.message for note in build.notes)


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
    assert any(
        "base QuestionnaireResponse instead of the aggregate response profile" in note.message for note in build.notes
    )


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
    respx.get(f"{_HOST}/api/programRules").mock(return_value=httpx.Response(200, json={"programRules": []}))
    respx.get(f"{_HOST}/api/trackedEntityTypes").mock(return_value=httpx.Response(200, json={"trackedEntityTypes": []}))
    respx.get(f"{_HOST}/api/optionSets").mock(return_value=httpx.Response(200, json=_OPTION_SETS_PAYLOAD))
    respx.get(f"{_HOST}/api/categories").mock(return_value=httpx.Response(200, json={"categories": []}))
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
    assert any("Dexaaaaaaaa" in note.message for note in report.notes)


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


async def _scaffold_tracker_project(directory: Path, **generate_lines: str) -> None:
    """Scaffold a project selecting nothing, so every form the mocked instance answers is a target."""
    options = InitOptions(
        ig_id="dhis2.fhir.tracker.examples",
        canonical=_CANONICAL,
        name="Dhis2FhirTrackerExamples",
        title="Tracker Example IG",
        publisher="Example Org",
    )
    await service.init_project(directory, options)
    config_path = directory / "fhir.toml"
    body = config_path.read_text(encoding="utf-8")
    for table, entries in generate_lines.items():
        body += f"\n[generate.{table}]\n{entries}\n"
    config_path.write_text(body, encoding="utf-8")


def _mock_tracker_metadata() -> None:
    """Mock the metadata a tracker-only run reads: no data sets, one tracker program, the root org unit."""
    respx.get(f"{_HOST}/api/dataSets").mock(return_value=httpx.Response(200, json={"dataSets": []}))
    respx.get(f"{_HOST}/api/programs").mock(return_value=httpx.Response(200, json=_TRACKER_PROGRAMS_PAYLOAD))
    respx.get(f"{_HOST}/api/programRules").mock(return_value=httpx.Response(200, json={"programRules": []}))
    respx.get(f"{_HOST}/api/trackedEntityTypes").mock(return_value=httpx.Response(200, json={"trackedEntityTypes": []}))
    respx.get(f"{_HOST}/api/optionSets").mock(return_value=httpx.Response(200, json=_OPTION_SETS_PAYLOAD))
    respx.get(f"{_HOST}/api/organisationUnits").mock(return_value=httpx.Response(200, json=_ROOT_PAYLOAD))


def _mock_tracked_entities(entities: list[dict[str, object]] | None = None) -> respx.Route:
    """Mock `/api/tracker/trackedEntities`, which the program's registration form reads its examples from."""
    return respx.get(f"{_HOST}/api/tracker/trackedEntities").mock(
        return_value=httpx.Response(200, json={"instances": [_TRACKED_ENTITY] if entities is None else entities})
    )


@respx.mock
async def test_instance_mode_reads_a_stages_events_by_program_stage(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    tmp_path: Path,
) -> None:
    """A stage's events are selected by `program` plus `programStage` - DHIS2 requires both (BUGS.md #67)."""
    mock_system_info("v42")
    await _scaffold_tracker_project(tmp_path, examples='per_target = 1\nsource = "instance"')
    _mock_tracker_metadata()
    _mock_tracked_entities()
    events = respx.get(f"{_HOST}/api/tracker/events").mock(
        return_value=httpx.Response(200, json={"instances": [_TRACKER_EVENT]})
    )

    report = await service.generate_examples(resolve_profile("probe"), load_project(tmp_path))

    params = events.calls.last.request.url.params
    assert params["programStage"] == "A03MvHHogjR"
    assert params["program"] == "IpHINAT79UW"
    assert params["fields"] == (
        "event,orgUnit,occurredAt,status,enrollment,trackedEntity,dataValues[dataElement,value]"
    )
    assert report.example_count == 2
    assert [note.message for note in report.notes] == []
    content = (tmp_path / "ig" / "input" / "fsh" / EXAMPLES_DIRECTORY / "A03MvHHogjR-1.fsh").read_text(encoding="utf-8")
    assert "Instance: QuestionnaireResponse-Ev2aaaaaaaa" in content
    assert "InstanceOf: D2TrackerEventResponse" in content
    assert '* extension[D2TrackerEnrollment].valueIdentifier.value = "En1aaaaaaaa"' in content
    assert "* extension[D2OrganisationUnit].valueReference = Reference(Location/Ou1aaaaaaaa)" in content
    assert '* subject.identifier.value = "Te1aaaaaaaa"' in content
    assert '* authored = "2026-07-15T10:30:00.000Z"' in content
    assert '* item[+].linkId = "a3kGcGDCuk6"' in content
    assert "* item[=].answer[+].valueInteger = 9" in content


@respx.mock
async def test_instance_mode_reads_a_registration_from_the_people_the_program_enrolled(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    tmp_path: Path,
) -> None:
    """A registration example is one enrollment: the person's attribute values plus the dates the enrollment holds."""
    mock_system_info("v42")
    await _scaffold_tracker_project(tmp_path, examples='per_target = 1\nsource = "instance"')
    _mock_tracker_metadata()
    tracked_entities = _mock_tracked_entities()
    respx.get(f"{_HOST}/api/tracker/events").mock(return_value=httpx.Response(200, json={"instances": []}))

    await service.generate_examples(resolve_profile("probe"), load_project(tmp_path))

    params = tracked_entities.calls.last.request.url.params
    assert params["program"] == "IpHINAT79UW"
    assert params["fields"] == (
        "trackedEntity,attributes[attribute,value],enrollments[enrollment,enrolledAt,occurredAt,orgUnit,program]"
    )
    content = (tmp_path / "ig" / "input" / "fsh" / EXAMPLES_DIRECTORY / "IpHINAT79UW-1.fsh").read_text(encoding="utf-8")
    assert "Instance: QuestionnaireResponse-En1aaaaaaaa" in content
    assert "InstanceOf: D2TrackerRegistrationResponse" in content
    assert "* extension[D2FormType].valueCode = #tracker" in content
    assert '* extension[D2TrackerEnrollment].valueIdentifier.value = "En1aaaaaaaa"' in content
    assert "* extension[D2OrganisationUnit].valueReference = Reference(Location/Ou1aaaaaaaa)" in content
    assert '* extension[D2EnrolledAt].valueDateTime = "2026-07-01T09:00:00.000Z"' in content
    assert '* extension[D2IncidentAt].valueDateTime = "2026-06-28T00:00:00.000Z"' in content
    assert '* subject.identifier.value = "Te1aaaaaaaa"' in content
    assert '* item[+].linkId = "w75KJ2mc4zz"' in content
    assert '* item[=].answer[+].valueString = "Amara"' in content


@respx.mock
async def test_a_stage_event_missing_its_enrollment_degrades_to_the_base_resource(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    tmp_path: Path,
) -> None:
    """An event the instance answered no enrollment for still publishes, as the base resource with one note."""
    mock_system_info("v42")
    await _scaffold_tracker_project(tmp_path, examples='per_target = 1\nsource = "instance"')
    _mock_tracker_metadata()
    _mock_tracked_entities([])
    without_enrollment = {key: value for key, value in _TRACKER_EVENT.items() if key != "enrollment"}
    respx.get(f"{_HOST}/api/tracker/events").mock(
        return_value=httpx.Response(200, json={"instances": [without_enrollment]})
    )

    report = await service.generate_examples(resolve_profile("probe"), load_project(tmp_path))

    assert report.example_count == 1
    assert [note.message for note in report.notes] == [
        "1 questionnaire targets hold no data on the instance; no examples emitted: Child Programme (IpHINAT79UW)",
        "1 example lacks the enrollment or tracked entity a tracker event carries; the base "
        "QuestionnaireResponse is declared instead of the tracker event response profile: Ev2aaaaaaaa",
    ]
    content = (tmp_path / "ig" / "input" / "fsh" / EXAMPLES_DIRECTORY / "A03MvHHogjR-1.fsh").read_text(encoding="utf-8")
    assert "InstanceOf: QuestionnaireResponse\n" in content
    assert "D2TrackerEnrollment" not in content
    assert '* subject.identifier.value = "Te1aaaaaaaa"' in content


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
    assert [note.message for note in report.notes] == [
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
async def test_the_solo_target_reads_the_registry_selection_the_location_guard_checks_against(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    tmp_path: Path,
) -> None:
    """`generate examples` on its own reads the id/code/name selection, under the registry's own filters.

    The light read carries exactly what identity-stem resolution consumes, so the Location guard
    and the stem map come out of one request instead of a second hierarchy walk.
    """
    mock_system_info("v42")
    await _scaffold_project(tmp_path, organisation_units="max_level = 2")
    organisation_units = respx.get(f"{_HOST}/api/organisationUnits", name="organisationUnits").mock(
        return_value=httpx.Response(200, json=_ROOT_PAYLOAD)
    )
    respx.get(f"{_HOST}/api/dataSets").mock(return_value=httpx.Response(200, json=_DATA_SETS_PAYLOAD))
    respx.get(f"{_HOST}/api/programs").mock(return_value=httpx.Response(200, json=_PROGRAMS_PAYLOAD))
    respx.get(f"{_HOST}/api/programRules").mock(return_value=httpx.Response(200, json={"programRules": []}))
    respx.get(f"{_HOST}/api/trackedEntityTypes").mock(return_value=httpx.Response(200, json={"trackedEntityTypes": []}))
    respx.get(f"{_HOST}/api/optionSets").mock(return_value=httpx.Response(200, json=_OPTION_SETS_PAYLOAD))

    await service.generate_examples(resolve_profile("probe"), load_project(tmp_path))

    selection = [
        call.request.url.params
        for call in organisation_units.calls
        if call.request.url.params.get("filter") == "level:le:2"
    ]
    assert len(selection) == 1
    assert selection[0]["fields"] == "id,code,name"
    assert selection[0]["paging"] == "false"


@respx.mock
async def test_a_form_the_questionnaire_target_refused_gets_no_example(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    mock_attributes: Callable[..., None],
    tmp_path: Path,
) -> None:
    """A linkId collision skips the whole form, so nothing may answer a Questionnaire that was never written."""
    mock_system_info("v42")
    mock_attributes()
    await _scaffold_project(tmp_path)
    data_sets: list[dict[str, Any]] = deepcopy(_DATA_SETS_PAYLOAD["dataSets"])
    data_sets[0]["sections"][0]["id"] = "De1aaaaaaaa"
    respx.get(f"{_HOST}/api/dataSets").mock(return_value=httpx.Response(200, json={"dataSets": data_sets}))
    respx.get(f"{_HOST}/api/programs").mock(return_value=httpx.Response(200, json=_PROGRAMS_PAYLOAD))
    respx.get(f"{_HOST}/api/programRules").mock(return_value=httpx.Response(200, json={"programRules": []}))
    respx.get(f"{_HOST}/api/trackedEntityTypes").mock(return_value=httpx.Response(200, json={"trackedEntityTypes": []}))
    respx.get(f"{_HOST}/api/optionSets").mock(return_value=httpx.Response(200, json=_OPTION_SETS_PAYLOAD))
    respx.get(f"{_HOST}/api/categories").mock(return_value=httpx.Response(200, json={"categories": []}))
    respx.get(f"{_HOST}/api/organisationUnits").mock(return_value=httpx.Response(200, json=_ROOT_PAYLOAD))

    report = await service.generate_full(resolve_profile("probe"), load_project(tmp_path))

    fsh = tmp_path / "ig" / "input" / "fsh"
    assert not (fsh / "data-sets" / "BfMAe6Itzgt.fsh").exists()
    assert not (fsh / EXAMPLES_DIRECTORY / "BfMAe6Itzgt-1.fsh").exists()
    assert not (tmp_path / "ig" / "input" / "pagecontent" / "Questionnaire-BfMAe6Itzgt-intro.md").exists()
    assert report.examples.example_count == 1
    assert any("linkId twice" in note.message for note in report.questionnaires.notes)
    assert not any("linkId twice" in note.message for note in report.examples.notes)
    assert not any("linkId twice" in note.message for note in report.pages.notes)


@respx.mock
async def test_generate_full_runs_the_example_target_after_the_questionnaires(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    mock_attributes: Callable[..., None],
    tmp_path: Path,
) -> None:
    """A full run carries an example report whose responses answer the questionnaires it just wrote."""
    mock_system_info("v42")
    mock_attributes()
    await _scaffold_project(tmp_path)
    _mock_metadata()

    report = await service.generate_full(resolve_profile("probe"), load_project(tmp_path))

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
    assert [note.message for note in build.notes] == []


def test_unanswerable_questions_are_left_unanswered_with_one_note() -> None:
    """An invented attachment, catchment polygon, or DHIS2 object reference misrepresents the form."""
    synthetic = build_synthetic_responses([_WIDE_TYPES], [_WIDE_OPTION_SET], 1, _ROOT_ORG_UNIT, _TODAY)
    content = _wide_content()
    for uid in ("Defile00000", "Deimage0000", "Degeo000000", "Deref000000", "Detrk000000"):
        assert uid not in content
    assert [note.message for note in synthetic.notes] == [
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
    assert [note.message for note in build.notes] == []


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
    respx.get(f"{_HOST}/api/programRules").mock(return_value=httpx.Response(200, json={"programRules": []}))
    respx.get(f"{_HOST}/api/trackedEntityTypes").mock(return_value=httpx.Response(200, json={"trackedEntityTypes": []}))
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
    assert any("base QuestionnaireResponse declared" in note.message for note in build.notes)


#: One registration form per DHIS2 value type a unique attribute can carry, so the spelling rule is
#: checked per type rather than on the one TEXT case a real program happens to ask.
_UNIQUE_VALUE_TYPES = ("TEXT", "LONG_TEXT", "USERNAME", "EMAIL", "PHONE_NUMBER", "URL", "INTEGER")

#: The value types a unique attribute cannot be made distinct in - a boolean has two values, a
#: `LETTER` fifty-two, and an option-bound attribute only as many as its set holds.
_INDISTINCT_VALUE_TYPES = ("BOOLEAN", "LETTER", "DATE")


def _unique_registration(value_type: str, *, option_set_uid: str | None = None) -> QuestionnaireSourceIn:
    """A registration form asking one unique attribute of the named value type, and nothing else."""
    return QuestionnaireSourceIn(
        uid="IpHINAT79UW",
        name="Child Programme",
        kind="tracker",
        tracked_entity_type_uid="nEenWmSyUEp",
        flat_items=[
            QuestionnaireItemIn(
                uid="Tea1aaaaaaa",
                name="Unique ID",
                value_type=value_type,
                unique=True,
                option_set_uid=option_set_uid,
            )
        ],
    )


def _unique_values(source: QuestionnaireSourceIn, per_target: int, option_sets: list[OptionSetIn]) -> list[str]:
    """The values `per_target` registrations answer the form's single unique attribute with."""
    build = build_synthetic_responses([source], option_sets, per_target, _ROOT_ORG_UNIT, _TODAY)
    return [answer.value for response in build.responses for answer in response.answers]


@pytest.mark.parametrize("value_type", _UNIQUE_VALUE_TYPES)
def test_a_unique_attribute_answers_distinctly_per_registration(value_type: str) -> None:
    """One invented constant registers one person and cascades every enrollment behind it into `E1064`."""
    values = _unique_values(_unique_registration(value_type), 12, [])

    assert len(values) == 12
    assert len(set(values)) == 12


def test_a_unique_attributes_value_carries_the_identity_that_minted_it() -> None:
    """The distinctness comes from the response's own minted UID, not from the RNG stream."""
    build = build_synthetic_responses([_unique_registration("TEXT")], [], 3, _ROOT_ORG_UNIT, _TODAY)

    for response in build.responses:
        assert response.tracked_entity_uid is not None
        assert response.tracked_entity_uid in response.answers[0].value


def test_a_unique_numeric_attribute_stays_inside_the_sign_its_value_type_admits() -> None:
    """A distinct number is still a legal one: DHIS2 refuses a negative `INTEGER_POSITIVE` whatever else it is."""
    positive = _unique_values(_unique_registration("INTEGER_POSITIVE"), 8, [])
    negative = _unique_values(_unique_registration("INTEGER_NEGATIVE"), 8, [])
    zero_or_positive = _unique_values(_unique_registration("INTEGER_ZERO_OR_POSITIVE"), 8, [])

    assert all(int(value) > 0 for value in positive)
    assert all(int(value) < 0 for value in negative)
    assert all(int(value) >= 0 for value in zero_or_positive)
    assert len(set(positive)) == len(set(negative)) == len(set(zero_or_positive)) == 8


def test_a_unique_email_and_url_keep_the_shape_their_value_type_asks_for() -> None:
    """A distinct value that stopped being an email would trade one refusal for another."""
    emails = _unique_values(_unique_registration("EMAIL"), 4, [])
    urls = _unique_values(_unique_registration("URL"), 4, [])
    phones = _unique_values(_unique_registration("PHONE_NUMBER"), 4, [])

    assert all(value.endswith("@example.com") and value.count("@") == 1 for value in emails)
    assert all(value.startswith("https://example.invalid/") for value in urls)
    assert all(value.startswith("+") and value[1:].isdigit() for value in phones)


@pytest.mark.parametrize("value_type", _INDISTINCT_VALUE_TYPES)
def test_a_unique_attribute_with_no_room_for_distinctness_is_tallied_rather_than_faked(value_type: str) -> None:
    """Inventing a value outside what the type admits trades a refusal we can explain for one we cannot."""
    build = build_synthetic_responses([_unique_registration(value_type)], [], 4, _ROOT_ORG_UNIT, _TODAY)

    messages = [note.message for note in build.notes]

    assert any("no room for a corpus-distinct value" in message and "E1064" in message for message in messages)
    assert any("Unique ID (Tea1aaaaaaa)" in message for message in messages)


def test_a_unique_option_bound_attribute_keeps_answering_its_own_option_set() -> None:
    """An option-bound answer has to name a concept the CodeSystem holds, so distinctness gives way to codability."""
    gender = _OPTION_SETS[0]
    source = _unique_registration("TEXT", option_set_uid=gender.uid)

    values = _unique_values(source, 4, [gender])
    build = build_synthetic_responses([source], [gender], 4, _ROOT_ORG_UNIT, _TODAY)

    assert set(values) <= {option.code for option in gender.options}
    assert any("no room for a corpus-distinct value" in note.message for note in build.notes)


def test_an_attribute_the_instance_does_not_call_unique_is_answered_as_it_always_was() -> None:
    """The rule is keyed on DHIS2's own `unique` flag, so an ordinary attribute keeps its illustrative value."""
    ordinary = _unique_registration("TEXT").model_copy(
        update={"flat_items": [QuestionnaireItemIn(uid="Tea1aaaaaaa", name="Unique ID", value_type="TEXT")]}
    )

    values = _unique_values(ordinary, 3, [])

    assert values == ["Example Unique ID"] * 3
