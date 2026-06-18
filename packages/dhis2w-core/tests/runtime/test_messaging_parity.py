"""Per-version parity for the `messaging` plugin service — exercise every public function on all trees.

Mirrors the v42-only `tests/messaging/test_messaging_plugin.py` routes + assertions, but resolves the
service per `core_version` (v41/v42/v43) so the v41/v43 service code is actually executed and counted,
not just smoke-imported. The three service trees are byte-identical copies (only the import version
differs), so the assertions are the same on every tree. Mocked (respx); no live stack.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from types import ModuleType

import httpx
import respx
from dhis2w_core.profile import resolve_profile

_HOST = "https://dhis2.example"


@respx.mock
async def test_list_conversations_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`list_conversations` unwraps the `{messageConversations: [...]}` envelope, on every tree."""
    mock_system_info(core_version)
    service = plugin_service("messaging")
    route = respx.get(f"{_HOST}/api/messageConversations").mock(
        return_value=httpx.Response(
            200,
            json={"messageConversations": [{"id": "convUid001", "subject": "hi", "messageCount": 1}]},
        ),
    )

    rows = await service.list_conversations(resolve_profile("probe"), filter="read:eq:false")

    assert [c.id for c in rows] == ["convUid001"]
    assert route.calls.last.request.url.params["filter"] == "read:eq:false"


@respx.mock
async def test_get_conversation_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`get_conversation` fetches one conversation by UID, on every tree."""
    mock_system_info(core_version)
    service = plugin_service("messaging")
    route = respx.get(f"{_HOST}/api/messageConversations/convUid001").mock(
        return_value=httpx.Response(200, json={"id": "convUid001", "subject": "hi", "messageCount": 1}),
    )

    conv = await service.get_conversation(resolve_profile("probe"), "convUid001")

    assert conv.id == "convUid001"
    assert route.called


@respx.mock
async def test_send_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`send` POSTs the body, resolves the Location header, then fetches the typed conversation, on every tree."""
    mock_system_info(core_version)
    service = plugin_service("messaging")
    created_uid = "newConv001"
    post_route = respx.post(f"{_HOST}/api/messageConversations").mock(
        return_value=httpx.Response(
            201,
            json={"status": "OK", "httpStatus": "Created"},
            headers={"location": f"{_HOST}/api/messageConversations/{created_uid}"},
        ),
    )
    respx.get(f"{_HOST}/api/messageConversations/{created_uid}").mock(
        return_value=httpx.Response(200, json={"id": created_uid, "subject": "s", "messageCount": 1}),
    )

    conv = await service.send(resolve_profile("probe"), subject="s", text="t", users=["userUid001"])

    assert conv.id == created_uid
    body = json.loads(post_route.calls.last.request.content)
    assert body["subject"] == "s"
    assert body["users"] == [{"id": "userUid001"}]


@respx.mock
async def test_reply_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`reply` POSTs the plain-text body to /api/messageConversations/{uid}, on every tree."""
    mock_system_info(core_version)
    service = plugin_service("messaging")
    route = respx.post(f"{_HOST}/api/messageConversations/convUid001").mock(
        return_value=httpx.Response(201, json={"status": "OK", "httpStatus": "Created", "httpStatusCode": 201}),
    )

    response = await service.reply(resolve_profile("probe"), "convUid001", text="thanks")

    assert response.status == "OK"
    assert route.calls.last.request.content == b"thanks"


@respx.mock
async def test_mark_read_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`mark_read` POSTs a single UID as `[uid]` to the bulk read endpoint, on every tree."""
    mock_system_info(core_version)
    service = plugin_service("messaging")
    route = respx.post(f"{_HOST}/api/messageConversations/read").mock(
        return_value=httpx.Response(200, json={"status": "OK", "httpStatus": "OK", "httpStatusCode": 200}),
    )

    response = await service.mark_read(resolve_profile("probe"), "convUid001")

    assert response.status == "OK"
    assert json.loads(route.calls.last.request.content) == ["convUid001"]


@respx.mock
async def test_mark_unread_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`mark_unread` POSTs a single UID as `[uid]` to the bulk unread endpoint, on every tree."""
    mock_system_info(core_version)
    service = plugin_service("messaging")
    route = respx.post(f"{_HOST}/api/messageConversations/unread").mock(
        return_value=httpx.Response(200, json={"status": "OK", "httpStatus": "OK", "httpStatusCode": 200}),
    )

    response = await service.mark_unread(resolve_profile("probe"), "convUid001")

    assert response.status == "OK"
    assert json.loads(route.calls.last.request.content) == ["convUid001"]


@respx.mock
async def test_delete_conversation_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`delete_conversation` DELETEs /api/messageConversations/{uid}, on every tree."""
    mock_system_info(core_version)
    service = plugin_service("messaging")
    route = respx.delete(f"{_HOST}/api/messageConversations/convUid001").mock(
        return_value=httpx.Response(200, json={"status": "OK", "httpStatus": "OK", "httpStatusCode": 200}),
    )

    await service.delete_conversation(resolve_profile("probe"), "convUid001")

    assert route.called


@respx.mock
async def test_set_priority_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`set_priority` POSTs the priority as a query param, on every tree."""
    mock_system_info(core_version)
    service = plugin_service("messaging")
    route = respx.post(f"{_HOST}/api/messageConversations/convUid001/priority").mock(
        return_value=httpx.Response(200, json={"status": "OK"}),
    )

    await service.set_priority(resolve_profile("probe"), "convUid001", "HIGH")

    assert route.calls.last.request.url.params["messageConversationPriority"] == "HIGH"


@respx.mock
async def test_set_status_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`set_status` POSTs the status as a query param, on every tree."""
    mock_system_info(core_version)
    service = plugin_service("messaging")
    route = respx.post(f"{_HOST}/api/messageConversations/convUid001/status").mock(
        return_value=httpx.Response(200, json={"status": "OK"}),
    )

    await service.set_status(resolve_profile("probe"), "convUid001", "SOLVED")

    assert route.calls.last.request.url.params["messageConversationStatus"] == "SOLVED"


@respx.mock
async def test_assign_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`assign` POSTs the assignee UID as a query param, on every tree."""
    mock_system_info(core_version)
    service = plugin_service("messaging")
    route = respx.post(f"{_HOST}/api/messageConversations/convUid001/assign").mock(
        return_value=httpx.Response(200, json={"status": "OK"}),
    )

    await service.assign(resolve_profile("probe"), "convUid001", "userUid001")

    assert route.calls.last.request.url.params["userId"] == "userUid001"


@respx.mock
async def test_unassign_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`unassign` DELETEs the assign endpoint, on every tree."""
    mock_system_info(core_version)
    service = plugin_service("messaging")
    route = respx.delete(f"{_HOST}/api/messageConversations/convUid001/assign").mock(
        return_value=httpx.Response(200, json={"status": "OK"}),
    )

    await service.unassign(resolve_profile("probe"), "convUid001")

    assert route.called
