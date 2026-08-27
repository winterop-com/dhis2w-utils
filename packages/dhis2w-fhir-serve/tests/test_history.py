"""`GET /facade/tracked-entities/{uid}/events`: the wire read it holds DHIS2 to, and the record it answers.

Mocked (respx); no live stack. The store is the compiled capture fixture, whose stage form
`PsAncVisit1` is the very Questionnaire a served event is projected through, and the DHIS2 client is
opened against a mocked host and put on `app.state.live_client` - the same stand-in for a live run
`test_register.py` builds and argues for.

What is asserted about the wire is the discipline the record read is built on: one request, to the
tracked entity's own address, with the events nested in `fields` and no `program` anywhere near it
(BUGS.md 72 and 91).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

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
from fixture_project import CAPTURE_CANONICAL, CAPTURE_IDENTIFIER_BASE, REGISTRATION_TRACKED_ENTITY_TYPE_UID

_HOST = "https://dhis2.example"
_BASE_URL = "http://serve.test"
_SYSTEM_INFO = {"version": "2.42.0"}

_PERSON_UID = "PLoWmEuLJl2"
_ENROLLMENT_UID = "EnrAnc00001"
_PROGRAM_UID = "PrAncCare01"
_STAGE_UID = "PsAncVisit1"
_ORG_UNIT_UID = "DiszpKrYNg8"

_TRACKED_ENTITY_URL = f"{_HOST}/api/tracker/trackedEntities/{_PERSON_UID}"
_TRACKED_ENTITY_SYSTEM = f"{CAPTURE_IDENTIFIER_BASE}/id/tracked-entity"
_ENROLLMENT_SYSTEM = f"{CAPTURE_IDENTIFIER_BASE}/id/tracker-enrollment"
_STAGE_QUESTIONNAIRE = f"{CAPTURE_CANONICAL}/Questionnaire/{_STAGE_UID}"
_EVENT_PROFILE = f"{CAPTURE_CANONICAL}/StructureDefinition/d2-tracker-event-response"
_ORGANISATION_UNIT_EXTENSION = f"{CAPTURE_CANONICAL}/StructureDefinition/d2-organisation-unit"
_ENROLLMENT_EXTENSION = f"{CAPTURE_CANONICAL}/StructureDefinition/d2-tracker-enrollment"
_FORM_TYPE_EXTENSION = f"{CAPTURE_CANONICAL}/StructureDefinition/d2-form-type"

_PROFILES_TOML = """
default = "probe"

[profiles.probe]
base_url = "https://dhis2.example"
auth = "basic"
username = "admin"
password = "district"
"""


def _event(
    event_uid: str,
    *,
    occurred_at: str | None = "2026-07-25T11:00:00.000",
    stage_uid: str = _STAGE_UID,
    status: str = "COMPLETED",
    enrollment_uid: str | None = _ENROLLMENT_UID,
    values: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """One event as the tracker endpoint nests it under an enrollment."""
    event: dict[str, Any] = {
        "event": event_uid,
        "programStage": stage_uid,
        "status": status,
        "orgUnit": _ORG_UNIT_UID,
        "dataValues": values
        if values is not None
        else [
            {"dataElement": "DeAncVisNo1", "value": "2"},
            {"dataElement": "DeAncDanger", "value": "true"},
        ],
    }
    if occurred_at is not None:
        event["occurredAt"] = occurred_at
    if enrollment_uid is not None:
        event["enrollment"] = enrollment_uid
    return event


def _record(*events: dict[str, Any]) -> dict[str, Any]:
    """One tracked entity carrying one enrollment, with the events under it."""
    return {
        "trackedEntity": _PERSON_UID,
        "trackedEntityType": REGISTRATION_TRACKED_ENTITY_TYPE_UID,
        "enrollments": [
            {
                "enrollment": _ENROLLMENT_UID,
                "program": _PROGRAM_UID,
                "status": "ACTIVE",
                "events": list(events),
            }
        ],
    }


def _record_route(*events: dict[str, Any]) -> respx.Route:
    """Mock the entity read the record comes off."""
    return respx.get(_TRACKED_ENTITY_URL).mock(return_value=httpx.Response(200, json=_record(*events)))


@pytest.fixture
def tracked_entities() -> TrackedEntitiesConfig:
    """The `[serve.tracked_entities]` table the app under test was started with; override to change it."""
    return TrackedEntitiesConfig()


@pytest.fixture
def record_profile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Profile:
    """A Basic profile against the mocked host, resolvable from a config home of this test's own."""
    config_directory = tmp_path / ".config" / "dhis2"
    config_directory.mkdir(parents=True)
    (config_directory / "profiles.toml").write_text(_PROFILES_TOML, encoding="utf-8")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_directory.parent))
    monkeypatch.delenv("DHIS2_PROFILE", raising=False)
    return Profile(base_url=_HOST, auth="basic", username="admin", password="district")


@pytest.fixture
async def record_client(
    capture_project: FhirProject,
    record_profile: Profile,
    tracked_entities: TrackedEntitiesConfig,
) -> AsyncIterator[httpx.AsyncClient]:
    """The facade over the capture guide, holding a DHIS2 client against the mocked host."""
    with respx.mock:
        respx.get(f"{_HOST}/api/system/info").mock(return_value=httpx.Response(200, json=_SYSTEM_INFO))
        app: FastAPI = create_app(
            ServeSettings(project_dir=capture_project.project_root, tracked_entities=tracked_entities)
        )
        async with (
            app.router.lifespan_context(app),
            open_client(record_profile) as dhis2,
        ):
            app.state.live_client = dhis2
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url=_BASE_URL) as http:
                yield http


@pytest.fixture
async def compiled_client(compiled_project: FhirProject) -> AsyncIterator[httpx.AsyncClient]:
    """The same facade with no instance behind it, which is what a compiled run is."""
    app: FastAPI = create_app(ServeSettings(project_dir=compiled_project.project_root))
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url=_BASE_URL) as http:
            yield http


def _link(bundle: dict[str, Any], relation: str) -> str | None:
    """One relation's URL out of a Bundle's links, or None when the Bundle offers no such link."""
    return next((link["url"] for link in bundle.get("link", []) if link["relation"] == relation), None)


def _parameters(url: str) -> dict[str, str]:
    """The query one link carries, as a client reading it would."""
    return {name: values[0] for name, values in parse_qs(urlsplit(url).query).items()}


def _matches(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    """The matched resources of a searchset, which is every entry but an `outcome` one."""
    return [entry["resource"] for entry in bundle.get("entry", []) if entry["search"]["mode"] == "match"]


async def test_the_record_is_one_entity_scoped_read_naming_no_program(record_client: httpx.AsyncClient) -> None:
    """The events come off the tracked entity, with the events named in `fields` and no `program` sent.

    Both halves are the contract: `/api/tracker/events` demands a `program` on 2.43 (BUGS.md 91) and
    an entity-scoped read naming one the entity is not enrolled in answers 404 (BUGS.md 72), so the
    record is read where neither can happen.
    """
    read = _record_route(_event("EvAncVis001"))

    response = await record_client.get(f"/facade/tracked-entities/{_PERSON_UID}/events")

    assert response.status_code == 200
    assert len(read.calls) == 1
    parameters = read.calls[0].request.url.params
    assert "program" not in parameters
    assert "events[" in parameters["fields"]
    assert "dataValues[" in parameters["fields"]


async def test_one_event_is_served_as_the_response_its_stage_form_describes(
    record_client: httpx.AsyncClient,
) -> None:
    """The document is the capture contract's own: the stage's questionnaire, the person, the values."""
    _record_route(_event("EvAncVis001"))

    body = (await record_client.get(f"/facade/tracked-entities/{_PERSON_UID}/events")).json()
    [response] = _matches(body)

    assert body["resourceType"] == "Bundle"
    assert body["type"] == "searchset"
    assert body["total"] == 1
    assert response["resourceType"] == "QuestionnaireResponse"
    assert response["id"] == "EvAncVis001"
    assert response["questionnaire"] == _STAGE_QUESTIONNAIRE
    assert response["status"] == "completed"
    assert response["meta"]["profile"] == [_EVENT_PROFILE]
    assert response["subject"] == {
        "type": "Patient",
        "identifier": {"system": _TRACKED_ENTITY_SYSTEM, "value": _PERSON_UID},
    }
    assert response["authored"].startswith("2026-07-25T11:00:00")
    assert response["item"] == [
        {"linkId": "DeAncVisNo1", "answer": [{"valueInteger": 2}]},
        {"linkId": "DeAncDanger", "answer": [{"valueBoolean": True}]},
    ]


async def test_the_document_carries_the_enrollment_and_the_reporting_unit(
    record_client: httpx.AsyncClient,
) -> None:
    """The two facts a stage response's own profile requires beside the person, as its extensions."""
    _record_route(_event("EvAncVis001"))

    body = (await record_client.get(f"/facade/tracked-entities/{_PERSON_UID}/events")).json()
    extensions = {extension["url"]: extension for extension in _matches(body)[0]["extension"]}

    assert extensions[_ORGANISATION_UNIT_EXTENSION]["valueReference"] == {"reference": f"Location/{_ORG_UNIT_UID}"}
    assert extensions[_ENROLLMENT_EXTENSION]["valueIdentifier"] == {
        "system": _ENROLLMENT_SYSTEM,
        "value": _ENROLLMENT_UID,
    }
    assert extensions[_FORM_TYPE_EXTENSION]["valueCode"] == "tracker-event"


async def test_the_record_is_newest_first_whatever_order_the_instance_answered_in(
    record_client: httpx.AsyncClient,
) -> None:
    """DHIS2 nests the events unordered, so the record states the order rather than passing one on."""
    _record_route(
        _event("EvAncVis002", occurred_at="2026-07-25T07:00:00.000"),
        _event("EvAncVis001", occurred_at="2026-07-25T09:00:00.000"),
        _event("EvAncVis003", occurred_at="2026-07-25T08:00:00.000"),
    )

    body = (await record_client.get(f"/facade/tracked-entities/{_PERSON_UID}/events")).json()

    assert [response["id"] for response in _matches(body)] == ["EvAncVis001", "EvAncVis003", "EvAncVis002"]


async def test_a_page_is_a_slice_of_the_record_and_the_links_walk_it(record_client: httpx.AsyncClient) -> None:
    """`_count` and `page` walk the ordered record, and `total` stays the whole of it on every page."""
    _record_route(
        _event("EvAncVis001", occurred_at="2026-07-25T09:00:00.000"),
        _event("EvAncVis002", occurred_at="2026-07-25T08:00:00.000"),
        _event("EvAncVis003", occurred_at="2026-07-25T07:00:00.000"),
    )

    first = (await record_client.get(f"/facade/tracked-entities/{_PERSON_UID}/events?_count=2")).json()
    second = (await record_client.get(_link(first, "next") or "")).json()
    back = (await record_client.get(_link(second, "previous") or "")).json()

    assert [response["id"] for response in _matches(first)] == ["EvAncVis001", "EvAncVis002"]
    assert [response["id"] for response in _matches(second)] == ["EvAncVis003"]
    assert [response["id"] for response in _matches(back)] == ["EvAncVis001", "EvAncVis002"]
    assert first["total"] == second["total"] == 3
    assert _link(first, "previous") is None
    assert _link(second, "next") is None


async def test_count_zero_asks_how_long_the_record_is(record_client: httpx.AsyncClient) -> None:
    """R4's request for the total alone: how many events the entity holds, and none of them."""
    _record_route(_event("EvAncVis001"), _event("EvAncVis002"))

    body = (await record_client.get(f"/facade/tracked-entities/{_PERSON_UID}/events?_count=0")).json()

    assert body["total"] == 2
    assert "entry" not in body


async def test_a_count_above_the_limit_is_served_the_limit(record_client: httpx.AsyncClient) -> None:
    """A page is bounded by `[serve.tracked_entities] page_size_limit`, clamped rather than refused."""
    _record_route(*[_event(f"EvAncVis{index:03d}") for index in range(1, 4)])

    body = (await record_client.get(f"/facade/tracked-entities/{_PERSON_UID}/events?_count=5000")).json()

    assert body["total"] == 3
    assert _parameters(_link(body, "self") or "")["_count"] == "100"


async def test_a_parameter_this_surface_cannot_apply_is_refused(record_client: httpx.AsyncClient) -> None:
    """Ignoring one would answer a narrower question with the whole record."""
    _record_route(_event("EvAncVis001"))

    response = await record_client.get(f"/facade/tracked-entities/{_PERSON_UID}/events?programStage={_STAGE_UID}")

    assert response.status_code == 400
    assert response.json()["issue"][0]["code"] == "invalid"
    assert "`programStage`" in response.json()["issue"][0]["diagnostics"]


async def test_an_event_of_an_unpublished_stage_is_stated_rather_than_dropped(
    record_client: httpx.AsyncClient,
) -> None:
    """It counts in the total, carries no document, and the searchset says which stage it was of."""
    _record_route(_event("EvOther0001", stage_uid="PsUnknown01"), _event("EvAncVis001"))

    body = (await record_client.get(f"/facade/tracked-entities/{_PERSON_UID}/events")).json()
    outcomes = [entry["resource"] for entry in body["entry"] if entry["search"]["mode"] == "outcome"]

    assert body["total"] == 2
    assert [response["id"] for response in _matches(body)] == ["EvAncVis001"]
    assert outcomes[0]["resourceType"] == "OperationOutcome"
    assert "PsUnknown01" in outcomes[0]["issue"][0]["diagnostics"]


async def test_an_event_missing_a_required_fact_claims_no_profile(record_client: httpx.AsyncClient) -> None:
    """An event the instance dates nothing is served as it is, without claiming to conform.

    A stage response's own profile requires the instant it was authored at, so a document carrying
    none is a document that does not meet it - and saying it does would be this server asserting
    conformance on the instance's behalf. It sorts to the end of a newest-first record for the same
    reason: an undated event is not newer than a dated one.
    """
    _record_route(_event("EvAncVis001", occurred_at=None), _event("EvAncVis002"))

    body = (await record_client.get(f"/facade/tracked-entities/{_PERSON_UID}/events")).json()
    undated = next(response for response in _matches(body) if response["id"] == "EvAncVis001")

    assert [response["id"] for response in _matches(body)] == ["EvAncVis002", "EvAncVis001"]
    assert "meta" not in undated
    assert "authored" not in undated


async def test_one_event_is_read_under_the_entity_whose_record_it_is(record_client: httpx.AsyncClient) -> None:
    """The URL a page's entry names answers that one document, and an event of nobody here is a 404."""
    _record_route(_event("EvAncVis001"))

    body = (await record_client.get(f"/facade/tracked-entities/{_PERSON_UID}/events")).json()
    entry_url = body["entry"][0]["fullUrl"]
    read = await record_client.get(entry_url)
    missing = await record_client.get(f"/facade/tracked-entities/{_PERSON_UID}/events/EvAncVis999")

    assert entry_url == f"{_BASE_URL}/facade/tracked-entities/{_PERSON_UID}/events/EvAncVis001"
    assert read.status_code == 200
    assert read.json()["id"] == "EvAncVis001"
    assert missing.status_code == 404


async def test_a_tracked_entity_the_instance_does_not_hold_is_a_404(record_client: httpx.AsyncClient) -> None:
    """The refusal names what was not found - the person - rather than the surface it was asked of."""
    respx.get(_TRACKED_ENTITY_URL).mock(return_value=httpx.Response(404, json={"message": "not found"}))

    response = await record_client.get(f"/facade/tracked-entities/{_PERSON_UID}/events")

    assert response.status_code == 404
    assert response.json()["issue"][0]["diagnostics"] == f"no tracked entity with id `{_PERSON_UID}` is served here"


@pytest.mark.parametrize("tracked_entities", [TrackedEntitiesConfig(events=False)])
async def test_a_project_serving_identity_alone_refuses_the_record_and_names_the_key(
    record_client: httpx.AsyncClient,
) -> None:
    """`[serve.tracked_entities] events = false` is a decision the refusal states in the operator's words."""
    read = _record_route(_event("EvAncVis001"))

    response = await record_client.get(f"/facade/tracked-entities/{_PERSON_UID}/events")

    assert response.status_code == 404
    assert response.json()["issue"][0]["code"] == "not-supported"
    assert "`[serve.tracked_entities] events = true`" in response.json()["issue"][0]["diagnostics"]
    assert not read.called


@pytest.mark.parametrize("tracked_entities", [TrackedEntitiesConfig(enabled=False)])
async def test_a_project_serving_no_register_serves_no_record_either(record_client: httpx.AsyncClient) -> None:
    """One line takes the register away, and the record is part of the register."""
    response = await record_client.get(f"/facade/tracked-entities/{_PERSON_UID}/events")

    assert response.status_code == 404
    assert "`[serve.tracked_entities] enabled`" in response.json()["issue"][0]["diagnostics"]


async def test_a_compiled_run_answers_that_it_has_no_instance_to_read(compiled_client: httpx.AsyncClient) -> None:
    """A compiled guide has nothing to answer about, and says so rather than answering an empty record."""
    response = await compiled_client.get(f"/facade/tracked-entities/{_PERSON_UID}/events")

    assert response.status_code == 404
    assert response.json()["issue"][0]["code"] == "not-supported"
    assert "--live" in response.json()["issue"][0]["diagnostics"]


@pytest.mark.parametrize(
    ("tracked_entities", "declared"),
    [(TrackedEntitiesConfig(), True), (TrackedEntitiesConfig(events=False), False)],
)
def test_the_capability_statement_states_where_a_record_is_read(
    capture_project: FhirProject, tracked_entities: TrackedEntitiesConfig, declared: bool
) -> None:
    """`/metadata` names the address, on the resource type whose documents it answers with."""
    store = load_compiled_store(capture_project)
    settings = ServeSettings(project_dir=capture_project.project_root, live=True, tracked_entities=tracked_entities)
    statement = build_server_capability(
        project=capture_project,
        store_summary=store.summary(),
        settings=settings,
        register_surface=RegisterSurface.resolve(
            TrackedEntityIndex.from_store(capture_project, store), tracked_entities
        ),
        server_version="9.9.9",
    )
    documentation = " ".join(
        resource.documentation or "" for rest in statement.rest or [] for resource in rest.resource or []
    )

    assert ("/facade/tracked-entities/{uid}/events" in documentation) is declared
