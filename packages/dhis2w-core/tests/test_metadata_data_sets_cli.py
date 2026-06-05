"""CliRunner + mock tests for `dhis2 metadata data-sets ...` and `dhis2 metadata sections ...`."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from dhis2w_cli.main import build_app
from dhis2w_client.generated.v42.schemas import DataSet, Section
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


def _data_set() -> DataSet:
    return DataSet.model_validate(
        {
            "id": "DS_PROBE001",
            "name": "ANC Monthly",
            "periodType": "Monthly",
            "dataSetElements": [{"dataElement": {"id": "DE_A"}}],
            "sections": [{"id": "SEC1"}],
        },
    )


def _section() -> Section:
    return Section.model_validate(
        {
            "id": "SEC_PROBE01",
            "name": "Stock",
            "sortOrder": 1,
            "dataSet": {"id": "DS_PROBE001"},
            "dataElements": [{"id": "DE_A"}, {"id": "DE_B"}],
        },
    )


# ---- data-sets list / show / create / rename / add-element / remove-element / delete ----


def test_data_sets_show_renders_counts(pat_profile: None) -> None:  # noqa: ARG001
    """Data sets show renders counts."""
    with patch(
        "dhis2w_core.v42.plugins.metadata.service.show_data_set",
        new=AsyncMock(return_value=_data_set()),
    ):
        result = CliRunner().invoke(build_app(), ["metadata", "data-sets", "get", "DS_PROBE001"])
    assert result.exit_code == 0, result.output
    assert "ANC Monthly" in result.output
    assert "elements:     1" in result.output
    assert "sections:     1" in result.output


def test_data_sets_create_forwards_every_flag(pat_profile: None) -> None:  # noqa: ARG001
    """Data sets create forwards every flag."""
    mock = AsyncMock(return_value=_data_set())
    with patch("dhis2w_core.v42.plugins.metadata.service.create_data_set", new=mock):
        result = CliRunner().invoke(
            build_app(),
            [
                "metadata",
                "data-sets",
                "create",
                "--name",
                "ANC Monthly",
                "--short-name",
                "ANCm",
                "--period-type",
                "Monthly",
                "--open-future-periods",
                "2",
                "--expiry-days",
                "10",
                "--timely-days",
                "3",
            ],
        )
    assert result.exit_code == 0, result.output
    assert mock.await_args is not None
    kwargs = mock.await_args.kwargs
    assert kwargs["name"] == "ANC Monthly"
    assert kwargs["short_name"] == "ANCm"
    assert kwargs["period_type"] == "Monthly"
    assert kwargs["open_future_periods"] == 2
    assert kwargs["expiry_days"] == 10
    assert kwargs["timely_days"] == 3


def test_data_sets_add_element_forwards_category_combo(pat_profile: None) -> None:  # noqa: ARG001
    """Data sets add element forwards category combo."""
    mock = AsyncMock(return_value=_data_set())
    with patch("dhis2w_core.v42.plugins.metadata.service.add_data_set_element", new=mock):
        result = CliRunner().invoke(
            build_app(),
            [
                "metadata",
                "data-sets",
                "add-element",
                "DS_PROBE001",
                "DE_B",
                "--category-combo",
                "cc_override",
            ],
        )
    assert result.exit_code == 0, result.output
    assert mock.await_args is not None
    args = mock.await_args.args
    kwargs = mock.await_args.kwargs
    assert args[1:] == ("DS_PROBE001", "DE_B")
    assert kwargs["category_combo_uid"] == "cc_override"


def test_data_sets_remove_element_routes_to_service(pat_profile: None) -> None:  # noqa: ARG001
    """Data sets remove element routes to service."""
    mock = AsyncMock(return_value=_data_set())
    with patch("dhis2w_core.v42.plugins.metadata.service.remove_data_set_element", new=mock):
        result = CliRunner().invoke(
            build_app(),
            ["metadata", "data-sets", "remove-element", "DS_PROBE001", "DE_A"],
        )
    assert result.exit_code == 0, result.output
    assert mock.await_args is not None
    assert mock.await_args.args[1:] == ("DS_PROBE001", "DE_A")


def test_data_sets_delete_skips_confirm_with_yes(pat_profile: None) -> None:  # noqa: ARG001
    """Data sets delete skips confirm with yes."""
    mock = AsyncMock(return_value=None)
    with patch("dhis2w_core.v42.plugins.metadata.service.delete_data_set", new=mock):
        result = CliRunner().invoke(build_app(), ["metadata", "data-sets", "delete", "DS_PROBE001", "--yes"])
    assert result.exit_code == 0, result.output
    assert mock.await_args is not None


# ---- sections list / show / create / add-element / reorder / delete -----------


def test_sections_create_seeds_data_elements(pat_profile: None) -> None:  # noqa: ARG001
    """Sections create seeds data elements."""
    mock = AsyncMock(return_value=_section())
    with patch("dhis2w_core.v42.plugins.metadata.service.create_section", new=mock):
        result = CliRunner().invoke(
            build_app(),
            [
                "metadata",
                "sections",
                "create",
                "--name",
                "Stock",
                "--data-set",
                "DS_PROBE001",
                "--sort-order",
                "1",
                "--data-element",
                "DE_A",
                "-de",
                "DE_B",
            ],
        )
    assert result.exit_code == 0, result.output
    assert mock.await_args is not None
    kwargs = mock.await_args.kwargs
    assert kwargs["name"] == "Stock"
    assert kwargs["data_set_uid"] == "DS_PROBE001"
    assert kwargs["sort_order"] == 1
    assert kwargs["data_element_uids"] == ["DE_A", "DE_B"]


def test_sections_add_element_forwards_position(pat_profile: None) -> None:  # noqa: ARG001
    """Sections add element forwards position."""
    mock = AsyncMock(return_value=_section())
    with patch("dhis2w_core.v42.plugins.metadata.service.add_section_element", new=mock):
        result = CliRunner().invoke(
            build_app(),
            ["metadata", "sections", "add-element", "SEC_PROBE01", "DE_B", "--position", "0"],
        )
    assert result.exit_code == 0, result.output
    assert mock.await_args is not None
    assert mock.await_args.args[1:] == ("SEC_PROBE01", "DE_B")
    assert mock.await_args.kwargs["position"] == 0


def test_sections_reorder_forwards_uid_list(pat_profile: None) -> None:  # noqa: ARG001
    """Sections reorder forwards uid list."""
    mock = AsyncMock(return_value=_section())
    with patch("dhis2w_core.v42.plugins.metadata.service.reorder_section_elements", new=mock):
        result = CliRunner().invoke(
            build_app(),
            ["metadata", "sections", "reorder", "SEC_PROBE01", "DE_C", "DE_A", "DE_B"],
        )
    assert result.exit_code == 0, result.output
    assert mock.await_args is not None
    assert mock.await_args.kwargs["data_element_uids"] == ["DE_C", "DE_A", "DE_B"]


def test_sections_delete_skips_confirm_with_yes(pat_profile: None) -> None:  # noqa: ARG001
    """Sections delete skips confirm with yes."""
    mock = AsyncMock(return_value=None)
    with patch("dhis2w_core.v42.plugins.metadata.service.delete_section", new=mock):
        result = CliRunner().invoke(build_app(), ["metadata", "sections", "delete", "SEC_PROBE01", "--yes"])
    assert result.exit_code == 0, result.output
    assert mock.await_args is not None
