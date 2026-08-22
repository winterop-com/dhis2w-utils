"""ANC tracker program with a repeatable stage - the visit pattern the play snapshot lacks.

The repeated visit is the most common tracker shape in real DHIS2 deployments: an
antenatal-care program enrolls a woman once and then captures the same "ANC visit" form
over and over, one event per visit. Some instances hardcode four numbered stages; most
model it as one stage with `repeatable = true`. The play snapshot carries neither - the
Child Programme's two stages are both non-repeatable - so nothing on the seeded stack
exercises a repeatable stage, several events of one enrollment against one stage, or a
compulsory program-stage data element on live data. This module seeds all three:

- Program `PrAncCare01` "ANC follow-up" (`WITH_REGISTRATION`, tracked entity type Person),
  first/last-name tracked entity attributes, assigned to the root and every facility OU.
- Stage `PsAncVisit1` "ANC visit", `repeatable = true`, `standardInterval = 30`, with three
  tracker-domain data elements: visit number (`INTEGER_POSITIVE`, compulsory), systolic
  blood pressure (`INTEGER`), and danger signs present (`BOOLEAN`).
- Two enrolled women with fixed UIDs: one with four monthly visit events, one with a
  single visit - so "several events of one enrollment on one stage" is live data, not a
  fixture assumption.

Idempotent twice over: metadata lands through `/api/metadata` with fixed UIDs under
`CREATE_AND_UPDATE`, and the tracker payload lands through `/api/tracker` with fixed
tracked entity, enrollment, and event UIDs under the same strategy, so a re-run updates
in place. Event dates are fixed literals for dump stability.

Called from `seed_play` after the FHIR variations, once the OU tree, the Person tracked
entity type, and its attributes exist.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from dhis2w_client.generated.v42.common import Reference
from dhis2w_client.generated.v42.enums import AggregationType, DataElementDomain, ProgramType, ValueType
from dhis2w_client.generated.v42.oas import Sharing, TrackerImportReport
from dhis2w_client.generated.v42.schemas import DataElement, Program, ProgramStage, ProgramStageDataElement
from dhis2w_client.v42.sharing import ACCESS_READ_WRITE_DATA

from .event_program import _level_four_org_units
from .loader import ANC_PERSON_IDENTIFIER_BASE, UNIQUE_IDENTIFIER_ATTRIBUTE_UID, person_identifier

if TYPE_CHECKING:
    from dhis2w_client.v42.client import Dhis2Client

PROGRAM_UID = "PrAncCare01"
STAGE_UID = "PsAncVisit1"

DATA_ELEMENT_VISIT_NUMBER_UID = "DeAncVisNo1"
DATA_ELEMENT_SYSTOLIC_UID = "DeAncBpSys1"
DATA_ELEMENT_DANGER_SIGNS_UID = "DeAncDanger"

# Person tracked entity type and its name attributes, from the play metadata import.
_TRACKED_ENTITY_TYPE_PERSON = "nEenWmSyUEp"
_ATTRIBUTE_FIRST_NAME = "w75KJ2mc4zz"
_ATTRIBUTE_LAST_NAME = "zDhUuAYrxNC"

_SL_ROOT = "ImspTQPwCqd"

# Tracker data with fixed UIDs so a re-run updates rather than duplicates.
TRACKED_ENTITY_FOUR_VISITS_UID = "TeAncMum001"
TRACKED_ENTITY_ONE_VISIT_UID = "TeAncMum002"
ENROLLMENT_FOUR_VISITS_UID = "EnAncMum001"
ENROLLMENT_ONE_VISIT_UID = "EnAncMum002"
EVENT_UIDS_FOUR_VISITS = ("EvAncM1v001", "EvAncM1v002", "EvAncM1v003", "EvAncM1v004")
EVENT_UID_ONE_VISIT = "EvAncM2v001"

#: Monthly visit dates for the four-visit enrollment; the single visit reuses the first.
_VISIT_DATES = ("2025-11-05", "2025-12-03", "2026-01-07", "2026-02-04")
_ENROLLED_AT = "2025-10-20"

_SHARING = Sharing(public=ACCESS_READ_WRITE_DATA, external=False, users={}, userGroups={})


def _visit_data_element(uid: str, name: str, short_name: str, value_type: ValueType) -> DataElement:
    """Typed tracker-domain `DataElement` for the ANC visit form."""
    return DataElement(
        id=uid,
        name=name,
        shortName=short_name,
        valueType=value_type,
        aggregationType=AggregationType.NONE,
        domainType=DataElementDomain.TRACKER,
        zeroIsSignificant=False,
        sharing=_SHARING,
    )


def visit_data_elements() -> list[DataElement]:
    """The three data elements the ANC visit stage asks, in stage order."""
    return [
        _visit_data_element(
            DATA_ELEMENT_VISIT_NUMBER_UID, "ANC visit number", "ANC visit no", ValueType.INTEGER_POSITIVE
        ),
        _visit_data_element(
            DATA_ELEMENT_SYSTOLIC_UID, "ANC systolic blood pressure", "ANC systolic", ValueType.INTEGER
        ),
        _visit_data_element(
            DATA_ELEMENT_DANGER_SIGNS_UID, "ANC danger signs present", "ANC danger signs", ValueType.BOOLEAN
        ),
    ]


def visit_stage() -> ProgramStage:
    """The repeatable ANC visit stage: one event per visit, visit number compulsory."""
    return ProgramStage(
        id=STAGE_UID,
        name="ANC visit",
        shortName="ANC visit",
        program=Reference(id=PROGRAM_UID),
        repeatable=True,
        standardInterval=30,
        minDaysFromStart=0,
        autoGenerateEvent=True,
        openAfterEnrollment=False,
        generatedByEnrollmentDate=False,
        sortOrder=1,
        programStageDataElements=[
            ProgramStageDataElement(
                dataElement=Reference(id=DATA_ELEMENT_VISIT_NUMBER_UID),
                compulsory=True,
                allowProvidedElsewhere=False,
                displayInReports=True,
                sortOrder=0,
            ),
            ProgramStageDataElement(
                dataElement=Reference(id=DATA_ELEMENT_SYSTOLIC_UID),
                compulsory=False,
                allowProvidedElsewhere=False,
                displayInReports=True,
                sortOrder=1,
            ),
            ProgramStageDataElement(
                dataElement=Reference(id=DATA_ELEMENT_DANGER_SIGNS_UID),
                compulsory=False,
                allowProvidedElsewhere=False,
                displayInReports=False,
                sortOrder=2,
            ),
        ],
        sharing=_SHARING,
    )


def anc_program(org_units: list[dict[str, str]]) -> Program:
    """The WITH_REGISTRATION ANC program, assigned to the root and every facility OU."""
    return Program(
        id=PROGRAM_UID,
        name="ANC follow-up",
        shortName="ANC follow-up",
        description="Antenatal care follow-up: one enrollment per pregnancy, one repeatable visit stage.",
        programType=ProgramType.WITH_REGISTRATION,
        trackedEntityType=Reference(id=_TRACKED_ENTITY_TYPE_PERSON),
        onlyEnrollOnce=False,
        displayIncidentDate=False,
        # The program must list its stages: without this the importer detaches the stage's
        # program reference and event writes fail with E1008 (same pattern as event_program).
        programStages=[{"id": STAGE_UID}],
        organisationUnits=[{"id": _SL_ROOT}, *org_units],
        programTrackedEntityAttributes=[
            {
                "id": "PtAncTea001",
                "trackedEntityAttribute": {"id": _ATTRIBUTE_FIRST_NAME},
                "mandatory": False,
                "displayInList": True,
                "sortOrder": 1,
            },
            {
                "id": "PtAncTea002",
                "trackedEntityAttribute": {"id": _ATTRIBUTE_LAST_NAME},
                "mandatory": False,
                "displayInList": True,
                "sortOrder": 2,
            },
        ],
        sharing=_SHARING,
    )


def _visit_event(
    event_uid: str, enrollment_uid: str, tracked_entity_uid: str, org_unit: str, index: int
) -> dict[str, Any]:
    """One completed ANC visit event with the visit number, a plausible BP, and a danger-sign flag."""
    return {
        "event": event_uid,
        "program": PROGRAM_UID,
        "programStage": STAGE_UID,
        "enrollment": enrollment_uid,
        "trackedEntity": tracked_entity_uid,
        "orgUnit": org_unit,
        "occurredAt": f"{_VISIT_DATES[index]}T09:00:00.000",
        "status": "COMPLETED",
        "dataValues": [
            {"dataElement": DATA_ELEMENT_VISIT_NUMBER_UID, "value": str(index + 1)},
            {"dataElement": DATA_ELEMENT_SYSTOLIC_UID, "value": str(110 + 4 * index)},
            {"dataElement": DATA_ELEMENT_DANGER_SIGNS_UID, "value": "false"},
        ],
    }


def _enrolled_woman(
    tracked_entity_uid: str,
    enrollment_uid: str,
    org_unit: str,
    first_name: str,
    last_name: str,
    identifier_index: int,
    event_uids: tuple[str, ...],
) -> dict[str, Any]:
    """One tracked entity with a single ANC enrollment and its visit events.

    The Unique ID comes from the ANC band of `person_identifier`, so these
    two women carry an identifier a register shows and a search finds,
    without ever landing on one of the play snapshot's.
    """
    return {
        "trackedEntity": tracked_entity_uid,
        "trackedEntityType": _TRACKED_ENTITY_TYPE_PERSON,
        "orgUnit": org_unit,
        "attributes": [
            {"attribute": _ATTRIBUTE_FIRST_NAME, "value": first_name},
            {"attribute": _ATTRIBUTE_LAST_NAME, "value": last_name},
            {
                "attribute": UNIQUE_IDENTIFIER_ATTRIBUTE_UID,
                "value": person_identifier(ANC_PERSON_IDENTIFIER_BASE, identifier_index),
            },
        ],
        "enrollments": [
            {
                "enrollment": enrollment_uid,
                "program": PROGRAM_UID,
                "trackedEntity": tracked_entity_uid,
                "orgUnit": org_unit,
                "enrolledAt": f"{_ENROLLED_AT}T08:00:00.000",
                "occurredAt": f"{_ENROLLED_AT}T08:00:00.000",
                "status": "ACTIVE",
                "events": [
                    _visit_event(event_uid, enrollment_uid, tracked_entity_uid, org_unit, index)
                    for index, event_uid in enumerate(event_uids)
                ],
            }
        ],
    }


async def seed_anc_program(client: Dhis2Client) -> int:
    """Create the ANC metadata and its tracker data; return the visit-event count.

    The facility for both women is the first level-4 org unit by UID, which is stable
    across rebuilds because the OU tree comes from the same fixture every time.
    """
    org_units = await _level_four_org_units(client)
    facility = min((entry["id"] for entry in org_units), default=_SL_ROOT)
    metadata_bundle: dict[str, list[dict[str, Any]]] = {
        "dataElements": [
            element.model_dump(by_alias=True, exclude_none=True, mode="json") for element in visit_data_elements()
        ],
        "programs": [anc_program(org_units).model_dump(by_alias=True, exclude_none=True, mode="json")],
        "programStages": [visit_stage().model_dump(by_alias=True, exclude_none=True, mode="json")],
    }
    await client.post_raw(
        "/api/metadata",
        body=metadata_bundle,
        params={"importStrategy": "CREATE_AND_UPDATE", "atomicMode": "OBJECT"},
    )
    tracker_body = {
        "trackedEntities": [
            _enrolled_woman(
                TRACKED_ENTITY_FOUR_VISITS_UID,
                ENROLLMENT_FOUR_VISITS_UID,
                facility,
                "Aminata",
                "Kamara",
                0,
                EVENT_UIDS_FOUR_VISITS,
            ),
            _enrolled_woman(
                TRACKED_ENTITY_ONE_VISIT_UID,
                ENROLLMENT_ONE_VISIT_UID,
                facility,
                "Isata",
                "Sesay",
                1,
                (EVENT_UID_ONE_VISIT,),
            ),
        ]
    }
    raw = await client.post_raw(
        "/api/tracker",
        body=tracker_body,
        params={"importStrategy": "CREATE_AND_UPDATE", "atomicMode": "OBJECT", "async": "false"},
    )
    report = TrackerImportReport.model_validate(raw)
    if report.status is not None and str(
        report.status.value if hasattr(report.status, "value") else report.status
    ) not in ("OK", "SUCCESS"):
        message = report.message or "tracker import did not report OK"
        raise RuntimeError(f"ANC tracker import failed: {message}")
    return len(EVENT_UIDS_FOUR_VISITS) + 1
