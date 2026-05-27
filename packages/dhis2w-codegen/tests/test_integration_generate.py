"""End-to-end codegen against the local DHIS2 stack. Marked slow."""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest
from dhis2w_client import BasicAuth
from dhis2w_codegen.discover import discover
from dhis2w_codegen.emit import emit

pytestmark = pytest.mark.slow


async def test_discover_returns_populated_manifest(
    local_url: str,
    local_username: str,
    local_password: str,
    local_available: bool,
) -> None:
    """Discover returns populated manifest."""
    if not local_available:
        pytest.skip(f"local DHIS2 not reachable at {local_url}")
    auth = BasicAuth(username=local_username, password=local_password)
    manifest = await discover(local_url, auth)
    assert manifest.raw_version
    assert manifest.version_key.startswith("v")
    assert len(manifest.schemas) > 50


async def test_full_codegen_cycle_produces_importable_module(
    local_url: str,
    local_username: str,
    local_password: str,
    local_available: bool,
    tmp_path: Path,
) -> None:
    """Full codegen cycle produces importable module."""
    if not local_available:
        pytest.skip(f"local DHIS2 not reachable at {local_url}")
    auth = BasicAuth(username=local_username, password=local_password)
    manifest = await discover(local_url, auth)
    destination = tmp_path / manifest.version_key
    emit(manifest, destination)

    assert (destination / "__init__.py").exists()
    assert (destination / "resources.py").exists()
    assert (destination / "schemas").is_dir()

    manifest_on_disk = json.loads((destination / "schemas_manifest.json").read_text())
    assert manifest_on_disk["version_key"] == manifest.version_key

    generated_files = list((destination / "schemas").glob("*.py"))
    assert len(generated_files) > 20

    sys.path.insert(0, str(tmp_path))
    try:
        module = importlib.import_module(manifest.version_key)
        assert getattr(module, "GENERATED", False) is True
        assert manifest.version_key == module.VERSION_KEY
        assert hasattr(module, "Resources")
    finally:
        sys.path.remove(str(tmp_path))
        for key in list(sys.modules):
            if key == manifest.version_key or key.startswith(f"{manifest.version_key}."):
                del sys.modules[key]
