"""CliRunner + mock tests for `d2w metadata viz ...` and `d2w metadata dashboard ...`."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from dhis2w_cli.main import build_app
from dhis2w_client.generated.v42.schemas import Dashboard, Visualization
from typer.testing import CliRunner


@pytest.fixture
def pat_profile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Global profiles.toml with one PAT profile, pointed at by HOME."""
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


def _viz() -> Visualization:
    return Visualization.model_validate(
        {
            "id": "VizProbeLn1",
            "name": "ANC probe line",
            "description": "Test fixture",
            "type": "LINE",
            "rowDimensions": ["pe"],
            "columnDimensions": ["ou"],
            "filterDimensions": ["dx"],
            "periods": [{"id": "202401"}, {"id": "202402"}],
            "organisationUnits": [{"id": "OU1"}, {"id": "OU2"}],
            "dataDimensionItems": [
                {"dataDimensionItemType": "DATA_ELEMENT", "dataElement": {"id": "DE1"}},
            ],
        },
    )


def _dashboard() -> Dashboard:
    return Dashboard.model_validate(
        {
            "id": "DashProbe01",
            "name": "Probe dashboard",
            "dashboardItems": [
                {
                    "id": "Ditm0001",
                    "type": "VISUALIZATION",
                    "visualization": {"id": "VizProbeLn1"},
                    "x": 0,
                    "y": 0,
                    "width": 60,
                    "height": 20,
                },
            ],
        },
    )


# ---- viz list / show / create / clone / delete ---------------------------


def test_viz_show_renders_axes_and_data_elements(pat_profile: None) -> None:  # noqa: ARG001
    """Viz show renders axes and data elements."""
    with patch(
        "dhis2w_core.v42.plugins.metadata.service.show_visualization",
        new=AsyncMock(return_value=_viz()),
    ):
        result = CliRunner().invoke(build_app(), ["metadata", "visualizations", "get", "VizProbeLn1"])
    assert result.exit_code == 0, result.output
    assert "ANC probe line" in result.output
    assert "rows=['pe']" in result.output
    assert "DE1" in result.output


def test_viz_create_forwards_every_flag(pat_profile: None) -> None:  # noqa: ARG001
    """Viz create forwards every flag."""
    mock = AsyncMock(return_value=_viz())
    with patch("dhis2w_core.v42.plugins.metadata.service.create_visualization", new=mock):
        result = CliRunner().invoke(
            build_app(),
            [
                "metadata",
                "visualizations",
                "create",
                "--name",
                "probe",
                "--type",
                "LINE",
                "--de",
                "DE1",
                "--pe",
                "202401",
                "--pe",
                "202402",
                "--ou",
                "OU1",
                "--ou",
                "OU2",
                "--category-dim",
                "pe",
                "--series-dim",
                "ou",
                "--filter-dim",
                "dx",
            ],
        )
    assert result.exit_code == 0, result.output
    assert mock.await_args is not None
    kwargs = mock.await_args.kwargs
    assert kwargs["name"] == "probe"
    assert kwargs["viz_type"] == "LINE"
    assert kwargs["data_elements"] == ["DE1"]
    assert kwargs["periods"] == ["202401", "202402"]
    assert kwargs["organisation_units"] == ["OU1", "OU2"]
    assert kwargs["category_dimension"] == "pe"
    assert kwargs["series_dimension"] == "ou"
    assert kwargs["filter_dimension"] == "dx"


def test_viz_clone_passes_new_name_and_new_uid(pat_profile: None) -> None:  # noqa: ARG001
    """Viz clone passes new name and new uid."""
    mock = AsyncMock(return_value=_viz().model_copy(update={"id": "VizClone001", "name": "cloned"}))
    with patch("dhis2w_core.v42.plugins.metadata.service.clone_visualization", new=mock):
        result = CliRunner().invoke(
            build_app(),
            [
                "metadata",
                "visualizations",
                "clone",
                "VizProbeLn1",
                "--new-name",
                "cloned",
                "--new-uid",
                "VizClone001",
            ],
        )
    assert result.exit_code == 0, result.output
    assert mock.await_args is not None
    assert mock.await_args.args[1] == "VizProbeLn1"
    assert mock.await_args.kwargs["new_name"] == "cloned"
    assert mock.await_args.kwargs["new_uid"] == "VizClone001"


def test_viz_delete_prompts_without_yes_flag(pat_profile: None) -> None:  # noqa: ARG001
    """Viz delete prompts without yes flag."""
    with patch(
        "dhis2w_core.v42.plugins.metadata.service.delete_visualization",
        new=AsyncMock(return_value=None),
    ):
        result = CliRunner().invoke(
            build_app(),
            ["metadata", "visualizations", "delete", "VizProbeLn1"],
            input="n\n",
        )
    assert result.exit_code != 0  # aborted by `typer.confirm(..., abort=True)`


def test_viz_delete_with_yes_skips_prompt(pat_profile: None) -> None:  # noqa: ARG001
    """Viz delete with yes skips prompt."""
    with patch(
        "dhis2w_core.v42.plugins.metadata.service.delete_visualization",
        new=AsyncMock(return_value=None),
    ):
        result = CliRunner().invoke(build_app(), ["metadata", "visualizations", "delete", "VizProbeLn1", "-y"])
    assert result.exit_code == 0, result.output
    assert "deleted" in result.output


# ---- dashboard list / show / add-item / remove-item ----------------------


def test_dashboard_show_renders_item_slot(pat_profile: None) -> None:  # noqa: ARG001
    """Dashboard show renders item slot."""
    with patch(
        "dhis2w_core.v42.plugins.metadata.service.show_dashboard",
        new=AsyncMock(return_value=_dashboard()),
    ):
        result = CliRunner().invoke(build_app(), ["metadata", "dashboards", "get", "DashProbe01"])
    assert result.exit_code == 0, result.output
    assert "Probe dashboard" in result.output
    assert "VizProbeLn1" in result.output
    assert "(0,0 60x20)" in result.output


def test_dashboard_add_item_forwards_slot(pat_profile: None) -> None:  # noqa: ARG001
    """Dashboard add item forwards slot."""
    mock = AsyncMock(return_value=_dashboard())
    with patch("dhis2w_core.v42.plugins.metadata.service.dashboard_add_item", new=mock):
        result = CliRunner().invoke(
            build_app(),
            [
                "metadata",
                "dashboards",
                "add-item",
                "DashProbe01",
                "--viz",
                "VizProbeLn1",
                "--x",
                "20",
                "--y",
                "0",
                "--width",
                "20",
                "--height",
                "15",
            ],
        )
    assert result.exit_code == 0, result.output
    assert mock.await_args is not None
    kwargs = mock.await_args.kwargs
    assert kwargs["x"] == 20
    assert kwargs["y"] == 0
    assert kwargs["width"] == 20
    assert kwargs["height"] == 15


def test_dashboard_add_item_auto_stacks_when_no_slot(pat_profile: None) -> None:  # noqa: ARG001
    """No slot flags should forward every slot field as None (auto-stack path)."""
    mock = AsyncMock(return_value=_dashboard())
    with patch("dhis2w_core.v42.plugins.metadata.service.dashboard_add_item", new=mock):
        result = CliRunner().invoke(
            build_app(),
            ["metadata", "dashboards", "add-item", "DashProbe01", "--viz", "VizProbeLn1"],
        )
    assert result.exit_code == 0, result.output
    assert mock.await_args is not None
    kwargs = mock.await_args.kwargs
    assert kwargs["x"] is None
    assert kwargs["y"] is None
    assert kwargs["width"] is None
    assert kwargs["height"] is None


def test_dashboard_remove_item_reports_new_count(pat_profile: None) -> None:  # noqa: ARG001
    """Dashboard remove item reports new count."""
    empty = _dashboard().model_copy(update={"dashboardItems": []})
    with patch(
        "dhis2w_core.v42.plugins.metadata.service.dashboard_remove_item",
        new=AsyncMock(return_value=empty),
    ):
        result = CliRunner().invoke(
            build_app(),
            ["metadata", "dashboards", "remove-item", "DashProbe01", "Ditm0001"],
        )
    assert result.exit_code == 0, result.output
    assert "removed" in result.output
    assert "now 0 items" in result.output
