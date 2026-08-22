"""The `projection` backend of `NameSearchIndex`: the search keys the sync wrote, asked once.

WHAT IT IMPROVES OVER THE `dhis2` BACKEND, STATED HONESTLY. Two things, and not a third.

- **It answers a name.** The `dhis2` backend puts `filter=<attribute>:eq:<value>` on the wire, so it
  finds a person only from the whole of a value spelled exactly. This matches a case-insensitive
  substring of one, which is what `docs/fhir/design/projection.md` section 3.3 measured `:like:`
  doing and what that section tells any replacement not to regress: the interior substring hits, the
  bare Khmer consonant hits, and neither would survive a word-tokenising analyzer over scripts that
  are written without spaces.
- **It costs one query.** The `dhis2` backend spends one round trip per search key per tracked entity
  type, sequentially, while the caller waits. This is one indexed read of one local file however many
  keys and types are in scope, and it is as of the cursor rather than as of now.

What it does NOT do is transliterate. Finding `ສົມສັກ` from `Somsack` is R8 and it is an index-time
ICU chain that arrives with the OpenSearch backend of step 6; the four rows section 3.3's table marks
**fails** still fail here, and the tests say so rather than assuming otherwise.

WHAT IT DISCLOSES. A tracked entity UID and a score. Not a name, not a value, not an organisation
unit - the shape of `NameMatch` is what makes that a property rather than a promise. The register
resolves each match through `register.wire.fetch_tracked_entity` under the caller's own credentials,
so DHIS2 authorizes every record this facade hands over, per match, per caller, exactly as it does
when the instance itself did the finding. That is R9's recommended posture (iii) in full, and it is
the reason a projection can answer the finding half without this facade taking on one line of DHIS2's
authorization model.

WHY IT READS THROUGH THE STORE RATHER THAN OPENING THE FILE ITSELF. The projection has exactly one
connection, because it has exactly one writer, and a second engine over the same file would be a
second thing SQLite has to arbitrate for no gain at all. The index is a reader of the store's
database, and the store is what owns the file.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select

from dhis2w_fhir_serve.projection.base import IndexedName, NameMatch, NameMatches, NameQuery
from dhis2w_fhir_serve.projection.schema import ProjectedNameRow

if TYPE_CHECKING:
    from collections.abc import Sequence

    from dhis2w_fhir_serve.projection.sqlite_store import SqliteProjectionStore

#: The characters SQL `LIKE` reads as wildcards, and the escape this index spells them with.
_LIKE_ESCAPE = "\\"
_LIKE_WILDCARDS = ("%", "_")

#: What a substring match scores against what an exact match scores.
#:
#: Two numbers rather than a distance, because two is all this index can honestly tell apart. A
#: folded value that IS the query is the thing the caller typed; a folded value that merely contains
#: it is a candidate. Ranking the middle ground needs the analyzer chain step 6 brings, and a score
#: invented here would be a precision this backend does not have.
EXACT_MATCH_SCORE = 1.0
SUBSTRING_MATCH_SCORE = 0.5


class SqliteNameSearchIndex:
    """Finds candidate tracked entities in the materialized projection, one indexed query per lookup."""

    def __init__(self, store: SqliteProjectionStore) -> None:
        """Read through the projection store that owns the file - see this module's docstring on why."""
        self._store = store

    async def index(self, entries: Sequence[IndexedName]) -> None:
        """Hold nothing on its own: a search key reaches this index on the batch its resource rides.

        The keys and the documents they find have to become true at the same instant, so they travel
        in one `ProjectionBatch` and land in one transaction. An `index` that wrote separately would
        be a second watermark with a second way of being wrong, which is the failure
        `docs/fhir/design/projection.md` section 5.2 rule 1 exists to make impossible.
        """
        return None

    async def find(self, query: NameQuery) -> NameMatches:
        """Answer the tracked entities one value matches, exact first, as of the projection's cursor.

        The value is folded and matched as a substring, which is the measured behaviour of the filter
        this replaces. An empty value matches nobody rather than everybody: a lookup that was given
        nothing to look for is not a request to hand over the register.
        """
        needle = query.value.strip().casefold()
        if not needle:
            return NameMatches(cursor=await self._store.cursor())
        async with self._store.session() as session:
            statement = select(ProjectedNameRow).where(
                ProjectedNameRow.folded.like(f"%{_escaped(needle)}%", escape=_LIKE_ESCAPE)
            )
            if query.attribute_uids:
                statement = statement.where(ProjectedNameRow.attribute_uid.in_(query.attribute_uids))
            if query.tracked_entity_type_uids:
                statement = statement.where(
                    ProjectedNameRow.tracked_entity_type_uid.in_(query.tracked_entity_type_uids)
                )
            rows = (await session.execute(statement)).scalars().all()
            cursor = await self._store.cursor()
        found: dict[str, NameMatch] = {}
        for row in sorted(rows, key=lambda row: (row.folded != needle, row.tracked_entity_uid)):
            found.setdefault(
                row.tracked_entity_uid,
                NameMatch(
                    tracked_entity_uid=row.tracked_entity_uid,
                    score=EXACT_MATCH_SCORE if row.folded == needle else SUBSTRING_MATCH_SCORE,
                ),
            )
        matches = tuple(found.values())
        return NameMatches(matches=matches if query.limit is None else matches[: query.limit], cursor=cursor)

    async def forget(self, tracked_entity_uids: Sequence[str]) -> None:
        """Drop nothing on its own: a tombstone reaches this index on the batch that removes the row.

        Same reason `index` holds nothing. `SqliteProjectionStore.write` deletes a removed resource's
        search keys in the transaction that deletes the resource, so the two can never disagree about
        whether somebody is still in the register.
        """
        return None


def _escaped(needle: str) -> str:
    """One folded value with its `LIKE` wildcards spelled out, so a `%` in a name is a `%` in a name."""
    escaped = needle.replace(_LIKE_ESCAPE, _LIKE_ESCAPE * 2)
    for wildcard in _LIKE_WILDCARDS:
        escaped = escaped.replace(wildcard, f"{_LIKE_ESCAPE}{wildcard}")
    return escaped
