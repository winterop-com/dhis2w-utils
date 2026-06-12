"""Tests for `service.patch_metadata` + `d2w metadata patch` CLI + `metadata_patch` MCP."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import respx
from dhis2w_cli.main import build_app
from dhis2w_client import RemoveOp, ReplaceOp, WebMessageResponse
from dhis2w_core.profile import Profile
from dhis2w_core.v42.plugins.metadata import service
from typer.testing import CliRunner


@pytest.fixture(autouse=True)
def _raw_env_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force env-only profile resolution for the tests in this file."""
    monkeypatch.delenv("DHIS2_PROFILE", raising=False)
    monkeypatch.setenv("DHIS2_URL", "http://mock.example")
    monkeypatch.setenv("DHIS2_PAT", "test-token")


@pytest.fixture
def runner() -> CliRunner:
    """Fresh Typer CliRunner for every test — isolates stdout/stderr capture."""
    return CliRunner()


def _mock_connect_preamble() -> None:
    """Mock the canonical-URL + `/api/system/info` probes `Dhis2Client.connect()` performs."""
    respx.get("http://mock.example/").mock(return_value=httpx.Response(200, text="ok"))
    respx.get("http://mock.example/api/system/info").mock(
        return_value=httpx.Response(200, json={"version": "2.42.4"}),
    )


@respx.mock
async def test_patch_metadata_posts_typed_ops_as_rfc_6902_array() -> None:
    """Typed op variants serialise to the RFC 6902 wire array at `PATCH /api/<resource>/{uid}`."""
    _mock_connect_preamble()
    route = respx.patch("http://mock.example/api/dataElements/DEancVisit1").mock(
        return_value=httpx.Response(200, json={"status": "OK"}),
    )
    profile = Profile(base_url="http://mock.example", auth="pat", token="t")
    response = await service.patch_metadata(
        profile,
        "dataElements",
        "DEancVisit1",
        [
            ReplaceOp(path="/description", value="new"),
            RemoveOp(path="/legacy"),
        ],
    )
    assert isinstance(response, WebMessageResponse)
    body = json.loads(route.calls.last.request.content)
    assert body == [
        {"op": "replace", "path": "/description", "value": "new"},
        {"op": "remove", "path": "/legacy"},
    ]


@respx.mock
async def test_patch_metadata_accepts_raw_dict_ops() -> None:
    """Service accepts `{op, path, ...}` dicts interchangeably — routes through the adapter."""
    _mock_connect_preamble()
    route = respx.patch("http://mock.example/api/indicators/ind00000001").mock(
        return_value=httpx.Response(200, json={"status": "OK"}),
    )
    profile = Profile(base_url="http://mock.example", auth="pat", token="t")
    await service.patch_metadata(
        profile,
        "indicators",
        "ind00000001",
        [{"op": "move", "path": "/newPath", "from": "/oldPath"}],
    )
    body = json.loads(route.calls.last.request.content)
    assert body == [{"op": "move", "path": "/newPath", "from": "/oldPath"}]


@respx.mock
async def test_patch_metadata_unknown_resource_raises() -> None:
    """`patch_metadata` surfaces `UnknownResourceError` for resource names not on the client."""
    _mock_connect_preamble()
    profile = Profile(base_url="http://mock.example", auth="pat", token="t")
    with pytest.raises(service.UnknownResourceError):
        await service.patch_metadata(profile, "notARealResource", "xxxxxxxxxxx", [RemoveOp(path="/x")])


def test_cli_patch_inline_set_and_remove_routes_correctly(runner: CliRunner) -> None:
    """`--set path=value --remove path` both reach the service as typed ops."""
    response = WebMessageResponse.model_validate({"status": "OK"})
    mock = AsyncMock(return_value=response)
    with (
        patch("dhis2w_core.v42.plugins.metadata.service.patch_metadata", mock),
        patch("dhis2w_core.v42.plugins.metadata.cli.render_webmessage", MagicMock()),
    ):
        result = runner.invoke(
            build_app(),
            [
                "metadata",
                "patch",
                "dataElements",
                "DEancVisit1",
                "--set",
                "/description=new desc",
                "--set",
                "/zeroIsSignificant=true",
                "--remove",
                "/legacy",
            ],
        )
    assert result.exit_code == 0, result.output
    args, _ = mock.call_args
    # args = (profile, resource, uid, ops)
    assert args[1] == "dataElements"
    assert args[2] == "DEancVisit1"
    ops = args[3]
    assert len(ops) == 3
    assert ops[0].op == "replace" and ops[0].path == "/description" and ops[0].value == "new desc"
    # JSON-decodable RHS parses as boolean rather than string "true".
    assert ops[1].value is True
    assert ops[2].op == "remove" and ops[2].path == "/legacy"


def test_cli_patch_file_mode(runner: CliRunner, tmp_path: Path) -> None:
    """`--file patch.json` reads a full RFC 6902 array and validates each op."""
    patch_file = tmp_path / "patch.json"
    patch_file.write_text(
        json.dumps(
            [
                {"op": "replace", "path": "/name", "value": "Renamed"},
                {"op": "copy", "path": "/alias", "from": "/name"},
            ]
        ),
        encoding="utf-8",
    )
    response = WebMessageResponse.model_validate({"status": "OK"})
    mock = AsyncMock(return_value=response)
    with (
        patch("dhis2w_core.v42.plugins.metadata.service.patch_metadata", mock),
        patch("dhis2w_core.v42.plugins.metadata.cli.render_webmessage", MagicMock()),
    ):
        result = runner.invoke(
            build_app(),
            ["metadata", "patch", "dataElements", "abc12345678", "--file", str(patch_file)],
        )
    assert result.exit_code == 0, result.output
    args, _ = mock.call_args
    ops = args[3]
    assert len(ops) == 2
    assert ops[0].op == "replace"
    assert ops[1].op == "copy" and ops[1].from_ == "/name"


def test_cli_patch_rejects_both_file_and_inline(runner: CliRunner, tmp_path: Path) -> None:
    """Passing both `--file` and `--set` is ambiguous — fail fast with a clear error."""
    patch_file = tmp_path / "patch.json"
    patch_file.write_text("[]", encoding="utf-8")
    result = runner.invoke(
        build_app(),
        [
            "metadata",
            "patch",
            "dataElements",
            "abc",
            "--file",
            str(patch_file),
            "--set",
            "/name=x",
        ],
    )
    assert result.exit_code != 0
    assert "file" in result.output.lower() or "inline" in result.output.lower()


def test_cli_patch_rejects_neither_file_nor_inline(runner: CliRunner) -> None:
    """Passing neither `--file` nor inline ops is an error — we don't want no-op calls."""
    result = runner.invoke(
        build_app(),
        ["metadata", "patch", "dataElements", "abc"],
    )
    assert result.exit_code != 0


def test_cli_patch_malformed_set_rejected(runner: CliRunner) -> None:
    """`--set missingequals` without `=` separator fails cleanly rather than posting garbage."""
    result = runner.invoke(
        build_app(),
        ["metadata", "patch", "dataElements", "abc", "--set", "justapath"],
    )
    assert result.exit_code != 0
    assert "path=value" in result.output or "set" in result.output.lower()


def test_cli_patch_file_must_be_array(runner: CliRunner, tmp_path: Path) -> None:
    """A JSON Patch source must be a top-level array; a single-op object is rejected."""
    patch_file = tmp_path / "patch.json"
    patch_file.write_text('{"op": "replace", "path": "/x", "value": 1}', encoding="utf-8")
    result = runner.invoke(
        build_app(),
        ["metadata", "patch", "dataElements", "abc", "--file", str(patch_file)],
    )
    assert result.exit_code != 0
    assert "array" in result.output.lower()
