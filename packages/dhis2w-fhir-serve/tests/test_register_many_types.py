"""Many tracked entity types on one instance, and two of them the same FHIR resource.

THE QUESTION THIS FILE ANSWERS. Two DHIS2 tracked entity types are both mapped to `Device`. What is
`GET /Device`? The answer this facade converged on, and the answer every test below pins:

**One FHIR resource type is one register surface serving the union of its tracked entity types.**
There is no collision, no refusal, and no last-writer-wins. `D2TET_CM` is read into one row per type;
`RegisterSurface.registers()` groups the rows by resource; and the read, the search, the listing, and
the count are all parameterized by the list of types the resource is served over. `/metadata`
declares one entry per resource naming every type behind it. Each served resource still says which
DHIS2 type it is, as a `meta.tag` under `{base}/id/tracked-entity-type`, so a union is a union of
stated things rather than a merge that loses which is which.

**`_tag` is how a caller asks that union about one of its types.** It is R4's own token search over
`meta.tag`, which is the very element the resource states the type in - so the parameter reads what
the resource says rather than naming a dimension this server invented. It narrows the listing walk,
the identifier search, and `_count=0` alike, and it rides the listing's own links so a walk stays
inside the type it started in.

Mocked (respx), on the same terms as `test_register_listing.py`: the fixture guide is compiled from
disk and a DHIS2 client against a mocked host is put on `app.state.live_client`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
import respx
from dhis2w_client.generated.v42.oas import TrackerTrackedEntity
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import Profile
from dhis2w_fhir.config import FhirProject, TrackedEntitiesConfig
from dhis2w_fhir_serve.app import create_app
from dhis2w_fhir_serve.capability import build_server_capability
from dhis2w_fhir_serve.register.index import TrackedEntityIndex
from dhis2w_fhir_serve.register.projection import registered_entity_for
from dhis2w_fhir_serve.register.surface import RegisterSurface
from dhis2w_fhir_serve.settings import ServeSettings
from dhis2w_fhir_serve.store import load_compiled_store
from fastapi import FastAPI
from fixture_many_types import (
    ASSET_TAG_IDENTIFIER_SYSTEM,
    FRIDGE_TYPE,
    HERD_TYPE,
    MANY_REGISTER_RESOURCE_TYPES,
    MANY_TRACKED_ENTITY_TYPES,
    PERSON_TYPE,
    SPECIMEN_TYPE,
    VEHICLE_TYPE,
    WATER_POINT_TYPE,
    FixtureTrackedEntityType,
    build_many_types_project,
)
from fixture_project import CAPTURE_IDENTIFIER_BASE

_HOST = "https://dhis2.example"
_BASE_URL = "http://serve.test"
_SYSTEM_INFO = {"version": "2.42.0"}
_TRACKER_URL = f"{_HOST}/api/tracker/trackedEntities"

#: The system a `_tag` names a tracked entity type under, which is the system the resource tags with.
_TYPE_SYSTEM = f"{CAPTURE_IDENTIFIER_BASE}/id/tracked-entity-type"

_PROFILES_TOML = """
default = "probe"

[profiles.probe]
base_url = "https://dhis2.example"
auth = "basic"
username = "admin"
password = "district"
"""


@pytest.fixture
def many_types_project(tmp_path: Path) -> FhirProject:
    """The capture guide with six tracked entity types published over five FHIR resource types."""
    return build_many_types_project(tmp_path / "project")


@pytest.fixture
def many_types_surface(many_types_project: FhirProject) -> RegisterSurface:
    """What a run over that guide serves, with `[serve.tracked_entities]` left at its defaults."""
    store = load_compiled_store(many_types_project)
    return RegisterSurface.resolve(TrackedEntityIndex.from_store(many_types_project, store), TrackedEntitiesConfig())


@pytest.fixture
def many_types_profile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Profile:
    """A Basic profile against the mocked host, resolvable from a config home of this test's own."""
    config_directory = tmp_path / ".config" / "dhis2"
    config_directory.mkdir(parents=True)
    (config_directory / "profiles.toml").write_text(_PROFILES_TOML, encoding="utf-8")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_directory.parent))
    monkeypatch.delenv("DHIS2_PROFILE", raising=False)
    return Profile(base_url=_HOST, auth="basic", username="admin", password="district")


@pytest.fixture
async def many_types_client(
    many_types_project: FhirProject, many_types_profile: Profile
) -> AsyncIterator[httpx.AsyncClient]:
    """The facade over the six-type guide, holding a DHIS2 client against the mocked host."""
    with respx.mock:
        respx.get(f"{_HOST}/api/system/info").mock(return_value=httpx.Response(200, json=_SYSTEM_INFO))
        app: FastAPI = create_app(ServeSettings(project_dir=many_types_project.project_root))
        async with (
            app.router.lifespan_context(app),
            open_client(many_types_profile) as dhis2,
        ):
            app.state.live_client = dhis2
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url=_BASE_URL) as http:
                yield http


def _entity(tracked_entity_uid: str, published: FixtureTrackedEntityType, asset_tag: str | None = None) -> Any:
    """One tracked entity as the tracker endpoint sends it, of one of the fixture's types."""
    attributes = [] if asset_tag is None else [{"attribute": "TeaAssetTg1", "value": asset_tag}]
    return {
        "trackedEntity": tracked_entity_uid,
        "trackedEntityType": published.uid,
        "orgUnit": "DiszpKrYNg8",
        "attributes": attributes,
        "enrollments": [],
    }


def _page(*entities: Any, page: int = 1, page_size: int = 20, total: int | None = None) -> dict[str, Any]:
    """One page as `totalPages=true` answers it: the array, and the pager stating where it sits."""
    pager: dict[str, Any] = {"page": page, "pageSize": page_size}
    if total is not None:
        pager["total"] = total
        pager["pageCount"] = -(-total // page_size)
    return {"pager": pager, "trackedEntities": list(entities)}


def _route(published: FixtureTrackedEntityType, page: dict[str, Any]) -> Any:
    """Mock the tracker collection for one tracked entity type and nothing else."""
    return respx.get(_TRACKER_URL, params__contains={"trackedEntityType": published.uid}).mock(
        return_value=httpx.Response(200, json=page)
    )


def _link(bundle: dict[str, Any], relation: str) -> str | None:
    """One relation's URL out of a Bundle's links, or None when the Bundle offers no such link."""
    return next((link["url"] for link in bundle.get("link", []) if link["relation"] == relation), None)


def _query(url: str) -> dict[str, list[str]]:
    """The query parameters of one link, so a test asserts what a client would send back."""
    return parse_qs(urlsplit(url).query)


# --------------------------------------------------------------------------------------------------
# What the published map becomes


def test_the_map_becomes_one_register_per_resource_over_the_union_of_its_types(
    many_types_surface: RegisterSurface,
) -> None:
    """THE SHARED-RESOURCE ANSWER: one resource, every type it was mapped from, nothing dropped."""
    registers = {register.resource_type: register for register in many_types_surface.registers()}

    assert tuple(registers) == MANY_REGISTER_RESOURCE_TYPES
    assert [published.uid for published in registers["Device"].tracked_entity_types] == [
        FRIDGE_TYPE.uid,
        VEHICLE_TYPE.uid,
    ]
    assert [published.name for published in registers["Device"].tracked_entity_types] == [
        FRIDGE_TYPE.name,
        VEHICLE_TYPE.name,
    ]
    assert [published.uid for published in registers["Patient"].tracked_entity_types] == [PERSON_TYPE.uid]


def test_every_published_type_reaches_the_register_and_none_shadows_another(
    many_types_surface: RegisterSurface,
) -> None:
    """Six types over five resources is six served types: a shared resource merges no row away."""
    assert [published.uid for published in many_types_surface.served_types] == [
        published.uid for published in MANY_TRACKED_ENTITY_TYPES
    ]
    assert many_types_surface.register_resource_types() == MANY_REGISTER_RESOURCE_TYPES


@pytest.mark.parametrize("published", MANY_TRACKED_ENTITY_TYPES, ids=lambda published: published.uid)
def test_a_resource_is_served_over_exactly_its_own_types(
    many_types_surface: RegisterSurface, published: FixtureTrackedEntityType
) -> None:
    """Each type rides the resource its row names, and a resource answers over every type that named it."""
    assert published.uid in many_types_surface.tracked_entity_type_uids_for(published.resource_type)


@pytest.mark.parametrize("published", MANY_TRACKED_ENTITY_TYPES, ids=lambda published: published.uid)
def test_a_registered_entity_states_which_dhis2_type_it_is(
    many_types_project: FhirProject, many_types_surface: RegisterSurface, published: FixtureTrackedEntityType
) -> None:
    """A union is a union of stated things: every served resource tags the type it came from."""
    entity = TrackerTrackedEntity.model_validate(_entity("TeAaaaaaaa1", published))

    registered = registered_entity_for(entity, many_types_surface.index, published.resource_type)

    assert registered.resourceType == published.resource_type
    assert registered.meta is not None
    assert [(tag.system, tag.code) for tag in registered.meta.tag or []] == [(_TYPE_SYSTEM, published.uid)]


def test_the_metadata_declares_one_resource_per_register_naming_every_type_behind_it(
    many_types_project: FhirProject,
) -> None:
    """A client reading the statement learns what a `Device` hit can be before it asks for one."""
    store = load_compiled_store(many_types_project)
    tracked_entities = TrackedEntitiesConfig()
    capability = build_server_capability(
        project=many_types_project,
        store_summary=store.summary(),
        settings=ServeSettings(project_dir=many_types_project.project_root, live=True),
        register_surface=RegisterSurface.resolve(
            TrackedEntityIndex.from_store(many_types_project, store), tracked_entities
        ),
        server_version="9.9.9",
    )

    rest = capability.rest or []
    declared = {
        resource.type: resource for resource in rest[0].resource or [] if resource.type in MANY_REGISTER_RESOURCE_TYPES
    }
    assert set(declared) == set(MANY_REGISTER_RESOURCE_TYPES)
    device = declared["Device"].documentation or ""
    assert f"{FRIDGE_TYPE.name} ({FRIDGE_TYPE.uid})" in device
    assert f"{VEHICLE_TYPE.name} ({VEHICLE_TYPE.uid})" in device
    tag = next(parameter for parameter in declared["Device"].searchParam or [] if parameter.name == "_tag")
    assert tag.type == "token"
    assert _TYPE_SYSTEM in (tag.documentation or "")


# --------------------------------------------------------------------------------------------------
# What a shared resource actually serves


async def test_a_shared_resource_lists_both_of_its_types_in_one_walk(
    many_types_client: httpx.AsyncClient,
) -> None:
    """`GET /Device` is the fridges and the vehicles, walked in the order the forms register them."""
    _route(FRIDGE_TYPE, _page(_entity("TeFridge001", FRIDGE_TYPE), total=1))
    _route(VEHICLE_TYPE, _page(_entity("TeVehicle01", VEHICLE_TYPE), total=1))

    first = (await many_types_client.get("/Device?_count=1")).json()
    following = _link(first, "next")
    assert following is not None
    second = (await many_types_client.get(following.replace(_BASE_URL, ""))).json()

    assert [entry["resource"]["id"] for entry in first["entry"]] == ["TeFridge001"]
    assert [entry["resource"]["id"] for entry in second["entry"]] == ["TeVehicle01"]
    assert first["total"] == 2
    assert [entry["resource"]["meta"]["tag"][0]["code"] for entry in second["entry"]] == [VEHICLE_TYPE.uid]


async def test_a_tag_narrows_a_shared_resource_to_one_of_its_types(
    many_types_client: httpx.AsyncClient,
) -> None:
    """`_tag` asks the union about one half of it, and the other half is never asked about."""
    fridges = _route(FRIDGE_TYPE, _page(_entity("TeFridge001", FRIDGE_TYPE), total=1))
    vehicles = _route(VEHICLE_TYPE, _page(_entity("TeVehicle01", VEHICLE_TYPE), total=1))

    response = await many_types_client.get(f"/Device?_tag={_TYPE_SYSTEM}|{FRIDGE_TYPE.uid}")

    assert response.status_code == 200
    assert [entry["resource"]["id"] for entry in response.json()["entry"]] == ["TeFridge001"]
    assert fridges.called
    assert not vehicles.called


async def test_a_bare_tag_names_the_type_code_alone(many_types_client: httpx.AsyncClient) -> None:
    """One tag rides these resources, so a code with no system has no ambiguity to fall into."""
    _route(FRIDGE_TYPE, _page(_entity("TeFridge001", FRIDGE_TYPE), total=1))
    vehicles = _route(VEHICLE_TYPE, _page(_entity("TeVehicle01", VEHICLE_TYPE), total=1))

    response = await many_types_client.get(f"/Device?_tag={FRIDGE_TYPE.uid}")

    assert [entry["resource"]["id"] for entry in response.json()["entry"]] == ["TeFridge001"]
    assert not vehicles.called


async def test_two_tags_widen_the_way_two_identifiers_do(many_types_client: httpx.AsyncClient) -> None:
    """Values of one token parameter are alternatives, so naming both types is naming the whole union."""
    _route(FRIDGE_TYPE, _page(_entity("TeFridge001", FRIDGE_TYPE), total=1))
    _route(VEHICLE_TYPE, _page(_entity("TeVehicle01", VEHICLE_TYPE), total=1))

    response = await many_types_client.get(f"/Device?_tag={FRIDGE_TYPE.uid},{VEHICLE_TYPE.uid}&_count=5")

    assert response.json()["total"] == 2


async def test_a_tag_rides_every_link_of_the_listing_it_narrowed(
    many_types_client: httpx.AsyncClient,
) -> None:
    """A `next` that dropped the tag would walk out of the type the client asked about."""
    _route(FRIDGE_TYPE, _page(_entity("TeFridge001", FRIDGE_TYPE), page_size=1, total=2))

    bundle = (await many_types_client.get(f"/Device?_tag={FRIDGE_TYPE.uid}&_count=1")).json()

    for relation in ("self", "next"):
        url = _link(bundle, relation)
        assert url is not None, relation
        assert _query(url)["_tag"] == [FRIDGE_TYPE.uid], relation


async def test_a_tag_naming_a_type_this_resource_does_not_serve_matches_nothing(
    many_types_client: httpx.AsyncClient,
) -> None:
    """An unsatisfied token is an empty searchset, and nothing upstream is asked to confirm it."""
    fridges = _route(FRIDGE_TYPE, _page(_entity("TeFridge001", FRIDGE_TYPE), total=1))

    response = await many_types_client.get(f"/Device?_tag={SPECIMEN_TYPE.uid}")

    assert response.status_code == 200
    bundle = response.json()
    assert bundle["total"] == 0
    assert "entry" not in bundle
    assert not fridges.called


async def test_a_tag_under_a_system_this_guide_publishes_nothing_for_matches_nothing(
    many_types_client: httpx.AsyncClient,
) -> None:
    """A token naming another vocabulary is a question about something else, not about these types."""
    fridges = _route(FRIDGE_TYPE, _page(_entity("TeFridge001", FRIDGE_TYPE), total=1))

    response = await many_types_client.get(f"/Device?_tag=http://example.org/tags|{FRIDGE_TYPE.uid}")

    assert response.json()["total"] == 0
    assert not fridges.called


async def test_an_identifier_search_over_a_shared_resource_tries_every_type_it_serves(
    many_types_client: httpx.AsyncClient,
) -> None:
    """A caller holding an asset tag does not have to know whether it is on a fridge or a vehicle."""
    respx.get(f"{_HOST}/api/tracker/trackedEntities/FRIDGE-0001").mock(return_value=httpx.Response(404))
    fridges = _route(FRIDGE_TYPE, _page(_entity("TeFridge001", FRIDGE_TYPE, asset_tag="FRIDGE-0001")))
    vehicles = _route(VEHICLE_TYPE, _page())
    respx.get(f"{_HOST}/api/tracker/trackedEntities/TeFridge001").mock(
        return_value=httpx.Response(200, json=_entity("TeFridge001", FRIDGE_TYPE, asset_tag="FRIDGE-0001"))
    )

    response = await many_types_client.get(f"/Device?identifier={ASSET_TAG_IDENTIFIER_SYSTEM}|FRIDGE-0001")

    assert [entry["resource"]["id"] for entry in response.json()["entry"]] == ["TeFridge001"]
    assert fridges.called
    assert vehicles.called


async def test_an_identifier_search_narrowed_by_a_tag_asks_one_type_only(
    many_types_client: httpx.AsyncClient,
) -> None:
    """`_tag` narrows a search as it narrows a listing: one upstream query rather than two."""
    respx.get(f"{_HOST}/api/tracker/trackedEntities/FRIDGE-0001").mock(return_value=httpx.Response(404))
    fridges = _route(FRIDGE_TYPE, _page(_entity("TeFridge001", FRIDGE_TYPE, asset_tag="FRIDGE-0001")))
    vehicles = _route(VEHICLE_TYPE, _page())
    respx.get(f"{_HOST}/api/tracker/trackedEntities/TeFridge001").mock(
        return_value=httpx.Response(200, json=_entity("TeFridge001", FRIDGE_TYPE, asset_tag="FRIDGE-0001"))
    )

    response = await many_types_client.get(
        f"/Device?identifier={ASSET_TAG_IDENTIFIER_SYSTEM}|FRIDGE-0001&_tag={FRIDGE_TYPE.uid}"
    )

    assert [entry["resource"]["id"] for entry in response.json()["entry"]] == ["TeFridge001"]
    assert fridges.called
    assert not vehicles.called


async def test_the_register_size_counts_the_union_and_a_tag_counts_one_type(
    many_types_client: httpx.AsyncClient,
) -> None:
    """`_count=0` asks how large the register is, and beside a `_tag` how large one type's part of it is."""
    _route(FRIDGE_TYPE, _page(total=7))
    _route(VEHICLE_TYPE, _page(total=4))

    whole = (await many_types_client.get("/Device?_count=0")).json()
    fridges = (await many_types_client.get(f"/Device?_count=0&_tag={FRIDGE_TYPE.uid}")).json()

    assert whole["total"] == 11
    assert fridges["total"] == 7
    assert _query(_link(fridges, "self") or "")["_tag"] == [FRIDGE_TYPE.uid]


async def test_a_read_answers_only_under_the_resource_the_entity_type_is_served_as(
    many_types_client: httpx.AsyncClient,
) -> None:
    """A fridge read as a `Group` is not found: a resource never hands back a type it does not serve."""
    respx.get(f"{_HOST}/api/tracker/trackedEntities/TeFridge001").mock(
        return_value=httpx.Response(200, json=_entity("TeFridge001", FRIDGE_TYPE))
    )

    served = await many_types_client.get("/Device/TeFridge001")
    other = await many_types_client.get("/Group/TeFridge001")

    assert served.status_code == 200
    assert served.json()["meta"]["tag"][0]["code"] == FRIDGE_TYPE.uid
    assert other.status_code == 404


@pytest.mark.parametrize(
    "published", (PERSON_TYPE, SPECIMEN_TYPE, HERD_TYPE, WATER_POINT_TYPE), ids=lambda published: published.uid
)
async def test_every_resource_the_map_names_answers_its_own_listing(
    many_types_client: httpx.AsyncClient, published: FixtureTrackedEntityType
) -> None:
    """Five resources are five register addresses, each one paged by the same machinery."""
    _route(published, _page(_entity("TeAaaaaaaa1", published), total=1))

    bundle = (await many_types_client.get(f"/{published.resource_type}?_count=5")).json()

    assert [entry["resource"]["resourceType"] for entry in bundle["entry"]] == [published.resource_type]
    assert bundle["entry"][0]["resource"]["meta"]["tag"][0]["code"] == published.uid
