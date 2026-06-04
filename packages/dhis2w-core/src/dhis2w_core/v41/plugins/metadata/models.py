"""Plugin-internal view-models for the metadata plugin.

`MetadataBundle` wraps DHIS2's `GET /api/metadata` response — a top-level
object keyed by resource name (`dataElements`, `indicators`, ...) plus two
meta keys (`system`, `date`). The bundle flows through the whole plugin
(export, import, diff, dangling-ref walker); typing it once here means no
callsite ever sees `dict[str, Any]` as a bundle type.

`MetadataItem` is the typed item inside each resource collection.
`extra="allow"` preserves every DHIS2 field without forcing a generated
model per resource; `id` + `name` are typed because they're the two fields
the plugin actually reads via attribute access (walker, diff keying,
display). Nested references inside an item (e.g. `categoryCombo: {id: x}`)
land in `model_extra` as bounded dicts — the innermost reachable-only
carveout allowed by the CLAUDE.md pydantic rule.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from pydantic import BaseModel, ConfigDict


class MetadataItem(BaseModel):
    """One object inside a metadata bundle — typed id/name with every other field preserved."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    id: str | None = None
    name: str | None = None

    def field(self, key: str) -> Any:
        """Read any non-typed field (from `model_extra`) or `None` when absent."""
        if key in ("id", "name"):
            return getattr(self, key)
        return (self.model_extra or {}).get(key)


# Resource keys in a DHIS2 metadata export that aren't resource collections
# — skipping them lets callers iterate only over real resource types.
_BUNDLE_META_KEYS: frozenset[str] = frozenset({"system", "date"})


class MetadataBundle(BaseModel):
    """Typed wrapper for a DHIS2 `GET /api/metadata` export bundle.

    Top-level keys come in two shapes:

    - Meta keys (`system`, `date`) — typed as nullable slots.
    - Resource collections (`dataElements`, `indicators`, ...) — dynamic
      set that varies by DHIS2 version and export narrowing. Held in
      `model_extra` with `extra="allow"`; reached through `resources()`,
      `get_resource(name)`, `resource_names()`, `has_resource(name)`.

    Items inside collections are `MetadataItem` — typed `id` / `name` plus
    preserved extras. The nested references inside an item's extras
    (`categoryCombo: {id: ...}`, `legendSets: [{id: ...}]`) stay as
    dicts: that's the innermost "bounded dict" carveout — dicts that
    are reachable only through typed accessors, never a function's
    top-level return type.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    system: dict[str, Any] | None = None
    date: str | None = None

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> MetadataBundle:
        """Parse a raw `GET /api/metadata` response into a typed `MetadataBundle`.

        Each resource collection's items are parsed through `MetadataItem`
        so every item carries typed id/name access while preserving the
        full DHIS2 shape in `model_extra`.
        """
        parsed: dict[str, Any] = {
            "system": raw.get("system"),
            "date": raw.get("date"),
        }
        for key, value in raw.items():
            if key in _BUNDLE_META_KEYS:
                continue
            if isinstance(value, list):
                parsed[key] = [MetadataItem.model_validate(item) for item in value if isinstance(item, dict)]
            else:
                parsed[key] = value
        return cls.model_validate(parsed)

    def resources(self) -> Iterator[tuple[str, list[MetadataItem]]]:
        """Iterate resource collections in insertion order (skipping `system` + `date`)."""
        for key, value in (self.model_extra or {}).items():
            if key in _BUNDLE_META_KEYS:
                continue
            if isinstance(value, list) and all(isinstance(entry, MetadataItem) for entry in value):
                yield key, value

    def get_resource(self, name: str) -> list[MetadataItem]:
        """Return one resource collection by name, or empty list if absent."""
        collection = (self.model_extra or {}).get(name)
        if isinstance(collection, list) and all(isinstance(entry, MetadataItem) for entry in collection):
            return collection
        return []

    def has_resource(self, name: str) -> bool:
        """True when the bundle carries a non-empty collection for the named resource."""
        extras = self.model_extra or {}
        value = extras.get(name)
        return isinstance(value, list) and bool(value)

    def resource_names(self) -> list[str]:
        """Names of every resource collection present in the bundle."""
        return [key for key, value in (self.model_extra or {}).items() if isinstance(value, list)]

    def all_uids(self) -> set[str]:
        """Every top-level UID across every resource collection."""
        return {item.id for _, items in self.resources() for item in items if item.id}

    def summary(self) -> dict[str, int]:
        """Per-resource count: `{dataElements: 12, indicators: 3, ...}`."""
        return {name: len(items) for name, items in self.resources()}

    def total(self) -> int:
        """Total object count across every resource collection."""
        return sum(len(items) for _, items in self.resources())

    def to_wire(self) -> dict[str, Any]:
        """Serialise back to DHIS2's `POST /api/metadata` wire shape.

        Used by `import_metadata` to upload the bundle; `mode='json'`
        turns nested `MetadataItem`s back into plain dicts with their
        extras intact. Dict-at-HTTP-boundary — the return value is
        consumed on the very next line by `client.post_raw`.
        """
        return self.model_dump(exclude_none=True, mode="json", by_alias=True)


class MetadataCount(BaseModel):
    """Total number of instances of a metadata resource (DHIS2 pager total)."""

    model_config = ConfigDict(populate_by_name=True)

    resource: str
    total: int
