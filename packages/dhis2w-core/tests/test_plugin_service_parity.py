"""Per-version core plugin service parity — exercise each version's plugin service module.

Where `test_v{41,43}_plugin_smoke` only checks that imports resolve + the plugin set is intact,
these run the actual service code against all three trees (via the `core_version` /
`plugin_service` fixtures in conftest), so v41/v43 plugin coverage is measured, not just smoke.
Mocked (respx) — no live stack.
"""

from __future__ import annotations

from collections.abc import Callable
from types import ModuleType

import httpx
import pytest
import respx
from dhis2w_core.profile import resolve_profile


@respx.mock
async def test_metadata_bulk_rename_service(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`metadata.bulk_rename_metadata` prefixes + patches matched rows, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("metadata")
    respx.get("https://dhis2.example/api/dataElements").mock(
        return_value=httpx.Response(
            200,
            json={
                "dataElements": [
                    {"id": "DE_A", "name": "ANC visits", "shortName": "ANCv"},
                    {"id": "DE_B", "name": "BCG doses", "shortName": "BCGd"},
                ],
            },
        ),
    )
    patch_a = respx.patch("https://dhis2.example/api/dataElements/DE_A").mock(return_value=httpx.Response(200, json={}))
    patch_b = respx.patch("https://dhis2.example/api/dataElements/DE_B").mock(return_value=httpx.Response(200, json={}))

    result = await service.bulk_rename_metadata(
        resolve_profile("probe"),
        "dataElements",
        filters=["name:like:visits"],
        name_prefix="[MoH] ",
    )
    assert result.matched == 2
    assert result.dry_run is False
    assert result.entries[0].name_after == "[MoH] ANC visits"
    assert patch_a.called and patch_b.called


async def test_metadata_bulk_rename_requires_a_mutation(plugin_service: Callable[[str], ModuleType]) -> None:
    """The no-mutation guard raises on every version tree (no network)."""
    service = plugin_service("metadata")
    with pytest.raises(ValueError, match="at least one of"):
        await service.bulk_rename_metadata(profile=None, resource="dataElements")
