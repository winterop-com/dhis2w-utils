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
    """`bulk_share_metadata` reads then posts a merged `/api/sharing` block per UID, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    for uid in ("DS_A", "DS_B"):
        respx.get(f"{_HOST}/api/sharing", params={"type": "dataSet", "id": uid}).mock(
            return_value=httpx.Response(
                200,
                json={"object": {"id": uid, "publicAccess": "--------", "externalAccess": False}},
            ),
        )
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


# ---------------------------------------------------------------------------
# DataElement authoring — create / rename / set-legend-sets / delete
# ---------------------------------------------------------------------------


@respx.mock
async def test_metadata_create_data_element_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`create_data_element` POSTs to `/api/dataElements` then re-fetches the row, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    create = respx.post(f"{_HOST}/api/dataElements").mock(
        return_value=httpx.Response(201, json={"status": "OK", "response": {"uid": "DEancVisit1"}}),
    )
    respx.get(f"{_HOST}/api/dataElements/DEancVisit1").mock(
        return_value=httpx.Response(200, json={"id": "DEancVisit1", "name": "ANC visits"}),
    )

    data_element = await service.create_data_element(
        resolve_profile("probe"),
        name="ANC visits",
        short_name="ANC",
        value_type="NUMBER",
        category_combo_uid="ccDefault001",
        uid="DEancVisit1",
    )

    assert data_element.id == "DEancVisit1"
    body = json.loads(create.calls.last.request.content)
    assert body["name"] == "ANC visits"
    assert body["valueType"] == "NUMBER"
    assert body["categoryCombo"] == {"id": "ccDefault001"}


@respx.mock
async def test_metadata_rename_data_element_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`rename_data_element` reads then PUTs the patched label, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    respx.get(f"{_HOST}/api/dataElements/DEancVisit1").mock(
        return_value=httpx.Response(200, json={"id": "DEancVisit1", "name": "Old", "shortName": "Old"}),
    )
    put = respx.put(f"{_HOST}/api/dataElements/DEancVisit1").mock(return_value=httpx.Response(200, json={}))

    await service.rename_data_element(resolve_profile("probe"), "DEancVisit1", name="ANC visits")

    assert put.called
    assert json.loads(put.calls.last.request.content)["name"] == "ANC visits"


@respx.mock
async def test_metadata_set_data_element_legend_sets_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`set_data_element_legend_sets` reads then PUTs the legendSets, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    respx.get(f"{_HOST}/api/dataElements/DEancVisit1").mock(
        return_value=httpx.Response(200, json={"id": "DEancVisit1", "name": "ANC visits"}),
    )
    put = respx.put(f"{_HOST}/api/dataElements/DEancVisit1").mock(return_value=httpx.Response(200, json={}))

    await service.set_data_element_legend_sets(resolve_profile("probe"), "DEancVisit1", legend_set_uids=["LSthresh001"])

    assert put.called
    assert json.loads(put.calls.last.request.content)["legendSets"] == [{"id": "LSthresh001"}]


@respx.mock
async def test_metadata_delete_data_element_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`delete_data_element` issues `DELETE /api/dataElements/{uid}`, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    route = respx.delete(f"{_HOST}/api/dataElements/DEancVisit1").mock(return_value=httpx.Response(200, json={}))

    await service.delete_data_element(resolve_profile("probe"), "DEancVisit1")

    assert route.called


# ---------------------------------------------------------------------------
# DataElementGroup + DataElementGroupSet
# ---------------------------------------------------------------------------


@respx.mock
async def test_metadata_create_data_element_group_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`create_data_element_group` POSTs then re-fetches, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    create = respx.post(f"{_HOST}/api/dataElementGroups").mock(
        return_value=httpx.Response(201, json={"status": "OK", "response": {"uid": "DEG0000001"}}),
    )
    respx.get(f"{_HOST}/api/dataElementGroups/DEG0000001").mock(
        return_value=httpx.Response(200, json={"id": "DEG0000001", "name": "ANC group"}),
    )

    group = await service.create_data_element_group(
        resolve_profile("probe"), name="ANC group", short_name="ANC", uid="DEG0000001"
    )

    assert group.id == "DEG0000001"
    assert json.loads(create.calls.last.request.content)["name"] == "ANC group"


@respx.mock
async def test_metadata_add_data_element_group_members_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`add_data_element_group_members` POSTs one member shortcut per UID, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    add = respx.post(f"{_HOST}/api/dataElementGroups/DEG0000001/dataElements/DE_A").mock(
        return_value=httpx.Response(200, json={}),
    )
    respx.get(f"{_HOST}/api/dataElementGroups/DEG0000001").mock(
        return_value=httpx.Response(200, json={"id": "DEG0000001", "name": "ANC group"}),
    )

    await service.add_data_element_group_members(resolve_profile("probe"), "DEG0000001", data_element_uids=["DE_A"])

    assert add.called


@respx.mock
async def test_metadata_remove_data_element_group_members_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`remove_data_element_group_members` DELETEs one member shortcut per UID, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    remove = respx.delete(f"{_HOST}/api/dataElementGroups/DEG0000001/dataElements/DE_A").mock(
        return_value=httpx.Response(200, json={}),
    )
    respx.get(f"{_HOST}/api/dataElementGroups/DEG0000001").mock(
        return_value=httpx.Response(200, json={"id": "DEG0000001", "name": "ANC group"}),
    )

    await service.remove_data_element_group_members(resolve_profile("probe"), "DEG0000001", data_element_uids=["DE_A"])

    assert remove.called


@respx.mock
async def test_metadata_delete_data_element_group_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`delete_data_element_group` issues `DELETE /api/dataElementGroups/{uid}`, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    route = respx.delete(f"{_HOST}/api/dataElementGroups/DEG0000001").mock(return_value=httpx.Response(200, json={}))

    await service.delete_data_element_group(resolve_profile("probe"), "DEG0000001")

    assert route.called


@respx.mock
async def test_metadata_create_data_element_group_set_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`create_data_element_group_set` POSTs then re-fetches, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    respx.post(f"{_HOST}/api/dataElementGroupSets").mock(
        return_value=httpx.Response(201, json={"status": "OK", "response": {"uid": "DEGS000001"}}),
    )
    respx.get(f"{_HOST}/api/dataElementGroupSets/DEGS000001").mock(
        return_value=httpx.Response(200, json={"id": "DEGS000001", "name": "ANC set"}),
    )

    group_set = await service.create_data_element_group_set(
        resolve_profile("probe"), name="ANC set", short_name="ANC", uid="DEGS000001"
    )

    assert group_set.id == "DEGS000001"


@respx.mock
async def test_metadata_add_data_element_group_set_groups_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`add_data_element_group_set_groups` POSTs one group shortcut per UID, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    add = respx.post(f"{_HOST}/api/dataElementGroupSets/DEGS000001/dataElementGroups/DEG0000001").mock(
        return_value=httpx.Response(200, json={}),
    )
    respx.get(f"{_HOST}/api/dataElementGroupSets/DEGS000001").mock(
        return_value=httpx.Response(200, json={"id": "DEGS000001", "name": "ANC set"}),
    )

    await service.add_data_element_group_set_groups(resolve_profile("probe"), "DEGS000001", group_uids=["DEG0000001"])

    assert add.called


@respx.mock
async def test_metadata_remove_data_element_group_set_groups_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`remove_data_element_group_set_groups` DELETEs one group shortcut per UID, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    remove = respx.delete(f"{_HOST}/api/dataElementGroupSets/DEGS000001/dataElementGroups/DEG0000001").mock(
        return_value=httpx.Response(200, json={}),
    )
    respx.get(f"{_HOST}/api/dataElementGroupSets/DEGS000001").mock(
        return_value=httpx.Response(200, json={"id": "DEGS000001", "name": "ANC set"}),
    )

    await service.remove_data_element_group_set_groups(
        resolve_profile("probe"), "DEGS000001", group_uids=["DEG0000001"]
    )

    assert remove.called


@respx.mock
async def test_metadata_delete_data_element_group_set_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`delete_data_element_group_set` issues `DELETE /api/dataElementGroupSets/{uid}`, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    route = respx.delete(f"{_HOST}/api/dataElementGroupSets/DEGS000001").mock(
        return_value=httpx.Response(200, json={}),
    )

    await service.delete_data_element_group_set(resolve_profile("probe"), "DEGS000001")

    assert route.called


# ---------------------------------------------------------------------------
# Indicator authoring + groups + group-sets
# ---------------------------------------------------------------------------


@respx.mock
async def test_metadata_create_indicator_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`create_indicator` POSTs numerator/denominator then re-fetches, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    create = respx.post(f"{_HOST}/api/indicators").mock(
        return_value=httpx.Response(201, json={"status": "OK", "response": {"uid": "IND0000001"}}),
    )
    respx.get(f"{_HOST}/api/indicators/IND0000001").mock(
        return_value=httpx.Response(200, json={"id": "IND0000001", "name": "ANC coverage"}),
    )

    indicator = await service.create_indicator(
        resolve_profile("probe"),
        name="ANC coverage",
        short_name="ANC cov",
        indicator_type_uid="ITpercent01",
        numerator="#{DE_A}",
        denominator="#{DE_B}",
        uid="IND0000001",
    )

    assert indicator.id == "IND0000001"
    body = json.loads(create.calls.last.request.content)
    assert body["indicatorType"] == {"id": "ITpercent01"}
    assert body["numerator"] == "#{DE_A}"


@respx.mock
async def test_metadata_rename_indicator_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`rename_indicator` reads then PUTs the patched label, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    respx.get(f"{_HOST}/api/indicators/IND0000001").mock(
        return_value=httpx.Response(200, json={"id": "IND0000001", "name": "Old"}),
    )
    put = respx.put(f"{_HOST}/api/indicators/IND0000001").mock(return_value=httpx.Response(200, json={}))

    await service.rename_indicator(resolve_profile("probe"), "IND0000001", name="ANC coverage")

    assert put.called
    assert json.loads(put.calls.last.request.content)["name"] == "ANC coverage"


@respx.mock
async def test_metadata_validate_indicator_expression_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`validate_indicator_expression` POSTs to `/api/indicators/expression/description`, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    route = respx.post(f"{_HOST}/api/indicators/expression/description").mock(
        return_value=httpx.Response(200, json={"status": "OK", "message": "Valid", "description": "#{DE_A}"}),
    )

    result = await service.validate_indicator_expression(resolve_profile("probe"), "#{DE_A}")

    assert result.valid is True
    assert route.calls.last.request.content == b"#{DE_A}"


@respx.mock
async def test_metadata_set_indicator_legend_sets_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`set_indicator_legend_sets` reads then PUTs the legendSets, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    respx.get(f"{_HOST}/api/indicators/IND0000001").mock(
        return_value=httpx.Response(200, json={"id": "IND0000001", "name": "ANC coverage"}),
    )
    put = respx.put(f"{_HOST}/api/indicators/IND0000001").mock(return_value=httpx.Response(200, json={}))

    await service.set_indicator_legend_sets(resolve_profile("probe"), "IND0000001", legend_set_uids=["LSthresh001"])

    assert put.called
    assert json.loads(put.calls.last.request.content)["legendSets"] == [{"id": "LSthresh001"}]


@respx.mock
async def test_metadata_delete_indicator_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`delete_indicator` issues `DELETE /api/indicators/{uid}`, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    route = respx.delete(f"{_HOST}/api/indicators/IND0000001").mock(return_value=httpx.Response(200, json={}))

    await service.delete_indicator(resolve_profile("probe"), "IND0000001")

    assert route.called


@respx.mock
async def test_metadata_create_indicator_group_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`create_indicator_group` POSTs then re-fetches, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    respx.post(f"{_HOST}/api/indicatorGroups").mock(
        return_value=httpx.Response(201, json={"status": "OK", "response": {"uid": "ING0000001"}}),
    )
    respx.get(f"{_HOST}/api/indicatorGroups/ING0000001").mock(
        return_value=httpx.Response(200, json={"id": "ING0000001", "name": "Coverage"}),
    )

    group = await service.create_indicator_group(
        resolve_profile("probe"), name="Coverage", short_name="Cov", uid="ING0000001"
    )

    assert group.id == "ING0000001"


@respx.mock
async def test_metadata_add_indicator_group_members_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`add_indicator_group_members` POSTs one member shortcut per UID, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    add = respx.post(f"{_HOST}/api/indicatorGroups/ING0000001/indicators/IND0000001").mock(
        return_value=httpx.Response(200, json={}),
    )
    respx.get(f"{_HOST}/api/indicatorGroups/ING0000001").mock(
        return_value=httpx.Response(200, json={"id": "ING0000001", "name": "Coverage"}),
    )

    await service.add_indicator_group_members(resolve_profile("probe"), "ING0000001", indicator_uids=["IND0000001"])

    assert add.called


@respx.mock
async def test_metadata_remove_indicator_group_members_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`remove_indicator_group_members` DELETEs one member shortcut per UID, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    remove = respx.delete(f"{_HOST}/api/indicatorGroups/ING0000001/indicators/IND0000001").mock(
        return_value=httpx.Response(200, json={}),
    )
    respx.get(f"{_HOST}/api/indicatorGroups/ING0000001").mock(
        return_value=httpx.Response(200, json={"id": "ING0000001", "name": "Coverage"}),
    )

    await service.remove_indicator_group_members(resolve_profile("probe"), "ING0000001", indicator_uids=["IND0000001"])

    assert remove.called


@respx.mock
async def test_metadata_delete_indicator_group_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`delete_indicator_group` issues `DELETE /api/indicatorGroups/{uid}`, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    route = respx.delete(f"{_HOST}/api/indicatorGroups/ING0000001").mock(return_value=httpx.Response(200, json={}))

    await service.delete_indicator_group(resolve_profile("probe"), "ING0000001")

    assert route.called


@respx.mock
async def test_metadata_create_indicator_group_set_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`create_indicator_group_set` POSTs then re-fetches, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    respx.post(f"{_HOST}/api/indicatorGroupSets").mock(
        return_value=httpx.Response(201, json={"status": "OK", "response": {"uid": "INGS00001"}}),
    )
    respx.get(f"{_HOST}/api/indicatorGroupSets/INGS00001").mock(
        return_value=httpx.Response(200, json={"id": "INGS00001", "name": "Themes"}),
    )

    group_set = await service.create_indicator_group_set(
        resolve_profile("probe"), name="Themes", short_name="Themes", uid="INGS00001"
    )

    assert group_set.id == "INGS00001"


@respx.mock
async def test_metadata_add_indicator_group_set_groups_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`add_indicator_group_set_groups` POSTs one group shortcut per UID, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    add = respx.post(f"{_HOST}/api/indicatorGroupSets/INGS00001/indicatorGroups/ING0000001").mock(
        return_value=httpx.Response(200, json={}),
    )
    respx.get(f"{_HOST}/api/indicatorGroupSets/INGS00001").mock(
        return_value=httpx.Response(200, json={"id": "INGS00001", "name": "Themes"}),
    )

    await service.add_indicator_group_set_groups(resolve_profile("probe"), "INGS00001", group_uids=["ING0000001"])

    assert add.called


@respx.mock
async def test_metadata_remove_indicator_group_set_groups_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`remove_indicator_group_set_groups` DELETEs one group shortcut per UID, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    remove = respx.delete(f"{_HOST}/api/indicatorGroupSets/INGS00001/indicatorGroups/ING0000001").mock(
        return_value=httpx.Response(200, json={}),
    )
    respx.get(f"{_HOST}/api/indicatorGroupSets/INGS00001").mock(
        return_value=httpx.Response(200, json={"id": "INGS00001", "name": "Themes"}),
    )

    await service.remove_indicator_group_set_groups(resolve_profile("probe"), "INGS00001", group_uids=["ING0000001"])

    assert remove.called


@respx.mock
async def test_metadata_delete_indicator_group_set_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`delete_indicator_group_set` issues `DELETE /api/indicatorGroupSets/{uid}`, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    route = respx.delete(f"{_HOST}/api/indicatorGroupSets/INGS00001").mock(return_value=httpx.Response(200, json={}))

    await service.delete_indicator_group_set(resolve_profile("probe"), "INGS00001")

    assert route.called


# ---------------------------------------------------------------------------
# OrganisationUnit + groups + group-sets + levels
# ---------------------------------------------------------------------------


@respx.mock
async def test_metadata_create_organisation_unit_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`create_organisation_unit` POSTs a child OU then re-fetches, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    respx.post(f"{_HOST}/api/organisationUnits").mock(
        return_value=httpx.Response(201, json={"status": "OK", "response": {"uid": "OUchild0001"}}),
    )
    respx.get(f"{_HOST}/api/organisationUnits/OUchild0001").mock(
        return_value=httpx.Response(200, json={"id": "OUchild0001", "name": "Clinic"}),
    )

    org_unit = await service.create_organisation_unit(
        resolve_profile("probe"),
        parent_uid="OUparent001",
        name="Clinic",
        short_name="Clinic",
        opening_date="2020-01-01",
        uid="OUchild0001",
    )

    assert org_unit.id == "OUchild0001"


@respx.mock
async def test_metadata_move_organisation_unit_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`move_organisation_unit` reads then PUTs the new parent ref, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    respx.get(f"{_HOST}/api/organisationUnits/OUchild0001").mock(
        return_value=httpx.Response(200, json={"id": "OUchild0001", "name": "Clinic"}),
    )
    put = respx.put(f"{_HOST}/api/organisationUnits/OUchild0001").mock(return_value=httpx.Response(200, json={}))

    await service.move_organisation_unit(resolve_profile("probe"), uid="OUchild0001", new_parent_uid="OUnewdad001")

    assert put.called
    assert json.loads(put.calls.last.request.content)["parent"] == {"id": "OUnewdad001"}


@respx.mock
async def test_metadata_tree_organisation_units_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`tree_organisation_units` at depth 0 returns just the root, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    respx.get(f"{_HOST}/api/organisationUnits/OUroot00001").mock(
        return_value=httpx.Response(200, json={"id": "OUroot00001", "name": "Country"}),
    )

    units = await service.tree_organisation_units(resolve_profile("probe"), root_uid="OUroot00001", max_depth=0)

    assert [unit.id for unit in units] == ["OUroot00001"]


@respx.mock
async def test_metadata_delete_organisation_unit_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`delete_organisation_unit` issues `DELETE /api/organisationUnits/{uid}`, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    route = respx.delete(f"{_HOST}/api/organisationUnits/OUchild0001").mock(return_value=httpx.Response(200, json={}))

    await service.delete_organisation_unit(resolve_profile("probe"), "OUchild0001")

    assert route.called


@respx.mock
async def test_metadata_create_organisation_unit_group_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`create_organisation_unit_group` POSTs then re-fetches, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    respx.post(f"{_HOST}/api/organisationUnitGroups").mock(
        return_value=httpx.Response(201, json={"status": "OK", "response": {"uid": "OUG0000001"}}),
    )
    respx.get(f"{_HOST}/api/organisationUnitGroups/OUG0000001").mock(
        return_value=httpx.Response(200, json={"id": "OUG0000001", "name": "Urban"}),
    )

    group = await service.create_organisation_unit_group(
        resolve_profile("probe"), name="Urban", short_name="Urban", uid="OUG0000001"
    )

    assert group.id == "OUG0000001"


@respx.mock
async def test_metadata_add_organisation_unit_group_members_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`add_organisation_unit_group_members` POSTs one member shortcut per UID, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    add = respx.post(f"{_HOST}/api/organisationUnitGroups/OUG0000001/organisationUnits/OUchild0001").mock(
        return_value=httpx.Response(200, json={}),
    )
    respx.get(f"{_HOST}/api/organisationUnitGroups/OUG0000001").mock(
        return_value=httpx.Response(200, json={"id": "OUG0000001", "name": "Urban"}),
    )

    await service.add_organisation_unit_group_members(resolve_profile("probe"), "OUG0000001", ou_uids=["OUchild0001"])

    assert add.called


@respx.mock
async def test_metadata_remove_organisation_unit_group_members_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`remove_organisation_unit_group_members` DELETEs one member shortcut per UID, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    remove = respx.delete(f"{_HOST}/api/organisationUnitGroups/OUG0000001/organisationUnits/OUchild0001").mock(
        return_value=httpx.Response(200, json={}),
    )
    respx.get(f"{_HOST}/api/organisationUnitGroups/OUG0000001").mock(
        return_value=httpx.Response(200, json={"id": "OUG0000001", "name": "Urban"}),
    )

    await service.remove_organisation_unit_group_members(
        resolve_profile("probe"), "OUG0000001", ou_uids=["OUchild0001"]
    )

    assert remove.called


@respx.mock
async def test_metadata_delete_organisation_unit_group_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`delete_organisation_unit_group` issues `DELETE /api/organisationUnitGroups/{uid}`, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    route = respx.delete(f"{_HOST}/api/organisationUnitGroups/OUG0000001").mock(
        return_value=httpx.Response(200, json={}),
    )

    await service.delete_organisation_unit_group(resolve_profile("probe"), "OUG0000001")

    assert route.called


@respx.mock
async def test_metadata_create_organisation_unit_group_set_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`create_organisation_unit_group_set` POSTs then re-fetches, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    respx.post(f"{_HOST}/api/organisationUnitGroupSets").mock(
        return_value=httpx.Response(201, json={"status": "OK", "response": {"uid": "OUGS00001"}}),
    )
    respx.get(f"{_HOST}/api/organisationUnitGroupSets/OUGS00001").mock(
        return_value=httpx.Response(200, json={"id": "OUGS00001", "name": "Type"}),
    )

    group_set = await service.create_organisation_unit_group_set(
        resolve_profile("probe"), name="Type", short_name="Type", uid="OUGS00001"
    )

    assert group_set.id == "OUGS00001"


@respx.mock
async def test_metadata_add_organisation_unit_group_set_groups_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`add_organisation_unit_group_set_groups` POSTs one group shortcut per UID, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    add = respx.post(f"{_HOST}/api/organisationUnitGroupSets/OUGS00001/organisationUnitGroups/OUG0000001").mock(
        return_value=httpx.Response(200, json={}),
    )
    respx.get(f"{_HOST}/api/organisationUnitGroupSets/OUGS00001").mock(
        return_value=httpx.Response(200, json={"id": "OUGS00001", "name": "Type"}),
    )

    await service.add_organisation_unit_group_set_groups(
        resolve_profile("probe"), "OUGS00001", group_uids=["OUG0000001"]
    )

    assert add.called


@respx.mock
async def test_metadata_remove_organisation_unit_group_set_groups_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`remove_organisation_unit_group_set_groups` DELETEs one group shortcut per UID, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    remove = respx.delete(f"{_HOST}/api/organisationUnitGroupSets/OUGS00001/organisationUnitGroups/OUG0000001").mock(
        return_value=httpx.Response(200, json={}),
    )
    respx.get(f"{_HOST}/api/organisationUnitGroupSets/OUGS00001").mock(
        return_value=httpx.Response(200, json={"id": "OUGS00001", "name": "Type"}),
    )

    await service.remove_organisation_unit_group_set_groups(
        resolve_profile("probe"), "OUGS00001", group_uids=["OUG0000001"]
    )

    assert remove.called


@respx.mock
async def test_metadata_delete_organisation_unit_group_set_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`delete_organisation_unit_group_set` issues the DELETE, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    route = respx.delete(f"{_HOST}/api/organisationUnitGroupSets/OUGS00001").mock(
        return_value=httpx.Response(200, json={}),
    )

    await service.delete_organisation_unit_group_set(resolve_profile("probe"), "OUGS00001")

    assert route.called


@respx.mock
async def test_metadata_rename_organisation_unit_level_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`rename_organisation_unit_level` reads then PUTs the level row by UID, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    respx.get(f"{_HOST}/api/organisationUnitLevels/OULvl000001").mock(
        return_value=httpx.Response(200, json={"id": "OULvl000001", "name": "Old", "level": 2}),
    )
    put = respx.put(f"{_HOST}/api/organisationUnitLevels/OULvl000001").mock(return_value=httpx.Response(200, json={}))

    await service.rename_organisation_unit_level(resolve_profile("probe"), "OULvl000001", name="District")

    assert put.called
    assert json.loads(put.calls.last.request.content)["name"] == "District"


# ---------------------------------------------------------------------------
# LegendSet authoring
# ---------------------------------------------------------------------------


@respx.mock
async def test_metadata_create_legend_set_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`create_legend_set` imports via `/api/metadata` then re-fetches, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    imp = respx.post(f"{_HOST}/api/metadata").mock(
        return_value=httpx.Response(200, json={"status": "OK", "httpStatusCode": 200}),
    )
    respx.get(url__regex=rf"{_HOST}/api/legendSets/.+").mock(
        return_value=httpx.Response(200, json={"id": "LS00000001", "name": "Coverage"}),
    )

    legend_set = await service.create_legend_set(
        resolve_profile("probe"),
        name="Coverage",
        legends=[(0.0, 50.0, "#ff0000", "Low"), (50.0, 100.0, "#00ff00", "High")],
        uid="LS00000001",
    )

    assert legend_set.id == "LS00000001"
    body = json.loads(imp.calls.last.request.content)
    assert "legendSets" in body


@respx.mock
async def test_metadata_clone_legend_set_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`clone_legend_set` reads the source then imports a fresh copy, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    respx.get(f"{_HOST}/api/legendSets/LSsource001").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "LSsource001",
                "name": "Coverage",
                "legends": [{"id": "Lg00000001", "name": "Low", "startValue": 0, "endValue": 50, "color": "#ff0000"}],
            },
        ),
    )
    respx.post(f"{_HOST}/api/metadata").mock(
        return_value=httpx.Response(200, json={"status": "OK", "httpStatusCode": 200}),
    )
    respx.get(f"{_HOST}/api/legendSets/LScloned001").mock(
        return_value=httpx.Response(200, json={"id": "LScloned001", "name": "Coverage copy"}),
    )

    clone = await service.clone_legend_set(
        resolve_profile("probe"), "LSsource001", new_uid="LScloned001", new_name="Coverage copy"
    )

    assert clone.id == "LScloned001"


@respx.mock
async def test_metadata_delete_legend_set_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`delete_legend_set` issues `DELETE /api/legendSets/{uid}`, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    route = respx.delete(f"{_HOST}/api/legendSets/LS00000001").mock(return_value=httpx.Response(200, json={}))

    await service.delete_legend_set(resolve_profile("probe"), "LS00000001")

    assert route.called


# ---------------------------------------------------------------------------
# DataSet + Section authoring
# ---------------------------------------------------------------------------


@respx.mock
async def test_metadata_create_data_set_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`create_data_set` POSTs then re-fetches, with an explicit CC to skip the default lookup."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    create = respx.post(f"{_HOST}/api/dataSets").mock(
        return_value=httpx.Response(201, json={"status": "OK", "response": {"uid": "DS00000001"}}),
    )
    respx.get(f"{_HOST}/api/dataSets/DS00000001").mock(
        return_value=httpx.Response(200, json={"id": "DS00000001", "name": "Monthly"}),
    )

    data_set = await service.create_data_set(
        resolve_profile("probe"),
        name="Monthly",
        short_name="Monthly",
        period_type="Monthly",
        category_combo_uid="ccDefault001",
        uid="DS00000001",
    )

    assert data_set.id == "DS00000001"
    assert json.loads(create.calls.last.request.content)["periodType"] == "Monthly"


@respx.mock
async def test_metadata_rename_data_set_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`rename_data_set` reads then PUTs the patched label, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    respx.get(f"{_HOST}/api/dataSets/DS00000001").mock(
        return_value=httpx.Response(200, json={"id": "DS00000001", "name": "Old"}),
    )
    put = respx.put(f"{_HOST}/api/dataSets/DS00000001").mock(return_value=httpx.Response(200, json={}))

    await service.rename_data_set(resolve_profile("probe"), "DS00000001", name="Monthly")

    assert put.called
    assert json.loads(put.calls.last.request.content)["name"] == "Monthly"


@respx.mock
async def test_metadata_add_data_set_element_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`add_data_set_element` reads then PUTs the appended dataSetElement, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    respx.get(f"{_HOST}/api/dataSets/DS00000001").mock(
        return_value=httpx.Response(200, json={"id": "DS00000001", "name": "Monthly", "dataSetElements": []}),
    )
    put = respx.put(f"{_HOST}/api/dataSets/DS00000001").mock(return_value=httpx.Response(200, json={}))

    await service.add_data_set_element(resolve_profile("probe"), "DS00000001", "DE_A")

    assert put.called


@respx.mock
async def test_metadata_remove_data_set_element_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`remove_data_set_element` reads then PUTs the trimmed dataSetElements, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    respx.get(f"{_HOST}/api/dataSets/DS00000001").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "DS00000001",
                "name": "Monthly",
                "dataSetElements": [{"dataElement": {"id": "DE_A"}}],
            },
        ),
    )
    put = respx.put(f"{_HOST}/api/dataSets/DS00000001").mock(return_value=httpx.Response(200, json={}))

    await service.remove_data_set_element(resolve_profile("probe"), "DS00000001", "DE_A")

    assert put.called


@respx.mock
async def test_metadata_delete_data_set_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`delete_data_set` issues `DELETE /api/dataSets/{uid}`, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    route = respx.delete(f"{_HOST}/api/dataSets/DS00000001").mock(return_value=httpx.Response(200, json={}))

    await service.delete_data_set(resolve_profile("probe"), "DS00000001")

    assert route.called


@respx.mock
async def test_metadata_create_section_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`create_section` POSTs then re-fetches, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    create = respx.post(f"{_HOST}/api/sections").mock(
        return_value=httpx.Response(201, json={"status": "OK", "response": {"uid": "SEC0000001"}}),
    )
    respx.get(f"{_HOST}/api/sections/SEC0000001").mock(
        return_value=httpx.Response(200, json={"id": "SEC0000001", "name": "Vaccines"}),
    )

    section = await service.create_section(
        resolve_profile("probe"), name="Vaccines", data_set_uid="DS00000001", uid="SEC0000001"
    )

    assert section.id == "SEC0000001"
    assert json.loads(create.calls.last.request.content)["dataSet"] == {"id": "DS00000001"}


@respx.mock
async def test_metadata_rename_section_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`rename_section` reads then PUTs the patched label, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    respx.get(f"{_HOST}/api/sections/SEC0000001").mock(
        return_value=httpx.Response(200, json={"id": "SEC0000001", "name": "Old"}),
    )
    put = respx.put(f"{_HOST}/api/sections/SEC0000001").mock(return_value=httpx.Response(200, json={}))

    await service.rename_section(resolve_profile("probe"), "SEC0000001", name="Vaccines")

    assert put.called
    assert json.loads(put.calls.last.request.content)["name"] == "Vaccines"


@respx.mock
async def test_metadata_add_section_element_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`add_section_element` reads then PUTs the appended dataElement, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    respx.get(f"{_HOST}/api/sections/SEC0000001").mock(
        return_value=httpx.Response(200, json={"id": "SEC0000001", "name": "Vaccines", "dataElements": []}),
    )
    put = respx.put(f"{_HOST}/api/sections/SEC0000001").mock(return_value=httpx.Response(200, json={}))

    await service.add_section_element(resolve_profile("probe"), "SEC0000001", "DE_A")

    assert put.called


@respx.mock
async def test_metadata_remove_section_element_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`remove_section_element` reads then PUTs the trimmed dataElements, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    respx.get(f"{_HOST}/api/sections/SEC0000001").mock(
        return_value=httpx.Response(
            200, json={"id": "SEC0000001", "name": "Vaccines", "dataElements": [{"id": "DE_A"}]}
        ),
    )
    put = respx.put(f"{_HOST}/api/sections/SEC0000001").mock(return_value=httpx.Response(200, json={}))

    await service.remove_section_element(resolve_profile("probe"), "SEC0000001", "DE_A")

    assert put.called


@respx.mock
async def test_metadata_reorder_section_elements_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`reorder_section_elements` reads then PUTs the reordered dataElements, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    respx.get(f"{_HOST}/api/sections/SEC0000001").mock(
        return_value=httpx.Response(
            200,
            json={"id": "SEC0000001", "name": "Vaccines", "dataElements": [{"id": "DE_A"}, {"id": "DE_B"}]},
        ),
    )
    put = respx.put(f"{_HOST}/api/sections/SEC0000001").mock(return_value=httpx.Response(200, json={}))

    await service.reorder_section_elements(resolve_profile("probe"), "SEC0000001", data_element_uids=["DE_B", "DE_A"])

    assert put.called


@respx.mock
async def test_metadata_delete_section_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`delete_section` issues `DELETE /api/sections/{uid}`, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    route = respx.delete(f"{_HOST}/api/sections/SEC0000001").mock(return_value=httpx.Response(200, json={}))

    await service.delete_section(resolve_profile("probe"), "SEC0000001")

    assert route.called


# ---------------------------------------------------------------------------
# Category / CategoryOption / CategoryCombo authoring
# ---------------------------------------------------------------------------


@respx.mock
async def test_metadata_create_category_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`create_category` POSTs then re-fetches, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    respx.post(f"{_HOST}/api/categories").mock(
        return_value=httpx.Response(201, json={"status": "OK", "response": {"uid": "CAT0000001"}}),
    )
    respx.get(f"{_HOST}/api/categories/CAT0000001").mock(
        return_value=httpx.Response(200, json={"id": "CAT0000001", "name": "Sex"}),
    )

    category = await service.create_category(resolve_profile("probe"), name="Sex", short_name="Sex", uid="CAT0000001")

    assert category.id == "CAT0000001"


@respx.mock
async def test_metadata_rename_category_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`rename_category` reads then PUTs the patched label, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    respx.get(f"{_HOST}/api/categories/CAT0000001").mock(
        return_value=httpx.Response(200, json={"id": "CAT0000001", "name": "Old"}),
    )
    put = respx.put(f"{_HOST}/api/categories/CAT0000001").mock(return_value=httpx.Response(200, json={}))

    await service.rename_category(resolve_profile("probe"), "CAT0000001", name="Sex")

    assert put.called
    assert json.loads(put.calls.last.request.content)["name"] == "Sex"


@respx.mock
async def test_metadata_add_category_option_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`add_category_option` POSTs the member shortcut, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    route = respx.post(f"{_HOST}/api/categories/CAT0000001/categoryOptions/CO00000001").mock(
        return_value=httpx.Response(200, json={}),
    )

    await service.add_category_option(resolve_profile("probe"), "CAT0000001", "CO00000001")

    assert route.called


@respx.mock
async def test_metadata_remove_category_option_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`remove_category_option` DELETEs the member shortcut, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    route = respx.delete(f"{_HOST}/api/categories/CAT0000001/categoryOptions/CO00000001").mock(
        return_value=httpx.Response(200, json={}),
    )

    await service.remove_category_option(resolve_profile("probe"), "CAT0000001", "CO00000001")

    assert route.called


@respx.mock
async def test_metadata_delete_category_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`delete_category` issues `DELETE /api/categories/{uid}`, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    route = respx.delete(f"{_HOST}/api/categories/CAT0000001").mock(return_value=httpx.Response(200, json={}))

    await service.delete_category(resolve_profile("probe"), "CAT0000001")

    assert route.called


@respx.mock
async def test_metadata_create_category_option_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`create_category_option` POSTs then re-fetches, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    respx.post(f"{_HOST}/api/categoryOptions").mock(
        return_value=httpx.Response(201, json={"status": "OK", "response": {"uid": "CO00000001"}}),
    )
    respx.get(f"{_HOST}/api/categoryOptions/CO00000001").mock(
        return_value=httpx.Response(200, json={"id": "CO00000001", "name": "Female"}),
    )

    option = await service.create_category_option(
        resolve_profile("probe"), name="Female", short_name="F", uid="CO00000001"
    )

    assert option.id == "CO00000001"


@respx.mock
async def test_metadata_rename_category_option_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`rename_category_option` reads then PUTs the patched label, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    respx.get(f"{_HOST}/api/categoryOptions/CO00000001").mock(
        return_value=httpx.Response(200, json={"id": "CO00000001", "name": "Old"}),
    )
    put = respx.put(f"{_HOST}/api/categoryOptions/CO00000001").mock(return_value=httpx.Response(200, json={}))

    await service.rename_category_option(resolve_profile("probe"), "CO00000001", name="Female")

    assert put.called
    assert json.loads(put.calls.last.request.content)["name"] == "Female"


@respx.mock
async def test_metadata_set_category_option_validity_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`set_category_option_validity` reads then PUTs the start/end window, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    respx.get(f"{_HOST}/api/categoryOptions/CO00000001").mock(
        return_value=httpx.Response(200, json={"id": "CO00000001", "name": "Female"}),
    )
    put = respx.put(f"{_HOST}/api/categoryOptions/CO00000001").mock(return_value=httpx.Response(200, json={}))

    await service.set_category_option_validity(
        resolve_profile("probe"), "CO00000001", start_date="2020-01-01", end_date="2020-12-31"
    )

    assert put.called
    body = json.loads(put.calls.last.request.content)
    assert body["startDate"].startswith("2020-01-01")
    assert body["endDate"].startswith("2020-12-31")


@respx.mock
async def test_metadata_delete_category_option_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`delete_category_option` issues `DELETE /api/categoryOptions/{uid}`, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    route = respx.delete(f"{_HOST}/api/categoryOptions/CO00000001").mock(return_value=httpx.Response(200, json={}))

    await service.delete_category_option(resolve_profile("probe"), "CO00000001")

    assert route.called


@respx.mock
async def test_metadata_create_category_combo_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`create_category_combo` POSTs an ordered category list then re-fetches, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    create = respx.post(f"{_HOST}/api/categoryCombos").mock(
        return_value=httpx.Response(201, json={"status": "OK", "response": {"uid": "CC00000001"}}),
    )
    respx.get(f"{_HOST}/api/categoryCombos/CC00000001").mock(
        return_value=httpx.Response(200, json={"id": "CC00000001", "name": "Sex x Age"}),
    )

    combo = await service.create_category_combo(
        resolve_profile("probe"), name="Sex x Age", categories=["CAT0000001", "CAT0000002"], uid="CC00000001"
    )

    assert combo.id == "CC00000001"
    body = json.loads(create.calls.last.request.content)
    assert body["categories"] == [{"id": "CAT0000001"}, {"id": "CAT0000002"}]


@respx.mock
async def test_metadata_rename_category_combo_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`rename_category_combo` reads then PUTs the patched label, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    respx.get(f"{_HOST}/api/categoryCombos/CC00000001").mock(
        return_value=httpx.Response(200, json={"id": "CC00000001", "name": "Old"}),
    )
    put = respx.put(f"{_HOST}/api/categoryCombos/CC00000001").mock(return_value=httpx.Response(200, json={}))

    await service.rename_category_combo(resolve_profile("probe"), "CC00000001", name="Sex x Age")

    assert put.called
    assert json.loads(put.calls.last.request.content)["name"] == "Sex x Age"


@respx.mock
async def test_metadata_add_category_to_combo_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`add_category_to_combo` POSTs the member shortcut, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    route = respx.post(f"{_HOST}/api/categoryCombos/CC00000001/categories/CAT0000001").mock(
        return_value=httpx.Response(200, json={}),
    )

    await service.add_category_to_combo(resolve_profile("probe"), "CC00000001", "CAT0000001")

    assert route.called


@respx.mock
async def test_metadata_remove_category_from_combo_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`remove_category_from_combo` DELETEs the member shortcut, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    route = respx.delete(f"{_HOST}/api/categoryCombos/CC00000001/categories/CAT0000001").mock(
        return_value=httpx.Response(200, json={}),
    )

    await service.remove_category_from_combo(resolve_profile("probe"), "CC00000001", "CAT0000001")

    assert route.called


@respx.mock
async def test_metadata_delete_category_combo_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`delete_category_combo` issues `DELETE /api/categoryCombos/{uid}`, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    route = respx.delete(f"{_HOST}/api/categoryCombos/CC00000001").mock(return_value=httpx.Response(200, json={}))

    await service.delete_category_combo(resolve_profile("probe"), "CC00000001")

    assert route.called


# ---------------------------------------------------------------------------
# CategoryOptionGroup + CategoryOptionGroupSet
# ---------------------------------------------------------------------------


@respx.mock
async def test_metadata_create_category_option_group_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`create_category_option_group` POSTs then re-fetches, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    respx.post(f"{_HOST}/api/categoryOptionGroups").mock(
        return_value=httpx.Response(201, json={"status": "OK", "response": {"uid": "COG0000001"}}),
    )
    respx.get(f"{_HOST}/api/categoryOptionGroups/COG0000001").mock(
        return_value=httpx.Response(200, json={"id": "COG0000001", "name": "Public"}),
    )

    group = await service.create_category_option_group(
        resolve_profile("probe"), name="Public", short_name="Pub", uid="COG0000001"
    )

    assert group.id == "COG0000001"


@respx.mock
async def test_metadata_add_category_option_group_members_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`add_category_option_group_members` POSTs one member shortcut per UID, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    add = respx.post(f"{_HOST}/api/categoryOptionGroups/COG0000001/categoryOptions/CO00000001").mock(
        return_value=httpx.Response(200, json={}),
    )
    respx.get(f"{_HOST}/api/categoryOptionGroups/COG0000001").mock(
        return_value=httpx.Response(200, json={"id": "COG0000001", "name": "Public"}),
    )

    await service.add_category_option_group_members(
        resolve_profile("probe"), "COG0000001", category_option_uids=["CO00000001"]
    )

    assert add.called


@respx.mock
async def test_metadata_remove_category_option_group_members_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`remove_category_option_group_members` DELETEs one member shortcut per UID, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    remove = respx.delete(f"{_HOST}/api/categoryOptionGroups/COG0000001/categoryOptions/CO00000001").mock(
        return_value=httpx.Response(200, json={}),
    )
    respx.get(f"{_HOST}/api/categoryOptionGroups/COG0000001").mock(
        return_value=httpx.Response(200, json={"id": "COG0000001", "name": "Public"}),
    )

    await service.remove_category_option_group_members(
        resolve_profile("probe"), "COG0000001", category_option_uids=["CO00000001"]
    )

    assert remove.called


@respx.mock
async def test_metadata_delete_category_option_group_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`delete_category_option_group` issues `DELETE /api/categoryOptionGroups/{uid}`, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    route = respx.delete(f"{_HOST}/api/categoryOptionGroups/COG0000001").mock(return_value=httpx.Response(200, json={}))

    await service.delete_category_option_group(resolve_profile("probe"), "COG0000001")

    assert route.called


@respx.mock
async def test_metadata_create_category_option_group_set_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`create_category_option_group_set` POSTs then re-fetches, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    respx.post(f"{_HOST}/api/categoryOptionGroupSets").mock(
        return_value=httpx.Response(201, json={"status": "OK", "response": {"uid": "COGS00001"}}),
    )
    respx.get(f"{_HOST}/api/categoryOptionGroupSets/COGS00001").mock(
        return_value=httpx.Response(200, json={"id": "COGS00001", "name": "Ownership"}),
    )

    group_set = await service.create_category_option_group_set(
        resolve_profile("probe"), name="Ownership", short_name="Own", uid="COGS00001"
    )

    assert group_set.id == "COGS00001"


@respx.mock
async def test_metadata_add_category_option_group_set_groups_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`add_category_option_group_set_groups` POSTs one group shortcut per UID, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    add = respx.post(f"{_HOST}/api/categoryOptionGroupSets/COGS00001/categoryOptionGroups/COG0000001").mock(
        return_value=httpx.Response(200, json={}),
    )
    respx.get(f"{_HOST}/api/categoryOptionGroupSets/COGS00001").mock(
        return_value=httpx.Response(200, json={"id": "COGS00001", "name": "Ownership"}),
    )

    await service.add_category_option_group_set_groups(resolve_profile("probe"), "COGS00001", group_uids=["COG0000001"])

    assert add.called


@respx.mock
async def test_metadata_remove_category_option_group_set_groups_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`remove_category_option_group_set_groups` DELETEs one group shortcut per UID, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    remove = respx.delete(f"{_HOST}/api/categoryOptionGroupSets/COGS00001/categoryOptionGroups/COG0000001").mock(
        return_value=httpx.Response(200, json={}),
    )
    respx.get(f"{_HOST}/api/categoryOptionGroupSets/COGS00001").mock(
        return_value=httpx.Response(200, json={"id": "COGS00001", "name": "Ownership"}),
    )

    await service.remove_category_option_group_set_groups(
        resolve_profile("probe"), "COGS00001", group_uids=["COG0000001"]
    )

    assert remove.called


@respx.mock
async def test_metadata_delete_category_option_group_set_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`delete_category_option_group_set` issues the DELETE, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    route = respx.delete(f"{_HOST}/api/categoryOptionGroupSets/COGS00001").mock(
        return_value=httpx.Response(200, json={}),
    )

    await service.delete_category_option_group_set(resolve_profile("probe"), "COGS00001")

    assert route.called


# ---------------------------------------------------------------------------
# ValidationRule + ValidationRuleGroup
# ---------------------------------------------------------------------------


@respx.mock
async def test_metadata_create_validation_rule_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`create_validation_rule` POSTs the left/right expressions then re-fetches, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    create = respx.post(f"{_HOST}/api/validationRules").mock(
        return_value=httpx.Response(201, json={"status": "OK", "response": {"uid": "VR00000001"}}),
    )
    respx.get(f"{_HOST}/api/validationRules/VR00000001").mock(
        return_value=httpx.Response(200, json={"id": "VR00000001", "name": "ANC consistency"}),
    )

    rule = await service.create_validation_rule(
        resolve_profile("probe"),
        name="ANC consistency",
        short_name="ANC con",
        left_expression="#{DE_A}",
        operator="equal_to",
        right_expression="#{DE_B}",
        uid="VR00000001",
    )

    assert rule.id == "VR00000001"
    assert json.loads(create.calls.last.request.content)["operator"] == "equal_to"


@respx.mock
async def test_metadata_rename_validation_rule_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`rename_validation_rule` reads then PUTs the patched label, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    respx.get(f"{_HOST}/api/validationRules/VR00000001").mock(
        return_value=httpx.Response(200, json={"id": "VR00000001", "name": "Old"}),
    )
    put = respx.put(f"{_HOST}/api/validationRules/VR00000001").mock(return_value=httpx.Response(200, json={}))

    await service.rename_validation_rule(resolve_profile("probe"), "VR00000001", name="ANC consistency")

    assert put.called
    assert json.loads(put.calls.last.request.content)["name"] == "ANC consistency"


@respx.mock
async def test_metadata_delete_validation_rule_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`delete_validation_rule` issues `DELETE /api/validationRules/{uid}`, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    route = respx.delete(f"{_HOST}/api/validationRules/VR00000001").mock(return_value=httpx.Response(200, json={}))

    await service.delete_validation_rule(resolve_profile("probe"), "VR00000001")

    assert route.called


@respx.mock
async def test_metadata_create_validation_rule_group_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`create_validation_rule_group` POSTs then re-fetches, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    respx.post(f"{_HOST}/api/validationRuleGroups").mock(
        return_value=httpx.Response(201, json={"status": "OK", "response": {"uid": "VRG0000001"}}),
    )
    respx.get(f"{_HOST}/api/validationRuleGroups/VRG0000001").mock(
        return_value=httpx.Response(200, json={"id": "VRG0000001", "name": "ANC checks"}),
    )

    group = await service.create_validation_rule_group(resolve_profile("probe"), name="ANC checks", uid="VRG0000001")

    assert group.id == "VRG0000001"


@respx.mock
async def test_metadata_add_validation_rule_group_members_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`add_validation_rule_group_members` POSTs one member shortcut per UID, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    add = respx.post(f"{_HOST}/api/validationRuleGroups/VRG0000001/validationRules/VR00000001").mock(
        return_value=httpx.Response(200, json={}),
    )
    respx.get(f"{_HOST}/api/validationRuleGroups/VRG0000001").mock(
        return_value=httpx.Response(200, json={"id": "VRG0000001", "name": "ANC checks"}),
    )

    await service.add_validation_rule_group_members(
        resolve_profile("probe"), "VRG0000001", validation_rule_uids=["VR00000001"]
    )

    assert add.called


@respx.mock
async def test_metadata_remove_validation_rule_group_members_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`remove_validation_rule_group_members` DELETEs one member shortcut per UID, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    remove = respx.delete(f"{_HOST}/api/validationRuleGroups/VRG0000001/validationRules/VR00000001").mock(
        return_value=httpx.Response(200, json={}),
    )
    respx.get(f"{_HOST}/api/validationRuleGroups/VRG0000001").mock(
        return_value=httpx.Response(200, json={"id": "VRG0000001", "name": "ANC checks"}),
    )

    await service.remove_validation_rule_group_members(
        resolve_profile("probe"), "VRG0000001", validation_rule_uids=["VR00000001"]
    )

    assert remove.called


@respx.mock
async def test_metadata_delete_validation_rule_group_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`delete_validation_rule_group` issues the DELETE, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    route = respx.delete(f"{_HOST}/api/validationRuleGroups/VRG0000001").mock(return_value=httpx.Response(200, json={}))

    await service.delete_validation_rule_group(resolve_profile("probe"), "VRG0000001")

    assert route.called


# ---------------------------------------------------------------------------
# Predictor + PredictorGroup
# ---------------------------------------------------------------------------


@respx.mock
async def test_metadata_create_predictor_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`create_predictor` POSTs then re-fetches, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    create = respx.post(f"{_HOST}/api/predictors").mock(
        return_value=httpx.Response(201, json={"status": "OK", "response": {"uid": "PRED000001"}}),
    )
    respx.get(f"{_HOST}/api/predictors/PRED000001").mock(
        return_value=httpx.Response(200, json={"id": "PRED000001", "name": "ANC forecast"}),
    )

    predictor = await service.create_predictor(
        resolve_profile("probe"),
        name="ANC forecast",
        short_name="ANC fc",
        expression="AVG(#{DE_A})",
        output_data_element_uid="DEout00001",
        uid="PRED000001",
    )

    assert predictor.id == "PRED000001"
    assert json.loads(create.calls.last.request.content)["output"] == {"id": "DEout00001"}


@respx.mock
async def test_metadata_rename_predictor_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`rename_predictor` reads then PUTs the patched label, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    respx.get(f"{_HOST}/api/predictors/PRED000001").mock(
        return_value=httpx.Response(200, json={"id": "PRED000001", "name": "Old"}),
    )
    put = respx.put(f"{_HOST}/api/predictors/PRED000001").mock(return_value=httpx.Response(200, json={}))

    await service.rename_predictor(resolve_profile("probe"), "PRED000001", name="ANC forecast")

    assert put.called
    assert json.loads(put.calls.last.request.content)["name"] == "ANC forecast"


@respx.mock
async def test_metadata_delete_predictor_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`delete_predictor` issues `DELETE /api/predictors/{uid}`, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    route = respx.delete(f"{_HOST}/api/predictors/PRED000001").mock(return_value=httpx.Response(200, json={}))

    await service.delete_predictor(resolve_profile("probe"), "PRED000001")

    assert route.called


@respx.mock
async def test_metadata_create_predictor_group_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`create_predictor_group` POSTs then re-fetches, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    respx.post(f"{_HOST}/api/predictorGroups").mock(
        return_value=httpx.Response(201, json={"status": "OK", "response": {"uid": "PRG0000001"}}),
    )
    respx.get(f"{_HOST}/api/predictorGroups/PRG0000001").mock(
        return_value=httpx.Response(200, json={"id": "PRG0000001", "name": "Forecasts"}),
    )

    group = await service.create_predictor_group(resolve_profile("probe"), name="Forecasts", uid="PRG0000001")

    assert group.id == "PRG0000001"


@respx.mock
async def test_metadata_add_predictor_group_members_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`add_predictor_group_members` POSTs one member shortcut per UID, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    add = respx.post(f"{_HOST}/api/predictorGroups/PRG0000001/predictors/PRED000001").mock(
        return_value=httpx.Response(200, json={}),
    )
    respx.get(f"{_HOST}/api/predictorGroups/PRG0000001").mock(
        return_value=httpx.Response(200, json={"id": "PRG0000001", "name": "Forecasts"}),
    )

    await service.add_predictor_group_members(resolve_profile("probe"), "PRG0000001", predictor_uids=["PRED000001"])

    assert add.called


@respx.mock
async def test_metadata_remove_predictor_group_members_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`remove_predictor_group_members` DELETEs one member shortcut per UID, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    remove = respx.delete(f"{_HOST}/api/predictorGroups/PRG0000001/predictors/PRED000001").mock(
        return_value=httpx.Response(200, json={}),
    )
    respx.get(f"{_HOST}/api/predictorGroups/PRG0000001").mock(
        return_value=httpx.Response(200, json={"id": "PRG0000001", "name": "Forecasts"}),
    )

    await service.remove_predictor_group_members(resolve_profile("probe"), "PRG0000001", predictor_uids=["PRED000001"])

    assert remove.called


@respx.mock
async def test_metadata_delete_predictor_group_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`delete_predictor_group` issues `DELETE /api/predictorGroups/{uid}`, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    route = respx.delete(f"{_HOST}/api/predictorGroups/PRG0000001").mock(return_value=httpx.Response(200, json={}))

    await service.delete_predictor_group(resolve_profile("probe"), "PRG0000001")

    assert route.called


# ---------------------------------------------------------------------------
# TrackedEntityAttribute + TrackedEntityType
# ---------------------------------------------------------------------------


@respx.mock
async def test_metadata_create_tracked_entity_attribute_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`create_tracked_entity_attribute` POSTs then re-fetches, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    respx.post(f"{_HOST}/api/trackedEntityAttributes").mock(
        return_value=httpx.Response(201, json={"status": "OK", "response": {"uid": "TEA0000001"}}),
    )
    respx.get(f"{_HOST}/api/trackedEntityAttributes/TEA0000001").mock(
        return_value=httpx.Response(200, json={"id": "TEA0000001", "name": "First name"}),
    )

    attribute = await service.create_tracked_entity_attribute(
        resolve_profile("probe"), name="First name", short_name="First", uid="TEA0000001"
    )

    assert attribute.id == "TEA0000001"


@respx.mock
async def test_metadata_rename_tracked_entity_attribute_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`rename_tracked_entity_attribute` reads then PUTs the patched label, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    respx.get(f"{_HOST}/api/trackedEntityAttributes/TEA0000001").mock(
        return_value=httpx.Response(200, json={"id": "TEA0000001", "name": "Old"}),
    )
    put = respx.put(f"{_HOST}/api/trackedEntityAttributes/TEA0000001").mock(return_value=httpx.Response(200, json={}))

    await service.rename_tracked_entity_attribute(resolve_profile("probe"), "TEA0000001", name="First name")

    assert put.called
    assert json.loads(put.calls.last.request.content)["name"] == "First name"


@respx.mock
async def test_metadata_delete_tracked_entity_attribute_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`delete_tracked_entity_attribute` issues the DELETE, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    route = respx.delete(f"{_HOST}/api/trackedEntityAttributes/TEA0000001").mock(
        return_value=httpx.Response(200, json={}),
    )

    await service.delete_tracked_entity_attribute(resolve_profile("probe"), "TEA0000001")

    assert route.called


@respx.mock
async def test_metadata_create_tracked_entity_type_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`create_tracked_entity_type` POSTs then re-fetches, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    respx.post(f"{_HOST}/api/trackedEntityTypes").mock(
        return_value=httpx.Response(201, json={"status": "OK", "response": {"uid": "TET0000001"}}),
    )
    respx.get(f"{_HOST}/api/trackedEntityTypes/TET0000001").mock(
        return_value=httpx.Response(200, json={"id": "TET0000001", "name": "Person"}),
    )

    tet = await service.create_tracked_entity_type(
        resolve_profile("probe"), name="Person", short_name="Person", uid="TET0000001"
    )

    assert tet.id == "TET0000001"


@respx.mock
async def test_metadata_rename_tracked_entity_type_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`rename_tracked_entity_type` reads then PUTs the patched label, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    respx.get(f"{_HOST}/api/trackedEntityTypes/TET0000001").mock(
        return_value=httpx.Response(200, json={"id": "TET0000001", "name": "Old"}),
    )
    put = respx.put(f"{_HOST}/api/trackedEntityTypes/TET0000001").mock(return_value=httpx.Response(200, json={}))

    await service.rename_tracked_entity_type(resolve_profile("probe"), "TET0000001", name="Person")

    assert put.called
    assert json.loads(put.calls.last.request.content)["name"] == "Person"


@respx.mock
async def test_metadata_add_tracked_entity_type_attribute_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`add_tracked_entity_type_attribute` reads then PUTs the link row, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    respx.get(f"{_HOST}/api/trackedEntityTypes/TET0000001").mock(
        return_value=httpx.Response(
            200, json={"id": "TET0000001", "name": "Person", "trackedEntityTypeAttributes": []}
        ),
    )
    put = respx.put(f"{_HOST}/api/trackedEntityTypes/TET0000001").mock(return_value=httpx.Response(200, json={}))

    await service.add_tracked_entity_type_attribute(resolve_profile("probe"), "TET0000001", "TEA0000001")

    assert put.called


@respx.mock
async def test_metadata_remove_tracked_entity_type_attribute_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`remove_tracked_entity_type_attribute` reads then PUTs the trimmed link list, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    respx.get(f"{_HOST}/api/trackedEntityTypes/TET0000001").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "TET0000001",
                "name": "Person",
                "trackedEntityTypeAttributes": [{"trackedEntityAttribute": {"id": "TEA0000001"}}],
            },
        ),
    )
    put = respx.put(f"{_HOST}/api/trackedEntityTypes/TET0000001").mock(return_value=httpx.Response(200, json={}))

    await service.remove_tracked_entity_type_attribute(resolve_profile("probe"), "TET0000001", "TEA0000001")

    assert put.called


@respx.mock
async def test_metadata_delete_tracked_entity_type_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`delete_tracked_entity_type` issues the DELETE, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    route = respx.delete(f"{_HOST}/api/trackedEntityTypes/TET0000001").mock(return_value=httpx.Response(200, json={}))

    await service.delete_tracked_entity_type(resolve_profile("probe"), "TET0000001")

    assert route.called


# ---------------------------------------------------------------------------
# Program authoring
# ---------------------------------------------------------------------------


@respx.mock
async def test_metadata_create_program_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`create_program` POSTs then re-fetches, with an explicit CC to skip the default lookup."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    create = respx.post(f"{_HOST}/api/programs").mock(
        return_value=httpx.Response(201, json={"status": "OK", "response": {"uid": "PRGanc0001"}}),
    )
    respx.get(f"{_HOST}/api/programs/PRGanc0001").mock(
        return_value=httpx.Response(200, json={"id": "PRGanc0001", "name": "ANC program"}),
    )

    program = await service.create_program(
        resolve_profile("probe"),
        name="ANC program",
        short_name="ANC prog",
        program_type="WITH_REGISTRATION",
        tracked_entity_type_uid="TET0000001",
        category_combo_uid="ccDefault001",
        uid="PRGanc0001",
    )

    assert program.id == "PRGanc0001"
    assert json.loads(create.calls.last.request.content)["trackedEntityType"] == {"id": "TET0000001"}


@respx.mock
async def test_metadata_rename_program_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`rename_program` reads then PUTs the patched label, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    respx.get(f"{_HOST}/api/programs/PRGanc0001").mock(
        return_value=httpx.Response(200, json={"id": "PRGanc0001", "name": "Old"}),
    )
    put = respx.put(f"{_HOST}/api/programs/PRGanc0001").mock(return_value=httpx.Response(200, json={}))

    await service.rename_program(resolve_profile("probe"), "PRGanc0001", name="ANC program")

    assert put.called
    assert json.loads(put.calls.last.request.content)["name"] == "ANC program"


@respx.mock
async def test_metadata_add_program_attribute_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`add_program_attribute` reads then PUTs the enrollment-attribute link, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    respx.get(f"{_HOST}/api/programs/PRGanc0001").mock(
        return_value=httpx.Response(
            200, json={"id": "PRGanc0001", "name": "ANC program", "programTrackedEntityAttributes": []}
        ),
    )
    put = respx.put(f"{_HOST}/api/programs/PRGanc0001").mock(return_value=httpx.Response(200, json={}))

    await service.add_program_attribute(resolve_profile("probe"), "PRGanc0001", "TEA0000001")

    assert put.called


@respx.mock
async def test_metadata_remove_program_attribute_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`remove_program_attribute` reads then PUTs the trimmed attribute list, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    respx.get(f"{_HOST}/api/programs/PRGanc0001").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "PRGanc0001",
                "name": "ANC program",
                "programTrackedEntityAttributes": [{"trackedEntityAttribute": {"id": "TEA0000001"}}],
            },
        ),
    )
    put = respx.put(f"{_HOST}/api/programs/PRGanc0001").mock(return_value=httpx.Response(200, json={}))

    await service.remove_program_attribute(resolve_profile("probe"), "PRGanc0001", "TEA0000001")

    assert put.called


@respx.mock
async def test_metadata_add_program_organisation_unit_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`add_program_organisation_unit` POSTs the member shortcut then re-fetches, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    add = respx.post(f"{_HOST}/api/programs/PRGanc0001/organisationUnits/OUchild0001").mock(
        return_value=httpx.Response(200, json={}),
    )
    respx.get(f"{_HOST}/api/programs/PRGanc0001").mock(
        return_value=httpx.Response(200, json={"id": "PRGanc0001", "name": "ANC program"}),
    )

    await service.add_program_organisation_unit(resolve_profile("probe"), "PRGanc0001", "OUchild0001")

    assert add.called


@respx.mock
async def test_metadata_remove_program_organisation_unit_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`remove_program_organisation_unit` DELETEs the member shortcut then re-fetches, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    remove = respx.delete(f"{_HOST}/api/programs/PRGanc0001/organisationUnits/OUchild0001").mock(
        return_value=httpx.Response(200, json={}),
    )
    respx.get(f"{_HOST}/api/programs/PRGanc0001").mock(
        return_value=httpx.Response(200, json={"id": "PRGanc0001", "name": "ANC program"}),
    )

    await service.remove_program_organisation_unit(resolve_profile("probe"), "PRGanc0001", "OUchild0001")

    assert remove.called


@respx.mock
async def test_metadata_delete_program_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`delete_program` issues `DELETE /api/programs/{uid}`, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    route = respx.delete(f"{_HOST}/api/programs/PRGanc0001").mock(return_value=httpx.Response(200, json={}))

    await service.delete_program(resolve_profile("probe"), "PRGanc0001")

    assert route.called


# ---------------------------------------------------------------------------
# ProgramStage authoring
# ---------------------------------------------------------------------------


@respx.mock
async def test_metadata_create_program_stage_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`create_program_stage` POSTs then re-fetches, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    create = respx.post(f"{_HOST}/api/programStages").mock(
        return_value=httpx.Response(201, json={"status": "OK", "response": {"uid": "PS00000001"}}),
    )
    respx.get(f"{_HOST}/api/programStages/PS00000001").mock(
        return_value=httpx.Response(200, json={"id": "PS00000001", "name": "Visit"}),
    )

    stage = await service.create_program_stage(
        resolve_profile("probe"), name="Visit", program_uid="PRGanc0001", uid="PS00000001"
    )

    assert stage.id == "PS00000001"
    assert json.loads(create.calls.last.request.content)["program"] == {"id": "PRGanc0001"}


@respx.mock
async def test_metadata_rename_program_stage_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`rename_program_stage` reads then PUTs the patched label, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    respx.get(f"{_HOST}/api/programStages/PS00000001").mock(
        return_value=httpx.Response(200, json={"id": "PS00000001", "name": "Old"}),
    )
    put = respx.put(f"{_HOST}/api/programStages/PS00000001").mock(return_value=httpx.Response(200, json={}))

    await service.rename_program_stage(resolve_profile("probe"), "PS00000001", name="Visit")

    assert put.called
    assert json.loads(put.calls.last.request.content)["name"] == "Visit"


@respx.mock
async def test_metadata_add_program_stage_element_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`add_program_stage_element` reads then PUTs the appended PSDE, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    respx.get(f"{_HOST}/api/programStages/PS00000001").mock(
        return_value=httpx.Response(200, json={"id": "PS00000001", "name": "Visit", "programStageDataElements": []}),
    )
    put = respx.put(f"{_HOST}/api/programStages/PS00000001").mock(return_value=httpx.Response(200, json={}))

    await service.add_program_stage_element(resolve_profile("probe"), "PS00000001", "DE_A")

    assert put.called


@respx.mock
async def test_metadata_remove_program_stage_element_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`remove_program_stage_element` reads then PUTs the trimmed PSDE list, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    respx.get(f"{_HOST}/api/programStages/PS00000001").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "PS00000001",
                "name": "Visit",
                "programStageDataElements": [{"dataElement": {"id": "DE_A"}}],
            },
        ),
    )
    put = respx.put(f"{_HOST}/api/programStages/PS00000001").mock(return_value=httpx.Response(200, json={}))

    await service.remove_program_stage_element(resolve_profile("probe"), "PS00000001", "DE_A")

    assert put.called


@respx.mock
async def test_metadata_reorder_program_stage_elements_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`reorder_program_stage_elements` reads then PUTs the reordered PSDEs, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    respx.get(f"{_HOST}/api/programStages/PS00000001").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "PS00000001",
                "name": "Visit",
                "programStageDataElements": [
                    {"dataElement": {"id": "DE_A"}},
                    {"dataElement": {"id": "DE_B"}},
                ],
            },
        ),
    )
    put = respx.put(f"{_HOST}/api/programStages/PS00000001").mock(return_value=httpx.Response(200, json={}))

    await service.reorder_program_stage_elements(
        resolve_profile("probe"), "PS00000001", data_element_uids=["DE_B", "DE_A"]
    )

    assert put.called


@respx.mock
async def test_metadata_delete_program_stage_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`delete_program_stage` issues `DELETE /api/programStages/{uid}`, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    route = respx.delete(f"{_HOST}/api/programStages/PS00000001").mock(return_value=httpx.Response(200, json={}))

    await service.delete_program_stage(resolve_profile("probe"), "PS00000001")

    assert route.called


# ---------------------------------------------------------------------------
# ProgramIndicator + ProgramIndicatorGroup
# ---------------------------------------------------------------------------


@respx.mock
async def test_metadata_create_program_indicator_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`create_program_indicator` POSTs then re-fetches, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    create = respx.post(f"{_HOST}/api/programIndicators").mock(
        return_value=httpx.Response(201, json={"status": "OK", "response": {"uid": "PI00000001"}}),
    )
    respx.get(f"{_HOST}/api/programIndicators/PI00000001").mock(
        return_value=httpx.Response(200, json={"id": "PI00000001", "name": "Visits count"}),
    )

    indicator = await service.create_program_indicator(
        resolve_profile("probe"),
        name="Visits count",
        short_name="Visits",
        program_uid="PRGanc0001",
        expression="V{event_count}",
        uid="PI00000001",
    )

    assert indicator.id == "PI00000001"
    assert json.loads(create.calls.last.request.content)["program"] == {"id": "PRGanc0001"}


@respx.mock
async def test_metadata_rename_program_indicator_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`rename_program_indicator` reads then PUTs the patched label, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    respx.get(f"{_HOST}/api/programIndicators/PI00000001").mock(
        return_value=httpx.Response(200, json={"id": "PI00000001", "name": "Old"}),
    )
    put = respx.put(f"{_HOST}/api/programIndicators/PI00000001").mock(return_value=httpx.Response(200, json={}))

    await service.rename_program_indicator(resolve_profile("probe"), "PI00000001", name="Visits count")

    assert put.called
    assert json.loads(put.calls.last.request.content)["name"] == "Visits count"


@respx.mock
async def test_metadata_validate_program_indicator_expression_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`validate_program_indicator_expression` POSTs to the PI describe endpoint, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    route = respx.post(f"{_HOST}/api/programIndicators/expression/description").mock(
        return_value=httpx.Response(200, json={"status": "OK", "message": "Valid", "description": "V{event_count}"}),
    )

    result = await service.validate_program_indicator_expression(resolve_profile("probe"), "V{event_count}")

    assert result.valid is True
    assert route.calls.last.request.content == b"V{event_count}"


@respx.mock
async def test_metadata_set_program_indicator_legend_sets_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`set_program_indicator_legend_sets` reads then PUTs the legendSets, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    respx.get(f"{_HOST}/api/programIndicators/PI00000001").mock(
        return_value=httpx.Response(200, json={"id": "PI00000001", "name": "Visits count"}),
    )
    put = respx.put(f"{_HOST}/api/programIndicators/PI00000001").mock(return_value=httpx.Response(200, json={}))

    await service.set_program_indicator_legend_sets(
        resolve_profile("probe"), "PI00000001", legend_set_uids=["LSthresh001"]
    )

    assert put.called
    assert json.loads(put.calls.last.request.content)["legendSets"] == [{"id": "LSthresh001"}]


@respx.mock
async def test_metadata_delete_program_indicator_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`delete_program_indicator` issues `DELETE /api/programIndicators/{uid}`, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    route = respx.delete(f"{_HOST}/api/programIndicators/PI00000001").mock(return_value=httpx.Response(200, json={}))

    await service.delete_program_indicator(resolve_profile("probe"), "PI00000001")

    assert route.called


@respx.mock
async def test_metadata_create_program_indicator_group_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`create_program_indicator_group` POSTs then re-fetches, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    respx.post(f"{_HOST}/api/programIndicatorGroups").mock(
        return_value=httpx.Response(201, json={"status": "OK", "response": {"uid": "PIG0000001"}}),
    )
    respx.get(f"{_HOST}/api/programIndicatorGroups/PIG0000001").mock(
        return_value=httpx.Response(200, json={"id": "PIG0000001", "name": "Event indicators"}),
    )

    group = await service.create_program_indicator_group(
        resolve_profile("probe"), name="Event indicators", short_name="Events", uid="PIG0000001"
    )

    assert group.id == "PIG0000001"


@respx.mock
async def test_metadata_add_program_indicator_group_members_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`add_program_indicator_group_members` POSTs one member shortcut per UID, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    add = respx.post(f"{_HOST}/api/programIndicatorGroups/PIG0000001/programIndicators/PI00000001").mock(
        return_value=httpx.Response(200, json={}),
    )
    respx.get(f"{_HOST}/api/programIndicatorGroups/PIG0000001").mock(
        return_value=httpx.Response(200, json={"id": "PIG0000001", "name": "Event indicators"}),
    )

    await service.add_program_indicator_group_members(
        resolve_profile("probe"), "PIG0000001", program_indicator_uids=["PI00000001"]
    )

    assert add.called


@respx.mock
async def test_metadata_remove_program_indicator_group_members_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`remove_program_indicator_group_members` DELETEs one member shortcut per UID, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    remove = respx.delete(f"{_HOST}/api/programIndicatorGroups/PIG0000001/programIndicators/PI00000001").mock(
        return_value=httpx.Response(200, json={}),
    )
    respx.get(f"{_HOST}/api/programIndicatorGroups/PIG0000001").mock(
        return_value=httpx.Response(200, json={"id": "PIG0000001", "name": "Event indicators"}),
    )

    await service.remove_program_indicator_group_members(
        resolve_profile("probe"), "PIG0000001", program_indicator_uids=["PI00000001"]
    )

    assert remove.called


@respx.mock
async def test_metadata_delete_program_indicator_group_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`delete_program_indicator_group` issues the DELETE, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    route = respx.delete(f"{_HOST}/api/programIndicatorGroups/PIG0000001").mock(
        return_value=httpx.Response(200, json={}),
    )

    await service.delete_program_indicator_group(resolve_profile("probe"), "PIG0000001")

    assert route.called


# ---------------------------------------------------------------------------
# Pure bundle analysis — diff + dangling references (no HTTP)
# ---------------------------------------------------------------------------


@respx.mock
async def test_metadata_diff_bundles_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`diff_bundles` structurally compares two in-memory bundles, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    metadata_bundle = import_module(f"dhis2w_core.{core_version}.plugins.metadata.models").MetadataBundle
    left = metadata_bundle.from_raw({"dataElements": [{"id": "DE_A", "name": "Old"}]})
    right = metadata_bundle.from_raw({"dataElements": [{"id": "DE_A", "name": "New"}, {"id": "DE_B", "name": "Added"}]})

    diff = service.diff_bundles(left, right)

    assert diff is not None


@respx.mock
async def test_metadata_bundle_dangling_references_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`bundle_dangling_references` reports refs to UIDs not present in the bundle, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    metadata_bundle = import_module(f"dhis2w_core.{core_version}.plugins.metadata.models").MetadataBundle
    bundle = metadata_bundle.from_raw(
        {"dataElements": [{"id": "DE_A", "name": "ANC", "categoryCombo": {"id": "ccMissing01"}}]}
    )

    dangling = service.bundle_dangling_references(bundle)

    assert dangling is not None


@respx.mock
async def test_metadata_iter_metadata_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`iter_metadata` streams rows across pages until a short page ends it, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    respx.get(f"{_HOST}/api/dataElements").mock(
        return_value=httpx.Response(200, json={"dataElements": [{"id": "DE_A"}, {"id": "DE_B"}]}),
    )

    collected = [model async for model in service.iter_metadata(resolve_profile("probe"), "dataElements", page_size=10)]

    assert {model.id for model in collected} == {"DE_A", "DE_B"}


# ---------------------------------------------------------------------------
# Visualization / Map / Dashboard authoring
# ---------------------------------------------------------------------------


@respx.mock
async def test_metadata_create_visualization_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`create_visualization` imports via `/api/metadata` then re-fetches, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    respx.post(f"{_HOST}/api/metadata").mock(
        return_value=httpx.Response(200, json={"status": "OK", "httpStatusCode": 200}),
    )
    respx.get(f"{_HOST}/api/visualizations/VIZ0000001").mock(
        return_value=httpx.Response(200, json={"id": "VIZ0000001", "name": "ANC chart"}),
    )

    viz = await service.create_visualization(
        resolve_profile("probe"),
        name="ANC chart",
        viz_type="COLUMN",
        data_elements=["DE_A"],
        periods=["LAST_12_MONTHS"],
        organisation_units=["OU_A"],
        uid="VIZ0000001",
    )

    assert viz.id == "VIZ0000001"


@respx.mock
async def test_metadata_create_map_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`create_map` imports a single-layer choropleth via `/api/metadata` then re-fetches, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    respx.post(f"{_HOST}/api/metadata").mock(
        return_value=httpx.Response(200, json={"status": "OK", "httpStatusCode": 200}),
    )
    respx.get(f"{_HOST}/api/maps/MAP0000001").mock(
        return_value=httpx.Response(200, json={"id": "MAP0000001", "name": "ANC map"}),
    )

    thematic_map = await service.create_map(
        resolve_profile("probe"),
        name="ANC map",
        data_elements=["DE_A"],
        periods=["LAST_12_MONTHS"],
        organisation_units=["OU_A"],
        organisation_unit_levels=[2],
        uid="MAP0000001",
    )

    assert thematic_map.id == "MAP0000001"


@respx.mock
async def test_metadata_dashboard_add_item_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`dashboard_add_item` reads the dashboard, imports the new item, then re-fetches, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    respx.get(f"{_HOST}/api/dashboards/DASH000001").mock(
        return_value=httpx.Response(200, json={"id": "DASH000001", "name": "Overview", "dashboardItems": []}),
    )
    respx.post(f"{_HOST}/api/metadata").mock(
        return_value=httpx.Response(200, json={"status": "OK", "httpStatusCode": 200}),
    )

    dashboard = await service.dashboard_add_item(
        resolve_profile("probe"), "DASH000001", "VIZ0000001", kind="visualization"
    )

    assert dashboard is not None


# ---------------------------------------------------------------------------
# Read-only getters + member listings (cheap per-tree coverage)
# ---------------------------------------------------------------------------


@respx.mock
async def test_metadata_show_indicator_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`show_indicator` fetches one Indicator by UID, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    respx.get(f"{_HOST}/api/indicators/IND0000001").mock(
        return_value=httpx.Response(200, json={"id": "IND0000001", "name": "ANC coverage"}),
    )

    indicator = await service.show_indicator(resolve_profile("probe"), "IND0000001")

    assert indicator.id == "IND0000001"


@respx.mock
async def test_metadata_show_program_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`show_program` fetches one Program by UID, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    respx.get(f"{_HOST}/api/programs/PRGanc0001").mock(
        return_value=httpx.Response(200, json={"id": "PRGanc0001", "name": "ANC program"}),
    )

    program = await service.show_program(resolve_profile("probe"), "PRGanc0001")

    assert program.id == "PRGanc0001"


@respx.mock
async def test_metadata_show_program_stage_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`show_program_stage` fetches one ProgramStage by UID, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    respx.get(f"{_HOST}/api/programStages/PS00000001").mock(
        return_value=httpx.Response(200, json={"id": "PS00000001", "name": "Visit"}),
    )

    stage = await service.show_program_stage(resolve_profile("probe"), "PS00000001")

    assert stage.id == "PS00000001"


@respx.mock
async def test_metadata_show_data_set_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`show_data_set` fetches one DataSet by UID, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    respx.get(f"{_HOST}/api/dataSets/DS00000001").mock(
        return_value=httpx.Response(200, json={"id": "DS00000001", "name": "Monthly"}),
    )

    data_set = await service.show_data_set(resolve_profile("probe"), "DS00000001")

    assert data_set.id == "DS00000001"


@respx.mock
async def test_metadata_show_category_combo_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`show_category_combo` fetches one CategoryCombo by UID, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    respx.get(f"{_HOST}/api/categoryCombos/CC00000001").mock(
        return_value=httpx.Response(200, json={"id": "CC00000001", "name": "Sex x Age"}),
    )

    combo = await service.show_category_combo(resolve_profile("probe"), "CC00000001")

    assert combo.id == "CC00000001"


@respx.mock
async def test_metadata_show_tracked_entity_type_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`show_tracked_entity_type` fetches one TrackedEntityType by UID, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    respx.get(f"{_HOST}/api/trackedEntityTypes/TET0000001").mock(
        return_value=httpx.Response(200, json={"id": "TET0000001", "name": "Person"}),
    )

    tet = await service.show_tracked_entity_type(resolve_profile("probe"), "TET0000001")

    assert tet.id == "TET0000001"


@respx.mock
async def test_metadata_list_indicator_group_members_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`list_indicator_group_members` pages indicators in one group, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    respx.get(f"{_HOST}/api/indicators").mock(
        return_value=httpx.Response(200, json={"indicators": [{"id": "IND0000001", "name": "ANC coverage"}]}),
    )

    members = await service.list_indicator_group_members(resolve_profile("probe"), "ING0000001")

    assert [member.id for member in members] == ["IND0000001"]


@respx.mock
async def test_metadata_list_data_element_group_members_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`list_data_element_group_members` pages data elements in one group, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    respx.get(f"{_HOST}/api/dataElements").mock(
        return_value=httpx.Response(200, json={"dataElements": [{"id": "DE_A", "name": "ANC visits"}]}),
    )

    members = await service.list_data_element_group_members(resolve_profile("probe"), "DEG0000001")

    assert [member.id for member in members] == ["DE_A"]


# ---------------------------------------------------------------------------
# OrganisationUnitLevel reads + by-level upsert
# ---------------------------------------------------------------------------


@respx.mock
async def test_metadata_show_organisation_unit_level_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`show_organisation_unit_level` fetches one level row by UID, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    respx.get(f"{_HOST}/api/organisationUnitLevels/OULvl000001").mock(
        return_value=httpx.Response(200, json={"id": "OULvl000001", "name": "District", "level": 2}),
    )

    level = await service.show_organisation_unit_level(resolve_profile("probe"), "OULvl000001")

    assert level is not None
    assert level.id == "OULvl000001"


@respx.mock
async def test_metadata_show_organisation_unit_level_by_level_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`show_organisation_unit_level_by_level` resolves a level row by numeric depth, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    respx.get(f"{_HOST}/api/organisationUnitLevels").mock(
        return_value=httpx.Response(
            200, json={"organisationUnitLevels": [{"id": "OULvl000001", "name": "District", "level": 2}]}
        ),
    )

    level = await service.show_organisation_unit_level_by_level(resolve_profile("probe"), 2)

    assert level is not None
    assert level.level == 2


@respx.mock
async def test_metadata_rename_organisation_unit_level_by_level_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`rename_organisation_unit_level_by_level` upserts the label at a depth, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    respx.get(f"{_HOST}/api/organisationUnitLevels").mock(
        return_value=httpx.Response(
            200, json={"organisationUnitLevels": [{"id": "OULvl000001", "name": "Old", "level": 2}]}
        ),
    )
    respx.get(f"{_HOST}/api/organisationUnitLevels/OULvl000001").mock(
        return_value=httpx.Response(200, json={"id": "OULvl000001", "name": "Old", "level": 2}),
    )
    put = respx.put(f"{_HOST}/api/organisationUnitLevels/OULvl000001").mock(return_value=httpx.Response(200, json={}))

    await service.rename_organisation_unit_level_by_level(resolve_profile("probe"), 2, name="District")

    assert put.called
    assert json.loads(put.calls.last.request.content)["name"] == "District"


# ---------------------------------------------------------------------------
# OptionSet resolution + option lookup + program-rule reads
# ---------------------------------------------------------------------------


@respx.mock
async def test_metadata_resolve_option_set_uid_by_code_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`resolve_option_set_uid` resolves a business code to a UID, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    respx.get(f"{_HOST}/api/optionSets").mock(
        return_value=httpx.Response(200, json={"optionSets": [{"id": "opt01234567", "code": "YN"}]}),
    )

    resolved = await service.resolve_option_set_uid(resolve_profile("probe"), "YN")

    assert resolved == "opt01234567"


@respx.mock
async def test_metadata_find_option_in_set_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`find_option_in_set` pinpoints one option by code within a set, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    respx.get(f"{_HOST}/api/options").mock(
        return_value=httpx.Response(200, json={"options": [{"id": "optAyesvalue", "code": "Y", "name": "Yes"}]}),
    )

    option = await service.find_option_in_set(
        resolve_profile("probe"), option_set_uid_or_code="opt01234567", option_code="Y"
    )

    assert option is not None
    assert option.code == "Y"


@respx.mock
async def test_metadata_show_program_rule_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`show_program_rule` fetches one ProgramRule by UID, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    respx.get(f"{_HOST}/api/programRules/PRule00001").mock(
        return_value=httpx.Response(200, json={"id": "PRule00001", "name": "Hide field"}),
    )

    rule = await service.show_program_rule(resolve_profile("probe"), "PRule00001")

    assert rule.id == "PRule00001"


@respx.mock
async def test_metadata_list_program_rule_variables_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`list_program_rule_variables` lists the variables in scope for a program, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    respx.get(f"{_HOST}/api/programRuleVariables").mock(
        return_value=httpx.Response(200, json={"programRuleVariables": [{"id": "PRV0000001", "name": "currentValue"}]}),
    )

    variables = await service.list_program_rule_variables(resolve_profile("probe"), "PRGanc0001")

    assert [variable.id for variable in variables] == ["PRV0000001"]


# ---------------------------------------------------------------------------
# Remaining cheap getters (per-tree coverage)
# ---------------------------------------------------------------------------


@respx.mock
async def test_metadata_show_legend_set_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`show_legend_set` fetches one LegendSet by UID, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    respx.get(f"{_HOST}/api/legendSets/LS00000001").mock(
        return_value=httpx.Response(200, json={"id": "LS00000001", "name": "Coverage"}),
    )

    legend_set = await service.show_legend_set(resolve_profile("probe"), "LS00000001")

    assert legend_set.id == "LS00000001"


@respx.mock
async def test_metadata_show_validation_rule_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`show_validation_rule` fetches one ValidationRule by UID, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    respx.get(f"{_HOST}/api/validationRules/VR00000001").mock(
        return_value=httpx.Response(200, json={"id": "VR00000001", "name": "ANC consistency"}),
    )

    rule = await service.show_validation_rule(resolve_profile("probe"), "VR00000001")

    assert rule.id == "VR00000001"


@respx.mock
async def test_metadata_show_predictor_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`show_predictor` fetches one Predictor by UID, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    respx.get(f"{_HOST}/api/predictors/PRED000001").mock(
        return_value=httpx.Response(200, json={"id": "PRED000001", "name": "ANC forecast"}),
    )

    predictor = await service.show_predictor(resolve_profile("probe"), "PRED000001")

    assert predictor.id == "PRED000001"


@respx.mock
async def test_metadata_show_category_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`show_category` fetches one Category by UID, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    respx.get(f"{_HOST}/api/categories/CAT0000001").mock(
        return_value=httpx.Response(200, json={"id": "CAT0000001", "name": "Sex"}),
    )

    category = await service.show_category(resolve_profile("probe"), "CAT0000001")

    assert category.id == "CAT0000001"


@respx.mock
async def test_metadata_show_category_option_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`show_category_option` fetches one CategoryOption by UID, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    respx.get(f"{_HOST}/api/categoryOptions/CO00000001").mock(
        return_value=httpx.Response(200, json={"id": "CO00000001", "name": "Female"}),
    )

    option = await service.show_category_option(resolve_profile("probe"), "CO00000001")

    assert option.id == "CO00000001"


@respx.mock
async def test_metadata_show_section_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`show_section` fetches one Section by UID, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    respx.get(f"{_HOST}/api/sections/SEC0000001").mock(
        return_value=httpx.Response(200, json={"id": "SEC0000001", "name": "Vaccines"}),
    )

    section = await service.show_section(resolve_profile("probe"), "SEC0000001")

    assert section.id == "SEC0000001"


@respx.mock
async def test_metadata_show_tracked_entity_attribute_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`show_tracked_entity_attribute` fetches one TEA by UID, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    respx.get(f"{_HOST}/api/trackedEntityAttributes/TEA0000001").mock(
        return_value=httpx.Response(200, json={"id": "TEA0000001", "name": "First name"}),
    )

    attribute = await service.show_tracked_entity_attribute(resolve_profile("probe"), "TEA0000001")

    assert attribute.id == "TEA0000001"


@respx.mock
async def test_metadata_show_program_indicator_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`show_program_indicator` fetches one ProgramIndicator by UID, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    respx.get(f"{_HOST}/api/programIndicators/PI00000001").mock(
        return_value=httpx.Response(200, json={"id": "PI00000001", "name": "Visits count"}),
    )

    indicator = await service.show_program_indicator(resolve_profile("probe"), "PI00000001")

    assert indicator.id == "PI00000001"


@respx.mock
async def test_metadata_show_organisation_unit_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`show_organisation_unit` fetches one OrganisationUnit by UID, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    respx.get(f"{_HOST}/api/organisationUnits/OUchild0001").mock(
        return_value=httpx.Response(200, json={"id": "OUchild0001", "name": "Clinic"}),
    )

    org_unit = await service.show_organisation_unit(resolve_profile("probe"), "OUchild0001")

    assert org_unit.id == "OUchild0001"
