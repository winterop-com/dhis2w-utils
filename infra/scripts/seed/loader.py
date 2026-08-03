"""Typed-model loader for the Sierra Leone immunization fixture snapshot.

See `infra/scripts/seed/__init__.py` for the high-level shape. This
module is the mechanical side: read the JSON fixtures off disk, rehydrate
into the matching generated pydantic models (for type-safety + client
validation), POST through the normal DHIS2 metadata importer, then stream
the aggregate data values + tracker payload.

Keep the module order-agnostic: DHIS2's `/api/metadata` importer handles
the dependency graph server-side as long as every referenced UID is
present in the bundle. That means we don't need to topo-sort sections
on the client — just validate + submit.
"""

from __future__ import annotations

import gzip
import json
import os
import time
from pathlib import Path
from typing import Any

from dhis2w_client import DataValue, WebMessageResponse
from dhis2w_client.errors import Dhis2ApiError
from dhis2w_client.generated.v42.oas import TrackerImportReport
from dhis2w_client.generated.v42.schemas import (
    Category,
    CategoryCombo,
    CategoryOption,
    Dashboard,
    DataElement,
    DataSet,
    Indicator,
    Map,
    OptionSet,
    OrganisationUnit,
    Program,
    ProgramRule,
    ProgramRuleAction,
    ProgramRuleVariable,
    ProgramStage,
    TrackedEntityAttribute,
    TrackedEntityType,
    Visualization,
)
from dhis2w_client.v42.client import Dhis2Client
from pydantic import BaseModel, ConfigDict

_SEED_START_MONOTONIC = time.monotonic()


def _log(message: str) -> None:
    """Print `message` prefixed with wall-clock time + elapsed-since-start."""
    elapsed = time.monotonic() - _SEED_START_MONOTONIC
    print(f"[{time.strftime('%H:%M:%S')}  +{elapsed:6.1f}s] {message}", flush=True)


def _fixture_dir() -> Path:
    """Return `infra/fixtures/v{N}/play` for the active DHIS2 major.

    Each major has its own fixture directory so v41 / v42 / v43 can carry
    version-specific shapes (different metadata structure, different
    AOC values, different period coverage) without a runtime-branching
    seed loader. The `DHIS2_VERSION` env var picks the major; defaults
    to v42 to match the historical baseline.
    """
    version = os.environ.get("DHIS2_VERSION", "v42")
    return Path(__file__).resolve().parents[2] / "fixtures" / version / "play"


FIXTURE_DIR = _fixture_dir()
SIERRA_LEONE_ROOT_UID = "ImspTQPwCqd"

# Sections we skip at JSON-import time — rebuilt programmatically in the
# seed flow so the client's typed builders (rather than the play snapshot)
# are the source of truth.
# - `visualizations`: re-authored via `VisualizationSpec` with Sierra Leone
#   DEs + 2024 monthly periods (see `seed.visualizations`).
# - `maps`: re-authored via `MapSpec` / `MapLayerSpec` with Sierra Leone DEs
#   and the single available `Immunization Coverage` legend set so the
#   choropleth actually renders against our 1-year data window
#   (see `seed.maps`). Pulling the original map JSON in was giving
#   blank tiles since half the referenced indicators aren't transitively
#   imported and the periods were frozen to `2024` / `2025` strings DHIS2
#   couldn't resolve against the rolling windows the UI expects.
_SKIP_SECTIONS: frozenset[str] = frozenset({"visualizations", "maps"})

# Sections we import in a dedicated LATER pass, after the programmatic viz
# + map build has run. Dashboards reference visualization and map UIDs —
# if we import them in the core pass before the vizes + maps exist, every
# dashboard item comes out as a dangling ref. Kept on the bundle but
# deferred until vizes + maps are live.
_POST_VIZ_SECTIONS: frozenset[str] = frozenset({"dashboards"})


# Map each metadata section to its typed model. Sections not listed here
# flow through as dicts (the `/api/metadata` importer doesn't care, and
# we don't have generated models for every DHIS2 resource type — e.g.
# `categoryOptionCombos`, `dataEntryForms`, `notificationTemplates`).
_TYPED_SECTIONS: dict[str, type[Any]] = {
    "organisationUnits": OrganisationUnit,
    "dataElements": DataElement,
    "dataSets": DataSet,
    "categories": Category,
    "categoryCombos": CategoryCombo,
    "categoryOptions": CategoryOption,
    "optionSets": OptionSet,
    "indicators": Indicator,
    "programs": Program,
    "programStages": ProgramStage,
    "programRules": ProgramRule,
    "programRuleActions": ProgramRuleAction,
    "programRuleVariables": ProgramRuleVariable,
    "trackedEntityAttributes": TrackedEntityAttribute,
    "trackedEntityTypes": TrackedEntityType,
    "dashboards": Dashboard,
    "visualizations": Visualization,
    "maps": Map,
}


def _load_json(path: Path) -> Any:
    """Read a JSON file + return the decoded payload."""
    return json.loads(path.read_text(encoding="utf-8"))


def _load_gzip_json(path: Path) -> Any:
    """Read a gzipped JSON file + return the decoded payload."""
    with gzip.open(path, "rb") as f:
        return json.loads(f.read().decode("utf-8"))


_STRIP_KEYS: frozenset[str] = frozenset(
    {
        # User / sharing refs — point at Sierra Leone accounts we don't
        # curate. Cleaning these is a common pattern when porting DHIS2
        # metadata between instances; the locally-created admin takes
        # over as de-facto owner after import. Smaller metadata too.
        "userAccesses",
        "userGroupAccesses",
        "user",
        "createdBy",
        "lastUpdatedBy",
        "notificationRecipients",
        "recipientUserGroup",
        "recipientUserGroups",
        # Computed / read-only fields that leak into `/api/.../metadata`
        # responses and confuse the importer — Hibernate tries to flush
        # them as first-class entities and fails on missing parent refs.
        "compulsoryDataElementOperands",
        "displayName",
        "displayShortName",
        "displayFormName",
        "displayDescription",
        "displayTitle",
        "displaySubtitle",
        "displayBaseLineLabel",
        "displayTargetLineLabel",
        "displayDomainAxisLabel",
        "displayRangeAxisLabel",
        "access",
        "favorite",
        "favorites",
        "subscribed",
        "subscribers",
        "interpretations",
        "translations",
        "href",
    },
)

# Uniform sharing block applied to every imported object so references to
# DHIS2 Play's users + groups don't reach the importer. Public read/write
# keeps the seed self-contained; the locally-created admin takes ownership
# via createdBy/lastUpdatedBy auto-population on write.
_DEFAULT_SHARING: dict[str, Any] = {
    "public": "rwrw----",
    "external": False,
    "users": {},
    "userGroups": {},
}


def _strip_dataset_self_refs(row: dict[str, Any]) -> dict[str, Any]:
    """Drop the self-referencing `dataSet` field from `dataSetElements`.

    Play's `/api/dataSets/{uid}/metadata` embeds
    `dataSetElements[].dataSet = {id: <parent>}`. DHIS2's importer treats
    each nested ref as a lazy proxy with no `periodType`, then Hibernate
    fails the whole flush with
    `PropertyValueException: not-null property references a null or
    transient value : org.hisp.dhis.dataset.DataSet.periodType` on a
    fresh stack. DHIS2 infers the parent from context so dropping the
    explicit back-ref is safe.
    """
    dse = row.get("dataSetElements")
    if not isinstance(dse, list):
        return row
    cleaned_items: list[dict[str, Any]] = []
    for entry in dse:
        if isinstance(entry, dict):
            cleaned_items.append({k: v for k, v in entry.items() if k != "dataSet"})
    copy = dict(row)
    copy["dataSetElements"] = cleaned_items
    return copy


def _strip_sharing(row: dict[str, Any]) -> dict[str, Any]:
    """Strip user-based sharing + computed fields + replace the sharing block.

    Common DHIS2 porting pattern: when migrating metadata between instances
    the source's users, user groups, createdBy / lastUpdatedBy, sharing
    arrays all reference identities that don't exist on the target. Scrub
    them aggressively and set a canonical `sharing` block so the
    locally-created admin becomes the de-facto owner after import.
    """
    cleaned: dict[str, Any] = {"sharing": dict(_DEFAULT_SHARING)}
    for key, value in row.items():
        if key in _STRIP_KEYS:
            continue
        if key == "sharing":
            # Replaced with _DEFAULT_SHARING above; skip the original.
            continue
        cleaned[key] = value
    return cleaned


def _strip_nested_sharing(rows: list[Any]) -> list[Any]:
    """Apply `_strip_sharing` + `_strip_dataset_self_refs` through rows."""
    out: list[Any] = []
    for row in rows:
        if hasattr(row, "model_dump"):
            dumped = row.model_dump(by_alias=True, exclude_none=True, mode="json")
            if isinstance(dumped, dict):
                out.append(_strip_dataset_self_refs(_strip_sharing(dumped)))
                continue
        if isinstance(row, dict):
            out.append(_strip_dataset_self_refs(_strip_sharing(row)))
            continue
        out.append(row)
    return out


def _merge_geometry_onto_org_units(
    org_units: list[dict[str, Any]],
    feature_collection: dict[str, Any],
) -> list[dict[str, Any]]:
    """Attach `geometry` to each OU row by matching feature.id."""
    by_id: dict[str, dict[str, Any]] = {}
    for feature in feature_collection.get("features") or []:
        uid = feature.get("id")
        if isinstance(uid, str):
            by_id[uid] = feature.get("geometry")
    result: list[dict[str, Any]] = []
    for ou in org_units:
        uid = ou.get("id")
        if isinstance(uid, str) and uid in by_id:
            result.append({**ou, "geometry": by_id[uid]})
        else:
            result.append(ou)
    return result


class MetadataBundleSummary(BaseModel):
    """Per-section row counts for a freshly-loaded metadata bundle."""

    model_config = ConfigDict(frozen=True)

    section_counts: dict[str, int]

    @classmethod
    def from_bundle(cls, bundle: dict[str, list[Any]]) -> MetadataBundleSummary:
        """Build the summary by counting rows in each section of `bundle`."""
        return cls(section_counts={section: len(rows) for section, rows in bundle.items()})

    @property
    def total(self) -> int:
        """Total row count across every section."""
        return sum(self.section_counts.values())

    def render(self) -> str:
        """Return a human-friendly multi-line representation, sorted by descending row count."""
        widest = max((len(name) for name in self.section_counts), default=0)
        lines = []
        for section, count in sorted(self.section_counts.items(), key=lambda item: (-item[1], item[0])):
            lines.append(f"      {section:<{widest}}  {count:>5}")
        lines.append(f"      {'TOTAL':<{widest}}  {self.total:>5}")
        return "\n".join(lines)


def load_metadata() -> dict[str, list[Any]]:
    """Read fixtures off disk + rehydrate into typed generated models.

    Returns a dict keyed by DHIS2 resource section name. Each value is a
    list of typed pydantic models (or dicts for sections not in
    `_TYPED_SECTIONS`). The return shape is directly consumable by
    `import_metadata_bundle` — no further massaging required.
    """
    bundle = _load_json(FIXTURE_DIR / "metadata.json")
    org_units = _load_json(FIXTURE_DIR / "organisation_units.json")
    geometry = _load_json(FIXTURE_DIR / "geometry.geojson")
    # Attach geometry to OUs + fold into the main bundle under the
    # canonical "organisationUnits" key.
    bundle["organisationUnits"] = _merge_geometry_onto_org_units(org_units, geometry)
    typed: dict[str, list[Any]] = {}
    for section, rows in bundle.items():
        if not isinstance(rows, list):
            continue
        model = _TYPED_SECTIONS.get(section)
        if model is None:
            # Pass untyped sections through — the importer still accepts them.
            typed[section] = [row for row in rows if isinstance(row, dict)]
            continue
        validated: list[Any] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            validated.append(model.model_validate(row))
        typed[section] = validated
    return typed


def _dump_section(rows: list[Any]) -> list[dict[str, Any]]:
    """Dump typed models back to JSON-friendly dicts for the /api/metadata post."""
    out: list[dict[str, Any]] = []
    for row in rows:
        if hasattr(row, "model_dump"):
            dumped = row.model_dump(by_alias=True, exclude_none=True, mode="json")
            if isinstance(dumped, dict):
                out.append(dumped)
                continue
        if isinstance(row, dict):
            out.append(row)
    return out


_DISAMBIGUATE_SECTIONS: frozenset[str] = frozenset(
    {"trackedEntityTypes", "trackedEntityAttributes"},
)


def _disambiguate_common_names(section: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Append a " (Play)" suffix to TET + TEA names so they don't collide with DHIS2 built-ins.

    A fresh DHIS2 install ships with a "Person" TrackedEntityType and
    "First name" / "Last name" TrackedEntityAttributes whose UIDs differ
    from play's. Name + shortName are UNIQUE in DHIS2, so importing our
    copies fails `E5003`. The suffix side-steps the collision without
    touching any UID references downstream.
    """
    if section not in _DISAMBIGUATE_SECTIONS:
        return rows
    out: list[dict[str, Any]] = []
    for row in rows:
        copy = dict(row)
        for field in ("name", "shortName", "displayName"):
            value = copy.get(field)
            if isinstance(value, str) and not value.endswith(" (Play)"):
                copy[field] = f"{value} (Play)"
        out.append(copy)
    return out


# OU-tree sections come first + on their own — the fresh DHIS2 admin
# has no OU scope until we attach the country root, and scope has to
# be in place before any data-value / tracker writes (see BUGS.md #26).
_OU_FIRST_SECTIONS: frozenset[str] = frozenset(
    {"organisationUnitGroups", "organisationUnitGroupSets", "organisationUnits"},
)

# DataSets + Sections + DataEntryForms land in the LAST pass — the
# Hibernate quirk documented in BUGS.md #23 prevents them from
# importing alongside their dependencies in one transaction.
_DEFERRED_SECTIONS: frozenset[str] = frozenset(
    {"dataSets", "sections", "dataEntryForms"},
)


async def _post_metadata(
    client: Dhis2Client,
    payload: dict[str, list[Any]],
    *,
    max_attempts: int = 3,
    retry_delay_seconds: float = 8.0,
) -> WebMessageResponse:
    """POST one bundle to `/api/metadata` with flakiness retry.

    Fresh DHIS2 installs sometimes hit timing bugs on the first
    few imports (see BUGS.md #27). Retry with a short delay — usually
    the second or third attempt succeeds against the same payload.
    """
    import asyncio as _asyncio  # noqa: PLC0415

    last_error: Dhis2ApiError | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            raw = await client.post_raw(
                "/api/metadata",
                payload,
                params={
                    "importStrategy": "CREATE_AND_UPDATE",
                    "atomicMode": "OBJECT",
                    "flushMode": "OBJECT",
                    # Match existing metadata by CODE rather than UID during
                    # the preheat — fixes the "default" Category /
                    # CategoryCombo collision on a fresh DHIS2 install (both
                    # ours + DHIS2's built-ins share code="default" but
                    # have different UIDs).
                    "preheatIdentifier": "CODE",
                    "skipSharing": "true",
                },
            )
            return WebMessageResponse.model_validate(raw)
        except Dhis2ApiError as exc:
            last_error = exc
            if attempt == max_attempts:
                break
            print(
                f"    metadata POST attempt {attempt} failed ({exc.status_code}); "
                f"retrying in {retry_delay_seconds:.0f}s",
                flush=True,
            )
            await _asyncio.sleep(retry_delay_seconds)
    assert last_error is not None
    raise last_error


def _build_pass(
    bundle: dict[str, list[Any]],
    predicate: Any,
) -> dict[str, list[dict[str, Any]]]:
    """Strip + disambiguate + dump every section matching `predicate`."""
    return {
        section: _disambiguate_common_names(section, _strip_nested_sharing(_dump_section(rows)))
        for section, rows in bundle.items()
        if rows and predicate(section)
    }


async def import_ou_tree(
    client: Dhis2Client,
    bundle: dict[str, list[Any]],
) -> WebMessageResponse | None:
    """Post the OU pass (`organisationUnits` + groups + group sets).

    Runs first so admin can be attached to the country root before any
    data-write endpoint is touched (BUGS.md #26).
    """
    payload = _build_pass(bundle, lambda section: section in _OU_FIRST_SECTIONS)
    if not payload:
        return None
    return await _post_metadata(client, payload)


async def import_core_metadata(
    client: Dhis2Client,
    bundle: dict[str, list[Any]],
) -> WebMessageResponse | None:
    """Post everything except the OU pass, deferred DataSets, and skipped sections.

    Data elements, categories, option sets, indicators, programs, program
    rules, TEAs/TETs, maps — all land here in a single request. DHIS2's
    importer resolves the cross-refs server-side.

    Visualizations are explicitly skipped (`_SKIP_SECTIONS`) — they're
    rebuilt programmatically via the client's `VisualizationSpec` builder
    in a separate pass (see `seed.visualizations.build_dashboard_visualizations`).
    """
    payload = _build_pass(
        bundle,
        lambda section: (
            section not in _OU_FIRST_SECTIONS
            and section not in _DEFERRED_SECTIONS
            and section not in _SKIP_SECTIONS
            and section not in _POST_VIZ_SECTIONS
        ),
    )
    if not payload:
        return None
    return await _post_metadata(client, payload)


async def import_post_viz_metadata(
    client: Dhis2Client,
    bundle: dict[str, list[Any]],
) -> WebMessageResponse | None:
    """Post dashboards (and anything else held for after the viz build).

    Dashboards reference visualization UIDs; if imported before the
    programmatic viz pass runs, every dashboard item resolves to a
    dangling ref. Runs after `build_dashboard_visualizations` so the
    dashboard items land on freshly-created viz records.
    """
    payload = _build_pass(bundle, lambda section: section in _POST_VIZ_SECTIONS)
    if not payload:
        return None
    return await _post_metadata(client, payload)


async def import_deferred_metadata(
    client: Dhis2Client,
    bundle: dict[str, list[Any]],
) -> WebMessageResponse | None:
    """Post the deferred DataSet + Section + DataEntryForm sections.

    Run last because DHIS2 trips a Hibernate flush error when these are
    imported in the same transaction as their dependencies (BUGS.md #23).
    """
    payload = _build_pass(bundle, lambda section: section in _DEFERRED_SECTIONS)
    if not payload:
        return None
    return await _post_metadata(client, payload)


async def import_metadata_bundle(
    client: Dhis2Client,
    bundle: dict[str, list[Any]],
    *,
    atomic_mode: str = "OBJECT",  # retained for back-compat; routed through _post_metadata
) -> WebMessageResponse:
    """Convenience wrapper: run all three passes in order with no admin-scope gate.

    Suitable for tests that only need metadata in place. The full seed
    (`seed_play`) calls the three pass helpers directly so it can slot
    `assign_admin_to_sierra_leone` between the OU pass and the core pass.
    """
    del atomic_mode  # noqa: F841 — kept in signature for back-compat
    ou_response = await import_ou_tree(client, bundle)
    core_response = await import_core_metadata(client, bundle)
    await import_deferred_metadata(client, bundle)
    response = core_response or ou_response
    if response is None:
        raise RuntimeError("metadata bundle was empty — nothing to import")
    return response


# Chunk size for `/api/dataValueSets` POSTs. v41 + v42 happily accept
# 10 k-row chunks in seconds; v43's stricter validation (per-DE category
# combo cross-check, plus the auto-target validator from BUGS.md #35)
# pushes a single 10 k-row chunk past 5 minutes under linux/amd64
# emulation on arm64 macOS — which times out the httpx read deadline.
# 1 k strikes the balance: each chunk completes in ~5-10 s on v43, total
# import takes ~3-4 minutes for the 188 k Sierra Leone fixture, well
# inside the 300 s read timeout.
_DATA_VALUE_CHUNK: int = 1_000


async def _build_dataelement_to_dataset(client: Dhis2Client) -> dict[str, str]:
    """Map every data-element id to one of the datasets that contain it.

    DHIS2 v43 added auto-target validation on `/api/dataValueSets`
    (BUGS.md #35) — posts without an envelope `dataSet` get rejected
    when a DE is referenced by multiple datasets. The fix is to scope
    each chunk to a single dataset, which v41 + v42 also accept.

    For DEs in multiple datasets we pick the lexicographically-first
    id so the choice is deterministic across runs.
    """
    raw = await client.get_raw(
        "/api/dataSets",
        params={"fields": "id,dataSetElements[dataElement[id]]", "paging": "false"},
    )
    members: dict[str, list[str]] = {}
    for dataset in raw.get("dataSets") or []:
        dataset_id = dataset.get("id")
        if not isinstance(dataset_id, str):
            continue
        for entry in dataset.get("dataSetElements") or []:
            element = (entry.get("dataElement") or {}).get("id")
            if isinstance(element, str):
                members.setdefault(element, []).append(dataset_id)
    return {element_id: sorted(dataset_ids)[0] for element_id, dataset_ids in members.items()}


async def import_data_values(client: Dhis2Client) -> WebMessageResponse:
    """Stream the gzipped aggregate data values into `/api/dataValueSets` in chunks.

    188 k values in a single POST blows past the client's default 30 s
    read timeout on a fresh stack. Chunk into 10 k-row batches grouped by
    dataset — each chunk POSTs `{"dataSet": "<id>", "dataValues": [...]}`
    so DHIS2 v43's auto-target validator (BUGS.md #26) accepts the import.

    Every row still round-trips through `DataValue.model_validate` so the
    typed shape is exercised on all 188 k rows.
    """
    raw_bundle = _load_gzip_json(FIXTURE_DIR / "data_values.json.gz")
    data_values = raw_bundle.get("dataValues") or []
    validated = [DataValue.model_validate(dv) for dv in data_values if isinstance(dv, dict)]
    dataelement_to_dataset = await _build_dataelement_to_dataset(client)
    grouped: dict[str, list[dict[str, Any]]] = {}
    skipped_no_dataset = 0
    for value in validated:
        if value.dataElement is None:
            skipped_no_dataset += 1
            continue
        dataset_id = dataelement_to_dataset.get(value.dataElement)
        if dataset_id is None:
            skipped_no_dataset += 1
            continue
        grouped.setdefault(dataset_id, []).append(
            value.model_dump(by_alias=True, exclude_none=True, mode="json"),
        )
    if skipped_no_dataset:
        print(f"    skipped {skipped_no_dataset} values with no matching dataset", flush=True)

    total_imported = 0
    total_updated = 0
    total_ignored = 0
    last_response: WebMessageResponse | None = None
    for dataset_id, dumped in grouped.items():
        for start in range(0, len(dumped), _DATA_VALUE_CHUNK):
            chunk = dumped[start : start + _DATA_VALUE_CHUNK]
            try:
                # `force=true` bypasses dataset-level expiryDays + openPeriodsAfterCoEndDate
                # checks. Required because the play fixture is historical (2024) data and
                # several datasets have closed entry windows for those periods. Admin
                # carries F_EDIT_EXPIRED + F_EDIT_FUTURE_PERIODS authorities so the
                # endpoint accepts the override.
                raw = await client.post_raw(
                    "/api/dataValueSets",
                    body={"dataSet": dataset_id, "dataValues": chunk},
                    params={"force": "true"},
                )
            except Dhis2ApiError as exc:
                # DHIS2 returns 409 even on partial success (e.g. a handful of
                # non-numeric values on play for numeric DEs — play data drift).
                # Treat 409 with a structured body as "warning" — extract the
                # import counts and keep going.
                if exc.status_code != 409 or not isinstance(exc.body, dict):
                    raise
                raw = exc.body
            last_response = WebMessageResponse.model_validate(raw)
            counts = last_response.import_count()
            if counts is not None:
                total_imported += counts.imported or 0
                total_updated += counts.updated or 0
                total_ignored += counts.ignored or 0
    if last_response is None:
        raise RuntimeError("no data values to import")
    # Synthesise a summary envelope so seed_play's reporting shows totals.
    summary_raw = {
        "status": last_response.status,
        "importCount": {
            "imported": total_imported,
            "updated": total_updated,
            "ignored": total_ignored,
            "deleted": 0,
        },
    }
    return WebMessageResponse.model_validate(summary_raw)


async def assign_admin_to_sierra_leone(client: Dhis2Client) -> None:
    """Attach the Sierra Leone root to admin's capture + view + search scopes.

    Without this, data-value + tracker writes fail with
    E7617 "Organisation unit not in hierarchy of current user". Called
    from `seed_play` after metadata import (so the root OU exists) and
    before any data-values / tracker write.

    Uses PUT-replace on the user resource rather than JSON Patch — the
    patch endpoint's shape varies across DHIS2 minors, but the full
    user PUT is stable.
    """
    me_raw = await client.get_raw(f"/api/users/{(await client.system.me()).id}")
    if not me_raw.get("id"):
        raise RuntimeError("admin user has no id — DHIS2 bootstrap not ready")
    root_ref = {"id": SIERRA_LEONE_ROOT_UID}
    me_raw["organisationUnits"] = [root_ref]
    me_raw["dataViewOrganisationUnits"] = [root_ref]
    me_raw["teiSearchOrganisationUnits"] = [root_ref]
    await client.put_raw(f"/api/users/{me_raw['id']}", me_raw)


async def attach_admin_to_datasets_and_programs(
    client: Dhis2Client,
    bundle: dict[str, list[Any]],
) -> None:
    """Grant admin capture access to every imported DataSet + Program.

    DHIS2's user record carries explicit `dataSets` + `programs` arrays
    alongside the organisationUnits capture scope. On a fresh install
    admin starts with neither, so Data Entry + Tracker Capture apps
    land on an empty picker until the arrays are populated. Called at
    the end of the seed, matching the DHIS2 bootstrap order:

        1) create OUs
        2) attach admin to root
        3) import metadata
        4) attach datasets + programs to admin   <-- here
    """
    dataset_ids = [row.id for row in bundle.get("dataSets") or [] if getattr(row, "id", None)]
    program_ids = [row.id for row in bundle.get("programs") or [] if getattr(row, "id", None)]
    if not dataset_ids and not program_ids:
        return
    me_id = (await client.system.me()).id
    me_raw = await client.get_raw(f"/api/users/{me_id}")
    if dataset_ids:
        me_raw["dataSets"] = [{"id": uid} for uid in dataset_ids]
    if program_ids:
        me_raw["programs"] = [{"id": uid} for uid in program_ids]
    await client.put_raw(f"/api/users/{me_id}", me_raw)


async def import_tracker(client: Dhis2Client) -> TrackerImportReport:
    """POST the sampled Child Programme tracker payload.

    The wire payload round-trips as dict because the input fixture lacks
    many of `TrackerBundle`'s optional fields (the seed isn't producing
    a full bundle, just the trackedEntities slice). The response from
    `/api/tracker` is parsed into the typed `TrackerImportReport` so
    callers see structured per-type stats instead of a verbose dict.
    """
    raw_bundle = _load_gzip_json(FIXTURE_DIR / "tracker_payload.json.gz")
    tes = raw_bundle.get("trackedEntities") or []
    body = {"trackedEntities": tes}
    raw = await client.post_raw(
        "/api/tracker",
        body=body,
        params={
            "importStrategy": "CREATE_AND_UPDATE",
            "atomicMode": "OBJECT",
            "async": "false",
        },
    )
    return TrackerImportReport.model_validate(raw)


def _print_tracker_report(report: TrackerImportReport) -> None:
    """Print one compact line per tracker type + grouped error summary.

    DHIS2's `/api/tracker` always emits a typeReportMap entry for each
    of the four tracker types (TRACKED_ENTITY / ENROLLMENT / EVENT /
    RELATIONSHIP), even when the request didn't include any of that
    type. Empty types print as `0 0 0 0` so the import shape is always
    visible.

    Rejection reasons live in `report.validationReport.errorReports`
    (the per-object `objectReports[].errorReports` only carry diagnostics
    for *successful* entities). Group them by `errorCode + trackerType`
    and print one summary line per group plus a sample message.
    """
    bundle = report.bundleReport
    type_map = bundle.typeReportMap if bundle else None
    if type_map:
        for tracker_type, type_report in type_map.items():
            stats = type_report.stats
            if stats is None:
                continue
            print(
                f"    {tracker_type:14s}  created={stats.created or 0:>4}  "
                f"updated={stats.updated or 0:>4}  ignored={stats.ignored or 0:>4}  "
                f"total={stats.total or 0:>4}",
                flush=True,
            )
    elif report.message:
        print(f"    tracker: {report.message}", flush=True)
        return

    # Group rejection reasons.
    if report.validationReport and report.validationReport.errorReports:
        groups: dict[tuple[str, str], list[str]] = {}
        for err in report.validationReport.errorReports:
            key = (err.errorCode or "?", err.trackerType or "?")
            groups.setdefault(key, []).append(err.message or "")
        if groups:
            print("    rejections:", flush=True)
            for (code, tracker_type), messages in sorted(groups.items(), key=lambda item: -len(item[1])):
                sample = messages[0]
                # Trim repetitive `«:` paths from the end of the message
                if len(sample) > 110:
                    sample = sample[:107] + "..."
                print(f"      {code:>6}  {tracker_type:14s}  x{len(messages):<4}  {sample}", flush=True)


def _print_counts(label: str, response: WebMessageResponse | None) -> None:
    """Print the importCount block from a DHIS2 WebMessage if present."""
    if response is None:
        return
    counts = response.import_count()
    if counts is None:
        return
    print(
        f"    {label}: imported={counts.imported}  updated={counts.updated}  "
        f"ignored={counts.ignored}  deleted={counts.deleted}",
        flush=True,
    )


async def seed_play(client: Dhis2Client) -> None:
    """End-to-end seed following DHIS2's required bootstrap order.

    Steps:
      1. Load + type-validate every fixture off disk.
      2. Import the OU tree (root + all 1332 org units).
      3. Assign admin to the Sierra Leone root across every scope
         (organisationUnits / dataViewOrganisationUnits /
         teiSearchOrganisationUnits). Reconnect the client so the
         session's cached OU scope refreshes (BUGS.md #26).
      4. Import everything except DataSets + Sections + DataEntryForms.
      5. Import the deferred DataSet trio on its own (BUGS.md #23).
      6. Import the aggregate data values (chunked).
      7. Import the tracker sample.
      8. Attach the imported datasets + programs to the admin user so
         Data Entry + Tracker Capture pickers are populated on login.
    """
    _log(">>> Loading typed metadata bundle")
    bundle = load_metadata()
    summary = MetadataBundleSummary.from_bundle(bundle)
    print(summary.render(), flush=True)

    _log(">>> Importing OU tree (pass 1/3)")
    _print_counts("ou", await import_ou_tree(client, bundle))

    _log(">>> Assigning admin to Sierra Leone OU scope")
    await assign_admin_to_sierra_leone(client)
    # DHIS2 caches OU scope per session — reconnect so the following
    # writes pick up the new scope (BUGS.md #26).
    await client.close()
    await client.connect()

    _log(">>> Importing core metadata (pass 2/3)")
    _print_counts("core", await import_core_metadata(client, bundle))

    # Workspace fixtures land BEFORE visualizations + maps because the
    # seeded LegendSet (LsDoseBand1) is referenced by two of the bar-chart
    # specs — DHIS2 rejects the viz POST with a 409 if the LegendSet UID
    # doesn't resolve yet. Everything else in workspace_fixtures is
    # independent of the viz / map layer, so the reorder is safe.
    print(
        ">>> Building workspace fixtures (SNOMED attribute + VACCINE_TYPE option set + "
        "SqlViews + BCG predictors + PredictorGroup + OU levels + BCG validation rules + "
        "dose-count legend set)",
        flush=True,
    )
    from .workspace_fixtures import build_workspace_fixtures  # noqa: PLC0415

    fixture_count = await build_workspace_fixtures(client)
    print(f"    workspace fixtures: {fixture_count} objects", flush=True)

    _log(">>> Building visualizations via VisualizationSpec")
    from .visualizations import build_dashboard_visualizations  # noqa: PLC0415

    viz_count = await build_dashboard_visualizations(client)
    print(f"    built {viz_count} visualizations", flush=True)

    _log(">>> Building maps via MapSpec")
    from .maps import build_dashboard_maps  # noqa: PLC0415

    map_count = await build_dashboard_maps(client)
    print(f"    built {map_count} maps", flush=True)

    _log(">>> Importing dashboards (reference freshly-built vizes)")
    _print_counts("dashboards", await import_post_viz_metadata(client, bundle))

    _log(">>> Importing deferred DataSet / Section / DataEntryForm (pass 3/3)")
    _print_counts("deferred", await import_deferred_metadata(client, bundle))

    _log(">>> Building supervision-visit event program")
    from .event_program import build_event_program  # noqa: PLC0415

    event_program_uid = await build_event_program(client)
    print(f"    event program: {event_program_uid}", flush=True)

    _log(">>> Importing aggregate data values")
    _print_counts("data values", await import_data_values(client))

    _log(">>> Importing Child Programme tracker sample")
    _print_tracker_report(await import_tracker(client))

    _log(">>> Attaching imported DataSets + Programs to admin")
    await attach_admin_to_datasets_and_programs(client, bundle)
