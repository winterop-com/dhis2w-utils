"""CliRunner + mock tests for `dhis2 metadata program-rule ...`."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from dhis2w_cli.main import build_app
from dhis2w_client.generated.v42.schemas import ProgramRule, ProgramRuleVariable
from dhis2w_client.v42.validation import ExpressionDescription
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


def _rule() -> ProgramRule:
    return ProgramRule.model_validate(
        {
            "id": "PrAnc000001",
            "name": "ANC visit count implausibly high",
            "condition": "#{V_X} > 50",
            "priority": 1,
            "programRuleActions": [
                {"id": "pra1", "programRuleActionType": "SHOWWARNING", "content": "warn"},
            ],
        }
    )


def test_program_rule_show_renders_action_table(pat_profile: None) -> None:  # noqa: ARG001
    """Program rule show renders action table."""
    with patch("dhis2w_core.v42.plugins.metadata.service.show_program_rule", new=AsyncMock(return_value=_rule())):
        result = CliRunner().invoke(build_app(), ["metadata", "program-rules", "get", "PrAnc000001"])
    assert result.exit_code == 0, result.output
    assert "ANC visit count implausibly high" in result.output
    assert "SHOWWARNING" in result.output


def test_program_rule_vars_for_surfaces_source_type(pat_profile: None) -> None:  # noqa: ARG001
    """Program rule vars for surfaces source type."""
    variables = [
        ProgramRuleVariable.model_validate(
            {
                "id": "v1",
                "name": "V_X",
                "programRuleVariableSourceType": "DATAELEMENT_CURRENT_EVENT",
                "dataElement": {"id": "DE1"},
            }
        ),
    ]
    with patch(
        "dhis2w_core.v42.plugins.metadata.service.list_program_rule_variables",
        new=AsyncMock(return_value=variables),
    ):
        result = CliRunner().invoke(build_app(), ["metadata", "program-rules", "vars-for", "PROG"])
    assert result.exit_code == 0, result.output
    assert "V_X" in result.output
    assert "DATAELEMENT_CURRENT_EVENT" in result.output
    assert "DE1" in result.output


def test_program_rule_validate_expression_exits_1_on_error(pat_profile: None) -> None:  # noqa: ARG001
    """Program rule validate expression exits 1 on error."""
    bad = ExpressionDescription.model_validate(
        {"status": "ERROR", "message": "Expression is not valid"},
    )
    with patch(
        "dhis2w_core.v42.plugins.metadata.service.validate_program_rule_expression",
        new=AsyncMock(return_value=bad),
    ):
        result = CliRunner().invoke(
            build_app(),
            ["metadata", "program-rules", "validate-expression", "broken"],
        )
    assert result.exit_code == 1
    assert "ERROR" in result.output


def test_program_rule_where_de_is_used_exits_1_on_miss(pat_profile: None) -> None:  # noqa: ARG001
    """Program rule where de is used exits 1 on miss."""

    async def _no_matches(*_args: Any, **_kwargs: Any) -> list[ProgramRule]:
        return []

    with patch(
        "dhis2w_core.v42.plugins.metadata.service.program_rules_using_data_element",
        new=AsyncMock(side_effect=_no_matches),
    ):
        result = CliRunner().invoke(
            build_app(),
            ["metadata", "program-rules", "where-de-is-used", "DEghost01"],
        )
    assert result.exit_code == 1
    assert "no rules" in result.output.lower()
