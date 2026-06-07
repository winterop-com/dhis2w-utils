"""Unit tests for `build_category_combo` — respx-mocked end-to-end."""

from __future__ import annotations

import json as _json
from collections.abc import Callable

import httpx
import respx
from dhis2w_client import (
    BasicAuth,
    CategoryComboBuildSpec,
    CategoryOptionSpec,
    CategorySpec,
    Dhis2Client,
    build_category_combo,
)


def _auth() -> BasicAuth:
    return BasicAuth(username="admin", password="district")


def _spec() -> CategoryComboBuildSpec:
    return CategoryComboBuildSpec(
        name="Sex x Modality",
        categories=[
            CategorySpec(
                name="Sex",
                short_name="Sex",
                options=[CategoryOptionSpec(name="Male"), CategoryOptionSpec(name="Female")],
            ),
            CategorySpec(
                name="Modality",
                short_name="Mod",
                options=[
                    CategoryOptionSpec(name="Inpatient"),
                    CategoryOptionSpec(name="Outpatient"),
                    CategoryOptionSpec(name="Outreach"),
                ],
            ),
        ],
    )


def _empty_filter_response(collection: str) -> httpx.Response:
    return httpx.Response(200, json={collection: []})


@respx.mock
async def test_build_creates_full_stack_when_nothing_exists(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """First-run path: every option, category, and the combo are created from scratch."""
    mock_system_info(server_version)
    # All filter lookups return empty — nothing exists yet.
    respx.get("https://dhis2.example/api/categoryOptions").mock(return_value=_empty_filter_response("categoryOptions"))
    respx.get("https://dhis2.example/api/categories").mock(return_value=_empty_filter_response("categories"))
    respx.get("https://dhis2.example/api/categoryCombos").mock(return_value=_empty_filter_response("categoryCombos"))

    # CategoryOption creates: 5 in total. Stub each WebMessage with a fresh UID.
    option_uids = iter(["CO_M", "CO_F", "CO_IN", "CO_OUT", "CO_REACH"])
    respx.post("https://dhis2.example/api/categoryOptions").mock(
        side_effect=lambda req: httpx.Response(
            201, json={"status": "OK", "httpStatusCode": 201, "response": {"uid": next(option_uids)}}
        ),
    )
    co_get_payload = {"id": "PLACEHOLDER", "name": "x", "shortName": "x", "categoryOptionGroups": [], "categories": []}
    for uid in ["CO_M", "CO_F", "CO_IN", "CO_OUT", "CO_REACH"]:
        respx.get(f"https://dhis2.example/api/categoryOptions/{uid}").mock(
            return_value=httpx.Response(200, json={**co_get_payload, "id": uid}),
        )

    # Category creates: 2.
    category_uids = iter(["CAT_SEX", "CAT_MOD"])
    respx.post("https://dhis2.example/api/categories").mock(
        side_effect=lambda req: httpx.Response(
            201, json={"status": "OK", "httpStatusCode": 201, "response": {"uid": next(category_uids)}}
        ),
    )
    respx.get("https://dhis2.example/api/categories/CAT_SEX").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "CAT_SEX",
                "name": "Sex",
                "shortName": "Sex",
                "dataDimensionType": "DISAGGREGATION",
                "categoryOptions": [{"id": "CO_M"}, {"id": "CO_F"}],
            },
        ),
    )
    respx.get("https://dhis2.example/api/categories/CAT_MOD").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "CAT_MOD",
                "name": "Modality",
                "shortName": "Mod",
                "dataDimensionType": "DISAGGREGATION",
                "categoryOptions": [{"id": "CO_IN"}, {"id": "CO_OUT"}, {"id": "CO_REACH"}],
            },
        ),
    )

    # Combo create + COC matrix poll. Six COCs (2 sex * 3 mod).
    respx.post("https://dhis2.example/api/categoryCombos").mock(
        return_value=httpx.Response(201, json={"status": "OK", "httpStatusCode": 201, "response": {"uid": "CC_NEW"}}),
    )
    respx.get("https://dhis2.example/api/categoryCombos/CC_NEW").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "CC_NEW",
                "name": "Sex x Modality",
                "categories": [{"id": "CAT_SEX"}, {"id": "CAT_MOD"}],
                "categoryOptionCombos": [{"id": f"COC_{n}"} for n in range(6)],
            },
        ),
    )
    # wait_for_coc_generation triggers the v43 maintenance update first, then polls.
    respx.post("https://dhis2.example/api/maintenance/categoryOptionComboUpdate").mock(
        return_value=httpx.Response(200, json={"httpStatus": "OK"}),
    )
    respx.get("https://dhis2.example/api/categoryOptionCombos").mock(
        return_value=httpx.Response(
            200,
            json={"categoryOptionCombos": [{"id": f"COC_{n}"} for n in range(6)]},
        ),
    )

    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        result = await build_category_combo(client, _spec(), timeout_seconds=5.0, poll_interval_seconds=0.01)
    finally:
        await client.close()

    assert result.combo_uid == "CC_NEW"
    assert result.combo_created is True
    assert result.expected_coc_count == 6
    assert result.coc_count == 6
    assert result.category_uids == ["CAT_SEX", "CAT_MOD"]
    sex_entry = result.categories[0]
    assert sex_entry.created is True
    assert sex_entry.option_uids == ["CO_M", "CO_F"]
    assert sex_entry.created_option_uids == ["CO_M", "CO_F"]
    mod_entry = result.categories[1]
    assert mod_entry.option_uids == ["CO_IN", "CO_OUT", "CO_REACH"]


@respx.mock
async def test_build_reuses_everything_when_already_present(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """Idempotent path: every option / category / combo already exists by name; no creates fire."""
    mock_system_info(server_version)

    def _option_lookup(req: httpx.Request) -> httpx.Response:
        name_filter = req.url.params.get("filter", "")
        # filter format: "name:eq:<NAME>"
        name = name_filter.split(":", 2)[2] if name_filter.startswith("name:eq:") else ""
        uid_by_name = {
            "Male": "CO_M",
            "Female": "CO_F",
            "Inpatient": "CO_IN",
            "Outpatient": "CO_OUT",
            "Outreach": "CO_REACH",
        }
        return httpx.Response(
            200,
            json={"categoryOptions": [{"id": uid_by_name[name], "name": name}]}
            if name in uid_by_name
            else {"categoryOptions": []},
        )

    respx.get("https://dhis2.example/api/categoryOptions").mock(side_effect=_option_lookup)

    def _category_lookup(req: httpx.Request) -> httpx.Response:
        name_filter = req.url.params.get("filter", "")
        name = name_filter.split(":", 2)[2] if name_filter.startswith("name:eq:") else ""
        if name == "Sex":
            return httpx.Response(
                200,
                json={
                    "categories": [
                        {"id": "CAT_SEX", "name": "Sex", "categoryOptions": [{"id": "CO_M"}, {"id": "CO_F"}]}
                    ]
                },
            )
        if name == "Modality":
            return httpx.Response(
                200,
                json={
                    "categories": [
                        {
                            "id": "CAT_MOD",
                            "name": "Modality",
                            "categoryOptions": [
                                {"id": "CO_IN"},
                                {"id": "CO_OUT"},
                                {"id": "CO_REACH"},
                            ],
                        }
                    ]
                },
            )
        return httpx.Response(200, json={"categories": []})

    respx.get("https://dhis2.example/api/categories").mock(side_effect=_category_lookup)
    respx.get("https://dhis2.example/api/categoryCombos").mock(
        return_value=httpx.Response(
            200,
            json={
                "categoryCombos": [
                    {
                        "id": "CC_EXIST",
                        "name": "Sex x Modality",
                        "categories": [{"id": "CAT_SEX"}, {"id": "CAT_MOD"}],
                    }
                ]
            },
        ),
    )
    respx.get("https://dhis2.example/api/categoryCombos/CC_EXIST").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "CC_EXIST",
                "name": "Sex x Modality",
                "categories": [{"id": "CAT_SEX"}, {"id": "CAT_MOD"}],
                "categoryOptionCombos": [{"id": f"COC_{n}"} for n in range(6)],
            },
        ),
    )
    # wait_for_coc_generation triggers the v43 maintenance update first, then polls.
    respx.post("https://dhis2.example/api/maintenance/categoryOptionComboUpdate").mock(
        return_value=httpx.Response(200, json={"httpStatus": "OK"}),
    )
    respx.get("https://dhis2.example/api/categoryOptionCombos").mock(
        return_value=httpx.Response(
            200,
            json={"categoryOptionCombos": [{"id": f"COC_{n}"} for n in range(6)]},
        ),
    )

    create_option_route = respx.post("https://dhis2.example/api/categoryOptions").mock()
    create_category_route = respx.post("https://dhis2.example/api/categories").mock()
    create_combo_route = respx.post("https://dhis2.example/api/categoryCombos").mock()

    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        result = await build_category_combo(client, _spec(), timeout_seconds=5.0, poll_interval_seconds=0.01)
    finally:
        await client.close()

    assert result.combo_uid == "CC_EXIST"
    assert result.combo_created is False
    assert result.combo_appended_category_uids == []
    for entry in result.categories:
        assert entry.created is False
        assert entry.created_option_uids == []
        assert entry.appended_option_uids == []
    assert not create_option_route.called
    assert not create_category_route.called
    assert not create_combo_route.called


def test_build_spec_rejects_empty_categories() -> None:
    """Pydantic validation enforces at least one Category and one Option per category."""
    import pytest

    with pytest.raises(ValueError):
        CategoryComboBuildSpec(name="Empty", categories=[])
    with pytest.raises(ValueError):
        CategorySpec(name="EmptyCat", options=[])


def test_spec_serialises_to_json_and_round_trips() -> None:
    """Spec is JSON-serialisable for CLI / MCP transport."""
    spec = _spec()
    payload = spec.model_dump(mode="json")
    rehydrated = CategoryComboBuildSpec.model_validate(payload)
    assert rehydrated == spec
    # And as a JSON string:
    blob = spec.model_dump_json()
    assert "Sex x Modality" in blob
    assert _json.loads(blob)["categories"][0]["name"] == "Sex"
