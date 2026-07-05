"""Clean-error rendering for CLI commands.

Expected user-facing errors get printed as a one-line message (in red, on
stderr) plus a short hint block, then exit 1. Programming bugs (AssertionError,
KeyError, etc.) still propagate and show a full traceback so they can be
triaged.
"""

from __future__ import annotations

import sys
from typing import NoReturn, cast

import typer
from dhis2w_client.errors import AuthenticationError, Dhis2ApiError, Dhis2ClientError, OAuth2FlowError
from dhis2w_client.v41.envelopes import WebMessageResponse

from dhis2w_core.profile import (
    NO_PROFILE_HINT_LINES,
    InvalidProfileNameError,
    NoProfileError,
    ProfileAlreadyExistsError,
    UnknownProfileError,
)

#: Shared with the MCP server's error middleware — hard requirement 1 keeps both surfaces identical.
_NO_PROFILE_HINT = list(NO_PROFILE_HINT_LINES)

_UNKNOWN_PROFILE_HINT = [
    "run `d2w profile list` to see available profiles",
    "or `d2w profile add <name> ...` to create one",
]

_INVALID_NAME_HINT = [
    "profile names must start with a letter and contain only letters,",
    "digits, and underscores (e.g. 'local', 'prod_eu', 'laohis42').",
]

_AUTH_HINT = [
    "run `d2w profile verify <name>` to confirm auth",
    "or `d2w profile show <name>` to inspect the stored credentials",
]

_ALREADY_EXISTS_HINT = [
    "run `d2w profile list` to see existing profiles",
    "or `d2w profile remove <name>` first to free the name",
]

_OAUTH2_HINT = [
    "run `d2w profile login <name>` to re-authorise the OAuth2 flow",
    "or `d2w profile verify <name>` to confirm the current state",
]


def run_app(app: typer.Typer) -> NoReturn:
    """Invoke a Typer app with clean error rendering for known exceptions."""
    try:
        app()
    except NoProfileError as exc:
        _render("error", str(exc), _NO_PROFILE_HINT)
    except UnknownProfileError as exc:
        _render("error", str(exc), _UNKNOWN_PROFILE_HINT)
    except InvalidProfileNameError as exc:
        _render("error", str(exc), _INVALID_NAME_HINT)
    except ProfileAlreadyExistsError as exc:
        _render("error", str(exc), _ALREADY_EXISTS_HINT)
    except AuthenticationError as exc:
        _render("auth error", str(exc), _AUTH_HINT)
    except OAuth2FlowError as exc:
        _render("oauth2 error", str(exc), _OAUTH2_HINT)
    except Dhis2ApiError as exc:
        _render_api_error(exc)
    except Dhis2ClientError as exc:
        _render("DHIS2 error", str(exc))
    except LookupError as exc:
        _render("error", str(exc))
    sys.exit(0)


def _render_api_error(exc: Dhis2ApiError) -> NoReturn:
    """Render a Dhis2ApiError — extract the WebMessage envelope when DHIS2 ships one."""
    # The shared Dhis2ApiError yields the v42-baseline WebMessageResponse; it's structurally
    # identical to this tree's, so type it as such for the version-typed render helpers below.
    envelope = cast("WebMessageResponse | None", exc.web_message)
    detail = exc.message or ""
    body_msg = envelope.message if envelope and envelope.message else _extract_body_message(exc.body)
    if body_msg:
        detail = f"{detail}: {body_msg}" if detail else body_msg
    extras = _webmessage_detail_lines(envelope) if envelope else []
    # Render the Rich conflict table BEFORE calling `_render` — the latter is
    # a `NoReturn` sys.exit wrapper, so nothing after it executes.
    if envelope:
        rows = envelope.conflict_rows()
        if rows:
            from dhis2w_core.v41.cli_output import render_conflicts

            render_conflicts(rows)
    _render(f"DHIS2 API error ({exc.status_code})", detail or "(no further detail)", extras=extras)


def _webmessage_detail_lines(envelope: WebMessageResponse) -> list[str]:
    """Format the import-count + rejected-indexes summary lines for end-user output.

    Conflicts themselves render separately as a Rich table via
    `render_conflicts(envelope.conflict_rows())` — this function handles
    only the one-line summary bits DHIS2 tucks under `response.*`.
    """
    lines: list[str] = []
    counts = envelope.import_count()
    if counts is not None and any((counts.imported, counts.updated, counts.ignored, counts.deleted)):
        lines.append(
            f"import_count: imported={counts.imported} updated={counts.updated} "
            f"ignored={counts.ignored} deleted={counts.deleted}"
        )
    rejected = envelope.rejected_indexes()
    if rejected:
        lines.append(f"rejected_indexes: {rejected}")
    return lines


def _render(label: str, message: str, hint: list[str] | None = None, extras: list[str] | None = None) -> NoReturn:
    """Print `label: message` + optional extras + optional hint block to stderr and exit 1."""
    typer.secho(f"{label}: {message}", err=True, fg=typer.colors.RED)
    if extras:
        for line in extras:
            typer.echo(line, err=True)
    if hint:
        typer.echo("", err=True)
        typer.echo("hint:", err=True)
        for line in hint:
            typer.echo(f"  {line}", err=True)
    sys.exit(1)


def _extract_body_message(body: object) -> str | None:
    """Pull a useful error message out of the DHIS2 JSON body, if present."""
    if isinstance(body, dict):
        message = body.get("message")
        if isinstance(message, str) and message:
            return message
    return None
