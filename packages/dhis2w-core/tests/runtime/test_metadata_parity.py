"""Per-version parity for the SHARED `metadata` plugin service surface — every tree, identical asserts.

The `metadata` plugin is the one plugin whose service genuinely diverges across version trees: v43
adds `set_program_labels`, `set_program_change_log_enabled`, and
`set_program_enrollment_category_combo`, which do not exist on v41/v42. These tests cover ONLY the
intersection — functions present on all three trees — so a single body resolves the service per
`core_version` (v41/v42/v43) and the v41/v43 code is executed and counted, not just smoke-imported.

`bulk_rename_metadata` is already parity-covered in `test_plugin_service_parity.py`, so it is not
repeated here. Routes + payloads mirror the v42-only `tests/metadata/*` suite. Mocked (respx); no
live stack.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from importlib import import_module
from pathlib import Path
from types import ModuleType

import httpx
import respx
from dhis2w_client import RemoveOp, ReplaceOp
from dhis2w_core.profile import resolve_profile

_HOST = "https://dhis2.example"


@respx.mock
async def test_metadata_count_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`count_metadata` reads `pager.total` from a 1-row probe, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    route = respx.get(f"{_HOST}/api/dataElements").mock(
        return_value=httpx.Response(200, json={"pager": {"total": 137}, "dataElements": [{"id": "DE_A"}]}),
    )

    total = await service.count_metadata(resolve_profile("probe"), "dataElements")

    assert total == 137
    params = route.calls.last.request.url.params
    assert params["pageSize"] == "1"
    assert params["fields"] == "id"


@respx.mock
async def test_metadata_list_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`list_metadata` parses `/api/<resource>` into typed generated models, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    respx.get(f"{_HOST}/api/dataElements").mock(
        return_value=httpx.Response(
            200,
            json={"dataElements": [{"id": "DE_A", "name": "ANC visits"}, {"id": "DE_B", "name": "BCG doses"}]},
        ),
    )

    models = await service.list_metadata(resolve_profile("probe"), "dataElements")

    assert len(models) == 2
    assert {m.id for m in models} == {"DE_A", "DE_B"}


@respx.mock
async def test_metadata_get_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`get_metadata` fetches one object by UID as a typed model, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    respx.get(f"{_HOST}/api/dataElements/DEancVisit1").mock(
        return_value=httpx.Response(200, json={"id": "DEancVisit1", "name": "ANC visits"}),
    )

    model = await service.get_metadata(resolve_profile("probe"), "dataElements", "DEancVisit1")

    assert model.id == "DEancVisit1"


@respx.mock
async def test_metadata_search_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`search_metadata` fans out to `/api/metadata` and dedups hits, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    respx.get(f"{_HOST}/api/metadata").mock(
        return_value=httpx.Response(200, json={"dataElements": [{"id": "DE_A", "name": "ANC visits"}]}),
    )

    results = await service.search_metadata(resolve_profile("probe"), "ANC")

    assert results.total >= 1
    assert {hit.uid for hit in results.hits["dataElements"]} == {"DE_A"}


@respx.mock
async def test_metadata_export_filter_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`export_metadata` forwards resource + field selectors to `/api/metadata`, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    route = respx.get(f"{_HOST}/api/metadata").mock(
        return_value=httpx.Response(200, json={"dataElements": [{"id": "DE_A"}]}),
    )

    bundle = await service.export_metadata(
        resolve_profile("probe"),
        resources=["dataElements", "indicators"],
        fields=":owner",
        skip_sharing=True,
    )

    params = dict(route.calls.last.request.url.params)
    assert params["dataElements"] == "true"
    assert params["indicators"] == "true"
    assert params["fields"] == ":owner"
    assert params["skipSharing"] == "true"
    assert [item.id for item in bundle.get_resource("dataElements")] == ["DE_A"]


@respx.mock
async def test_metadata_import_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`import_metadata` posts the bundle + forwards strategy params, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    metadata_bundle = import_module(f"dhis2w_core.{core_version}.plugins.metadata.models").MetadataBundle
    route = respx.post(f"{_HOST}/api/metadata").mock(
        return_value=httpx.Response(200, json={"status": "OK", "httpStatusCode": 200}),
    )

    response = await service.import_metadata(
        resolve_profile("probe"),
        metadata_bundle.from_raw({"dataElements": [{"id": "DE_A"}]}),
        import_strategy="CREATE",
        atomic_mode="NONE",
        identifier="CODE",
    )

    assert response.status is not None
    params = dict(route.calls.last.request.url.params)
    assert params["importStrategy"] == "CREATE"
    assert params["atomicMode"] == "NONE"
    assert params["identifier"] == "CODE"
    assert json.loads(route.calls.last.request.content) == {"dataElements": [{"id": "DE_A"}]}


@respx.mock
async def test_metadata_merge_bundle_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
    tmp_path: Path,
) -> None:
    """`merge_metadata_from_bundle` imports every section from a bundle on disk, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    bundle_path = tmp_path / "bundle.json"
    bundle_path.write_text(
        json.dumps(
            {
                "system": {"id": "sys"},
                "dataElements": [{"id": "DE_A", "name": "ANC visits"}],
                "indicators": [{"id": "IND_A", "name": "ANC indicator"}],
            }
        )
    )
    route = respx.post(f"{_HOST}/api/metadata").mock(
        return_value=httpx.Response(
            200,
            json={"status": "OK", "httpStatusCode": 200, "response": {"stats": {"total": 2}}},
        ),
    )

    result = await service.merge_metadata_from_bundle(resolve_profile("probe"), bundle_path)

    assert route.called
    assert result.dry_run is False
    assert sorted(result.export_counts) == ["dataElements", "indicators"]
    assert result.export_counts["dataElements"] == 1
    assert result.export_counts["indicators"] == 1


@respx.mock
async def test_metadata_patch_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`patch_metadata` serialises typed ops to the RFC 6902 wire array, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    route = respx.patch(f"{_HOST}/api/dataElements/DEancVisit1").mock(
        return_value=httpx.Response(200, json={"status": "OK"}),
    )

    response = await service.patch_metadata(
        resolve_profile("probe"),
        "dataElements",
        "DEancVisit1",
        [ReplaceOp(path="/description", value="new"), RemoveOp(path="/legacy")],
    )

    assert response.status is not None
    assert json.loads(route.calls.last.request.content) == [
        {"op": "replace", "path": "/description", "value": "new"},
        {"op": "remove", "path": "/legacy"},
    ]


@respx.mock
async def test_metadata_bulk_share_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`bulk_share_metadata` posts a `/api/sharing` grant per UID, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    route = respx.post(f"{_HOST}/api/sharing").mock(return_value=httpx.Response(200, json={}))

    result = await service.bulk_share_metadata(
        resolve_profile("probe"),
        "dataSet",
        ["DS_A", "DS_B"],
        public_access="r-------",
        user_group_access=["UG_PROG:rwrw----"],
    )

    assert route.call_count == 2
    assert result.matched == 2
    assert result.succeeded == 2
    assert result.failed == 0
    assert result.entries[0].user_group_grants == ["UG_PROG:rwrw----"]


@respx.mock
async def test_metadata_bulk_retag_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`bulk_retag_metadata` patches only rows whose tag actually changes, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    respx.get(f"{_HOST}/api/dataElements").mock(
        return_value=httpx.Response(
            200,
            json={
                "dataElements": [
                    {"id": "DE_A", "categoryCombo": {"id": "ccOld00001"}},
                    {"id": "DE_B", "categoryCombo": {"id": "ccNew00001"}},
                ],
            },
        ),
    )
    patch_a = respx.patch(f"{_HOST}/api/dataElements/DE_A").mock(return_value=httpx.Response(200, json={}))
    patch_b = respx.patch(f"{_HOST}/api/dataElements/DE_B").mock(return_value=httpx.Response(200, json={}))

    result = await service.bulk_retag_metadata(
        resolve_profile("probe"),
        "dataElements",
        category_combo_uid="ccNew00001",
    )

    assert result.matched == 1
    assert result.entries[0].uid == "DE_A"
    assert result.entries[0].before["/categoryCombo"] == "ccOld00001"
    assert result.entries[0].after["/categoryCombo"] == "ccNew00001"
    assert patch_a.called
    assert patch_b.called is False


@respx.mock
async def test_metadata_show_option_set_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`show_option_set` fetches an OptionSet by UID with options resolved, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    respx.get(f"{_HOST}/api/optionSets/opt01234567").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "opt01234567",
                "name": "Yes/No",
                "valueType": "TEXT",
                "options": [{"id": "optAyesvalue", "code": "Y", "name": "Yes", "sortOrder": 1}],
            },
        ),
    )

    option_set = await service.show_option_set(resolve_profile("probe"), "opt01234567")

    assert option_set is not None
    assert option_set.id == "opt01234567"


@respx.mock
async def test_metadata_create_option_set_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`create_option_set` POSTs `{name, valueType, code}` to `/api/optionSets`, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    route = respx.post(f"{_HOST}/api/optionSets").mock(
        return_value=httpx.Response(
            201, json={"status": "OK", "httpStatusCode": 201, "response": {"uid": "opt01234567"}}
        ),
    )

    result = await service.create_option_set(resolve_profile("probe"), name="Yes/No", value_type="TEXT", code="YN")

    body = json.loads(route.calls.last.request.content)
    assert body["name"] == "Yes/No"
    assert body["valueType"] == "TEXT"
    assert body["code"] == "YN"
    assert result is not None


@respx.mock
async def test_metadata_show_data_element_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`show_data_element` fetches one DataElement by UID as a typed model, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    respx.get(f"{_HOST}/api/dataElements/DEancVisit1").mock(
        return_value=httpx.Response(200, json={"id": "DEancVisit1", "name": "ANC visits"}),
    )

    data_element = await service.show_data_element(resolve_profile("probe"), "DEancVisit1")

    assert data_element.id == "DEancVisit1"
