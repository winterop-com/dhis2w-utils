"""Source abstraction: the engine fetches rows through a `DataSource` it never has to understand.

A `ResourceBinder` maps a pipeline's source name to a `DataSource`. The DHIS2 binding lives in the
`query` plugin; `InMemoryDataSource`/`InMemoryBinder` here back tests and local fixtures.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from dhis2w_ql.engine.plan import NativeQuery, SourceCapabilities


@runtime_checkable
class DataSource(Protocol):
    """A fetchable collection of rows that may satisfy part of a query natively."""

    def capabilities(self) -> SourceCapabilities:
        """Report which pushdown operations this source can satisfy."""
        ...

    async def fetch(self, native: NativeQuery) -> list[Any]:
        """Fetch rows, honouring whatever portion of `native` the capabilities allow."""
        ...


@runtime_checkable
class CountableSource(Protocol):
    """A source that can return a total row count natively (e.g. via a pager total) without fetching."""

    async def count(self, native: NativeQuery) -> int:
        """Return how many rows match the native query's filters, without fetching them.

        The count ignores `skip`/`limit`: the engine narrows the total by the pushed paging itself.
        """
        ...


@runtime_checkable
class ResourceBinder(Protocol):
    """Resolves a pipeline source name to a `DataSource`, or None when it is not a known resource."""

    def bind(self, name: str) -> DataSource | None:
        """Return a data source for `name`, or None when the name is not a bindable resource."""
        ...

    def bind_call(self, name: str, args: dict[str, Any]) -> DataSource | None:
        """Return a data source for a call source `name(args)` (e.g. analytics), or None when unknown."""
        ...


class InMemoryDataSource:
    """A data source backed by an in-memory list; declares no native capabilities (all-local)."""

    def __init__(self, rows: list[Any]) -> None:
        """Hold the rows this source will return verbatim."""
        self._rows = rows

    def capabilities(self) -> SourceCapabilities:
        """In-memory sources push nothing down; the engine applies every stage locally."""
        return SourceCapabilities()

    async def fetch(self, native: NativeQuery) -> list[Any]:
        """Return all rows; pushdown is a no-op for an in-memory source."""
        return list(self._rows)


class InMemoryBinder:
    """Binds resource names to in-memory row lists (test/fixture binding)."""

    def __init__(self, resources: dict[str, list[Any]]) -> None:
        """Hold the name-to-rows mapping this binder resolves against."""
        self._resources = resources

    def bind(self, name: str) -> DataSource | None:
        """Return an in-memory source for `name`, or None when the name is unknown."""
        if name not in self._resources:
            return None
        return InMemoryDataSource(self._resources[name])

    def bind_call(self, name: str, args: dict[str, Any]) -> DataSource | None:
        """In-memory binding has no call sources; bind a name with no args, else None."""
        return self.bind(name) if not args else None
