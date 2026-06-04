"""CliRunner + mock tests for `dhis2 metadata programs ...`."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from dhis2w_cli.main import build_app
from dhis2w_client.generated.v42.schemas import Program
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


def _program() -> Program:
    return Program.model_validate(
        {
            "id": "PRGprobe0001",
            "name": "Example ANC",
            "shortName": "ExANC",
            "programType": "WITH_REGISTRATION",
            "trackedEntityType": {"id": "TETperson001"},
            "programTrackedEntityAttributes": [{"trackedEntityAttribute": {"id": "TEA_A"}}],
            "organisationUnits": [{"id": "OU_A"}],
        },
    )


def test_programs_create_forwards_tet_and_knobs(pat_profile: None) -> None:  # noqa: ARG001
    """Programs create forwards tet and knobs."""
    mock = AsyncMock(return_value=_program())
    with patch("dhis2w_core.v42.plugins.metadata.service.create_program", new=mock):
        result = CliRunner().invoke(
            build_app(),
            [
                "metadata",
                "programs",
                "create",
                "--name",
                "Example ANC",
                "--short-name",
                "ExANC",
                "--program-type",
                "WITH_REGISTRATION",
                "--tracked-entity-type",
                "TETperson001",
                "--display-incident-date",
                "--only-enroll-once",
                "--min-attrs",
                "1",
            ],
        )
    assert result.exit_code == 0, result.output
    assert mock.await_args is not None
    kwargs = mock.await_args.kwargs
    assert kwargs["name"] == "Example ANC"
    assert kwargs["program_type"] == "WITH_REGISTRATION"
    assert kwargs["tracked_entity_type_uid"] == "TETperson001"
    assert kwargs["display_incident_date"] is True
    assert kwargs["only_enroll_once"] is True
    assert kwargs["min_attributes_required_to_search"] == 1


def test_programs_add_attribute_routes_to_service(pat_profile: None) -> None:  # noqa: ARG001
    """Programs add attribute routes to service."""
    mock = AsyncMock(return_value=_program())
    with patch("dhis2w_core.v42.plugins.metadata.service.add_program_attribute", new=mock):
        result = CliRunner().invoke(
            build_app(),
            [
                "metadata",
                "programs",
                "add-attribute",
                "PRG1",
                "TEA_A",
                "--mandatory",
                "--searchable",
                "--sort-order",
                "2",
            ],
        )
    assert result.exit_code == 0, result.output
    assert mock.await_args is not None
    assert mock.await_args.args[1:] == ("PRG1", "TEA_A")
    kwargs = mock.await_args.kwargs
    assert kwargs["mandatory"] is True
    assert kwargs["searchable"] is True
    assert kwargs["sort_order"] == 2


def test_programs_remove_attribute_routes_to_service(pat_profile: None) -> None:  # noqa: ARG001
    """Programs remove attribute routes to service."""
    mock = AsyncMock(return_value=_program())
    with patch("dhis2w_core.v42.plugins.metadata.service.remove_program_attribute", new=mock):
        result = CliRunner().invoke(
            build_app(),
            ["metadata", "programs", "remove-attribute", "PRG1", "TEA_A"],
        )
    assert result.exit_code == 0, result.output
    assert mock.await_args is not None
    assert mock.await_args.args[1:] == ("PRG1", "TEA_A")


def test_programs_add_to_ou_routes_to_service(pat_profile: None) -> None:  # noqa: ARG001
    """Programs add to ou routes to service."""
    mock = AsyncMock(return_value=_program())
    with patch("dhis2w_core.v42.plugins.metadata.service.add_program_organisation_unit", new=mock):
        result = CliRunner().invoke(
            build_app(),
            ["metadata", "programs", "add-to-ou", "PRG1", "OU_A"],
        )
    assert result.exit_code == 0, result.output
    assert mock.await_args is not None
    assert mock.await_args.args[1:] == ("PRG1", "OU_A")


def test_programs_remove_from_ou_routes_to_service(pat_profile: None) -> None:  # noqa: ARG001
    """Programs remove from ou routes to service."""
    mock = AsyncMock(return_value=_program())
    with patch("dhis2w_core.v42.plugins.metadata.service.remove_program_organisation_unit", new=mock):
        result = CliRunner().invoke(
            build_app(),
            ["metadata", "programs", "remove-from-ou", "PRG1", "OU_A"],
        )
    assert result.exit_code == 0, result.output
    assert mock.await_args is not None
    assert mock.await_args.args[1:] == ("PRG1", "OU_A")


def test_programs_delete_skips_confirm_with_yes(pat_profile: None) -> None:  # noqa: ARG001
    """Programs delete skips confirm with yes."""
    mock = AsyncMock(return_value=None)
    with patch("dhis2w_core.v42.plugins.metadata.service.delete_program", new=mock):
        result = CliRunner().invoke(build_app(), ["metadata", "programs", "delete", "PRG_X", "-y"])
    assert result.exit_code == 0, result.output
    assert mock.await_args is not None
