"""Tests for the files plugin — CLI surface, service wiring, plugin descriptor."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import respx
from dhis2w_cli.main import build_app
from dhis2w_core.profile import Profile
from dhis2w_core.v42.plugins.files import plugin, service
from dhis2w_core.v42.plugins.files.cli import app as files_app
from typer.testing import CliRunner

_runner = CliRunner()


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
    """Minimal profile for the service-layer tests."""
    return Profile(base_url="https://dhis2.example", auth="pat", token="test-token")


def _mock_preamble() -> None:
    """Connect-time probes (root + /api/system/info)."""
    respx.get("https://dhis2.example/").mock(return_value=httpx.Response(200, text=""))
    respx.get("https://dhis2.example/api/system/info").mock(
        return_value=httpx.Response(200, json={"version": "2.42.4"}),
    )


def test_plugin_descriptor() -> None:
    """Plugin registers under the expected name + has a description."""
    assert plugin.name == "files"
    assert "document" in plugin.description.lower() or "file" in plugin.description.lower()


def test_cli_help_lists_documents_and_resources() -> None:
    """`d2w files --help` lists both sub-apps."""
    result = _runner.invoke(files_app, ["--help"])
    assert result.exit_code == 0, result.output
    assert "documents" in result.output
    assert "resources" in result.output


def test_cli_documents_help_lists_verbs() -> None:
    """`d2w files documents --help` exposes list / get / upload / upload-url / download / delete."""
    result = _runner.invoke(files_app, ["documents", "--help"])
    assert result.exit_code == 0, result.output
    for verb in ("list", "get", "upload", "upload-url", "download", "delete"):
        assert verb in result.output


def test_cli_resources_help_lists_verbs() -> None:
    """`d2w files resources --help` exposes upload / get / download."""
    result = _runner.invoke(files_app, ["resources", "--help"])
    assert result.exit_code == 0, result.output
    for verb in ("upload", "get", "download"):
        assert verb in result.output


def test_cli_mounted_on_root() -> None:
    """`d2w files` resolves through the root app (plugin auto-discovery)."""
    result = _runner.invoke(build_app(), ["files", "--help"])
    assert result.exit_code == 0, result.output
    assert "documents" in result.output


def test_documents_delete_confirm_accept() -> None:
    """`documents delete <uid>` with `y` at the prompt proceeds to delete."""
    delete = AsyncMock(return_value=None)
    with patch("dhis2w_core.v42.plugins.files.service.delete_document", new=delete):
        result = _runner.invoke(build_app(), ["files", "documents", "delete", "docUid00001"], input="y\n")
    assert result.exit_code == 0, result.output
    assert "deleted docUid00001" in result.output
    delete.assert_awaited_once()


def test_documents_delete_confirm_abort_skips_service() -> None:
    """`documents delete <uid>` with `n` at the prompt aborts before the service is called."""
    delete = AsyncMock()
    with patch("dhis2w_core.v42.plugins.files.service.delete_document", new=delete):
        result = _runner.invoke(build_app(), ["files", "documents", "delete", "docUid00001"], input="n\n")
    assert result.exit_code != 0
    delete.assert_not_called()


def test_documents_delete_yes_flag_skips_prompt() -> None:
    """`documents delete <uid> --yes` deletes without prompting."""
    delete = AsyncMock(return_value=None)
    with patch("dhis2w_core.v42.plugins.files.service.delete_document", new=delete):
        result = _runner.invoke(build_app(), ["files", "documents", "delete", "docUid00001", "--yes"])
    assert result.exit_code == 0, result.output
    assert "deleted docUid00001" in result.output
    delete.assert_awaited_once()


@respx.mock
async def test_service_list_documents_returns_typed_rows(profile: Profile) -> None:
    """Service layer returns `Document` pydantic models (no dict leakage)."""
    _mock_preamble()
    respx.get("https://dhis2.example/api/documents").mock(
        return_value=httpx.Response(
            200,
            json={
                "documents": [
                    {"id": "doc1", "name": "A", "external": False, "attachment": True},
                ],
            },
        ),
    )
    docs = await service.list_documents(profile)
    assert len(docs) == 1
    assert docs[0].id == "doc1"


@respx.mock
async def test_service_upload_document_writes_bytes_and_returns_document(profile: Profile, tmp_path: Path) -> None:
    """Two-step upload: fileResource (domain=DOCUMENT) -> document JSON -> typed `Document`.

    See BUGS.md #16 for why `/api/documents` doesn't accept multipart directly.
    """
    _mock_preamble()
    payload = tmp_path / "report.txt"
    payload.write_bytes(b"hello")
    respx.post("https://dhis2.example/api/fileResources").mock(
        return_value=httpx.Response(202, json={"response": {"fileResource": {"id": "frDocUid0001"}}}),
    )
    respx.get("https://dhis2.example/api/fileResources/frDocUid0001").mock(
        return_value=httpx.Response(200, json={"id": "frDocUid0001", "domain": "DOCUMENT"}),
    )
    respx.post("https://dhis2.example/api/documents").mock(
        return_value=httpx.Response(200, json={"response": {"uid": "uploadedUi1"}}),
    )
    respx.get("https://dhis2.example/api/documents/uploadedUi1").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "uploadedUi1",
                "name": "report.txt",
                "url": "frDocUid0001",
                "external": False,
                "attachment": True,
            },
        ),
    )
    doc = await service.upload_document(profile, payload)
    assert doc.id == "uploadedUi1"


@respx.mock
async def test_service_download_writes_destination(profile: Profile, tmp_path: Path) -> None:
    """`download_document(profile, uid, dest)` writes bytes to dest and returns the byte count."""
    _mock_preamble()
    payload = b"\x00\x01\x02\x03"
    respx.get("https://dhis2.example/api/documents/doc1/data").mock(
        return_value=httpx.Response(200, content=payload),
    )
    destination = tmp_path / "out.bin"
    written = await service.download_document(profile, "doc1", destination)
    assert written == len(payload)
    assert destination.read_bytes() == payload


@respx.mock
async def test_service_upload_file_resource_with_string_domain(profile: Profile, tmp_path: Path) -> None:
    """Upload a fileResource via string domain — forwards `domain=ICON` to DHIS2."""
    _mock_preamble()
    f = tmp_path / "icon.svg"
    f.write_bytes(b"<svg/>")
    route = respx.post("https://dhis2.example/api/fileResources").mock(
        return_value=httpx.Response(202, json={"response": {"fileResource": {"id": "iconFrUid01"}}}),
    )
    respx.get("https://dhis2.example/api/fileResources/iconFrUid01").mock(
        return_value=httpx.Response(200, json={"id": "iconFrUid01", "name": "icon.svg", "domain": "ICON"}),
    )
    fr = await service.upload_file_resource(profile, f, domain="ICON")
    assert fr.id == "iconFrUid01"
    assert route.calls.last.request.url.params["domain"] == "ICON"
