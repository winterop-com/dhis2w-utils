"""CliRunner + mock tests for `d2w metadata options ...`.

Service-layer hits dhis2w-client; we mock those at the module boundary so
the CLI exercise stays fast and stable without a live stack.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from dhis2w_cli.main import build_app
from dhis2w_client import OptionSpec, UpsertReport
from dhis2w_client.generated.v42.common import Reference
from dhis2w_client.generated.v42.schemas import Option, OptionSet
from typer.testing import CliRunner


@pytest.fixture
def pat_profile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Write a global profiles.toml with one PAT profile and point resolution at it."""
    config_dir = tmp_path / ".config" / "dhis2"
    config_dir.mkdir(parents=True)
    profiles = config_dir / "profiles.toml"
    profiles.write_text(
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
    # Clear cross-test pollution — other tests invoke `d2w --profile ghost`
    # which writes into `os.environ` directly inside `dhis2w-cli/main.py`.
    monkeypatch.delenv("DHIS2_PROFILE", raising=False)
    monkeypatch.chdir(tmp_path)


def _vaccine_set() -> OptionSet:
    return OptionSet(
        id="OsVaccType1",
        code="VACCINE_TYPE",
        name="Vaccine type",
        options=[
            Reference(id="OptVacBCG01"),
            Reference(id="OptVacMes01"),
        ],
    )


def test_options_show_renders_table_for_code_input(pat_profile: None) -> None:  # noqa: ARG001
    """`show VACCINE_TYPE` routes through `service.show_option_set` and prints each option."""
    with patch("dhis2w_core.v42.plugins.metadata.service.show_option_set", new=AsyncMock(return_value=_vaccine_set())):
        runner = CliRunner()
        result = runner.invoke(build_app(), ["metadata", "option-sets", "get", "VACCINE_TYPE"])
    assert result.exit_code == 0, result.output
    assert "Vaccine type" in result.output
    assert "VACCINE_TYPE" in result.output
    assert "OsVaccType1" in result.output


def test_options_show_exits_1_when_not_found(pat_profile: None) -> None:  # noqa: ARG001
    """None from the service → exit 1 with a stderr hint."""
    with patch("dhis2w_core.v42.plugins.metadata.service.show_option_set", new=AsyncMock(return_value=None)):
        runner = CliRunner()
        result = runner.invoke(build_app(), ["metadata", "option-sets", "get", "DOES_NOT_EXIST"])
    assert result.exit_code == 1


def test_options_find_rejects_both_selectors(pat_profile: None) -> None:  # noqa: ARG001
    """`--code X --name Y` is a caller error — Typer's BadParameter maps to exit 2."""
    runner = CliRunner()
    result = runner.invoke(
        build_app(),
        ["metadata", "option-sets", "find", "--set", "VACCINE_TYPE", "--code", "X", "--name", "Y"],
    )
    assert result.exit_code != 0
    assert "exactly one" in result.output.lower()


def test_options_find_hit_prints_option_summary(pat_profile: None) -> None:  # noqa: ARG001
    """Options find hit prints option summary."""
    option = Option(id="OptVacMes01", code="MEASLES", name="Measles", sortOrder=1)
    with patch(
        "dhis2w_core.v42.plugins.metadata.service.find_option_in_set",
        new=AsyncMock(return_value=option),
    ):
        runner = CliRunner()
        result = runner.invoke(
            build_app(),
            ["metadata", "option-sets", "find", "--set", "VACCINE_TYPE", "--code", "MEASLES"],
        )
    assert result.exit_code == 0, result.output
    assert "MEASLES" in result.output
    assert "OptVacMes01" in result.output


def test_options_sync_from_json_file(pat_profile: None, tmp_path: Path) -> None:  # noqa: ARG001
    """Options sync from json file."""
    spec = [
        {"code": "BCG", "name": "BCG"},
        {"code": "HPV", "name": "HPV vaccine"},
    ]
    spec_file = tmp_path / "spec.json"
    spec_file.write_text(json.dumps(spec), encoding="utf-8")

    report = UpsertReport(
        option_set_uid="OsVaccType1",
        added=["HPV"],
        updated=[],
        removed=[],
        skipped=["BCG"],
        dry_run=False,
    )
    captured_spec: list[OptionSpec] = []

    async def fake_sync(
        profile: Any,
        *,
        option_set_uid_or_code: str,
        spec: list[OptionSpec],
        remove_missing: bool,
        dry_run: bool,
    ) -> UpsertReport:
        captured_spec.extend(spec)
        assert option_set_uid_or_code == "VACCINE_TYPE"
        assert remove_missing is False
        assert dry_run is False
        return report

    with patch("dhis2w_core.v42.plugins.metadata.service.sync_option_set", new=fake_sync):
        runner = CliRunner()
        result = runner.invoke(
            build_app(),
            ["metadata", "option-sets", "sync", "VACCINE_TYPE", str(spec_file)],
        )
    assert result.exit_code == 0, result.output
    assert [s.code for s in captured_spec] == ["BCG", "HPV"]
    assert "added" in result.output
    assert "HPV" in result.output


def test_options_sync_rejects_non_list_json(pat_profile: None, tmp_path: Path) -> None:  # noqa: ARG001
    """Spec file must be a JSON array of objects; a top-level object raises BadParameter."""
    spec_file = tmp_path / "bad.json"
    spec_file.write_text('{"code": "BCG", "name": "BCG"}', encoding="utf-8")
    runner = CliRunner()
    result = runner.invoke(
        build_app(),
        ["metadata", "option-sets", "sync", "VACCINE_TYPE", str(spec_file)],
    )
    assert result.exit_code != 0
    assert "JSON array" in result.output
