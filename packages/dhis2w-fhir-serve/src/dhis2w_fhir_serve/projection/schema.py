"""The four tables a materialized projection is held in, and the one connection they are reached over.

`docs/fhir/design/projection.md` step 3 asks for SQLAlchemy over aiosqlite with typed `Mapped[...]`
columns, which is CLAUDE.md rule 10's own default for state - and a projection is state in the exact
sense that rule draws: derived, mutable, queried by predicate. The spool stayed as files on the other
side of that line, because a receipt is an immutable artifact; this is the side the line was drawn to
put something on.

WHAT IS TYPED AND WHAT IS NOT. The document is held as the wire JSON it was projected into, in one
text column, and every dimension a query runs over is a column beside it: which resource it is, which
identifiers name it, which instant it was written at. That is the split `StoreEntry.body` already
states - parse just enough to index, pass the rest through untouched - and it is what lets the
projection hold a resource this toolkit gains a model for tomorrow without a schema change today.

THE INSTANTS ARE THE INSTANCE'S OWN CLOCK, AND THEY ARE NAIVE ON PURPOSE. DHIS2 2.43 answers
`updatedAt` as a zone-less wall-clock reading in the instance's own zone (BUGS.md 62), and a sync's
watermark is compared against, and sent back as, exactly that reading. Stamping it with this host's
zone would make the cursor a claim about a clock nobody consulted, and the first `updatedAfter` built
from it would silently skip or re-read hours of rows. So the columns are naive, the values come from
DHIS2 and never from `datetime.now`, and nothing here converts.

THERE IS NO MIGRATION AND THAT IS THE DESIGN. D3 makes rebuilding routine rather than a recovery
step, so the way a schema change reaches a projection is `d2w fhir sync --rebuild`: the tables are
created if they are absent, and a projection whose shape has moved on is refilled from the instance
that is the record for all of it. A migration would be machinery for carrying forward a copy that is
cheaper to make again.
"""

from __future__ import annotations

from datetime import datetime  # noqa: TC003 - SQLAlchemy resolves `Mapped[...]` annotations at runtime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Index, String, Text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

if TYPE_CHECKING:
    from pathlib import Path

    from sqlalchemy.ext.asyncio import AsyncSession

#: What a stored identifier's system column holds when the identifier states no system at all.
#:
#: An empty string rather than NULL, because the column is part of a primary key and SQLite does not
#: hold NULL to a uniqueness rule - two identifiers differing only in "no system" would both land.
NO_IDENTIFIER_SYSTEM = ""


class ProjectionBase(DeclarativeBase):
    """The declarative base every projection table is defined on."""


class ProjectedResourceRow(ProjectionBase):
    """One projected FHIR resource: what it is, when it was written, and the document verbatim."""

    __tablename__ = "projected_resource"

    resource_type: Mapped[str] = mapped_column(String, primary_key=True)
    resource_id: Mapped[str] = mapped_column(String, primary_key=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)


class ProjectedIdentifierRow(ProjectionBase):
    """One `identifier` entry of one projected resource, as the token search matches it.

    Every value of `Resource.identifier[]` lands here, system and all, so a `system|value` token and
    a bare value are the same index read with one predicate more or less. The row is a copy of what
    the document already says - the document stays the answer, and this is only how it is found.
    """

    __tablename__ = "projected_identifier"

    resource_type: Mapped[str] = mapped_column(String, primary_key=True)
    resource_id: Mapped[str] = mapped_column(String, primary_key=True)
    system: Mapped[str] = mapped_column(String, primary_key=True, default=NO_IDENTIFIER_SYSTEM)
    value: Mapped[str] = mapped_column(String, primary_key=True)

    __table_args__ = (
        Index("ix_projected_identifier_value", "resource_type", "value"),
        Index("ix_projected_identifier_system_value", "resource_type", "system", "value"),
    )


class ProjectedNameRow(ProjectionBase):
    """One attribute value a tracked entity is searchable by, and the folded key a name search matches.

    `folded` is `value.casefold()` and it is what makes a name search behave the way the `:like:`
    filter of `docs/fhir/design/projection.md` section 3.3 measured: a case-insensitive substring
    match, which is the finding that page tells any replacement index not to regress. Lao and Khmer
    are written without spaces, so a word-tokenising analyzer would find LESS than a substring does -
    the interior substring and the bare Khmer consonant both hit, and both keep hitting here.

    What this column deliberately does not hold is a transliteration. Finding `ສົມສັກ` from `Somsack`
    is R8, it is an index-time ICU chain, and it arrives with the OpenSearch backend of step 6. A
    fold is honest about being a fold.
    """

    __tablename__ = "projected_name"

    tracked_entity_uid: Mapped[str] = mapped_column(String, primary_key=True)
    attribute_uid: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str] = mapped_column(String, primary_key=True)
    folded: Mapped[str] = mapped_column(String, nullable=False)
    tracked_entity_type_uid: Mapped[str | None] = mapped_column(String, nullable=True)

    __table_args__ = (
        Index("ix_projected_name_folded", "folded"),
        Index("ix_projected_name_attribute_folded", "attribute_uid", "folded"),
    )


class ProjectionWatermarkRow(ProjectionBase):
    """How far one tracker collection has been read, which is what the next poll asks from.

    One row per `ProjectionEndpoint`, never one row for the projection, because the polled collections
    move independently and a single global cursor would be a guess about which of their clocks leads
    (`docs/fhir/design/projection.md` section 5.2, rule 3).
    """

    __tablename__ = "projection_watermark"

    endpoint: Mapped[str] = mapped_column(String, primary_key=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


def open_projection_engine(database_path: Path) -> AsyncEngine:
    """Open the aiosqlite engine one projection file is reached over, without touching the file yet."""
    return create_async_engine(f"sqlite+aiosqlite:///{database_path}", echo=False, future=True)


def projection_sessions(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """The session factory every read and every write of a projection runs in, one transaction apiece."""
    return async_sessionmaker(engine, expire_on_commit=False)


async def create_projection_tables(engine: AsyncEngine) -> None:
    """Create whatever of the four tables is absent, which is what opening an empty projection does."""
    async with engine.begin() as connection:
        await connection.run_sync(ProjectionBase.metadata.create_all)
