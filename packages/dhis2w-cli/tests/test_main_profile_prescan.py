"""Tests for the argv pre-scan that applies --profile before plugin discovery."""

from __future__ import annotations

import pytest
from dhis2w_cli.main import _extract_profile_from_argv


def test_returns_none_for_empty_argv() -> None:
    """Returns none for empty argv."""
    assert _extract_profile_from_argv([]) is None


def test_returns_none_when_no_profile_flag() -> None:
    """Returns none when no profile flag."""
    assert _extract_profile_from_argv(["system", "info"]) is None


def test_long_form_space_separated() -> None:
    """Long form space separated."""
    assert _extract_profile_from_argv(["--profile", "v43p", "system", "info"]) == "v43p"


def test_long_form_equals_separated() -> None:
    """Long form equals separated."""
    assert _extract_profile_from_argv(["--profile=v43p", "system", "info"]) == "v43p"


def test_short_form() -> None:
    """Short form."""
    assert _extract_profile_from_argv(["-p", "v43p", "system", "info"]) == "v43p"


def test_short_form_attached_value() -> None:
    """An attached short-option value (`-pNAME`) is the profile, as Click reads it."""
    assert _extract_profile_from_argv(["-pv43p", "system", "info"]) == "v43p"


def test_last_profile_flag_wins() -> None:
    """Repeating the flag takes the last value, which is the one Click applies."""
    assert _extract_profile_from_argv(["-p", "first", "--profile", "second", "system", "info"]) == "second"


def test_flag_after_the_command_path_is_not_a_root_flag() -> None:
    """Root options end at the command path, so a later `-p` belongs to the subcommand."""
    assert _extract_profile_from_argv(["system", "info", "--profile", "v43p"]) is None
    assert _extract_profile_from_argv(["-p", "root", "analytics", "query", "-p", "sub"]) == "root"


def test_double_dash_stops_scanning() -> None:
    """Double dash stops scanning."""
    assert _extract_profile_from_argv(["--", "--profile", "v43p"]) is None


def test_long_form_without_value_returns_none() -> None:
    """Long form without value returns none."""
    assert _extract_profile_from_argv(["--profile"]) is None


def test_short_form_without_value_returns_none() -> None:
    """Short form without value returns none."""
    assert _extract_profile_from_argv(["-p"]) is None


def _click_root_profile(argv: list[str]) -> str | None:
    """Return the profile the Typer root callback receives for `argv`, parsing only."""
    import typer.main
    from dhis2w_cli.main import build_app

    root = typer.main.get_command(build_app())
    context = root.make_context("d2w", list(argv), resilient_parsing=True)
    profile = context.params.get("profile")
    return profile if profile is None else str(profile)


@pytest.mark.parametrize(
    "argv",
    [
        ["system", "info"],
        ["--profile", "alpha", "system", "info"],
        ["--profile=alpha", "system", "info"],
        ["-p", "alpha", "system", "info"],
        ["-palpha", "system", "info"],
        ["-p=alpha", "system", "info"],
        ["-p", "alpha", "-p", "beta", "system", "info"],
        ["--profile", "alpha", "--profile=beta", "system", "info"],
        ["-palpha", "--profile", "beta", "system", "info"],
        ["--json", "-p", "alpha", "system", "info"],
        ["-p", "alpha", "analytics", "query", "-p", "beta"],
        ["--", "--profile", "alpha"],
    ],
)
def test_prescan_agrees_with_the_root_callback(argv: list[str]) -> None:
    """The pre-scan names the same profile Click hands the root callback, in every form.

    The pre-scan picks the plugin tree (`v41`/`v42`/`v43`) and Click picks the profile the
    commands run against, so any disagreement mounts one instance's tree and talks to another.
    """
    assert _extract_profile_from_argv(argv) == _click_root_profile(argv)
