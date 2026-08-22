"""The two Protocols a projection is served over, and the models they speak in.

`ProjectionStore` is the durable document backend: the mapped scope of a DHIS2 instance held as FHIR
resources, filled by a sync and by nothing else. `NameSearchIndex` is the lookup beside it: it finds
candidates and it answers with identifiers. Both are async, because everything in the serve layer is.

WHY THEY ARE TWO PROTOCOLS AND NOT ONE. They are separately adoptable, separately backed, and -
this is the sharp one - separately safe. A store holds records, so serving an answer out of one
means this facade has decided the caller may see it. An index holds no records, so it can do its
whole job while disclosing nothing but the fact that some identifier matched.

AUTHORIZATION BY CONSTRUCTION, WHICH IS WHY `NameMatch` CARRIES SO LITTLE. DHIS2 enforces sharing,
organisation-unit scope, and tracker ownership in the request path, and a projection takes DHIS2 out
of the request path. `docs/fhir/design/projection.md` R9 is the posture that answer forces: an index
discloses a tracked entity UID and how well it matched, and **resolving one of those UIDs into a
record goes back through the live, caller-credentialed read** - `register.wire.fetch_tracked_entity`,
under the caller's own credentials, exactly as a register read runs today. So DHIS2 decides, per UID,
per caller, what may be seen; a caller who may not see somebody gets nothing back from the read and
learns from the search only that an identifier exists. Nothing in this module may widen that: a field
added to `NameMatch` is a disclosure this facade makes without asking DHIS2, and there is no place in
the design where that is the right thing to add.

WHERE THAT LINE ACTUALLY FALLS, NOW THAT A STORE EXISTS. The store holds whole records, because a
document backend that held less could rebuild neither its own index nor the evaluations of steps 8
and 9 without re-reading the instance. What it never does is hand one over on its own authority: a
`ProjectionStore` answer names candidates, and `routes/register` reads each one back live under the
caller's credentials before it reaches a Bundle. So the boundary is at the response and not at the
row - which is R9's posture (iii) exactly, and section 6's one rule regardless of posture: the
projection stores what a configured BUILD identity could read, and the facade never lets a caller's
own identity imply more than that.

THE STORE'S DOCTRINE, in one line each, from section 4 of the same paper. A projection is derived and
its sync is the only thing that writes it; it is rebuildable from zero as a routine operation; every
row is cursor-stamped and every answer served from it states the cursor it was read at; and DHIS2
stays the record for everything DHIS2 can hold.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from collections.abc import Sequence


class ProjectionEndpoint(StrEnum):
    """Which DHIS2 tracker collection a watermark belongs to.

    One watermark per collection rather than one for the projection, because
    `docs/fhir/design/projection.md` section 3.4 measured them as independent polls with independent
    tombstone behaviour, and 5.2 rule 3 draws the conclusion: a single global cursor would be a guess
    about which endpoint's clock leads.

    Two, and `/api/tracker/events` is deliberately not a third. A projected register resource carries
    identity and attribute values (`register.projection`), and an event carries neither - so an event
    that moved is not a change to anything this projection holds, and polling for one would be a
    request per interval spent to learn nothing. The event watermark arrives with the resources that
    need it, which is steps 8 and 9 of that paper. A member that parses and then has nothing to poll
    for is the shape `SearchBackend` refuses to reserve, and this refuses it for the same reason.
    """

    #: `/api/tracker/trackedEntities` - the collection the projected resources come from.
    TRACKED_ENTITIES = "trackedEntities"

    #: `/api/tracker/enrollments` - polled for whose enrollment moved, never projected on its own.
    #:
    #: A tracked entity's own `lastUpdated` does not move when an enrollment of theirs does, and an
    #: enrollment carries program-level attribute values that the projected resource does carry. So
    #: this poll says whose projection has gone stale, and the rows it finds are re-materialized from
    #: the tracked entity read rather than mapped here.
    ENROLLMENTS = "enrollments"


class ProjectionCursor(BaseModel):
    """How far a projection has been filled: the instant every change up to it has been read.

    A sync advances it in the same write as the batch it describes, which is what makes "the
    watermark never runs ahead of the rows" a property of the store rather than a convention a
    caller has to honour. `updated_at` is None on a projection nothing has been written into yet.
    """

    model_config = ConfigDict(frozen=True)

    updated_at: datetime | None = None


class ProjectedResourceKey(BaseModel):
    """Which resource one projection row is: the type it is served under, and the id it is served at."""

    model_config = ConfigDict(frozen=True)

    resource_type: str
    resource_id: str


class ProjectedResource(BaseModel):
    """One FHIR resource a projection holds, and the cursor the sync wrote it at."""

    model_config = ConfigDict(frozen=True)

    resource_type: str
    resource_id: str
    cursor: ProjectionCursor = Field(default_factory=ProjectionCursor)

    tracked_entity_type_uid: str | None = None
    """Which DHIS2 tracked entity type this resource is, where the entity it came from stated one.

    One FHIR resource type is served over every tracked entity type the published map takes onto it,
    so `resource_type` alone cannot answer "which of these are fridges" - two types both published as
    `Device` are one register and two kinds of thing. The document already states it as a `meta.tag`
    (`register.projection`); this is the same fact as a column, so a page narrowed to one type is one
    indexed query rather than a page read and then thinned.
    """

    body: dict[str, Any] = Field(default_factory=dict)
    """The FHIR document verbatim.

    The same HTTP/JSON-boundary escape hatch `StoreEntry.body` documents, and for the same reason: a
    store parses just enough of a document to index it and passes the rest through untouched, so a
    resource this toolkit has no model for is still a resource the projection can hold.
    """


class ProjectionWatermarks(BaseModel):
    """How far each polled tracker collection has been read, one instant apiece.

    Both are None on a projection nothing has been synced into. `cursor` folds them into the one
    instant an answer states, and it folds them by taking the EARLIER: a projection is as current as
    its least current half, and stating the later one would be claiming to know about changes at a
    collection nobody has polled that far.
    """

    model_config = ConfigDict(frozen=True)

    tracked_entities: datetime | None = None
    enrollments: datetime | None = None

    def at(self, endpoint: ProjectionEndpoint) -> datetime | None:
        """How far one collection has been read, or None where nothing has read it yet."""
        match endpoint:
            case ProjectionEndpoint.TRACKED_ENTITIES:
                return self.tracked_entities
            case ProjectionEndpoint.ENROLLMENTS:
                return self.enrollments

    def cursor(self) -> ProjectionCursor:
        """The one instant every answer served from this projection states - the earlier of the two."""
        marks = [mark for mark in (self.tracked_entities, self.enrollments) if mark is not None]
        return ProjectionCursor() if len(marks) < 2 else ProjectionCursor(updated_at=min(marks))


class ProjectionQuery(BaseModel):
    """What a caller is asking a projection for: which resources, which identifiers, and how many."""

    model_config = ConfigDict(frozen=True)

    resource_type: str
    identifiers: tuple[str, ...] = ()
    identifier_systems: tuple[str, ...] = ()
    """The systems those identifiers are looked for under; empty looks under every system held.

    Two questions FHIR spells with one parameter. `identifier=<system>|<value>` says which key the
    value is, and `identifier=<value>` says the caller does not know - so a query naming systems is
    the first and a query naming none is the second, and neither is a filter the other can express.
    """

    tracked_entity_type_uids: tuple[str, ...] = ()
    """Which tracked entity types the answer is narrowed to; empty asks about every type held.

    This is what `_tag` on a register search becomes. Narrowing in the store rather than after it is
    what keeps a narrowed page a full page: thinning a page of the whole resource down to one type
    would hand back a short page with more of that type still behind it.
    """

    offset: int = 0
    """How many resources to skip before the page starts, which is how the listing walks the store."""

    count: int | None = None
    """How many resources the caller will read, or None for as many as the backend carries."""


class ProjectionPage(BaseModel):
    """One page of a projection search: the resources on it, how many there are, and when it was read."""

    model_config = ConfigDict(frozen=True)

    resources: tuple[ProjectedResource, ...] = ()
    total: int | None = None
    """How many the whole result set holds, or None where the backend stated no total."""

    cursor: ProjectionCursor = Field(default_factory=ProjectionCursor)
    """The instant this page is as of, which every answer served from a projection states."""


class IndexedName(BaseModel):
    """One name an index holds for one tracked entity, in the script the instance stores it in."""

    model_config = ConfigDict(frozen=True)

    tracked_entity_uid: str
    attribute_uid: str
    value: str
    tracked_entity_type_uid: str | None = None


class ProjectionBatch(BaseModel):
    """One sync's worth of writes: the rows it maps, the rows it removes, and the cursor it advances to."""

    model_config = ConfigDict(frozen=True)

    resources: tuple[ProjectedResource, ...] = ()
    removed: tuple[ProjectedResourceKey, ...] = ()
    """What DHIS2 no longer holds. A tombstone means "remove the row", never "keep the last state"."""

    names: tuple[IndexedName, ...] = ()
    """The search keys the resources on this batch carry, written in the same transaction they are.

    An index that advanced separately from the documents it describes would be a second watermark
    with a second way of being wrong, and the whole reason the batch is one write is that there is
    exactly one instant at which the projection is true.
    """

    endpoint: ProjectionEndpoint | None = None
    """Which collection's watermark this batch advances, or None for a batch that advances none.

    Per-endpoint because the three collections are polled independently
    (`docs/fhir/design/projection.md` section 5.2, rule 3). None is the honest value for a batch
    written to re-materialize entities an enrollment poll found stale: it carries rows, it advances
    no watermark of its own, and the poll that found them advances theirs when it finishes.
    """

    cursor: ProjectionCursor = Field(default_factory=ProjectionCursor)


class NameQuery(BaseModel):
    """One lookup put to an index: the value typed, and how wide the index may look for it."""

    model_config = ConfigDict(frozen=True)

    value: str
    attribute_uids: tuple[str, ...] = ()
    """The attributes the value is looked for under; empty asks the backend to use every key it holds."""

    tracked_entity_type_uids: tuple[str, ...] = ()
    """The tracked entity types in scope; empty asks the backend to look across every type it holds."""

    limit: int | None = None
    """How many candidates the caller will read, or None for every one the backend finds.

    The register asks for None: a searchset states what was found rather than a page of it, and a
    lookup that quietly dropped the fifty-first person holding a value would be an answer that
    contradicts the question.
    """


class NameMatch(BaseModel):
    """One candidate an index found: which tracked entity, and how well it matched.

    Nothing else, deliberately. No attribute value, no organisation unit, no enrollment - see this
    module's docstring on authorization by construction. `display_name` is the label a candidate list
    shows where the backend holds one; the `dhis2` backend holds none, because the instance states no
    display name for a tracked entity and assembling one out of attribute values would be this index
    disclosing exactly what it exists not to disclose.
    """

    model_config = ConfigDict(frozen=True)

    tracked_entity_uid: str
    display_name: str | None = None
    score: float = 1.0


class NameMatches(BaseModel):
    """What an index answers a lookup with: the candidates, in the order it ranked them."""

    model_config = ConfigDict(frozen=True)

    matches: tuple[NameMatch, ...] = ()

    cursor: ProjectionCursor | None = None
    """When these matches are as of, and None where they were read live.

    A live answer states no cursor because there is no watermark to state: it is as of the moment
    the instance answered. An index backend fills this in, and the register's answer says so.
    """


@runtime_checkable
class ProjectionStore(Protocol):
    """Holds the FHIR projection of a DHIS2 instance, written only by sync."""

    async def read(self, resource_type: str, resource_id: str) -> ProjectedResource | None:
        """Read one projected resource, or None where the projection holds none under that id."""
        ...

    async def search(self, query: ProjectionQuery) -> ProjectionPage:
        """Answer one page of the projection, stating the cursor it was read at."""
        ...

    async def write(self, batch: ProjectionBatch) -> ProjectionCursor:
        """Write one sync's batch and answer the cursor the projection now stands at."""
        ...

    async def cursor(self) -> ProjectionCursor:
        """How far this projection has been filled, which every answer served from it states."""
        ...

    async def watermarks(self) -> ProjectionWatermarks:
        """How far each tracker collection has been read, which is what the next poll asks from."""
        ...

    async def rebuild(self) -> None:
        """Empty the projection so a full materialization can fill it from zero."""
        ...


@runtime_checkable
class NameSearchIndex(Protocol):
    """Finds candidate tracked entity identifiers by name, across scripts."""

    async def index(self, entries: Sequence[IndexedName]) -> None:
        """Hold these names, replacing whatever was held for the tracked entities they name."""
        ...

    async def find(self, query: NameQuery) -> NameMatches:
        """Answer the candidates one lookup matched - identifiers and scores, never records."""
        ...

    async def forget(self, tracked_entity_uids: Sequence[str]) -> None:
        """Drop everything held for these tracked entities, which is what a tombstone means here."""
        ...
