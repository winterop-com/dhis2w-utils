"""The SQLite backend of `ProjectionStore`: one file under the project, written only by a sync.

This is step 3 of `docs/fhir/design/projection.md` and it is the Embedded posture's whole backend -
no service, no port, no operator, one file `make install` already gave you the driver for. It is also
the reference implementation of the Protocol, which is the part that outlives it: every later backend
is measured against what this one does, and every test of the sync and of the serving path runs
against it.

THE THREE CORRECTNESS RULES, EACH IN ONE PLACE HERE.

1. **The watermark advances only when the rows it describes are durable.** `write` puts the
   resources, their identifiers, their search keys, the removals, and the new watermark in ONE
   session and ONE commit. A watermark ahead of its data is silent, permanent, undetectable data
   loss - the rows in the gap are never polled again - and this is the design that deletes the window
   rather than managing it (section 5.2, rule 1, and the sharpest argument in section 8.2).
2. **A write is idempotent by resource id.** A sync re-polls from `watermark - overlap` and therefore
   re-reads rows it already holds; every one of them is an upsert, so re-reading a batch changes
   nothing but the instant it was written at. That is what makes the overlap window safe rather than
   duplicating (section 5.2, rule 2).
3. **A tombstone removes the row.** `removed` deletes the resource, its identifiers, and its search
   keys. It never archives a last known state - the collection route enumerates a tombstone but the
   single-resource route answers 404 for it (`docs/fhir/design/projection.md` section 3.4, finding 3),
   so there is no final state to archive and pretending otherwise would be inventing one.

WHAT THIS CLASS IS, AND WHY IT IS NOT A PYDANTIC MODEL. It holds an open database engine and a file
it creates on first use, which is a connection rather than a value - the same reading that keeps
`Dhis2Client` off `ServeContext` and puts `open_pass_through_client`'s pool on the runtime instead.
`dhis2w_core.token_store.SqliteTokenStore` is the shape this follows; everything it hands back and
takes in is a `BaseModel`.

WHAT IT DOES NOT DO. It does not write itself: D2 says the sync is the only writer, and nothing here
is reachable from a route that changes anything. It does not reconcile: a row that disagrees with
DHIS2 is a sync defect whose honest fix is `rebuild`. And it never decides who may read what - every
answer it gives is a set of resources, and which caller may see which of them is settled by the
instance, on the live read that resolves each one (`docs/fhir/design/projection.md` R9).
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from dhis2w_fhir_serve.projection.base import (
    IndexedName,
    ProjectedResource,
    ProjectionBatch,
    ProjectionCursor,
    ProjectionEndpoint,
    ProjectionPage,
    ProjectionQuery,
    ProjectionWatermarks,
)
from dhis2w_fhir_serve.projection.schema import (
    NO_IDENTIFIER_SYSTEM,
    ProjectedIdentifierRow,
    ProjectedNameRow,
    ProjectedResourceRow,
    ProjectionWatermarkRow,
    create_projection_tables,
    open_projection_engine,
    projection_sessions,
    recreate_projection_tables,
)

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator
    from pathlib import Path

    from sqlalchemy.ext.asyncio import AsyncSession

#: The permissions the projection file is held at once it exists.
#:
#: The same 0600 the token store uses, and for a related reason: this file holds a copy of an
#: instance's register, and a copy of people's identifiers is not a thing to leave world-readable
#: because it happens to be derived.
PROJECTION_FILE_MODE = 0o600


class SqliteProjectionStore:
    """Holds the FHIR projection of a DHIS2 instance in one SQLite file, written only by sync."""

    def __init__(self, database_path: Path) -> None:
        """Bind an engine to one projection file, which is not created until something reads it."""
        self._database_path = database_path
        self._engine = open_projection_engine(database_path)
        self._sessions = projection_sessions(self._engine)
        self._created = False

    @property
    def database_path(self) -> Path:
        """Where this projection lives, which is what a sync report names and an operator deletes."""
        return self._database_path

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession]:
        """Open one session over this projection's database, creating the file and its tables if new.

        Public because the name index reads the same database through it. The projection has one
        connection, because it has one writer, and a second engine over the same file would be
        something SQLite has to arbitrate for no gain - see `sqlite_names`.
        """
        await self._ensure_tables()
        async with self._sessions() as opened:
            yield opened

    async def read(self, resource_type: str, resource_id: str) -> ProjectedResource | None:
        """Read one projected resource, or None where the projection holds none under that id."""
        async with self.session() as session:
            row = await session.get(ProjectedResourceRow, (resource_type, resource_id))
            if row is None:
                return None
            return _projected(row, await self._cursor_in(session))

    async def search(self, query: ProjectionQuery) -> ProjectionPage:
        """Answer one page of the projection, stating the cursor it was read at.

        `total` is the whole match set and never the page, which is what R4 defines `Bundle.total`
        as - so a client paging a register of eight hundred people is told eight hundred on the first
        page rather than twenty. The order is by resource id: a walk needs an order that does not
        move between two pages of it, and the id is the one thing every projected resource has.
        """
        async with self.session() as session:
            matched = _matching_ids(query)
            total = await session.scalar(select(func.count()).select_from(matched.subquery()))
            page = select(ProjectedResourceRow).where(
                ProjectedResourceRow.resource_type == query.resource_type,
                ProjectedResourceRow.resource_id.in_(matched),
            )
            page = page.order_by(ProjectedResourceRow.resource_id).offset(query.offset)
            if query.count is not None:
                page = page.limit(query.count)
            cursor = await self._cursor_in(session)
            rows = (await session.execute(page)).scalars().all()
            return ProjectionPage(
                resources=tuple(_projected(row, cursor) for row in rows),
                total=int(total or 0),
                cursor=cursor,
            )

    async def write(self, batch: ProjectionBatch) -> ProjectionCursor:
        """Write one sync's batch and answer the cursor the projection now stands at.

        One session, one commit, everything in it: the rows, the index entries beside them, the
        removals, and the watermark the batch advances. Nothing here is written that the commit does
        not cover, which is the whole of correctness rule 1.
        """
        async with self.session() as session:
            for key in batch.removed:
                await _forget(session, key.resource_type, key.resource_id)
            for resource in batch.resources:
                await _forget(session, resource.resource_type, resource.resource_id)
                session.add(
                    ProjectedResourceRow(
                        resource_type=resource.resource_type,
                        resource_id=resource.resource_id,
                        updated_at=resource.cursor.updated_at,
                        tracked_entity_type_uid=resource.tracked_entity_type_uid,
                        body=json.dumps(resource.body, ensure_ascii=False, sort_keys=True),
                    )
                )
                for system, value in _identifiers_of(resource.body):
                    session.add(
                        ProjectedIdentifierRow(
                            resource_type=resource.resource_type,
                            resource_id=resource.resource_id,
                            system=system,
                            value=value,
                        )
                    )
            for name in _distinct_names(batch):
                session.add(
                    ProjectedNameRow(
                        tracked_entity_uid=name.tracked_entity_uid,
                        attribute_uid=name.attribute_uid,
                        value=name.value,
                        folded=name.value.casefold(),
                        tracked_entity_type_uid=name.tracked_entity_type_uid,
                    )
                )
            if batch.endpoint is not None and batch.cursor.updated_at is not None:
                await session.execute(
                    sqlite_insert(ProjectionWatermarkRow)
                    .values(endpoint=batch.endpoint.value, updated_at=batch.cursor.updated_at)
                    .on_conflict_do_update(
                        index_elements=[ProjectionWatermarkRow.endpoint],
                        set_={"updated_at": batch.cursor.updated_at},
                    )
                )
            await session.commit()
            return (await self._watermarks_in(session)).cursor()

    async def cursor(self) -> ProjectionCursor:
        """How far this projection has been filled, which every answer served from it states."""
        async with self.session() as session:
            return await self._cursor_in(session)

    async def watermarks(self) -> ProjectionWatermarks:
        """How far each tracker collection has been read, which is what the next poll asks from."""
        async with self.session() as session:
            return await self._watermarks_in(session)

    async def rebuild(self) -> None:
        """Drop and recreate the projection's tables so a full materialization fills a current schema.

        The watermarks go with the rows. A projection emptied of documents but still claiming to have
        read up to yesterday would never poll for any of them again, which is correctness rule 1
        stated backwards - and it is exactly the state a rebuild exists to be unable to leave behind.

        Dropping rather than deleting is what makes the rebuild the schema migration: a file written
        by an older schema keeps its old columns through any DELETE, and the refill would then write
        columns the table does not have. A rebuild starts from zero anyway, so the tables are remade
        at the schema this process carries.
        """
        await self._ensure_tables()
        await recreate_projection_tables(self._engine)

    async def close(self) -> None:
        """Dispose of the connection, which is what the serve lifespan does when the process unwinds."""
        await self._engine.dispose()

    async def _ensure_tables(self) -> None:
        """Create the file and its tables on the first read or write, and never again in this process."""
        if self._created:
            return
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        await create_projection_tables(self._engine)
        if self._database_path.exists():
            self._database_path.chmod(PROJECTION_FILE_MODE)
        self._created = True

    async def _cursor_in(self, session: AsyncSession) -> ProjectionCursor:
        """The one instant this projection is as of, read inside a session a caller already opened."""
        return (await self._watermarks_in(session)).cursor()

    async def _watermarks_in(self, session: AsyncSession) -> ProjectionWatermarks:
        """The three watermarks as one value, read inside a session a caller already opened."""
        rows = (await session.execute(select(ProjectionWatermarkRow))).scalars().all()
        marks = {row.endpoint: row.updated_at for row in rows}
        return ProjectionWatermarks(
            tracked_entities=marks.get(ProjectionEndpoint.TRACKED_ENTITIES.value),
            enrollments=marks.get(ProjectionEndpoint.ENROLLMENTS.value),
        )


async def _forget(session: AsyncSession, resource_type: str, resource_id: str) -> None:
    """Drop one resource and everything indexed about it, which is both a removal and half an upsert.

    The name rows go by tracked entity UID rather than by resource key, because a search key belongs
    to the entity rather than to the resource its type is published as - and the UID is the id the
    resource is served under, so the two are the same string read two ways.
    """
    await session.execute(
        delete(ProjectedIdentifierRow).where(
            ProjectedIdentifierRow.resource_type == resource_type,
            ProjectedIdentifierRow.resource_id == resource_id,
        )
    )
    await session.execute(delete(ProjectedNameRow).where(ProjectedNameRow.tracked_entity_uid == resource_id))
    await session.execute(
        delete(ProjectedResourceRow).where(
            ProjectedResourceRow.resource_type == resource_type,
            ProjectedResourceRow.resource_id == resource_id,
        )
    )


def _matching_ids(query: ProjectionQuery) -> Any:
    """The ids one query selects, as a subquery the page and the count both run over.

    A query naming no identifier selects the whole resource type, which is the listing. A query
    naming identifiers selects whoever holds one of them - under one of the named systems where the
    token said which key it was, and under any system where it did not.

    A query naming tracked entity types narrows either of those to the types it names, which is what
    `_tag` asks of a resource served over several of them. It narrows through the resource table in
    both cases, because the type is a fact about the resource rather than about one identifier of it.

    A query naming attribute values narrows either of them again, once per value, through the index
    the sync writes every attribute value into - which is what `d2-attribute` asks. One subquery per
    filter and not one predicate, because two filters are two rows of that table about one person:
    ANDing the columns of a single row would ask for one value that is two things at once.
    """
    if not query.identifiers:
        return _filtered(
            _narrowed(
                select(ProjectedResourceRow.resource_id).where(
                    ProjectedResourceRow.resource_type == query.resource_type
                ),
                query,
            ),
            query,
        )
    matched = select(ProjectedIdentifierRow.resource_id).where(
        ProjectedIdentifierRow.resource_type == query.resource_type,
        ProjectedIdentifierRow.value.in_(query.identifiers),
    )
    if query.identifier_systems:
        matched = matched.where(ProjectedIdentifierRow.system.in_(query.identifier_systems))
    if query.tracked_entity_type_uids:
        matched = matched.where(
            ProjectedIdentifierRow.resource_id.in_(
                _narrowed(
                    select(ProjectedResourceRow.resource_id).where(
                        ProjectedResourceRow.resource_type == query.resource_type
                    ),
                    query,
                )
            )
        )
    for holders in _value_holders(query):
        matched = matched.where(ProjectedIdentifierRow.resource_id.in_(holders))
    return matched.distinct()


def _narrowed(statement: Any, query: ProjectionQuery) -> Any:
    """Narrow one selection over the resource table to the tracked entity types a query names."""
    if not query.tracked_entity_type_uids:
        return statement
    return statement.where(ProjectedResourceRow.tracked_entity_type_uid.in_(query.tracked_entity_type_uids))


def _filtered(statement: Any, query: ProjectionQuery) -> Any:
    """Narrow one selection over the resource table to the entities holding every value a query names."""
    for holders in _value_holders(query):
        statement = statement.where(ProjectedResourceRow.resource_id.in_(holders))
    return statement


def _value_holders(query: ProjectionQuery) -> list[Any]:
    """One selection of tracked entity UIDs per value filter - whoever holds that value under that attribute.

    Matched on the folded column, because DHIS2's own `eq` matches a tracked entity attribute value
    without regard to case (BUGS.md 109) and an equality that meant one thing live and another here
    would be two operators wearing one name. The folded column is already indexed - `_content` needed
    it first - so the filter costs an index read rather than a scan.
    """
    return [
        select(ProjectedNameRow.tracked_entity_uid).where(
            ProjectedNameRow.attribute_uid == attribute_value.attribute_uid,
            ProjectedNameRow.folded == attribute_value.folded_value(),
        )
        for attribute_value in query.attribute_values
    ]


def _identifiers_of(body: dict[str, Any]) -> list[tuple[str, str]]:
    """Every `identifier` entry of one projected document, as the pair the token index holds.

    Read off the document rather than handed in beside it, so what a token search matches is exactly
    what a client reading the resource would see under `identifier[]` - there is no second statement
    of a person's identifiers that could come to disagree with the first.
    """
    entries = body.get("identifier")
    if not isinstance(entries, list):
        return []
    found: dict[tuple[str, str], None] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        value = entry.get("value")
        system = entry.get("system")
        if isinstance(value, str) and value:
            found[(system if isinstance(system, str) else NO_IDENTIFIER_SYSTEM, value)] = None
    return list(found)


def _distinct_names(batch: ProjectionBatch) -> list[IndexedName]:
    """The batch's search keys, once apiece: a person holding one value under one attribute is one key.

    A tracked entity can carry the same attribute value at its own level and again on an enrollment,
    which is one fact about that person however many places DHIS2 keeps it in.
    """
    distinct: dict[tuple[str, str, str], IndexedName] = {}
    for name in batch.names:
        distinct.setdefault((name.tracked_entity_uid, name.attribute_uid, name.value), name)
    return list(distinct.values())


def _projected(row: ProjectedResourceRow, cursor: ProjectionCursor) -> ProjectedResource:
    """One stored row as the resource a caller reads, stamped with the cursor it was read at."""
    body = json.loads(row.body)
    return ProjectedResource(
        resource_type=row.resource_type,
        resource_id=row.resource_id,
        cursor=ProjectionCursor(updated_at=row.updated_at) if row.updated_at is not None else cursor,
        tracked_entity_type_uid=row.tracked_entity_type_uid,
        body=body if isinstance(body, dict) else {},
    )
