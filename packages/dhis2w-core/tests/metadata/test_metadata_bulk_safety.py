"""Data-safety behavior of the metadata bulk verbs, parametrised over all three version trees.

Covers the guardrails that keep bulk operations from destroying data:
empty strip strings on `rename`, read-merge-write sharing on `share`,
bundle narrowing on `merge-bundle`, empty-selection rejection on
`diff --live`, `legend_set_uids=[]` preview accuracy on `retag`, and the
typed group-set member-count view.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from importlib import import_module
from types import ModuleType
from typing import Any

import httpx
import pytest
import respx

_BASE_URL = "https://dhis2.example"


def _sharing_payload(request: httpx.Request) -> dict[str, Any]:
    """Decode the `{"object": {...}}` body of a `POST /api/sharing` request."""
    body = json.loads(request.content)
    assert isinstance(body, dict)
    payload = body.get("object")
    assert isinstance(payload, dict)
    return payload


# ---------------------------------------------------------------------------
# Bug 1 — empty strip strings on `metadata rename`
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "strip_flag",
    ["name_strip_prefix", "name_strip_suffix", "short_name_strip_prefix", "short_name_strip_suffix"],
)
async def test_bulk_rename_rejects_empty_strip_values(
    core_profile: None,  # noqa: ARG001
    plugin_service: Callable[[str], ModuleType],
    strip_flag: str,
) -> None:
    """An empty strip string would wipe every matched label — rejected before any HTTP call."""
    service = plugin_service("metadata")

    from dhis2w_core.profile import resolve_profile

    profile = resolve_profile("probe")
    with pytest.raises(service.MetadataUsageError, match="non-empty"):
        await service.bulk_rename_metadata(profile, "dataElements", **{strip_flag: ""})


async def test_metadata_usage_error_renders_cleanly(plugin_service: Callable[[str], ModuleType]) -> None:
    """`MetadataUsageError` is a LookupError so `run_app` renders it (exit 1, no traceback)."""
    service = plugin_service("metadata")
    assert issubclass(service.MetadataUsageError, LookupError)


# ---------------------------------------------------------------------------
# Bug 1b — a no-filter live rename/retag would mutate the whole catalog
# ---------------------------------------------------------------------------


async def test_bulk_rename_refuses_no_filter_live_mutation(
    core_profile: None,  # noqa: ARG001
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """A live rename with no filter targets the whole catalog — refused before any HTTP call."""
    service = plugin_service("metadata")

    from dhis2w_core.profile import resolve_profile

    with pytest.raises(service.MetadataUsageError, match="no filter"):
        await service.bulk_rename_metadata(resolve_profile("probe"), "dataElements", name_prefix="[X] ")


async def test_bulk_retag_refuses_no_filter_live_mutation(
    core_profile: None,  # noqa: ARG001
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """A live retag with no filter targets the whole catalog — refused before any HTTP call."""
    service = plugin_service("metadata")

    from dhis2w_core.profile import resolve_profile

    with pytest.raises(service.MetadataUsageError, match="no filter"):
        await service.bulk_retag_metadata(resolve_profile("probe"), "dataElements", category_combo_uid="ccNew00001")


@respx.mock
async def test_bulk_rename_no_filter_dry_run_is_allowed(
    core_version: str,
    core_profile: None,  # noqa: ARG001
    plugin_service: Callable[[str], ModuleType],
    mock_system_info: Callable[..., None],
) -> None:
    """A no-filter dry-run is a safe preview — it must not be refused."""
    service = plugin_service("metadata")
    mock_system_info(core_version)
    respx.get(f"{_BASE_URL}/api/dataElements").mock(
        return_value=httpx.Response(200, json={"dataElements": [{"id": "DE_A", "name": "ANC"}]}),
    )

    from dhis2w_core.profile import resolve_profile

    result = await service.bulk_rename_metadata(
        resolve_profile("probe"),
        "dataElements",
        name_prefix="[X] ",
        dry_run=True,
    )
    assert result.dry_run is True
    assert result.matched == 1


# ---------------------------------------------------------------------------
# Bug 2 — `metadata share` merges into existing sharing instead of replacing it
# ---------------------------------------------------------------------------

_EXISTING_SHARING = {
    "meta": {"allowPublicAccess": True, "allowExternalAccess": False},
    "object": {
        "id": "DS_A",
        "publicAccess": "rw------",
        "externalAccess": False,
        "user": {"id": "OWNER_UID"},
        "userAccesses": [{"id": "U_OLD", "access": "r-------"}],
        "userGroupAccesses": [{"id": "UG_OLD", "access": "rw------"}],
    },
}


@respx.mock
async def test_bulk_share_merges_existing_grants_on_apply(
    core_version: str,
    core_profile: None,  # noqa: ARG001
    plugin_service: Callable[[str], ModuleType],
    mock_system_info: Callable[..., None],
) -> None:
    """Applying a new grant preserves the current publicAccess + every existing grant."""
    service = plugin_service("metadata")
    mock_system_info(core_version)
    respx.get(f"{_BASE_URL}/api/sharing", params={"type": "dataSet", "id": "DS_A"}).mock(
        return_value=httpx.Response(200, json=_EXISTING_SHARING),
    )
    post_route = respx.post(f"{_BASE_URL}/api/sharing").mock(return_value=httpx.Response(200, json={}))

    from dhis2w_core.profile import resolve_profile

    profile = resolve_profile("probe")
    result = await service.bulk_share_metadata(
        profile,
        "dataSet",
        ["DS_A"],
        user_group_access=["UG_NEW:rwrw----"],
    )

    assert post_route.call_count == 1
    payload = _sharing_payload(post_route.calls.last.request)
    assert payload["publicAccess"] == "rw------"
    assert {grant["id"]: grant["access"] for grant in payload["userAccesses"]} == {"U_OLD": "r-------"}
    assert {grant["id"]: grant["access"] for grant in payload["userGroupAccesses"]} == {
        "UG_OLD": "rw------",
        "UG_NEW": "rwrw----",
    }
    entry = result.entries[0]
    assert entry.public_access == "rw------"
    assert entry.user_grants == ["U_OLD:r-------"]
    assert sorted(entry.user_group_grants) == ["UG_NEW:rwrw----", "UG_OLD:rw------"]
    assert result.succeeded == 1


@respx.mock
async def test_bulk_share_new_grant_overrides_existing_grant_for_same_uid(
    core_version: str,
    core_profile: None,  # noqa: ARG001
    plugin_service: Callable[[str], ModuleType],
    mock_system_info: Callable[..., None],
) -> None:
    """A grant for an already-granted UID replaces that UID's access string (others untouched)."""
    service = plugin_service("metadata")
    mock_system_info(core_version)
    respx.get(f"{_BASE_URL}/api/sharing", params={"type": "dataSet", "id": "DS_A"}).mock(
        return_value=httpx.Response(200, json=_EXISTING_SHARING),
    )
    post_route = respx.post(f"{_BASE_URL}/api/sharing").mock(return_value=httpx.Response(200, json={}))

    from dhis2w_core.profile import resolve_profile

    profile = resolve_profile("probe")
    await service.bulk_share_metadata(
        profile,
        "dataSet",
        ["DS_A"],
        public_access="r-------",
        user_access=["U_OLD:rw------"],
    )

    payload = _sharing_payload(post_route.calls.last.request)
    assert payload["publicAccess"] == "r-------"
    assert {grant["id"]: grant["access"] for grant in payload["userAccesses"]} == {"U_OLD": "rw------"}
    assert {grant["id"]: grant["access"] for grant in payload["userGroupAccesses"]} == {"UG_OLD": "rw------"}


@respx.mock
async def test_bulk_share_dry_run_previews_merged_sharing_without_posting(
    core_version: str,
    core_profile: None,  # noqa: ARG001
    plugin_service: Callable[[str], ModuleType],
    mock_system_info: Callable[..., None],
) -> None:
    """Dry run fetches current sharing so the preview shows the merged result, and never POSTs."""
    service = plugin_service("metadata")
    mock_system_info(core_version)
    respx.get(f"{_BASE_URL}/api/sharing", params={"type": "dataSet", "id": "DS_A"}).mock(
        return_value=httpx.Response(200, json=_EXISTING_SHARING),
    )
    post_route = respx.post(f"{_BASE_URL}/api/sharing").mock(return_value=httpx.Response(200, json={}))

    from dhis2w_core.profile import resolve_profile

    profile = resolve_profile("probe")
    result = await service.bulk_share_metadata(
        profile,
        "dataSet",
        ["DS_A"],
        user_access=["U_NEW:rw------"],
        dry_run=True,
    )

    assert not post_route.called
    assert result.dry_run is True
    assert result.sharing_result is None
    entry = result.entries[0]
    assert entry.public_access == "rw------"
    assert sorted(entry.user_grants) == ["U_NEW:rw------", "U_OLD:r-------"]
    assert entry.user_group_grants == ["UG_OLD:rw------"]


# ---------------------------------------------------------------------------
# Bug 3 — `merge-bundle` imports only the selected resource collections
# ---------------------------------------------------------------------------


@respx.mock
async def test_merge_bundle_resources_filter_restricts_import_payload(
    core_version: str,
    core_profile: None,  # noqa: ARG001
    plugin_service: Callable[[str], ModuleType],
    mock_system_info: Callable[..., None],
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """`resources` narrows what gets POSTed, not just the count summary."""
    service = plugin_service("metadata")
    mock_system_info(core_version)
    import_route = respx.post(f"{_BASE_URL}/api/metadata").mock(
        return_value=httpx.Response(
            200, json={"status": "OK", "httpStatusCode": 200, "response": {"stats": {"total": 0}}}
        ),
    )
    bundle_path = tmp_path_factory.mktemp("bundle") / "bundle.json"
    bundle_path.write_text(
        json.dumps(
            {
                "system": {"id": "sys"},
                "dataElements": [{"id": "DE_A"}, {"id": "DE_B"}],
                "indicators": [{"id": "IND_A"}],
            }
        ),
        encoding="utf-8",
    )

    from dhis2w_core.profile import resolve_profile

    profile = resolve_profile("probe")
    result = await service.merge_metadata_from_bundle(profile, bundle_path, resources=["dataElements"])

    posted = json.loads(import_route.calls.last.request.content)
    assert "indicators" not in posted
    assert [item["id"] for item in posted["dataElements"]] == ["DE_A", "DE_B"]
    assert result.export_counts == {"dataElements": 2}


async def test_merge_bundle_rejects_empty_resources(
    core_profile: None,  # noqa: ARG001
    plugin_service: Callable[[str], ModuleType],
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """An explicit empty selection is a caller mistake, not a whole-bundle import."""
    service = plugin_service("metadata")
    bundle_path = tmp_path_factory.mktemp("bundle") / "bundle.json"
    bundle_path.write_text(json.dumps({"dataElements": [{"id": "DE_A"}]}), encoding="utf-8")

    from dhis2w_core.profile import resolve_profile

    profile = resolve_profile("probe")
    with pytest.raises(service.MetadataUsageError, match="resources"):
        await service.merge_metadata_from_bundle(profile, bundle_path, resources=[])


# ---------------------------------------------------------------------------
# Bug 4 — `diff --live` distinguishes an empty selection from "no selection"
# ---------------------------------------------------------------------------


async def test_diff_bundle_against_instance_rejects_empty_resources(
    core_version: str,
    core_profile: None,  # noqa: ARG001
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`resources=[]` must not silently widen to a whole-instance export."""
    service = plugin_service("metadata")
    models = import_module(f"dhis2w_core.{core_version}.plugins.metadata.models")
    bundle = models.MetadataBundle.from_raw({"dataElements": [{"id": "DE_A"}]})

    from dhis2w_core.profile import resolve_profile

    profile = resolve_profile("probe")
    with pytest.raises(service.MetadataUsageError, match="resources"):
        await service.diff_bundle_against_instance(profile, bundle, resources=[])


async def test_diff_bundle_against_instance_empty_bundle_never_exports_whole_instance(
    core_version: str,
    core_profile: None,  # noqa: ARG001
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """A bundle with no resource collections diffs against nothing (no whole-instance export)."""
    service = plugin_service("metadata")
    models = import_module(f"dhis2w_core.{core_version}.plugins.metadata.models")
    bundle = models.MetadataBundle.from_raw({"system": {"id": "sys"}})

    from dhis2w_core.profile import resolve_profile

    profile = resolve_profile("probe")
    # No respx mock is active: any HTTP call would raise. An empty bundle must not export.
    diff = await service.diff_bundle_against_instance(profile, bundle)
    assert diff.resources == []


# ---------------------------------------------------------------------------
# Bug 5 — `retag` treats `legend_set_uids=[]` consistently in fields + preview
# ---------------------------------------------------------------------------


@respx.mock
async def test_bulk_retag_empty_legend_set_list_previews_current_legends(
    core_version: str,
    core_profile: None,  # noqa: ARG001
    plugin_service: Callable[[str], ModuleType],
    mock_system_info: Callable[..., None],
) -> None:
    """`legend_set_uids=[]` fetches current legendSets so before/after in the preview is accurate."""
    service = plugin_service("metadata")
    mock_system_info(core_version)
    list_route = respx.get(f"{_BASE_URL}/api/dataElements").mock(
        return_value=httpx.Response(
            200,
            json={
                "dataElements": [
                    {"id": "DE_A", "aggregationType": "SUM", "legendSets": [{"id": "LS_OLD"}]},
                ],
            },
        ),
    )

    from dhis2w_core.profile import resolve_profile

    profile = resolve_profile("probe")
    result = await service.bulk_retag_metadata(
        profile,
        "dataElements",
        aggregation_type="AVERAGE",
        legend_set_uids=[],
        dry_run=True,
    )

    requested_fields = list_route.calls.last.request.url.params["fields"]
    assert "legendSets[id]" in requested_fields
    entry = result.entries[0]
    assert entry.before["/legendSets"] == "LS_OLD"
    assert entry.after["/legendSets"] is None


# ---------------------------------------------------------------------------
# Bug 6 — typed group-set view with per-group member counts
# ---------------------------------------------------------------------------


@respx.mock
async def test_show_organisation_unit_group_set_returns_typed_member_counts(
    core_version: str,
    core_profile: None,  # noqa: ARG001
    plugin_service: Callable[[str], ModuleType],
    mock_system_info: Callable[..., None],
) -> None:
    """The view is one frozen model; an unparseable `~size` is None (unknown), not 0."""
    service = plugin_service("metadata")
    mock_system_info(core_version)
    respx.get(f"{_BASE_URL}/api/organisationUnitGroupSets/GS_A").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "GS_A",
                "name": "Facility Type",
                "organisationUnitGroups": [
                    {"id": "G_A", "name": "Clinics"},
                    {"id": "G_B", "name": "Hospitals"},
                ],
            },
        ),
    )
    respx.get(f"{_BASE_URL}/api/organisationUnitGroups/G_A").mock(
        return_value=httpx.Response(200, json={"id": "G_A", "organisationUnits": 5}),
    )
    respx.get(f"{_BASE_URL}/api/organisationUnitGroups/G_B").mock(
        return_value=httpx.Response(200, json={"id": "G_B", "organisationUnits": {"unexpected": "shape"}}),
    )

    from dhis2w_core.profile import resolve_profile

    profile = resolve_profile("probe")
    detail = await service.show_organisation_unit_group_set(profile, "GS_A")

    assert detail.group_set.id == "GS_A"
    assert detail.member_counts == {"G_A": 5, "G_B": None}
    with pytest.raises(Exception, match="frozen"):
        detail.member_counts = {}
