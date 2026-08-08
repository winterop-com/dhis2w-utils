"""The IG resource store: every resource the facade serves, loaded once and indexed for read and search.

A store holds two trees merged into one collection. `ig/fsh-generated/resources` is what SUSHI
compiled from the emitted FSH, and `ig/input/resources` is the predefined registry, terminology,
and category tree the project committed by hand - SUSHI never re-emits those, so a store built
from the compiled tree alone would serve a partial IG.

Resources are held as the bytes they were written as. The store parses just enough of each one to
index it (`resourceType`, `id`, `url`, `identifier[]`) and passes the rest through untouched, so
what a FHIR client reads back is exactly what the project publishes.

This module knows nothing about DHIS2 - a live store is built elsewhere and lands in the same
`ResourceStore` shape.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from dhis2w_fhir.config import FhirProject
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr

#: Directory under the IG that SUSHI compiles FSH into.
COMPILED_RESOURCES_RELATIVE_PATH = "fsh-generated/resources"


class CompiledIgMissingError(LookupError):
    """Raised when a project has no compiled IG to serve."""

    def __init__(self) -> None:
        super().__init__(
            "no compiled IG at ig/fsh-generated/resources - run `d2w fhir generate`, "
            "then `make sushi` in the project, and serve again."
        )


class IdentifierToken(BaseModel):
    """One `system|value` search token, with `system=None` standing for the value in any system."""

    model_config = ConfigDict(frozen=True)

    system: str | None = None
    value: str


class StoreEntry(BaseModel):
    """One served resource: the index fields the facade reads it by, plus the resource itself."""

    model_config = ConfigDict(frozen=True)

    resource_type: str
    resource_id: str
    canonical_url: str | None = None
    identifiers: tuple[IdentifierToken, ...] = ()
    source: str
    """Posix path of the file this entry was read from, or the `live` marker for a built store."""

    body: dict[str, Any]
    """The resource verbatim - the one deliberate `dict[str, Any]` in this package.

    An IG holds resource types this repo has no models for (StructureDefinition, ImplementationGuide,
    whatever a project hand-writes into `input/resources`), and the server's contract is byte-faithful
    passthrough: modelling a subset would silently drop the rest. The dict leaves the store only as an
    HTTP response body, never as an argument another layer reads fields off.
    """


class SearchQuery(BaseModel):
    """The search parameters the facade supports, in FHIR's combination semantics.

    Within one field the values OR (`_id=a,b` matches either), across fields they AND
    (`_id=a&url=x` matches only the resource that is both). An empty query matches every
    resource of the searched type. An identifier token with `system=None` matches the value
    in any system, mirroring a bare `identifier=value` search.
    """

    model_config = ConfigDict(frozen=True)

    ids: tuple[str, ...] = ()
    urls: tuple[str, ...] = ()
    identifiers: tuple[IdentifierToken, ...] = ()

    def is_empty(self) -> bool:
        """True when no parameter was given, so the query matches every resource of the type."""
        return not (self.ids or self.urls or self.identifiers)


class StoreSummary(BaseModel):
    """How many resources of each type the store holds - the shape a capability or status page reports."""

    model_config = ConfigDict(frozen=True)

    counts_by_type: dict[str, int] = Field(default_factory=dict)

    @property
    def total(self) -> int:
        """Total resources across every type."""
        return sum(self.counts_by_type.values())


class ResourceStore(BaseModel):
    """Every resource the facade serves, indexed by `(resourceType, id)` and by canonical url.

    The entry tuple is the load order - compiled resources first, then the predefined tree - and
    the indexes are built once in `model_post_init`. When both trees carry the same
    `(resourceType, id)` the first one loaded wins, so a compiled resource is never shadowed.
    """

    model_config = ConfigDict(frozen=True)

    entries: tuple[StoreEntry, ...] = ()

    _by_type_and_id: dict[tuple[str, str], StoreEntry] = PrivateAttr(default_factory=dict)
    _by_canonical: dict[str, StoreEntry] = PrivateAttr(default_factory=dict)

    def model_post_init(self, context: Any, /) -> None:
        """Build the read indexes (private attributes stay settable on a frozen model)."""
        for entry in self.entries:
            self._by_type_and_id.setdefault((entry.resource_type, entry.resource_id), entry)
            if entry.canonical_url is not None:
                self._by_canonical.setdefault(entry.canonical_url, entry)

    def by_type_and_id(self, resource_type: str, resource_id: str) -> StoreEntry | None:
        """The resource a `GET /{type}/{id}` read resolves to, or None."""
        return self._by_type_and_id.get((resource_type, resource_id))

    def by_canonical(self, canonical_url: str) -> StoreEntry | None:
        """The resource a canonical url resolves to, whatever its type, or None."""
        return self._by_canonical.get(canonical_url)

    def search(self, resource_type: str, query: SearchQuery) -> tuple[StoreEntry, ...]:
        """Every resource of `resource_type` matching the query, in load order."""
        candidates = [entry for entry in self.entries if entry.resource_type == resource_type]
        if query.is_empty():
            return tuple(candidates)
        return tuple(entry for entry in candidates if self._matches(entry, query))

    def types_present(self) -> tuple[str, ...]:
        """Every resource type the store holds, sorted."""
        return tuple(sorted({entry.resource_type for entry in self.entries}))

    def summary(self) -> StoreSummary:
        """Resource counts per type."""
        counts = Counter(entry.resource_type for entry in self.entries)
        return StoreSummary(counts_by_type=dict(sorted(counts.items())))

    @staticmethod
    def _matches(entry: StoreEntry, query: SearchQuery) -> bool:
        """AND every given field of the query, OR the values within each one."""
        if query.ids and entry.resource_id not in query.ids:
            return False
        if query.urls and entry.canonical_url not in query.urls:
            return False
        return not query.identifiers or any(
            ResourceStore._matches_identifier(entry, token) for token in query.identifiers
        )

    @staticmethod
    def _matches_identifier(entry: StoreEntry, token: IdentifierToken) -> bool:
        """A token matches when the value matches and the system matches, or the token names no system."""
        return any(
            held.value == token.value and (token.system is None or held.system == token.system)
            for held in entry.identifiers
        )


def load_compiled_store(project: FhirProject) -> ResourceStore:
    """Read a project's compiled IG plus its predefined resource tree into a store.

    The load is strict: a file that is not a JSON object, or that carries no string `resourceType`
    and `id`, fails loudly naming the file rather than being skipped, because a resource the store
    silently drops reads to a client as a resource the IG never published.
    """
    compiled_directory = project.ig_directory / "fsh-generated" / "resources"
    compiled_paths = sorted(compiled_directory.glob("*.json")) if compiled_directory.is_dir() else []
    if not compiled_paths:
        raise CompiledIgMissingError

    predefined_directory = project.resources_directory
    predefined_paths = sorted(predefined_directory.rglob("*.json")) if predefined_directory.is_dir() else []

    entries = [_read_entry(path, project.project_root) for path in [*compiled_paths, *predefined_paths]]
    return ResourceStore(entries=tuple(entries))


def _read_entry(path: Path, project_root: Path) -> StoreEntry:
    """Parse one resource file into a store entry, failing loudly and naming the file."""
    try:
        body = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"{path}: not valid JSON ({error})") from error
    if not isinstance(body, dict):
        raise ValueError(f"{path}: expected a JSON object holding a FHIR resource")
    resource_type = body.get("resourceType")
    resource_id = body.get("id")
    if not isinstance(resource_type, str) or not resource_type:
        raise ValueError(f"{path}: resource has no `resourceType`")
    if not isinstance(resource_id, str) or not resource_id:
        raise ValueError(f"{path}: resource has no `id`")
    canonical_url = body.get("url")
    return StoreEntry(
        resource_type=resource_type,
        resource_id=resource_id,
        canonical_url=canonical_url if isinstance(canonical_url, str) else None,
        identifiers=_read_identifiers(body),
        source=_relative_source(path, project_root),
        body=body,
    )


def _read_identifiers(body: dict[str, Any]) -> tuple[IdentifierToken, ...]:
    """Index `identifier`, which FHIR declares as a list on most types and as a single value on a few."""
    raw = body.get("identifier")
    candidates = raw if isinstance(raw, list) else [raw]
    tokens: list[IdentifierToken] = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        value = candidate.get("value")
        if not isinstance(value, str):
            continue
        system = candidate.get("system")
        tokens.append(IdentifierToken(system=system if isinstance(system, str) else None, value=value))
    return tuple(tokens)


def _relative_source(path: Path, project_root: Path) -> str:
    """Name the file relative to the project when it lives inside it, so the marker stays portable."""
    try:
        return path.relative_to(project_root).as_posix()
    except ValueError:
        return path.as_posix()
