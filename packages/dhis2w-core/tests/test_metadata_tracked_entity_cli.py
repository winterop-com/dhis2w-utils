"""CliRunner + mock tests for `dhis2 metadata tracked-entity-attributes|tracked-entity-types ...`."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from dhis2w_cli.main import build_app
from dhis2w_client.generated.v42.schemas import TrackedEntityAttribute, TrackedEntityType
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


def _tea() -> TrackedEntityAttribute:
    return TrackedEntityAttribute.model_validate(
        {
            "id": "TEAprobe0001",
            "name": "National ID",
            "shortName": "NatID",
            "valueType": "TEXT",
            "unique": True,
            "generated": True,
        },
    )


def _tet() -> TrackedEntityType:
    return TrackedEntityType.model_validate(
        {
            "id": "TETprobe0001",
            "name": "Person",
            "shortName": "Person",
            "featureType": "NONE",
            "trackedEntityTypeAttributes": [{"trackedEntityAttribute": {"id": "TEAprobe0001"}}],
        },
    )


# ---- tracked-entity-attributes ---------------------------------------------


def test_tea_create_forwards_flags(pat_profile: None) -> None:  # noqa: ARG001
    """Tea create forwards flags."""
    mock = AsyncMock(return_value=_tea())
    with patch("dhis2w_core.v42.plugins.metadata.service.create_tracked_entity_attribute", new=mock):
        result = CliRunner().invoke(
            build_app(),
            [
                "metadata",
                "tracked-entity-attributes",
                "create",
                "--name",
                "National ID",
                "--short-name",
                "NatID",
                "--value-type",
                "TEXT",
                "--unique",
                "--generated",
                "--pattern",
                "#(RANDOM)",
            ],
        )
    assert result.exit_code == 0, result.output
    assert mock.await_args is not None
    kwargs = mock.await_args.kwargs
    assert kwargs["name"] == "National ID"
    assert kwargs["value_type"] == "TEXT"
    assert kwargs["unique"] is True
    assert kwargs["generated"] is True
    assert kwargs["pattern"] == "#(RANDOM)"


def test_tea_delete_skips_confirm_with_yes(pat_profile: None) -> None:  # noqa: ARG001
    """Tea delete skips confirm with yes."""
    mock = AsyncMock(return_value=None)
    with patch("dhis2w_core.v42.plugins.metadata.service.delete_tracked_entity_attribute", new=mock):
        result = CliRunner().invoke(
            build_app(),
            ["metadata", "tracked-entity-attributes", "delete", "TEA_X", "-y"],
        )
    assert result.exit_code == 0, result.output
    assert mock.await_args is not None


# ---- tracked-entity-types --------------------------------------------------


def test_tet_create_forwards_every_flag(pat_profile: None) -> None:  # noqa: ARG001
    """Tet create forwards every flag."""
    mock = AsyncMock(return_value=_tet())
    with patch("dhis2w_core.v42.plugins.metadata.service.create_tracked_entity_type", new=mock):
        result = CliRunner().invoke(
            build_app(),
            [
                "metadata",
                "tracked-entity-types",
                "create",
                "--name",
                "Person",
                "--short-name",
                "Person",
                "--allow-audit-log",
                "--feature-type",
                "NONE",
                "--min-attrs",
                "1",
            ],
        )
    assert result.exit_code == 0, result.output
    assert mock.await_args is not None
    kwargs = mock.await_args.kwargs
    assert kwargs["name"] == "Person"
    assert kwargs["allow_audit_log"] is True
    assert kwargs["feature_type"] == "NONE"
    assert kwargs["min_attributes_required_to_search"] == 1


def test_tet_add_attribute_routes_to_service(pat_profile: None) -> None:  # noqa: ARG001
    """Tet add attribute routes to service."""
    mock = AsyncMock(return_value=_tet())
    with patch("dhis2w_core.v42.plugins.metadata.service.add_tracked_entity_type_attribute", new=mock):
        result = CliRunner().invoke(
            build_app(),
            [
                "metadata",
                "tracked-entity-types",
                "add-attribute",
                "TET1",
                "TEA_A",
                "--mandatory",
                "--searchable",
            ],
        )
    assert result.exit_code == 0, result.output
    assert mock.await_args is not None
    assert mock.await_args.args[1:] == ("TET1", "TEA_A")
    kwargs = mock.await_args.kwargs
    assert kwargs["mandatory"] is True
    assert kwargs["searchable"] is True


def test_tet_remove_attribute_routes_to_service(pat_profile: None) -> None:  # noqa: ARG001
    """Tet remove attribute routes to service."""
    mock = AsyncMock(return_value=_tet())
    with patch("dhis2w_core.v42.plugins.metadata.service.remove_tracked_entity_type_attribute", new=mock):
        result = CliRunner().invoke(
            build_app(),
            ["metadata", "tracked-entity-types", "remove-attribute", "TET1", "TEA_A"],
        )
    assert result.exit_code == 0, result.output
    assert mock.await_args is not None
    assert mock.await_args.args[1:] == ("TET1", "TEA_A")


def test_tet_delete_skips_confirm_with_yes(pat_profile: None) -> None:  # noqa: ARG001
    """Tet delete skips confirm with yes."""
    mock = AsyncMock(return_value=None)
    with patch("dhis2w_core.v42.plugins.metadata.service.delete_tracked_entity_type", new=mock):
        result = CliRunner().invoke(
            build_app(),
            ["metadata", "tracked-entity-types", "delete", "TET_X", "-y"],
        )
    assert result.exit_code == 0, result.output
    assert mock.await_args is not None
