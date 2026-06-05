"""Service layer for the `metadata` plugin — thin wrapper over generated resources."""

from __future__ import annotations

import difflib
import json
import re
from collections.abc import AsyncIterator, Mapping, Sequence
from pathlib import Path
from typing import Any

from dhis2w_client.generated.v42.oas import (
    AtomicMode,
    FlushMode,
    ImportStrategy,
    MergeMode,
    PreheatIdentifier,
    PreheatMode,
)
from dhis2w_client.v42 import (
    ACCESS_READ_METADATA,
    BulkPatchResult,
    BulkSharingResult,
    Category,
    CategoryCombo,
    CategoryComboBuildResult,
    CategoryComboBuildSpec,
    CategoryOption,
    CategoryOptionCombo,
    CategoryOptionGroup,
    CategoryOptionGroupSet,
    DataElement,
    DataElementGroup,
    DataElementGroupSet,
    DataSet,
    ExpressionDescription,
    Indicator,
    IndicatorGroup,
    IndicatorGroupSet,
    JsonPatchOp,
    LegendSet,
    LegendSetSpec,
    LegendSpec,
    OrganisationUnit,
    OrganisationUnitGroup,
    OrganisationUnitGroupSet,
    OrganisationUnitLevel,
    Predictor,
    PredictorGroup,
    Program,
    ProgramIndicator,
    ProgramIndicatorGroup,
    ProgramStage,
    SearchResults,
    Section,
    SharingBuilder,
    TrackedEntityAttribute,
    TrackedEntityType,
    ValidationRule,
    ValidationRuleGroup,
    WebMessageResponse,
    build_category_combo,
)
from pydantic import BaseModel, ConfigDict, Field

from dhis2w_core.profile import Profile
from dhis2w_core.v42.client_context import open_client
from dhis2w_core.v42.plugins.metadata.models import MetadataBundle, MetadataItem

_CAMEL_RE = re.compile(r"(?<!^)(?=[A-Z])")
_STREAM_PAGE_SIZE = 500


class UnknownResourceError(LookupError):
    """Raised when a caller asks for a metadata resource not present on this instance."""


def _attr_name(resource: str) -> str:
    """Convert a DHIS2 resource name (camelCase plural) to a Resources attribute name."""
    return _CAMEL_RE.sub("_", resource).lower()


def _resource_names(resources: object) -> list[str]:
    """List the DHIS2 wire (camelCase) resource names this client exposes.

    Reads each accessor's `_path` (`/api/<wireName>`) so discovery output matches the
    camelCase names the docs and `metadata list <resource>` expect, not snake_case attrs.
    """
    names: list[str] = []
    for attr in dir(resources):
        if attr.startswith("_"):
            continue
        path = getattr(getattr(resources, attr, None), "_path", None)
        if isinstance(path, str) and path.startswith("/api/"):
            names.append(path.removeprefix("/api/"))
    return sorted(names)


async def list_resource_types(profile: Profile) -> list[str]:
    """Return every metadata resource type exposed by the instance's generated client."""
    async with open_client(profile) as client:
        return _resource_names(client.resources)


async def list_metadata(
    profile: Profile,
    resource: str,
    *,
    fields: str | None = None,
    filters: list[str] | None = None,
    root_junction: str | None = None,
    order: list[str] | None = None,
    page: int | None = None,
    page_size: int | None = None,
    paging: bool | None = None,
    translate: bool | None = None,
    locale: str | None = None,
) -> list[BaseModel]:
    """List a metadata resource (e.g. `dataElements`, `indicators`) as typed generated models.

    Returns the generated pydantic models the resource accessor parses — e.g.
    `list[DataElement]` for `dataElements`. Callers that need JSON-friendly
    dicts (MCP tools, CLI JSON output) dump at the edge via
    `model.model_dump(...)`.

    Every DHIS2 `/api/<resource>` query parameter is forwarded. `filters` and
    `order` may repeat — a list of strings becomes `?filter=a&filter=b`.
    `root_junction` is `"AND"` (default) or `"OR"`. `paging=False` returns the
    full catalog in one response; for memory-friendly streaming use
    `iter_metadata`.
    """
    # organisationUnitLevels: the convenience accessor synthesises the unnamed levels DHIS2 omits,
    # so an unfiltered list returns the COMPLETE hierarchy (matching the removed typed
    # `organisation-unit-levels list`). Filtered/paged queries fall through to the generic path.
    if _attr_name(resource) == "organisation_unit_levels" and not filters and page is None and page_size is None:
        async with open_client(profile) as client:
            ou_levels: list[BaseModel] = []
            ou_levels.extend(await client.organisation_unit_levels.list_with_gaps())
            return ou_levels
    async with open_client(profile) as client:
        accessor = _resolve_accessor(client.resources, resource)
        models: list[BaseModel] = await accessor.list(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=paging,
            translate=translate,
            locale=locale,
        )
        return models


async def count_metadata(
    profile: Profile,
    resource: str,
    *,
    filters: list[str] | None = None,
    root_junction: str | None = None,
) -> int:
    """Return the total number of matching instances of a metadata resource (DHIS2 `pager.total`).

    Issues a single paged request (`pageSize=1`, `fields=id`) and reads the
    pager total, so counting is one cheap round-trip regardless of how many
    objects exist — no need to fetch every row. `filters` narrows the count the
    same way it narrows `list_metadata`.
    """
    async with open_client(profile) as client:
        accessor = _resolve_accessor(client.resources, resource)
        raw = await accessor.list_raw(
            fields="id",
            filters=filters,
            root_junction=root_junction,
            page=1,
            page_size=1,
            paging=True,
        )
    total = raw.get("pager", {}).get("total") if isinstance(raw, dict) else None
    if not isinstance(total, int):
        raise UnknownResourceError(f"DHIS2 returned no pager total for resource {resource!r}; cannot count")
    return total


async def iter_metadata(
    profile: Profile,
    resource: str,
    *,
    fields: str | None = None,
    filters: list[str] | None = None,
    root_junction: str | None = None,
    order: list[str] | None = None,
    page_size: int = _STREAM_PAGE_SIZE,
    translate: bool | None = None,
    locale: str | None = None,
) -> AsyncIterator[BaseModel]:
    """Stream every row of a metadata resource as typed generated models, one at a time.

    Walks successive pages server-side (`page=1`, `page=2`, ...) stopping when
    a page returns fewer rows than `page_size`. `page_size` defaults to 500 —
    large enough to keep request count low, small enough not to blow memory on
    heavy fields selectors.
    """
    page = 1
    async with open_client(profile) as client:
        accessor = _resolve_accessor(client.resources, resource)
        while True:
            models = await accessor.list(
                fields=fields,
                filters=filters,
                root_junction=root_junction,
                order=order,
                page=page,
                page_size=page_size,
                paging=True,
                translate=translate,
                locale=locale,
            )
            if not models:
                return
            for model in models:
                yield model
            if len(models) < page_size:
                return
            page += 1


async def export_metadata(
    profile: Profile,
    *,
    resources: list[str] | None = None,
    fields: str | None = None,
    skip_sharing: bool = False,
    skip_translation: bool = False,
    skip_validation: bool = False,
    per_resource_filters: Mapping[str, list[str]] | None = None,
    per_resource_fields: Mapping[str, str] | None = None,
) -> MetadataBundle:
    """Download a metadata bundle from `GET /api/metadata` and return a typed `MetadataBundle`.

    `resources` limits the export to specific types (e.g. `["dataElements",
    "indicators"]`); omit for everything. `fields` is the standard DHIS2
    selector — `":owner"` (the default DHIS2 uses internally for
    cross-instance imports) preserves every field required for a faithful
    round-trip, while `:identifiable` / `:all` / a custom list give tighter
    control.

    `per_resource_filters` narrows an export to a subset of each resource,
    using DHIS2's per-resource filter wire format
    (`?dataElements:filter=name:like:ANC`). The dict key is the resource
    name (matching `resources`); the value is a list of
    `property:operator:value` filter strings — same DSL as
    `dhis2 metadata list --filter`. Repeated filters are AND'd by DHIS2.

    `per_resource_fields` per-resource-overrides the global `fields`
    selector (`?dataElements:fields=:identifiable`). Useful when one
    resource type needs a heavy `:owner` selector and another just needs
    `id,name`.

    The returned `MetadataBundle` has typed accessors (`resources()`,
    `get_resource(name)`, `all_uids()`, `summary()`, `total()`) so callers
    never see the raw dict shape.
    """
    params: dict[str, Any] = {}
    if resources:
        for name in resources:
            params[name] = "true"
    if fields is not None:
        params["fields"] = fields
    if skip_sharing:
        params["skipSharing"] = "true"
    if skip_translation:
        params["skipTranslation"] = "true"
    if skip_validation:
        params["skipValidation"] = "true"
    if per_resource_filters:
        for resource, filter_exprs in per_resource_filters.items():
            if filter_exprs:
                # httpx serialises a list-valued param as repeated query
                # params — exactly what DHIS2 expects for per-resource filters.
                params[f"{resource}:filter"] = list(filter_exprs)
    if per_resource_fields:
        for resource, selector in per_resource_fields.items():
            params[f"{resource}:fields"] = selector
    async with open_client(profile) as client:
        raw = await client.get_raw("/api/metadata", params=params)
    return MetadataBundle.from_raw(raw)


async def import_metadata(
    profile: Profile,
    bundle: MetadataBundle,
    *,
    import_strategy: ImportStrategy | str = ImportStrategy.CREATE_AND_UPDATE,
    atomic_mode: AtomicMode | str = AtomicMode.ALL,
    dry_run: bool = False,
    skip_sharing: bool = False,
    skip_translation: bool = False,
    skip_validation: bool = False,
    identifier: PreheatIdentifier | str = PreheatIdentifier.UID,
    merge_mode: MergeMode | str | None = None,
    preheat_mode: PreheatMode | str | None = None,
    flush_mode: FlushMode | str | None = None,
) -> WebMessageResponse:
    """Upload a metadata bundle via `POST /api/metadata` and return the parsed import report.

    Strategy defaults match DHIS2's own defaults: `CREATE_AND_UPDATE` (upsert),
    `ALL` (atomic — roll back every object if any fails), `identifier=UID`.
    `dry_run=True` runs validation + preheat but commits nothing — use it to
    pre-check a bundle before a real import. Returns the `WebMessageResponse`
    envelope; `.import_count()`, `.conflicts()`, and
    `.web_message`'s typed `ImportReport` body are all available on it.

    Every enum-typed argument accepts either the generated `StrEnum` member
    (e.g. `ImportStrategy.CREATE`) or the raw string — `StrEnum` members ARE
    strings, so both go on the wire identically.
    """
    params: dict[str, Any] = {
        "importStrategy": str(import_strategy),
        "atomicMode": str(atomic_mode),
        "identifier": str(identifier),
    }
    if dry_run:
        params["importMode"] = "VALIDATE"
    if skip_sharing:
        params["skipSharing"] = "true"
    if skip_translation:
        params["skipTranslation"] = "true"
    if skip_validation:
        params["skipValidation"] = "true"
    if merge_mode is not None:
        params["mergeMode"] = str(merge_mode)
    if preheat_mode is not None:
        params["preheatMode"] = str(preheat_mode)
    if flush_mode is not None:
        params["flushMode"] = str(flush_mode)
    async with open_client(profile) as client:
        return await client.post("/api/metadata", bundle.to_wire(), params=params, model=WebMessageResponse)


# Fields whose nested references are structurally expected to sit outside the
# bundle (user ownership, sharing blocks). Otherwise every filtered export
# would drown in "dangling user" / "dangling userGroupAccess" warnings. Pass
# `skip_fields=frozenset()` to `bundle_dangling_references` to check these too.
_REFERENCE_NOISE_FIELDS: frozenset[str] = frozenset(
    {
        "createdBy",
        "lastUpdatedBy",
        "user",
        "userAccesses",
        "userGroupAccesses",
        "sharing",
    }
)


class DanglingReference(BaseModel):
    """One reference-field bucket: field name + UIDs it points at that aren't in the bundle."""

    model_config = ConfigDict(frozen=True)

    field_name: str
    missing_uids: list[str] = Field(default_factory=list)

    @property
    def count(self) -> int:
        """Number of missing UIDs in this bucket."""
        return len(self.missing_uids)


class DanglingReferences(BaseModel):
    """Summary of references inside a bundle that point at UIDs not present in the bundle.

    `items` groups every missing reference by the field name where it was
    found (`categoryCombo`, `optionSet`, `legendSets`, ...) — this is
    usually enough to decide which resource type is missing from the
    export. `bundle_uid_count` is the denominator.
    """

    items: list[DanglingReference] = Field(default_factory=list)
    bundle_uid_count: int = 0
    skipped_fields: list[str] = Field(default_factory=list)

    @property
    def total_missing(self) -> int:
        """Total missing UIDs summed across every field bucket."""
        return sum(item.count for item in self.items)

    @property
    def is_clean(self) -> bool:
        """True when every reference in the bundle resolves to a UID present in the bundle."""
        return self.total_missing == 0


def bundle_dangling_references(
    bundle: MetadataBundle,
    *,
    skip_fields: frozenset[str] = _REFERENCE_NOISE_FIELDS,
) -> DanglingReferences:
    """Walk `bundle` and report references to UIDs not present in the bundle.

    A reference is any nested `{"id": "<uid>"}` dict — DHIS2's wire shape
    for object-to-object pointers. The parent field name (e.g.
    `categoryCombo`, `optionSet`) is what gets reported so the user knows
    what to add to their export.

    `skip_fields` defaults to a curated noise list (user ownership blocks,
    sharing blocks) that almost always points at UIDs outside a typical
    metadata export; pass `frozenset()` to check everything.
    """
    known_uids = bundle.all_uids()
    missing_by_field: dict[str, set[str]] = {}
    for _, items in bundle.resources():
        for item in items:
            # Typed id/name on the item aren't references — they identify the
            # item itself. Only walk the extras for nested reference shapes.
            _collect_reference_uids(item.model_extra or {}, missing_by_field, known_uids, skip_fields)

    return DanglingReferences(
        items=[
            DanglingReference(field_name=field, missing_uids=sorted(uids))
            for field, uids in sorted(missing_by_field.items())
        ],
        bundle_uid_count=len(known_uids),
        skipped_fields=sorted(skip_fields),
    )


def _collect_reference_uids(
    obj: Any,
    missing: dict[str, set[str]],
    known_uids: set[str],
    skip_fields: frozenset[str],
) -> None:
    """Recursively walk `obj`, recording `(field_name, uid)` refs that aren't in `known_uids`."""
    if not isinstance(obj, dict):
        return
    for key, value in obj.items():
        if key in skip_fields:
            continue
        if isinstance(value, dict):
            uid = value.get("id")
            if isinstance(uid, str) and uid not in known_uids:
                missing.setdefault(key, set()).add(uid)
            _collect_reference_uids(value, missing, known_uids, skip_fields)
        elif isinstance(value, list):
            for element in value:
                if isinstance(element, dict):
                    uid = element.get("id")
                    if isinstance(uid, str) and uid not in known_uids:
                        missing.setdefault(key, set()).add(uid)
                    _collect_reference_uids(element, missing, known_uids, skip_fields)


class ObjectChange(BaseModel):
    """One object affected by a metadata diff."""

    model_config = ConfigDict(frozen=True)

    id: str
    name: str | None = None
    changed_fields: list[str] = Field(default_factory=list)


class ResourceDiff(BaseModel):
    """Per-resource diff — what happens to `<resource>` when going from left → right."""

    model_config = ConfigDict(frozen=True)

    resource: str
    created: list[ObjectChange] = Field(default_factory=list)
    deleted: list[ObjectChange] = Field(default_factory=list)
    updated: list[ObjectChange] = Field(default_factory=list)
    unchanged_count: int = 0

    @property
    def total_changed(self) -> int:
        """Count of objects that differ between the two bundles (create + update + delete)."""
        return len(self.created) + len(self.deleted) + len(self.updated)


class MergeResult(BaseModel):
    """Outcome of `merge_metadata(source, target)` — both export + import halves in one model.

    Pairs the per-resource export count (how many UIDs left the source)
    with the typed `WebMessageResponse` from the target import. Callers
    can surface either side: the count summary for a "what moved?"
    headline, or the full envelope for conflict / rejected-index detail.
    """

    model_config = ConfigDict(frozen=True)

    source_base_url: str
    target_base_url: str
    resources: list[str]
    dry_run: bool
    export_counts: dict[str, int]
    import_report: WebMessageResponse


class MetadataDiff(BaseModel):
    """Structured comparison between two metadata bundles.

    `left` and `right` refer to the two bundles passed in. `created` objects
    are in `right` but not `left`; `deleted` are in `left` but not `right`;
    `updated` exist in both but differ on at least one non-ignored field.
    """

    left_label: str
    right_label: str
    resources: list[ResourceDiff] = Field(default_factory=list)
    ignored_fields: list[str] = Field(default_factory=list)

    @property
    def total_created(self) -> int:
        """Sum of created counts across every resource."""
        return sum(len(r.created) for r in self.resources)

    @property
    def total_updated(self) -> int:
        """Sum of updated counts across every resource."""
        return sum(len(r.updated) for r in self.resources)

    @property
    def total_deleted(self) -> int:
        """Sum of deleted counts across every resource."""
        return sum(len(r.deleted) for r in self.resources)

    @property
    def total_unchanged(self) -> int:
        """Sum of unchanged counts across every resource."""
        return sum(r.unchanged_count for r in self.resources)


# Metadata noise that differs across instances without being a "real" change.
# Skipped by default on field comparison so diff output stays meaningful.
_DEFAULT_IGNORED_FIELDS: frozenset[str] = frozenset(
    {
        "lastUpdated",
        "lastUpdatedBy",
        "created",
        "createdBy",
        "translations",
        "access",
        "favorites",
        "href",
    }
)


def _item_field_map(item: MetadataItem) -> dict[str, Any]:
    """Flatten typed id/name + extras into one key-indexed view for field comparison."""
    # id + name are typed on MetadataItem; everything else lives in model_extra.
    flat: dict[str, Any] = dict(item.model_extra or {})
    if item.id is not None:
        flat["id"] = item.id
    if item.name is not None:
        flat["name"] = item.name
    return flat


def _changed_fields(left_flat: Mapping[str, Any], right_flat: Mapping[str, Any], ignored: frozenset[str]) -> list[str]:
    """Return top-level field names whose values differ between the two objects."""
    keys = (set(left_flat) | set(right_flat)) - ignored
    return sorted(key for key in keys if left_flat.get(key) != right_flat.get(key))


def diff_bundles(
    left: MetadataBundle,
    right: MetadataBundle,
    *,
    left_label: str = "left",
    right_label: str = "right",
    ignored_fields: frozenset[str] = _DEFAULT_IGNORED_FIELDS,
) -> MetadataDiff:
    """Structurally compare two metadata bundles; returns a typed `MetadataDiff`.

    Bundles are the shape `dhis2 metadata export` produces. Default
    `ignored_fields` skips DHIS2's per-instance noise (`lastUpdated`,
    `createdBy`, `access`, ...) so a round-trip `export → import → export`
    diff shows zero real changes instead of every object as "updated"
    because timestamps bumped.
    """
    resources: list[ResourceDiff] = []
    # Union the resource names present in either bundle — something could be
    # entirely absent on one side.
    resource_names = sorted({*left.resource_names(), *right.resource_names()})
    for name in resource_names:
        left_items = {item.id: item for item in left.get_resource(name) if item.id}
        right_items = {item.id: item for item in right.get_resource(name) if item.id}
        created: list[ObjectChange] = []
        deleted: list[ObjectChange] = []
        updated: list[ObjectChange] = []
        unchanged = 0
        for uid in sorted(set(left_items) | set(right_items)):
            left_item = left_items.get(uid)
            right_item = right_items.get(uid)
            if left_item is None and right_item is not None:
                created.append(ObjectChange(id=uid, name=right_item.name))
            elif right_item is None and left_item is not None:
                deleted.append(ObjectChange(id=uid, name=left_item.name))
            elif left_item is not None and right_item is not None:
                changed = _changed_fields(_item_field_map(left_item), _item_field_map(right_item), ignored_fields)
                if changed:
                    updated.append(ObjectChange(id=uid, name=right_item.name, changed_fields=changed))
                else:
                    unchanged += 1
        resources.append(
            ResourceDiff(
                resource=name,
                created=created,
                deleted=deleted,
                updated=updated,
                unchanged_count=unchanged,
            )
        )
    return MetadataDiff(
        left_label=left_label,
        right_label=right_label,
        resources=resources,
        ignored_fields=sorted(ignored_fields),
    )


async def diff_bundle_against_instance(
    profile: Profile,
    bundle: MetadataBundle,
    *,
    bundle_label: str = "file",
    resources: list[str] | None = None,
    ignored_fields: frozenset[str] = _DEFAULT_IGNORED_FIELDS,
) -> MetadataDiff:
    """Export the live instance + diff it against `bundle`.

    `resources` narrows the export to specific types (defaults to every
    resource present in `bundle`, so we don't drag down the entire
    catalog just to compare one slice).
    """
    if resources is None:
        resources = bundle.resource_names()
    live_bundle = await export_metadata(profile, resources=resources or None, fields=":owner")
    return diff_bundles(
        live_bundle,
        bundle,
        left_label=f"instance:{profile.base_url}",
        right_label=bundle_label,
        ignored_fields=ignored_fields,
    )


async def diff_profiles(
    profile_a: Profile,
    profile_b: Profile,
    *,
    resources: list[str],
    left_label: str | None = None,
    right_label: str | None = None,
    fields: str = ":owner",
    per_resource_filters: Mapping[str, list[str]] | None = None,
    ignored_fields: frozenset[str] = _DEFAULT_IGNORED_FIELDS,
) -> MetadataDiff:
    """Export `resources` from two profiles in parallel and diff them structurally.

    Staging-vs-prod drift monitoring: pick a narrow resource slice + filters
    (stage and prod always differ on user accounts, timestamps, and
    incidental config — filter those out first) and compare the remainder
    structurally.

    `resources` must be explicit — there's no "diff everything" default,
    because a whole-instance diff is rarely what an operator actually
    wants (drift in e.g. `userRoles` / `organisationUnits` is usually
    expected + noise-dominated).

    `per_resource_filters` takes the same shape `export_metadata` uses:
    `{resource: [filter_expr, ...]}` with the standard DHIS2
    `property:operator:value` syntax. Every exported side gets the
    same filters so what you're comparing on each profile is apples-to-apples.

    `ignored_fields` extends the default `lastUpdated` / `createdBy` /
    `access` skip list. Pass `frozenset({*_DEFAULT_IGNORED_FIELDS, "sharing"})`
    to also ignore per-instance sharing blocks, or pass a custom frozenset
    to override entirely.

    Runs the two exports concurrently — one profile shouldn't block the
    other, and staging instances tend to be slower than prod.
    """
    if not resources:
        raise ValueError("diff_profiles requires at least one resource type")

    import asyncio as _asyncio

    bundle_a, bundle_b = await _asyncio.gather(
        export_metadata(
            profile_a,
            resources=resources,
            fields=fields,
            per_resource_filters=per_resource_filters,
        ),
        export_metadata(
            profile_b,
            resources=resources,
            fields=fields,
            per_resource_filters=per_resource_filters,
        ),
    )
    return diff_bundles(
        bundle_a,
        bundle_b,
        left_label=left_label or f"profile-a:{profile_a.base_url}",
        right_label=right_label or f"profile-b:{profile_b.base_url}",
        ignored_fields=ignored_fields,
    )


async def merge_metadata(
    source_profile: Profile,
    target_profile: Profile,
    *,
    resources: list[str],
    per_resource_filters: Mapping[str, list[str]] | None = None,
    fields: str = ":owner",
    import_strategy: ImportStrategy | str = ImportStrategy.CREATE_AND_UPDATE,
    atomic_mode: AtomicMode | str = AtomicMode.ALL,
    dry_run: bool = False,
    skip_sharing: bool = True,
    skip_translation: bool = False,
) -> MergeResult:
    """Export `resources` from `source_profile` + import into `target_profile` in one pass.

    The "bring matching resources from staging into prod" workflow that
    `diff-profiles` only reads. Pairs naturally with it: run `diff-profiles`
    first to preview what will change, then `merge` to apply.

    `resources` must be explicit — there's no "whole instance" default,
    because cross-instance whole-instance merges overwrite user / role /
    org-unit state the operator almost never actually wants synced. The
    resource list is passed both to the source export + factors into the
    import count summary.

    `per_resource_filters` applies server-side on the source export via
    the standard DHIS2 per-resource filter syntax
    (`?dataElements:filter=name:like:ANC`). Repeated filters are AND'd.
    No filtering happens on the target — the import sees exactly what
    the export emitted.

    `skip_sharing=True` by default — sharing blocks routinely differ
    between instances (different user UIDs, different groups) and
    trying to import them causes false-positive conflicts. Set False
    when you've pre-aligned users + groups and want sharing to land too.

    Returns a typed `MergeResult` with the export-side UID counts
    per resource, the import-side `WebMessageResponse` envelope, and
    the `dry_run` flag. Caller's CLI / MCP renders both halves.

    `dry_run=True` flows through as `importMode=VALIDATE` on the
    target — the import endpoint reports conflicts + stats but doesn't
    commit. Use to preview before applying.
    """
    if not resources:
        raise ValueError("merge_metadata requires at least one resource type")
    bundle = await export_metadata(
        source_profile,
        resources=resources,
        fields=fields,
        per_resource_filters=per_resource_filters,
        skip_sharing=skip_sharing,
        skip_translation=skip_translation,
    )
    import_report = await import_metadata(
        target_profile,
        bundle,
        import_strategy=import_strategy,
        atomic_mode=atomic_mode,
        dry_run=dry_run,
        skip_sharing=skip_sharing,
        skip_translation=skip_translation,
    )
    return MergeResult(
        source_base_url=source_profile.base_url,
        target_base_url=target_profile.base_url,
        resources=resources,
        dry_run=dry_run,
        export_counts={name: len(bundle.get_resource(name)) for name in resources},
        import_report=import_report,
    )


async def merge_metadata_from_bundle(
    target_profile: Profile,
    bundle_path: Path,
    *,
    resources: list[str] | None = None,
    import_strategy: ImportStrategy | str = ImportStrategy.CREATE_AND_UPDATE,
    atomic_mode: AtomicMode | str = AtomicMode.ALL,
    dry_run: bool = False,
    skip_sharing: bool = True,
    skip_translation: bool = False,
) -> MergeResult:
    """Import a metadata bundle from a local file into `target_profile`.

    Same import semantics as `merge_metadata` — atomic + sharing skipped
    by default, `dry_run=True` flips to `importMode=VALIDATE` — but the
    bundle comes from disk instead of an export against a source profile.
    Useful when the source is a saved export, a manually-crafted bundle,
    or output from a non-DHIS2 tool.

    `resources` narrows the export-count summary to a subset of the
    bundle's resource keys (matches the `--resource` filter on
    `merge_metadata`). When omitted, every resource section in the bundle
    is reported.

    `MergeResult.source_base_url` carries the bundle file path (prefixed
    with `bundle:`) so callers can tell at a glance which source
    produced the merge.
    """
    raw = json.loads(bundle_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"bundle file {bundle_path} did not parse to an object")
    bundle = MetadataBundle.from_raw(raw)
    bundle_resources = list(resources) if resources else sorted(name for name, _ in bundle.resources())
    import_report = await import_metadata(
        target_profile,
        bundle,
        import_strategy=import_strategy,
        atomic_mode=atomic_mode,
        dry_run=dry_run,
        skip_sharing=skip_sharing,
        skip_translation=skip_translation,
    )
    return MergeResult(
        source_base_url=f"bundle:{bundle_path}",
        target_base_url=target_profile.base_url,
        resources=bundle_resources,
        dry_run=dry_run,
        export_counts={name: len(bundle.get_resource(name)) for name in bundle_resources},
        import_report=import_report,
    )


async def search_metadata(
    profile: Profile,
    query: str,
    *,
    page_size: int = 50,
    resource: str | None = None,
    fields: str | None = None,
    exact: bool = False,
) -> SearchResults:
    """Cross-resource text search via `client.metadata.search`.

    Three concurrent `/api/metadata?filter=<field>:<op>:<query>` calls (one
    per match axis: `id`, `code`, `name`) merged client-side with UID
    dedup. `resource` narrows to one DHIS2 resource plural; `fields` asks
    DHIS2 for extra columns (stored on `SearchHit.extras`); `exact=True`
    switches the operator from `ilike` substring to `eq` strict match.
    """
    async with open_client(profile) as client:
        return await client.metadata.search(
            query,
            page_size=page_size,
            resource=resource,
            fields=fields,
            exact=exact,
        )


async def usage_metadata(
    profile: Profile,
    uid: str,
    *,
    page_size: int = 100,
) -> SearchResults:
    """Reverse lookup — find every object that references the given UID.

    Resolves the UID's owning resource via `/api/identifiableObjects/{uid}`,
    then fans out concurrent `/api/<target>?filter=<path>:eq:<uid>` calls
    against every known reference path for that owning type. Useful as a
    deletion-safety probe before `dhis2 metadata patch` / `delete_bulk`.
    """
    async with open_client(profile) as client:
        return await client.metadata.usage(uid, page_size=page_size)


async def get_metadata(
    profile: Profile,
    resource: str,
    uid: str,
    *,
    fields: str | None = None,
) -> BaseModel:
    """Fetch one metadata object by UID; returns the typed generated model."""
    async with open_client(profile) as client:
        accessor = _resolve_accessor(client.resources, resource)
        model: BaseModel = await accessor.get(uid, fields=fields)
        return model


async def patch_metadata(
    profile: Profile,
    resource: str,
    uid: str,
    ops: Sequence[JsonPatchOp | dict[str, Any]],
) -> WebMessageResponse:
    """Apply an RFC 6902 JSON Patch to a single metadata object.

    Wraps `PATCH /api/<resource>/{uid}`. `ops` accepts typed `JsonPatchOp`
    variants (e.g. `ReplaceOp(path="/name", value="New")`) and raw
    `{op, path, ...}` dicts interchangeably — dicts are validated through
    `JsonPatchOpAdapter` at the wire boundary.

    Returns a typed `WebMessageResponse`; read `.import_count()`,
    `.conflicts()`, `.status` as usual.
    """
    async with open_client(profile) as client:
        accessor = _resolve_accessor(client.resources, resource)
        raw = await accessor.patch(uid, ops)
    return WebMessageResponse.model_validate(raw)


def _parse_grant(raw: str, *, flag_name: str) -> tuple[str, str]:
    """Parse a `UID:access` CLI argument into `(uid, access_string)`.

    Access strings are 8-char DHIS2 patterns (`rwrw----`, `r-------`, etc.).
    """
    if ":" not in raw:
        raise ValueError(f"{flag_name} expects `UID:access`; got {raw!r}")
    uid, access = raw.split(":", 1)
    uid = uid.strip()
    access = access.strip()
    if not uid or not access:
        raise ValueError(f"{flag_name} expects non-empty UID + access; got {raw!r}")
    return uid, access


async def bulk_share_metadata(
    profile: Profile,
    resource_type: str,
    uids: Sequence[str],
    *,
    public_access: str | None = None,
    user_access: Sequence[str] | None = None,
    user_group_access: Sequence[str] | None = None,
    concurrency: int = 8,
    dry_run: bool = False,
) -> BulkShareResult:
    """Apply a single sharing block across many UIDs of one resource.

    `resource_type` is the DHIS2 singular form used by `/api/sharing?type=`
    (`dataSet`, `dataElement`, `program`, ...). `uids` is the cohort.
    `user_access` / `user_group_access` are repeatable `UID:access` strings.

    `dry_run=True` returns a preview without sending any POSTs — the
    `BulkShareResult.entries` reflect the planned grants.
    """
    builder = SharingBuilder(public_access=public_access or ACCESS_READ_METADATA)
    for raw in user_access or []:
        uid, access = _parse_grant(raw, flag_name="--user-access")
        builder = builder.grant_user(uid, access)
    for raw in user_group_access or []:
        gid, access = _parse_grant(raw, flag_name="--user-group-access")
        builder = builder.grant_user_group(gid, access)
    user_grants = list(builder.user_accesses.items())
    group_grants = list(builder.user_group_accesses.items())
    entries = [
        BulkShareEntry(
            uid=uid,
            public_access=builder.public_access,
            user_grants=[f"{u}:{a}" for u, a in user_grants],
            user_group_grants=[f"{g}:{a}" for g, a in group_grants],
        )
        for uid in uids
    ]
    if dry_run or not uids:
        return BulkShareResult(entries=entries, dry_run=dry_run)
    async with open_client(profile) as client:
        sharing_result = await client.metadata.apply_sharing_bulk(
            resource_type, list(uids), builder, concurrency=concurrency
        )
    return BulkShareResult(entries=entries, dry_run=False, sharing_result=sharing_result)


class BulkShareEntry(BaseModel):
    """One row in a `bulk_share_metadata` preview / result."""

    model_config = ConfigDict(frozen=True)

    uid: str
    public_access: str
    user_grants: list[str] = Field(default_factory=list)
    user_group_grants: list[str] = Field(default_factory=list)


class BulkShareResult(BaseModel):
    """Result of a `bulk_share_metadata` call (dry-run or applied)."""

    model_config = ConfigDict(frozen=True)

    entries: list[BulkShareEntry]
    dry_run: bool
    sharing_result: BulkSharingResult | None = None

    @property
    def matched(self) -> int:
        """How many UIDs were targeted."""
        return len(self.entries)

    @property
    def succeeded(self) -> int:
        """How many UIDs were successfully shared (0 on dry-run)."""
        return len(self.sharing_result.successful_uids) if self.sharing_result else 0

    @property
    def failed(self) -> int:
        """How many UIDs failed to apply (0 on dry-run)."""
        return len(self.sharing_result.failures) if self.sharing_result else 0


def _resolve_accessor(resources: object, resource: str) -> Any:
    """Resolve `client.resources.<attr>` for a resource name; raise UnknownResourceError on miss."""
    attr = _attr_name(resource)
    accessor = getattr(resources, attr, None)
    if accessor is None:
        available = _resource_names(resources)
        suggestions = difflib.get_close_matches(resource, available, n=3, cutoff=0.6)
        hint = f" did you mean {' or '.join(repr(s) for s in suggestions)}?" if suggestions else ""
        raise UnknownResourceError(
            f"unknown metadata resource {resource!r} (tried attribute {attr!r});{hint} "
            f"this instance exposes {len(available)} types — run `dhis2 metadata type list` to see them"
        )
    return accessor


async def resolve_option_set_uid(profile: Profile, uid_or_code: str) -> str:
    """Resolve an OptionSet identifier to its DHIS2 UID.

    Accepts either the literal 11-char DHIS2 UID or the business `code`
    the set was registered under. The `code` path hits
    `/api/optionSets?filter=code:eq:{code}` via the accessor; UID inputs
    are returned unchanged (no round-trip).

    Raises `LookupError` if the input is a code that doesn't resolve.
    """
    from dhis2w_client.v42.uids import is_valid_uid  # noqa: PLC0415 — local import keeps the main file's surface lean

    if is_valid_uid(uid_or_code):
        return uid_or_code
    async with open_client(profile) as client:
        option_set = await client.option_sets.get_by_code(uid_or_code, include_options=False)
    if option_set is None or option_set.id is None:
        raise LookupError(f"no OptionSet with code {uid_or_code!r} (and not a valid UID)")
    return option_set.id


async def show_option_set(profile: Profile, uid_or_code: str) -> Any:
    """Fetch one OptionSet (with options resolved inline) by UID or business code; None on miss."""
    from dhis2w_client.generated.v42.schemas import OptionSet  # noqa: PLC0415
    from dhis2w_client.v42.uids import is_valid_uid  # noqa: PLC0415

    async with open_client(profile) as client:
        if is_valid_uid(uid_or_code):
            raw = await client.get_raw(
                f"/api/optionSets/{uid_or_code}",
                params={
                    "fields": "id,code,name,description,valueType,version,options[id,code,name,sortOrder]",
                },
            )
            return OptionSet.model_validate(raw)
        return await client.option_sets.get_by_code(uid_or_code)


async def create_option_set(
    profile: Profile,
    *,
    name: str,
    value_type: str,
    code: str | None = None,
    uid: str | None = None,
) -> WebMessageResponse:
    """Create an OptionSet (name + valueType); returns the import-summary (new UID in response.uid)."""
    from dhis2w_client.generated.v42.schemas import OptionSet  # noqa: PLC0415

    payload: dict[str, Any] = {"name": name, "valueType": value_type}
    if code:
        payload["code"] = code
    if uid:
        payload["id"] = uid
    async with open_client(profile) as client:
        result = await client.resources.option_sets.create(OptionSet.model_validate(payload))
        return WebMessageResponse.model_validate(result)


async def delete_option_set(profile: Profile, uid: str) -> None:
    """Delete an OptionSet by UID."""
    async with open_client(profile) as client:
        await client.resources.option_sets.delete(uid)


async def find_option_in_set(
    profile: Profile,
    *,
    option_set_uid_or_code: str,
    option_code: str | None = None,
    option_name: str | None = None,
) -> Any:
    """Pinpoint a single option inside a set by code or name; None on miss."""
    async with open_client(profile) as client:
        set_uid = await resolve_option_set_uid(profile, option_set_uid_or_code)
        return await client.option_sets.find_option(
            set_uid,
            option_code=option_code,
            option_name=option_name,
        )


async def sync_option_set(
    profile: Profile,
    *,
    option_set_uid_or_code: str,
    spec: Sequence[Any],
    remove_missing: bool = False,
    dry_run: bool = False,
) -> Any:
    """Run `upsert_options` against a set identified by UID or code; return the typed report."""
    async with open_client(profile) as client:
        set_uid = await resolve_option_set_uid(profile, option_set_uid_or_code)
        return await client.option_sets.upsert_options(
            set_uid,
            spec,
            remove_missing=remove_missing,
            dry_run=dry_run,
        )


async def get_option_attribute_value(
    profile: Profile,
    *,
    option_uid: str,
    attribute_code_or_uid: str,
) -> str | None:
    """Read one attribute value off an Option; None if unset."""
    async with open_client(profile) as client:
        return await client.option_sets.get_option_attribute_value(option_uid, attribute_code_or_uid)


async def set_option_attribute_value(
    profile: Profile,
    *,
    option_uid: str,
    attribute_code_or_uid: str,
    value: str,
) -> None:
    """Set / replace one attribute value on an Option (read-merge-write)."""
    async with open_client(profile) as client:
        await client.option_sets.set_option_attribute_value(option_uid, attribute_code_or_uid, value)


async def find_option_by_attribute(
    profile: Profile,
    *,
    option_set_uid_or_code: str,
    attribute_code_or_uid: str,
    value: str,
) -> Any:
    """Reverse lookup: Option in a set whose attribute value matches."""
    async with open_client(profile) as client:
        set_uid = await resolve_option_set_uid(profile, option_set_uid_or_code)
        return await client.option_sets.find_option_by_attribute(
            set_uid,
            attribute_code_or_uid,
            value,
        )


async def get_attribute_value(
    profile: Profile,
    *,
    resource: str,
    resource_uid: str,
    attribute_code_or_uid: str,
) -> str | None:
    """Generic read — any resource with `attributeValues` (DEs, OUs, options, …)."""
    async with open_client(profile) as client:
        return await client.attribute_values.get_value(resource, resource_uid, attribute_code_or_uid)


async def set_attribute_value(
    profile: Profile,
    *,
    resource: str,
    resource_uid: str,
    attribute_code_or_uid: str,
    value: str,
) -> None:
    """Generic set — any resource with `attributeValues` (DEs, OUs, options, …)."""
    async with open_client(profile) as client:
        await client.attribute_values.set_value(resource, resource_uid, attribute_code_or_uid, value)


async def delete_attribute_value(
    profile: Profile,
    *,
    resource: str,
    resource_uid: str,
    attribute_code_or_uid: str,
) -> bool:
    """Generic delete — returns True if an attribute value was removed, False on no-op."""
    async with open_client(profile) as client:
        return await client.attribute_values.delete_value(resource, resource_uid, attribute_code_or_uid)


async def find_resources_by_attribute(
    profile: Profile,
    *,
    resource: str,
    attribute_code_or_uid: str,
    value: str,
    extra_filters: list[str] | None = None,
) -> list[str]:
    """Generic reverse lookup — UIDs of every resource whose attribute matches."""
    async with open_client(profile) as client:
        return await client.attribute_values.find_uids_by_value(
            resource,
            attribute_code_or_uid,
            value,
            extra_filters=extra_filters,
        )


async def show_program_rule(profile: Profile, rule_uid: str) -> Any:
    """Fetch one ProgramRule with actions resolved inline."""
    async with open_client(profile) as client:
        return await client.program_rules.get_rule(rule_uid)


async def list_program_rule_variables(profile: Profile, program_uid: str) -> list[Any]:
    """List every `ProgramRuleVariable` in scope for a program."""
    async with open_client(profile) as client:
        return await client.program_rules.variables_for(program_uid)


async def validate_program_rule_expression(
    profile: Profile,
    expression: str,
    *,
    context: str = "program-indicator",
) -> Any:
    """Parse-check a program-rule condition expression via DHIS2's description endpoint."""
    from typing import cast  # noqa: PLC0415

    from dhis2w_client.v42.validation import ExpressionContext  # noqa: PLC0415

    typed_context = cast(ExpressionContext, context)
    async with open_client(profile) as client:
        return await client.program_rules.validate_expression(expression, context=typed_context)


async def program_rules_using_data_element(profile: Profile, data_element_uid: str) -> list[Any]:
    """Impact analysis: every ProgramRule whose actions reference the DE."""
    async with open_client(profile) as client:
        return await client.program_rules.where_de_is_used(data_element_uid)


async def show_sql_view(profile: Profile, view_uid: str) -> Any:
    """Fetch one SqlView, including its `sqlQuery` text."""
    async with open_client(profile) as client:
        return await client.sql_views.get(view_uid)


async def execute_sql_view(
    profile: Profile,
    view_uid: str,
    *,
    variables: Mapping[str, str] | None = None,
    criteria: Mapping[str, str] | None = None,
) -> Any:
    """Execute a SqlView and return its typed `SqlViewResult`."""
    async with open_client(profile) as client:
        return await client.sql_views.execute(view_uid, variables=variables, criteria=criteria)


async def refresh_sql_view(profile: Profile, view_uid: str) -> Any:
    """Refresh a MATERIALIZED_VIEW or lazily create a VIEW's DB object."""
    async with open_client(profile) as client:
        return await client.sql_views.refresh(view_uid)


async def adhoc_sql_view(
    profile: Profile,
    name: str,
    sql: str,
    *,
    view_type: str = "QUERY",
    keep: bool = False,
    variables: Mapping[str, str] | None = None,
) -> Any:
    """Register a throwaway SqlView, execute it once, delete it on the way out."""
    async with open_client(profile) as client:
        kwargs = dict(variables) if variables else {}
        return await client.sql_views.runner.adhoc(
            name,
            sql,
            view_type=view_type,
            keep=keep,
            **kwargs,
        )


async def show_visualization(profile: Profile, viz_uid: str) -> Any:
    """Fetch one Visualization with axes + data dimensions resolved inline."""
    async with open_client(profile) as client:
        return await client.visualizations.get(viz_uid)


async def create_visualization(
    profile: Profile,
    *,
    name: str,
    viz_type: str,
    data_elements: Sequence[str],
    periods: Sequence[str],
    organisation_units: Sequence[str],
    description: str | None = None,
    uid: str | None = None,
    category_dimension: str | None = None,
    series_dimension: str | None = None,
    filter_dimension: str | None = None,
) -> Any:
    """Create a Visualization from a typed VisualizationSpec."""
    from dhis2w_client.generated.v42.enums import VisualizationType  # noqa: PLC0415
    from dhis2w_client.v42 import VisualizationSpec  # noqa: PLC0415 — local import to keep import cost low

    spec_kwargs: dict[str, Any] = {
        "name": name,
        "viz_type": VisualizationType(viz_type),
        "data_elements": list(data_elements),
        "periods": list(periods),
        "organisation_units": list(organisation_units),
        "description": description,
        "uid": uid,
    }
    if category_dimension is not None:
        spec_kwargs["category_dimension"] = category_dimension
    if series_dimension is not None:
        spec_kwargs["series_dimension"] = series_dimension
    if filter_dimension is not None:
        spec_kwargs["filter_dimension"] = filter_dimension
    spec = VisualizationSpec.model_validate(spec_kwargs)
    async with open_client(profile) as client:
        return await client.visualizations.create_from_spec(spec)


async def clone_visualization(
    profile: Profile,
    source_uid: str,
    *,
    new_name: str,
    new_uid: str | None = None,
    new_description: str | None = None,
) -> Any:
    """Duplicate a Visualization with a fresh UID + new name."""
    async with open_client(profile) as client:
        return await client.visualizations.clone(
            source_uid,
            new_name=new_name,
            new_uid=new_uid,
            new_description=new_description,
        )


async def delete_visualization(profile: Profile, viz_uid: str) -> None:
    """DELETE a Visualization by UID."""
    async with open_client(profile) as client:
        await client.visualizations.delete(viz_uid)


async def list_dashboards(profile: Profile) -> list[Any]:
    """List every Dashboard on the instance, sorted by name."""
    async with open_client(profile) as client:
        return await client.dashboards.list_all()


async def show_dashboard(profile: Profile, dashboard_uid: str) -> Any:
    """Fetch one Dashboard with every item resolved inline."""
    async with open_client(profile) as client:
        return await client.dashboards.get(dashboard_uid)


async def dashboard_add_item(
    profile: Profile,
    dashboard_uid: str,
    target_uid: str,
    *,
    kind: str = "visualization",
    x: int | None = None,
    y: int | None = None,
    width: int | None = None,
    height: int | None = None,
) -> Any:
    """Add a metadata-backed item (viz / map / event chart / …) to a dashboard."""
    from typing import cast  # noqa: PLC0415

    from dhis2w_client.v42 import DashboardSlot  # noqa: PLC0415
    from dhis2w_client.v42.dashboards import DashboardItemKind  # noqa: PLC0415

    slot: DashboardSlot | None = None
    if any(v is not None for v in (x, y, width, height)):
        slot = DashboardSlot(
            x=x if x is not None else 0,
            y=y if y is not None else 0,
            width=width if width is not None else 60,
            height=height if height is not None else 20,
        )
    async with open_client(profile) as client:
        return await client.dashboards.add_item(
            dashboard_uid,
            target_uid,
            kind=cast(DashboardItemKind, kind),
            slot=slot,
        )


async def dashboard_remove_item(profile: Profile, dashboard_uid: str, item_uid: str) -> Any:
    """Remove one dashboard item by its UID."""
    async with open_client(profile) as client:
        return await client.dashboards.remove_item(dashboard_uid, item_uid)


async def show_map(profile: Profile, map_uid: str) -> Any:
    """Fetch one Map with every mapViews layer resolved inline."""
    async with open_client(profile) as client:
        return await client.maps.get(map_uid)


async def create_map(
    profile: Profile,
    *,
    name: str,
    data_elements: Sequence[str],
    periods: Sequence[str],
    organisation_units: Sequence[str],
    organisation_unit_levels: Sequence[int],
    description: str | None = None,
    uid: str | None = None,
    longitude: float = 15.0,
    latitude: float = 0.0,
    zoom: int = 4,
    basemap: str = "openStreetMap",
    classes: int = 5,
    color_low: str = "#fef0d9",
    color_high: str = "#b30000",
) -> Any:
    """Create a single-layer thematic choropleth Map from flags."""
    from dhis2w_client.v42 import MapLayerSpec, MapSpec  # noqa: PLC0415

    spec = MapSpec(
        name=name,
        description=description,
        uid=uid,
        longitude=longitude,
        latitude=latitude,
        zoom=zoom,
        basemap=basemap,
        layers=[
            MapLayerSpec(
                layer_kind="thematic",
                data_elements=list(data_elements),
                periods=list(periods),
                organisation_units=list(organisation_units),
                organisation_unit_levels=list(organisation_unit_levels),
                classes=classes,
                color_low=color_low,
                color_high=color_high,
            ),
        ],
    )
    async with open_client(profile) as client:
        return await client.maps.create_from_spec(spec)


async def clone_map(
    profile: Profile,
    source_uid: str,
    *,
    new_name: str,
    new_uid: str | None = None,
    new_description: str | None = None,
) -> Any:
    """Duplicate a Map with a fresh UID + new name."""
    async with open_client(profile) as client:
        return await client.maps.clone(
            source_uid,
            new_name=new_name,
            new_uid=new_uid,
            new_description=new_description,
        )


async def delete_map(profile: Profile, map_uid: str) -> None:
    """DELETE a Map by UID."""
    async with open_client(profile) as client:
        await client.maps.delete(map_uid)


# ---------------------------------------------------------------------------
# DataElement workflows — `dhis2 metadata data-elements ...`
# ---------------------------------------------------------------------------


async def show_data_element(profile: Profile, uid: str) -> DataElement:
    """Fetch one DataElement by UID."""
    async with open_client(profile) as client:
        return await client.data_elements.get(uid)


async def create_data_element(
    profile: Profile,
    *,
    name: str,
    short_name: str,
    value_type: str,
    domain_type: str = "AGGREGATE",
    aggregation_type: str = "SUM",
    category_combo_uid: str | None = None,
    option_set_uid: str | None = None,
    legend_set_uids: list[str] | None = None,
    code: str | None = None,
    form_name: str | None = None,
    description: str | None = None,
    uid: str | None = None,
    zero_is_significant: bool = False,
) -> DataElement:
    """Create a DataElement."""
    async with open_client(profile) as client:
        return await client.data_elements.create(
            name=name,
            short_name=short_name,
            value_type=value_type,
            domain_type=domain_type,
            aggregation_type=aggregation_type,
            category_combo_uid=category_combo_uid,
            option_set_uid=option_set_uid,
            legend_set_uids=legend_set_uids,
            code=code,
            form_name=form_name,
            description=description,
            uid=uid,
            zero_is_significant=zero_is_significant,
        )


async def rename_data_element(
    profile: Profile,
    uid: str,
    *,
    name: str | None = None,
    short_name: str | None = None,
    form_name: str | None = None,
    description: str | None = None,
) -> DataElement:
    """Partial-update the label fields on a DataElement."""
    async with open_client(profile) as client:
        return await client.data_elements.rename(
            uid,
            name=name,
            short_name=short_name,
            form_name=form_name,
            description=description,
        )


async def set_data_element_legend_sets(
    profile: Profile,
    uid: str,
    *,
    legend_set_uids: list[str],
) -> DataElement:
    """Replace the legendSets on a DataElement."""
    async with open_client(profile) as client:
        return await client.data_elements.set_legend_sets(uid, legend_set_uids=legend_set_uids)


async def delete_data_element(profile: Profile, uid: str) -> None:
    """Delete a DataElement."""
    async with open_client(profile) as client:
        await client.data_elements.delete(uid)


# ---------------------------------------------------------------------------
# DataElementGroup — `dhis2 metadata data-element-groups ...`
# ---------------------------------------------------------------------------


async def show_data_element_group(profile: Profile, uid: str) -> DataElementGroup:
    """Fetch one group with member + group-set refs inline."""
    async with open_client(profile) as client:
        return await client.data_element_groups.get(uid)


async def list_data_element_group_members(
    profile: Profile,
    uid: str,
    *,
    page: int = 1,
    page_size: int = 50,
) -> list[DataElement]:
    """Page through DataElements inside one group."""
    async with open_client(profile) as client:
        return await client.data_element_groups.list_members(uid, page=page, page_size=page_size)


async def create_data_element_group(
    profile: Profile,
    *,
    name: str,
    short_name: str,
    uid: str | None = None,
    code: str | None = None,
    description: str | None = None,
) -> DataElementGroup:
    """Create an empty DataElementGroup."""
    async with open_client(profile) as client:
        return await client.data_element_groups.create(
            name=name,
            short_name=short_name,
            uid=uid,
            code=code,
            description=description,
        )


async def add_data_element_group_members(
    profile: Profile,
    uid: str,
    *,
    data_element_uids: list[str],
) -> DataElementGroup:
    """Add DataElements to a group."""
    async with open_client(profile) as client:
        return await client.data_element_groups.add_members(uid, data_element_uids=data_element_uids)


async def remove_data_element_group_members(
    profile: Profile,
    uid: str,
    *,
    data_element_uids: list[str],
) -> DataElementGroup:
    """Drop DataElements from a group."""
    async with open_client(profile) as client:
        return await client.data_element_groups.remove_members(uid, data_element_uids=data_element_uids)


async def delete_data_element_group(profile: Profile, uid: str) -> None:
    """Delete the grouping row."""
    async with open_client(profile) as client:
        await client.data_element_groups.delete(uid)


# ---------------------------------------------------------------------------
# DataElementGroupSet — `dhis2 metadata data-element-group-sets ...`
# ---------------------------------------------------------------------------


async def show_data_element_group_set(profile: Profile, uid: str) -> DataElementGroupSet:
    """Fetch one group set by UID."""
    async with open_client(profile) as client:
        return await client.data_element_group_sets.get(uid)


async def create_data_element_group_set(
    profile: Profile,
    *,
    name: str,
    short_name: str,
    uid: str | None = None,
    code: str | None = None,
    description: str | None = None,
    compulsory: bool = False,
    data_dimension: bool = True,
) -> DataElementGroupSet:
    """Create an empty DataElementGroupSet."""
    async with open_client(profile) as client:
        return await client.data_element_group_sets.create(
            name=name,
            short_name=short_name,
            uid=uid,
            code=code,
            description=description,
            compulsory=compulsory,
            data_dimension=data_dimension,
        )


async def add_data_element_group_set_groups(
    profile: Profile,
    uid: str,
    *,
    group_uids: list[str],
) -> DataElementGroupSet:
    """Add groups to a group set."""
    async with open_client(profile) as client:
        return await client.data_element_group_sets.add_groups(uid, group_uids=group_uids)


async def remove_data_element_group_set_groups(
    profile: Profile,
    uid: str,
    *,
    group_uids: list[str],
) -> DataElementGroupSet:
    """Drop groups from a group set."""
    async with open_client(profile) as client:
        return await client.data_element_group_sets.remove_groups(uid, group_uids=group_uids)


async def delete_data_element_group_set(profile: Profile, uid: str) -> None:
    """Delete a DataElementGroupSet."""
    async with open_client(profile) as client:
        await client.data_element_group_sets.delete(uid)


# ---------------------------------------------------------------------------
# Indicator workflows — `dhis2 metadata indicators ...`
# ---------------------------------------------------------------------------


async def show_indicator(profile: Profile, uid: str) -> Indicator:
    """Fetch one Indicator by UID."""
    async with open_client(profile) as client:
        return await client.indicators.get(uid)


async def create_indicator(
    profile: Profile,
    *,
    name: str,
    short_name: str,
    indicator_type_uid: str,
    numerator: str,
    denominator: str,
    numerator_description: str | None = None,
    denominator_description: str | None = None,
    legend_set_uids: list[str] | None = None,
    annualized: bool = False,
    decimals: int | None = None,
    code: str | None = None,
    description: str | None = None,
    uid: str | None = None,
) -> Indicator:
    """Create an Indicator from numerator + denominator expressions."""
    async with open_client(profile) as client:
        return await client.indicators.create(
            name=name,
            short_name=short_name,
            indicator_type_uid=indicator_type_uid,
            numerator=numerator,
            denominator=denominator,
            numerator_description=numerator_description,
            denominator_description=denominator_description,
            legend_set_uids=legend_set_uids,
            annualized=annualized,
            decimals=decimals,
            code=code,
            description=description,
            uid=uid,
        )


async def rename_indicator(
    profile: Profile,
    uid: str,
    *,
    name: str | None = None,
    short_name: str | None = None,
    description: str | None = None,
) -> Indicator:
    """Partial-update the label fields on an Indicator."""
    async with open_client(profile) as client:
        return await client.indicators.rename(uid, name=name, short_name=short_name, description=description)


async def validate_indicator_expression(profile: Profile, expression: str) -> ExpressionDescription:
    """Parse-check a numerator/denominator expression against DHIS2's validator."""
    async with open_client(profile) as client:
        return await client.indicators.validate_expression(expression)


async def set_indicator_legend_sets(
    profile: Profile,
    uid: str,
    *,
    legend_set_uids: list[str],
) -> Indicator:
    """Replace the legendSets on an Indicator."""
    async with open_client(profile) as client:
        return await client.indicators.set_legend_sets(uid, legend_set_uids=legend_set_uids)


async def delete_indicator(profile: Profile, uid: str) -> None:
    """Delete an Indicator."""
    async with open_client(profile) as client:
        await client.indicators.delete(uid)


# ---------------------------------------------------------------------------
# IndicatorGroup — `dhis2 metadata indicator-groups ...`
# ---------------------------------------------------------------------------


async def show_indicator_group(profile: Profile, uid: str) -> IndicatorGroup:
    """Fetch one group with member + group-set refs."""
    async with open_client(profile) as client:
        return await client.indicator_groups.get(uid)


async def list_indicator_group_members(
    profile: Profile,
    uid: str,
    *,
    page: int = 1,
    page_size: int = 50,
) -> list[Indicator]:
    """Page through Indicators inside one group."""
    async with open_client(profile) as client:
        return await client.indicator_groups.list_members(uid, page=page, page_size=page_size)


async def create_indicator_group(
    profile: Profile,
    *,
    name: str,
    short_name: str,
    uid: str | None = None,
    code: str | None = None,
    description: str | None = None,
) -> IndicatorGroup:
    """Create an empty IndicatorGroup."""
    async with open_client(profile) as client:
        return await client.indicator_groups.create(
            name=name,
            short_name=short_name,
            uid=uid,
            code=code,
            description=description,
        )


async def add_indicator_group_members(
    profile: Profile,
    uid: str,
    *,
    indicator_uids: list[str],
) -> IndicatorGroup:
    """Add Indicators to a group."""
    async with open_client(profile) as client:
        return await client.indicator_groups.add_members(uid, indicator_uids=indicator_uids)


async def remove_indicator_group_members(
    profile: Profile,
    uid: str,
    *,
    indicator_uids: list[str],
) -> IndicatorGroup:
    """Drop Indicators from a group."""
    async with open_client(profile) as client:
        return await client.indicator_groups.remove_members(uid, indicator_uids=indicator_uids)


async def delete_indicator_group(profile: Profile, uid: str) -> None:
    """Delete an IndicatorGroup — members stay."""
    async with open_client(profile) as client:
        await client.indicator_groups.delete(uid)


# ---------------------------------------------------------------------------
# IndicatorGroupSet — `dhis2 metadata indicator-group-sets ...`
# ---------------------------------------------------------------------------


async def show_indicator_group_set(profile: Profile, uid: str) -> IndicatorGroupSet:
    """Fetch one group set by UID."""
    async with open_client(profile) as client:
        return await client.indicator_group_sets.get(uid)


async def create_indicator_group_set(
    profile: Profile,
    *,
    name: str,
    short_name: str,
    uid: str | None = None,
    code: str | None = None,
    description: str | None = None,
    compulsory: bool = False,
) -> IndicatorGroupSet:
    """Create an empty IndicatorGroupSet."""
    async with open_client(profile) as client:
        return await client.indicator_group_sets.create(
            name=name,
            short_name=short_name,
            uid=uid,
            code=code,
            description=description,
            compulsory=compulsory,
        )


async def add_indicator_group_set_groups(
    profile: Profile,
    uid: str,
    *,
    group_uids: list[str],
) -> IndicatorGroupSet:
    """Add groups to a group set."""
    async with open_client(profile) as client:
        return await client.indicator_group_sets.add_groups(uid, group_uids=group_uids)


async def remove_indicator_group_set_groups(
    profile: Profile,
    uid: str,
    *,
    group_uids: list[str],
) -> IndicatorGroupSet:
    """Drop groups from a group set."""
    async with open_client(profile) as client:
        return await client.indicator_group_sets.remove_groups(uid, group_uids=group_uids)


async def delete_indicator_group_set(profile: Profile, uid: str) -> None:
    """Delete an IndicatorGroupSet — member groups stay."""
    async with open_client(profile) as client:
        await client.indicator_group_sets.delete(uid)


# ---------------------------------------------------------------------------
# OrganisationUnit hierarchy — `dhis2 metadata organisation-units ...`
# ---------------------------------------------------------------------------


async def show_organisation_unit(profile: Profile, uid: str) -> OrganisationUnit:
    """Fetch one OU by UID."""
    async with open_client(profile) as client:
        return await client.organisation_units.get(uid)


async def tree_organisation_units(
    profile: Profile,
    *,
    root_uid: str,
    max_depth: int = 3,
) -> list[OrganisationUnit]:
    """Walk a subtree rooted at `root_uid` at bounded depth (breadth-first)."""
    async with open_client(profile) as client:
        return await client.organisation_units.list_descendants(root_uid, max_depth=max_depth)


async def create_organisation_unit(
    profile: Profile,
    *,
    parent_uid: str,
    name: str,
    short_name: str,
    opening_date: str,
    uid: str | None = None,
    code: str | None = None,
    description: str | None = None,
) -> OrganisationUnit:
    """Create a child OU under `parent_uid`."""
    async with open_client(profile) as client:
        return await client.organisation_units.create_under(
            parent_uid,
            name=name,
            short_name=short_name,
            opening_date=opening_date,
            uid=uid,
            code=code,
            description=description,
        )


async def move_organisation_unit(
    profile: Profile,
    *,
    uid: str,
    new_parent_uid: str,
) -> OrganisationUnit:
    """Reparent an OU. DHIS2 recomputes `path` + `hierarchyLevel` server-side."""
    async with open_client(profile) as client:
        return await client.organisation_units.move(uid, new_parent_uid)


async def delete_organisation_unit(profile: Profile, uid: str) -> None:
    """Delete an OU — DHIS2 rejects deletes on units with children or data."""
    async with open_client(profile) as client:
        await client.organisation_units.delete(uid)


# ---------------------------------------------------------------------------
# OrganisationUnitGroup — `dhis2 metadata organisation-unit-groups ...`
# ---------------------------------------------------------------------------


async def show_organisation_unit_group(profile: Profile, uid: str) -> OrganisationUnitGroup:
    """Fetch one OrganisationUnitGroup with member + group-set refs inline."""
    async with open_client(profile) as client:
        return await client.organisation_unit_groups.get(uid)


async def list_organisation_unit_group_members(
    profile: Profile,
    uid: str,
    *,
    page: int = 1,
    page_size: int = 50,
) -> list[OrganisationUnit]:
    """Page through OUs that belong to one group."""
    async with open_client(profile) as client:
        return await client.organisation_unit_groups.list_members(uid, page=page, page_size=page_size)


async def create_organisation_unit_group(
    profile: Profile,
    *,
    name: str,
    short_name: str,
    uid: str | None = None,
    code: str | None = None,
    description: str | None = None,
    color: str | None = None,
) -> OrganisationUnitGroup:
    """Create an empty OrganisationUnitGroup."""
    async with open_client(profile) as client:
        return await client.organisation_unit_groups.create(
            name=name,
            short_name=short_name,
            uid=uid,
            code=code,
            description=description,
            color=color,
        )


async def add_organisation_unit_group_members(
    profile: Profile,
    uid: str,
    *,
    ou_uids: list[str],
) -> OrganisationUnitGroup:
    """Add OUs to a group."""
    async with open_client(profile) as client:
        return await client.organisation_unit_groups.add_members(uid, ou_uids=ou_uids)


async def remove_organisation_unit_group_members(
    profile: Profile,
    uid: str,
    *,
    ou_uids: list[str],
) -> OrganisationUnitGroup:
    """Drop OUs from a group."""
    async with open_client(profile) as client:
        return await client.organisation_unit_groups.remove_members(uid, ou_uids=ou_uids)


async def delete_organisation_unit_group(profile: Profile, uid: str) -> None:
    """Delete an OrganisationUnitGroup — members stay, only the grouping row is removed."""
    async with open_client(profile) as client:
        await client.organisation_unit_groups.delete(uid)


# ---------------------------------------------------------------------------
# OrganisationUnitGroupSet — `dhis2 metadata organisation-unit-group-sets ...`
# ---------------------------------------------------------------------------


async def show_organisation_unit_group_set(
    profile: Profile,
    uid: str,
) -> tuple[OrganisationUnitGroupSet, dict[str, int]]:
    """Fetch a group set + per-child-group member counts.

    One trip for the set itself + one `organisationUnits~size` call per
    referenced group. Gives the reporting-friendly "how many OUs in
    each slice?" view without hitting analytics.
    """
    async with open_client(profile) as client:
        group_set = await client.organisation_unit_group_sets.get(uid)
        counts: dict[str, int] = {}
        for group in group_set.organisationUnitGroups or []:
            if not isinstance(group, dict):
                continue
            gid = group.get("id")
            if not isinstance(gid, str):
                continue
            raw = await client.get_raw(
                f"/api/organisationUnitGroups/{gid}",
                params={"fields": "id,organisationUnits~size"},
            )
            size_raw = raw.get("organisationUnits")
            try:
                counts[gid] = int(size_raw) if isinstance(size_raw, int | str) else 0
            except (TypeError, ValueError):
                counts[gid] = 0
    return group_set, counts


async def create_organisation_unit_group_set(
    profile: Profile,
    *,
    name: str,
    short_name: str,
    uid: str | None = None,
    code: str | None = None,
    description: str | None = None,
    compulsory: bool = False,
    data_dimension: bool = True,
) -> OrganisationUnitGroupSet:
    """Create an empty OrganisationUnitGroupSet."""
    async with open_client(profile) as client:
        return await client.organisation_unit_group_sets.create(
            name=name,
            short_name=short_name,
            uid=uid,
            code=code,
            description=description,
            compulsory=compulsory,
            data_dimension=data_dimension,
        )


async def add_organisation_unit_group_set_groups(
    profile: Profile,
    uid: str,
    *,
    group_uids: list[str],
) -> OrganisationUnitGroupSet:
    """Add groups to a group set."""
    async with open_client(profile) as client:
        return await client.organisation_unit_group_sets.add_groups(uid, group_uids=group_uids)


async def remove_organisation_unit_group_set_groups(
    profile: Profile,
    uid: str,
    *,
    group_uids: list[str],
) -> OrganisationUnitGroupSet:
    """Drop groups from a group set."""
    async with open_client(profile) as client:
        return await client.organisation_unit_group_sets.remove_groups(uid, group_uids=group_uids)


async def delete_organisation_unit_group_set(profile: Profile, uid: str) -> None:
    """Delete an OrganisationUnitGroupSet — groups stay."""
    async with open_client(profile) as client:
        await client.organisation_unit_group_sets.delete(uid)


# ---------------------------------------------------------------------------
# OrganisationUnitLevel naming — `dhis2 metadata organisation-unit-levels ...`
# ---------------------------------------------------------------------------


async def show_organisation_unit_level(profile: Profile, uid: str) -> OrganisationUnitLevel | None:
    """Fetch one level row by UID."""
    async with open_client(profile) as client:
        return await client.organisation_unit_levels.get(uid)


async def show_organisation_unit_level_by_level(
    profile: Profile,
    level: int,
) -> OrganisationUnitLevel | None:
    """Fetch one level row by numeric depth (1 = roots)."""
    async with open_client(profile) as client:
        return await client.organisation_unit_levels.get_by_level(level)


async def rename_organisation_unit_level(
    profile: Profile,
    uid: str,
    *,
    name: str,
    code: str | None = None,
    offline_levels: int | None = None,
) -> OrganisationUnitLevel:
    """Rename a level row by UID."""
    async with open_client(profile) as client:
        return await client.organisation_unit_levels.rename(
            uid,
            name=name,
            code=code,
            offline_levels=offline_levels,
        )


async def rename_organisation_unit_level_by_level(
    profile: Profile,
    level: int,
    *,
    name: str,
    code: str | None = None,
    offline_levels: int | None = None,
) -> OrganisationUnitLevel:
    """Rename the level row at numeric depth `level`."""
    async with open_client(profile) as client:
        return await client.organisation_unit_levels.rename_by_level(
            level,
            name=name,
            code=code,
            offline_levels=offline_levels,
        )


# ---------------------------------------------------------------------------
# LegendSet authoring — `dhis2 metadata legend-sets ...`
# ---------------------------------------------------------------------------


async def show_legend_set(profile: Profile, uid: str) -> LegendSet:
    """Fetch one LegendSet by UID with the child `legends` list populated."""
    async with open_client(profile) as client:
        return await client.legend_sets.get(uid)


async def create_legend_set(
    profile: Profile,
    *,
    name: str,
    legends: list[tuple[float, float, str, str | None]],
    uid: str | None = None,
    code: str | None = None,
) -> LegendSet:
    """Build a LegendSet from typed legends and POST it through `/api/metadata`.

    `legends` is a list of `(start, end, color, name)` tuples. `start`
    must be strictly less than `end`; `color` is a `#RRGGBB` or
    `#RRGGBBAA` hex string; `name` is optional (auto-generated from the
    numeric range when omitted). Returns the freshly-fetched LegendSet
    with DHIS2's computed fields populated.
    """
    spec = LegendSetSpec(
        uid=uid,
        name=name,
        code=code,
        legends=[
            LegendSpec(start=start, end=end, color=color, name=legend_name)
            for start, end, color, legend_name in legends
        ],
    )
    async with open_client(profile) as client:
        return await client.legend_sets.create_from_spec(spec)


async def clone_legend_set(
    profile: Profile,
    source_uid: str,
    *,
    new_uid: str | None = None,
    new_name: str | None = None,
    new_code: str | None = None,
) -> LegendSet:
    """Duplicate an existing LegendSet with the same bands + fresh UIDs."""
    async with open_client(profile) as client:
        return await client.legend_sets.clone(
            source_uid,
            new_uid=new_uid,
            new_name=new_name,
            new_code=new_code,
        )


async def delete_legend_set(profile: Profile, uid: str) -> None:
    """Delete a LegendSet — `DELETE /api/legendSets/{uid}`."""
    async with open_client(profile) as client:
        await client.legend_sets.delete(uid)


# ---------------------------------------------------------------------------
# ProgramIndicator workflows — `dhis2 metadata program-indicators ...`
# ---------------------------------------------------------------------------


async def show_program_indicator(profile: Profile, uid: str) -> ProgramIndicator:
    """Fetch one ProgramIndicator by UID."""
    async with open_client(profile) as client:
        return await client.program_indicators.get(uid)


async def create_program_indicator(
    profile: Profile,
    *,
    name: str,
    short_name: str,
    program_uid: str,
    expression: str,
    analytics_type: str = "EVENT",
    filter_expression: str | None = None,
    description: str | None = None,
    aggregation_type: str | None = None,
    decimals: int | None = None,
    legend_set_uids: list[str] | None = None,
    code: str | None = None,
    uid: str | None = None,
) -> ProgramIndicator:
    """Create a ProgramIndicator for a given program."""
    async with open_client(profile) as client:
        return await client.program_indicators.create(
            name=name,
            short_name=short_name,
            program_uid=program_uid,
            expression=expression,
            analytics_type=analytics_type,
            filter_expression=filter_expression,
            description=description,
            aggregation_type=aggregation_type,
            decimals=decimals,
            legend_set_uids=legend_set_uids,
            code=code,
            uid=uid,
        )


async def rename_program_indicator(
    profile: Profile,
    uid: str,
    *,
    name: str | None = None,
    short_name: str | None = None,
    description: str | None = None,
) -> ProgramIndicator:
    """Partial-update the label fields on a ProgramIndicator."""
    async with open_client(profile) as client:
        return await client.program_indicators.rename(uid, name=name, short_name=short_name, description=description)


async def validate_program_indicator_expression(profile: Profile, expression: str) -> ExpressionDescription:
    """Parse-check a program-indicator expression via DHIS2's validator."""
    async with open_client(profile) as client:
        return await client.program_indicators.validate_expression(expression)


async def set_program_indicator_legend_sets(
    profile: Profile,
    uid: str,
    *,
    legend_set_uids: list[str],
) -> ProgramIndicator:
    """Replace the legendSets on a ProgramIndicator."""
    async with open_client(profile) as client:
        return await client.program_indicators.set_legend_sets(uid, legend_set_uids=legend_set_uids)


async def delete_program_indicator(profile: Profile, uid: str) -> None:
    """Delete a ProgramIndicator."""
    async with open_client(profile) as client:
        await client.program_indicators.delete(uid)


# ---------------------------------------------------------------------------
# ProgramIndicatorGroup — `dhis2 metadata program-indicator-groups ...`
# ---------------------------------------------------------------------------


async def show_program_indicator_group(profile: Profile, uid: str) -> ProgramIndicatorGroup:
    """Fetch one group with member refs inline."""
    async with open_client(profile) as client:
        return await client.program_indicator_groups.get(uid)


async def list_program_indicator_group_members(
    profile: Profile,
    uid: str,
    *,
    page: int = 1,
    page_size: int = 50,
) -> list[ProgramIndicator]:
    """Page through ProgramIndicators inside one group."""
    async with open_client(profile) as client:
        return await client.program_indicator_groups.list_members(uid, page=page, page_size=page_size)


async def create_program_indicator_group(
    profile: Profile,
    *,
    name: str,
    short_name: str,
    uid: str | None = None,
    code: str | None = None,
    description: str | None = None,
) -> ProgramIndicatorGroup:
    """Create an empty ProgramIndicatorGroup."""
    async with open_client(profile) as client:
        return await client.program_indicator_groups.create(
            name=name,
            short_name=short_name,
            uid=uid,
            code=code,
            description=description,
        )


async def add_program_indicator_group_members(
    profile: Profile,
    uid: str,
    *,
    program_indicator_uids: list[str],
) -> ProgramIndicatorGroup:
    """Add ProgramIndicators to a group."""
    async with open_client(profile) as client:
        return await client.program_indicator_groups.add_members(uid, program_indicator_uids=program_indicator_uids)


async def remove_program_indicator_group_members(
    profile: Profile,
    uid: str,
    *,
    program_indicator_uids: list[str],
) -> ProgramIndicatorGroup:
    """Drop ProgramIndicators from a group."""
    async with open_client(profile) as client:
        return await client.program_indicator_groups.remove_members(uid, program_indicator_uids=program_indicator_uids)


async def delete_program_indicator_group(profile: Profile, uid: str) -> None:
    """Delete a ProgramIndicatorGroup — members stay."""
    async with open_client(profile) as client:
        await client.program_indicator_groups.delete(uid)


# ---------------------------------------------------------------------------
# CategoryOption workflows — `dhis2 metadata category-options ...`
# ---------------------------------------------------------------------------


async def show_category_option(profile: Profile, uid: str) -> CategoryOption:
    """Fetch one CategoryOption by UID."""
    async with open_client(profile) as client:
        return await client.category_options.get(uid)


async def create_category_option(
    profile: Profile,
    *,
    name: str,
    short_name: str,
    code: str | None = None,
    description: str | None = None,
    form_name: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    uid: str | None = None,
) -> CategoryOption:
    """Create a CategoryOption."""
    async with open_client(profile) as client:
        return await client.category_options.create(
            name=name,
            short_name=short_name,
            code=code,
            description=description,
            form_name=form_name,
            start_date=start_date,
            end_date=end_date,
            uid=uid,
        )


async def rename_category_option(
    profile: Profile,
    uid: str,
    *,
    name: str | None = None,
    short_name: str | None = None,
    form_name: str | None = None,
    description: str | None = None,
) -> CategoryOption:
    """Partial-update the label fields on a CategoryOption."""
    async with open_client(profile) as client:
        return await client.category_options.rename(
            uid,
            name=name,
            short_name=short_name,
            form_name=form_name,
            description=description,
        )


async def set_category_option_validity(
    profile: Profile,
    uid: str,
    *,
    start_date: str | None,
    end_date: str | None,
) -> CategoryOption:
    """Set or clear the start/end date validity window on a CategoryOption."""
    async with open_client(profile) as client:
        return await client.category_options.set_validity_window(uid, start_date=start_date, end_date=end_date)


async def delete_category_option(profile: Profile, uid: str) -> None:
    """Delete a CategoryOption."""
    async with open_client(profile) as client:
        await client.category_options.delete(uid)


# ---------------------------------------------------------------------------
# Category workflows — `dhis2 metadata categories ...`
# ---------------------------------------------------------------------------


async def show_category(profile: Profile, uid: str) -> Category:
    """Fetch one Category by UID."""
    async with open_client(profile) as client:
        return await client.categories.get(uid)


async def create_category(
    profile: Profile,
    *,
    name: str,
    short_name: str,
    code: str | None = None,
    description: str | None = None,
    data_dimension_type: str = "DISAGGREGATION",
    options: list[str] | None = None,
    uid: str | None = None,
) -> Category:
    """Create a Category, optionally wiring CategoryOption members on create."""
    async with open_client(profile) as client:
        return await client.categories.create(
            name=name,
            short_name=short_name,
            code=code,
            description=description,
            data_dimension_type=data_dimension_type,
            options=options,
            uid=uid,
        )


async def rename_category(
    profile: Profile,
    uid: str,
    *,
    name: str | None = None,
    short_name: str | None = None,
    description: str | None = None,
) -> Category:
    """Partial-update the label fields on a Category."""
    async with open_client(profile) as client:
        return await client.categories.rename(
            uid,
            name=name,
            short_name=short_name,
            description=description,
        )


async def add_category_option(profile: Profile, uid: str, option_uid: str) -> None:
    """Append a CategoryOption to this Category's ordered membership."""
    async with open_client(profile) as client:
        await client.categories.add_option(uid, option_uid)


async def remove_category_option(profile: Profile, uid: str, option_uid: str) -> None:
    """Remove a CategoryOption from this Category's membership."""
    async with open_client(profile) as client:
        await client.categories.remove_option(uid, option_uid)


async def delete_category(profile: Profile, uid: str) -> None:
    """Delete a Category."""
    async with open_client(profile) as client:
        await client.categories.delete(uid)


# ---------------------------------------------------------------------------
# CategoryCombo workflows — `dhis2 metadata category-combos ...`
# ---------------------------------------------------------------------------


async def show_category_combo(profile: Profile, uid: str) -> CategoryCombo:
    """Fetch one CategoryCombo by UID."""
    async with open_client(profile) as client:
        return await client.category_combos.get(uid)


async def create_category_combo(
    profile: Profile,
    *,
    name: str,
    categories: list[str],
    code: str | None = None,
    data_dimension_type: str = "DISAGGREGATION",
    skip_total: bool = False,
    uid: str | None = None,
) -> CategoryCombo:
    """Create a CategoryCombo with an ordered list of Category UIDs."""
    async with open_client(profile) as client:
        return await client.category_combos.create(
            name=name,
            categories=categories,
            code=code,
            data_dimension_type=data_dimension_type,
            skip_total=skip_total,
            uid=uid,
        )


async def rename_category_combo(
    profile: Profile,
    uid: str,
    *,
    name: str | None = None,
    code: str | None = None,
) -> CategoryCombo:
    """Partial-update label fields on a CategoryCombo."""
    async with open_client(profile) as client:
        return await client.category_combos.rename(uid, name=name, code=code)


async def add_category_to_combo(profile: Profile, uid: str, category_uid: str) -> None:
    """Append a Category to this CategoryCombo's ordered membership."""
    async with open_client(profile) as client:
        await client.category_combos.add_category(uid, category_uid)


async def remove_category_from_combo(profile: Profile, uid: str, category_uid: str) -> None:
    """Remove a Category from this CategoryCombo's membership."""
    async with open_client(profile) as client:
        await client.category_combos.remove_category(uid, category_uid)


async def wait_for_coc_generation(
    profile: Profile,
    uid: str,
    *,
    expected_count: int,
    timeout_seconds: float = 60.0,
    poll_interval_seconds: float = 1.0,
) -> int:
    """Block until the CategoryOptionCombo matrix reaches `expected_count`."""
    async with open_client(profile) as client:
        return await client.category_combos.wait_for_coc_generation(
            uid,
            expected_count=expected_count,
            timeout_seconds=timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
        )


async def delete_category_combo(profile: Profile, uid: str) -> None:
    """Delete a CategoryCombo — DHIS2 rejects the default + combos in use."""
    async with open_client(profile) as client:
        await client.category_combos.delete(uid)


async def build_category_combo_spec(
    profile: Profile,
    spec: CategoryComboBuildSpec,
    *,
    timeout_seconds: float = 120.0,
    poll_interval_seconds: float = 1.0,
) -> CategoryComboBuildResult:
    """Ensure a CategoryComboBuildSpec exists end-to-end on the target instance.

    Walks the spec, creating only what's missing across CategoryOption /
    Category / CategoryCombo (idempotent — re-running is a no-op modulo
    new options getting wired into existing categories). Polls the
    CategoryOptionCombo matrix until the cross-product count lands.
    """
    async with open_client(profile) as client:
        return await build_category_combo(
            client, spec, timeout_seconds=timeout_seconds, poll_interval_seconds=poll_interval_seconds
        )


# ---------------------------------------------------------------------------
# CategoryOptionCombo workflows — `dhis2 metadata category-option-combos ...`
# ---------------------------------------------------------------------------


async def show_category_option_combo(profile: Profile, uid: str) -> CategoryOptionCombo:
    """Fetch one CategoryOptionCombo by UID."""
    async with open_client(profile) as client:
        return await client.category_option_combos.get(uid)


async def list_category_option_combos_for_combo(profile: Profile, combo_uid: str) -> list[CategoryOptionCombo]:
    """List every CategoryOptionCombo materialised by one CategoryCombo."""
    async with open_client(profile) as client:
        return await client.category_option_combos.list_for_combo(combo_uid)


# ---------------------------------------------------------------------------
# CategoryOptionGroup — `dhis2 metadata category-option-groups ...`
# ---------------------------------------------------------------------------


async def show_category_option_group(profile: Profile, uid: str) -> CategoryOptionGroup:
    """Fetch one group with member + group-set refs."""
    async with open_client(profile) as client:
        return await client.category_option_groups.get(uid)


async def list_category_option_group_members(
    profile: Profile,
    uid: str,
    *,
    page: int = 1,
    page_size: int = 50,
) -> list[CategoryOption]:
    """Page through CategoryOptions inside one group."""
    async with open_client(profile) as client:
        return await client.category_option_groups.list_members(uid, page=page, page_size=page_size)


async def create_category_option_group(
    profile: Profile,
    *,
    name: str,
    short_name: str,
    data_dimension_type: str = "DISAGGREGATION",
    uid: str | None = None,
    code: str | None = None,
    description: str | None = None,
) -> CategoryOptionGroup:
    """Create an empty CategoryOptionGroup."""
    async with open_client(profile) as client:
        return await client.category_option_groups.create(
            name=name,
            short_name=short_name,
            data_dimension_type=data_dimension_type,
            uid=uid,
            code=code,
            description=description,
        )


async def add_category_option_group_members(
    profile: Profile,
    uid: str,
    *,
    category_option_uids: list[str],
) -> CategoryOptionGroup:
    """Add CategoryOptions to a group."""
    async with open_client(profile) as client:
        return await client.category_option_groups.add_members(uid, category_option_uids=category_option_uids)


async def remove_category_option_group_members(
    profile: Profile,
    uid: str,
    *,
    category_option_uids: list[str],
) -> CategoryOptionGroup:
    """Drop CategoryOptions from a group."""
    async with open_client(profile) as client:
        return await client.category_option_groups.remove_members(uid, category_option_uids=category_option_uids)


async def delete_category_option_group(profile: Profile, uid: str) -> None:
    """Delete a CategoryOptionGroup — members stay."""
    async with open_client(profile) as client:
        await client.category_option_groups.delete(uid)


# ---------------------------------------------------------------------------
# CategoryOptionGroupSet — `dhis2 metadata category-option-group-sets ...`
# ---------------------------------------------------------------------------


async def show_category_option_group_set(profile: Profile, uid: str) -> CategoryOptionGroupSet:
    """Fetch one group set by UID."""
    async with open_client(profile) as client:
        return await client.category_option_group_sets.get(uid)


async def create_category_option_group_set(
    profile: Profile,
    *,
    name: str,
    short_name: str,
    data_dimension_type: str = "DISAGGREGATION",
    data_dimension: bool = True,
    uid: str | None = None,
    code: str | None = None,
    description: str | None = None,
) -> CategoryOptionGroupSet:
    """Create an empty CategoryOptionGroupSet."""
    async with open_client(profile) as client:
        return await client.category_option_group_sets.create(
            name=name,
            short_name=short_name,
            data_dimension_type=data_dimension_type,
            data_dimension=data_dimension,
            uid=uid,
            code=code,
            description=description,
        )


async def add_category_option_group_set_groups(
    profile: Profile,
    uid: str,
    *,
    group_uids: list[str],
) -> CategoryOptionGroupSet:
    """Add groups to a group set."""
    async with open_client(profile) as client:
        return await client.category_option_group_sets.add_groups(uid, group_uids=group_uids)


async def remove_category_option_group_set_groups(
    profile: Profile,
    uid: str,
    *,
    group_uids: list[str],
) -> CategoryOptionGroupSet:
    """Drop groups from a group set."""
    async with open_client(profile) as client:
        return await client.category_option_group_sets.remove_groups(uid, group_uids=group_uids)


async def delete_category_option_group_set(profile: Profile, uid: str) -> None:
    """Delete a CategoryOptionGroupSet — member groups stay."""
    async with open_client(profile) as client:
        await client.category_option_group_sets.delete(uid)


# ---------------------------------------------------------------------------
# DataSet — `dhis2 metadata data-sets ...`
# ---------------------------------------------------------------------------


async def show_data_set(profile: Profile, uid: str) -> DataSet:
    """Fetch one DataSet with its DSE + section + OU refs resolved."""
    async with open_client(profile) as client:
        return await client.data_sets.get(uid)


async def create_data_set(
    profile: Profile,
    *,
    name: str,
    short_name: str,
    period_type: str,
    category_combo_uid: str | None = None,
    code: str | None = None,
    form_name: str | None = None,
    description: str | None = None,
    open_future_periods: int | None = None,
    expiry_days: int | None = None,
    timely_days: int | None = None,
    uid: str | None = None,
) -> DataSet:
    """Create a DataSet."""
    async with open_client(profile) as client:
        return await client.data_sets.create(
            name=name,
            short_name=short_name,
            period_type=period_type,
            category_combo_uid=category_combo_uid,
            code=code,
            form_name=form_name,
            description=description,
            open_future_periods=open_future_periods,
            expiry_days=expiry_days,
            timely_days=timely_days,
            uid=uid,
        )


async def rename_data_set(
    profile: Profile,
    uid: str,
    *,
    name: str | None = None,
    short_name: str | None = None,
    form_name: str | None = None,
    description: str | None = None,
) -> DataSet:
    """Partial-update the label fields on a DataSet."""
    async with open_client(profile) as client:
        return await client.data_sets.rename(
            uid,
            name=name,
            short_name=short_name,
            form_name=form_name,
            description=description,
        )


async def add_data_set_element(
    profile: Profile,
    data_set_uid: str,
    data_element_uid: str,
    *,
    category_combo_uid: str | None = None,
) -> DataSet:
    """Append a DataElement to the DataSet, with optional CC override."""
    async with open_client(profile) as client:
        return await client.data_sets.add_element(
            data_set_uid,
            data_element_uid,
            category_combo_uid=category_combo_uid,
        )


async def remove_data_set_element(
    profile: Profile,
    data_set_uid: str,
    data_element_uid: str,
) -> DataSet:
    """Remove a DataElement from the DataSet."""
    async with open_client(profile) as client:
        return await client.data_sets.remove_element(data_set_uid, data_element_uid)


async def delete_data_set(profile: Profile, uid: str) -> None:
    """Delete a DataSet — DHIS2 rejects deletes on DataSets with saved values."""
    async with open_client(profile) as client:
        await client.data_sets.delete(uid)


# ---------------------------------------------------------------------------
# Section — `dhis2 metadata sections ...`
# ---------------------------------------------------------------------------


async def show_section(profile: Profile, uid: str) -> Section:
    """Fetch one Section with its DE + indicator refs resolved."""
    async with open_client(profile) as client:
        return await client.sections.get(uid)


async def create_section(
    profile: Profile,
    *,
    name: str,
    data_set_uid: str,
    sort_order: int | None = None,
    description: str | None = None,
    code: str | None = None,
    data_element_uids: list[str] | None = None,
    indicator_uids: list[str] | None = None,
    show_column_totals: bool | None = None,
    show_row_totals: bool | None = None,
    uid: str | None = None,
) -> Section:
    """Create a Section attached to `data_set_uid`."""
    async with open_client(profile) as client:
        return await client.sections.create(
            name=name,
            data_set_uid=data_set_uid,
            sort_order=sort_order,
            description=description,
            code=code,
            data_element_uids=data_element_uids,
            indicator_uids=indicator_uids,
            show_column_totals=show_column_totals,
            show_row_totals=show_row_totals,
            uid=uid,
        )


async def rename_section(
    profile: Profile,
    uid: str,
    *,
    name: str | None = None,
    description: str | None = None,
    sort_order: int | None = None,
) -> Section:
    """Partial-update the label / order fields on a Section."""
    async with open_client(profile) as client:
        return await client.sections.rename(
            uid,
            name=name,
            description=description,
            sort_order=sort_order,
        )


async def add_section_element(
    profile: Profile,
    section_uid: str,
    data_element_uid: str,
    *,
    position: int | None = None,
) -> Section:
    """Append (or insert at `position`) a DataElement to the Section."""
    async with open_client(profile) as client:
        return await client.sections.add_element(
            section_uid,
            data_element_uid,
            position=position,
        )


async def remove_section_element(
    profile: Profile,
    section_uid: str,
    data_element_uid: str,
) -> Section:
    """Remove a DataElement from the Section (DE stays on the parent DataSet)."""
    async with open_client(profile) as client:
        return await client.sections.remove_element(section_uid, data_element_uid)


async def reorder_section_elements(
    profile: Profile,
    section_uid: str,
    *,
    data_element_uids: list[str],
) -> Section:
    """Replace the Section's ordered `dataElements` with exactly the given UIDs."""
    async with open_client(profile) as client:
        return await client.sections.reorder(section_uid, data_element_uids)


async def delete_section(profile: Profile, uid: str) -> None:
    """Delete a Section — DEs stay on the parent DataSet."""
    async with open_client(profile) as client:
        await client.sections.delete(uid)


# ---------------------------------------------------------------------------
# ValidationRule — `dhis2 metadata validation-rules ...`
# ---------------------------------------------------------------------------


async def show_validation_rule(profile: Profile, uid: str) -> ValidationRule:
    """Fetch one ValidationRule with both sides resolved."""
    async with open_client(profile) as client:
        return await client.validation_rules.get(uid)


async def create_validation_rule(
    profile: Profile,
    *,
    name: str,
    short_name: str,
    left_expression: str,
    operator: str,
    right_expression: str,
    period_type: str = "Monthly",
    importance: str = "MEDIUM",
    missing_value_strategy: str = "SKIP_IF_ALL_VALUES_MISSING",
    description: str | None = None,
    code: str | None = None,
    organisation_unit_levels: list[int] | None = None,
    uid: str | None = None,
) -> ValidationRule:
    """Create a ValidationRule."""
    async with open_client(profile) as client:
        return await client.validation_rules.create(
            name=name,
            short_name=short_name,
            left_expression=left_expression,
            operator=operator,
            right_expression=right_expression,
            period_type=period_type,
            importance=importance,
            missing_value_strategy=missing_value_strategy,
            description=description,
            code=code,
            organisation_unit_levels=organisation_unit_levels,
            uid=uid,
        )


async def rename_validation_rule(
    profile: Profile,
    uid: str,
    *,
    name: str | None = None,
    short_name: str | None = None,
    description: str | None = None,
) -> ValidationRule:
    """Partial-update the label fields on a ValidationRule."""
    async with open_client(profile) as client:
        return await client.validation_rules.rename(
            uid,
            name=name,
            short_name=short_name,
            description=description,
        )


async def delete_validation_rule(profile: Profile, uid: str) -> None:
    """Delete a ValidationRule."""
    async with open_client(profile) as client:
        await client.validation_rules.delete(uid)


# ---------------------------------------------------------------------------
# ValidationRuleGroup — `dhis2 metadata validation-rule-groups ...`
# ---------------------------------------------------------------------------


async def show_validation_rule_group(profile: Profile, uid: str) -> ValidationRuleGroup:
    """Fetch one group with rule refs."""
    async with open_client(profile) as client:
        return await client.validation_rule_groups.get(uid)


async def list_validation_rule_group_members(
    profile: Profile,
    uid: str,
    *,
    page: int = 1,
    page_size: int = 50,
) -> list[ValidationRule]:
    """Page through ValidationRules in a group."""
    async with open_client(profile) as client:
        return await client.validation_rule_groups.list_members(uid, page=page, page_size=page_size)


async def create_validation_rule_group(
    profile: Profile,
    *,
    name: str,
    short_name: str | None = None,
    code: str | None = None,
    description: str | None = None,
    uid: str | None = None,
) -> ValidationRuleGroup:
    """Create an empty ValidationRuleGroup."""
    async with open_client(profile) as client:
        return await client.validation_rule_groups.create(
            name=name,
            short_name=short_name,
            code=code,
            description=description,
            uid=uid,
        )


async def add_validation_rule_group_members(
    profile: Profile,
    uid: str,
    *,
    validation_rule_uids: list[str],
) -> ValidationRuleGroup:
    """Attach ValidationRules to a group."""
    async with open_client(profile) as client:
        return await client.validation_rule_groups.add_members(uid, validation_rule_uids=validation_rule_uids)


async def remove_validation_rule_group_members(
    profile: Profile,
    uid: str,
    *,
    validation_rule_uids: list[str],
) -> ValidationRuleGroup:
    """Detach ValidationRules from a group."""
    async with open_client(profile) as client:
        return await client.validation_rule_groups.remove_members(uid, validation_rule_uids=validation_rule_uids)


async def delete_validation_rule_group(profile: Profile, uid: str) -> None:
    """Delete a ValidationRuleGroup — members stay."""
    async with open_client(profile) as client:
        await client.validation_rule_groups.delete(uid)


# ---------------------------------------------------------------------------
# Predictor — `dhis2 metadata predictors ...`
# ---------------------------------------------------------------------------


async def show_predictor(profile: Profile, uid: str) -> Predictor:
    """Fetch one Predictor."""
    async with open_client(profile) as client:
        return await client.predictors.get(uid)


async def create_predictor(
    profile: Profile,
    *,
    name: str,
    short_name: str,
    expression: str,
    output_data_element_uid: str,
    period_type: str = "Monthly",
    sequential_sample_count: int = 3,
    annual_sample_count: int = 0,
    organisation_unit_level_uids: list[str] | None = None,
    output_combo_uid: str | None = None,
    description: str | None = None,
    code: str | None = None,
    uid: str | None = None,
) -> Predictor:
    """Create a Predictor."""
    async with open_client(profile) as client:
        return await client.predictors.create(
            name=name,
            short_name=short_name,
            expression=expression,
            output_data_element_uid=output_data_element_uid,
            period_type=period_type,
            sequential_sample_count=sequential_sample_count,
            annual_sample_count=annual_sample_count,
            organisation_unit_level_uids=organisation_unit_level_uids,
            output_combo_uid=output_combo_uid,
            description=description,
            code=code,
            uid=uid,
        )


async def rename_predictor(
    profile: Profile,
    uid: str,
    *,
    name: str | None = None,
    short_name: str | None = None,
    description: str | None = None,
) -> Predictor:
    """Partial-update the label fields on a Predictor."""
    async with open_client(profile) as client:
        return await client.predictors.rename(
            uid,
            name=name,
            short_name=short_name,
            description=description,
        )


async def delete_predictor(profile: Profile, uid: str) -> None:
    """Delete a Predictor."""
    async with open_client(profile) as client:
        await client.predictors.delete(uid)


# ---------------------------------------------------------------------------
# PredictorGroup — `dhis2 metadata predictor-groups ...`
# ---------------------------------------------------------------------------


async def show_predictor_group(profile: Profile, uid: str) -> PredictorGroup:
    """Fetch one group with predictor refs."""
    async with open_client(profile) as client:
        return await client.predictor_groups.get(uid)


async def list_predictor_group_members(
    profile: Profile,
    uid: str,
    *,
    page: int = 1,
    page_size: int = 50,
) -> list[Predictor]:
    """Page through Predictors in a group."""
    async with open_client(profile) as client:
        return await client.predictor_groups.list_members(uid, page=page, page_size=page_size)


async def create_predictor_group(
    profile: Profile,
    *,
    name: str,
    short_name: str | None = None,
    code: str | None = None,
    description: str | None = None,
    uid: str | None = None,
) -> PredictorGroup:
    """Create an empty PredictorGroup."""
    async with open_client(profile) as client:
        return await client.predictor_groups.create(
            name=name,
            short_name=short_name,
            code=code,
            description=description,
            uid=uid,
        )


async def add_predictor_group_members(
    profile: Profile,
    uid: str,
    *,
    predictor_uids: list[str],
) -> PredictorGroup:
    """Attach Predictors to a group."""
    async with open_client(profile) as client:
        return await client.predictor_groups.add_members(uid, predictor_uids=predictor_uids)


async def remove_predictor_group_members(
    profile: Profile,
    uid: str,
    *,
    predictor_uids: list[str],
) -> PredictorGroup:
    """Detach Predictors from a group."""
    async with open_client(profile) as client:
        return await client.predictor_groups.remove_members(uid, predictor_uids=predictor_uids)


async def delete_predictor_group(profile: Profile, uid: str) -> None:
    """Delete a PredictorGroup — members stay."""
    async with open_client(profile) as client:
        await client.predictor_groups.delete(uid)


# ---------------------------------------------------------------------------
# TrackedEntityAttribute — `dhis2 metadata tracked-entity-attributes ...`
# ---------------------------------------------------------------------------


async def show_tracked_entity_attribute(profile: Profile, uid: str) -> TrackedEntityAttribute:
    """Fetch one TrackedEntityAttribute with its refs resolved."""
    async with open_client(profile) as client:
        return await client.tracked_entity_attributes.get(uid)


async def create_tracked_entity_attribute(
    profile: Profile,
    *,
    name: str,
    short_name: str,
    value_type: str = "TEXT",
    aggregation_type: str = "NONE",
    option_set_uid: str | None = None,
    legend_set_uids: list[str] | None = None,
    unique: bool = False,
    generated: bool = False,
    confidential: bool = False,
    inherit: bool = False,
    display_in_list_no_program: bool = False,
    orgunit_scope: bool = False,
    pattern: str | None = None,
    field_mask: str | None = None,
    code: str | None = None,
    form_name: str | None = None,
    description: str | None = None,
    uid: str | None = None,
) -> TrackedEntityAttribute:
    """Create a TrackedEntityAttribute."""
    async with open_client(profile) as client:
        return await client.tracked_entity_attributes.create(
            name=name,
            short_name=short_name,
            value_type=value_type,
            aggregation_type=aggregation_type,
            option_set_uid=option_set_uid,
            legend_set_uids=legend_set_uids,
            unique=unique,
            generated=generated,
            confidential=confidential,
            inherit=inherit,
            display_in_list_no_program=display_in_list_no_program,
            orgunit_scope=orgunit_scope,
            pattern=pattern,
            field_mask=field_mask,
            code=code,
            form_name=form_name,
            description=description,
            uid=uid,
        )


async def rename_tracked_entity_attribute(
    profile: Profile,
    uid: str,
    *,
    name: str | None = None,
    short_name: str | None = None,
    form_name: str | None = None,
    description: str | None = None,
) -> TrackedEntityAttribute:
    """Partial-update the label fields on a TrackedEntityAttribute."""
    async with open_client(profile) as client:
        return await client.tracked_entity_attributes.rename(
            uid,
            name=name,
            short_name=short_name,
            form_name=form_name,
            description=description,
        )


async def delete_tracked_entity_attribute(profile: Profile, uid: str) -> None:
    """Delete a TrackedEntityAttribute."""
    async with open_client(profile) as client:
        await client.tracked_entity_attributes.delete(uid)


# ---------------------------------------------------------------------------
# TrackedEntityType — `dhis2 metadata tracked-entity-types ...`
# ---------------------------------------------------------------------------


async def show_tracked_entity_type(profile: Profile, uid: str) -> TrackedEntityType:
    """Fetch one TrackedEntityType with its attribute link table resolved."""
    async with open_client(profile) as client:
        return await client.tracked_entity_types.get(uid)


async def create_tracked_entity_type(
    profile: Profile,
    *,
    name: str,
    short_name: str,
    description: str | None = None,
    code: str | None = None,
    form_name: str | None = None,
    allow_audit_log: bool | None = None,
    feature_type: str | None = None,
    min_attributes_required_to_search: int | None = None,
    max_tei_count_to_return: int | None = None,
    uid: str | None = None,
) -> TrackedEntityType:
    """Create a TrackedEntityType."""
    async with open_client(profile) as client:
        return await client.tracked_entity_types.create(
            name=name,
            short_name=short_name,
            description=description,
            code=code,
            form_name=form_name,
            allow_audit_log=allow_audit_log,
            feature_type=feature_type,
            min_attributes_required_to_search=min_attributes_required_to_search,
            max_tei_count_to_return=max_tei_count_to_return,
            uid=uid,
        )


async def rename_tracked_entity_type(
    profile: Profile,
    uid: str,
    *,
    name: str | None = None,
    short_name: str | None = None,
    form_name: str | None = None,
    description: str | None = None,
) -> TrackedEntityType:
    """Partial-update the label fields on a TrackedEntityType."""
    async with open_client(profile) as client:
        return await client.tracked_entity_types.rename(
            uid,
            name=name,
            short_name=short_name,
            form_name=form_name,
            description=description,
        )


async def add_tracked_entity_type_attribute(
    profile: Profile,
    tet_uid: str,
    attribute_uid: str,
    *,
    mandatory: bool = False,
    searchable: bool = False,
    display_in_list: bool = True,
) -> TrackedEntityType:
    """Wire a TrackedEntityAttribute onto a TrackedEntityType."""
    async with open_client(profile) as client:
        return await client.tracked_entity_types.add_attribute(
            tet_uid,
            attribute_uid,
            mandatory=mandatory,
            searchable=searchable,
            display_in_list=display_in_list,
        )


async def remove_tracked_entity_type_attribute(
    profile: Profile,
    tet_uid: str,
    attribute_uid: str,
) -> TrackedEntityType:
    """Drop a TrackedEntityAttribute from a TrackedEntityType's link table."""
    async with open_client(profile) as client:
        return await client.tracked_entity_types.remove_attribute(tet_uid, attribute_uid)


async def delete_tracked_entity_type(profile: Profile, uid: str) -> None:
    """Delete a TrackedEntityType."""
    async with open_client(profile) as client:
        await client.tracked_entity_types.delete(uid)


# ---------------------------------------------------------------------------
# Program — `dhis2 metadata programs ...`
# ---------------------------------------------------------------------------


async def show_program(profile: Profile, uid: str) -> Program:
    """Fetch one Program with its PTEAs + OUs + stages resolved."""
    async with open_client(profile) as client:
        return await client.programs.get(uid)


async def create_program(
    profile: Profile,
    *,
    name: str,
    short_name: str,
    program_type: str = "WITH_REGISTRATION",
    tracked_entity_type_uid: str | None = None,
    category_combo_uid: str | None = None,
    description: str | None = None,
    code: str | None = None,
    form_name: str | None = None,
    display_incident_date: bool | None = None,
    enrollment_date_label: str | None = None,
    incident_date_label: str | None = None,
    feature_type: str | None = None,
    only_enroll_once: bool | None = None,
    select_enrollment_dates_in_future: bool | None = None,
    select_incident_dates_in_future: bool | None = None,
    expiry_days: int | None = None,
    min_attributes_required_to_search: int | None = None,
    max_tei_count_to_return: int | None = None,
    use_first_stage_during_registration: bool | None = None,
    uid: str | None = None,
) -> Program:
    """Create a Program."""
    async with open_client(profile) as client:
        return await client.programs.create(
            name=name,
            short_name=short_name,
            program_type=program_type,
            tracked_entity_type_uid=tracked_entity_type_uid,
            category_combo_uid=category_combo_uid,
            description=description,
            code=code,
            form_name=form_name,
            display_incident_date=display_incident_date,
            enrollment_date_label=enrollment_date_label,
            incident_date_label=incident_date_label,
            feature_type=feature_type,
            only_enroll_once=only_enroll_once,
            select_enrollment_dates_in_future=select_enrollment_dates_in_future,
            select_incident_dates_in_future=select_incident_dates_in_future,
            expiry_days=expiry_days,
            min_attributes_required_to_search=min_attributes_required_to_search,
            max_tei_count_to_return=max_tei_count_to_return,
            use_first_stage_during_registration=use_first_stage_during_registration,
            uid=uid,
        )


async def rename_program(
    profile: Profile,
    uid: str,
    *,
    name: str | None = None,
    short_name: str | None = None,
    form_name: str | None = None,
    description: str | None = None,
) -> Program:
    """Partial-update the label fields on a Program."""
    async with open_client(profile) as client:
        return await client.programs.rename(
            uid,
            name=name,
            short_name=short_name,
            form_name=form_name,
            description=description,
        )


async def add_program_attribute(
    profile: Profile,
    program_uid: str,
    attribute_uid: str,
    *,
    mandatory: bool = False,
    searchable: bool = False,
    display_in_list: bool = True,
    sort_order: int | None = None,
    allow_future_date: bool = False,
    render_options_as_radio: bool = False,
) -> Program:
    """Wire a TrackedEntityAttribute into the Program's enrollment form."""
    async with open_client(profile) as client:
        return await client.programs.add_attribute(
            program_uid,
            attribute_uid,
            mandatory=mandatory,
            searchable=searchable,
            display_in_list=display_in_list,
            sort_order=sort_order,
            allow_future_date=allow_future_date,
            render_options_as_radio=render_options_as_radio,
        )


async def remove_program_attribute(profile: Profile, program_uid: str, attribute_uid: str) -> Program:
    """Drop a TrackedEntityAttribute from the Program's enrollment form."""
    async with open_client(profile) as client:
        return await client.programs.remove_attribute(program_uid, attribute_uid)


async def add_program_organisation_unit(
    profile: Profile,
    program_uid: str,
    organisation_unit_uid: str,
) -> Program:
    """Scope the Program to another OrganisationUnit."""
    async with open_client(profile) as client:
        return await client.programs.add_organisation_unit(program_uid, organisation_unit_uid)


async def remove_program_organisation_unit(
    profile: Profile,
    program_uid: str,
    organisation_unit_uid: str,
) -> Program:
    """Drop an OrganisationUnit from the Program's scope."""
    async with open_client(profile) as client:
        return await client.programs.remove_organisation_unit(program_uid, organisation_unit_uid)


async def delete_program(profile: Profile, uid: str) -> None:
    """Delete a Program — DHIS2 rejects deletes on programs with enrollments or events."""
    async with open_client(profile) as client:
        await client.programs.delete(uid)


# ---------------------------------------------------------------------------
# ProgramStage — `dhis2 metadata program-stages ...`
# ---------------------------------------------------------------------------


async def show_program_stage(profile: Profile, uid: str) -> ProgramStage:
    """Fetch one ProgramStage with its PSDE list resolved."""
    async with open_client(profile) as client:
        return await client.program_stages.get(uid)


async def create_program_stage(
    profile: Profile,
    *,
    name: str,
    program_uid: str,
    short_name: str | None = None,
    description: str | None = None,
    code: str | None = None,
    form_name: str | None = None,
    sort_order: int | None = None,
    repeatable: bool | None = None,
    auto_generate_event: bool | None = None,
    generated_by_enrollment_date: bool | None = None,
    open_after_enrollment: bool | None = None,
    block_entry_form: bool | None = None,
    feature_type: str | None = None,
    period_type: str | None = None,
    validation_strategy: str | None = None,
    min_days_from_start: int | None = None,
    standard_interval: int | None = None,
    enable_user_assignment: bool | None = None,
    pre_generate_uid: bool | None = None,
    due_date_label: str | None = None,
    execution_date_label: str | None = None,
    event_label: str | None = None,
    uid: str | None = None,
) -> ProgramStage:
    """Create a ProgramStage under the given Program."""
    async with open_client(profile) as client:
        return await client.program_stages.create(
            name=name,
            program_uid=program_uid,
            short_name=short_name,
            description=description,
            code=code,
            form_name=form_name,
            sort_order=sort_order,
            repeatable=repeatable,
            auto_generate_event=auto_generate_event,
            generated_by_enrollment_date=generated_by_enrollment_date,
            open_after_enrollment=open_after_enrollment,
            block_entry_form=block_entry_form,
            feature_type=feature_type,
            period_type=period_type,
            validation_strategy=validation_strategy,
            min_days_from_start=min_days_from_start,
            standard_interval=standard_interval,
            enable_user_assignment=enable_user_assignment,
            pre_generate_uid=pre_generate_uid,
            due_date_label=due_date_label,
            execution_date_label=execution_date_label,
            event_label=event_label,
            uid=uid,
        )


async def rename_program_stage(
    profile: Profile,
    uid: str,
    *,
    name: str | None = None,
    short_name: str | None = None,
    form_name: str | None = None,
    description: str | None = None,
) -> ProgramStage:
    """Partial-update the label fields on a ProgramStage."""
    async with open_client(profile) as client:
        return await client.program_stages.rename(
            uid,
            name=name,
            short_name=short_name,
            form_name=form_name,
            description=description,
        )


async def add_program_stage_element(
    profile: Profile,
    stage_uid: str,
    data_element_uid: str,
    *,
    compulsory: bool = False,
    allow_future_date: bool = False,
    display_in_reports: bool = True,
    allow_provided_elsewhere: bool = False,
    render_options_as_radio: bool = False,
    sort_order: int | None = None,
) -> ProgramStage:
    """Wire a DataElement into the ProgramStage's PSDE list."""
    async with open_client(profile) as client:
        return await client.program_stages.add_element(
            stage_uid,
            data_element_uid,
            compulsory=compulsory,
            allow_future_date=allow_future_date,
            display_in_reports=display_in_reports,
            allow_provided_elsewhere=allow_provided_elsewhere,
            render_options_as_radio=render_options_as_radio,
            sort_order=sort_order,
        )


async def remove_program_stage_element(
    profile: Profile,
    stage_uid: str,
    data_element_uid: str,
) -> ProgramStage:
    """Drop a DataElement from the ProgramStage's PSDE list."""
    async with open_client(profile) as client:
        return await client.program_stages.remove_element(stage_uid, data_element_uid)


async def reorder_program_stage_elements(
    profile: Profile,
    stage_uid: str,
    *,
    data_element_uids: list[str],
) -> ProgramStage:
    """Replace the ordered `programStageDataElements` with exactly the given UIDs."""
    async with open_client(profile) as client:
        return await client.program_stages.reorder(stage_uid, data_element_uids)


async def delete_program_stage(profile: Profile, uid: str) -> None:
    """Delete a ProgramStage — DHIS2 rejects deletes on stages with recorded events."""
    async with open_client(profile) as client:
        await client.program_stages.delete(uid)


# ---------------------------------------------------------------------------
# Bulk rename — `dhis2 metadata rename ...`
# ---------------------------------------------------------------------------


class BulkRenameEntry(BaseModel):
    """One per-UID preview row produced by `bulk_rename_metadata`.

    `*_before` are the server-side values at read time;
    `*_after` apply the requested prefix / suffix / replacement. Fields
    DHIS2 doesn't expose (e.g. shortName on a resource that skips it)
    come through as `None`.
    """

    model_config = ConfigDict(frozen=True)

    uid: str
    name_before: str | None = None
    name_after: str | None = None
    short_name_before: str | None = None
    short_name_after: str | None = None


class BulkRenameResult(BaseModel):
    """Aggregated result from `dhis2 metadata rename`.

    `entries` is always the per-UID preview with before/after values;
    `patch_result` is the committed outcome when `dry_run=False`, else
    `None`. Callers rendering a CLI table pick one based on the mode.
    """

    model_config = ConfigDict(frozen=True)

    resource: str
    dry_run: bool
    matched: int
    entries: list[BulkRenameEntry] = Field(default_factory=list)
    patch_result: BulkPatchResult | None = None

    @property
    def failed(self) -> int:
        """Number of UIDs the server rejected; `0` on dry-run."""
        if self.patch_result is None:
            return 0
        return len(self.patch_result.failures)

    @property
    def succeeded(self) -> int:
        """Number of UIDs the server applied; `0` on dry-run."""
        if self.patch_result is None:
            return 0
        return len(self.patch_result.successful_uids)


async def bulk_rename_metadata(
    profile: Profile,
    resource: str,
    *,
    filters: list[str] | None = None,
    root_junction: str | None = None,
    name_prefix: str | None = None,
    name_suffix: str | None = None,
    name_strip_prefix: str | None = None,
    name_strip_suffix: str | None = None,
    short_name_prefix: str | None = None,
    short_name_suffix: str | None = None,
    short_name_strip_prefix: str | None = None,
    short_name_strip_suffix: str | None = None,
    set_description: str | None = None,
    concurrency: int = 8,
    dry_run: bool = False,
) -> BulkRenameResult:
    """Bulk-rename many metadata objects with RFC 6902 patches.

    The filter DSL is the same as `dhis2 metadata list` — each
    `filters` entry is a `<prop>:<op>:<value>` expression, `AND`-joined
    by default (pass `root_junction="OR"` to switch). The mutation
    flags stack: a DE that matches can receive a name prefix + a short
    name suffix + a description rewrite from one invocation.

    Prefix / suffix add paths (`name_prefix`, `name_suffix`) and their
    strip counterparts (`name_strip_prefix`, `name_strip_suffix`) are
    all idempotent — the add helpers skip rows already prefixed /
    suffixed, the strip helpers skip rows that don't carry the
    pattern. You can stack them: `--name-strip-prefix "[old] "
    --name-prefix "[new] "` rewrites the prefix.

    `dry_run=True` returns the preview (matched UIDs + before/after
    names) without calling `/api/<resource>/<uid>`. Live calls fan out
    through `client.metadata.patch_bulk(...)` under `concurrency`;
    failures land on `BulkRenameResult.patch_result.failures` instead
    of raising.
    """
    mutation_flags = (
        name_prefix,
        name_suffix,
        name_strip_prefix,
        name_strip_suffix,
        short_name_prefix,
        short_name_suffix,
        short_name_strip_prefix,
        short_name_strip_suffix,
        set_description,
    )
    if not any(m is not None for m in mutation_flags):
        raise ValueError(
            "bulk_rename_metadata requires at least one of name_prefix / name_suffix / "
            "name_strip_prefix / name_strip_suffix / short_name_prefix / short_name_suffix / "
            "short_name_strip_prefix / short_name_strip_suffix / set_description",
        )

    params: dict[str, Any] = {
        "fields": "id,name,shortName",
        "paging": "false",
    }
    if filters:
        params["filter"] = filters
    if root_junction is not None:
        params["rootJunction"] = root_junction

    async with open_client(profile) as client:
        raw = await client.get_raw(f"/api/{resource}", params=params)
        rows = raw.get(resource) or []
        entries: list[BulkRenameEntry] = []
        patches: list[tuple[str, list[dict[str, Any]]]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            uid = row.get("id")
            if not isinstance(uid, str):
                continue
            name_before = row.get("name") if isinstance(row.get("name"), str) else None
            short_before = row.get("shortName") if isinstance(row.get("shortName"), str) else None
            name_after = _apply_string_mutation(
                name_before,
                prefix=name_prefix,
                suffix=name_suffix,
                strip_prefix=name_strip_prefix,
                strip_suffix=name_strip_suffix,
            )
            short_after = _apply_string_mutation(
                short_before,
                prefix=short_name_prefix,
                suffix=short_name_suffix,
                strip_prefix=short_name_strip_prefix,
                strip_suffix=short_name_strip_suffix,
            )
            ops: list[dict[str, Any]] = []
            if name_after != name_before and name_after is not None:
                ops.append({"op": "replace", "path": "/name", "value": name_after})
            if short_after != short_before and short_after is not None:
                ops.append({"op": "replace", "path": "/shortName", "value": short_after})
            if set_description is not None:
                ops.append({"op": "replace", "path": "/description", "value": set_description})
            if not ops:
                continue
            entries.append(
                BulkRenameEntry(
                    uid=uid,
                    name_before=name_before,
                    name_after=name_after,
                    short_name_before=short_before,
                    short_name_after=short_after,
                ),
            )
            patches.append((uid, ops))

        patch_result: BulkPatchResult | None = None
        if patches and not dry_run:
            patch_result = await client.metadata.patch_bulk(resource, patches, concurrency=concurrency)

    return BulkRenameResult(
        resource=resource,
        dry_run=dry_run,
        matched=len(entries),
        entries=entries,
        patch_result=patch_result,
    )


def _apply_string_mutation(
    current: str | None,
    *,
    prefix: str | None = None,
    suffix: str | None = None,
    strip_prefix: str | None = None,
    strip_suffix: str | None = None,
) -> str | None:
    """Apply add + strip prefix/suffix to a label idempotently.

    `None` input stays `None`. Strip operations run first so callers
    can combine `--strip-prefix "[old] " --prefix "[new] "` to rewrite
    the prefix in one pass. Each op is a no-op when the pattern isn't
    present / already present — so re-running is safe.
    """
    if current is None:
        return None
    result = current
    if strip_prefix is not None and result.startswith(strip_prefix):
        result = result[len(strip_prefix) :]
    if strip_suffix is not None and result.endswith(strip_suffix):
        result = result[: -len(strip_suffix)]
    if prefix is not None and not result.startswith(prefix):
        result = f"{prefix}{result}"
    if suffix is not None and not result.endswith(suffix):
        result = f"{result}{suffix}"
    return result


# ---------------------------------------------------------------------------
# Bulk retag — `dhis2 metadata retag ...`
# ---------------------------------------------------------------------------


class BulkRetagEntry(BaseModel):
    """One per-UID preview row produced by `bulk_retag_metadata`.

    Keys in `before` / `after` mirror the RFC 6902 paths the retag
    would apply (`/categoryCombo`, `/optionSet/id`, `/aggregationType`,
    …). Values are string representations of the server-side state
    pre/post — refs render as UIDs, enums as their string form. Fields
    the resource doesn't expose come through as `None` on both sides.
    """

    model_config = ConfigDict(frozen=True)

    uid: str
    before: dict[str, str | None] = Field(default_factory=dict)
    after: dict[str, str | None] = Field(default_factory=dict)


class BulkRetagResult(BaseModel):
    """Aggregated result from `dhis2 metadata retag`."""

    model_config = ConfigDict(frozen=True)

    resource: str
    dry_run: bool
    matched: int
    entries: list[BulkRetagEntry] = Field(default_factory=list)
    patch_result: BulkPatchResult | None = None

    @property
    def failed(self) -> int:
        """Number of UIDs the server rejected; `0` on dry-run."""
        if self.patch_result is None:
            return 0
        return len(self.patch_result.failures)

    @property
    def succeeded(self) -> int:
        """Number of UIDs the server applied; `0` on dry-run."""
        if self.patch_result is None:
            return 0
        return len(self.patch_result.successful_uids)


async def bulk_retag_metadata(
    profile: Profile,
    resource: str,
    *,
    filters: list[str] | None = None,
    root_junction: str | None = None,
    category_combo_uid: str | None = None,
    option_set_uid: str | None = None,
    clear_option_set: bool = False,
    aggregation_type: str | None = None,
    domain_type: str | None = None,
    legend_set_uids: list[str] | None = None,
    clear_legend_sets: bool = False,
    concurrency: int = 8,
    dry_run: bool = False,
) -> BulkRetagResult:
    """Bulk-rewrite ref / enum fields across a filtered cohort.

    Sister to `bulk_rename_metadata`. Each flag maps to an RFC 6902
    patch:
    - `category_combo_uid` → `replace /categoryCombo` with `{id: uid}`.
    - `option_set_uid` → `replace /optionSet` with `{id: uid}`.
    - `clear_option_set=True` → `remove /optionSet`.
    - `aggregation_type` → `replace /aggregationType` (string enum).
    - `domain_type` → `replace /domainType` (DataElement-only; DHIS2
      rejects on other resources — surfaces in `patch_result.failures`).
    - `legend_set_uids` → `replace /legendSets` with `[{id: u}, …]`
      (full-list replacement — previous legends are dropped).
    - `clear_legend_sets=True` → `replace /legendSets` with `[]`.

    Pass at least one mutation; multiple flags stack into one
    bulk-patch round-trip per matched UID. `dry_run=True` returns the
    preview without calling `/api/<resource>/<uid>`.
    """
    if not any(
        [
            category_combo_uid,
            option_set_uid,
            clear_option_set,
            aggregation_type,
            domain_type,
            legend_set_uids,
            clear_legend_sets,
        ],
    ):
        raise ValueError(
            "bulk_retag_metadata requires at least one of category_combo_uid / option_set_uid / "
            "clear_option_set / aggregation_type / domain_type / legend_set_uids / clear_legend_sets",
        )
    if option_set_uid and clear_option_set:
        raise ValueError("pick one of option_set_uid / clear_option_set (not both)")
    if legend_set_uids and clear_legend_sets:
        raise ValueError("pick one of legend_set_uids / clear_legend_sets (not both)")

    fields_parts = ["id"]
    if category_combo_uid:
        fields_parts.append("categoryCombo[id]")
    if option_set_uid or clear_option_set:
        fields_parts.append("optionSet[id]")
    if aggregation_type:
        fields_parts.append("aggregationType")
    if domain_type:
        fields_parts.append("domainType")
    if legend_set_uids or clear_legend_sets:
        fields_parts.append("legendSets[id]")
    fields = ",".join(fields_parts)

    params: dict[str, Any] = {"fields": fields, "paging": "false"}
    if filters:
        params["filter"] = filters
    if root_junction is not None:
        params["rootJunction"] = root_junction

    async with open_client(profile) as client:
        raw = await client.get_raw(f"/api/{resource}", params=params)
        rows = raw.get(resource) or []
        entries: list[BulkRetagEntry] = []
        patches: list[tuple[str, list[dict[str, Any]]]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            uid = row.get("id")
            if not isinstance(uid, str):
                continue
            before: dict[str, str | None] = {}
            after: dict[str, str | None] = {}
            ops: list[dict[str, Any]] = []

            if category_combo_uid is not None:
                cc_before = _ref_id(row.get("categoryCombo"))
                before["/categoryCombo"] = cc_before
                after["/categoryCombo"] = category_combo_uid
                if cc_before != category_combo_uid:
                    ops.append({"op": "replace", "path": "/categoryCombo", "value": {"id": category_combo_uid}})

            if option_set_uid is not None:
                os_before = _ref_id(row.get("optionSet"))
                before["/optionSet"] = os_before
                after["/optionSet"] = option_set_uid
                if os_before != option_set_uid:
                    ops.append({"op": "replace", "path": "/optionSet", "value": {"id": option_set_uid}})
            elif clear_option_set:
                os_before = _ref_id(row.get("optionSet"))
                before["/optionSet"] = os_before
                after["/optionSet"] = None
                if os_before is not None:
                    ops.append({"op": "remove", "path": "/optionSet"})

            if aggregation_type is not None:
                at_before = row.get("aggregationType") if isinstance(row.get("aggregationType"), str) else None
                before["/aggregationType"] = at_before
                after["/aggregationType"] = aggregation_type
                if at_before != aggregation_type:
                    ops.append({"op": "replace", "path": "/aggregationType", "value": aggregation_type})

            if domain_type is not None:
                dt_before = row.get("domainType") if isinstance(row.get("domainType"), str) else None
                before["/domainType"] = dt_before
                after["/domainType"] = domain_type
                if dt_before != domain_type:
                    ops.append({"op": "replace", "path": "/domainType", "value": domain_type})

            if legend_set_uids is not None:
                ls_before_ids = _list_ref_ids(row.get("legendSets"))
                before["/legendSets"] = ",".join(ls_before_ids) or None
                after["/legendSets"] = ",".join(legend_set_uids) or None
                if ls_before_ids != legend_set_uids:
                    ops.append(
                        {
                            "op": "replace",
                            "path": "/legendSets",
                            "value": [{"id": ls_uid} for ls_uid in legend_set_uids],
                        },
                    )
            elif clear_legend_sets:
                ls_before_ids = _list_ref_ids(row.get("legendSets"))
                before["/legendSets"] = ",".join(ls_before_ids) or None
                after["/legendSets"] = None
                if ls_before_ids:
                    ops.append({"op": "replace", "path": "/legendSets", "value": []})

            if not ops:
                continue
            entries.append(BulkRetagEntry(uid=uid, before=before, after=after))
            patches.append((uid, ops))

        patch_result: BulkPatchResult | None = None
        if patches and not dry_run:
            patch_result = await client.metadata.patch_bulk(resource, patches, concurrency=concurrency)

    return BulkRetagResult(
        resource=resource,
        dry_run=dry_run,
        matched=len(entries),
        entries=entries,
        patch_result=patch_result,
    )


def _ref_id(value: Any) -> str | None:
    """Pull the `.id` out of a ref dict, or `None` for missing / malformed entries."""
    if isinstance(value, dict):
        inner = value.get("id")
        if isinstance(inner, str):
            return inner
    return None


def _list_ref_ids(value: Any) -> list[str]:
    """Extract `[{id: x}, …]` → `[x, …]`, filtering out malformed entries."""
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for entry in value:
        inner = _ref_id(entry)
        if inner is not None:
            out.append(inner)
    return out
