"""Unit tests for the dhis2 CLI root and plugin-mounted sub-apps."""

from __future__ import annotations

import pytest
import typer.main
from dhis2w_cli.main import build_app
from typer.testing import CliRunner


@pytest.mark.slow
def test_every_command_renders_help() -> None:
    """Every leaf command's `--help` renders (exit 0) — no broken/unregistered command in the tree.

    The deterministic "all commands work" structural guard across the full CLI surface (~363 leaves).
    A capable agent's command-discoverability column in the model matrix should match this 100%.
    """
    app = build_app()
    root = typer.main.get_command(app)
    runner = CliRunner()
    leaves: list[tuple[str, ...]] = []

    def walk(node: object, path: tuple[str, ...]) -> None:
        commands = getattr(node, "commands", None)
        if commands:
            for name, child in commands.items():
                walk(child, (*path, name))
        else:
            leaves.append(path)

    walk(root, ())
    assert len(leaves) > 300, f"expected the full CLI surface, found only {len(leaves)} leaves"
    broken = [" ".join(path) for path in leaves if runner.invoke(app, [*path, "--help"]).exit_code != 0]
    assert not broken, f"commands with broken --help: {broken}"


def test_help_lists_discovered_plugins() -> None:
    """Help lists discovered plugins."""
    runner = CliRunner()
    result = runner.invoke(build_app(), ["--help"])
    assert result.exit_code == 0
    for name in ("analytics", "data", "dev", "metadata", "profile", "route", "system"):
        assert name in result.stdout


def test_system_subcommand_help_lists_commands() -> None:
    """System subcommand help lists commands."""
    runner = CliRunner()
    result = runner.invoke(build_app(), ["system", "--help"])
    assert result.exit_code == 0
    assert "whoami" in result.stdout
    assert "info" in result.stdout


def test_data_subcommand_tree() -> None:
    """Data subcommand tree."""
    runner = CliRunner()
    data_help = runner.invoke(build_app(), ["data", "--help"])
    assert data_help.exit_code == 0
    assert "aggregate" in data_help.stdout
    assert "tracker" in data_help.stdout
    tracker_help = runner.invoke(build_app(), ["data", "tracker", "--help"])
    assert tracker_help.exit_code == 0
    for sub in ("entity", "enrollment", "event", "relationship", "push"):
        assert sub in tracker_help.stdout


def test_dev_includes_codegen_and_uid() -> None:
    """Dev includes codegen and uid."""
    runner = CliRunner()
    result = runner.invoke(build_app(), ["dev", "--help"])
    assert result.exit_code == 0
    for name in ("codegen", "uid", "oauth2"):
        assert name in result.stdout
