"""The SQLite `ProjectionStore` and the name index beside it: what they hold, and what they refuse to.

No DHIS2 and no application. A store is a file, so it is tested as one - opened on a `tmp_path`,
written, read back, and asked the questions the serving path asks it.

What is under test is the three correctness rules of `docs/fhir/design/projection.md` section 5.2
rather than the SQL that implements them: a watermark that never runs ahead of its rows, a write that
is idempotent by resource id, and a tombstone that removes rather than archives. Plus the two claims
the search surface rests on - an identifier is matched exactly and a name is matched as a fold-and-
substring - and the measured weakness section 3.3 tells this index to characterize rather than assume.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from dhis2w_fhir_serve.projection.base import (
    IndexedName,
    NameQuery,
    NameSearchIndex,
    ProjectedResource,
    ProjectedResourceKey,
    ProjectionBatch,
    ProjectionCursor,
    ProjectionEndpoint,
    ProjectionQuery,
    ProjectionStore,
)
from dhis2w_fhir_serve.projection.sqlite_names import EXACT_MATCH_SCORE, SUBSTRING_MATCH_SCORE, SqliteNameSearchIndex
from dhis2w_fhir_serve.projection.sqlite_store import SqliteProjectionStore

_SYSTEM = "http://dhis2.org/fhir/tracked-entity-attribute/TeaNationId"
_UID_SYSTEM = "http://dhis2.org/fhir/id/tracked-entity"
_TYPE_UID = "TetPerson01"
_NAME_ATTRIBUTE = "TeaFirstNam"

_EARLIER = datetime(2026, 8, 20, 9, 0, 0)
_LATER = datetime(2026, 8, 21, 9, 0, 0)


def _person(resource_id: str, *, national_id: str, at: datetime | None = None) -> ProjectedResource:
    """One projected Patient carrying the two identifiers a register resource always carries."""
    return ProjectedResource(
        resource_type="Patient",
        resource_id=resource_id,
        cursor=ProjectionCursor(updated_at=at),
        body={
            "resourceType": "Patient",
            "id": resource_id,
            "identifier": [
                {"system": _UID_SYSTEM, "value": resource_id},
                {"system": _SYSTEM, "value": national_id},
            ],
        },
    )


@pytest.fixture
async def store(tmp_path: Path) -> SqliteProjectionStore:
    """An empty projection in a directory of this test's own, created on its first read."""
    return SqliteProjectionStore(tmp_path / ".serve" / "projection.sqlite")


@pytest.fixture
def index(store: SqliteProjectionStore) -> SqliteNameSearchIndex:
    """The name index over that same projection - one file, one connection, one writer."""
    return SqliteNameSearchIndex(store)


def test_the_sqlite_backends_satisfy_the_two_protocols(store: SqliteProjectionStore) -> None:
    """The seams ship before their backends, so what each one asks for is checked against what arrived."""
    assert isinstance(store, ProjectionStore)
    assert isinstance(SqliteNameSearchIndex(store), NameSearchIndex)


async def test_a_projection_nobody_filled_states_no_cursor(store: SqliteProjectionStore) -> None:
    """An empty projection is as of nothing, and says so rather than as of the moment it was asked."""
    assert await store.cursor() == ProjectionCursor()
    assert (await store.watermarks()).tracked_entities is None


async def test_a_written_resource_reads_back_as_the_document_it_was_written_as(
    store: SqliteProjectionStore,
) -> None:
    """The body is the wire JSON, verbatim - a store parses enough to index and passes the rest through."""
    written = _person("PLoWmEuLJl2", national_id="SCEN-A-0001", at=_EARLIER)

    await store.write(ProjectionBatch(resources=(written,)))
    held = await store.read("Patient", "PLoWmEuLJl2")

    assert held is not None
    assert held.body == written.body
    assert held.cursor.updated_at == _EARLIER


async def test_a_second_write_of_one_resource_replaces_it_rather_than_duplicating_it(
    store: SqliteProjectionStore,
) -> None:
    """Rule 2: an overlap window re-reads rows, so every write is an upsert by resource id."""
    await store.write(ProjectionBatch(resources=(_person("PLoWmEuLJl2", national_id="SCEN-A-0001", at=_EARLIER),)))
    await store.write(ProjectionBatch(resources=(_person("PLoWmEuLJl2", national_id="SCEN-A-0002", at=_LATER),)))

    page = await store.search(ProjectionQuery(resource_type="Patient"))

    assert page.total == 1
    assert page.resources[0].cursor.updated_at == _LATER
    assert (await store.search(ProjectionQuery(resource_type="Patient", identifiers=("SCEN-A-0001",)))).total == 0
    assert (await store.search(ProjectionQuery(resource_type="Patient", identifiers=("SCEN-A-0002",)))).total == 1


async def test_a_removal_takes_the_row_and_its_index_entries_with_it(store: SqliteProjectionStore) -> None:
    """Rule 3: a tombstone removes. There is no last state to keep - DHIS2 will not answer a read of one."""
    await store.write(
        ProjectionBatch(
            resources=(_person("PLoWmEuLJl2", national_id="SCEN-A-0001", at=_EARLIER),),
            names=(
                IndexedName(
                    tracked_entity_uid="PLoWmEuLJl2",
                    attribute_uid=_NAME_ATTRIBUTE,
                    value="Somsack",
                    tracked_entity_type_uid=_TYPE_UID,
                ),
            ),
        )
    )

    await store.write(
        ProjectionBatch(removed=(ProjectedResourceKey(resource_type="Patient", resource_id="PLoWmEuLJl2"),))
    )

    assert await store.read("Patient", "PLoWmEuLJl2") is None
    assert (await store.search(ProjectionQuery(resource_type="Patient", identifiers=("SCEN-A-0001",)))).total == 0
    found = await SqliteNameSearchIndex(store).find(NameQuery(value="Somsack"))
    assert found.matches == ()


async def test_the_watermark_advances_with_the_batch_that_carries_it(store: SqliteProjectionStore) -> None:
    """Rule 1: the rows and the watermark land in one write, so the watermark never runs ahead of them."""
    answered = await store.write(
        ProjectionBatch(
            resources=(_person("PLoWmEuLJl2", national_id="SCEN-A-0001", at=_EARLIER),),
            endpoint=ProjectionEndpoint.TRACKED_ENTITIES,
            cursor=ProjectionCursor(updated_at=_EARLIER),
        )
    )

    assert answered == ProjectionCursor()
    assert (await store.watermarks()).tracked_entities == _EARLIER


async def test_the_projection_is_as_of_the_earlier_of_its_two_watermarks(store: SqliteProjectionStore) -> None:
    """A projection is as current as its least current half, so the cursor is the earlier reading."""
    await store.write(
        ProjectionBatch(endpoint=ProjectionEndpoint.TRACKED_ENTITIES, cursor=ProjectionCursor(updated_at=_LATER))
    )
    await store.write(
        ProjectionBatch(endpoint=ProjectionEndpoint.ENROLLMENTS, cursor=ProjectionCursor(updated_at=_EARLIER))
    )

    assert (await store.cursor()).updated_at == _EARLIER


async def test_a_rebuild_drops_the_rows_and_the_watermarks_together(store: SqliteProjectionStore) -> None:
    """A projection emptied of rows but still claiming to have read up to yesterday never polls for them again."""
    await store.write(
        ProjectionBatch(
            resources=(_person("PLoWmEuLJl2", national_id="SCEN-A-0001", at=_EARLIER),),
            endpoint=ProjectionEndpoint.TRACKED_ENTITIES,
            cursor=ProjectionCursor(updated_at=_EARLIER),
        )
    )

    await store.rebuild()

    assert (await store.search(ProjectionQuery(resource_type="Patient"))).total == 0
    assert await store.cursor() == ProjectionCursor()
    assert (await store.watermarks()).tracked_entities is None


async def test_an_identifier_is_matched_exactly_and_under_the_system_the_token_named(
    store: SqliteProjectionStore,
) -> None:
    """An identifier names somebody rather than describes them, so a substring of one matches nobody."""
    await store.write(ProjectionBatch(resources=(_person("PLoWmEuLJl2", national_id="SCEN-A-0001", at=_EARLIER),)))

    under_its_system = await store.search(
        ProjectionQuery(resource_type="Patient", identifiers=("SCEN-A-0001",), identifier_systems=(_SYSTEM,))
    )
    under_another = await store.search(
        ProjectionQuery(resource_type="Patient", identifiers=("SCEN-A-0001",), identifier_systems=(_UID_SYSTEM,))
    )
    a_substring = await store.search(ProjectionQuery(resource_type="Patient", identifiers=("SCEN-A",)))

    assert [resource.resource_id for resource in under_its_system.resources] == ["PLoWmEuLJl2"]
    assert under_another.total == 0
    assert a_substring.total == 0


async def test_the_tracked_entity_uid_is_an_identifier_like_any_other(store: SqliteProjectionStore) -> None:
    """The projected resource carries its UID under the tracked entity system, so one index answers both."""
    await store.write(ProjectionBatch(resources=(_person("PLoWmEuLJl2", national_id="SCEN-A-0001", at=_EARLIER),)))

    page = await store.search(ProjectionQuery(resource_type="Patient", identifiers=("PLoWmEuLJl2",)))

    assert [resource.resource_id for resource in page.resources] == ["PLoWmEuLJl2"]


async def test_a_page_states_the_whole_match_set_and_carries_the_slice_it_was_asked_for(
    store: SqliteProjectionStore,
) -> None:
    """`total` is the searchset and never the page, and the order does not move between two pages of one walk."""
    await store.write(
        ProjectionBatch(
            resources=tuple(_person(f"PLoWmEuLJl{index}", national_id=f"SCEN-{index}") for index in range(5))
        )
    )

    first = await store.search(ProjectionQuery(resource_type="Patient", offset=0, count=2))
    second = await store.search(ProjectionQuery(resource_type="Patient", offset=2, count=2))

    assert first.total == 5
    assert second.total == 5
    assert [resource.resource_id for resource in first.resources] == ["PLoWmEuLJl0", "PLoWmEuLJl1"]
    assert [resource.resource_id for resource in second.resources] == ["PLoWmEuLJl2", "PLoWmEuLJl3"]


async def _index_names(store: SqliteProjectionStore, *values: str) -> None:
    """Put one person per value into the projection, each holding that value under the name attribute."""
    await store.write(
        ProjectionBatch(
            resources=tuple(_person(f"PLoWmEuLJl{index}", national_id=f"SCEN-{index}") for index in range(len(values))),
            names=tuple(
                IndexedName(
                    tracked_entity_uid=f"PLoWmEuLJl{index}",
                    attribute_uid=_NAME_ATTRIBUTE,
                    value=value,
                    tracked_entity_type_uid=_TYPE_UID,
                )
                for index, value in enumerate(values)
            ),
        )
    )


async def test_a_name_search_matches_a_case_insensitive_substring(
    store: SqliteProjectionStore, index: SqliteNameSearchIndex
) -> None:
    """The measured behaviour of the filter this replaces (section 3.3, findings 1 and the case rows)."""
    await _index_names(store, "ສົມສັກ", "ສົມພອນ", "SOMBOUN", "Sophea")

    assert [match.tracked_entity_uid for match in (await index.find(NameQuery(value="ສົມ"))).matches] == [
        "PLoWmEuLJl0",
        "PLoWmEuLJl1",
    ]
    assert (await index.find(NameQuery(value="ມສັກ"))).matches[0].tracked_entity_uid == "PLoWmEuLJl0"
    assert (await index.find(NameQuery(value="somboun"))).matches[0].tracked_entity_uid == "PLoWmEuLJl2"
    assert (await index.find(NameQuery(value="SOPHEA"))).matches[0].tracked_entity_uid == "PLoWmEuLJl3"


async def test_a_name_search_does_not_transliterate_and_does_not_forgive_a_typo(
    store: SqliteProjectionStore, index: SqliteNameSearchIndex
) -> None:
    """The four rows section 3.3's table marks **fails** still fail, characterized rather than assumed.

    Transliteration is R8 and it arrives with the OpenSearch backend of step 6. Asserting the gap is
    what keeps this backend honest about the size of what it does not do.
    """
    await _index_names(store, "ສົມສັກ", "សុភា", "Somsack")

    assert [match.tracked_entity_uid for match in (await index.find(NameQuery(value="Somsack"))).matches] == [
        "PLoWmEuLJl2"
    ]
    assert (await index.find(NameQuery(value="Sophea"))).matches == ()
    assert (await index.find(NameQuery(value="Somsck"))).matches == ()
    assert (await index.find(NameQuery(value="ສົມສີກ"))).matches == ()


async def test_a_whole_value_scores_above_a_substring_of_one(
    store: SqliteProjectionStore, index: SqliteNameSearchIndex
) -> None:
    """Two scores rather than a distance, and the exact one is ranked first."""
    await _index_names(store, "Som", "Somsack")

    found = await index.find(NameQuery(value="Som"))

    assert [match.tracked_entity_uid for match in found.matches] == ["PLoWmEuLJl0", "PLoWmEuLJl1"]
    assert found.matches[0].score == pytest.approx(EXACT_MATCH_SCORE)
    assert found.matches[1].score == pytest.approx(SUBSTRING_MATCH_SCORE)


async def test_a_name_search_states_the_cursor_it_was_read_at(
    store: SqliteProjectionStore, index: SqliteNameSearchIndex
) -> None:
    """An index answer is as of the projection's watermark, unlike a live one which is as of now."""
    await _index_names(store, "Somsack")
    await store.write(
        ProjectionBatch(endpoint=ProjectionEndpoint.TRACKED_ENTITIES, cursor=ProjectionCursor(updated_at=_EARLIER))
    )
    await store.write(
        ProjectionBatch(endpoint=ProjectionEndpoint.ENROLLMENTS, cursor=ProjectionCursor(updated_at=_LATER))
    )

    found = await index.find(NameQuery(value="Somsack"))

    assert found.cursor is not None
    assert found.cursor.updated_at == _EARLIER


async def test_a_lookup_given_nothing_matches_nobody(
    store: SqliteProjectionStore, index: SqliteNameSearchIndex
) -> None:
    """A search for an empty value is not a request to hand over the register."""
    await _index_names(store, "Somsack")

    assert (await index.find(NameQuery(value="   "))).matches == ()


async def test_a_like_wildcard_in_a_value_is_a_character_and_not_a_wildcard(
    store: SqliteProjectionStore, index: SqliteNameSearchIndex
) -> None:
    """A `%` somebody typed is a `%` somebody typed, and never the whole register."""
    await _index_names(store, "Somsack", "50%")

    assert [match.tracked_entity_uid for match in (await index.find(NameQuery(value="%"))).matches] == ["PLoWmEuLJl1"]


async def test_a_name_search_is_narrowed_by_attribute_and_by_tracked_entity_type(
    store: SqliteProjectionStore, index: SqliteNameSearchIndex
) -> None:
    """A resource is served over its own types alone, so a sample never comes back as a person."""
    await _index_names(store, "Somsack")

    assert (await index.find(NameQuery(value="Somsack", attribute_uids=(_NAME_ATTRIBUTE,)))).matches != ()
    assert (await index.find(NameQuery(value="Somsack", attribute_uids=("TeaOther001",)))).matches == ()
    assert (await index.find(NameQuery(value="Somsack", tracked_entity_type_uids=(_TYPE_UID,)))).matches != ()
    assert (await index.find(NameQuery(value="Somsack", tracked_entity_type_uids=("TetSample01",)))).matches == ()


async def test_a_rebuild_migrates_a_file_written_by_an_older_schema(tmp_path: Path) -> None:
    """A projection file missing a column the current schema carries is remade whole by rebuild.

    `create_all` never alters a present table, so a DELETE-based rebuild would leave the old columns
    in place and the refill would write columns the table does not have - the failure a live upgrade
    hit on 2026-08-22. The rebuild drops and recreates instead, which a from-zero refill makes free.
    """
    import sqlite3

    database_path = tmp_path / "projection.sqlite"
    connection = sqlite3.connect(database_path)
    connection.execute(
        "CREATE TABLE projected_resource (resource_type TEXT NOT NULL, resource_id TEXT NOT NULL,"
        " document TEXT NOT NULL, updated_at TEXT NOT NULL, PRIMARY KEY (resource_type, resource_id))"
    )
    connection.commit()
    connection.close()

    store = SqliteProjectionStore(database_path)
    await store.rebuild()
    try:
        columns = {row[1] for row in sqlite3.connect(database_path).execute("PRAGMA table_info(projected_resource)")}
        assert "tracked_entity_type_uid" in columns
    finally:
        await store.close()
