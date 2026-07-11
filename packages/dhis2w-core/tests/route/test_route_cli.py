"""CliRunner tests for `d2w route ...` commands."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from dhis2w_cli.main import build_app
from dhis2w_client import WebMessageResponse
from dhis2w_client.generated.v42.schemas import Route
from dhis2w_core.cli_errors import run_app
from typer.testing import CliRunner


@pytest.fixture
def pat_profile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Global profiles.toml with one PAT profile pointed at by HOME."""
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
    monkeypatch.chdir(tmp_path)


def _route(**overrides: object) -> Route:
    """Build a Route fixture for tests; overrides win over defaults."""
    base: dict[str, object] = {
        "id": "E8OPcc45A22",
        "code": "chap",
        "name": "chap",
        "url": "http://upstream.example/get",
        "disabled": False,
    }
    base.update(overrides)
    return Route.model_validate(base)


def test_route_list_renders_id_code_url(pat_profile: None) -> None:  # noqa: ARG001
    """Route list renders id code url."""
    routes = [_route(), _route(id="yt4aUhoQOqH", code="mrc", name="mrc", url="http://other.example/api/")]
    with patch("dhis2w_core.v42.plugins.route.service.list_routes", new=AsyncMock(return_value=routes)):
        result = CliRunner().invoke(build_app(), ["route", "list"])
    assert result.exit_code == 0, result.output
    assert "E8OPcc45A22" in result.output
    assert "chap" in result.output
    assert "yt4aUhoQOqH" in result.output


def test_route_get_renders_detail_table(pat_profile: None) -> None:  # noqa: ARG001
    """Route get renders detail table."""
    with patch("dhis2w_core.v42.plugins.route.service.get_route", new=AsyncMock(return_value=_route())):
        result = CliRunner().invoke(build_app(), ["route", "get", "chap"])
    assert result.exit_code == 0, result.output
    assert "E8OPcc45A22" in result.output
    assert "chap" in result.output
    assert "http://upstream.example/get" in result.output


def test_route_get_json_output_emits_model_dump(pat_profile: None) -> None:  # noqa: ARG001
    """Route get json output emits model dump."""
    with patch("dhis2w_core.v42.plugins.route.service.get_route", new=AsyncMock(return_value=_route())):
        result = CliRunner().invoke(build_app(), ["--json", "route", "get", "chap"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["id"] == "E8OPcc45A22"
    assert payload["code"] == "chap"


def test_route_run_prints_upstream_payload(pat_profile: None) -> None:  # noqa: ARG001
    """Route run prints upstream payload."""
    upstream = {"version": "2.0", "ok": True}
    with patch("dhis2w_core.v42.plugins.route.service.run_route", new=AsyncMock(return_value=upstream)):
        result = CliRunner().invoke(build_app(), ["route", "run", "chap", "--path", "system/info"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == upstream


def test_route_run_surfaces_lookup_error_with_red_hint(
    pat_profile: None,  # noqa: ARG001
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """LookupError from service propagates to `run_app` and renders cleanly on stderr + exit 1."""
    error = LookupError(
        "route 'chap' has a wildcard URL ('http://upstream.example/**'); "
        "pass --path SEGMENT to fill the wildcard suffix"
    )
    monkeypatch.setattr("sys.argv", ["d2w", "route", "run", "chap"])
    with (
        patch("dhis2w_core.v42.plugins.route.service.run_route", new=AsyncMock(side_effect=error)),
        pytest.raises(SystemExit) as exc_info,
    ):
        run_app(build_app())
    assert exc_info.value.code == 1
    err = capsys.readouterr().err
    assert "wildcard URL" in err
    assert "--path" in err
    assert "Traceback" not in err


def test_route_delete_renders_webmessage(pat_profile: None) -> None:  # noqa: ARG001
    """Route delete renders webmessage when the confirmation is skipped with --yes."""
    envelope = WebMessageResponse.model_validate({"status": "OK", "message": "Route deleted"})
    with patch("dhis2w_core.v42.plugins.route.service.delete_route", new=AsyncMock(return_value=envelope)):
        result = CliRunner().invoke(build_app(), ["route", "delete", "chap", "--yes"])
    assert result.exit_code == 0, result.output
    assert "deleted chap" in result.output


def test_route_delete_confirm_accept(pat_profile: None) -> None:  # noqa: ARG001
    """Answering `y` at the prompt proceeds to delete."""
    envelope = WebMessageResponse.model_validate({"status": "OK", "message": "Route deleted"})
    delete = AsyncMock(return_value=envelope)
    with patch("dhis2w_core.v42.plugins.route.service.delete_route", new=delete):
        result = CliRunner().invoke(build_app(), ["route", "delete", "chap"], input="y\n")
    assert result.exit_code == 0, result.output
    assert "deleted chap" in result.output
    delete.assert_awaited_once()


def test_route_delete_confirm_abort_skips_service(pat_profile: None) -> None:  # noqa: ARG001
    """Answering `n` at the prompt aborts before the service is called."""
    delete = AsyncMock()
    with patch("dhis2w_core.v42.plugins.route.service.delete_route", new=delete):
        result = CliRunner().invoke(build_app(), ["route", "delete", "chap"], input="n\n")
    assert result.exit_code != 0
    delete.assert_not_called()


def test_route_delete_unknown_code_exits_1(
    pat_profile: None,  # noqa: ARG001
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An unknown code raises LookupError which `run_app` renders as `error: ...` on stderr."""
    monkeypatch.setattr("sys.argv", ["d2w", "route", "delete", "nope", "--yes"])
    with (
        patch(
            "dhis2w_core.v42.plugins.route.service.delete_route",
            new=AsyncMock(side_effect=LookupError("no route found with code or UID 'nope'")),
        ),
        pytest.raises(SystemExit) as exc_info,
    ):
        run_app(build_app())
    assert exc_info.value.code == 1
    err = capsys.readouterr().err
    assert "no route found" in err
