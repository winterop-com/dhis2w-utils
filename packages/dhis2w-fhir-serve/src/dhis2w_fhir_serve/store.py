"""The IG resource store: every resource the facade serves, loaded once and indexed for read and search.

A store holds two trees merged into one collection. `ig/fsh-generated/resources` is what SUSHI
compiled from the emitted FSH, and `ig/input/resources` is the predefined registry, terminology,
and category tree the project committed by hand - SUSHI never re-emits those, so a store built
from the compiled tree alone would serve a partial IG.

Resources are held as the bytes they were written as. The store parses just enough of each one to
index it (`resourceType`, `id`, `url`, `identifier[]`) and passes the rest through untouched, so
what a FHIR client reads back is exactly what the project publishes. ConceptMap is the one type
read further than its index: `$translate` answers off mappings, not off a document, so the stored
maps are parsed into their R4 models at load and held alongside the entries.

`GUIDE_CONFORMANCE_RESOURCE_TYPES` is the one set of types this module names for a reason other than
indexing. They ride the compiled tree like everything else, and `load_compiled_conformance_entries`
reads them out of it on their own so that a live store - built from a DHIS2 instance, holding no
definitional layer of its own - hosts the same guide the compiled one does.

This module knows nothing about DHIS2 - a live store is built elsewhere and lands in the same
`ResourceStore` shape.
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from pathlib import Path
from typing import Any

from dhis2w_fhir.config import FhirProject
from dhis2w_fhir.r4 import ConceptMap
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, ValidationError

from dhis2w_fhir_serve.log import LOGGER_NAME

#: Directory under the IG that SUSHI compiles FSH into.
COMPILED_RESOURCES_RELATIVE_PATH = "fsh-generated/resources"

#: The resource type `$translate` reads its mappings from.
CONCEPT_MAP_RESOURCE_TYPE = "ConceptMap"

#: The conformance resources a compiled guide publishes, which a served project hosts read-only.
#:
#: A guide has to be resolvable before it is published somewhere of its own, and until then the
#: facade serving it is the only address its canonicals have. These three are what SUSHI actually
#: emits for a generated project: the profiles and extensions a response claims, the guide resource
#: that lists them, and the definition of the one operation `/metadata` declares. SearchParameter is
#: not among them because a generated project emits none, and a type nothing writes is a type the
#: store would never hold.
# CapabilityStatement here is the guide's `kind #requirements` statement - the one /metadata
# `instantiates` - not this server's own instance statement, which /metadata alone answers.
GUIDE_CONFORMANCE_RESOURCE_TYPES = (
    "StructureDefinition",
    "ImplementationGuide",
    "OperationDefinition",
    "CapabilityStatement",
)

logger = logging.getLogger(LOGGER_NAME)


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
    passthrough: modelling a subset would silently drop the rest. That is what lets the conformance
    resources be served without a model apiece - a profile is answered as the bytes SUSHI wrote. The
    dict leaves the store only as an HTTP response body, never as an argument another layer reads
    fields off.
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
    _concept_maps: tuple[ConceptMap, ...] = PrivateAttr(default=())

    def model_post_init(self, context: Any, /) -> None:
        """Build the read indexes (private attributes stay settable on a frozen model)."""
        for entry in self.entries:
            self._by_type_and_id.setdefault((entry.resource_type, entry.resource_id), entry)
            if entry.canonical_url is not None:
                self._by_canonical.setdefault(entry.canonical_url, entry)
        self._concept_maps = self._parse_concept_maps()

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

    def concept_maps(self) -> tuple[ConceptMap, ...]:
        """Every ConceptMap the store holds, as the R4 models `$translate` reads its mappings off."""
        return self._concept_maps

    def types_present(self) -> tuple[str, ...]:
        """Every resource type the store holds, sorted."""
        return tuple(sorted({entry.resource_type for entry in self.entries}))

    def summary(self) -> StoreSummary:
        """Resource counts per type."""
        counts = Counter(entry.resource_type for entry in self.entries)
        return StoreSummary(counts_by_type=dict(sorted(counts.items())))

    def _parse_concept_maps(self) -> tuple[ConceptMap, ...]:
        """Parse the stored ConceptMaps once, at load, so `$translate` reads models rather than documents.

        A ConceptMap the R4 model cannot read - an IG is free to hand-write elements this package
        does not serve - is left out and named in the log, so one unreadable document costs its own
        mappings rather than the whole operation.
        """
        parsed: list[ConceptMap] = []
        for entry in self.entries:
            if entry.resource_type != CONCEPT_MAP_RESOURCE_TYPE:
                continue
            try:
                parsed.append(ConceptMap.model_validate(entry.body))
            except ValidationError as error:
                logger.warning("%s: ConceptMap holds elements this server cannot read (%s)", entry.source, error)
        return tuple(parsed)

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


BUILTIN_CONFORMANCE_DIRECTORY = "conformance"
"""Where this package keeps the conformance resources that are the facade's own, not any guide's."""


def builtin_conformance_entries() -> tuple[StoreEntry, ...]:
    """The conformance resources this package itself publishes, served by every run.

    One today: the `$evaluate` OperationDefinition, whose canonical the CapabilityStatement names.
    The facade never names a canonical it cannot answer for, so what /metadata points at is readable
    here and searchable by `url` exactly like the guide's own definitions. Product-level rather than
    per-guide, which is why these ride the package instead of the compiled tree.
    """
    entries: list[StoreEntry] = []
    package_directory = Path(__file__).parent / BUILTIN_CONFORMANCE_DIRECTORY
    for path in sorted(package_directory.glob("*.json")):
        body = json.loads(path.read_text())
        entries.append(
            StoreEntry(
                resource_type=str(body["resourceType"]),
                resource_id=str(body["id"]),
                canonical_url=body.get("url"),
                identifiers=(),
                source=path.as_posix(),
                body=body,
            )
        )
    return tuple(entries)


def attach_builtin_conformance(store: ResourceStore) -> ResourceStore:
    """The store with the package's own conformance resources appended, whichever mode built it."""
    return ResourceStore(entries=(*store.entries, *builtin_conformance_entries()))


def load_compiled_conformance_entries(project: FhirProject) -> tuple[StoreEntry, ...]:
    """Read the conformance resources out of a project's compiled IG, and nothing else from it.

    This is how one guide reaches both store modes. A compiled store already holds these along with
    everything else the build wrote, and a live store is built from a DHIS2 instance and has no
    definitional layer of its own - no FSH compiler runs in the server - so a live run reads them
    from whatever SUSHI last compiled beside the project and hosts that.

    A project with no compiled tree beside it holds none, and says so by holding none: the store has
    fewer types and the CapabilityStatement declares exactly the types the store has. The parse is
    the strict one `load_compiled_store` uses, for the reason stated there.
    """
    compiled_directory = project.ig_directory / "fsh-generated" / "resources"
    if not compiled_directory.is_dir():
        return ()
    entries = (_read_entry(path, project.project_root) for path in sorted(compiled_directory.glob("*.json")))
    return tuple(entry for entry in entries if entry.resource_type in GUIDE_CONFORMANCE_RESOURCE_TYPES)


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
