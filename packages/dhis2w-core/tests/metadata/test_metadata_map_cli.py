"""CliRunner + mock tests for `d2w metadata map ...`."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from dhis2w_cli.main import build_app
from dhis2w_client.generated.v42.schemas import Map
from typer.testing import CliRunner


@pytest.fixture
def pat_profile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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


def _map() -> Map:
    return Map.model_validate(
        {
            "id": "MapProbe001",
            "name": "Probe choropleth",
            "description": "Fixture",
            "longitude": 15.0,
            "latitude": 64.5,
            "zoom": 4,
            "basemap": "openStreetMap",
            "mapViews": [
                {
                    "layer": "thematic",
                    "thematicMapType": "CHOROPLETH",
                    "classes": 5,
                    "colorLow": "#fef0d9",
                    "colorHigh": "#b30000",
                },
            ],
        },
    )


def test_map_show_renders_layer_summary(pat_profile: None) -> None:  # noqa: ARG001
    """Map show renders layer summary."""
    with patch(
        "dhis2w_core.v42.plugins.metadata.service.show_map",
        new=AsyncMock(return_value=_map()),
    ):
        result = CliRunner().invoke(build_app(), ["metadata", "maps", "get", "MapProbe001"])
    assert result.exit_code == 0, result.output
    assert "Probe choropleth" in result.output
    assert "thematic" in result.output
    assert "CHOROPLETH" in result.output
    assert "#fef0d9" in result.output


def test_map_create_forwards_every_flag(pat_profile: None) -> None:  # noqa: ARG001
    """Map create forwards every flag."""
    mock = AsyncMock(return_value=_map())
    with patch("dhis2w_core.v42.plugins.metadata.service.create_map", new=mock):
        result = CliRunner().invoke(
            build_app(),
            [
                "metadata",
                "maps",
                "create",
                "--name",
                "demo",
                "--de",
                "DE1",
                "--pe",
                "2024",
                "--ou",
                "OU_ROOT",
                "--ou-level",
                "2",
                "--longitude",
                "10.5",
                "--latitude",
                "60.0",
                "--zoom",
                "5",
                "--classes",
                "6",
            ],
        )
    assert result.exit_code == 0, result.output
    assert mock.await_args is not None
    kwargs = mock.await_args.kwargs
    assert kwargs["name"] == "demo"
    assert kwargs["data_elements"] == ["DE1"]
    assert kwargs["periods"] == ["2024"]
    assert kwargs["organisation_units"] == ["OU_ROOT"]
    assert kwargs["organisation_unit_levels"] == [2]
    assert kwargs["longitude"] == 10.5
    assert kwargs["classes"] == 6


def test_map_clone_forwards_new_name(pat_profile: None) -> None:  # noqa: ARG001
    """Map clone forwards new name."""
    mock = AsyncMock(return_value=_map().model_copy(update={"id": "MapClone001", "name": "clone"}))
    with patch("dhis2w_core.v42.plugins.metadata.service.clone_map", new=mock):
        result = CliRunner().invoke(
            build_app(),
            [
                "metadata",
                "maps",
                "clone",
                "MapProbe001",
                "--new-name",
                "clone",
                "--new-uid",
                "MapClone001",
            ],
        )
    assert result.exit_code == 0, result.output
    assert mock.await_args is not None
    assert mock.await_args.args[1] == "MapProbe001"
    assert mock.await_args.kwargs["new_name"] == "clone"


def test_map_delete_aborts_without_yes(pat_profile: None) -> None:  # noqa: ARG001
    """Map delete aborts without yes."""
    with patch(
        "dhis2w_core.v42.plugins.metadata.service.delete_map",
        new=AsyncMock(return_value=None),
    ):
        result = CliRunner().invoke(build_app(), ["metadata", "maps", "delete", "MapProbe001"], input="n\n")
    assert result.exit_code != 0


def test_map_delete_with_yes_runs(pat_profile: None) -> None:  # noqa: ARG001
    """Map delete with yes runs."""
    with patch(
        "dhis2w_core.v42.plugins.metadata.service.delete_map",
        new=AsyncMock(return_value=None),
    ):
        result = CliRunner().invoke(build_app(), ["metadata", "maps", "delete", "MapProbe001", "-y"])
    assert result.exit_code == 0, result.output
    assert "deleted" in result.output
