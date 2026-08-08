"""FastMCP surface tests for the `fhir` plugin - the read-only validate tool and the dry-run forwarder."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from dhis2w_fhir import CodedAnswerMode, ForwardReport
from dhis2w_fhir.plugin import plugin
from dhis2w_fhir.validation.schemas import FhirValidationReport
from fastmcp import Client, FastMCP

_FHIR_TOML = """
[ig]
id = "dhis2.fhir.test"
canonical = "http://example.org/fhir"
name = "Dhis2FhirTest"
title = "DHIS2 FHIR Test IG"
publisher = "Test Organisation"
"""


def _server() -> FastMCP:
    """Register the fhir plugin onto a fresh FastMCP server."""
    server: FastMCP = FastMCP("fhir-mcp-test")
    plugin.register_mcp(server)
    return server


def _project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A directory the forward tool can discover a project and a profile in."""
    config_dir = tmp_path / ".config" / "dhis2"
    config_dir.mkdir(parents=True)
    (config_dir / "profiles.toml").write_text(
        """
default = "probe"

[profiles.probe]
base_url = "https://dhis2.example"
auth = "pat"
token = "d2p_test"
"""
    )
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_dir.parent))
    monkeypatch.delenv("DHIS2_PROFILE", raising=False)
    (tmp_path / "fhir.toml").write_text(_FHIR_TOML, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    return tmp_path


async def test_registers_the_two_data_shaped_tools() -> None:
    """Scaffolding/generation are CLI-only; MCP exposes the read-only validate and the forwarder."""
    async with Client(_server()) as client:
        tools = {tool.name: tool for tool in await client.list_tools()}
    assert set(tools) == {"fhir_validate", "fhir_forward"}
    validate = tools["fhir_validate"].annotations
    assert validate is not None and validate.readOnlyHint is True
    forward = tools["fhir_forward"].annotations
    assert forward is not None and forward.readOnlyHint is False and forward.destructiveHint is False


async def test_forward_defaults_to_a_dry_run(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """The tool an agent reaches for first cannot change the instance: `dry_run` defaults to True."""
    project = _project(tmp_path, monkeypatch)
    report = ForwardReport(project_root=project, dry_run=True, coded_answer_mode=CodedAnswerMode.LENIENT, spooled=0)
    mock = AsyncMock(return_value=report)
    with patch("dhis2w_fhir.service.forward_responses", new=mock):
        async with Client(_server()) as client:
            result = await client.call_tool("fhir_forward", {})
    assert mock.await_args is not None
    assert mock.await_args.kwargs == {"import_responses": False, "coded_answer_mode": None}
    structured = result.structured_content or {}
    assert structured.get("dry_run") is True


async def test_forward_commits_and_takes_the_code_dial(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """`dry_run=False` is the commit, and `strict_codes` reaches the service as the mode it names."""
    project = _project(tmp_path, monkeypatch)
    report = ForwardReport(project_root=project, dry_run=False, coded_answer_mode=CodedAnswerMode.STRICT)
    mock = AsyncMock(return_value=report)
    with patch("dhis2w_fhir.service.forward_responses", new=mock):
        async with Client(_server()) as client:
            await client.call_tool(
                "fhir_forward",
                {"project_directory": str(project), "dry_run": False, "strict_codes": True},
            )
    assert mock.await_args is not None
    assert mock.await_args.kwargs == {"import_responses": True, "coded_answer_mode": CodedAnswerMode.STRICT}


async def test_validate_dispatches(monkeypatch: pytest.MonkeyPatch) -> None:
    """`fhir_validate` resolves the profile and returns the service report."""
    monkeypatch.delenv("DHIS2_PROFILE", raising=False)
    monkeypatch.setenv("DHIS2_URL", "https://dhis2.example")
    monkeypatch.setenv("DHIS2_PAT", "d2p_test")
    report = FhirValidationReport(option_set_count=2, option_count=9)
    mock = AsyncMock(return_value=report)
    with patch("dhis2w_fhir.service.validate_codes", new=mock):
        async with Client(_server()) as client:
            result = await client.call_tool("fhir_validate", {})
    mock.assert_awaited_once()
    structured = result.structured_content or {}
    assert structured.get("option_set_count") == 2
