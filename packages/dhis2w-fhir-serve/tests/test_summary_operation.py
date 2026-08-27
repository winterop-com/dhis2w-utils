"""`$summary`: what the operation is gated by, whose record it reads, and what a dose becomes.

`docs/fhir/design/ips.md` section 9, phase 2. Mocked (respx); no live stack. The store is the
compiled capture fixture, whose stage form `ZzYYXq4fJie` is the seeded Baby Postnatal form - so the
data elements mapped here are real immunisation elements and the projection a dose is read through
is the very one `GET /facade/tracked-entities/{uid}/events` answers with.

Every other test in this package runs against a project whose `[ips] enabled` is false, which is
where the additive claim is proven: the suite passes unchanged, so a project that publishes no
summary serves exactly what it served before the operation existed.
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
from dhis2w_fhir.config import FhirProject, TrackedEntitiesConfig, load_project
from dhis2w_fhir_serve.app import create_app
from dhis2w_fhir_serve.capability import build_server_capability
from dhis2w_fhir_serve.register.index import TrackedEntityIndex
from dhis2w_fhir_serve.register.surface import RegisterSurface
from dhis2w_fhir_serve.routes.summary import SUMMARY_CAVEAT_HEADER
from dhis2w_fhir_serve.settings import ServeSettings
from dhis2w_fhir_serve.store import load_compiled_store
from fastapi import FastAPI
from fixture_project import (
    CAPTURE_FHIR_TOML,
    CAPTURE_IDENTIFIER_BASE,
    REGISTRATION_TRACKED_ENTITY_TYPE_UID,
    REGISTRATION_UNIQUE_ATTRIBUTE,
    build_capture_project,
)

_HOST = "https://dhis2.example"
_BASE_URL = "http://serve.test"
_SYSTEM_INFO = {"version": "2.42.0"}

_PERSON_UID = "PLoWmEuLJl2"
_NATIONAL_ID = "SCEN-A-0001"
_ENROLLMENT_UID = "EnrChild001"
_PROGRAM_UID = "IpHINAT79UW"

#: The seeded Baby Postnatal form the fixture publishes, and three of its data elements: two the
#: mapping nominates as doses - one boolean, one coded - and one it does not.
_POSTNATAL_STAGE = "ZzYYXq4fJie"
_MEASLES = "FqlgKAG8HOu"
_PENTA = "vTUhAUZFoys"
_INFANT_WEIGHT = "GQY2lXrypjO"

#: A stage the mapping nominates and this guide publishes no form for, which is a fact worth stating.
_UNPUBLISHED_STAGE = "A03MvHHogjR"

_TRACKED_ENTITY_URL = f"{_HOST}/api/tracker/trackedEntities/{_PERSON_UID}"
_TRACKED_ENTITY_SEARCH = f"{_HOST}/api/tracker/trackedEntities"
_TRACKED_ENTITY_SYSTEM = f"{CAPTURE_IDENTIFIER_BASE}/id/tracked-entity"
_DATA_ELEMENT_SYSTEM = f"{CAPTURE_IDENTIFIER_BASE}/id/data-element"

_SUMMARY_TABLES = f"""
[ips]
enabled = true

[ips.identity]
name = "{REGISTRATION_UNIQUE_ATTRIBUTE}"

[ips.sections.immunizations]
program_stages = ["{_POSTNATAL_STAGE}"]
dose_data_elements = ["{_MEASLES}", "{_PENTA}"]
"""

_SUMMARY_TABLES_WITH_AN_UNPUBLISHED_STAGE = f"""
[ips]
enabled = true

[ips.sections.immunizations]
program_stages = ["{_POSTNATAL_STAGE}", "{_UNPUBLISHED_STAGE}"]
dose_data_elements = ["{_MEASLES}"]
"""

_SUMMARY_MAPPING_NOTHING = """
[ips]
enabled = true
"""

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
    stage_uid: str = _POSTNATAL_STAGE,
    occurred_at: str | None = "2026-07-25T11:00:00.000",
    values: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """One event as the tracker endpoint nests it under an enrollment."""
    event: dict[str, Any] = {
        "event": event_uid,
        "programStage": stage_uid,
        "enrollment": _ENROLLMENT_UID,
        "status": "COMPLETED",
        "orgUnit": "DiszpKrYNg8",
        "dataValues": values if values is not None else [{"dataElement": _MEASLES, "value": "true"}],
    }
    if occurred_at is not None:
        event["occurredAt"] = occurred_at
    return event


def _entity(*events: dict[str, Any]) -> dict[str, Any]:
    """One tracked entity carrying one enrollment, with the events under it."""
    return {
        "trackedEntity": _PERSON_UID,
        "trackedEntityType": REGISTRATION_TRACKED_ENTITY_TYPE_UID,
        "attributes": [{"attribute": REGISTRATION_UNIQUE_ATTRIBUTE, "value": _NATIONAL_ID}],
        "enrollments": [
            {
                "enrollment": _ENROLLMENT_UID,
                "program": _PROGRAM_UID,
                "status": "ACTIVE",
                "events": list(events),
            }
        ],
    }


def _routes(*events: dict[str, Any]) -> None:
    """Mock the two reads a summary makes: the register's own, and the record behind it."""
    body = _entity(*events)
    respx.get(_TRACKED_ENTITY_URL).mock(return_value=httpx.Response(200, json=body))
    respx.get(_TRACKED_ENTITY_SEARCH).mock(return_value=httpx.Response(200, json={"trackedEntities": [body]}))


@pytest.fixture
def summary_profile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Profile:
    """A Basic profile against the mocked host, resolvable from a config home of this test's own."""
    config_directory = tmp_path / ".config" / "dhis2"
    config_directory.mkdir(parents=True)
    (config_directory / "profiles.toml").write_text(_PROFILES_TOML, encoding="utf-8")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_directory.parent))
    monkeypatch.delenv("DHIS2_PROFILE", raising=False)
    return Profile(base_url=_HOST, auth="basic", username="admin", password="district")


@pytest.fixture
def summary_tables() -> str:
    """The `[ips]` tables the project under test states; override to change them."""
    return _SUMMARY_TABLES


@pytest.fixture
def summary_project(tmp_path: Path, summary_tables: str) -> FhirProject:
    """The compiled capture guide, with the summary tables written into its `fhir.toml`."""
    build_capture_project(tmp_path)
    (tmp_path / "fhir.toml").write_text(CAPTURE_FHIR_TOML + summary_tables, encoding="utf-8")
    return load_project(tmp_path)


@pytest.fixture
async def summary_client(summary_project: FhirProject, summary_profile: Profile) -> AsyncIterator[httpx.AsyncClient]:
    """The facade over that guide, holding a DHIS2 client against the mocked host."""
    with respx.mock:
        respx.get(f"{_HOST}/api/system/info").mock(return_value=httpx.Response(200, json=_SYSTEM_INFO))
        app: FastAPI = create_app(ServeSettings(project_dir=summary_project.project_root))
        async with app.router.lifespan_context(app), open_client(summary_profile) as dhis2:
            app.state.live_client = dhis2
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url=_BASE_URL) as http:
                yield http


def _resources(bundle: dict[str, Any], resource_type: str) -> list[dict[str, Any]]:
    """Every entry of one resource type, as the wire carries it."""
    return [
        entry["resource"] for entry in bundle.get("entry", []) if entry["resource"]["resourceType"] == resource_type
    ]


def _sections(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    """The Composition's sections, in the order the document states them."""
    return list(_resources(bundle, "Composition")[0]["section"])


async def test_a_summary_is_a_document_carrying_the_person_and_their_doses(
    summary_client: httpx.AsyncClient,
) -> None:
    """The instance form: one document, the register's own Patient in it, one Immunization per dose."""
    _routes(_event("EvPostnat01"))

    response = await summary_client.get(f"/Patient/{_PERSON_UID}/$summary")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/fhir+json")
    body = response.json()
    assert body["type"] == "document"
    assert body["entry"][0]["resource"]["resourceType"] == "Composition"
    assert [served["id"] for served in _resources(body, "Patient")] == [_PERSON_UID]
    immunizations = _resources(body, "Immunization")
    assert [held["vaccineCode"]["coding"][0]["code"] for held in immunizations] == [_MEASLES]
    assert immunizations[0]["vaccineCode"]["coding"][0]["system"] == _DATA_ELEMENT_SYSTEM
    assert immunizations[0]["status"] == "completed"
    assert immunizations[0]["patient"]["reference"] == body["entry"][1]["fullUrl"]


async def test_the_three_required_sections_state_an_empty_reason_and_the_mapped_one_carries_entries(
    summary_client: httpx.AsyncClient,
) -> None:
    """Nothing is invented for the sections nobody mapped, and the mapped one carries the real doses."""
    _routes(_event("EvPostnat01"))

    body = (await summary_client.get(f"/Patient/{_PERSON_UID}/$summary")).json()

    sections = _sections(body)
    assert [section["title"] for section in sections] == [
        "Problems",
        "Allergies and Intolerances",
        "Medication Summary",
        "Immunizations",
    ]
    for section in sections[:3]:
        assert "entry" not in section
        assert section["emptyReason"]["coding"][0]["code"] == "unavailable"
    assert len(sections[3]["entry"]) == 1


async def test_the_caveat_rides_the_document_and_the_response(summary_client: httpx.AsyncClient) -> None:
    """One fact stated where resources are read, and stated again where responses are."""
    _routes(_event("EvPostnat01"))

    response = await summary_client.get(f"/Patient/{_PERSON_UID}/$summary")

    caveat = response.headers[SUMMARY_CAVEAT_HEADER]
    assert "does not claim the Creator (IPS) actor's obligations" in caveat
    assert caveat in _resources(response.json(), "Composition")[0]["text"]["div"]


async def test_a_value_recording_no_dose_produces_no_immunization(summary_client: httpx.AsyncClient) -> None:
    """A boolean `false` says the vaccine was not given and states no reason, so nothing is minted."""
    _routes(_event("EvPostnat01", values=[{"dataElement": _MEASLES, "value": "false"}]))

    body = (await summary_client.get(f"/Patient/{_PERSON_UID}/$summary")).json()

    assert _resources(body, "Immunization") == []
    assert _sections(body)[3]["emptyReason"]["coding"][0]["code"] == "unavailable"


async def test_a_value_the_mapping_does_not_nominate_is_not_a_dose(summary_client: httpx.AsyncClient) -> None:
    """Every entry traces to a line somebody wrote, so an unmapped element on a mapped stage is left alone."""
    _routes(_event("EvPostnat01", values=[{"dataElement": _INFANT_WEIGHT, "value": "4100"}]))

    assert _resources((await summary_client.get(f"/Patient/{_PERSON_UID}/$summary")).json(), "Immunization") == []


async def test_a_coded_dose_carries_the_dose_number_it_names(summary_client: httpx.AsyncClient) -> None:
    """The value of a coded dose element names which dose of the series it was, and that is what it becomes."""
    _routes(_event("EvPostnat01", values=[{"dataElement": _PENTA, "value": "2"}]))

    immunizations = _resources((await summary_client.get(f"/Patient/{_PERSON_UID}/$summary")).json(), "Immunization")

    assert immunizations[0]["protocolApplied"] == [{"doseNumberString": "2"}]


@pytest.mark.parametrize("summary_tables", [_SUMMARY_TABLES_WITH_AN_UNPUBLISHED_STAGE])
async def test_a_mapped_stage_with_no_published_form_is_named_in_the_section(
    summary_client: httpx.AsyncClient,
) -> None:
    """A guide narrower than its mapping is a fact about the guide, not a person who was never vaccinated."""
    _routes(_event("EvBirth00001", stage_uid=_UNPUBLISHED_STAGE))

    body = (await summary_client.get(f"/Patient/{_PERSON_UID}/$summary")).json()

    assert _unpublished_stated(_sections(body)[3]["text"]["div"])


def _unpublished_stated(narrative: str) -> bool:
    """Whether the section's own narrative names the stage it could not read."""
    return _UNPUBLISHED_STAGE in narrative and "publishes no" in narrative


@pytest.mark.parametrize("summary_tables", [_SUMMARY_MAPPING_NOTHING])
async def test_a_summary_with_no_mapped_section_is_served_with_the_caveat(
    summary_client: httpx.AsyncClient,
) -> None:
    """The owner's call: such a document is served, and it says what it is and is not."""
    _routes(_event("EvPostnat01"))

    response = await summary_client.get(f"/Patient/{_PERSON_UID}/$summary")

    assert response.status_code == 200
    assert [section["title"] for section in _sections(response.json())] == [
        "Problems",
        "Allergies and Intolerances",
        "Medication Summary",
    ]
    assert "No clinical section of this summary is mapped" in response.headers[SUMMARY_CAVEAT_HEADER]


async def test_the_type_level_form_resolves_through_the_registers_identifier_search(
    summary_client: httpx.AsyncClient,
) -> None:
    """`$summary?identifier=` answers the same document the UID form does, for the person it names."""
    _routes(_event("EvPostnat01"))

    named = await summary_client.get("/Patient/$summary", params={"identifier": _NATIONAL_ID})
    by_uid = await summary_client.get(f"/Patient/{_PERSON_UID}/$summary")

    assert named.status_code == 200
    assert _without_instants(named.json()) == _without_instants(by_uid.json())


def _without_instants(bundle: dict[str, Any]) -> dict[str, Any]:
    """One document without the two elements two assemblies are allowed to differ in (R4)."""
    body = dict(bundle)
    body.pop("timestamp")
    body["entry"] = [
        {**entry, "resource": {key: value for key, value in entry["resource"].items() if key != "date"}}
        for entry in body["entry"]
    ]
    return body


async def test_the_type_level_form_refuses_a_request_naming_nobody(summary_client: httpx.AsyncClient) -> None:
    """The IPS says a requestor SHALL provide an identifier, so a bare type-level call is refused."""
    _routes(_event("EvPostnat01"))

    response = await summary_client.get("/Patient/$summary")

    assert response.status_code == 400
    assert "names no person" in response.json()["issue"][0]["diagnostics"]


async def test_the_type_level_form_refuses_a_parameter_it_cannot_apply(summary_client: httpx.AsyncClient) -> None:
    """A narrowing this operation cannot perform would answer a question the caller did not ask."""
    _routes(_event("EvPostnat01"))

    response = await summary_client.get("/Patient/$summary", params={"identifier": _NATIONAL_ID, "_count": "5"})

    assert response.status_code == 400
    assert "`identifier` is the one it supports" in response.json()["issue"][0]["diagnostics"]


async def test_a_uid_the_instance_holds_nobody_under_is_a_not_found(summary_client: httpx.AsyncClient) -> None:
    """A summary is about somebody the register serves, and about nobody else."""
    respx.get(_TRACKED_ENTITY_URL).mock(return_value=httpx.Response(404, json={}))

    response = await summary_client.get(f"/Patient/{_PERSON_UID}/$summary")

    assert response.status_code == 404


async def test_the_operation_is_refused_on_a_register_that_is_not_people(
    summary_client: httpx.AsyncClient,
) -> None:
    """`$summary` is a patient summary, and the refusal names what this server does answer it on."""
    response = await summary_client.get("/Specimen/$summary", params={"identifier": _NATIONAL_ID})

    assert response.status_code == 404
    diagnostics = response.json()["issue"][0]["diagnostics"]
    assert "names no person" in diagnostics
    assert "`Patient`" in diagnostics


@pytest.mark.parametrize("summary_tables", [""])
async def test_a_project_that_publishes_no_summary_is_refused_by_the_key(
    summary_client: httpx.AsyncClient,
) -> None:
    """`[ips] enabled` is false by default, and the refusal names the line an operator would change."""
    response = await summary_client.get(f"/Patient/{_PERSON_UID}/$summary")

    assert response.status_code == 404
    assert "`[ips] enabled`" in response.json()["issue"][0]["diagnostics"]


async def test_a_compiled_run_answers_no_summary(capture_project: FhirProject) -> None:
    """A summary is read from the instance, and a compiled guide has none behind it."""
    (capture_project.project_root / "fhir.toml").write_text(CAPTURE_FHIR_TOML + _SUMMARY_TABLES, encoding="utf-8")
    app: FastAPI = create_app(ServeSettings(project_dir=capture_project.project_root))
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url=_BASE_URL) as http:
            response = await http.get(f"/Patient/{_PERSON_UID}/$summary")

    assert response.status_code == 404
    assert "--live" in response.json()["issue"][0]["diagnostics"]


@pytest.mark.parametrize(("tables", "declared"), [(_SUMMARY_TABLES, True), ("", False)])
def test_the_operation_is_declared_on_the_person_register(
    capture_project: FhirProject, tables: str, declared: bool
) -> None:
    """A client that speaks IPS finds the operation in the conformance document, under its own definition.

    And finds it nowhere on a project that publishes no summary: a statement declaring the operation
    anyway would advertise an interaction every request to it refuses by name.
    """
    (capture_project.project_root / "fhir.toml").write_text(CAPTURE_FHIR_TOML + tables, encoding="utf-8")
    project = load_project(capture_project.project_root)
    store = load_compiled_store(project)
    tracked_entities = TrackedEntitiesConfig()
    statement = build_server_capability(
        project=project,
        store_summary=store.summary(),
        settings=ServeSettings(project_dir=project.project_root, live=True, tracked_entities=tracked_entities),
        register_surface=RegisterSurface.resolve(TrackedEntityIndex.from_store(project, store), tracked_entities),
        server_version="9.9.9",
    )

    operations = {
        resource.type: [(operation.name, operation.definition) for operation in resource.operation or []]
        for rest in statement.rest or []
        for resource in rest.resource or []
    }
    summary = ("summary", "http://hl7.org/fhir/uv/ips/OperationDefinition/summary")
    assert (summary in operations.get("Patient", [])) is declared
    assert summary not in operations.get("Specimen", [])
