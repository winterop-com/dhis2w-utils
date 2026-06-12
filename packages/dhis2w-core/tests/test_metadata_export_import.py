"""Tests for metadata export/import — service params + CLI flag routing + bundle summaries."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import respx
from dhis2w_cli.main import build_app
from dhis2w_client import WebMessageResponse
from dhis2w_core.v42.plugins.metadata import service
from dhis2w_core.v42.plugins.metadata.models import MetadataBundle
from typer.testing import CliRunner


@pytest.fixture(autouse=True)
def _raw_env_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    """Isolate tests from any system `profiles.toml` — force raw-env resolution."""
    monkeypatch.delenv("DHIS2_PROFILE", raising=False)
    monkeypatch.setenv("DHIS2_URL", "http://mock.example")
    monkeypatch.setenv("DHIS2_PAT", "test-token")


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _mock_connect_preamble() -> None:
    """Mock the endpoints Dhis2Client.connect() hits before the per-test route."""
    # Canonical-URL probe GET / (follow-redirects).
    respx.get("http://mock.example/").mock(return_value=httpx.Response(200, text="ok"))
    # Version discovery via /api/system/info.
    respx.get("http://mock.example/api/system/info").mock(
        return_value=httpx.Response(200, json={"version": "2.42.4"}),
    )


@respx.mock
async def test_export_metadata_no_args_hits_bare_endpoint() -> None:
    """With no resource filter, GET /api/metadata carries no per-resource params."""
    _mock_connect_preamble()
    route = respx.get("http://mock.example/api/metadata").mock(
        return_value=httpx.Response(200, json={"date": "2026-04-19", "dataElements": [{"id": "x"}]}),
    )
    from dhis2w_core.profile import Profile

    profile = Profile(base_url="http://mock.example", auth="pat", token="t")
    bundle = await service.export_metadata(profile)
    assert route.called
    sent = dict(route.calls.last.request.url.params)
    assert all(v != "true" for v in sent.values())
    assert [item.id for item in bundle.get_resource("dataElements")] == ["x"]


@respx.mock
async def test_export_metadata_filters_resources_and_fields() -> None:
    """`resources=["dataElements", "indicators"]` → `?dataElements=true&indicators=true`; fields forwarded."""
    _mock_connect_preamble()
    route = respx.get("http://mock.example/api/metadata").mock(
        return_value=httpx.Response(200, json={"dataElements": []}),
    )
    from dhis2w_core.profile import Profile

    profile = Profile(base_url="http://mock.example", auth="pat", token="t")
    await service.export_metadata(
        profile,
        resources=["dataElements", "indicators"],
        fields=":owner",
        skip_sharing=True,
    )
    params = dict(route.calls.last.request.url.params)
    assert params["dataElements"] == "true"
    assert params["indicators"] == "true"
    assert params["fields"] == ":owner"
    assert params["skipSharing"] == "true"
    assert "skipTranslation" not in params


@respx.mock
async def test_import_metadata_posts_bundle_and_forwards_strategy() -> None:
    """import_metadata posts the bundle body + forwards strategy/atomic/identifier as URL params."""
    _mock_connect_preamble()
    route = respx.post("http://mock.example/api/metadata").mock(
        return_value=httpx.Response(200, json={"status": "OK", "httpStatusCode": 200}),
    )
    from dhis2w_core.profile import Profile

    profile = Profile(base_url="http://mock.example", auth="pat", token="t")
    response = await service.import_metadata(
        profile,
        MetadataBundle.from_raw({"dataElements": [{"id": "x"}]}),
        import_strategy="CREATE",
        atomic_mode="NONE",
        identifier="CODE",
    )
    assert route.called
    assert isinstance(response, WebMessageResponse)
    params = dict(route.calls.last.request.url.params)
    assert params["importStrategy"] == "CREATE"
    assert params["atomicMode"] == "NONE"
    assert params["identifier"] == "CODE"
    body = json.loads(route.calls.last.request.content)
    assert body == {"dataElements": [{"id": "x"}]}


@respx.mock
async def test_import_metadata_dry_run_maps_to_importMode_VALIDATE() -> None:
    """DHIS2 calls the dry-run mode `importMode=VALIDATE`; `--dry-run` must hit that wire name."""
    _mock_connect_preamble()
    route = respx.post("http://mock.example/api/metadata").mock(
        return_value=httpx.Response(200, json={"status": "OK"}),
    )
    from dhis2w_core.profile import Profile

    profile = Profile(base_url="http://mock.example", auth="pat", token="t")
    await service.import_metadata(profile, MetadataBundle.from_raw({}), dry_run=True)
    params = dict(route.calls.last.request.url.params)
    assert params["importMode"] == "VALIDATE"


def test_metadata_bundle_summary_skips_meta_keys() -> None:
    """`MetadataBundle.summary()` counts resource collections; system/date must not appear."""
    bundle = MetadataBundle.from_raw(
        {
            "system": {"id": "abc", "version": "2.42"},
            "date": "2026-04-19",
            "dataElements": [{"id": "a"}, {"id": "b"}],
            "indicators": [{"id": "i1"}],
        }
    )
    assert bundle.summary() == {"dataElements": 2, "indicators": 1}


def test_metadata_bundle_resources_iterates_insertion_order_skipping_meta() -> None:
    """Resource collections iterate in insertion order; `system`/`date` are filtered out."""
    bundle = MetadataBundle.from_raw(
        {
            "system": {},
            "indicators": [{"id": "i1"}],
            "date": "x",
            "dataElements": [{"id": "d1"}, {"id": "d2"}],
        }
    )
    pairs = list(bundle.resources())
    assert [key for key, _ in pairs] == ["indicators", "dataElements"]
    assert len(pairs[1][1]) == 2
    assert pairs[1][1][0].id == "d1"


def _mock_export(raw: dict[str, Any]) -> AsyncMock:
    """Patch `service.export_metadata` to return a typed bundle built from `raw`, recording kwargs."""
    return AsyncMock(return_value=MetadataBundle.from_raw(raw))


def _mock_import(response: WebMessageResponse) -> AsyncMock:
    """Patch `service.import_metadata` to return `response`."""
    return AsyncMock(return_value=response)


def test_cli_export_writes_output_file(runner: CliRunner, tmp_path: Path) -> None:
    """`d2w metadata export --output FILE` writes bundle JSON to FILE + prints stderr summary."""
    out = tmp_path / "bundle.json"
    mock = _mock_export({"dataElements": [{"id": "x"}]})
    with patch("dhis2w_core.v42.plugins.metadata.service.export_metadata", mock):
        result = runner.invoke(build_app(), ["metadata", "export", "--output", str(out)])
    assert result.exit_code == 0, result.output
    assert out.exists()
    bundle_loaded = json.loads(out.read_text())
    assert bundle_loaded == {"dataElements": [{"id": "x"}]}


def test_cli_export_forwards_flags(runner: CliRunner, tmp_path: Path) -> None:
    """Every export flag must reach the service call as a kwarg — regression for the wire names."""
    out = tmp_path / "b.json"
    mock = _mock_export({"dataElements": []})
    with patch("dhis2w_core.v42.plugins.metadata.service.export_metadata", mock):
        result = runner.invoke(
            build_app(),
            [
                "metadata",
                "export",
                "--resource",
                "dataElements",
                "--resource",
                "indicators",
                "--fields",
                ":identifiable",
                "--skip-sharing",
                "--skip-translation",
                "--output",
                str(out),
            ],
        )
    assert result.exit_code == 0, result.output
    _, kwargs = mock.call_args
    assert kwargs == {
        "resources": ["dataElements", "indicators"],
        "fields": ":identifiable",
        "skip_sharing": True,
        "skip_translation": True,
        "skip_validation": False,
        "per_resource_filters": None,
        "per_resource_fields": None,
    }


def test_cli_import_reads_file_and_forwards_flags(runner: CliRunner, tmp_path: Path) -> None:
    """`d2w metadata import FILE` reads the bundle + forwards strategy/atomic/dry-run flags."""
    bundle_path = tmp_path / "in.json"
    bundle_path.write_text(json.dumps({"dataElements": [{"id": "a"}]}), encoding="utf-8")
    response = WebMessageResponse.model_validate({"status": "OK"})
    mock = _mock_import(response)
    with (
        patch("dhis2w_core.v42.plugins.metadata.service.import_metadata", mock),
        patch("dhis2w_core.v42.plugins.metadata.cli.render_webmessage", MagicMock()),
    ):
        result = runner.invoke(
            build_app(),
            [
                "metadata",
                "import",
                str(bundle_path),
                "--strategy",
                "CREATE",
                "--atomic-mode",
                "NONE",
                "--dry-run",
                "--identifier",
                "CODE",
            ],
        )
    assert result.exit_code == 0, result.output
    # kwargs should match the wire-name conversion:
    args, kwargs = mock.call_args
    assert isinstance(args[1], MetadataBundle)
    assert args[1].get_resource("dataElements")[0].id == "a"
    assert kwargs["import_strategy"] == "CREATE"
    assert kwargs["atomic_mode"] == "NONE"
    assert kwargs["dry_run"] is True
    assert kwargs["identifier"] == "CODE"


def test_cli_import_rejects_non_object_json(runner: CliRunner, tmp_path: Path) -> None:
    """Top-level JSON array is not a bundle — fail fast, don't post."""
    bad = tmp_path / "bad.json"
    bad.write_text("[]", encoding="utf-8")
    result = runner.invoke(build_app(), ["metadata", "import", str(bad)])
    assert result.exit_code != 0
    assert "bundle" in result.output.lower() or "object" in result.output.lower()
