"""CliRunner + mock tests for `dhis2 metadata validation-rules|predictors ...` + their groups."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from dhis2w_cli.main import build_app
from dhis2w_client.generated.v42.schemas import (
    Predictor,
    PredictorGroup,
    ValidationRule,
    ValidationRuleGroup,
)
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


def _validation_rule() -> ValidationRule:
    return ValidationRule.model_validate(
        {
            "id": "VR_PROBE001",
            "name": "BCG gt zero",
            "periodType": "Monthly",
            "operator": "greater_than",
            "importance": "HIGH",
            "leftSide": {"expression": "#{deBCG000001}"},
            "rightSide": {"expression": "0"},
        },
    )


def _validation_rule_group() -> ValidationRuleGroup:
    return ValidationRuleGroup.model_validate(
        {
            "id": "VRG_PROBE01",
            "name": "BCG rules",
            "validationRules": [{"id": "VR_PROBE001"}],
        },
    )


def _predictor() -> Predictor:
    return Predictor.model_validate(
        {
            "id": "PRD_PROBE01",
            "name": "BCG 3m rolling",
            "periodType": "Monthly",
            "sequentialSampleCount": 3,
            "output": {"id": "deOutput0001"},
            "generator": {"expression": "#{deBCG000001}"},
        },
    )


def _predictor_group() -> PredictorGroup:
    return PredictorGroup.model_validate(
        {
            "id": "PDG_PROBE01",
            "name": "BCG predictors",
            "predictors": [{"id": "PRD_PROBE01"}],
        },
    )


# ---- validation-rules list / create / delete --------------------------------


def test_validation_rules_create_forwards_flags(pat_profile: None) -> None:  # noqa: ARG001
    """Validation rules create forwards flags."""
    mock = AsyncMock(return_value=_validation_rule())
    with patch("dhis2w_core.v42.plugins.metadata.service.create_validation_rule", new=mock):
        result = CliRunner().invoke(
            build_app(),
            [
                "metadata",
                "validation-rules",
                "create",
                "--name",
                "BCG gt zero",
                "--short-name",
                "BCGgt0",
                "--left",
                "#{deBCG000001}",
                "--operator",
                "greater_than",
                "--right",
                "0",
                "--importance",
                "HIGH",
                "--ou-level",
                "4",
            ],
        )
    assert result.exit_code == 0, result.output
    assert mock.await_args is not None
    kwargs = mock.await_args.kwargs
    assert kwargs["name"] == "BCG gt zero"
    assert kwargs["left_expression"] == "#{deBCG000001}"
    assert kwargs["operator"] == "greater_than"
    assert kwargs["right_expression"] == "0"
    assert kwargs["importance"] == "HIGH"
    assert kwargs["organisation_unit_levels"] == [4]


def test_validation_rules_delete_skips_confirm_with_yes(pat_profile: None) -> None:  # noqa: ARG001
    """Validation rules delete skips confirm with yes."""
    mock = AsyncMock(return_value=None)
    with patch("dhis2w_core.v42.plugins.metadata.service.delete_validation_rule", new=mock):
        result = CliRunner().invoke(build_app(), ["metadata", "validation-rules", "delete", "VR_X", "-y"])
    assert result.exit_code == 0, result.output
    assert mock.await_args is not None


# ---- validation-rule-groups -------------------------------------------------


def test_validation_rule_groups_add_members_forwards_repeated_flag(pat_profile: None) -> None:  # noqa: ARG001
    """Validation rule groups add members forwards repeated flag."""
    mock = AsyncMock(return_value=_validation_rule_group())
    with patch("dhis2w_core.v42.plugins.metadata.service.add_validation_rule_group_members", new=mock):
        result = CliRunner().invoke(
            build_app(),
            [
                "metadata",
                "validation-rule-groups",
                "add-members",
                "VRG_X",
                "--rule",
                "VR_A",
                "-r",
                "VR_B",
            ],
        )
    assert result.exit_code == 0, result.output
    assert mock.await_args is not None
    assert mock.await_args.kwargs["validation_rule_uids"] == ["VR_A", "VR_B"]


# ---- predictors list / create / delete -------------------------------------


def test_predictors_create_forwards_every_flag(pat_profile: None) -> None:  # noqa: ARG001
    """Predictors create forwards every flag."""
    mock = AsyncMock(return_value=_predictor())
    with patch("dhis2w_core.v42.plugins.metadata.service.create_predictor", new=mock):
        result = CliRunner().invoke(
            build_app(),
            [
                "metadata",
                "predictors",
                "create",
                "--name",
                "BCG 3m rolling",
                "--short-name",
                "BCG3m",
                "--expression",
                "#{deBCG000001}",
                "--output",
                "deOutput0001",
                "--sequential",
                "3",
                "--ou-level",
                "ouLvlFac001",
            ],
        )
    assert result.exit_code == 0, result.output
    assert mock.await_args is not None
    kwargs = mock.await_args.kwargs
    assert kwargs["name"] == "BCG 3m rolling"
    assert kwargs["expression"] == "#{deBCG000001}"
    assert kwargs["output_data_element_uid"] == "deOutput0001"
    assert kwargs["sequential_sample_count"] == 3
    assert kwargs["organisation_unit_level_uids"] == ["ouLvlFac001"]


def test_predictors_delete_skips_confirm_with_yes(pat_profile: None) -> None:  # noqa: ARG001
    """Predictors delete skips confirm with yes."""
    mock = AsyncMock(return_value=None)
    with patch("dhis2w_core.v42.plugins.metadata.service.delete_predictor", new=mock):
        result = CliRunner().invoke(build_app(), ["metadata", "predictors", "delete", "PRD_X", "-y"])
    assert result.exit_code == 0, result.output
    assert mock.await_args is not None


# ---- predictor-groups -------------------------------------------------------


def test_predictor_groups_add_members_forwards_repeated_flag(pat_profile: None) -> None:  # noqa: ARG001
    """Predictor groups add members forwards repeated flag."""
    mock = AsyncMock(return_value=_predictor_group())
    with patch("dhis2w_core.v42.plugins.metadata.service.add_predictor_group_members", new=mock):
        result = CliRunner().invoke(
            build_app(),
            [
                "metadata",
                "predictor-groups",
                "add-members",
                "PDG_X",
                "--predictor",
                "PRD_A",
                "-p",
                "PRD_B",
            ],
        )
    assert result.exit_code == 0, result.output
    assert mock.await_args is not None
    assert mock.await_args.kwargs["predictor_uids"] == ["PRD_A", "PRD_B"]
