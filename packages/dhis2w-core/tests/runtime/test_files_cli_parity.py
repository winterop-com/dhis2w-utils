"""Per-version CLI invocation parity for the `files` plugin — exercise cli.py command bodies on all trees.

The service parity tests cover the service layer; these invoke the CLI commands (via CliRunner against a
version-pinned `build_app()`) with the version's service mocked, so the v41/v43 cli.py command bodies
(arg parsing + result rendering) run, not just their import-time definitions.
"""

from __future__ import annotations

from importlib import import_module
from unittest.mock import AsyncMock, patch

import pytest
from dhis2w_cli.main import build_app
from typer import Typer
from typer.testing import CliRunner


def _build_versioned_app(core_version: str, monkeypatch: pytest.MonkeyPatch) -> Typer:
    """Build the CLI app pinned to `core_version` (so it discovers that tree's plugins)."""
    monkeypatch.setenv("DHIS2_VERSION", core_version)
    return build_app()


def _document(core_version: str) -> object:
    """Build one `Document` for the parametrized version tree."""
    document_cls = import_module(f"dhis2w_client.{core_version}").Document
    return document_cls.model_validate(
        {"id": "docUid00001", "name": "Annual Report", "external": False, "url": "f.pdf"}
    )


def _file_resource(core_version: str) -> object:
    """Build one `FileResource` for the parametrized version tree."""
    fr_cls = import_module(f"dhis2w_client.{core_version}").FileResource
    return fr_cls.model_validate({"id": "frUid000001", "name": "blob.bin", "domain": "DATA_VALUE"})


def test_files_documents_list_cli_parity(
    core_version: str, core_profile: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`d2w files documents list` renders the documents table on every tree."""
    mock = AsyncMock(return_value=[_document(core_version)])
    with patch(f"dhis2w_core.{core_version}.plugins.files.service.list_documents", new=mock):
        app = _build_versioned_app(core_version, monkeypatch)
        result = CliRunner().invoke(app, ["-p", "probe", "files", "documents", "list"])
    assert result.exit_code == 0, result.output
    assert "docUid00001" in result.output


def test_files_documents_get_cli_parity(core_version: str, core_profile: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """`d2w files documents get <uid>` renders one document on every tree."""
    mock = AsyncMock(return_value=_document(core_version))
    with patch(f"dhis2w_core.{core_version}.plugins.files.service.get_document", new=mock):
        app = _build_versioned_app(core_version, monkeypatch)
        result = CliRunner().invoke(app, ["-p", "probe", "files", "documents", "get", "docUid00001"])
    assert result.exit_code == 0, result.output
    assert "docUid00001" in result.output


def test_files_documents_upload_url_cli_parity(
    core_version: str, core_profile: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`d2w files documents upload-url <name> <url>` confirms the create on every tree."""
    mock = AsyncMock(return_value=_document(core_version))
    with patch(f"dhis2w_core.{core_version}.plugins.files.service.create_external_document", new=mock):
        app = _build_versioned_app(core_version, monkeypatch)
        result = CliRunner().invoke(
            app, ["-p", "probe", "files", "documents", "upload-url", "Annual Report", "http://up.example"]
        )
    assert result.exit_code == 0, result.output
    assert "docUid00001" in result.output


def test_files_documents_delete_cli_parity(
    core_version: str, core_profile: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`d2w files documents delete <uid> --yes` confirms the delete on every tree."""
    mock = AsyncMock(return_value=None)
    with patch(f"dhis2w_core.{core_version}.plugins.files.service.delete_document", new=mock):
        app = _build_versioned_app(core_version, monkeypatch)
        result = CliRunner().invoke(app, ["-p", "probe", "files", "documents", "delete", "docUid00001", "--yes"])
    assert result.exit_code == 0, result.output
    assert "deleted docUid00001" in result.output


def test_files_resources_get_cli_parity(core_version: str, core_profile: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """`d2w files resources get <uid>` renders one file resource on every tree."""
    mock = AsyncMock(return_value=_file_resource(core_version))
    with patch(f"dhis2w_core.{core_version}.plugins.files.service.get_file_resource", new=mock):
        app = _build_versioned_app(core_version, monkeypatch)
        result = CliRunner().invoke(app, ["-p", "probe", "files", "resources", "get", "frUid000001"])
    assert result.exit_code == 0, result.output
    assert "frUid000001" in result.output
