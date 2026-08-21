"""The `dhis2` backend of `NameSearchIndex`: the instance itself, asked one filtered search at a time.

IT IMPROVES NOTHING, AND THAT IS THE POINT. `find` runs exactly the search a live register has always
run - `filter=<attribute>:eq:<value>` against `/api/tracker/trackedEntities`, one query per key per
tracked entity type, `ouMode=ACCESSIBLE` on every one of them - so it is exactly as weak as an exact
match is, and it carries exactly today's authorization properties. Its whole value is that once a
lookup is the only path a register search takes, swapping in a real index is a config line rather
than a refactor. `docs/fhir/design/projection.md` section 7.2 is the design, and R5 is the reason
this backend is built first: a seam nothing has crossed is not a seam.

WHOSE CREDENTIALS IT READS UNDER. Whatever the `RegisterReader` it was handed reads under, which is
settled per request rather than per process: the caller's own `Authorization` under
`[serve] auth = "dhis2"`, and the runtime's client otherwise. `dhis2w_fhir_serve.passthrough` is
where that is decided, and nothing here branches on the answer.

WHAT IT DISCLOSES, AND WHAT IT DOES NOT. A match is a tracked entity UID and a score. The record
behind one is not this index's to hand over: the register resolves each match through
`register.wire.fetch_tracked_entity`, under the same credentials, so DHIS2 authorizes the disclosure
per match per caller - `docs/fhir/design/projection.md` R9. This backend therefore reads more than it
discloses, because the tracker endpoint answers a filtered search with whole entities and this index
keeps their identifiers alone. Narrowing that projection is an optimisation the index backends make
moot, and it is not what proves the seam.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

from dhis2w_fhir_serve.passthrough import RegisterReader
from dhis2w_fhir_serve.projection.base import IndexedName, NameMatch, NameMatches, NameQuery
from dhis2w_fhir_serve.register.wire import search_tracked_entities

if TYPE_CHECKING:
    from collections.abc import Sequence


class Dhis2NameSearchIndex(BaseModel):
    """Finds candidate tracked entities by asking the DHIS2 instance, one exact-match search per key."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    reader: RegisterReader
    """What this lookup reads DHIS2 through - the caller's own credentials, or the runtime's client."""

    async def index(self, entries: Sequence[IndexedName]) -> None:
        """Hold nothing: this backend is the instance, and DHIS2 is the only thing that writes it."""
        return None

    async def find(self, query: NameQuery) -> NameMatches:
        """Answer the tracked entities one value matches exactly, one query per key per type.

        Attribute-major, type-minor, first match first: the order a register search folds its result
        set in, and the order a client sees the entries in. A tracked entity matched under two keys
        is one candidate, because a person holding the same value twice is one person. No cursor is
        stated, because a live answer is as of the moment the instance answered it.
        """
        found: dict[str, NameMatch] = {}
        for attribute_uid in query.attribute_uids:
            for tracked_entity_type_uid in query.tracked_entity_type_uids:
                for entity in await search_tracked_entities(
                    self.reader,
                    tracked_entity_type_uid=tracked_entity_type_uid,
                    attribute_uid=attribute_uid,
                    value=query.value,
                ):
                    if entity.trackedEntity is not None:
                        found.setdefault(entity.trackedEntity, NameMatch(tracked_entity_uid=entity.trackedEntity))
        matches = tuple(found.values())
        return NameMatches(matches=matches if query.limit is None else matches[: query.limit])

    async def forget(self, tracked_entity_uids: Sequence[str]) -> None:
        """Drop nothing: an entity DHIS2 no longer holds is one this backend stops finding by itself."""
        return None
