"""Tests for the shared TrackedEntityType listing service (CLI + MCP both route through it)."""

from __future__ import annotations

from collections.abc import Callable
from types import ModuleType

import httpx
import respx
from dhis2w_core.profile import resolve_profile

_HOST = "https://dhis2.example"


@respx.mock
async def test_list_tracked_entity_types_returns_typed_summaries(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`list_tracked_entity_types` parses the envelope into typed summaries, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("tracker")
    route = respx.get(f"{_HOST}/api/trackedEntityTypes").mock(
        return_value=httpx.Response(
            200,
            json={
                "trackedEntityTypes": [
                    {"id": "tet01234567", "name": "Person", "description": "A person"},
                    {"id": "tet76543210", "name": "Case"},
                ]
            },
        ),
    )

    types = await service.list_tracked_entity_types(resolve_profile("probe"))

    assert len(types) == 2
    assert types[0].id == "tet01234567"
    assert types[0].name == "Person"
    assert types[0].description == "A person"
    assert types[1].id == "tet76543210"
    assert types[1].description is None
    params = route.calls.last.request.url.params
    assert params["fields"] == "id,name,description"
    assert params["paging"] == "false"
