"""Typer root for the `d2w` CLI — discovers plugins and mounts them."""

from __future__ import annotations

import logging
import os
import sys
from importlib.metadata import PackageNotFoundError, version
from typing import Annotated

import typer
from dhis2w_core.cli_errors import run_app
from dhis2w_core.cli_output import JSON_OUTPUT
from dhis2w_core.plugin import DEFAULT_VERSION_KEY, discover_plugins, resolve_startup_version
from dhis2w_core.rich_console import STDERR_CONSOLE
from rich.logging import RichHandler


def _extract_profile_from_argv(argv: list[str]) -> str | None:
    """Pre-scan argv for the profile Click will apply: the last root `--profile` / `-p` value.

    Plugin discovery needs to happen *after* `--profile` is applied — the
    `version` field on the resolved profile picks which `v{41,42,43}`
    plugin tree gets mounted. The Typer root callback sets the env var,
    but plugins are mounted before any argv is parsed. This pre-scan
    runs before `build_app()` so the env is in place when
    `resolve_startup_version()` fires.

    It reads argv exactly as Click does, so the mounted tree and the
    executed profile always name the same instance: every form of the
    option (`--profile NAME`, `--profile=NAME`, `-p NAME`, `-pNAME`),
    the last occurrence winning, over the leading option region only.
    Click stops reading root options at the first positional token, so
    the scan stops at the command path (a `-p` after it belongs to that
    subcommand) and at `--`.

    Returns `None` when the root region carries no profile flag.
    """
    profile: str | None = None
    index = 0
    while index < len(argv):
        argument = argv[index]
        if argument == "--" or not argument.startswith("-"):
            break
        index += 1
        if argument.startswith("--"):
            if argument == "--profile":
                if index >= len(argv):
                    break
                profile = argv[index]
                index += 1
            elif argument.startswith("--profile="):
                profile = argument.removeprefix("--profile=")
            continue
        # A single-dash token is read character by character, and `-p` is the only root short
        # option that takes a value: the rest of the token when attached (`-pNAME`, and `-p=NAME`
        # keeps the `=` exactly as Click does), otherwise the next argument (`-p NAME`).
        position = argument.find("p", 1)
        if position == -1:
            continue
        attached = argument[position + 1 :]
        if attached:
            profile = attached
        elif index < len(argv):
            profile = argv[index]
            index += 1
        else:
            break
    return profile


def _version_banner() -> str:
    """Multi-line banner shown for `d2w --version` — package version + active plugin tree.

    Surfaces which plugin tree (`v41` / `v42` / `v43`) the CLI booted with
    and where that came from in the resolution chain (`profile.version` →
    `DHIS2_VERSION` env → default). Helps debug "which DHIS2 major is
    this CLI talking to" without reading the profile by hand.
    """
    try:
        pkg_version = version("dhis2w-cli")
    except PackageNotFoundError:
        pkg_version = "unknown"
    active = resolve_startup_version()
    env_version = os.environ.get("DHIS2_VERSION", "").strip()
    if env_version in {"v41", "v42", "v43"} and env_version == active:
        source = f"DHIS2_VERSION={env_version!r} env"
    elif active == DEFAULT_VERSION_KEY:
        source = "default (no profile.version, no DHIS2_VERSION env)"
    else:
        source = "profile.version"
    return f"d2w {pkg_version}  (plugin tree: {active} — {source})"


def _version_callback(value: bool) -> None:
    """Eager `--version` callback — print the banner and exit."""
    if value:
        typer.echo(_version_banner())
        raise typer.Exit(0)


_DEBUG_HANDLER_NAME = "dhis2w-cli-debug"


def _enable_debug_logging() -> None:
    """Turn on dhis2w-client HTTP traces + dhis2w-core debug logs on stderr.

    Uses `rich.logging.RichHandler` tied to the shared `STDERR_CONSOLE` so log
    lines render above any active Rich `Progress` / `Status` display instead
    of tearing through it.

    Idempotent — repeated invocations within the same Python process (e.g.
    `CliRunner.invoke()` called multiple times in a single test session, or
    `make docs-cli`'s typer-docs sweep) won't accumulate duplicate handlers.
    The handler is tagged with a stable name and a second call finds the
    existing one and returns.
    """
    root = logging.getLogger()
    if any(getattr(h, "name", None) == _DEBUG_HANDLER_NAME for h in root.handlers):
        return
    handler = RichHandler(
        console=STDERR_CONSOLE,
        show_path=False,
        show_time=True,
        markup=False,
        rich_tracebacks=False,
        log_time_format="%H:%M:%S",
    )
    handler.name = _DEBUG_HANDLER_NAME
    handler.setLevel(logging.DEBUG)
    root.addHandler(handler)
    for name in ("dhis2w_client", "dhis2w_core"):
        logging.getLogger(name).setLevel(logging.DEBUG)


def build_app() -> typer.Typer:
    """Build a fresh Typer app with every discovered plugin mounted.

    Every call returns a new app, which keeps unit tests hermetic and lets
    callers introspect the mounted surface without side effects.

    `pretty_exceptions_enable=False` so our `run_app` wrapper (invoked from
    `main()` below) sees uncaught exceptions and can render them cleanly.
    """
    app = typer.Typer(
        help="d2w — command-line interface for DHIS2 (discovers plugins from dhis2w-core).",
        no_args_is_help=True,
        add_completion=False,
        pretty_exceptions_enable=False,
    )

    @app.callback()
    def _root(
        profile: Annotated[
            str | None,
            typer.Option(
                "--profile",
                "-p",
                help="DHIS2 profile name (overrides DHIS2_PROFILE env + TOML default).",
            ),
        ] = None,
        debug: Annotated[
            bool,
            typer.Option(
                "--debug",
                "-d",
                help="Verbose output on stderr — HTTP method/URL/status/elapsed for every request.",
            ),
        ] = False,
        json_: Annotated[
            bool,
            typer.Option(
                "--json",
                "-j",
                help="Emit raw JSON to stdout instead of Rich tables (uniform across all commands).",
            ),
        ] = False,
        _version: Annotated[
            bool,
            typer.Option(
                "--version",
                "-V",
                help="Print the CLI version + active plugin tree and exit.",
                callback=_version_callback,
                is_eager=True,
            ),
        ] = False,
    ) -> None:
        """Set the active DHIS2 profile + optional debug logging + output mode for this invocation."""
        if profile:
            os.environ["DHIS2_PROFILE"] = profile
        if debug:
            _enable_debug_logging()
        # Always set, not just when True — `CliRunner` reuses the same
        # process across `invoke` calls, so a stale `True` from a previous
        # invocation must not leak into the next one.
        JSON_OUTPUT.set(json_)

    for plugin in discover_plugins(resolve_startup_version()):
        plugin.register_cli(app)
    return app


def main() -> None:
    """Console-script entrypoint — wraps the Typer app with clean error rendering.

    Resolves `--profile` from argv *before* mounting plugins so the
    correct `v{41,42,43}` plugin tree gets discovered. Without this
    pre-pass, `d2w --profile v43p ...` would freeze the plugin tree
    at whatever the default profile pinned (typically v42), hiding
    v43-only commands and making `--version`'s banner disagree with
    the actual mounted command tree.
    """
    profile = _extract_profile_from_argv(sys.argv[1:])
    if profile:
        os.environ["DHIS2_PROFILE"] = profile
    fresh_app = build_app()
    run_app(fresh_app)


# Module-level Typer app instance for `typer dhis2w_cli.main utils docs ...`
# introspection used by `make docs-cli` to regenerate `docs/cli-reference.md`.
# Not consumed by the console-script entry point — `main()` above builds its
# own fresh app *after* applying `--profile` from argv, which is what the user
# expects at runtime. This module-level instance is only walked at docs-build
# time, where no user CLI args are in play and the canonical (default-profile)
# command tree is the correct thing to dump.
app = build_app()


if __name__ == "__main__":
    main()
