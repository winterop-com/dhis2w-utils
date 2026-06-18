"""Per-version parity for the `schema` plugin service — exercise every public function on all trees.

Mirrors the v42-only `tests/schema/test_schema_cli.py` introspection assertions, but resolves the
service per `core_version` (v41/v42/v43) so the v41/v43 service code is actually executed and counted,
not just smoke-imported. The three service trees are byte-identical copies (only the import version
differs), so the assertions are the same on every tree — no version-specific expectations. Mocked
(respx); no live stack.
"""

from __future__ import annotations

from collections.abc import Callable
from types import ModuleType

import respx
from dhis2w_core.profile import resolve_profile

_HOST = "https://dhis2.example"


@respx.mock
async def test_detect_version_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`detect_version` returns the server's auto-detected version key, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("schema")

    version = await service.detect_version(resolve_profile("probe"))

    assert version == core_version


@respx.mock
async def test_describe_type_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`describe_type` introspects the OAS tree into a typed `TypeSchema`, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("schema")

    schema = service.describe_type(core_version, "dataElement")

    assert schema is not None
    assert schema.name == "DataElement"
    assert schema.source == "oas"
    assert schema.version == core_version
    assert schema.field_count > 0
    assert {"code", "valueType", "domainType"} <= {field.name for field in schema.fields}


@respx.mock
async def test_search_types_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`search_types` returns close-match type names for a 'did you mean' hint, on every tree."""
    mock_system_info(core_version)
    service = plugin_service("schema")

    matches = service.search_types(core_version, "dataElementz")

    assert "DataElement" in matches


@respx.mock
async def test_unknown_fields_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`unknown_fields` flags bare unknown field names and skips known ones, on every tree."""
    mock_system_info(core_version)
    service = plugin_service("schema")

    flagged = service.unknown_fields(core_version, "dataElements", "id,name,code,bogusField")

    assert flagged == ["bogusField"]
