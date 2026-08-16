"""`GET /Patient` and the enrollment listing: the wire contract they hold DHIS2 to, and what they answer.

Mocked (respx); no live stack. The store is the compiled capture fixture, which publishes exactly
what a patient lookup reads out of a guide - a registration form naming tracked entity type
`TetPerson01`, and a `D2TEA_CS` declaring `TeaNationId` unique and three other attributes not - and
the DHIS2 client is opened against a mocked host and put on `app.state.live_client`, which is the
one thing that makes these routes answer rather than refuse. That split is the design: the routes
read the guide only through `TrackedEntityIndex` and the instance only through `register.wire`, so a
compiled store plus a live client is a faithful stand-in for a live run and costs no IG fetch.

What is asserted about the wire is the empirical contract, not the code's own habits: the
`trackedEntityType` a search is required to name, the `filter=<uid>:eq:<value>` it filters with, and
`ouMode=ACCESSIBLE` on every single search - the one BUGS.md 74 says an identifier lookup cannot do
without.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import Profile
from dhis2w_fhir.config import FhirProject, TrackedEntitiesConfig
from dhis2w_fhir_serve.app import create_app
from dhis2w_fhir_serve.capability import build_server_capability
from dhis2w_fhir_serve.register.index import TrackedEntityIndex
from dhis2w_fhir_serve.register.surface import RegisterSurface
from dhis2w_fhir_serve.settings import ServeSettings
from dhis2w_fhir_serve.store import load_compiled_store
from fastapi import FastAPI
from fixture_project import (
    CAPTURE_IDENTIFIER_BASE,
    REGISTRATION_CODED_ATTRIBUTE,
    REGISTRATION_DATE_ATTRIBUTE,
    REGISTRATION_GENERATED_ATTRIBUTE,
    REGISTRATION_PROGRAM_ONLY_ATTRIBUTE,
    REGISTRATION_PROGRAM_UID,
    REGISTRATION_TRACKED_ENTITY_TYPE_UID,
    REGISTRATION_UNIQUE_ATTRIBUTE,
    SPECIMEN_RESOURCE_TYPE,
    SPECIMEN_TRACKED_ENTITY_TYPE_NAME,
    SPECIMEN_TRACKED_ENTITY_TYPE_UID,
    SPECIMEN_UNIQUE_ATTRIBUTE,
)

_HOST = "https://dhis2.example"

_BASE_URL = "http://serve.test"

_SYSTEM_INFO = {"version": "2.42.0"}

_TRACKED_ENTITY_SYSTEM = f"{CAPTURE_IDENTIFIER_BASE}/id/tracked-entity"
_TRACKED_ENTITY_TYPE_SYSTEM = f"{CAPTURE_IDENTIFIER_BASE}/id/tracked-entity-type"
_NATIONAL_ID_SYSTEM = f"{CAPTURE_IDENTIFIER_BASE}/tracked-entity-attribute/{REGISTRATION_UNIQUE_ATTRIBUTE}"

_PERSON_UID = "PLoWmEuLJl2"
_OTHER_PERSON_UID = "QaTbMxTeSt01"
_NATIONAL_ID = "SCEN-A-0001"

_PROFILES_TOML = """
default = "probe"

[profiles.probe]
base_url = "https://dhis2.example"
auth = "basic"
username = "admin"
password = "district"
"""


def _entity(
    tracked_entity_uid: str = _PERSON_UID,
    *,
    national_id: str = _NATIONAL_ID,
    enrollments: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """One tracked entity as the tracker endpoint sends it: entity attributes, and enrollment ones beside them."""
    return {
        "trackedEntity": tracked_entity_uid,
        "trackedEntityType": REGISTRATION_TRACKED_ENTITY_TYPE_UID,
        "orgUnit": "DiszpKrYNg8",
        "attributes": [
            {
                "attribute": REGISTRATION_DATE_ATTRIBUTE,
                "displayName": "Date of birth",
                "valueType": "DATE",
                "value": "1994-03-02",
            },
            {
                "attribute": REGISTRATION_CODED_ATTRIBUTE,
                "displayName": "Sex",
                "valueType": "TEXT",
                "value": "OpFemale001",
            },
        ],
        "enrollments": enrollments
        if enrollments is not None
        else [
            {
                "enrollment": "EnrAnc00001",
                "program": REGISTRATION_PROGRAM_UID,
                "status": "ACTIVE",
                "orgUnit": "DiszpKrYNg8",
                "enrolledAt": "2026-07-25T11:00:00.000",
                "attributes": [
                    {
                        "attribute": REGISTRATION_UNIQUE_ATTRIBUTE,
                        "displayName": "National identifier",
                        "valueType": "TEXT",
                        "value": national_id,
                    },
                    {
                        "attribute": REGISTRATION_PROGRAM_ONLY_ATTRIBUTE,
                        "displayName": "Household size",
                        "valueType": "INTEGER",
                        "value": "4",
                    },
                ],
            }
        ],
    }


@pytest.fixture
def patient_profile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Profile:
    """A Basic profile against the mocked host, resolvable from a config home of this test's own."""
    config_directory = tmp_path / ".config" / "dhis2"
    config_directory.mkdir(parents=True)
    (config_directory / "profiles.toml").write_text(_PROFILES_TOML, encoding="utf-8")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_directory.parent))
    monkeypatch.delenv("DHIS2_PROFILE", raising=False)
    return Profile(base_url=_HOST, auth="basic", username="admin", password="district")


@pytest.fixture
async def live_client(
    capture_project: FhirProject,
    patient_profile: Profile,
) -> AsyncIterator[httpx.AsyncClient]:
    """The facade over the capture guide, holding a DHIS2 client against the mocked host.

    The respx router is opened here rather than by a decorator on each test: a fixture is set up
    before the decorator would activate, and the client connects during setup. Tests register their
    own tracker routes on this same router.
    """
    with respx.mock:
        respx.get(f"{_HOST}/api/system/info").mock(return_value=httpx.Response(200, json=_SYSTEM_INFO))
        app: FastAPI = create_app(ServeSettings(project_dir=capture_project.project_root))
        async with (
            app.router.lifespan_context(app),
            open_client(patient_profile) as dhis2,
        ):
            app.state.live_client = dhis2
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url=_BASE_URL) as http:
                yield http


def _search_route(*entities: dict[str, Any]) -> respx.Route:
    """Mock the tracker search, answering every query with the same page."""
    return respx.get(f"{_HOST}/api/tracker/trackedEntities").mock(
        return_value=httpx.Response(200, json={"trackedEntities": list(entities)})
    )


def _read_route(entity: dict[str, Any] | None, tracked_entity_uid: str = _PERSON_UID) -> respx.Route:
    """Mock the one-entity read, answering 404 the way DHIS2 does for a UID it does not hold."""
    response = (
        httpx.Response(200, json=entity)
        if entity is not None
        else httpx.Response(404, json={"httpStatusCode": 404, "status": "ERROR", "message": "not found"})
    )
    return respx.get(f"{_HOST}/api/tracker/trackedEntities/{tracked_entity_uid}").mock(return_value=response)


async def test_a_system_qualified_identifier_searches_the_attribute_it_names(
    live_client: httpx.AsyncClient,
) -> None:
    """`identifier={system}|{value}` filters on the one attribute that system belongs to."""
    _read_route(None, _NATIONAL_ID)
    search = _search_route(_entity())

    response = await live_client.get(f"/Patient?identifier={_NATIONAL_ID_SYSTEM}|{_NATIONAL_ID}")
    body = response.json()

    assert response.status_code == 200
    assert body["resourceType"] == "Bundle"
    assert body["type"] == "searchset"
    assert body["total"] == 1
    assert body["entry"][0]["resource"]["id"] == _PERSON_UID
    request_url = search.calls[0].request.url
    assert request_url.params["trackedEntityType"] == REGISTRATION_TRACKED_ENTITY_TYPE_UID
    assert request_url.params["filter"] == f"{REGISTRATION_UNIQUE_ATTRIBUTE}:eq:{_NATIONAL_ID}"
    assert request_url.params["ouMode"] == "ACCESSIBLE"


async def test_a_bare_identifier_value_tries_the_uid_and_every_search_key(
    live_client: httpx.AsyncClient,
) -> None:
    """A token naming no system is a lookup across every key at once, the tracked entity UID included.

    Every key, by default, is every attribute DHIS2 declares unique **or** searchable - so the
    searchable-but-not-unique date of birth is filtered on beside the unique national identifier and
    the unique laboratory reference, which is the widening a clinic looking somebody up by a
    searchable attribute depends on. A generated attribute is a key like any other: DHIS2 mints its
    value, and the value on somebody's card is exactly the thing a clerk types in here.
    """
    _read_route(None, _NATIONAL_ID)
    search = _search_route(_entity())

    response = await live_client.get(f"/Patient?identifier={_NATIONAL_ID}")

    assert response.status_code == 200
    assert response.json()["total"] == 1
    filters = [call.request.url.params["filter"] for call in search.calls]
    assert filters == [
        f"{REGISTRATION_DATE_ATTRIBUTE}:eq:{_NATIONAL_ID}",
        f"{REGISTRATION_UNIQUE_ATTRIBUTE}:eq:{_NATIONAL_ID}",
        f"{SPECIMEN_UNIQUE_ATTRIBUTE}:eq:{_NATIONAL_ID}",
        f"{REGISTRATION_GENERATED_ATTRIBUTE}:eq:{_NATIONAL_ID}",
    ]
    assert all(call.request.url.params["ouMode"] == "ACCESSIBLE" for call in search.calls)


async def test_a_value_that_is_not_uid_shaped_is_never_read_as_one(live_client: httpx.AsyncClient) -> None:
    """DHIS2 answers 400 for a non-UID in the UID slot, so a national ID is not spent on that read."""
    read = _read_route(None, _NATIONAL_ID)
    _search_route()

    response = await live_client.get(f"/Patient?identifier={_NATIONAL_ID}")

    assert response.status_code == 200
    assert not read.called


async def test_the_tracked_entity_system_reads_the_entity_rather_than_filtering(
    live_client: httpx.AsyncClient,
) -> None:
    """The UID system is not an attribute, so it is answered by reading that one entity."""
    read = _read_route(_entity())
    search = _search_route()

    response = await live_client.get(f"/Patient?identifier={_TRACKED_ENTITY_SYSTEM}|{_PERSON_UID}")

    assert response.status_code == 200
    assert response.json()["entry"][0]["resource"]["id"] == _PERSON_UID
    assert read.called
    assert not search.called


async def test_two_identifiers_finding_one_person_answer_one_entry(
    live_client: httpx.AsyncClient,
) -> None:
    """A person matched by two tokens is carried once - the fold deduplicates by tracked entity UID."""
    _read_route(_entity(), _PERSON_UID)
    _search_route(_entity())

    response = await live_client.get(
        f"/Patient?identifier={_TRACKED_ENTITY_SYSTEM}|{_PERSON_UID}&identifier={_NATIONAL_ID_SYSTEM}|{_NATIONAL_ID}"
    )
    body = response.json()

    assert body["total"] == 1
    assert [entry["resource"]["id"] for entry in body["entry"]] == [_PERSON_UID]


async def test_two_people_holding_the_value_both_come_back(live_client: httpx.AsyncClient) -> None:
    """Nothing here collapses a result set DHIS2 returned with two people in it."""
    _read_route(None, _NATIONAL_ID)
    _search_route(_entity(), _entity(_OTHER_PERSON_UID))

    body = (await live_client.get(f"/Patient?identifier={_NATIONAL_ID}")).json()

    assert body["total"] == 2
    assert [entry["resource"]["id"] for entry in body["entry"]] == [_PERSON_UID, _OTHER_PERSON_UID]


async def test_a_search_parameter_this_server_cannot_answer_is_refused(live_client: httpx.AsyncClient) -> None:
    """`family=Smith` is a query the register cannot run, so it is refused rather than answered with everybody."""
    read = _read_route(None, "NOBODY00001")
    search = _search_route()

    response = await live_client.get("/Patient?family=Smith")

    assert response.status_code == 400
    assert response.headers["content-type"] == "application/fhir+json"
    issue = response.json()["issue"][0]
    assert issue["code"] == "invalid"
    assert issue["diagnostics"] == (
        "`family` is not a search parameter this server answers `Patient` on: `identifier` is the one it supports"
    )
    assert not read.called
    assert not search.called


async def test_an_unanswerable_parameter_beside_an_identifier_is_refused_too(
    live_client: httpx.AsyncClient,
) -> None:
    """A refused parameter is refused whatever it was sent with - a partly-run query is not an answer."""
    _read_route(None, _NATIONAL_ID)
    _search_route(_entity())

    response = await live_client.get(f"/Patient?identifier={_NATIONAL_ID}&birthdate=1994-03-02")

    assert response.status_code == 400
    assert "`birthdate`" in response.json()["issue"][0]["diagnostics"]


async def test_a_page_named_on_an_identifier_search_is_refused(live_client: httpx.AsyncClient) -> None:
    """`page` walks the listing; a search naming an identifier is answered whole, so the two do not combine."""
    _read_route(None, _NATIONAL_ID)
    _search_route(_entity())

    response = await live_client.get(f"/Patient?identifier={_NATIONAL_ID}&page=dDBwMg")

    assert response.status_code == 400
    assert response.json()["issue"][0]["diagnostics"] == (
        "`page` names a page of the `Patient` listing, and a search naming `identifier` is answered whole"
    )


async def test_the_identifier_search_carries_no_more_than_the_count_asked_for(
    live_client: httpx.AsyncClient,
) -> None:
    """`_count` caps the matches a client is handed, and `total` still states how many there were."""
    _read_route(None, _NATIONAL_ID)
    _search_route(_entity(), _entity(_OTHER_PERSON_UID))

    response = await live_client.get(f"/Patient?identifier={_NATIONAL_ID}&_count=1")
    body = response.json()

    assert body["total"] == 2
    assert [entry["resource"]["id"] for entry in body["entry"]] == [_PERSON_UID]
    assert body["link"][0]["relation"] == "self"
    assert body["link"][0]["url"] == f"{_BASE_URL}/Patient?identifier={_NATIONAL_ID}&_count=1"
    assert [link["relation"] for link in body["link"]] == ["self"]


async def test_a_count_of_zero_on_an_identifier_search_answers_the_total_alone(
    live_client: httpx.AsyncClient,
) -> None:
    """R4's way of asking how many matched: the number, and none of the matches."""
    _read_route(None, _NATIONAL_ID)
    _search_route(_entity(), _entity(_OTHER_PERSON_UID))

    body = (await live_client.get(f"/Patient?identifier={_NATIONAL_ID}&_count=0")).json()

    assert body["total"] == 2
    assert "entry" not in body
    assert body["link"][0]["url"] == f"{_BASE_URL}/Patient?identifier={_NATIONAL_ID}&_count=0"


async def test_a_count_that_is_not_a_number_of_matches_is_refused(live_client: httpx.AsyncClient) -> None:
    """An unreadable cap is a malformed query, and a negative one is not a number of rows."""
    _read_route(None, _NATIONAL_ID)
    _search_route(_entity())

    words = await live_client.get(f"/Patient?identifier={_NATIONAL_ID}&_count=lots")
    negative = await live_client.get(f"/Patient?identifier={_NATIONAL_ID}&_count=-1")

    assert words.status_code == 400
    assert words.json()["issue"][0]["code"] == "invalid"
    assert negative.status_code == 400
    assert negative.json()["issue"][0]["code"] == "invalid"


async def test_an_identifier_nobody_holds_is_an_empty_searchset(live_client: httpx.AsyncClient) -> None:
    """An unmatched search is an empty Bundle, never a 404 - a 404 would deny the endpoint exists."""
    _read_route(None, "NOBODY00001")
    _search_route()

    response = await live_client.get("/Patient?identifier=NOBODY00001")
    body = response.json()

    assert response.status_code == 200
    assert body["type"] == "searchset"
    assert body["total"] == 0
    assert "entry" not in body


async def test_a_system_the_guide_publishes_nothing_for_matches_nothing(
    live_client: httpx.AsyncClient,
) -> None:
    """An unknown identifier system is an unsatisfied query, not a malformed one."""
    search = _search_route(_entity())

    response = await live_client.get("/Patient?identifier=http://elsewhere.example/mrn|A-1")

    assert response.status_code == 200
    assert response.json()["total"] == 0
    assert not search.called


async def test_the_patient_carries_the_uid_the_unique_value_and_the_rest_as_extensions(
    live_client: httpx.AsyncClient,
) -> None:
    """The projection: identity in `identifier`, the type as a tag, every other value an extension."""
    _read_route(_entity())
    _search_route()

    patient = (await live_client.get(f"/Patient/{_PERSON_UID}")).json()

    assert patient["resourceType"] == "Patient"
    assert patient["id"] == _PERSON_UID
    assert patient["identifier"] == [
        {"system": _TRACKED_ENTITY_SYSTEM, "value": _PERSON_UID},
        {"system": _NATIONAL_ID_SYSTEM, "value": _NATIONAL_ID},
    ]
    assert patient["meta"]["tag"] == [
        {"system": _TRACKED_ENTITY_TYPE_SYSTEM, "code": REGISTRATION_TRACKED_ENTITY_TYPE_UID}
    ]
    carried = {
        nested["valueString"]
        for extension in patient["extension"]
        for nested in extension["extension"]
        if nested["url"] == "attributeId"
    }
    assert carried == {
        REGISTRATION_DATE_ATTRIBUTE,
        REGISTRATION_CODED_ATTRIBUTE,
        REGISTRATION_PROGRAM_ONLY_ATTRIBUTE,
    }
    assert "name" not in patient
    assert "gender" not in patient
    assert "birthDate" not in patient


async def test_an_unknown_tracked_entity_uid_reads_as_not_found(live_client: httpx.AsyncClient) -> None:
    """A read - unlike a search - does 404, and answers it as an OperationOutcome."""
    _read_route(None, "NOBODY00001")

    response = await live_client.get("/Patient/NOBODY00001")

    assert response.status_code == 404
    assert response.json()["issue"][0]["code"] == "not-found"


async def test_the_enrollment_listing_names_the_program_and_the_organisation_unit(
    live_client: httpx.AsyncClient,
) -> None:
    """The picker's feed: the enrollment, joined to the names this guide publishes."""
    _read_route(_entity())

    listing = (await live_client.get(f"/tracked-entities/{_PERSON_UID}/enrollments")).json()

    assert listing["tracked_entity_uid"] == _PERSON_UID
    assert listing["enrollments"] == [
        {
            "enrollment_uid": "EnrAnc00001",
            "program_uid": REGISTRATION_PROGRAM_UID,
            "program_name": "Antenatal care",
            "status": "ACTIVE",
            "active": True,
            "enrolled_at": "2026-07-25T11:00:00",
            "organisation_unit_uid": "DiszpKrYNg8",
            "organisation_unit_name": "Ngelehun CHC",
        }
    ]


async def test_a_completed_enrollment_is_listed_and_marked(live_client: httpx.AsyncClient) -> None:
    """DHIS2 takes events into a completed enrollment without a word (BUGS.md 70); the listing says so."""
    _read_route(
        _entity(
            enrollments=[
                {
                    "enrollment": "EnrDone0001",
                    "program": REGISTRATION_PROGRAM_UID,
                    "status": "COMPLETED",
                    "orgUnit": "DiszpKrYNg8",
                    "enrolledAt": "2026-01-04T11:00:00.000",
                    "attributes": [],
                }
            ]
        )
    )

    listing = (await live_client.get(f"/tracked-entities/{_PERSON_UID}/enrollments")).json()

    assert listing["enrollments"][0]["status"] == "COMPLETED"
    assert listing["enrollments"][0]["active"] is False


async def test_the_enrollment_read_never_names_a_program(live_client: httpx.AsyncClient) -> None:
    """BUGS.md 72: a program the person is not enrolled in answers 404 claiming the person is gone."""
    read = _read_route(_entity())

    await live_client.get(f"/tracked-entities/{_PERSON_UID}/enrollments")

    assert "program" not in read.calls[0].request.url.params


async def test_a_compiled_run_refuses_patient_as_not_supported(capture_client: httpx.AsyncClient) -> None:
    """No live client, so no instance to ask - stated as the FHIR refusal, not as an empty result."""
    search = await capture_client.get("/Patient?identifier=anything")
    listing = await capture_client.get(f"/tracked-entities/{_PERSON_UID}/enrollments")

    assert search.status_code == 404
    assert search.json()["issue"][0]["code"] == "not-supported"
    assert "--live" in search.json()["issue"][0]["diagnostics"]
    assert listing.status_code == 404
    assert listing.json()["issue"][0]["code"] == "not-supported"


def test_a_compiled_statement_declares_no_patient(capture_project: FhirProject) -> None:
    """`/metadata` states the refusal ahead of the request: a compiled run advertises no Patient."""
    capability = _capability(capture_project, live=False)

    assert "Patient" not in [resource.type for resource in capability.rest[0].resource or []]


def test_a_live_statement_declares_patient_search_on_identifier(capture_project: FhirProject) -> None:
    """A live run over a guide that publishes a registration form declares the search and its parameter."""
    capability = _capability(capture_project, live=True)

    patient = next(resource for resource in capability.rest[0].resource or [] if resource.type == "Patient")
    assert [interaction.code for interaction in patient.interaction or []] == ["read", "search-type"]
    assert [parameter.name for parameter in patient.searchParam or []] == ["identifier"]
    assert (parameter := (patient.searchParam or [])[0]).type == "token"
    assert _NATIONAL_ID_SYSTEM.rsplit("/", 1)[0] in (parameter.documentation or "")


def test_the_index_reads_the_search_keys_and_the_published_types(capture_project: FhirProject) -> None:
    """What the guide states, as the index reads it: the search keys, and the two types the forms register."""
    index = TrackedEntityIndex.from_store(capture_project, load_compiled_store(capture_project))

    assert index.serves_tracked_entities()
    assert index.tracked_entity_type_uids() == (
        REGISTRATION_TRACKED_ENTITY_TYPE_UID,
        SPECIMEN_TRACKED_ENTITY_TYPE_UID,
    )
    assert [attribute.attribute_uid for attribute in index.search_key_attributes()] == [
        REGISTRATION_DATE_ATTRIBUTE,
        REGISTRATION_UNIQUE_ATTRIBUTE,
        SPECIMEN_UNIQUE_ATTRIBUTE,
        REGISTRATION_GENERATED_ATTRIBUTE,
    ]
    assert index.attribute_for_system(_NATIONAL_ID_SYSTEM) is not None
    assert index.program_name(REGISTRATION_PROGRAM_UID) == "Antenatal care"


def test_the_index_reads_each_type_resource_off_the_published_map(capture_project: FhirProject) -> None:
    """`D2TET_CM` is the contract: the resource a type is served as, and the name the instance holds for it."""
    index = TrackedEntityIndex.from_store(capture_project, load_compiled_store(capture_project))

    person = index.tracked_entity_type(REGISTRATION_TRACKED_ENTITY_TYPE_UID)
    specimen = index.tracked_entity_type(SPECIMEN_TRACKED_ENTITY_TYPE_UID)

    assert person is not None
    assert (person.resource_type, person.name) == ("Patient", "Person")
    assert specimen is not None
    assert (specimen.resource_type, specimen.name) == (SPECIMEN_RESOURCE_TYPE, SPECIMEN_TRACKED_ENTITY_TYPE_NAME)


def _capability(project: FhirProject, *, live: bool, tracked_entities: TrackedEntitiesConfig | None = None) -> Any:
    """The statement one run publishes, over the capture guide's own index."""
    store = load_compiled_store(project)
    settings = ServeSettings(
        project_dir=project.project_root, live=live, tracked_entities=tracked_entities or TrackedEntitiesConfig()
    )
    return build_server_capability(
        project=project,
        store_summary=store.summary(),
        settings=settings,
        register_surface=RegisterSurface.resolve(
            TrackedEntityIndex.from_store(project, store), settings.tracked_entities
        ),
        server_version="9.9.9",
    )
