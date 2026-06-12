"""Tests for the messaging plugin — CLI surface, service wiring, plugin descriptor."""

from __future__ import annotations

from collections.abc import Iterator

import httpx
import pytest
import respx
from dhis2w_cli.main import build_app
from dhis2w_core.profile import Profile
from dhis2w_core.v42.plugins.messaging import plugin, service
from dhis2w_core.v42.plugins.messaging.cli import app as messaging_app
from typer.testing import CliRunner


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Raw-env profile so `profile_from_env()` resolves without TOML."""
    for key in ("DHIS2_PROFILE", "DHIS2_URL", "DHIS2_PAT", "DHIS2_USERNAME", "DHIS2_PASSWORD"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("DHIS2_URL", "https://dhis2.example")
    monkeypatch.setenv("DHIS2_PAT", "test-token")
    yield


@pytest.fixture
def profile() -> Profile:
    """Minimal profile for service-layer tests."""
    return Profile(base_url="https://dhis2.example", auth="pat", token="test-token")


def _mock_preamble() -> None:
    """Connect-time probes."""
    respx.get("https://dhis2.example/").mock(return_value=httpx.Response(200, text=""))
    respx.get("https://dhis2.example/api/system/info").mock(
        return_value=httpx.Response(200, json={"version": "2.42.4"}),
    )


def test_plugin_descriptor() -> None:
    """Plugin registers under `messaging`."""
    assert plugin.name == "messaging"
    assert "message" in plugin.description.lower()


def test_cli_help_lists_every_verb() -> None:
    """`d2w messaging --help` shows the full verb surface."""
    result = CliRunner().invoke(messaging_app, ["--help"])
    assert result.exit_code == 0, result.output
    for verb in ("list", "get", "send", "reply", "mark-read", "mark-unread", "delete"):
        assert verb in result.output


def test_cli_mounted_on_root() -> None:
    """`d2w messaging` resolves through the root app."""
    result = CliRunner().invoke(build_app(), ["messaging", "--help"])
    assert result.exit_code == 0, result.output


@respx.mock
async def test_service_list_conversations_returns_typed_rows(profile: Profile) -> None:
    """Service layer returns typed `MessageConversation` models."""
    _mock_preamble()
    respx.get("https://dhis2.example/api/messageConversations").mock(
        return_value=httpx.Response(
            200,
            json={"messageConversations": [{"id": "convUid001", "subject": "hi", "messageCount": 1}]},
        ),
    )
    rows = await service.list_conversations(profile)
    assert len(rows) == 1
    assert rows[0].id == "convUid001"


@respx.mock
async def test_service_send_returns_typed_conversation(profile: Profile) -> None:
    """`send(profile, ...)` resolves the Location header + fetches the typed `MessageConversation` back."""
    _mock_preamble()
    created_uid = "newConv001"
    respx.post("https://dhis2.example/api/messageConversations").mock(
        return_value=httpx.Response(
            201,
            json={"status": "OK", "httpStatus": "Created"},
            headers={"location": f"https://dhis2.example/api/messageConversations/{created_uid}"},
        ),
    )
    respx.get(f"https://dhis2.example/api/messageConversations/{created_uid}").mock(
        return_value=httpx.Response(200, json={"id": created_uid, "subject": "s", "messageCount": 1}),
    )
    conv = await service.send(profile, subject="s", text="t", users=["userUid001"])
    assert conv.id == created_uid


@respx.mock
async def test_service_mark_read_wraps_single_uid(profile: Profile) -> None:
    """A single UID ends up as `[uid]` on the wire."""
    _mock_preamble()
    route = respx.post("https://dhis2.example/api/messageConversations/read").mock(
        return_value=httpx.Response(200, json={"status": "OK", "httpStatus": "OK", "httpStatusCode": 200}),
    )
    await service.mark_read(profile, "convUid001")
    import json as _json

    assert _json.loads(route.calls.last.request.content) == ["convUid001"]
