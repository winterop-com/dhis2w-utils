"""The identity dial on the register: what a nomination fills, what it states absent, and what it leaves alone.

`docs/fhir/design/ips.md` section 9, phase 1. The fixture guide publishes no attribute that means
"name" - no DHIS2 instance does, which is the whole argument - so the nomination here names the one
TEXT attribute the fixture publishes. What is under test is the reading, not the fixture's semantics.

Every other test in this package runs against a project that nominates nothing, which is where the
byte-identical claim is proven: the suite passes unchanged, so a project without the table serves
exactly what it served before the table existed.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from dhis2w_client.errors import Dhis2ApiError
from dhis2w_client.generated.v42.oas import TrackerTrackedEntity
from dhis2w_fhir.config import FhirProject, TrackedEntitiesConfig, load_project
from dhis2w_fhir.ips import DATA_ABSENT_ERROR, DATA_ABSENT_UNKNOWN
from dhis2w_fhir.r4 import DATA_ABSENT_REASON_EXTENSION_URL
from dhis2w_fhir_serve.projection.sqlite_store import SqliteProjectionStore
from dhis2w_fhir_serve.projection.sync import run_sync
from dhis2w_fhir_serve.register.index import NominatedAttributeError, TrackedEntityIndex
from dhis2w_fhir_serve.register.projection import registered_entity_for
from dhis2w_fhir_serve.register.surface import RegisterSurface
from dhis2w_fhir_serve.store import load_compiled_store
from fixture_project import (
    CAPTURE_FHIR_TOML,
    REGISTRATION_CODED_ATTRIBUTE,
    REGISTRATION_DATE_ATTRIBUTE,
    REGISTRATION_PROGRAM_ONLY_ATTRIBUTE,
    REGISTRATION_TRACKED_ENTITY_TYPE_UID,
    REGISTRATION_UNIQUE_ATTRIBUTE,
    SPECIMEN_TRACKED_ENTITY_TYPE_UID,
    build_capture_project,
)
from pydantic import BaseModel, ConfigDict

_PERSON_UID = "PLoWmEuLJl2"
_NATIONAL_ID = "SCEN-A-0001"

#: The table this test nominates through. `TeaNationId` is TEXT and is the only TEXT attribute the
#: fixture's registration form asks; `TeaBirthDat` is DATE; `TeaSex00001` is TEXT bound to an option
#: set whose two options carry the DHIS2 codes `F` and `M`, which are the values DHIS2 stores.
_IDENTITY_TABLE = f"""
[ips.identity]
name = "{REGISTRATION_UNIQUE_ATTRIBUTE}"
birth_date = "{REGISTRATION_DATE_ATTRIBUTE}"
sex = "{REGISTRATION_CODED_ATTRIBUTE}"

[ips.identity.administrative_gender]
"F" = "female"
"M" = "male"
"""

_HOST = "https://dhis2.example"
_TRACKER_PATH = f"{_HOST}/api/tracker/trackedEntities"
_ENROLLMENTS_PATH = f"{_HOST}/api/tracker/enrollments"


def _project_with(destination: Path, table: str) -> FhirProject:
    """The compiled capture guide, with one more table written into its `fhir.toml`."""
    build_capture_project(destination)
    (destination / "fhir.toml").write_text(CAPTURE_FHIR_TOML + table, encoding="utf-8")
    return load_project(destination)


@pytest.fixture
def nominating_project(tmp_path: Path) -> FhirProject:
    """The capture guide with a name, a birth date, and a sex nominated."""
    return _project_with(tmp_path, _IDENTITY_TABLE)


def _index(project: FhirProject) -> TrackedEntityIndex:
    """What a run over that guide resolves a register lookup against."""
    return TrackedEntityIndex.from_store(project, load_compiled_store(project))


def _entity(**values: str) -> TrackerTrackedEntity:
    """One tracked entity holding the named attribute values, as the tracker endpoint sends it."""
    return TrackerTrackedEntity.model_validate(_entity_body(**values))


def _entity_body(**values: str) -> dict[str, Any]:
    """The wire body of that entity, which the sync poll receives verbatim."""
    return {
        "trackedEntity": _PERSON_UID,
        "trackedEntityType": REGISTRATION_TRACKED_ENTITY_TYPE_UID,
        "orgUnit": "DiszpKrYNg8",
        "updatedAt": "2026-08-20T09:00:00.123",
        "deleted": False,
        "attributes": [{"attribute": uid, "value": value} for uid, value in values.items()],
        "enrollments": [],
    }


def _served(project: FhirProject, entity: TrackerTrackedEntity, resource_type: str = "Patient") -> dict[str, Any]:
    """One registered entity as the register route and the sync both serialise it."""
    registered = registered_entity_for(entity, _index(project), resource_type)
    body: dict[str, Any] = registered.model_dump(mode="json", exclude_none=True, by_alias=True)
    return body


def test_a_nominated_person_carries_a_name_a_birth_date_and_a_gender(nominating_project: FhirProject) -> None:
    """The register already served `Patient` resources a client could not recognise a person from."""
    entity = _entity(
        **{
            REGISTRATION_UNIQUE_ATTRIBUTE: _NATIONAL_ID,
            REGISTRATION_DATE_ATTRIBUTE: "2001-02-03",
            REGISTRATION_CODED_ATTRIBUTE: "F",
        }
    )

    patient = _served(nominating_project, entity)

    assert patient["name"] == [{"text": _NATIONAL_ID}]
    assert patient["birthDate"] == "2001-02-03"
    assert patient["gender"] == "female"
    assert "_birthDate" not in patient


def test_the_nominated_value_still_rides_the_attribute_value_extension(nominating_project: FhirProject) -> None:
    """A nomination adds a reading of a value and removes nothing: DHIS2's own string is still there."""
    entity = _entity(**{REGISTRATION_CODED_ATTRIBUTE: "F"})

    patient = _served(nominating_project, entity)

    values = [
        nested["valueString"]
        for extension in patient["extension"]
        for nested in extension["extension"]
        if nested["url"] == "value"
    ]
    assert values == ["F"]
    assert patient["gender"] == "female"


def test_a_midnight_instant_reads_as_the_day_it_names(nominating_project: FhirProject) -> None:
    """DHIS2 answers a DATE attribute two ways, and `Patient.birthDate` is a FHIR `date` either way."""
    entity = _entity(**{REGISTRATION_DATE_ATTRIBUTE: "2001-02-03T00:00:00.000"})

    assert _served(nominating_project, entity)["birthDate"] == "2001-02-03"


def test_a_person_the_instance_holds_no_birth_date_for_states_it_unknown(nominating_project: FhirProject) -> None:
    """The IG's own worked example: a required element with no value carries data-absent-reason."""
    patient = _served(nominating_project, _entity(**{REGISTRATION_UNIQUE_ATTRIBUTE: _NATIONAL_ID}))

    assert "birthDate" not in patient
    assert patient["_birthDate"] == {
        "extension": [{"url": DATA_ABSENT_REASON_EXTENSION_URL, "valueCode": DATA_ABSENT_UNKNOWN}]
    }


def test_a_birth_date_this_server_cannot_read_states_the_absence_as_an_error(
    nominating_project: FhirProject,
) -> None:
    """ "Nobody recorded one" and "what was recorded is not a date" are different answers, and stay different."""
    patient = _served(nominating_project, _entity(**{REGISTRATION_DATE_ATTRIBUTE: "sometime in 2001"}))

    assert "birthDate" not in patient
    assert patient["_birthDate"] == {
        "extension": [{"url": DATA_ABSENT_REASON_EXTENSION_URL, "valueCode": DATA_ABSENT_ERROR}]
    }


def test_a_sex_value_outside_the_map_publishes_no_gender(nominating_project: FhirProject) -> None:
    """The binding on `Patient.gender` is required, so an unmapped value has no code to become."""
    patient = _served(nominating_project, _entity(**{REGISTRATION_CODED_ATTRIBUTE: "X"}))

    assert "gender" not in patient
    assert "_gender" not in patient


def test_a_person_holding_none_of_the_nominated_values_states_only_the_birth_date_absence(
    nominating_project: FhirProject,
) -> None:
    """`name` and `gender` are required on nothing the register serves, so their absence is omission."""
    patient = _served(nominating_project, _entity())

    assert "name" not in patient
    assert "gender" not in patient
    assert "_birthDate" in patient


def test_a_specimen_is_no_business_of_a_nomination_about_a_person(nominating_project: FhirProject) -> None:
    """R4 gives a `Specimen` no name, no gender, and no birth date, so a nomination never reaches one."""
    entity = TrackerTrackedEntity.model_validate(
        {
            "trackedEntity": "SpEcImEn001",
            "trackedEntityType": SPECIMEN_TRACKED_ENTITY_TYPE_UID,
            "orgUnit": "DiszpKrYNg8",
            "attributes": [{"attribute": REGISTRATION_DATE_ATTRIBUTE, "value": "2001-02-03"}],
        }
    )

    specimen = _served(nominating_project, entity, resource_type="Specimen")

    assert "name" not in specimen
    assert "birthDate" not in specimen
    assert "_birthDate" not in specimen


def test_a_project_nominating_nothing_serves_what_it_always_served(tmp_path: Path) -> None:
    """The absent table is byte-identical to the register before the table existed."""
    project = _project_with(tmp_path, "")
    entity = _entity(**{REGISTRATION_UNIQUE_ATTRIBUTE: _NATIONAL_ID, REGISTRATION_DATE_ATTRIBUTE: "2001-02-03"})

    patient = _served(project, entity)

    assert set(patient) == {"resourceType", "id", "meta", "identifier", "extension"}


def test_a_nomination_the_guide_says_is_the_wrong_type_refuses_the_run(tmp_path: Path) -> None:
    """A birth date read off a household size is a wrong answer nobody sees, so the run never opens."""
    project = _project_with(tmp_path, f'\n[ips.identity]\nbirth_date = "{REGISTRATION_PROGRAM_ONLY_ATTRIBUTE}"\n')

    with pytest.raises(NominatedAttributeError) as raised:
        _index(project)

    message = str(raised.value)
    assert "birth_date" in message
    assert REGISTRATION_PROGRAM_ONLY_ATTRIBUTE in message
    assert "INTEGER_POSITIVE" in message
    assert "DATE" in message


def test_a_nomination_the_guide_publishes_nothing_about_is_served_rather_than_refused(tmp_path: Path) -> None:
    """The guide's silence means the attribute is outside this project's selection, not that it is wrong."""
    project = _project_with(tmp_path, '\n[ips.identity]\nname = "TeaUnknown1"\n')

    index = _index(project)

    assert index.identity.name == "TeaUnknown1"


class _Reader(BaseModel):
    """A `RegisterReader` over one respx-mocked host, which is what a sync is handed."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    connection: httpx.AsyncClient

    async def get_raw(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Read one DHIS2 path, answering the parsed JSON body and raising on a refusal."""
        answer = await self.connection.get(path, params=params)
        if answer.status_code >= 400:
            raise Dhis2ApiError(status_code=answer.status_code, message=answer.reason_phrase, body=answer.json())
        body = answer.json()
        return body if isinstance(body, dict) else {"data": body}


async def test_the_synced_body_and_the_live_answer_are_the_same_bytes(
    nominating_project: FhirProject, tmp_path: Path
) -> None:
    """One mapping surface, so a nominated identity reaches a synced copy exactly as it reaches a read."""
    store = SqliteProjectionStore(tmp_path / "sync" / "projection.sqlite")
    body = _entity_body(
        **{
            REGISTRATION_UNIQUE_ATTRIBUTE: _NATIONAL_ID,
            REGISTRATION_DATE_ATTRIBUTE: "2001-02-03",
            REGISTRATION_CODED_ATTRIBUTE: "M",
        }
    )
    surface = RegisterSurface.resolve(
        _index(nominating_project), TrackedEntitiesConfig(tracked_entity_types=[REGISTRATION_TRACKED_ENTITY_TYPE_UID])
    )

    with respx.mock:
        respx.get(_TRACKER_PATH).mock(
            return_value=httpx.Response(
                200,
                json={"pager": {"page": 1, "pageSize": 200, "total": 1, "pageCount": 1}, "trackedEntities": [body]},
            )
        )
        respx.get(_ENROLLMENTS_PATH).mock(
            return_value=httpx.Response(
                200, json={"pager": {"page": 1, "pageSize": 200, "total": 0, "pageCount": 0}, "enrollments": []}
            )
        )
        await run_sync(
            _Reader(connection=httpx.AsyncClient(base_url=_HOST)),
            surface=surface,
            store=store,
            project_root=nominating_project.project_root,
            store_path=store.database_path,
            overlap=timedelta(seconds=300),
        )

    held = await store.read("Patient", _PERSON_UID)
    assert held is not None
    assert held.body == _served(nominating_project, TrackerTrackedEntity.model_validate(body))
    assert held.body["gender"] == "male"
    assert held.body["name"] == [{"text": _NATIONAL_ID}]
