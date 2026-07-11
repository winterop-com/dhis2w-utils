"""Drift guard for the v43-only `d2w metadata programs` CLI surface.

The v43 metadata cli.py starts as a mechanical copy of v42 and then grows v43-only
commands (the Program label / change-log / enrollment-CC setters). A careless
v42-copy refresh of the file silently drops them: the service and MCP layers keep
the functionality, so nothing else fails. These tests pin the contract directly on
the registered Typer commands — the v43 `programs` sub-app must expose the v43-only
setters and be a superset of v42's `programs` sub-app.
"""

from __future__ import annotations

import pytest
from dhis2w_cli.main import build_app
from typer import Typer

V43_ONLY_PROGRAM_COMMANDS = {"set-labels", "set-change-log", "set-enrollment-category-combo"}


def _build_versioned_app(core_version: str, monkeypatch: pytest.MonkeyPatch) -> Typer:
    """Build the CLI app pinned to `core_version` (so it discovers that tree's plugins)."""
    monkeypatch.setenv("DHIS2_VERSION", core_version)
    return build_app()


def _sub_app(app: Typer, name: str) -> Typer:
    """Return the mounted sub-app registered under `name`."""
    for group in app.registered_groups:
        if group.name == name and group.typer_instance is not None:
            return group.typer_instance
    raise AssertionError(f"no sub-app named {name!r} on {app.info.name or 'root'}")


def _program_command_names(app: Typer) -> set[str]:
    """Collect the command names registered on the `metadata programs` sub-app."""
    programs_app = _sub_app(_sub_app(app, "metadata"), "programs")
    names = {command.name for command in programs_app.registered_commands if command.name}
    assert names, "metadata programs sub-app registered no commands"
    return names


def test_v43_programs_cli_exposes_v43_only_setters(core_profile: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """The v43 tree registers the v43-only Program set-* commands."""
    names = _program_command_names(_build_versioned_app("v43", monkeypatch))
    missing = V43_ONLY_PROGRAM_COMMANDS - names
    assert not missing, f"v43-only program commands missing from the v43 metadata CLI: {sorted(missing)}"


def test_v42_programs_cli_does_not_grow_the_v43_only_setters(
    core_profile: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The v43-only Program set-* commands stay off the v42 tree — deliberate v43-only surface."""
    names = _program_command_names(_build_versioned_app("v42", monkeypatch))
    leaked = V43_ONLY_PROGRAM_COMMANDS & names
    assert not leaked, f"v43-only program commands leaked into the v42 metadata CLI: {sorted(leaked)}"


def test_v43_programs_cli_is_a_superset_of_v42(core_profile: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """Every v42 `metadata programs` command also exists on v43 — a v42-copy clobber fails here."""
    v42_names = _program_command_names(_build_versioned_app("v42", monkeypatch))
    v43_names = _program_command_names(_build_versioned_app("v43", monkeypatch))
    missing = v42_names - v43_names
    assert not missing, f"v42 program commands missing from the v43 metadata CLI: {sorted(missing)}"
