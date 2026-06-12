"""Unit tests for the `dev` plugin — uid generation + sub-command registration.

The `pat`, `oauth2`, and `sample` sub-commands are network-driven and
covered separately by integration tests against a live stack. This file
locks in the plugin descriptor + offline UID command.
"""

from __future__ import annotations

import re

from dhis2w_cli.main import build_app
from dhis2w_core.v42.plugins.dev import plugin
from typer.testing import CliRunner

_runner = CliRunner()


def test_plugin_descriptor() -> None:
    """The dev plugin exposes name + description + a non-trivial CLI mount."""
    assert plugin.name == "dev"
    assert "developer" in plugin.description.lower() or "operator" in plugin.description.lower()


def test_dev_help_lists_subcommands() -> None:
    """`d2w dev --help` lists every dev sub-command (uid / sample)."""
    result = _runner.invoke(build_app(), ["dev", "--help"])
    assert result.exit_code == 0
    for sub in ("uid", "sample"):
        assert sub in result.output, f"`d2w dev` should mount the {sub!r} sub-command"


def test_dev_uid_default_count_emits_one_uid() -> None:
    """`d2w dev uid` with no args emits exactly one 11-char DHIS2 UID."""
    result = _runner.invoke(build_app(), ["dev", "uid"])
    assert result.exit_code == 0
    lines = [line for line in result.output.strip().splitlines() if line.strip()]
    assert len(lines) == 1
    assert re.fullmatch(r"[A-Za-z][A-Za-z0-9]{10}", lines[0])


def test_dev_uid_count_emits_n_uids() -> None:
    """`d2w dev uid --count 5` emits five distinct UIDs, one per line."""
    result = _runner.invoke(build_app(), ["dev", "uid", "--count", "5"])
    assert result.exit_code == 0
    lines = [line for line in result.output.strip().splitlines() if line.strip()]
    assert len(lines) == 5
    assert len(set(lines)) == 5  # CSPRNG -> all distinct
    for uid in lines:
        assert re.fullmatch(r"[A-Za-z][A-Za-z0-9]{10}", uid)


def test_dev_uid_rejects_count_below_min() -> None:
    """`--count 0` is rejected by Typer's `min=1` constraint."""
    result = _runner.invoke(build_app(), ["dev", "uid", "--count", "0"])
    assert result.exit_code != 0
    assert "min" in result.output.lower() or "0" in result.output
