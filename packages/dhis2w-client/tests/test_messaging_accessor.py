"""Tests for `Dhis2Client.messaging` — DHIS2 /api/messageConversations."""

from __future__ import annotations

import json
from collections.abc import Callable

import httpx
import pytest
import respx
from dhis2w_client import BasicAuth, Dhis2Client


def _auth() -> BasicAuth:
    """Throwaway auth for test clients."""
    return BasicAuth(username="a", password="b")


@respx.mock
async def test_list_conversations_returns_typed_models(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """`list_conversations` parses the `messageConversations` array into typed objects."""
    mock_system_info(server_version)
    respx.get("https://dhis2.example/api/messageConversations").mock(
        return_value=httpx.Response(
            200,
            json={
                "messageConversations": [
                    {
                        "id": "convUidAAA001",
                        "subject": "Pilot rollout",
                        "read": False,
                        "messageType": "PRIVATE",
                        "messageCount": 3,
                    },
                    {
                        "id": "convUidBBB002",
                        "subject": "Coverage report",
                        "read": True,
                        "messageType": "TICKET",
                        "messageCount": 1,
                    },
                ],
            },
        ),
    )

    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        rows = await client.messaging.list_conversations()
    finally:
        await client.close()

    assert [c.id for c in rows] == ["convUidAAA001", "convUidBBB002"]
    assert rows[0].read is False
    assert rows[0].messageCount == 3


@respx.mock
async def test_list_conversations_forwards_filter_and_paging(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """`filter` / `page` / `page_size` flow through as DHIS2 query params."""
    mock_system_info(server_version)
    route = respx.get("https://dhis2.example/api/messageConversations").mock(
        return_value=httpx.Response(200, json={"messageConversations": []}),
    )

    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        await client.messaging.list_conversations(filter="read:eq:false", page=2, page_size=25)
    finally:
        await client.close()

    params = route.calls.last.request.url.params
    assert params["filter"] == "read:eq:false"
    assert params["page"] == "2"
    assert params["pageSize"] == "25"


@respx.mock
async def test_send_posts_every_recipient_type_and_parses_location_header(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """Users + userGroups + orgUnits + attachments land in body; UID comes from Location.

    DHIS2's `POST /api/messageConversations` returns just a status envelope
    (no `response.uid`); the created UID is on the 201 `Location` header
    (see BUGS.md #17). `send()` extracts it + GETs the conversation back so
    the caller receives a typed object.
    """
    mock_system_info(server_version)
    created_uid = "newConvUid01"
    post_route = respx.post("https://dhis2.example/api/messageConversations").mock(
        return_value=httpx.Response(
            201,
            json={"status": "OK", "httpStatus": "Created", "httpStatusCode": 201},
            headers={"location": f"https://dhis2.example/api/messageConversations/{created_uid}"},
        ),
    )
    respx.get(f"https://dhis2.example/api/messageConversations/{created_uid}").mock(
        return_value=httpx.Response(
            200,
            json={"id": created_uid, "subject": "Hello", "messageCount": 1},
        ),
    )

    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        conversation = await client.messaging.send(
            subject="Hello",
            text="Hi team",
            users=["userUid00001", "userUid00002"],
            user_groups=["groupUid0001"],
            organisation_units=["ouUid0000001"],
            attachments=["fileResUid01"],
        )
    finally:
        await client.close()

    body = json.loads(post_route.calls.last.request.content)
    assert body["subject"] == "Hello"
    assert body["text"] == "Hi team"
    assert body["users"] == [{"id": "userUid00001"}, {"id": "userUid00002"}]
    assert body["userGroups"] == [{"id": "groupUid0001"}]
    assert body["organisationUnits"] == [{"id": "ouUid0000001"}]
    assert body["attachments"] == [{"id": "fileResUid01"}]
    assert conversation.id == created_uid


@respx.mock
async def test_send_raises_when_location_header_missing(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """Without a Location header there's no way to look up the conversation — fail loud."""
    mock_system_info(server_version)
    respx.post("https://dhis2.example/api/messageConversations").mock(
        return_value=httpx.Response(201, json={"status": "OK"}),
    )

    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        with pytest.raises(RuntimeError, match="no Location header"):
            await client.messaging.send(subject="x", text="y", users=["userUidNoHd01"])
    finally:
        await client.close()


async def test_send_rejects_empty_recipients() -> None:
    """`send` without any recipient list raises — DHIS2 silently drops such messages."""
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    with pytest.raises(ValueError, match="at least one recipient"):
        await client.messaging.send(subject="x", text="y")


@respx.mock
async def test_reply_posts_plain_text_body(server_version: str, mock_system_info: Callable[..., None]) -> None:
    """`reply` POSTs the text as raw `text/plain` bytes — DHIS2 v42 ignores JSON bodies here."""
    mock_system_info(server_version)
    route = respx.post("https://dhis2.example/api/messageConversations/convUidAAA001").mock(
        return_value=httpx.Response(201, json={"status": "OK", "httpStatus": "Created"}),
    )

    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        envelope = await client.messaging.reply("convUidAAA001", text="thanks — reviewed")
    finally:
        await client.close()

    # Em dash is 3-byte UTF-8 (0xE2 0x80 0x94); confirm encode() path + header.
    assert route.calls.last.request.content == "thanks — reviewed".encode()
    assert route.calls.last.request.headers["content-type"] == "text/plain"
    assert envelope.status == "OK"


@respx.mock
async def test_mark_read_single_uid_wraps_in_list(server_version: str, mock_system_info: Callable[..., None]) -> None:
    """A single UID string is wrapped as `[uid]` to match DHIS2's bulk-array body shape."""
    mock_system_info(server_version)
    route = respx.post("https://dhis2.example/api/messageConversations/read").mock(
        return_value=httpx.Response(200, json={"status": "OK", "httpStatus": "OK", "httpStatusCode": 200}),
    )

    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        await client.messaging.mark_read("convUidAAA001")
    finally:
        await client.close()

    body = json.loads(route.calls.last.request.content)
    assert body == ["convUidAAA001"]


@respx.mock
async def test_mark_unread_list_input(server_version: str, mock_system_info: Callable[..., None]) -> None:
    """A list of UIDs maps 1:1 onto the JSON body."""
    mock_system_info(server_version)
    route = respx.post("https://dhis2.example/api/messageConversations/unread").mock(
        return_value=httpx.Response(200, json={"status": "OK", "httpStatus": "OK", "httpStatusCode": 200}),
    )

    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        await client.messaging.mark_unread(["convUidA", "convUidB"])
    finally:
        await client.close()

    body = json.loads(route.calls.last.request.content)
    assert body == ["convUidA", "convUidB"]


@respx.mock
async def test_get_conversation_returns_typed_thread(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """Single-conversation GET parses the thread via the typed MessageConversation model."""
    mock_system_info(server_version)
    respx.get("https://dhis2.example/api/messageConversations/convUidAAA001").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "convUidAAA001",
                "subject": "Pilot rollout",
                "messageType": "PRIVATE",
                "messageCount": 2,
                "messages": [
                    {"id": "m1", "text": "hello", "created": "2026-04-20T10:00:00.000"},
                    {"id": "m2", "text": "world", "created": "2026-04-20T10:05:00.000"},
                ],
            },
        ),
    )

    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        conv = await client.messaging.get_conversation("convUidAAA001")
    finally:
        await client.close()

    assert conv.id == "convUidAAA001"
    assert conv.messageCount == 2
    assert conv.messages is not None
    assert len(conv.messages) == 2
    assert conv.messages[0].text == "hello"


@respx.mock
async def test_set_priority_passes_query_param(server_version: str, mock_system_info: Callable[..., None]) -> None:
    """`set_priority` POSTs `/priority` with the enum as a query parameter."""
    mock_system_info(server_version)
    route = respx.post("https://dhis2.example/api/messageConversations/convUidAAA001/priority").mock(
        return_value=httpx.Response(200, text=""),
    )

    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        await client.messaging.set_priority("convUidAAA001", "HIGH")
    finally:
        await client.close()

    assert route.calls.last.request.url.params["messageConversationPriority"] == "HIGH"


@respx.mock
async def test_set_status_passes_query_param(server_version: str, mock_system_info: Callable[..., None]) -> None:
    """`set_status` POSTs `/status` with the enum as a query parameter."""
    mock_system_info(server_version)
    route = respx.post("https://dhis2.example/api/messageConversations/convUidAAA001/status").mock(
        return_value=httpx.Response(200, text=""),
    )

    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        await client.messaging.set_status("convUidAAA001", "OPEN")
    finally:
        await client.close()

    assert route.calls.last.request.url.params["messageConversationStatus"] == "OPEN"


@respx.mock
async def test_assign_and_unassign(server_version: str, mock_system_info: Callable[..., None]) -> None:
    """`assign` POSTs `/assign?userId=...`; `unassign` DELETEs the same path."""
    mock_system_info(server_version)
    assign_route = respx.post("https://dhis2.example/api/messageConversations/convUidAAA001/assign").mock(
        return_value=httpx.Response(200, text=""),
    )
    unassign_route = respx.delete("https://dhis2.example/api/messageConversations/convUidAAA001/assign").mock(
        return_value=httpx.Response(200, text=""),
    )

    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        await client.messaging.assign("convUidAAA001", "userUidBBB002")
        await client.messaging.unassign("convUidAAA001")
    finally:
        await client.close()

    assert assign_route.calls.last.request.url.params["userId"] == "userUidBBB002"
    assert unassign_route.call_count == 1


@respx.mock
async def test_delete_conversation(server_version: str, mock_system_info: Callable[..., None]) -> None:
    """Delete fires DELETE on the conversation path + returns None."""
    mock_system_info(server_version)
    route = respx.delete("https://dhis2.example/api/messageConversations/convUidAAA001").mock(
        return_value=httpx.Response(200, json={}),
    )

    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        await client.messaging.delete_conversation("convUidAAA001")
    finally:
        await client.close()

    assert route.call_count == 1
