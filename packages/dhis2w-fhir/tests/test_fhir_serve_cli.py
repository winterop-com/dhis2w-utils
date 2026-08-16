"""CliRunner tests for `d2w fhir serve` - the guard, the preflights, and what reaches uvicorn."""

from __future__ import annotations

import builtins
import errno
import json
import os
import socket
import sys
from pathlib import Path
from typing import Any

import pytest
import uvicorn
from dhis2w_cli.main import build_app
from dhis2w_fhir import cli as fhir_cli
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

[profiles.demo]
base_url = "https://demo.example"
auth = "pat"
token = "d2p_demo"
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
    """Replace `uvicorn.run` with a recorder, so the command runs to completion without listening.

    The bind preflight is recorded rather than run for the same reason: these tests point the
    command at addresses the machine really owns - the 8080 default among them - and a probe
    that truly binds would couple them to whatever the machine happens to be running. The
    tests about the preflight itself install their own recorder and keep the real probe.
    """
    recorder = _RecordedRun()
    monkeypatch.setattr(uvicorn, "run", recorder)
    monkeypatch.setattr(fhir_cli, "_preflight_bind", lambda host, port: None)
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


def _write_serve_table(project: Path, body: str) -> None:
    """Append a `[serve]` table to the scaffolded fhir.toml."""
    config_path = project / "fhir.toml"
    config_path.write_text(f"{config_path.read_text(encoding='utf-8')}\n[serve]\n{body}\n", encoding="utf-8")


def test_serve_reads_its_address_from_the_project_config(workdir: Path, recorded_run: _RecordedRun) -> None:
    """A `[serve]` table states once where this project is served, so a bare `serve` honours it."""
    project = _scaffold(workdir)
    _compile(project)
    _write_serve_table(project, 'host = "0.0.0.0"\nport = 8090\nstrict_codes = true')

    result = _runner.invoke(build_app(), ["fhir", "serve", "project"])

    assert result.exit_code == 0, result.output
    assert recorded_run.keyword_arguments["host"] == "0.0.0.0"
    assert recorded_run.keyword_arguments["port"] == 8090
    assert recorded_run.application.state.settings.strict_codes is True
    assert "http://0.0.0.0:8090" in result.output


def test_a_serve_flag_beats_the_table_and_the_table_beats_the_default(
    workdir: Path, recorded_run: _RecordedRun
) -> None:
    """Three-way precedence: an explicit flag wins, an unflagged key falls to the table, the rest to defaults."""
    project = _scaffold(workdir)
    _compile(project)
    _write_serve_table(project, "port = 8090\nstrict_codes = true")

    result = _runner.invoke(build_app(), ["fhir", "serve", "project", "--port", "9123", "--no-strict-codes"])

    assert result.exit_code == 0, result.output
    assert recorded_run.keyword_arguments["port"] == 9123
    assert recorded_run.keyword_arguments["host"] == "127.0.0.1"
    assert recorded_run.application.state.settings.strict_codes is False


def test_the_basemaps_follow_the_same_three_way_precedence(workdir: Path, recorded_run: _RecordedRun) -> None:
    """One layer by default, the table restates the offer once per project, and the flag beats both."""
    from dhis2w_fhir.config import DEFAULT_BASEMAP_NAME, DEFAULT_BASEMAP_TEMPLATE

    project = _scaffold(workdir)
    _compile(project)

    default_run = _runner.invoke(build_app(), ["fhir", "serve", "project"])
    assert default_run.exit_code == 0, default_run.output
    assert [(layer.name, layer.url) for layer in recorded_run.application.state.settings.basemaps] == [
        (DEFAULT_BASEMAP_NAME, DEFAULT_BASEMAP_TEMPLATE)
    ]

    _write_serve_table(project, "basemaps = []")
    from_table = _runner.invoke(build_app(), ["fhir", "serve", "project"])
    assert from_table.exit_code == 0, from_table.output
    assert recorded_run.application.state.settings.basemaps == []

    from_flag = _runner.invoke(
        build_app(), ["fhir", "serve", "project", "--basemap", "Streets=https://tiles.example/{z}/{x}/{y}.png"]
    )
    assert from_flag.exit_code == 0, from_flag.output
    assert [(layer.name, layer.url) for layer in recorded_run.application.state.settings.basemaps] == [
        ("Streets", "https://tiles.example/{z}/{x}/{y}.png")
    ]


def test_a_repeated_basemap_flag_offers_every_layer_it_names_in_the_order_it_named_them(
    workdir: Path, recorded_run: _RecordedRun
) -> None:
    """The layer control is a list, so the flag that fills it is repeatable and the order is the offer."""
    project = _scaffold(workdir)
    _compile(project)

    result = _runner.invoke(
        build_app(),
        [
            "fhir",
            "serve",
            "project",
            "--basemap",
            "Streets=https://tiles.example/{z}/{x}/{y}.png",
            "--basemap",
            "https://aerial.example/{z}/{x}/{y}.jpg?key=abc",
        ],
    )

    assert result.exit_code == 0, result.output
    # The bare template is named after its host - the honest word for a source with nothing else
    # stated about it - and its `key=abc` is part of one url rather than a name and a url.
    assert [(layer.name, layer.url) for layer in recorded_run.application.state.settings.basemaps] == [
        ("Streets", "https://tiles.example/{z}/{x}/{y}.png"),
        ("aerial.example", "https://aerial.example/{z}/{x}/{y}.jpg?key=abc"),
    ]


def test_basemap_none_offers_no_layer_and_refuses_to_be_combined_with_one(
    workdir: Path, recorded_run: _RecordedRun
) -> None:
    """`none` is the command line's way of writing `basemaps = []`, and it means it."""
    project = _scaffold(workdir)
    _compile(project)

    result = _runner.invoke(build_app(), ["fhir", "serve", "project", "--basemap", "none"])
    assert result.exit_code == 0, result.output
    assert recorded_run.application.state.settings.basemaps == []

    contradiction = _runner.invoke(
        build_app(),
        ["fhir", "serve", "project", "--basemap", "none", "--basemap", "https://tiles.example/{z}/{x}/{y}.png"],
    )
    assert contradiction.exit_code != 0
    assert "--basemap" in contradiction.output
    assert recorded_run.calls == 1


def test_the_resolved_profile_hands_the_screens_the_instance_they_link_to(
    workdir: Path, recorded_run: _RecordedRun
) -> None:
    """A guide is generated from one instance; naming its address is what makes an identity clickable."""
    project = _scaffold(workdir)
    _compile(project)

    result = _runner.invoke(build_app(), ["fhir", "serve", "project"])

    assert result.exit_code == 0, result.output
    assert recorded_run.application.state.settings.dhis2_base_url == "https://dhis2.example"
    # The name and the origin are for whoever runs the process; only the address reaches a browser.
    assert recorded_run.application.state.settings.profile is None


def test_serving_a_compiled_guide_where_no_profile_exists_links_to_no_instance(
    workdir: Path, recorded_run: _RecordedRun
) -> None:
    """A compiled guide on a machine that names no profile is a whole posture, not a broken one."""
    project = _scaffold(workdir)
    _compile(project)
    (workdir / ".config" / "dhis2" / "profiles.toml").unlink()

    result = _runner.invoke(build_app(), ["fhir", "serve", "project"])

    assert result.exit_code == 0, result.output
    assert recorded_run.application.state.settings.dhis2_base_url is None


def test_a_profile_that_is_named_and_does_not_exist_refuses_the_run(
    workdir: Path, monkeypatch: pytest.MonkeyPatch, recorded_run: _RecordedRun
) -> None:
    """Absence links nothing; a statement that is wrong is a statement, and it fails as one."""
    project = _scaffold(workdir)
    _compile(project)
    monkeypatch.setenv("DHIS2_PROFILE", "not-a-profile")

    result = _runner.invoke(build_app(), ["fhir", "serve", "project"])

    assert result.exit_code != 0
    assert recorded_run.calls == 0


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
    # And the instance the root flag named is the one the screens link identities into.
    assert recorded_run.application.state.settings.dhis2_base_url == "https://demo.example"


def test_serve_announces_the_address_before_the_server_starts(workdir: Path, recorded_run: _RecordedRun) -> None:
    """The banner is what a caller reads while uvicorn boots, so it precedes the run and names the address."""
    project = _scaffold(workdir)
    _compile(project)

    result = _runner.invoke(build_app(), ["fhir", "serve", "project", "--port", "9123"])

    assert result.exit_code == 0, result.output
    expected = f"starting {project.resolve()} on http://127.0.0.1:9123 as a FHIR endpoint (ctrl-c to stop)"
    assert expected in result.stderr
    assert recorded_run.calls == 1


def test_serve_ui_without_a_built_bundle_refuses_before_the_banner(
    workdir: Path, monkeypatch: pytest.MonkeyPatch, recorded_run: _RecordedRun
) -> None:
    """`--ui` on a checkout that never built the frontend is one line, not a page that loads blank."""
    from dhis2w_fhir_serve import ui as ui_module

    project = _scaffold(workdir)
    _compile(project)
    monkeypatch.setattr(ui_module, "STATIC_DIRECTORY", workdir / "never-built")

    result = _runner.invoke(build_app(), ["fhir", "serve", "project", "--ui"])

    assert result.exit_code == 1
    assert isinstance(result.exception, ui_module.UiBundleMissingError)
    assert "make build-frontend" in str(result.exception)
    assert recorded_run.calls == 0
    assert "starting" not in result.stderr


def test_serve_ui_says_the_surface_it_is_serving(workdir: Path, recorded_run: _RecordedRun) -> None:
    """With a bundle present the banner names the UI, so a caller knows to open the address."""
    from dhis2w_fhir_serve import ui as ui_module

    if not ui_module.ui_bundle_present():
        pytest.skip("no built frontend; run `make build-frontend`")

    project = _scaffold(workdir)
    _compile(project)

    result = _runner.invoke(build_app(), ["fhir", "serve", "project", "--ui", "--port", "9124"])

    assert result.exit_code == 0, result.output
    assert "http://127.0.0.1:9124 as a FHIR endpoint + capture UI" in result.stderr
    assert recorded_run.application.state.settings.ui is True


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


def _occupied_port() -> tuple[socket.socket, int]:
    """Hold an ephemeral loopback port the way a running DHIS2 does, and say which one."""
    blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    blocker.bind(("127.0.0.1", 0))
    blocker.listen(1)
    return blocker, blocker.getsockname()[1]


def _occupied_ipv6_only_port() -> tuple[socket.socket, int]:
    """Hold an ephemeral port on the IPv6 loopback alone, the way a v6-only container publishes one."""
    blocker = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    blocker.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
    blocker.bind(("::1", 0))
    blocker.listen(1)
    return blocker, blocker.getsockname()[1]


def _occupied_wildcard_port() -> tuple[socket.socket, int]:
    """Hold an ephemeral port on all interfaces, the way a published Docker container holds one."""
    blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    blocker.bind(("0.0.0.0", 0))  # noqa: S104 - a test blocker standing in for a published container
    blocker.listen(1)
    return blocker, blocker.getsockname()[1]


def _free_port() -> int:
    """An ephemeral loopback port that was free a moment ago."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.bind(("127.0.0.1", 0))
    port: int = probe.getsockname()[1]
    probe.close()
    return port


def _port_in_use_line(port: int, host: str = "127.0.0.1") -> str:
    """The one-line refusal the preflight and the uvicorn catch both render."""
    return (
        f"port {port} on {host} is already in use "
        "(usually the local DHIS2 instance; set [serve] port in fhir.toml or pass --port)"
    )


def test_serve_refuses_a_taken_port_before_the_banner(workdir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A port something else holds fails as one line before any output that looks like a start."""
    project = _scaffold(workdir)
    _compile(project)
    recorder = _RecordedRun()
    monkeypatch.setattr(uvicorn, "run", recorder)
    blocker, port = _occupied_port()
    try:
        result = _runner.invoke(build_app(), ["fhir", "serve", "project", "--port", str(port)])
    finally:
        blocker.close()

    assert result.exit_code == 1
    assert isinstance(result.exception, fhir_cli.PortInUseError)
    assert _port_in_use_line(port) in str(result.exception)
    assert recorder.calls == 0
    assert "starting" not in result.stderr
    assert "Traceback" not in result.output


def test_serve_refuses_a_port_held_on_the_other_ip_stack(workdir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A port held on the IPv6 loopback alone refuses an IPv4 host: a browser reaches either one."""
    project = _scaffold(workdir)
    _compile(project)
    recorder = _RecordedRun()
    monkeypatch.setattr(uvicorn, "run", recorder)
    try:
        blocker, port = _occupied_ipv6_only_port()
    except OSError as error:  # pragma: no cover - a machine with no IPv6 stack has no v6 listener
        pytest.skip(f"this machine cannot bind the IPv6 loopback: {error}")
    try:
        result = _runner.invoke(build_app(), ["fhir", "serve", "project", "--port", str(port)])
    finally:
        blocker.close()

    assert result.exit_code == 1
    assert isinstance(result.exception, fhir_cli.PortInUseError)
    assert _port_in_use_line(port) in str(result.exception)
    assert recorder.calls == 0


def test_serve_refuses_a_port_a_wildcard_listener_holds(workdir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The local DHIS2 stack's own shape: published to all interfaces, so loopback is not free for us.

    SO_REUSEADDR would let this server bind the loopback underneath that listener and take the
    localhost traffic meant for the instance, which is the failure this refusal exists to prevent.
    """
    project = _scaffold(workdir)
    _compile(project)
    recorder = _RecordedRun()
    monkeypatch.setattr(uvicorn, "run", recorder)
    blocker, port = _occupied_wildcard_port()
    try:
        result = _runner.invoke(build_app(), ["fhir", "serve", "project", "--port", str(port)])
    finally:
        blocker.close()

    assert result.exit_code == 1
    assert isinstance(result.exception, fhir_cli.PortInUseError)
    assert _port_in_use_line(port) in str(result.exception)
    assert recorder.calls == 0


def test_the_taken_port_renders_as_one_line_through_the_funnel(
    workdir: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """End to end through `run_app`: exit code 1, the `error:` one-liner on stderr, no traceback."""
    from dhis2w_core.cli_errors import run_app

    project = _scaffold(workdir)
    _compile(project)
    recorder = _RecordedRun()
    monkeypatch.setattr(uvicorn, "run", recorder)
    blocker, port = _occupied_port()
    monkeypatch.setattr(sys, "argv", ["d2w", "fhir", "serve", "project", "--port", str(port)])
    try:
        with pytest.raises(SystemExit) as exit_info:
            run_app(build_app())
    finally:
        blocker.close()

    assert exit_info.value.code == 1
    captured = capsys.readouterr()
    assert f"error: {_port_in_use_line(port)}" in captured.err
    assert "Traceback" not in captured.err + captured.out
    assert recorder.calls == 0


def test_the_preflight_releases_the_port(workdir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A successful probe leaves the port free, so uvicorn's own bind is next in line for it."""
    project = _scaffold(workdir)
    _compile(project)
    recorder = _RecordedRun()
    monkeypatch.setattr(uvicorn, "run", recorder)
    port = _free_port()

    result = _runner.invoke(build_app(), ["fhir", "serve", "project", "--port", str(port)])

    assert result.exit_code == 0, result.output
    assert recorder.calls == 1
    rebind = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        rebind.bind(("127.0.0.1", port))
    finally:
        rebind.close()


def test_a_bind_race_lost_at_uvicorn_renders_the_same_line(workdir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """An EADDRINUSE raised out of the uvicorn run itself renders the one-liner, never a traceback."""
    project = _scaffold(workdir)
    _compile(project)
    port = _free_port()

    def _refuse_bind(application: Any, **keyword_arguments: Any) -> None:
        raise OSError(errno.EADDRINUSE, "address already in use")

    monkeypatch.setattr(uvicorn, "run", _refuse_bind)

    result = _runner.invoke(build_app(), ["fhir", "serve", "project", "--port", str(port)])

    assert result.exit_code == 1
    assert isinstance(result.exception, fhir_cli.PortInUseError)
    assert _port_in_use_line(port) in str(result.exception)
    assert "Traceback" not in result.output


def test_a_system_exit_from_uvicorn_with_the_port_taken_renders_the_same_line(
    workdir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """uvicorn refuses a taken port with `sys.exit(1)`; a re-probe maps that back to the one-liner."""
    project = _scaffold(workdir)
    _compile(project)
    port = _free_port()
    blockers: list[socket.socket] = []

    def _lose_the_race(application: Any, **keyword_arguments: Any) -> None:
        blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        blocker.bind(("127.0.0.1", port))
        blocker.listen(1)
        blockers.append(blocker)
        raise SystemExit(1)

    monkeypatch.setattr(uvicorn, "run", _lose_the_race)
    try:
        result = _runner.invoke(build_app(), ["fhir", "serve", "project", "--port", str(port)])
    finally:
        for blocker in blockers:
            blocker.close()

    assert result.exit_code == 1
    assert isinstance(result.exception, fhir_cli.PortInUseError)
    assert _port_in_use_line(port) in str(result.exception)
    assert "Traceback" not in result.output


def test_a_system_exit_from_uvicorn_with_the_port_free_passes_through(
    workdir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Exit 1 is also how uvicorn reports failures that are not about the port; those keep their exit."""
    project = _scaffold(workdir)
    _compile(project)
    port = _free_port()

    def _fail_elsewhere(application: Any, **keyword_arguments: Any) -> None:
        raise SystemExit(3)

    monkeypatch.setattr(uvicorn, "run", _fail_elsewhere)

    result = _runner.invoke(build_app(), ["fhir", "serve", "project", "--port", str(port)])

    assert result.exit_code == 3
    assert not isinstance(result.exception, fhir_cli.PortInUseError)
