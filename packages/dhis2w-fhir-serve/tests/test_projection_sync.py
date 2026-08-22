"""`d2w fhir sync` from the inside: what it puts on the wire, what it writes, and what it refuses to.

Mocked (respx); no live stack and no application. The register surface is the compiled capture
fixture - the same guide `test_register.py` runs against - so the resources this sync writes are the
resources a live register read would answer with, produced by the same `registered_entity_for`.

Three families of claim. **The wire**: `includeDeleted=true` on every poll, because section 3.4's
finding 2 is that its absence is silent; a stable `createdAt` order, because paging by the column the
filter moves is how a walk drops a row; and `updatedAfter` in the instance's own zone-less spelling.
**The watermark**: it comes off the rows rather than off this host's clock, it advances after its walk
rather than during it, and a run that never finished advances nothing. **The counts**: created,
updated, and removed are read out of the projection rather than assumed, so the report says what
happened rather than how many rows went past.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from dhis2w_client.errors import Dhis2ApiError
from dhis2w_fhir.config import FhirProject, TrackedEntitiesConfig
from dhis2w_fhir_serve.projection.base import ProjectionQuery
from dhis2w_fhir_serve.projection.sqlite_store import SqliteProjectionStore
from dhis2w_fhir_serve.projection.sync import SyncMode, run_sync
from dhis2w_fhir_serve.register.index import TrackedEntityIndex
from dhis2w_fhir_serve.register.surface import RegisterSurface
from dhis2w_fhir_serve.store import load_compiled_store
from fixture_project import (
    REGISTRATION_PROGRAM_UID,
    REGISTRATION_TRACKED_ENTITY_TYPE_UID,
    REGISTRATION_UNIQUE_ATTRIBUTE,
)
from pydantic import BaseModel, ConfigDict

_HOST = "https://dhis2.example"
_TRACKER_PATH = f"{_HOST}/api/tracker/trackedEntities"
_ENROLLMENTS_PATH = f"{_HOST}/api/tracker/enrollments"

_PERSON_UID = "PLoWmEuLJl2"
_OTHER_PERSON_UID = "QaTbMxTeS01"
_NATIONAL_ID = "SCEN-A-0001"

#: The zone-less wall-clock readings DHIS2 2.43 answers `updatedAt` with (BUGS.md 62).
_FIRST_READ = "2026-08-20T09:00:00.123"
_SECOND_READ = "2026-08-21T09:00:00.456"

_OVERLAP = timedelta(seconds=300)


class _Reader(BaseModel):
    """A `RegisterReader` over one respx-mocked host, which is what a sync is handed."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    connection: httpx.AsyncClient

    async def get_raw(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Read one DHIS2 path, answering the parsed JSON body and raising on a refusal.

        Raising is the part that matters: a sync that walked on past a 500 would advance a watermark
        over rows it never read, which is the one failure the design has no way back from.
        """
        answer = await self.connection.get(path, params=params)
        if answer.status_code >= 400:
            raise Dhis2ApiError(status_code=answer.status_code, message=answer.reason_phrase, body=answer.json())
        body = answer.json()
        return body if isinstance(body, dict) else {"data": body}


def _entity(
    tracked_entity_uid: str = _PERSON_UID,
    *,
    national_id: str = _NATIONAL_ID,
    updated_at: str = _FIRST_READ,
    deleted: bool = False,
) -> dict[str, Any]:
    """One tracked entity as a poll receives it - the register's own fields plus the two a sync reads."""
    return {
        "trackedEntity": tracked_entity_uid,
        "trackedEntityType": REGISTRATION_TRACKED_ENTITY_TYPE_UID,
        "orgUnit": "DiszpKrYNg8",
        "updatedAt": updated_at,
        "deleted": deleted,
        "attributes": [
            {"attribute": REGISTRATION_UNIQUE_ATTRIBUTE, "displayName": "National identifier", "value": national_id}
        ],
    }


def _page(*entities: dict[str, Any]) -> dict[str, Any]:
    """One page of the tracker collection, counted the way `totalPages=true` counts it."""
    return {
        "pager": {"page": 1, "pageSize": 200, "total": len(entities), "pageCount": 1 if entities else 0},
        "trackedEntities": list(entities),
    }


def _enrollment_page(*rows: dict[str, Any]) -> dict[str, Any]:
    """One page of the enrollment poll, which carries whose projection moved and nothing else."""
    return {
        "pager": {"page": 1, "pageSize": 200, "total": len(rows), "pageCount": 1 if rows else 0},
        "enrollments": list(rows),
    }


def _surface(project: FhirProject) -> RegisterSurface:
    """What this run serves, narrowed to the one tracked entity type the fixture registers as a person."""
    return RegisterSurface.resolve(
        TrackedEntityIndex.from_store(project, load_compiled_store(project)),
        TrackedEntitiesConfig(tracked_entity_types=[REGISTRATION_TRACKED_ENTITY_TYPE_UID]),
    )


@pytest.fixture
async def reader() -> _Reader:
    """The connection a sync reads DHIS2 through, pointed at the mocked host."""
    return _Reader(connection=httpx.AsyncClient(base_url=_HOST))


@pytest.fixture
def store(tmp_path: Path) -> SqliteProjectionStore:
    """An empty projection in a directory of this test's own."""
    return SqliteProjectionStore(tmp_path / "projection.sqlite")


async def _sync(
    project: FhirProject,
    store: SqliteProjectionStore,
    reader: _Reader,
    *,
    rebuild: bool = False,
    dry_run: bool = False,
) -> Any:
    """Run one sync over the mocked instance with the fixture's own register surface."""
    return await run_sync(
        reader,
        surface=_surface(project),
        store=store,
        project_root=project.project_root,
        store_path=store.database_path,
        overlap=_OVERLAP,
        rebuild=rebuild,
        dry_run=dry_run,
    )


async def test_the_first_run_reads_the_whole_scope_and_writes_what_a_live_read_would_answer(
    capture_project: FhirProject, store: SqliteProjectionStore, reader: _Reader
) -> None:
    """An initial materialization projects each page through the register's own mapping surface."""
    with respx.mock:
        respx.get(_TRACKER_PATH).mock(return_value=httpx.Response(200, json=_page(_entity())))
        respx.get(_ENROLLMENTS_PATH).mock(return_value=httpx.Response(200, json=_enrollment_page()))

        report = await _sync(capture_project, store, reader)

    held = await store.read("Patient", _PERSON_UID)
    assert report.mode is SyncMode.INITIAL
    assert held is not None
    assert held.body["resourceType"] == "Patient"
    assert held.body["id"] == _PERSON_UID
    assert {entry["value"] for entry in held.body["identifier"]} == {_PERSON_UID, _NATIONAL_ID}
    assert [(row.resource_type, row.created, row.updated, row.removed) for row in report.counts] == [
        ("Patient", 1, 0, 0)
    ]


async def test_every_poll_carries_include_deleted_and_a_stable_order(
    capture_project: FhirProject, store: SqliteProjectionStore, reader: _Reader
) -> None:
    """Finding 2 of section 3.4: without it a sync never learns that anybody left, and does not error."""
    with respx.mock:
        entities = respx.get(_TRACKER_PATH).mock(return_value=httpx.Response(200, json=_page(_entity())))
        enrollments = respx.get(_ENROLLMENTS_PATH).mock(return_value=httpx.Response(200, json=_enrollment_page()))

        await _sync(capture_project, store, reader)

    for route in (entities, enrollments):
        assert route.calls
        for call in route.calls:
            assert call.request.url.params["includeDeleted"] == "true"
            assert call.request.url.params["order"] == "createdAt:asc"


async def test_the_enrollment_poll_is_scoped_by_program_because_the_endpoint_admits_nothing_else(
    capture_project: FhirProject, store: SqliteProjectionStore, reader: _Reader
) -> None:
    """`/api/tracker/enrollments` answers `E1003 "Program is mandatory"` to any other scope (BUGS.md 102)."""
    with respx.mock:
        respx.get(_TRACKER_PATH).mock(return_value=httpx.Response(200, json=_page(_entity())))
        enrollments = respx.get(_ENROLLMENTS_PATH).mock(return_value=httpx.Response(200, json=_enrollment_page()))

        report = await _sync(capture_project, store, reader)

    assert REGISTRATION_PROGRAM_UID in report.programs
    assert {call.request.url.params["program"] for call in enrollments.calls} == set(report.programs)


async def test_the_watermark_comes_off_the_rows_rather_than_off_this_hosts_clock(
    capture_project: FhirProject, store: SqliteProjectionStore, reader: _Reader
) -> None:
    """A cursor read out of the instance's own answer goes back on the wire exactly as it arrived."""
    with respx.mock:
        respx.get(_TRACKER_PATH).mock(return_value=httpx.Response(200, json=_page(_entity(updated_at=_FIRST_READ))))
        respx.get(_ENROLLMENTS_PATH).mock(
            return_value=httpx.Response(
                200,
                json=_enrollment_page(
                    {"enrollment": "EnrAnc00001", "trackedEntity": _PERSON_UID, "updatedAt": _FIRST_READ}
                ),
            )
        )

        report = await _sync(capture_project, store, reader)

    assert (await store.watermarks()).tracked_entities == datetime.fromisoformat(_FIRST_READ)
    assert report.cursor.updated_at == datetime.fromisoformat(_FIRST_READ)
    assert [move.moved() for move in report.cursors] == [True, True]


async def test_the_second_run_polls_from_the_watermark_less_the_overlap(
    capture_project: FhirProject, store: SqliteProjectionStore, reader: _Reader
) -> None:
    """Rule 2: a poll from exactly the watermark drops the rows written in the instant it was reading."""
    with respx.mock:
        respx.get(_TRACKER_PATH).mock(return_value=httpx.Response(200, json=_page(_entity())))
        respx.get(_ENROLLMENTS_PATH).mock(return_value=httpx.Response(200, json=_enrollment_page()))
        await _sync(capture_project, store, reader)

    with respx.mock:
        entities = respx.get(_TRACKER_PATH).mock(return_value=httpx.Response(200, json=_page()))
        respx.get(_ENROLLMENTS_PATH).mock(return_value=httpx.Response(200, json=_enrollment_page()))

        report = await _sync(capture_project, store, reader)

    asked = entities.calls.last.request.url.params["updatedAfter"]
    assert report.mode is SyncMode.INCREMENTAL
    assert datetime.fromisoformat(asked) == datetime.fromisoformat(_FIRST_READ).replace(microsecond=0) - _OVERLAP


async def test_a_tombstone_removes_the_row_and_is_counted_as_a_removal(
    capture_project: FhirProject, store: SqliteProjectionStore, reader: _Reader
) -> None:
    """R10: a deletion means "remove the row", never "archive the final state" - there is none to archive."""
    with respx.mock:
        respx.get(_TRACKER_PATH).mock(return_value=httpx.Response(200, json=_page(_entity())))
        respx.get(_ENROLLMENTS_PATH).mock(return_value=httpx.Response(200, json=_enrollment_page()))
        await _sync(capture_project, store, reader)

    with respx.mock:
        respx.get(_TRACKER_PATH).mock(
            return_value=httpx.Response(200, json=_page(_entity(updated_at=_SECOND_READ, deleted=True)))
        )
        respx.get(_ENROLLMENTS_PATH).mock(return_value=httpx.Response(200, json=_enrollment_page()))

        report = await _sync(capture_project, store, reader)

    assert await store.read("Patient", _PERSON_UID) is None
    assert [(row.created, row.updated, row.removed) for row in report.counts] == [(0, 0, 1)]


async def test_a_second_read_of_an_unchanged_row_is_counted_as_an_update_rather_than_a_creation(
    capture_project: FhirProject, store: SqliteProjectionStore, reader: _Reader
) -> None:
    """The counts are read out of the projection, so an overlap re-read is honestly an update."""
    with respx.mock:
        respx.get(_TRACKER_PATH).mock(return_value=httpx.Response(200, json=_page(_entity())))
        respx.get(_ENROLLMENTS_PATH).mock(return_value=httpx.Response(200, json=_enrollment_page()))
        await _sync(capture_project, store, reader)

    with respx.mock:
        respx.get(_TRACKER_PATH).mock(return_value=httpx.Response(200, json=_page(_entity())))
        respx.get(_ENROLLMENTS_PATH).mock(return_value=httpx.Response(200, json=_enrollment_page()))

        report = await _sync(capture_project, store, reader)

    assert [(row.created, row.updated, row.removed) for row in report.counts] == [(0, 1, 0)]
    assert (await store.search(ProjectionQuery(resource_type="Patient"))).total == 1


async def test_an_enrollment_that_moved_re_reads_the_entity_it_names(
    capture_project: FhirProject, store: SqliteProjectionStore, reader: _Reader
) -> None:
    """A tracked entity's own `lastUpdated` does not move when one of its enrollments does."""
    with respx.mock:
        respx.get(_TRACKER_PATH).mock(return_value=httpx.Response(200, json=_page(_entity())))
        respx.get(_ENROLLMENTS_PATH).mock(return_value=httpx.Response(200, json=_enrollment_page()))
        await _sync(capture_project, store, reader)

    with respx.mock:
        # The tracked entity poll finds nothing moved; the by-UID read that resolves the stale entity
        # is the same path every projected row comes from, and it carries the new value.
        respx.get(url=f"{_TRACKER_PATH}/{_PERSON_UID}").mock(
            return_value=httpx.Response(200, json=_entity(national_id="SCEN-A-0002", updated_at=_SECOND_READ))
        )
        respx.get(_TRACKER_PATH).mock(return_value=httpx.Response(200, json=_page()))
        respx.get(_ENROLLMENTS_PATH).mock(
            return_value=httpx.Response(
                200,
                json=_enrollment_page(
                    {"enrollment": "EnrAnc00001", "trackedEntity": _PERSON_UID, "updatedAt": _SECOND_READ}
                ),
            )
        )

        report = await _sync(capture_project, store, reader)

    held = await store.read("Patient", _PERSON_UID)
    assert report.pages_read > 0
    assert held is not None
    assert {entry["value"] for entry in held.body["identifier"]} == {_PERSON_UID, "SCEN-A-0002"}


async def test_a_rebuild_drops_what_was_there_and_reads_the_whole_scope_again(
    capture_project: FhirProject, store: SqliteProjectionStore, reader: _Reader
) -> None:
    """D3: rebuilding is routine, and it is how a mapping change reaches what is already stored."""
    with respx.mock:
        respx.get(_TRACKER_PATH).mock(
            return_value=httpx.Response(200, json=_page(_entity(), _entity(_OTHER_PERSON_UID, national_id="SCEN-B")))
        )
        respx.get(_ENROLLMENTS_PATH).mock(return_value=httpx.Response(200, json=_enrollment_page()))
        await _sync(capture_project, store, reader)

    with respx.mock:
        entities = respx.get(_TRACKER_PATH).mock(return_value=httpx.Response(200, json=_page(_entity())))
        respx.get(_ENROLLMENTS_PATH).mock(return_value=httpx.Response(200, json=_enrollment_page()))

        report = await _sync(capture_project, store, reader, rebuild=True)

    assert report.mode is SyncMode.REBUILD
    assert "updatedAfter" not in entities.calls.last.request.url.params
    assert (await store.search(ProjectionQuery(resource_type="Patient"))).total == 1
    assert await store.read("Patient", _OTHER_PERSON_UID) is None


async def test_a_dry_run_reads_the_instance_and_writes_nothing(
    capture_project: FhirProject, store: SqliteProjectionStore, reader: _Reader
) -> None:
    """The posture `[forward] import = false` establishes: the real endpoint answers, the disk does not move."""
    with respx.mock:
        entities = respx.get(_TRACKER_PATH).mock(return_value=httpx.Response(200, json=_page(_entity())))
        respx.get(_ENROLLMENTS_PATH).mock(return_value=httpx.Response(200, json=_enrollment_page()))

        report = await _sync(capture_project, store, reader, dry_run=True)

    assert entities.calls
    assert report.dry_run is True
    assert [(row.resource_type, row.created, row.updated, row.removed) for row in report.counts] == [
        ("Patient", 1, 0, 0)
    ]
    assert await store.read("Patient", _PERSON_UID) is None
    assert (await store.watermarks()).tracked_entities is None


async def test_a_walk_that_failed_advances_no_watermark(
    capture_project: FhirProject, store: SqliteProjectionStore, reader: _Reader
) -> None:
    """Rule 1 in the direction that matters: behind its data costs a re-read, ahead of it loses rows."""
    with respx.mock:
        respx.get(_TRACKER_PATH).mock(return_value=httpx.Response(500, json={"message": "no"}))
        respx.get(_ENROLLMENTS_PATH).mock(return_value=httpx.Response(200, json=_enrollment_page()))

        with pytest.raises(Dhis2ApiError):
            await _sync(capture_project, store, reader)

    assert (await store.watermarks()).tracked_entities is None
    assert (await store.cursor()).updated_at is None


async def test_the_watermark_is_the_latest_instant_the_walk_saw_and_not_the_last_page_it_read(
    capture_project: FhirProject, store: SqliteProjectionStore, reader: _Reader
) -> None:
    """The walk is ordered by `createdAt`, so a later page can carry an earlier `updatedAt`."""
    with respx.mock:
        respx.get(_TRACKER_PATH).mock(
            return_value=httpx.Response(
                200,
                json=_page(
                    _entity(_PERSON_UID, updated_at=_SECOND_READ),
                    _entity(_OTHER_PERSON_UID, national_id="SCEN-B", updated_at=_FIRST_READ),
                ),
            )
        )
        respx.get(_ENROLLMENTS_PATH).mock(return_value=httpx.Response(200, json=_enrollment_page()))

        await _sync(capture_project, store, reader)

    assert (await store.watermarks()).tracked_entities == datetime.fromisoformat(_SECOND_READ)
