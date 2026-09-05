"""Unit tests for dhis2w-mcp server construction."""

from __future__ import annotations

from dhis2w_mcp.server import build_server


def test_build_server_registers_plugins() -> None:
    """Build server registers plugins."""
    server = build_server()
    assert server is not None


async def test_read_tools_are_annotated_read_only() -> None:
    """A post-registration pass stamps `readOnlyHint=True` on read tools so kodo's gate skips them.

    Uses the same tool names `test_readonly.py` pins so the classifier's verdicts are known: `*_get`
    reads become read-only-hinted; `*_create`/`*_delete`/`set_status` writes carry `readOnlyHint=False`.
    """
    server = build_server()
    tools = {tool.name: tool for tool in await server.list_tools(run_middleware=False)}

    for read_name in ("metadata_data_element_get", "metadata_data_set_get", "metadata_list"):
        annotations = tools[read_name].annotations
        assert annotations is not None and annotations.read_only_hint is True

    for write_name in ("metadata_data_element_create", "metadata_data_set_delete", "messaging_set_status"):
        annotations = tools[write_name].annotations
        assert annotations is not None and annotations.read_only_hint is False
