"""The materialized projection at many-types scale: six types, five resources, two sharing one.

What the projection has to be true of when a resource is served over several tracked entity types:

- **A sync stores all of them.** The scope a sync walks is the types the register serves, one poll
  apiece, and every row lands under the resource its type is published as. Two types published as
  `Device` fill one `Device` collection with both, and neither displaces the other.
- **Every row remembers which type it is.** The document says so as a `meta.tag`, and the store says
  so as a column, because a page narrowed to one type has to be narrowed by a query rather than
  thinned after one - a thinned page is a short page with more of that type still behind it.
- **A search finds across the union, and `_tag` narrows it to one type.** Both are the same store
  query with one predicate more or less.

Mocked (respx), no application: the store and the sync are exercised directly, which is the layer
these claims live at. `test_register_many_types` is where the same rules are asserted over HTTP.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from dhis2w_client.errors import Dhis2ApiError
from dhis2w_fhir.config import FhirProject, TrackedEntitiesConfig
from dhis2w_fhir_serve.projection.base import ProjectionQuery
from dhis2w_fhir_serve.projection.sqlite_store import SqliteProjectionStore
from dhis2w_fhir_serve.projection.sync import run_sync
from dhis2w_fhir_serve.register.index import TrackedEntityIndex
from dhis2w_fhir_serve.register.surface import RegisterSurface
from dhis2w_fhir_serve.store import load_compiled_store
from fixture_many_types import (
    ASSET_TAG_ATTRIBUTE,
    FRIDGE_TYPE,
    HERD_TYPE,
    MANY_TRACKED_ENTITY_TYPES,
    PERSON_TYPE,
    VEHICLE_TYPE,
    FixtureTrackedEntityType,
    build_many_types_project,
)
from pydantic import BaseModel, ConfigDict

_HOST = "https://dhis2.example"
_TRACKER_PATH = f"{_HOST}/api/tracker/trackedEntities"
_ENROLLMENTS_PATH = f"{_HOST}/api/tracker/enrollments"

#: The zone-less wall-clock reading DHIS2 answers `updatedAt` with (BUGS.md 62).
_READ_AT = "2026-08-20T09:00:00.123"

_OVERLAP = timedelta(seconds=300)


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


def _entity(tracked_entity_uid: str, published: FixtureTrackedEntityType, asset_tag: str) -> dict[str, Any]:
    """One tracked entity as a poll receives it, of one of the fixture's six types."""
    return {
        "trackedEntity": tracked_entity_uid,
        "trackedEntityType": published.uid,
        "orgUnit": "DiszpKrYNg8",
        "updatedAt": _READ_AT,
        "deleted": False,
        "attributes": [{"attribute": ASSET_TAG_ATTRIBUTE, "displayName": "Asset tag", "value": asset_tag}],
        "enrollments": [],
    }


def _page(*entities: dict[str, Any]) -> dict[str, Any]:
    """One page of the tracker collection, counted the way `totalPages=true` counts it."""
    return {
        "pager": {"page": 1, "pageSize": 200, "total": len(entities), "pageCount": 1 if entities else 0},
        "trackedEntities": list(entities),
    }


def _enrollment_page() -> dict[str, Any]:
    """An empty enrollment poll: these types are registered into no program."""
    return {"pager": {"page": 1, "pageSize": 200, "total": 0, "pageCount": 0}, "enrollments": []}


#: One entity per published type, each carrying an asset tag naming what it is.
_ENTITIES: dict[str, dict[str, Any]] = {
    published.uid: _entity(f"Te{index}aaaaaaa", published, f"TAG-{index}")
    for index, published in enumerate(MANY_TRACKED_ENTITY_TYPES)
}


@pytest.fixture
def many_types_project(tmp_path: Path) -> FhirProject:
    """The capture guide with six tracked entity types published over five FHIR resource types."""
    return build_many_types_project(tmp_path / "project")


@pytest.fixture
async def reader() -> _Reader:
    """The connection a sync reads DHIS2 through, pointed at the mocked host."""
    return _Reader(connection=httpx.AsyncClient(base_url=_HOST))


@pytest.fixture
def store(tmp_path: Path) -> SqliteProjectionStore:
    """An empty projection in a directory of this test's own."""
    return SqliteProjectionStore(tmp_path / "projection.sqlite")


def _surface(project: FhirProject) -> RegisterSurface:
    """What this run serves, which with the table left empty is every type the forms register."""
    return RegisterSurface.resolve(
        TrackedEntityIndex.from_store(project, load_compiled_store(project)), TrackedEntitiesConfig()
    )


async def _sync_every_type(project: FhirProject, store: SqliteProjectionStore, reader: _Reader) -> Any:
    """Materialize one entity of every published type, each poll answering only about its own type."""
    with respx.mock:
        for uid, entity in _ENTITIES.items():
            respx.get(_TRACKER_PATH, params__contains={"trackedEntityType": uid}).mock(
                return_value=httpx.Response(200, json=_page(entity))
            )
        respx.get(_ENROLLMENTS_PATH).mock(return_value=httpx.Response(200, json=_enrollment_page()))
        return await run_sync(
            reader,
            surface=_surface(project),
            store=store,
            project_root=project.project_root,
            store_path=store.database_path,
            overlap=_OVERLAP,
        )


async def test_a_sync_stores_every_type_under_the_resource_its_map_row_names(
    many_types_project: FhirProject, store: SqliteProjectionStore, reader: _Reader
) -> None:
    """Six types, six rows, each under the resource the published map takes it onto."""
    await _sync_every_type(many_types_project, store, reader)

    for published in MANY_TRACKED_ENTITY_TYPES:
        entity = _ENTITIES[published.uid]
        held = await store.read(published.resource_type, entity["trackedEntity"])
        assert held is not None, published.uid
        assert held.body["resourceType"] == published.resource_type
        assert held.tracked_entity_type_uid == published.uid
        assert [tag["code"] for tag in held.body["meta"]["tag"]] == [published.uid]


async def test_two_types_sharing_a_resource_fill_one_collection_with_both(
    many_types_project: FhirProject, store: SqliteProjectionStore, reader: _Reader
) -> None:
    """THE SHARED-RESOURCE ANSWER, in the store: `Device` holds the fridge and the vehicle alike."""
    await _sync_every_type(many_types_project, store, reader)

    page = await store.search(ProjectionQuery(resource_type="Device"))

    assert page.total == 2
    assert {resource.tracked_entity_type_uid for resource in page.resources} == {FRIDGE_TYPE.uid, VEHICLE_TYPE.uid}


async def test_the_sync_report_states_one_line_per_resource_the_types_landed_under(
    many_types_project: FhirProject, store: SqliteProjectionStore, reader: _Reader
) -> None:
    """Five resources from six types, and the `Device` line counts both of the types behind it."""
    report = await _sync_every_type(many_types_project, store, reader)

    counted = {row.resource_type: row.created for row in report.counts}
    assert counted == {"Patient": 1, "Device": 2, "Group": 1, "Specimen": 1, "Location": 1}


async def test_a_query_narrowed_to_one_type_answers_that_type_alone(
    many_types_project: FhirProject, store: SqliteProjectionStore, reader: _Reader
) -> None:
    """What `_tag` becomes at the store: one predicate more, and a page that is a page of one type."""
    await _sync_every_type(many_types_project, store, reader)

    page = await store.search(ProjectionQuery(resource_type="Device", tracked_entity_type_uids=(VEHICLE_TYPE.uid,)))

    assert page.total == 1
    assert [resource.tracked_entity_type_uid for resource in page.resources] == [VEHICLE_TYPE.uid]


async def test_an_identifier_query_narrowed_to_the_wrong_type_finds_nobody(
    many_types_project: FhirProject, store: SqliteProjectionStore, reader: _Reader
) -> None:
    """A tag and an identifier are conditions that both hold, so the fridge's tag is not the vehicle's."""
    await _sync_every_type(many_types_project, store, reader)
    fridge_tag = _ENTITIES[FRIDGE_TYPE.uid]["attributes"][0]["value"]

    found = await store.search(
        ProjectionQuery(resource_type="Device", identifiers=(fridge_tag,), tracked_entity_type_uids=(FRIDGE_TYPE.uid,))
    )
    missed = await store.search(
        ProjectionQuery(resource_type="Device", identifiers=(fridge_tag,), tracked_entity_type_uids=(VEHICLE_TYPE.uid,))
    )

    assert [resource.resource_id for resource in found.resources] == [_ENTITIES[FRIDGE_TYPE.uid]["trackedEntity"]]
    assert missed.resources == ()


async def test_an_identifier_search_over_a_shared_resource_finds_across_its_types(
    many_types_project: FhirProject, store: SqliteProjectionStore, reader: _Reader
) -> None:
    """Naming no type is naming the union: the vehicle's tag is found under `Device` without a hint."""
    await _sync_every_type(many_types_project, store, reader)
    vehicle_tag = _ENTITIES[VEHICLE_TYPE.uid]["attributes"][0]["value"]

    page = await store.search(ProjectionQuery(resource_type="Device", identifiers=(vehicle_tag,)))

    assert [resource.tracked_entity_type_uid for resource in page.resources] == [VEHICLE_TYPE.uid]


@pytest.mark.parametrize("published", (PERSON_TYPE, HERD_TYPE), ids=lambda published: published.uid)
async def test_a_resource_serving_one_type_is_narrowed_by_that_type_and_by_no_other(
    many_types_project: FhirProject,
    store: SqliteProjectionStore,
    reader: _Reader,
    published: FixtureTrackedEntityType,
) -> None:
    """A register of one type narrows to itself and to nothing else, which is the degenerate union."""
    await _sync_every_type(many_types_project, store, reader)

    own = await store.search(
        ProjectionQuery(resource_type=published.resource_type, tracked_entity_type_uids=(published.uid,))
    )
    other = await store.search(
        ProjectionQuery(resource_type=published.resource_type, tracked_entity_type_uids=(FRIDGE_TYPE.uid,))
    )

    assert own.total == 1
    assert other.total == 0
