"""`Dhis2Client.metadata` — bulk operations over `/api/metadata`.

One accessor for bulk-write paths that don't have a typed generated CRUD
entry (generated resources cover the per-UID `GET / POST / PUT / PATCH /
DELETE` surface per resource type). Covers:

- `delete_bulk` / `delete_bulk_multi` — fast-delete via `importStrategy=DELETE`.
- `dry_run` — validate a cross-resource bundle without committing
  (`importMode=VALIDATE`).
- `search` — cross-resource metadata search. Fans out three concurrent
  `/api/metadata?filter=<field>:ilike:<q>` calls (one per match axis:
  `id`, `code`, `name`) and merges the results with UID dedup. Supports
  `--resource <type>` narrowing to one resource kind, `--fields` extra
  columns in the typed response, `exact=True` to switch from `ilike`
  substring to `eq` exact match. DHIS2's `/api/metadata` silently
  ignores `rootJunction` and ANDs multiple filters (see BUGS.md #29),
  so OR-across-fields needs N requests.
- `usage` — reverse lookup: "what metadata references this UID?" Given
  a UID, resolves the owning resource via `/api/identifiableObjects/{uid}`,
  then fans out concurrent per-resource queries against `/api/<target>?
  filter=<ref-path>:eq:<uid>` to find every object that references it.
  Useful as a deletion-safety check — any dashboard / viz / dataset
  referencing the UID you're about to delete surfaces in the result.

For typed bulk writes scoped to a single resource, reach for the generated
per-resource accessor's `save_bulk` method
(`client.resources.data_elements.save_bulk([DataElement(...), ...])`) —
IDE autocomplete gives you model-typed input on that path.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field

from dhis2w_client.errors import Dhis2ApiError
from dhis2w_client.generated.v43.oas import SharingObject, Status
from dhis2w_client.v43.envelopes import WebMessageResponse
from dhis2w_client.v43.json_patch import JsonPatchOp
from dhis2w_client.v43.sharing import SharingBuilder

if TYPE_CHECKING:
    from dhis2w_client.v43.client import Dhis2Client

# Match axes for `MetadataAccessor.search` — one `/api/metadata?filter=X:ilike:<q>`
# call per entry, results merged and deduplicated by UID.
_SEARCH_FIELDS: tuple[str, ...] = ("id", "code", "name")

# Minimum fields each search / usage hit carries. Overridable via the `fields` kwarg
# on `MetadataAccessor.search`. `id`, `name`, `code`, `href` feed the typed
# `SearchHit` model directly; extras land on `SearchHit.extras`.
_SEARCH_DEFAULT_FIELDS: str = "id,name,code,href"

# Reference-path map for `MetadataAccessor.usage`. Each entry maps an owning
# resource type (plural form DHIS2 uses on its /api/<type> endpoints) to the
# `(target_resource, filter_path_template)` tuples that find objects of the
# target type referencing a UID of the owning type.
#
# The filter-path strings are DHIS2's dotted-filter DSL as documented in
# https://docs.dhis2.org/.../metadata-object-filter.html. `{uid}` is replaced
# at call time. `eq` is used for structured references (primary keys, nested
# object IDs); `ilike` is used for text fields where the UID is embedded in an
# expression (indicator numerators, validation-rule expressions, predictor
# generators).
#
# Coverage is best-effort — targets reflect the reference shapes most likely
# to block a delete in practice. Extend this map as concrete needs surface.
_USAGE_PATTERNS: dict[str, tuple[tuple[str, str], ...]] = {
    "dataElements": (
        ("dataSets", "dataSetElements.dataElement.id:eq:{uid}"),
        ("visualizations", "dataDimensionItems.dataElement.id:eq:{uid}"),
        ("maps", "mapViews.dataDimensionItems.dataElement.id:eq:{uid}"),
        ("programStages", "programStageDataElements.dataElement.id:eq:{uid}"),
        ("programRuleVariables", "dataElement.id:eq:{uid}"),
        # Indicator numerator / denominator / predictor generators embed DE UIDs
        # as `#{<uid>}` expressions — ilike on the raw text catches them.
        ("indicators", "numerator:ilike:{uid}"),
        ("predictors", "generator.expression:ilike:{uid}"),
        ("validationRules", "leftSide.expression:ilike:{uid}"),
    ),
    "indicators": (
        ("visualizations", "dataDimensionItems.indicator.id:eq:{uid}"),
        ("maps", "mapViews.dataDimensionItems.indicator.id:eq:{uid}"),
    ),
    "programIndicators": (
        ("visualizations", "dataDimensionItems.programIndicator.id:eq:{uid}"),
        ("maps", "mapViews.dataDimensionItems.programIndicator.id:eq:{uid}"),
    ),
    "visualizations": (("dashboards", "dashboardItems.visualization.id:eq:{uid}"),),
    "maps": (("dashboards", "dashboardItems.map.id:eq:{uid}"),),
    "categoryCombos": (
        ("dataElements", "categoryCombo.id:eq:{uid}"),
        ("dataSets", "categoryCombo.id:eq:{uid}"),
        ("programs", "categoryCombo.id:eq:{uid}"),
    ),
    "optionSets": (
        ("dataElements", "optionSet.id:eq:{uid}"),
        ("trackedEntityAttributes", "optionSet.id:eq:{uid}"),
        ("attributes", "optionSet.id:eq:{uid}"),
    ),
    "organisationUnits": (
        ("users", "organisationUnits.id:eq:{uid}"),
        ("organisationUnitGroups", "organisationUnits.id:eq:{uid}"),
        ("dataSets", "organisationUnits.id:eq:{uid}"),
        ("programs", "organisationUnits.id:eq:{uid}"),
    ),
    "organisationUnitGroups": (("organisationUnitGroupSets", "organisationUnitGroups.id:eq:{uid}"),),
    "programs": (
        ("programStages", "program.id:eq:{uid}"),
        ("programIndicators", "program.id:eq:{uid}"),
        ("programRules", "program.id:eq:{uid}"),
    ),
    "programStages": (("programs", "programStages.id:eq:{uid}"),),
    "dataSets": (("sections", "dataSet.id:eq:{uid}"),),
    "trackedEntityAttributes": (
        ("programs", "programTrackedEntityAttributes.trackedEntityAttribute.id:eq:{uid}"),
        ("trackedEntityTypes", "trackedEntityTypeAttributes.trackedEntityAttribute.id:eq:{uid}"),
    ),
    "trackedEntityTypes": (("programs", "trackedEntityType.id:eq:{uid}"),),
    "userRoles": (("users", "userRoles.id:eq:{uid}"),),
    "userGroups": (("users", "userGroups.id:eq:{uid}"),),
}


class SearchHit(BaseModel):
    """One matching metadata object returned by `MetadataAccessor.search` or `.usage`.

    `extras` holds any DHIS2 fields beyond the core four (`id`, `name`, `code`,
    `href`) — populated when callers pass a wider `fields` selector to `search`.
    """

    model_config = ConfigDict(frozen=True)

    uid: str
    name: str
    code: str | None = None
    resource: str = Field(..., description="DHIS2 resource plural (e.g. 'dataElements', 'dashboards')")
    href: str | None = None
    extras: dict[str, Any] = Field(default_factory=dict)


class SearchResults(BaseModel):
    """Grouped results from `MetadataAccessor.search` — one list per resource type.

    `hits` maps each DHIS2 resource plural (`dataElements`, `indicators`,
    `dashboards`, …) to the matching objects within that resource. Empty
    resources are omitted, so `SearchResults.total` plus
    `hits.keys()` answer "which resource types matched" in one look.
    """

    model_config = ConfigDict(frozen=True)

    query: str
    hits: dict[str, list[SearchHit]] = Field(default_factory=dict)

    @property
    def total(self) -> int:
        """Total hits across every resource type."""
        return sum(len(rows) for rows in self.hits.values())

    def flat(self) -> list[SearchHit]:
        """Return every hit as a flat list — convenient for sorted/ranked display."""
        return [hit for rows in self.hits.values() for hit in rows]


class BulkPatchError(BaseModel):
    """One per-UID failure from `MetadataAccessor.patch_bulk(_multi)`.

    DHIS2 reports PATCH errors one-at-a-time (the bulk endpoint is
    client-side fan-out over per-UID `PATCH /api/<resource>/<uid>`).
    This model captures what each rejection carried so callers can
    surface row-level detail without catching exceptions themselves.
    """

    model_config = ConfigDict(frozen=True)

    uid: str
    resource: str
    status_code: int
    message: str


class BulkPatchResult(BaseModel):
    """Aggregated result from `MetadataAccessor.patch_bulk(_multi)`.

    Tracks per-UID success/failure across a fan-out of RFC 6902 PATCH
    requests. The overall call always succeeds at the HTTP-layer level
    — individual rejections land in `failures` instead of raising.
    """

    model_config = ConfigDict(frozen=True)

    successful_uids: list[str] = Field(default_factory=list)
    failures: list[BulkPatchError] = Field(default_factory=list)

    @property
    def total(self) -> int:
        """Total UIDs attempted — `successful + failed`."""
        return len(self.successful_uids) + len(self.failures)

    @property
    def ok(self) -> bool:
        """True when every UID succeeded; False when at least one failed."""
        return not self.failures


class BulkSharingError(BaseModel):
    """One per-UID failure from `MetadataAccessor.apply_sharing_bulk(_multi)`.

    DHIS2's `/api/sharing` is per-object, so the bulk surface is
    client-side fan-out. Per-object rejections land here so callers
    surface row-level detail without catching exceptions themselves.
    """

    model_config = ConfigDict(frozen=True)

    uid: str
    resource: str
    status_code: int
    message: str


class BulkSharingResult(BaseModel):
    """Aggregated result from `MetadataAccessor.apply_sharing_bulk(_multi)`.

    Tracks per-UID success/failure across a fan-out of `POST /api/sharing`
    requests. The overall call always succeeds at the HTTP-layer level
    — individual rejections land in `failures` instead of raising.
    """

    model_config = ConfigDict(frozen=True)

    successful_uids: list[str] = Field(default_factory=list)
    failures: list[BulkSharingError] = Field(default_factory=list)

    @property
    def total(self) -> int:
        """Total UIDs attempted — `successful + failed`."""
        return len(self.successful_uids) + len(self.failures)

    @property
    def ok(self) -> bool:
        """True when every UID succeeded; False when at least one failed."""
        return not self.failures


class MetadataAccessor:
    """Bulk metadata operations on `/api/metadata`.

    Per-resource CRUD lives on the generated `client.resources.<Resource>`
    accessors (one class per DHIS2 resource type, auto-generated from
    `/api/schemas`). This accessor is specifically for the
    multi-resource / multi-UID paths that need the `/api/metadata`
    bundle endpoint — they don't fit the single-resource accessor shape.
    """

    def __init__(self, client: Dhis2Client) -> None:
        """Bind to the sharing client."""
        self._client = client

    async def search(
        self,
        query: str,
        *,
        page_size: int = 50,
        resource: str | None = None,
        fields: str | None = None,
        exact: bool = False,
    ) -> SearchResults:
        """Cross-resource metadata search — UID / code / name, OR-merged.

        Fans out `len(_SEARCH_FIELDS)` concurrent `/api/metadata` calls, one
        per match axis (`id`, `code`, `name`), each filtered as
        `<field>:ilike:<query>` (or `<field>:eq:<query>` when `exact=True`).
        DHIS2 returns a bundle `{dataElements: [...], indicators: [...], ...}`
        per call grouped by resource type; this method merges them,
        deduplicating by `(resource, uid)` so an object matching on both
        id and name doesn't appear twice.

        Works uniformly for:

        - **Full UID** — id:ilike hits the exact record, the other axes
          usually miss; result is one hit.
        - **Partial UID** — id:ilike:<prefix> matches every UID starting
          with or containing the substring across every resource.
        - **Code lookup** — code:ilike:<fragment> matches on the business
          identifier; indicators / DEs often carry meaningful codes.
        - **Name substring** — name:ilike:<fragment> is the broadest
          match and usually dominates the result set.

        Pass `resource="dataElements"` (etc.) to narrow the result to one
        resource kind. Pass `fields="id,name,code,valueType,domainType"`
        to ask DHIS2 for extra attributes per hit — anything beyond the
        core four (`id` / `name` / `code` / `href`) lands on `SearchHit.extras`.
        Pass `exact=True` to switch from `ilike` substring to `eq` exact
        match (useful when a partial-UID search would otherwise match too
        many siblings).

        A single `rootJunction=OR` call would be cleaner, but DHIS2's
        `/api/metadata` endpoint silently ignores `rootJunction` and
        ANDs multiple filters (BUGS.md #29), so N requests are the only
        way to get cross-field OR.
        """
        operator = "eq" if exact else "ilike"
        effective_fields = fields or _SEARCH_DEFAULT_FIELDS
        field_results = await asyncio.gather(
            *(
                self._search_one_field(
                    field,
                    query,
                    operator=operator,
                    fields=effective_fields,
                    resource=resource,
                    page_size=page_size,
                )
                for field in _SEARCH_FIELDS
            ),
        )
        return _merge_search_results(query, field_results)

    async def _search_one_field(
        self,
        field: str,
        query: str,
        *,
        operator: str,
        fields: str,
        resource: str | None,
        page_size: int,
    ) -> SearchResults:
        """Issue one `/api/metadata?filter=<field>:<op>:<query>` call, optionally narrowed."""
        params: dict[str, Any] = {
            "filter": f"{field}:{operator}:{query}",
            "fields": fields,
            "pageSize": page_size,
        }
        if resource is not None:
            # Per-resource narrowing: DHIS2 understands `filter=<attr>:...` on
            # `/api/<resource>` exactly the same way, so we can hit the typed
            # endpoint and save the broadcast over every resource section.
            raw = await self._client.get_raw(f"/api/{resource}", params=params)
            # Response shape is `{<resource>: [...]}` — repackage as a bundle
            # so `_search_results_from_bundle` sees a uniform input.
            bundle = {resource: raw.get(resource) or []}
            return _search_results_from_bundle(query, bundle)
        raw = await self._client.get_raw("/api/metadata", params=params)
        return _search_results_from_bundle(query, raw)

    async def usage(
        self,
        uid: str,
        *,
        page_size: int = 100,
    ) -> SearchResults:
        """Reverse lookup — find every object that references `uid`.

        Two-step workflow: (1) resolve the UID's owning resource via
        `/api/identifiableObjects/{uid}` so we know which reference-shapes
        to look up; (2) fan out concurrent `/api/<target>?filter=<path>:eq:<uid>`
        calls against the known reference paths for that owning type.

        Coverage is best-effort — the reference map (`_USAGE_PATTERNS`)
        encodes the reference shapes most likely to block a delete in
        practice (dataSets + visualizations + maps + programStages
        referencing a DE, dashboards referencing a viz/map, categoryCombo
        references on DEs / dataSets / programs, OU references on users /
        groups, etc.). Extend `_USAGE_PATTERNS` when a new shape surfaces.

        Returns a `SearchResults` keyed by target resource — the same
        shape as `search`, so CLI rendering reuses cleanly. Empty result
        means no reference was found on any covered path — caveat: it
        does not prove the UID is safe to delete if the reference shape
        isn't in the map.

        Raises `Dhis2ApiError` with `status_code=404` when the UID
        doesn't resolve to any known resource.
        """
        owning = await self._resolve_resource(uid)
        patterns = _USAGE_PATTERNS.get(owning, ())
        if not patterns:
            return SearchResults(query=uid, hits={})
        query_results = await asyncio.gather(
            *(
                self._usage_query(target, template.format(uid=uid), page_size=page_size)
                for target, template in patterns
            ),
        )
        return _merge_search_results(uid, query_results)

    async def _resolve_resource(self, uid: str) -> str:
        """Resolve the UID's owning resource via `/api/identifiableObjects/{uid}`."""
        raw = await self._client.get_raw(f"/api/identifiableObjects/{uid}")
        href = str(raw.get("href") or "")
        parts = [p for p in href.split("/") if p]
        if len(parts) < 2 or parts[-1] != uid:
            return "unknown"
        return parts[-2]

    async def _usage_query(self, target: str, filter_expr: str, *, page_size: int) -> SearchResults:
        """Issue one `/api/<target>?filter=<expr>` call for the reverse-reference scan."""
        params: dict[str, Any] = {"filter": filter_expr, "fields": _SEARCH_DEFAULT_FIELDS, "pageSize": page_size}
        raw = await self._client.get_raw(f"/api/{target}", params=params)
        bundle = {target: raw.get(target) or []}
        return _search_results_from_bundle(target, bundle)

    async def delete_bulk(self, resource_type: str, uids: Sequence[str]) -> WebMessageResponse:
        """Delete every UID in `uids` from one DHIS2 resource type in a single request.

        Wraps `POST /api/metadata?importStrategy=DELETE&atomicMode=NONE` with a
        minimal `{resource_type: [{"id": uid}, ...]}` bundle. Returns the
        `WebMessageResponse` envelope — `.import_count().deleted` reports the
        total rows deleted; `.conflicts()` lists anything DHIS2 refused
        (foreign-key constraints, soft-delete protection, etc.).

        `atomicMode=NONE` lets partial failures through: some UIDs deleted,
        some held back with a conflict. Switch to `delete_bulk_multi` with
        atomic semantics when every row must delete or none should.
        Empty `uids` short-circuits with a no-op envelope (no HTTP call).
        """
        return await self.delete_bulk_multi({resource_type: list(uids)})

    async def delete_bulk_multi(
        self,
        by_resource: Mapping[str, Sequence[str]],
        *,
        atomic_mode: str = "NONE",
    ) -> WebMessageResponse:
        """Delete across multiple resource types in one `/api/metadata` call.

        `by_resource` maps each resource type (e.g. `"dataElements"`,
        `"indicators"`) to the UIDs to delete for that type. Entries with
        empty UID lists are skipped. `atomic_mode` controls DHIS2's
        partial-failure behaviour: `"NONE"` (default) lets individual
        conflicts through, `"ALL"` rolls the entire bundle back on any
        conflict.
        """
        bundle: dict[str, list[dict[str, str]]] = {
            resource: [{"id": uid} for uid in uids] for resource, uids in by_resource.items() if uids
        }
        if not bundle:
            return WebMessageResponse(status=Status.OK, httpStatus="OK", httpStatusCode=200, message="no uids supplied")
        raw = await self._client.post_raw(
            "/api/metadata",
            body=bundle,
            params={"importStrategy": "DELETE", "atomicMode": atomic_mode},
        )
        return WebMessageResponse.model_validate(raw)

    async def patch_bulk(
        self,
        resource_type: str,
        patches: Sequence[tuple[str, Sequence[JsonPatchOp | dict[str, Any]]]],
        *,
        concurrency: int = 8,
    ) -> BulkPatchResult:
        """Apply RFC 6902 patches to many UIDs on one resource in parallel.

        `patches` is a list of `(uid, ops)` pairs. `ops` can carry typed
        `JsonPatchOp` models (auto-dumped via `by_alias + exclude_none`)
        or raw dicts already matching the RFC 6902 shape. DHIS2 does not
        expose a single bulk-PATCH endpoint, so this is client-side
        fan-out over `PATCH /api/<resource>/<uid>` — `concurrency` caps
        simultaneous in-flight requests (default 8, a sensible sweet
        spot against a single DHIS2 node).

        Per-UID failures do not raise — they land in the returned
        `BulkPatchResult.failures`. Call `.ok` for a bool "every patch
        applied" summary, or inspect `.failures` for row-level detail.
        """
        return await self.patch_bulk_multi({resource_type: patches}, concurrency=concurrency)

    async def patch_bulk_multi(
        self,
        by_resource: Mapping[str, Sequence[tuple[str, Sequence[JsonPatchOp | dict[str, Any]]]]],
        *,
        concurrency: int = 8,
    ) -> BulkPatchResult:
        """Apply RFC 6902 patches across multiple resource types in parallel.

        `by_resource` maps each resource type to its `(uid, ops)` pairs;
        every pair across every type runs through the same concurrency
        budget. Resources with empty pair lists are skipped.
        Merges into one `BulkPatchResult`.
        """
        flat: list[tuple[str, str, list[dict[str, Any]]]] = []
        for resource, pairs in by_resource.items():
            for uid, ops in pairs:
                flat.append((resource, uid, _normalise_patch_ops(ops)))
        if not flat:
            return BulkPatchResult()

        semaphore = asyncio.Semaphore(max(1, concurrency))

        async def _one(resource: str, uid: str, ops: list[dict[str, Any]]) -> tuple[str, str, BulkPatchError | None]:
            async with semaphore:
                try:
                    await self._client.patch_raw(f"/api/{resource}/{uid}", body=ops)
                except Dhis2ApiError as exc:
                    return (
                        resource,
                        uid,
                        BulkPatchError(
                            uid=uid,
                            resource=resource,
                            status_code=exc.status_code,
                            message=exc.message,
                        ),
                    )
            return resource, uid, None

        results = await asyncio.gather(*(_one(r, u, o) for r, u, o in flat))
        successful: list[str] = []
        failures: list[BulkPatchError] = []
        for _resource, uid, error in results:
            if error is None:
                successful.append(uid)
            else:
                failures.append(error)
        return BulkPatchResult(successful_uids=successful, failures=failures)

    async def apply_sharing_bulk(
        self,
        resource_type: str,
        uids: Sequence[str],
        sharing: SharingObject | SharingBuilder,
        *,
        concurrency: int = 8,
    ) -> BulkSharingResult:
        """Apply one sharing block to many UIDs of one resource in parallel.

        DHIS2's `/api/sharing` is per-object (one POST per UID). This method
        fans the same `SharingObject` / `SharingBuilder` payload across every
        UID in `uids` under a `concurrency` semaphore (default 8). Useful
        when rolling a single user-group-access pattern across a cohort
        without writing the loop in caller code.

        Per-UID failures do not raise — they land in the returned
        `BulkSharingResult.failures`. Call `.ok` for a bool "every grant
        applied" summary, or inspect `.failures` for row-level detail.
        """
        return await self.apply_sharing_bulk_multi({resource_type: uids}, sharing, concurrency=concurrency)

    async def apply_sharing_bulk_multi(
        self,
        by_resource: Mapping[str, Sequence[str]],
        sharing: SharingObject | SharingBuilder,
        *,
        concurrency: int = 8,
    ) -> BulkSharingResult:
        """Apply one sharing block across multiple resource types in parallel.

        `by_resource` maps each resource type (`"dataSet"`, `"program"`, ...)
        to the UIDs receiving the same sharing payload; every UID across
        every type runs through one `concurrency` budget. Resources with
        empty UID lists are skipped. Merges into one `BulkSharingResult`.
        """
        payload_obj = sharing.to_sharing_object() if isinstance(sharing, SharingBuilder) else sharing
        payload = {"object": payload_obj.model_dump(by_alias=True, exclude_none=True, mode="json")}

        flat: list[tuple[str, str]] = []
        for resource, uids in by_resource.items():
            for uid in uids:
                flat.append((resource, uid))
        if not flat:
            return BulkSharingResult()

        semaphore = asyncio.Semaphore(max(1, concurrency))

        async def _one(resource: str, uid: str) -> tuple[str, str, BulkSharingError | None]:
            async with semaphore:
                try:
                    await self._client.post_raw(
                        "/api/sharing",
                        payload,
                        params={"type": resource, "id": uid},
                    )
                except Dhis2ApiError as exc:
                    return (
                        resource,
                        uid,
                        BulkSharingError(
                            uid=uid,
                            resource=resource,
                            status_code=exc.status_code,
                            message=exc.message,
                        ),
                    )
            return resource, uid, None

        results = await asyncio.gather(*(_one(r, u) for r, u in flat))
        successful: list[str] = []
        failures: list[BulkSharingError] = []
        for _resource, uid, error in results:
            if error is None:
                successful.append(uid)
            else:
                failures.append(error)
        return BulkSharingResult(successful_uids=successful, failures=failures)

    async def dry_run(
        self,
        by_resource: Mapping[str, Sequence[BaseModel | dict[str, Any]]],
        *,
        import_strategy: str = "CREATE_AND_UPDATE",
    ) -> WebMessageResponse:
        """Validate a cross-resource bundle without committing (`importMode=VALIDATE`).

        `by_resource` maps each resource type (e.g. `"dataElements"`,
        `"indicators"`) to the objects that would be imported. Objects can be
        typed pydantic models (auto-dumped via `by_alias + exclude_none`) or
        raw dicts (pass-through). Empty resource entries are skipped.

        Returns the `WebMessageResponse` DHIS2 would have returned on a real
        import — `.import_report().stats` carries the per-type
        created/updated counts; `.conflicts()` lists everything DHIS2 would
        have rejected. Useful as a safety gate in a CI pipeline before a
        real bulk write, or before `delete_bulk` on resources with
        foreign-key dependencies.
        """
        bundle = _bundle_from_by_resource(by_resource)
        if not bundle:
            return WebMessageResponse(
                status=Status.OK, httpStatus="OK", httpStatusCode=200, message="no items supplied"
            )
        raw = await self._client.post_raw(
            "/api/metadata",
            body=bundle,
            params={"importStrategy": import_strategy, "importMode": "VALIDATE"},
        )
        return WebMessageResponse.model_validate(raw)


# Non-metadata keys DHIS2 always includes on an `/api/metadata` response.
# Skip them when enumerating resource sections.
_NON_RESOURCE_KEYS: frozenset[str] = frozenset({"system", "date"})


def _merge_search_results(query: str, per_field: Sequence[SearchResults]) -> SearchResults:
    """OR-merge per-field `SearchResults`, deduplicating by (resource, uid)."""
    merged: dict[str, dict[str, SearchHit]] = {}
    for field_result in per_field:
        for resource, rows in field_result.hits.items():
            slot = merged.setdefault(resource, {})
            for hit in rows:
                slot.setdefault(hit.uid, hit)
    ordered: dict[str, list[SearchHit]] = {
        resource: list(uid_map.values()) for resource, uid_map in sorted(merged.items()) if uid_map
    }
    return SearchResults(query=query, hits=ordered)


_CORE_FIELD_KEYS: frozenset[str] = frozenset({"id", "name", "displayName", "code", "href"})


def _search_results_from_bundle(query: str, bundle: dict[str, Any]) -> SearchResults:
    """Convert a `/api/metadata` bundle response into a typed `SearchResults`.

    Fields beyond the core four (`id` / `name` / `code` / `href`) — anything
    the caller asked for via `fields=...` — land on `SearchHit.extras` so
    consumers can render them without reshaping the response.
    """
    hits: dict[str, list[SearchHit]] = {}
    for resource, rows in bundle.items():
        if resource in _NON_RESOURCE_KEYS or not isinstance(rows, list):
            continue
        resource_hits: list[SearchHit] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            uid = row.get("id")
            if not isinstance(uid, str):
                continue
            extras = {k: v for k, v in row.items() if k not in _CORE_FIELD_KEYS}
            resource_hits.append(
                SearchHit(
                    uid=uid,
                    name=str(row.get("name") or row.get("displayName") or uid),
                    code=row.get("code") if isinstance(row.get("code"), str) else None,
                    resource=resource,
                    href=row.get("href") if isinstance(row.get("href"), str) else None,
                    extras=extras,
                ),
            )
        if resource_hits:
            hits[resource] = resource_hits
    return SearchResults(query=query, hits=hits)


def _bundle_from_by_resource(
    by_resource: Mapping[str, Sequence[BaseModel | dict[str, Any]]],
) -> dict[str, list[dict[str, Any]]]:
    """Normalise a `{resource: [models|dicts]}` map to DHIS2's wire bundle shape."""
    return {
        resource: [
            item.model_dump(by_alias=True, exclude_none=True, mode="json")
            if isinstance(item, BaseModel)
            else dict(item)
            for item in items
        ]
        for resource, items in by_resource.items()
        if items
    }


def _normalise_patch_ops(
    ops: Sequence[JsonPatchOp | dict[str, Any]],
) -> list[dict[str, Any]]:
    """Normalise typed JsonPatchOps / dicts to the RFC 6902 JSON wire shape."""
    return [
        op.model_dump(by_alias=True, exclude_none=True, mode="json") if isinstance(op, BaseModel) else dict(op)
        for op in ops
    ]


__all__ = [
    "BulkPatchError",
    "BulkPatchResult",
    "BulkSharingError",
    "BulkSharingResult",
    "MetadataAccessor",
    "SearchHit",
    "SearchResults",
]
