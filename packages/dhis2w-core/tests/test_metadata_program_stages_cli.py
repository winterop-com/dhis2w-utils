"""CliRunner + mock tests for `dhis2 metadata program-stages ...`."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from dhis2w_cli.main import build_app
from dhis2w_client.generated.v42.schemas import ProgramStage
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


def _stage() -> ProgramStage:
    return ProgramStage.model_validate(
        {
            "id": "PSprobe0001",
            "name": "ANC 1st visit",
            "sortOrder": 1,
            "repeatable": False,
            "program": {"id": "PRGprobe0001"},
            "programStageDataElements": [{"dataElement": {"id": "DE_A"}}],
        },
    )


def test_program_stages_create_forwards_flags(pat_profile: None) -> None:  # noqa: ARG001
    """Program stages create forwards flags."""
    mock = AsyncMock(return_value=_stage())
    with patch("dhis2w_core.v42.plugins.metadata.service.create_program_stage", new=mock):
        result = CliRunner().invoke(
            build_app(),
            [
                "metadata",
                "program-stages",
                "create",
                "--name",
                "ANC 1st visit",
                "--program",
                "PRG1",
                "--repeatable",
                "--sort-order",
                "1",
                "--min-days",
                "0",
                "--standard-interval",
                "30",
            ],
        )
    assert result.exit_code == 0, result.output
    assert mock.await_args is not None
    kwargs = mock.await_args.kwargs
    assert kwargs["name"] == "ANC 1st visit"
    assert kwargs["program_uid"] == "PRG1"
    assert kwargs["repeatable"] is True
    assert kwargs["sort_order"] == 1
    assert kwargs["min_days_from_start"] == 0
    assert kwargs["standard_interval"] == 30


def test_program_stages_add_element_forwards_flags(pat_profile: None) -> None:  # noqa: ARG001
    """Program stages add element forwards flags."""
    mock = AsyncMock(return_value=_stage())
    with patch("dhis2w_core.v42.plugins.metadata.service.add_program_stage_element", new=mock):
        result = CliRunner().invoke(
            build_app(),
            [
                "metadata",
                "program-stages",
                "add-element",
                "PS1",
                "DE_B",
                "--compulsory",
                "--sort-order",
                "2",
            ],
        )
    assert result.exit_code == 0, result.output
    assert mock.await_args is not None
    assert mock.await_args.args[1:] == ("PS1", "DE_B")
    kwargs = mock.await_args.kwargs
    assert kwargs["compulsory"] is True
    assert kwargs["sort_order"] == 2


def test_program_stages_reorder_forwards_uid_list(pat_profile: None) -> None:  # noqa: ARG001
    """Program stages reorder forwards uid list."""
    mock = AsyncMock(return_value=_stage())
    with patch("dhis2w_core.v42.plugins.metadata.service.reorder_program_stage_elements", new=mock):
        result = CliRunner().invoke(
            build_app(),
            ["metadata", "program-stages", "reorder", "PS1", "DE_C", "DE_A", "DE_B"],
        )
    assert result.exit_code == 0, result.output
    assert mock.await_args is not None
    assert mock.await_args.kwargs["data_element_uids"] == ["DE_C", "DE_A", "DE_B"]


def test_program_stages_delete_skips_confirm_with_yes(pat_profile: None) -> None:  # noqa: ARG001
    """Program stages delete skips confirm with yes."""
    mock = AsyncMock(return_value=None)
    with patch("dhis2w_core.v42.plugins.metadata.service.delete_program_stage", new=mock):
        result = CliRunner().invoke(
            build_app(),
            ["metadata", "program-stages", "delete", "PS_X", "-y"],
        )
    assert result.exit_code == 0, result.output
    assert mock.await_args is not None
