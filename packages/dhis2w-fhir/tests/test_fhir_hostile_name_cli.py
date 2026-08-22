"""CliRunner tests for how `d2w fhir generate` answers the hostile-name question.

Three answers reach the service as one gate: the two flags, the `fhir.toml` dial, and the question
a terminal is asked when neither decided. The service is mocked to a gate-reading stub, so what is
measured here is the decision the command hands down rather than a generate run.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from dhis2w_cli.main import build_app
from dhis2w_core.cli_errors import CliUserError
from dhis2w_fhir import GenerateFullReport, GenerateReport, OptionSetIn
from dhis2w_fhir.hostile_names import HostileNameGate
from typer.testing import CliRunner

_runner = CliRunner()

_FHIR_TOML = """
[ig]
id = "dhis2.fhir.test"
canonical = "http://example.org/fhir"
name = "Dhis2FhirTest"
title = "DHIS2 FHIR Test IG"
publisher = "Test Organisation"
"""

#: The DHIS2 name the stubbed service screens, and the wording a rewrite publishes in its place.
_HOSTILE_NAME = "5 to < 15 years, Female"
_REWRITTEN_NAME = "5 to under 15 years, Female"


@pytest.fixture
def fhir_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A working directory holding a fhir.toml and a default profile, as the generate commands need."""
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
    monkeypatch.setenv("COLUMNS", "300")
    (tmp_path / "fhir.toml").write_text(_FHIR_TOML, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _screening_stub(screened: list[str]) -> AsyncMock:
    """A stubbed generate that screens one hostile name through the gate the command handed it."""

    async def _generate(*_args: Any, gate: HostileNameGate | None = None, **_kwargs: Any) -> GenerateReport:
        """Screen one option set and record the name the run would publish."""
        assert gate is not None
        option_sets = gate.screen([OptionSetIn(uid="Os1aaaaaaaa", name=_HOSTILE_NAME)], [])
        screened.append(option_sets[0].name)
        return GenerateReport(project_root=Path("/project"), target_directory="terminology")

    return AsyncMock(side_effect=_generate)


def _full_run_stub(screened: list[str]) -> Any:
    """A stubbed full generate that screens one hostile name and answers with the seven-target report."""

    async def _generate(*_args: Any, gate: HostileNameGate | None = None, **_kwargs: Any) -> GenerateFullReport:
        """Screen one option set, then report every target as having written nothing."""
        assert gate is not None
        screened.append(gate.screen([OptionSetIn(uid="Os1aaaaaaaa", name=_HOSTILE_NAME)], [])[0].name)
        report = GenerateReport(project_root=Path("/project"), target_directory="terminology")
        return GenerateFullReport(
            foundation=report,
            option_sets=report,
            categories=report,
            questionnaires=report,
            examples=report,
            organisation_units=report,
            pages=report,
        )

    return _generate


def _invoke(arguments: list[str], stub: AsyncMock, *, stdin: str | None = None, a_terminal: bool = False) -> Any:
    """Run one generate command against the stub, with the terminal answer the test is about."""
    with (
        patch("dhis2w_fhir.service.generate_option_sets", new=stub),
        patch("dhis2w_fhir.cli._has_terminal", return_value=a_terminal),
    ):
        return _runner.invoke(build_app(), arguments, input=stdin)


def test_the_substitute_flag_publishes_the_rewritten_name(fhir_project: Path) -> None:  # noqa: ARG001
    """`--substitute-hostile-names` answers the question before it is asked, and no prompt appears."""
    screened: list[str] = []

    result = _invoke(["fhir", "generate", "--substitute-hostile-names", "option-sets"], _screening_stub(screened))

    assert result.exit_code == 0, result.output
    assert screened == [_REWRITTEN_NAME]
    assert "Rewrite these names" not in result.output


def test_the_refuse_flag_leaves_the_name_as_dhis2_states_it(fhir_project: Path) -> None:  # noqa: ARG001
    """`--refuse-hostile-names` answers it the other way, and the emit-site refusal then acts on the name."""
    screened: list[str] = []

    result = _invoke(["fhir", "generate", "--refuse-hostile-names", "option-sets"], _screening_stub(screened))

    assert result.exit_code == 0, result.output
    assert screened == [_HOSTILE_NAME]


def test_the_two_flags_together_are_refused(fhir_project: Path) -> None:  # noqa: ARG001
    """The flags state opposite answers to one question, so passing both is a mistake worth naming."""
    result = _invoke(
        ["fhir", "generate", "--substitute-hostile-names", "--refuse-hostile-names", "option-sets"],
        _screening_stub([]),
    )

    assert result.exit_code != 0
    assert isinstance(result.exception, CliUserError)
    assert "opposite answers" in str(result.exception)
    assert "--substitute-hostile-names" in str(result.exception)


def test_the_flag_reaches_a_bare_run(fhir_project: Path) -> None:  # noqa: ARG001
    """The bare `d2w fhir generate` reads the same flag its named targets do."""
    screened: list[str] = []
    stub = AsyncMock(side_effect=_full_run_stub(screened))
    with (
        patch("dhis2w_fhir.service.generate_full", new=stub),
        patch("dhis2w_fhir.cli._has_terminal", return_value=False),
    ):
        result = _runner.invoke(build_app(), ["fhir", "generate", "--substitute-hostile-names"])

    assert result.exit_code == 0, result.output
    assert screened == [_REWRITTEN_NAME]


def test_the_project_dial_answers_when_no_flag_does(fhir_project: Path) -> None:
    """`hostile_names = "substitute"` in fhir.toml is the project's standing answer."""
    config_path = fhir_project / "fhir.toml"
    config_path.write_text(
        f'{config_path.read_text(encoding="utf-8")}\n[generate]\nhostile_names = "substitute"\n', encoding="utf-8"
    )
    screened: list[str] = []

    result = _invoke(["fhir", "generate", "option-sets"], _screening_stub(screened))

    assert result.exit_code == 0, result.output
    assert screened == [_REWRITTEN_NAME]


def test_the_flag_beats_the_project_dial(fhir_project: Path) -> None:
    """One run's flag overrides the project's standing answer, which is what a flag is for."""
    config_path = fhir_project / "fhir.toml"
    config_path.write_text(
        f'{config_path.read_text(encoding="utf-8")}\n[generate]\nhostile_names = "refuse"\n', encoding="utf-8"
    )
    screened: list[str] = []

    result = _invoke(["fhir", "generate", "--substitute-hostile-names", "option-sets"], _screening_stub(screened))

    assert result.exit_code == 0, result.output
    assert screened == [_REWRITTEN_NAME]


def test_a_terminal_is_asked_and_yes_rewrites(fhir_project: Path) -> None:  # noqa: ARG001
    """With no flag and no dial, the person running it is shown the names and asked."""
    screened: list[str] = []

    result = _invoke(["fhir", "generate", "option-sets"], _screening_stub(screened), stdin="y\n", a_terminal=True)

    assert result.exit_code == 0, result.output
    assert screened == [_REWRITTEN_NAME]
    assert "DHIS2 names the IG publisher cannot build" in result.output
    assert f"{_HOSTILE_NAME!r} -> {_REWRITTEN_NAME!r}" in result.output
    assert "DHIS2 is never modified" in result.output
    assert "ConceptMaps keep the original identifiers" in result.output
    assert "Rewrite these names for publication?" in result.output


def test_a_terminal_answering_no_leaves_every_name_alone(fhir_project: Path) -> None:  # noqa: ARG001
    """No is the default answer, and it publishes what DHIS2 states - which is what the refusal reads."""
    screened: list[str] = []

    result = _invoke(["fhir", "generate", "option-sets"], _screening_stub(screened), stdin="n\n", a_terminal=True)

    assert result.exit_code == 0, result.output
    assert screened == [_HOSTILE_NAME]


def test_a_script_is_never_hung_on_the_question(fhir_project: Path) -> None:  # noqa: ARG001
    """With no terminal to ask on, the run says which flags answer it and rewrites nothing."""
    screened: list[str] = []

    result = _invoke(["fhir", "generate", "option-sets"], _screening_stub(screened))

    assert result.exit_code == 0, result.output
    assert screened == [_HOSTILE_NAME]
    assert "no terminal to ask on" in result.output
    assert "--substitute-hostile-names" in result.output
    assert "--refuse-hostile-names" in result.output
    assert "Rewrite these names for publication?" not in result.output
