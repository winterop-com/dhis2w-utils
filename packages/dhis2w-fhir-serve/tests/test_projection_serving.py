"""The register served from the projection: what the searchset says, and what the instance still decides.

Mocked (respx); the guide is the compiled capture fixture and the projection is a real SQLite file in
a `tmp_path`, filled by hand with the resources a sync would have written. Filling it by hand rather
than by running a sync is the point: this file is about what the SERVING path does with a filled
projection, and `test_projection_sync.py` is about how one gets filled.

Four claims carry it, and every one is a line of `docs/fhir/design/projection.md` section 6 or R3.

- **The projection decides who is on the page, and DHIS2 decides who may see them.** Every entry is a
  live read under the credentials of whoever asked, so a person the projection holds and the instance
  will not disclose is on nobody's page. That is R9's posture (iii), and it is what makes a synced
  server safe to point at a real register.
- **Every projection-served answer states the instant it is as of** - an `outcome` entry, and a header
  beside it. A live answer states neither.
- **No projection-served answer states a total**, because the projection counted under the identity
  the sync ran as.
- **A read of one entity by its id is answered from the instance**, whatever the search backend says,
  because it is a person-level read.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import Profile
from dhis2w_fhir.config import (
    FhirProject,
    ProjectionBackend,
    ProjectionConfig,
    SearchBackend,
    SearchConfig,
    TrackedEntitiesConfig,
)
from dhis2w_fhir_serve.app import create_app
from dhis2w_fhir_serve.capability import build_server_capability
from dhis2w_fhir_serve.projection.base import (
    IndexedName,
    ProjectedResource,
    ProjectionBatch,
    ProjectionCursor,
    ProjectionEndpoint,
)
from dhis2w_fhir_serve.projection.serving import PROJECTION_AS_OF_HEADER
from dhis2w_fhir_serve.projection.sqlite_store import SqliteProjectionStore
from dhis2w_fhir_serve.register.index import TrackedEntityIndex
from dhis2w_fhir_serve.register.surface import RegisterSurface
from dhis2w_fhir_serve.settings import ServeSettings
from dhis2w_fhir_serve.store import load_compiled_store
from fastapi import FastAPI
from fixture_project import (
    CAPTURE_IDENTIFIER_BASE,
    REGISTRATION_TRACKED_ENTITY_TYPE_UID,
    REGISTRATION_UNIQUE_ATTRIBUTE,
)

_HOST = "https://dhis2.example"
_BASE_URL = "http://serve.test"
_SYSTEM_INFO = {"version": "2.42.0"}

_TRACKED_ENTITY_SYSTEM = f"{CAPTURE_IDENTIFIER_BASE}/id/tracked-entity"
_NATIONAL_ID_SYSTEM = f"{CAPTURE_IDENTIFIER_BASE}/tracked-entity-attribute/{REGISTRATION_UNIQUE_ATTRIBUTE}"
_NAME_ATTRIBUTE = "TeaFirstNam"

_PERSON_UID = "PLoWmEuLJl2"
_OTHER_PERSON_UID = "QaTbMxTeS01"
_NATIONAL_ID = "SCEN-A-0001"

_AS_OF = datetime(2026, 8, 21, 9, 0, 0)

_PROFILES_TOML = """
default = "probe"

[profiles.probe]
base_url = "https://dhis2.example"
auth = "basic"
username = "admin"
password = "district"
"""


def _entity(tracked_entity_uid: str = _PERSON_UID, *, national_id: str = _NATIONAL_ID) -> dict[str, Any]:
    """One tracked entity as the instance answers a read of it, which is what an entry is built from."""
    return {
        "trackedEntity": tracked_entity_uid,
        "trackedEntityType": REGISTRATION_TRACKED_ENTITY_TYPE_UID,
        "orgUnit": "DiszpKrYNg8",
        "attributes": [
            {
                "attribute": REGISTRATION_UNIQUE_ATTRIBUTE,
                "displayName": "National identifier",
                "valueType": "TEXT",
                "value": national_id,
            }
        ],
    }


def _projected(tracked_entity_uid: str, *, national_id: str) -> ProjectedResource:
    """One row as a sync wrote it - the registered resource, carrying the two identifiers it always does."""
    return ProjectedResource(
        resource_type="Patient",
        resource_id=tracked_entity_uid,
        cursor=ProjectionCursor(updated_at=_AS_OF),
        body={
            "resourceType": "Patient",
            "id": tracked_entity_uid,
            "identifier": [
                {"system": _TRACKED_ENTITY_SYSTEM, "value": tracked_entity_uid},
                {"system": _NATIONAL_ID_SYSTEM, "value": national_id},
            ],
        },
    )


def _read_route(entity: dict[str, Any] | None, tracked_entity_uid: str = _PERSON_UID) -> respx.Route:
    """Mock the one-entity read, answering 404 the way DHIS2 does for a UID it will not disclose."""
    answer = (
        httpx.Response(200, json=entity)
        if entity is not None
        else httpx.Response(404, json={"httpStatusCode": 404, "status": "ERROR", "message": "not found"})
    )
    return respx.get(f"{_HOST}/api/tracker/trackedEntities/{tracked_entity_uid}").mock(return_value=answer)


async def _fill(store: SqliteProjectionStore, *, names: tuple[tuple[str, str], ...] = ()) -> None:
    """Put two people in the projection and mark both collections read up to one instant."""
    await store.write(
        ProjectionBatch(
            resources=(
                _projected(_PERSON_UID, national_id=_NATIONAL_ID),
                _projected(_OTHER_PERSON_UID, national_id="SCEN-B-0002"),
            ),
            names=tuple(
                IndexedName(
                    tracked_entity_uid=tracked_entity_uid,
                    attribute_uid=_NAME_ATTRIBUTE,
                    value=value,
                    tracked_entity_type_uid=REGISTRATION_TRACKED_ENTITY_TYPE_UID,
                )
                for tracked_entity_uid, value in names
            ),
        )
    )
    for endpoint in (ProjectionEndpoint.TRACKED_ENTITIES, ProjectionEndpoint.ENROLLMENTS):
        await store.write(ProjectionBatch(endpoint=endpoint, cursor=ProjectionCursor(updated_at=_AS_OF)))


@pytest.fixture
def probe_profile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Profile:
    """A Basic profile against the mocked host, resolvable from a config home of this test's own."""
    config_directory = tmp_path / ".config" / "dhis2"
    config_directory.mkdir(parents=True)
    (config_directory / "profiles.toml").write_text(_PROFILES_TOML, encoding="utf-8")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_directory.parent))
    monkeypatch.delenv("DHIS2_PROFILE", raising=False)
    return Profile(base_url=_HOST, auth="basic", username="admin", password="district")


@pytest.fixture
def projection_config(capture_project: FhirProject) -> ProjectionConfig:
    """A SQLite projection beside the fixture project, which is where a real one lives too."""
    return ProjectionConfig(store=ProjectionBackend.SQLITE, path=".serve/projection.sqlite")


@pytest.fixture
async def filled_projection(
    capture_project: FhirProject, projection_config: ProjectionConfig
) -> AsyncIterator[SqliteProjectionStore]:
    """The projection two people and two names have been synced into, closed when the test ends."""
    store = SqliteProjectionStore(capture_project.project_root / projection_config.path)
    await _fill(store, names=((_PERSON_UID, "Somsack"), (_OTHER_PERSON_UID, "ສົມພອນ")))
    yield store
    await store.close()


@pytest.fixture
async def synced_facade(
    capture_project: FhirProject,
    probe_profile: Profile,
    projection_config: ProjectionConfig,
    filled_projection: SqliteProjectionStore,
) -> AsyncIterator[httpx.AsyncClient]:
    """The facade over that project with `[serve.search] backend = "projection"` and a live client."""
    with respx.mock:
        respx.get(f"{_HOST}/api/system/info").mock(return_value=httpx.Response(200, json=_SYSTEM_INFO))
        app: FastAPI = create_app(
            ServeSettings(
                project_dir=capture_project.project_root,
                search=SearchConfig(backend=SearchBackend.PROJECTION),
                projection=projection_config,
            )
        )
        async with app.router.lifespan_context(app), open_client(probe_profile) as dhis2:
            app.state.live_client = dhis2
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url=_BASE_URL) as http:
                yield http


async def test_an_identifier_search_is_answered_from_the_projection_and_resolved_from_the_instance(
    synced_facade: httpx.AsyncClient,
) -> None:
    """One indexed query decides the membership; one live read per match decides the disclosure."""
    read = _read_route(_entity())
    collection = respx.get(f"{_HOST}/api/tracker/trackedEntities")

    answered = await synced_facade.get(f"/Patient?identifier={_NATIONAL_ID_SYSTEM}|{_NATIONAL_ID}")
    body = answered.json()

    matches = [entry for entry in body["entry"] if entry.get("search", {}).get("mode") == "match"]
    assert answered.status_code == 200
    assert [entry["resource"]["id"] for entry in matches] == [_PERSON_UID]
    assert read.calls.call_count == 1
    assert not collection.calls, "a projection-served search puts no filtered tracker query on the wire"


async def test_a_projection_served_searchset_states_the_instant_it_is_as_of(
    synced_facade: httpx.AsyncClient,
) -> None:
    """R3, twice over: an `outcome` entry the data model carries, and a header beside it."""
    _read_route(_entity())

    answered = await synced_facade.get(f"/Patient?identifier={_NATIONAL_ID}")
    body = answered.json()

    outcomes = [entry for entry in body["entry"] if entry.get("search", {}).get("mode") == "outcome"]
    assert answered.headers[PROJECTION_AS_OF_HEADER] == _AS_OF.isoformat()
    assert len(outcomes) == 1
    issue = outcomes[0]["resource"]["issue"][0]
    assert issue["severity"] == "information"
    assert _AS_OF.isoformat() in issue["diagnostics"]


async def test_a_projection_served_searchset_states_no_total(synced_facade: httpx.AsyncClient) -> None:
    """The projection counted under the identity the sync ran as, and this caller's count is DHIS2's to say."""
    _read_route(_entity())

    body = (await synced_facade.get(f"/Patient?identifier={_NATIONAL_ID}")).json()

    assert "total" not in body


async def test_a_person_the_instance_will_not_disclose_is_on_nobodys_page(
    synced_facade: httpx.AsyncClient,
) -> None:
    """R9 in one assertion: the projection holds them, DHIS2 answers 404, and the searchset carries nobody."""
    read = _read_route(None)

    body = (await synced_facade.get(f"/Patient?identifier={_NATIONAL_ID}")).json()

    matches = [entry for entry in body["entry"] if entry.get("search", {}).get("mode") == "match"]
    assert read.calls.call_count == 1
    assert matches == []


async def test_a_content_search_finds_a_person_by_a_value_no_exact_match_could_find(
    synced_facade: httpx.AsyncClient,
) -> None:
    """The thing the live backend cannot do at all: a substring of a name, folded, over the index."""
    _read_route(_entity())

    body = (await synced_facade.get("/Patient?_content=somsa")).json()

    matches = [entry for entry in body["entry"] if entry.get("search", {}).get("mode") == "match"]
    assert [entry["resource"]["id"] for entry in matches] == [_PERSON_UID]


async def test_two_search_parameters_are_conditions_that_both_hold(synced_facade: httpx.AsyncClient) -> None:
    """R4's own rule: values within one parameter widen, and two parameters narrow."""
    _read_route(_entity())
    _read_route(_entity(_OTHER_PERSON_UID, national_id="SCEN-B-0002"), _OTHER_PERSON_UID)

    both = (await synced_facade.get(f"/Patient?identifier={_NATIONAL_ID}&_content=somsack")).json()
    contradictory = (await synced_facade.get(f"/Patient?identifier={_NATIONAL_ID}&_content=ສົມພອນ")).json()

    assert [entry["resource"]["id"] for entry in both["entry"] if entry.get("search", {}).get("mode") == "match"] == [
        _PERSON_UID
    ]
    assert [entry for entry in contradictory["entry"] if entry.get("search", {}).get("mode") == "match"] == []


async def test_the_listing_pages_the_projection_and_links_the_next_page(
    synced_facade: httpx.AsyncClient,
) -> None:
    """The same `_count` and opaque `page` pair every other page of this listing uses - D6 keeps the shape."""
    _read_route(_entity())
    _read_route(_entity(_OTHER_PERSON_UID, national_id="SCEN-B-0002"), _OTHER_PERSON_UID)

    first = (await synced_facade.get("/Patient?_count=1")).json()
    following = [link["url"] for link in first["link"] if link["relation"] == "next"][0]
    second = (await synced_facade.get(following.removeprefix(_BASE_URL))).json()

    assert [entry["resource"]["id"] for entry in first["entry"] if entry.get("search", {}).get("mode") == "match"] == [
        _PERSON_UID
    ]
    assert [entry["resource"]["id"] for entry in second["entry"] if entry.get("search", {}).get("mode") == "match"] == [
        _OTHER_PERSON_UID
    ]
    assert {link["relation"] for link in second["link"]} == {"self", "previous"}


async def test_a_search_reads_back_no_more_matches_than_a_page_may_carry(
    capture_project: FhirProject,
    probe_profile: Profile,
    projection_config: ProjectionConfig,
    filled_projection: SqliteProjectionStore,
) -> None:
    """Every resolution is a live read, so the bound an operator wrote for a page bounds a search too."""
    with respx.mock:
        respx.get(f"{_HOST}/api/system/info").mock(return_value=httpx.Response(200, json=_SYSTEM_INFO))
        app: FastAPI = create_app(
            ServeSettings(
                project_dir=capture_project.project_root,
                search=SearchConfig(backend=SearchBackend.PROJECTION),
                projection=projection_config,
                tracked_entities=TrackedEntitiesConfig(page_size=1, page_size_limit=1),
            )
        )
        async with app.router.lifespan_context(app), open_client(probe_profile) as dhis2:
            app.state.live_client = dhis2
            first = _read_route(_entity())
            second = _read_route(_entity(_OTHER_PERSON_UID, national_id="SCEN-B-0002"), _OTHER_PERSON_UID)
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url=_BASE_URL) as http:
                body = (await http.get("/Patient?_content=somsack,ສົມພອນ&_count=50")).json()

    matches = [entry for entry in body["entry"] if entry.get("search", {}).get("mode") == "match"]
    assert len(matches) <= 1
    assert first.calls.call_count + second.calls.call_count == 1


async def test_a_count_of_zero_is_answered_with_the_cursor_and_no_walk_to_follow(
    synced_facade: httpx.AsyncClient,
) -> None:
    """The one question this posture cannot answer is "how many", and a page of nothing leads nowhere."""
    body = (await synced_facade.get("/Patient?_count=0")).json()

    assert "total" not in body
    assert {link["relation"] for link in body["link"]} == {"self"}
    assert [entry.get("search", {}).get("mode") for entry in body["entry"]] == ["outcome"]


async def test_a_read_of_one_entity_by_its_id_is_answered_from_the_instance(
    synced_facade: httpx.AsyncClient,
) -> None:
    """A person-level read stays live whatever the search backend says, and states no cursor."""
    read = _read_route(_entity())

    answered = await synced_facade.get(f"/Patient/{_PERSON_UID}")

    assert answered.status_code == 200
    assert answered.json()["id"] == _PERSON_UID
    assert read.calls.call_count == 1
    assert PROJECTION_AS_OF_HEADER not in answered.headers


async def test_the_content_parameter_is_refused_where_no_projection_answers_it(
    capture_project: FhirProject, probe_profile: Profile
) -> None:
    """Under `backend = "dhis2"` an exact-match filter cannot search a content, so the query is refused."""
    with respx.mock:
        respx.get(f"{_HOST}/api/system/info").mock(return_value=httpx.Response(200, json=_SYSTEM_INFO))
        app: FastAPI = create_app(ServeSettings(project_dir=capture_project.project_root))
        async with app.router.lifespan_context(app), open_client(probe_profile) as dhis2:
            app.state.live_client = dhis2
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url=_BASE_URL) as http:
                answered = await http.get("/Patient?_content=somsack")

    assert answered.status_code == 400
    assert "`_content`" in answered.json()["issue"][0]["diagnostics"]


def _patient_entry(project: FhirProject, backend: SearchBackend) -> Any:
    """What one run's CapabilityStatement declares about `Patient`, under one search backend."""
    store = load_compiled_store(project)
    settings = ServeSettings(project_dir=project.project_root, live=True, search=SearchConfig(backend=backend))
    statement = build_server_capability(
        project=project,
        store_summary=store.summary(),
        settings=settings,
        register_surface=RegisterSurface.resolve(
            TrackedEntityIndex.from_store(project, store), settings.tracked_entities
        ),
        server_version="9.9.9",
    )
    declared = [
        resource
        for resource in (statement.rest or [])[0].resource or []
        if resource.type == "Patient" and resource.searchParam
    ]
    return declared[0]


def test_the_metadata_declares_the_content_parameter_only_where_it_is_answered(
    capture_project: FhirProject,
) -> None:
    """Which searches this server answers is its contract, so the statement moves with the backend."""
    synced = _patient_entry(capture_project, SearchBackend.PROJECTION)
    live = _patient_entry(capture_project, SearchBackend.DHIS2)

    assert {parameter.name for parameter in synced.searchParam or []} == {"identifier", "_tag", "_content"}
    assert {parameter.name for parameter in live.searchParam or []} == {"identifier", "_tag"}
    assert synced.documentation is not None
    assert "materialized projection" in synced.documentation
    assert live.documentation is not None
    assert "materialized projection" not in live.documentation


@pytest.mark.parametrize("query", ["/Patient", "/Patient?identifier=SCEN-A-0001", "/Patient?_content=somsack"])
async def test_a_projection_nobody_synced_says_so_rather_than_answering_an_empty_register(
    capture_project: FhirProject, probe_profile: Profile, projection_config: ProjectionConfig, query: str
) -> None:
    """ "Nobody matched" and "nobody has looked" are different facts, and only the second is true here."""
    with respx.mock:
        respx.get(f"{_HOST}/api/system/info").mock(return_value=httpx.Response(200, json=_SYSTEM_INFO))
        app: FastAPI = create_app(
            ServeSettings(
                project_dir=capture_project.project_root,
                search=SearchConfig(backend=SearchBackend.PROJECTION),
                projection=projection_config,
            )
        )
        async with app.router.lifespan_context(app), open_client(probe_profile) as dhis2:
            app.state.live_client = dhis2
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url=_BASE_URL) as http:
                answered = await http.get(query)

    assert answered.status_code == 404
    assert "d2w fhir sync" in answered.json()["issue"][0]["diagnostics"]
