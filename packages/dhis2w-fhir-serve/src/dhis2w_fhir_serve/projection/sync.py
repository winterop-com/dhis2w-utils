"""Filling the projection: the initial materialization, the incremental poll, and the report of both.

This is step 4 of `docs/fhir/design/projection.md`, and `d2w fhir sync` is the one thing that calls
it. Section 5.1 states the shape in three sentences and this module is those three sentences:

- **Initial materialization.** Walk the mapped scope - the tracked entity types
  `[serve.tracked_entities]` puts in scope - bulk-paged the way section 3.2 measured, project each
  page, write it.
- **Incremental runs.** Poll the same collection with `updatedAfter` and `includeDeleted=true`, apply
  creates, updates, and tombstones, and advance the watermark. Measured idle cost: one request,
  56 bytes.
- **Full rebuild.** `--rebuild` drops to empty and refills. Per D3 that is routine rather than a
  recovery step, and it is how a `fhir.toml` mapping change reaches the projection.

NOTHING HERE MAPS ANYTHING. The projection of one tracked entity onto the FHIR resource its type is
registered as is `register.projection.registered_entity_for`, which is the same function the live
register answers a read with, and the search keys come off `register.projection.attribute_values`,
which is the same function that decides what a served resource carries. A second mapping surface
would be a second answer to "what is this person in FHIR", and the two would drift on the first
mapping change. So a synced answer and a live answer are the same bytes, produced by the same code,
and the only difference between them is the instant they are true as of.

WHY THE ENROLLMENTS ARE POLLED AND THE EVENTS ARE NOT. A tracked entity's own `lastUpdated` does not
move when one of its enrollments does, and an enrollment carries program-level attribute values that
the projected resource does carry - so an enrollment poll is how the projection learns whose copy has
gone stale, and each entity it names is re-read through the one tracked entity path. An event carries
data values, the projected resource carries none, so an event that moved is not a change to anything
this projection holds; polling for one would be a request per interval spent to learn nothing. The
event walk arrives with the resources that need it, at steps 8 and 9.

THE WATERMARK ADVANCES AFTER ITS WALK AND NEVER DURING IT. Pages are ordered by `createdAt` so the
walk is stable, which means a later page can carry an EARLIER `updatedAt` than an earlier one - so no
page knows the watermark, and only the finished walk does. Each page is written as its own batch, and
the walk is closed by a batch carrying the new watermark once every row it describes is durable. That
is section 5.2 rule 1 in the direction that matters: a watermark behind its data costs one re-read,
and a watermark ahead of its data is silent permanent loss. A walk that fails halfway advances
nothing and the next run re-reads it, which the idempotent write makes free.

WHOSE CREDENTIALS IT READS UNDER, AND WHAT THAT MEANS FOR WHAT IT HOLDS. Whatever the caller handed
in - `d2w fhir sync` hands in the client for the profile the project resolves, which is the facade's
own build identity. Section 6's one rule regardless of posture: **the projection stores what a
configured build identity could read, and the facade must never let a caller's own identity imply
more than that.** Which is why the serving path resolves every match live under the caller's
credentials rather than handing over the row this sync wrote (R9, posture (iii)).
"""

from __future__ import annotations

from datetime import datetime, timedelta  # noqa: TC003 - pydantic resolves these annotations at runtime
from enum import StrEnum
from pathlib import Path  # noqa: TC003 - pydantic resolves this annotation at runtime
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from dhis2w_fhir_serve.projection.base import (
    IndexedName,
    ProjectedResource,
    ProjectedResourceKey,
    ProjectionBatch,
    ProjectionCursor,
    ProjectionEndpoint,
    ProjectionWatermarks,
)
from dhis2w_fhir_serve.register.projection import attribute_values, registered_entity_for
from dhis2w_fhir_serve.register.wire import (
    POLL_PAGE_SIZE,
    as_instant,
    fetch_tracked_entity,
    poll_enrollments,
    poll_tracked_entities,
)

if TYPE_CHECKING:
    from dhis2w_client.generated.v42.oas import TrackerTrackedEntity

    from dhis2w_fhir_serve.passthrough import RegisterReader
    from dhis2w_fhir_serve.projection.base import ProjectionStore
    from dhis2w_fhir_serve.register.surface import RegisterSurface

#: How many steps a run narrates, so a caller can size a progress display before the first read.
SYNC_STEPS = 3

#: What each of them is called on the line that reports it finished.
SYNC_STEP_LABELS = ("register", "tracked entities", "enrollments")


@runtime_checkable
class SyncNarrator(Protocol):
    """What a run announces a finished step to, so a long materialization is not a silent one.

    Narrow on purpose, and structurally satisfied by `dhis2w_core.progress.ProgressReporter` - the
    same reason `RegisterReader` is one method wide. A sync is a batch job that a district's whole
    register goes through, and the caller that started it is entitled to see it moving; what it is
    NOT entitled to is a dependency edge from this package to the CLI's console.
    """

    def complete(self, index: int, total: int, label: str, summary: str, *, style: str | None = None) -> None:
        """Announce that step `index` finished, with a one-line summary."""
        ...


class SyncMode(StrEnum):
    """What one run of the sync was: how much it read, and why it read that much."""

    #: The projection held no watermark, so the whole mapped scope was read. The one place the
    #: population-scale read cost of section 3.2 is paid.
    INITIAL = "initial"

    #: The projection held a watermark, so only what moved since it was read.
    INCREMENTAL = "incremental"

    #: `--rebuild`: the projection was dropped to empty first, then filled as an initial run.
    REBUILD = "rebuild"


class SyncResourceCounts(BaseModel):
    """What one run did to one FHIR resource type of the projection."""

    model_config = ConfigDict(frozen=True)

    resource_type: str
    created: int = 0
    updated: int = 0
    removed: int = 0
    """Rows a tombstone took out. A deletion means "remove the row", never "keep the last state"."""

    def changed(self) -> int:
        """How many rows of this type the run touched at all."""
        return self.created + self.updated + self.removed


class SyncCursorMove(BaseModel):
    """Where one collection's watermark stood before the run, and where it stands after it."""

    model_config = ConfigDict(frozen=True)

    endpoint: ProjectionEndpoint
    moved_from: datetime | None = None
    moved_to: datetime | None = None

    def moved(self) -> bool:
        """Whether this run learned anything new about how far the collection has been read."""
        return self.moved_to is not None and self.moved_to != self.moved_from


class SyncReport(BaseModel):
    """What one `d2w fhir sync` did: what it read, what it changed, and where the cursor now stands."""

    model_config = ConfigDict(frozen=True)

    mode: SyncMode
    dry_run: bool = False
    """True when the run read the instance, counted what it would change, and wrote nothing."""

    project_root: Path
    store_path: Path
    tracked_entity_types: tuple[str, ...] = ()
    """The types the mapped scope put in this run, which is what `[serve.tracked_entities]` narrowed."""

    programs: tuple[str, ...] = ()
    """The programs whose enrollments were polled - the ones the guide publishes, since the endpoint
    admits no other scope (BUGS.md 102)."""

    pages_read: int = 0
    counts: tuple[SyncResourceCounts, ...] = ()
    cursors: tuple[SyncCursorMove, ...] = ()
    cursor: ProjectionCursor = Field(default_factory=ProjectionCursor)
    """Where the projection as a whole now stands, which is what every answer served from it states."""

    def changed(self) -> int:
        """How many projection rows this run touched, across every resource type."""
        return sum(counts.changed() for counts in self.counts)

    def counts_line(self) -> str:
        """The one line a finished run closes with - the same shape a forward report closes with."""
        created = sum(counts.created for counts in self.counts)
        updated = sum(counts.updated for counts in self.counts)
        removed = sum(counts.removed for counts in self.counts)
        posture = "would create" if self.dry_run else "created"
        return f"{posture} {created}, updated {updated}, removed {removed} over {self.pages_read} page(s)"


async def run_sync(
    reader: RegisterReader,
    *,
    surface: RegisterSurface,
    store: ProjectionStore,
    project_root: Path,
    store_path: Path,
    overlap: timedelta,
    rebuild: bool = False,
    dry_run: bool = False,
    narrator: SyncNarrator | None = None,
) -> SyncReport:
    """Fill or refresh the projection from one DHIS2 instance, and report exactly what changed.

    The mode is read off the projection rather than asked for: a store holding no watermark has never
    been filled, so the first run is a full materialization whether or not anybody said so, and every
    run after it reads what moved. `rebuild` is the one that is asked for, because dropping a filled
    projection is a decision rather than an inference.

    `dry_run` reads the instance exactly as a committing run does and writes nothing at all - not the
    rows, not the watermark. It is the posture `[forward] import = false` establishes for the other
    half of the loop: the real endpoint answers, the real work is counted, and the file on disk is
    the file that was there before.
    """
    before = await store.watermarks()
    mode = (
        SyncMode.REBUILD if rebuild else (SyncMode.INITIAL if before.tracked_entities is None else SyncMode.INCREMENTAL)
    )
    if rebuild:
        if not dry_run:
            await store.rebuild()
        before = ProjectionWatermarks()
    served = tuple((served.uid, served.resource_type) for served in surface.served_types)
    programs = surface.index.program_uids()
    _narrate(
        narrator,
        1,
        "register",
        f"{len(served)} tracked entity type(s), {len(programs)} program(s), mode {mode.value}",
    )

    run = _Run(reader=reader, surface=surface, store=store, dry_run=dry_run)
    entities_mark = await run.materialize(served, since=_since(before.tracked_entities, overlap))
    _narrate(narrator, 2, "tracked entities", run.counts_line())
    enrollments_mark = await run.refresh_from_enrollments(
        served,
        programs,
        since=_since(before.enrollments, overlap),
        whole_scope_read=mode is not SyncMode.INCREMENTAL,
    )
    _narrate(narrator, 3, "enrollments", f"{run.touched} entity(s) re-read from an enrollment that moved")

    after = ProjectionWatermarks(
        tracked_entities=entities_mark or before.tracked_entities,
        enrollments=enrollments_mark or before.enrollments,
    )
    return SyncReport(
        mode=mode,
        dry_run=dry_run,
        project_root=project_root,
        store_path=store_path,
        tracked_entity_types=tuple(uid for uid, _ in served),
        programs=programs,
        pages_read=run.pages,
        counts=run.counts(),
        cursors=(
            SyncCursorMove(
                endpoint=ProjectionEndpoint.TRACKED_ENTITIES,
                moved_from=before.tracked_entities,
                moved_to=after.tracked_entities,
            ),
            SyncCursorMove(
                endpoint=ProjectionEndpoint.ENROLLMENTS,
                moved_from=before.enrollments,
                moved_to=after.enrollments,
            ),
        ),
        cursor=after.cursor() if dry_run else await store.cursor(),
    )


class _Tally(BaseModel):
    """What a run has done to one FHIR resource type so far, counted as it goes.

    Mutable, unlike everything else here, because a running total is the one thing in a sync that is
    not a value: it is the same three numbers being added to page after page.
    """

    created: int = 0
    updated: int = 0
    removed: int = 0


class _Run:
    """One sync in progress: what it has read, what it has written, and what it has counted.

    Mutable because a walk is, and private because a caller is entitled to the report rather than to
    the tallies it was assembled from.
    """

    def __init__(
        self, *, reader: RegisterReader, surface: RegisterSurface, store: ProjectionStore, dry_run: bool
    ) -> None:
        """Start a run with nothing read, nothing written, and nothing counted."""
        self._reader = reader
        self._surface = surface
        self._store = store
        self._dry_run = dry_run
        self._counts: dict[str, _Tally] = {}
        self._materialized: set[str] = set()
        self.pages = 0
        self.touched = 0

    async def materialize(self, served: tuple[tuple[str, str], ...], *, since: datetime | None) -> datetime | None:
        """Walk each tracked entity type in scope, writing every page, and answer the watermark reached.

        None means the walk learned no instant it can stand on - an empty scope, or a poll whose rows
        carried no comparable `updatedAt` - and the caller then leaves the watermark where it was
        rather than inventing one from this host's clock.
        """
        reached: datetime | None = None
        for tracked_entity_type_uid, resource_type in served:
            page = 1
            while True:
                read = await poll_tracked_entities(
                    self._reader,
                    tracked_entity_type_uid=tracked_entity_type_uid,
                    updated_after=since,
                    page=page,
                    page_size=POLL_PAGE_SIZE,
                )
                self.pages += 1
                if not read.trackedEntities:
                    break
                reached = _later(reached, await self._write_entities(read.trackedEntities, resource_type))
                page_count = None if read.pager is None else read.pager.pageCount
                if page_count is not None and page >= page_count:
                    break
                if page_count is None and len(read.trackedEntities) < POLL_PAGE_SIZE:
                    break
                page += 1
        await self._close_walk(ProjectionEndpoint.TRACKED_ENTITIES, reached)
        return reached

    async def refresh_from_enrollments(
        self,
        served: tuple[tuple[str, str], ...],
        programs: tuple[str, ...],
        *,
        since: datetime | None,
        whole_scope_read: bool,
    ) -> datetime | None:
        """Poll each program's enrollments for whose projection went stale, and re-read those entities.

        A run that read the whole scope through the tracked entity walk - an initial one, or a
        rebuild - has every entity an enrollment could name already current: this walk then only
        establishes the watermark, and the entities it names cost nothing to skip. A tombstoned
        enrollment names an entity whose removal - if the person is gone at all - is the tracked
        entity poll's to find, because that is the collection R10 makes the authority on who left.
        """
        resource_types = dict(served)
        reached: datetime | None = None
        stale: dict[str, None] = {}
        for program_uid in programs:
            page = 1
            while True:
                read = await poll_enrollments(
                    self._reader, program_uid=program_uid, updated_after=since, page=page, page_size=POLL_PAGE_SIZE
                )
                self.pages += 1
                if not read.rows:
                    break
                for row in read.rows:
                    reached = _later(reached, row.updated_at)
                    if row.tracked_entity_uid is not None and not row.deleted:
                        stale.setdefault(row.tracked_entity_uid, None)
                if read.page_count is not None and page >= read.page_count:
                    break
                if read.page_count is None and len(read.rows) < POLL_PAGE_SIZE:
                    break
                page += 1
        if not whole_scope_read:
            for tracked_entity_uid in stale:
                if tracked_entity_uid in self._materialized:
                    continue
                entity = await fetch_tracked_entity(self._reader, tracked_entity_uid)
                resource_type = None if entity is None else resource_types.get(entity.trackedEntityType or "")
                if entity is None or resource_type is None:
                    continue
                self.touched += 1
                await self._write_entities([entity], resource_type)
        await self._close_walk(ProjectionEndpoint.ENROLLMENTS, reached)
        return reached

    def counts(self) -> tuple[SyncResourceCounts, ...]:
        """What the run did, one row per FHIR resource type, in the order the types were walked."""
        return tuple(
            SyncResourceCounts(
                resource_type=resource_type, created=tally.created, updated=tally.updated, removed=tally.removed
            )
            for resource_type, tally in self._counts.items()
        )

    def counts_line(self) -> str:
        """The one-line tally a finished step is narrated with."""
        held = self._counts.values()
        return (
            f"{sum(tally.created for tally in held)} created, {sum(tally.updated for tally in held)} updated, "
            f"{sum(tally.removed for tally in held)} removed over {self.pages} page(s)"
        )

    async def _write_entities(self, entities: list[TrackerTrackedEntity], resource_type: str) -> datetime | None:
        """Project one page of tracked entities, write it as one batch, and answer its latest instant.

        A tombstone becomes a removal and everything else becomes a row. The counts are honest rather
        than assumed: whether a row is new is read out of the projection before it is written, which
        is one indexed local get per entity and the difference between a report that says what
        happened and one that says how many rows went past.
        """
        resources: list[ProjectedResource] = []
        removed: list[ProjectedResourceKey] = []
        names: list[IndexedName] = []
        latest: datetime | None = None
        for entity in entities:
            tracked_entity_uid = entity.trackedEntity
            if tracked_entity_uid is None:
                continue
            instant = as_instant(entity.updatedAt)
            latest = _later(latest, instant)
            held = await self._store.read(resource_type, tracked_entity_uid)
            if entity.deleted:
                if held is not None:
                    removed.append(ProjectedResourceKey(resource_type=resource_type, resource_id=tracked_entity_uid))
                    self._tally(resource_type).removed += 1
                continue
            self._materialized.add(tracked_entity_uid)
            registered = registered_entity_for(entity, self._surface.index, resource_type)
            resources.append(
                ProjectedResource(
                    resource_type=resource_type,
                    resource_id=tracked_entity_uid,
                    cursor=ProjectionCursor(updated_at=instant),
                    tracked_entity_type_uid=entity.trackedEntityType,
                    body=registered.model_dump(mode="json", exclude_none=True, by_alias=True),
                )
            )
            names.extend(
                IndexedName(
                    tracked_entity_uid=tracked_entity_uid,
                    attribute_uid=value.attribute_uid,
                    value=value.value,
                    tracked_entity_type_uid=entity.trackedEntityType,
                )
                for value in attribute_values(entity, self._surface.index)
            )
            tally = self._tally(resource_type)
            if held is not None:
                tally.updated += 1
            else:
                tally.created += 1
        if not self._dry_run and (resources or removed):
            await self._store.write(
                ProjectionBatch(resources=tuple(resources), removed=tuple(removed), names=tuple(names))
            )
        return latest

    async def _close_walk(self, endpoint: ProjectionEndpoint, reached: datetime | None) -> None:
        """Advance one collection's watermark, once every row the walk read is already durable."""
        if self._dry_run or reached is None:
            return
        await self._store.write(ProjectionBatch(endpoint=endpoint, cursor=ProjectionCursor(updated_at=reached)))

    def _tally(self, resource_type: str) -> _Tally:
        """The running total for one FHIR resource type, started at zero the first time it is asked for."""
        return self._counts.setdefault(resource_type, _Tally())


def _since(watermark: datetime | None, overlap: timedelta) -> datetime | None:
    """What an incremental poll asks `updatedAfter` for: the watermark, less the overlap window.

    None is the full read, and it is what a projection nobody has filled answers. The window is
    subtracted rather than the watermark trusted exactly, because `updatedAfter` boundary semantics,
    clock skew, and transactions in flight at the instant of a poll all drop rows at the edge - and
    a re-read costs one upsert where a dropped row is a person who silently stops existing
    (`docs/fhir/design/projection.md` section 5.2, rule 2).
    """
    return None if watermark is None else watermark - overlap


def _later(held: datetime | None, candidate: datetime | None) -> datetime | None:
    """The later of two instants, either of which may be an instant nobody stated."""
    if candidate is None:
        return held
    return candidate if held is None else max(held, candidate)


def _narrate(narrator: SyncNarrator | None, index: int, label: str, summary: str) -> None:
    """Announce one finished step, or nothing at all where the run was started quietly."""
    if narrator is not None:
        narrator.complete(index, SYNC_STEPS, label, summary)
