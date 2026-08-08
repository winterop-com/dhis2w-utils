"""CliRunner tests for `d2w fhir serve` - the guard, the preflight, and what reaches uvicorn."""

from __future__ import annotations

import builtins
import json
import os
from pathlib import Path
from typing import Any

import pytest
import uvicorn
from dhis2w_cli.main import build_app
from typer.testing import CliRunner

_runner = CliRunner()


@pytest.fixture
def workdir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Run in an empty temporary working directory, with a `probe` profile and nothing of the machine's."""
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
    return tmp_path


class _RecordedRun:
    """What a monkeypatched `uvicorn.run` was asked to serve, so a test can read it back."""

    def __init__(self) -> None:
        self.application: Any = None
        self.keyword_arguments: dict[str, Any] = {}
        self.calls = 0

    def __call__(self, application: Any, **keyword_arguments: Any) -> None:
        """Record one server launch instead of binding a socket."""
        self.application = application
        self.keyword_arguments = keyword_arguments
        self.calls += 1


@pytest.fixture
def recorded_run(monkeypatch: pytest.MonkeyPatch) -> _RecordedRun:
    """Replace `uvicorn.run` with a recorder, so the command runs to completion without listening."""
    recorder = _RecordedRun()
    monkeypatch.setattr(uvicorn, "run", recorder)
    return recorder


def _scaffold(workdir: Path) -> Path:
    """Scaffold a project to serve, and return its root."""
    result = _runner.invoke(build_app(), ["fhir", "init", "project", "--id", "dhis2.fhir.test"])
    assert result.exit_code == 0, result.output
    return workdir / "project"


def _compile(project: Path) -> None:
    """Write what SUSHI would have compiled, which is all the preflight and the store need."""
    compiled = project / "ig" / "fsh-generated" / "resources"
    compiled.mkdir(parents=True, exist_ok=True)
    (compiled / "Questionnaire-BfMAe6Itzgt.json").write_text(
        json.dumps({"resourceType": "Questionnaire", "id": "BfMAe6Itzgt", "status": "active"}),
        encoding="utf-8",
    )


def test_serve_without_the_package_says_how_to_install_it(workdir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The guard names the package and both install routes rather than raising an ImportError."""
    real_import = builtins.__import__

    def _refuse(name: str, *arguments: Any, **keyword_arguments: Any) -> Any:
        if name == "dhis2w_fhir_serve":
            raise ImportError("No module named 'dhis2w_fhir_serve'")
        return real_import(name, *arguments, **keyword_arguments)

    monkeypatch.setattr(builtins, "__import__", _refuse)

    result = _runner.invoke(build_app(), ["fhir", "serve", "project"])

    assert result.exit_code != 0
    assert isinstance(result.exception, LookupError)
    assert "dhis2w-fhir-serve" in str(result.exception)
    assert "pip install 'dhis2w-cli[serve]'" in str(result.exception)


def test_serve_outside_a_project_says_there_is_nothing_to_serve(workdir: Path, recorded_run: _RecordedRun) -> None:
    """No fhir.toml anywhere above the directory means the preflight refuses before any socket opens."""
    result = _runner.invoke(build_app(), ["fhir", "serve", "."])

    assert result.exit_code != 0
    assert "fhir.toml" in str(result.exception)
    assert recorded_run.calls == 0


def test_serve_without_a_compiled_ig_points_at_the_build(workdir: Path, recorded_run: _RecordedRun) -> None:
    """A scaffolded but uncompiled project is refused with the one message the store owns."""
    _scaffold(workdir)

    result = _runner.invoke(build_app(), ["fhir", "serve", "project"])

    assert result.exit_code != 0
    message = str(result.exception)
    assert "d2w fhir generate" in message
    assert "make sushi" in message
    assert recorded_run.calls == 0


def test_serve_launches_the_facade_on_the_requested_address(workdir: Path, recorded_run: _RecordedRun) -> None:
    """A compiled project reaches uvicorn as an app bound to the host and port that were asked for."""
    project = _scaffold(workdir)
    _compile(project)

    result = _runner.invoke(build_app(), ["fhir", "serve", "project", "--host", "0.0.0.0", "--port", "9123"])

    assert result.exit_code == 0, result.output
    assert recorded_run.calls == 1
    assert recorded_run.keyword_arguments["host"] == "0.0.0.0"
    assert recorded_run.keyword_arguments["port"] == 9123
    assert recorded_run.keyword_arguments["access_log"] is False
    assert recorded_run.application.title == "d2w fhir serve"


def test_serve_defaults_to_loopback_and_lenient_codes(workdir: Path, recorded_run: _RecordedRun) -> None:
    """The defaults bind loopback and keep the capture path lenient about unknown codes."""
    project = _scaffold(workdir)
    _compile(project)

    result = _runner.invoke(build_app(), ["fhir", "serve", "project"])

    assert result.exit_code == 0, result.output
    assert recorded_run.keyword_arguments["host"] == "127.0.0.1"
    assert recorded_run.keyword_arguments["port"] == 8080
    assert recorded_run.application.state.settings.strict_codes is False
    assert recorded_run.application.state.settings.live is False


def test_serve_carries_the_flags_into_the_settings(workdir: Path, recorded_run: _RecordedRun) -> None:
    """`--strict-codes` lands on the settings the app factory was built from."""
    project = _scaffold(workdir)
    _compile(project)

    result = _runner.invoke(build_app(), ["fhir", "serve", "project", "--strict-codes"])

    assert result.exit_code == 0, result.output
    settings = recorded_run.application.state.settings
    assert settings.strict_codes is True


def test_serve_takes_the_profile_from_the_root_flag(
    workdir: Path, monkeypatch: pytest.MonkeyPatch, recorded_run: _RecordedRun
) -> None:
    """The profile is the root `d2w -p`, so the command carries no second flag of its own to disagree with it."""
    project = _scaffold(workdir)
    _compile(project)
    # The root callback writes DHIS2_PROFILE straight into the environment; setting it through
    # monkeypatch first is what puts the variable back the way this session found it afterwards.
    monkeypatch.setenv("DHIS2_PROFILE", "probe")

    rejected = _runner.invoke(build_app(), ["fhir", "serve", "project", "--profile", "demo"])
    assert rejected.exit_code != 0
    assert "--profile" in rejected.output
    assert recorded_run.calls == 0

    result = _runner.invoke(build_app(), ["-p", "demo", "fhir", "serve", "project"])
    assert result.exit_code == 0, result.output
    assert os.environ["DHIS2_PROFILE"] == "demo"
    assert recorded_run.application.state.settings.profile is None


def test_serve_announces_the_address_before_the_server_starts(workdir: Path, recorded_run: _RecordedRun) -> None:
    """The banner is what a caller reads while uvicorn boots, so it precedes the run and names the address."""
    project = _scaffold(workdir)
    _compile(project)

    result = _runner.invoke(build_app(), ["fhir", "serve", "project", "--port", "9123"])

    assert result.exit_code == 0, result.output
    assert f"starting {project.resolve()} on http://127.0.0.1:9123 (ctrl-c to stop)" in result.stderr
    assert recorded_run.calls == 1


def test_serve_live_resolves_the_profile_before_it_says_anything(
    workdir: Path, monkeypatch: pytest.MonkeyPatch, recorded_run: _RecordedRun
) -> None:
    """An unknown profile fails as a failure, not under a banner that already claimed the server started."""
    _scaffold(workdir)
    monkeypatch.setenv("DHIS2_PROFILE", "no-such-profile")

    result = _runner.invoke(build_app(), ["fhir", "serve", "project", "--live"])

    assert result.exit_code != 0
    assert "starting" not in result.stderr
    assert recorded_run.calls == 0


def test_serve_live_skips_the_compiled_preflight(workdir: Path, recorded_run: _RecordedRun) -> None:
    """`--live` builds the store from the instance at startup, so an uncompiled project still serves."""
    _scaffold(workdir)

    result = _runner.invoke(build_app(), ["fhir", "serve", "project", "--live"])

    assert result.exit_code == 0, result.output
    assert recorded_run.calls == 1
    assert recorded_run.application.state.settings.live is True


def test_serve_exits_cleanly_on_interrupt(
    workdir: Path, monkeypatch: pytest.MonkeyPatch, recorded_run: _RecordedRun
) -> None:
    """Ctrl-C is how a server is stopped, so it exits 0 rather than as a failed command."""
    project = _scaffold(workdir)
    _compile(project)

    def _interrupt(application: Any, **keyword_arguments: Any) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(uvicorn, "run", _interrupt)

    result = _runner.invoke(build_app(), ["fhir", "serve", "project"])

    assert result.exit_code == 0, result.output
