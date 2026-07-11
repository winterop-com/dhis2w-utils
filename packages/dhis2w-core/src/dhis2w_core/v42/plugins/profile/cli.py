"""Typer sub-app for the `profile` plugin (mounted under `d2w profile`)."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any

import typer

# DEFAULT_REDIRECT_URI stays at module scope: it is a Typer option default on the add /
# bootstrap / oidc-config commands, evaluated at command-registration time (import). Its
# source module (auth.oauth2) is light — it does not pull the generated OAS tree.
from dhis2w_client.v42.auth.oauth2 import DEFAULT_REDIRECT_URI
from rich.console import Console
from rich.table import Table

from dhis2w_core.oauth2_preflight import check_oauth2_server
from dhis2w_core.profile import Profile, UnknownProfileError, resolve
from dhis2w_core.v42.cli_output import is_json_output

# oauth2_module / pat_module stay at module scope: they are mounted via app.add_typer(...)
# at import time, so they cannot be deferred here. They keep their own heavy imports
# (admin_auth / registration → generated OAS) deferred into command bodies, so importing
# them here stays light.
from dhis2w_core.v42.plugins.profile import oauth2 as oauth2_module
from dhis2w_core.v42.plugins.profile import pat as pat_module

if TYPE_CHECKING:
    from dhis2w_client.v42 import Dhis2

    from dhis2w_core.v42.plugins.profile import service

_VERSION_HELP = (
    "Expected DHIS2 major for this profile (v41 | v42 | v43). Used by CLI/MCP "
    "to pick which version's plugin tree to load; the wire client always "
    "auto-detects on connect."
)


def _validate_version(value: str | None) -> Dhis2 | None:
    """Normalize a `--version` flag value into a `Dhis2` enum member or None."""
    from dhis2w_client.v42 import Dhis2

    if value is None:
        return None
    candidate = value.strip().lower()
    match candidate:
        case "v41" | "v42" | "v43":
            return Dhis2(candidate)
        case _:
            raise typer.BadParameter(f"unsupported --version {value!r}; use one of v41, v42, v43")


app = typer.Typer(
    help="Manage DHIS2 profiles (project .dhis2/profiles.toml and user-wide ~/.config/dhis2/profiles.toml).",
    no_args_is_help=True,
)
_console = Console()


@app.command("list")
@app.command("ls", hidden=True)
def list_command(
    all_: Annotated[
        bool,
        typer.Option("--all", "-a", help="Include shadowed profiles (global entries hidden by project ones)."),
    ] = False,
) -> None:
    """List every known profile with its source and default status."""
    from dhis2w_core.v42.plugins.profile import service

    summaries = service.list_profiles(include_shadowed=all_)
    if is_json_output():
        typer.echo(json.dumps([s.model_dump() for s in summaries], indent=2))
        return
    if not summaries:
        typer.echo("no profiles found — run `d2w profile add <name>` to create one.")
        return
    table = Table(title=f"DHIS2 profiles ({len(summaries)})")
    table.add_column("name")
    table.add_column("auth")
    table.add_column("base_url", overflow="fold")
    table.add_column("source")
    for summary in summaries:
        name = _format_profile_name(summary.name, summary.is_default, summary.shadowed)
        table.add_row(
            name,
            _colorize_auth(summary.auth),
            summary.base_url,
            _friendly_source(summary.source),
        )
    _console.print(table)


def _format_profile_name(name: str, is_default: bool, shadowed: bool) -> str:
    """Name column: bold-green + trailing `*` on default, append `(shadowed)` dim when shadowed."""
    base = f"[bold green]{name}[/bold green] [bold green]*[/bold green]" if is_default else name
    if shadowed:
        base += " [dim](shadowed)[/dim]"
    return base


def _colorize_auth(auth: str) -> str:
    """Color auth kind so basic / pat / oauth2 / oidc / session stand apart in the table."""
    upper = auth.lower()
    if upper == "basic":
        return f"[yellow]{auth}[/yellow]"
    if upper == "pat":
        return f"[cyan]{auth}[/cyan]"
    if upper in ("oauth2", "oidc"):
        return f"[magenta]{auth}[/magenta]"
    if upper == "session":
        return f"[blue]{auth}[/blue]"
    return auth


def _friendly_source(source: str) -> str:
    """Trim the internal `-toml` suffix for display (`global-toml` -> `global`, `project-toml` -> `local`).

    Keeps the internal `ProfileSource` literal type untouched — `--json`
    output still carries the canonical values.
    """
    if source == "global-toml":
        return "global"
    if source == "project-toml":
        return "local"
    return source


@app.command("verify")
def verify_command(
    name: Annotated[
        str | None,
        typer.Argument(help="Profile name to verify; omit to verify all."),
    ] = None,
) -> None:
    """Verify one profile or all profiles by hitting /api/system/info + /api/me."""
    from dhis2w_core.v42.plugins.profile import service

    if name:
        result = asyncio.run(service.verify_profile(name))
        if is_json_output():
            typer.echo(json.dumps(result.model_dump(), indent=2))
        else:
            _print_verify_row(result)
        raise typer.Exit(0 if result.ok else 1)

    results = asyncio.run(service.verify_all_profiles())
    if is_json_output():
        typer.echo(json.dumps([r.model_dump() for r in results], indent=2))
        raise typer.Exit(0 if all(r.ok for r in results) else 1)
    table = Table(title=f"DHIS2 profile verification ({len(results)})")
    table.add_column("name")
    table.add_column("ok")
    table.add_column("version")
    table.add_column("user")
    table.add_column("latency", justify="right")
    table.add_column("error", overflow="fold")
    for r in results:
        table.add_row(
            r.name,
            "[green]ok[/green]" if r.ok else "[red]fail[/red]",
            r.version or "-",
            r.username or "-",
            f"{r.latency_ms} ms" if r.latency_ms is not None else "-",
            f"[red]{r.error}[/red]" if r.error else "",
        )
    _console.print(table)
    raise typer.Exit(0 if all(r.ok for r in results) else 1)


def _print_verify_row(result: service.VerifyResult) -> None:
    status = "OK" if result.ok else "FAIL"
    line = f"{status} {result.name}  {result.base_url}  auth={result.auth}"
    if result.ok:
        line += f"  version={result.version}  user={result.username}  {result.latency_ms} ms"
    else:
        line += f"  error: {result.error}"
    typer.echo(line)


@app.command("show")
def show_command(
    name: Annotated[str, typer.Argument()],
    secrets: Annotated[bool, typer.Option("--secrets", help="Include sensitive values.")] = False,
) -> None:
    """Print one profile (secrets redacted by default)."""
    from dhis2w_core.v42.cli_output import DetailRow, render_detail
    from dhis2w_core.v42.plugins.profile import service

    view = service.show_profile(name, include_secrets=secrets)
    dumped = view.model_dump(exclude_none=True)
    if is_json_output():
        typer.echo(json.dumps(dumped, indent=2, default=str))
        return
    rows: list[DetailRow] = []
    meta = dumped.pop("meta", None)
    for key, value in dumped.items():
        rows.append(DetailRow(key, str(value) if not isinstance(value, (dict, list)) else json.dumps(value)))
    if isinstance(meta, dict):
        for sub_key, sub_value in meta.items():
            rows.append(DetailRow(f"meta.{sub_key}", str(sub_value)))
    render_detail(f"profile {name}", rows)


@app.command("env")
def env_command(
    name: Annotated[str | None, typer.Argument(help="Profile name; defaults to the active profile.")] = None,
) -> None:
    """Print `export DHIS2_*` lines for a profile, for `eval`.

    Offline read — no instance probe; the wire client auto-detects the version on connect.
    Values are printed as-is (the password / token is already plaintext in `profiles.toml`),
    so the output is directly usable: `eval "$(d2w profile env local_basic)"`. The command
    only prints to stdout — it cannot mutate the caller's shell. For a redacted view (e.g.
    screen-sharing) use `d2w profile show` instead.
    """
    import shlex

    from dhis2w_core.plugin import DEFAULT_VERSION_KEY

    resolved = resolve(name)
    profile = resolved.profile

    def _export(key: str, value: str) -> None:
        typer.echo(f"export {key}={shlex.quote(value)}")

    def _export_if(key: str, value: str | None) -> None:
        if value:
            _export(key, value)

    # DHIS2_PROFILE alone reproduces the whole profile via the TOML.
    _export("DHIS2_PROFILE", resolved.name)
    _export("DHIS2_URL", profile.base_url)
    if profile.version is not None:
        version_key = profile.version.value
    else:
        env_version = os.environ.get("DHIS2_VERSION", "").strip()
        version_key = env_version if env_version in {"v41", "v42", "v43"} else DEFAULT_VERSION_KEY
        typer.echo(
            f"note: profile {resolved.name!r} has no version pin; emitting {version_key}. "
            "Pin it with `d2w profile add ... --version vNN`.",
            err=True,
        )
    _export("DHIS2_VERSION", version_key)

    if profile.auth == "basic":
        _export_if("DHIS2_USERNAME", profile.username)
        _export_if("DHIS2_PASSWORD", profile.password)
    elif profile.auth == "pat":
        _export_if("DHIS2_PAT", profile.token)
    elif profile.auth == "session":
        _export_if("DHIS2_SESSION_COOKIE", profile.cookie)
        typer.echo(
            "note: DHIS2_SESSION_COOKIE has no raw-env path; a session profile must exist in "
            "profiles.toml. The exported DHIS2_PROFILE makes `d2w` use this TOML profile.",
            err=True,
        )
    elif profile.auth == "oauth2":
        _export_if("DHIS2_OAUTH_CLIENT_ID", profile.client_id)
        oauth_client_secret = profile.client_secret
        _export_if("DHIS2_OAUTH_CLIENT_SECRET", oauth_client_secret)
        typer.echo(
            "note: oauth2 has no full raw-env path; the access token comes from the profile's "
            "token store. The exported DHIS2_PROFILE makes `d2w` use this TOML profile.",
            err=True,
        )


def _resolve_scope(*, is_global: bool, is_local: bool, default: str = "global") -> str:
    """Translate the --global/--local flag pair into a 'global' | 'project' string."""
    if is_global and is_local:
        raise typer.BadParameter("--global and --local are mutually exclusive")
    if is_local:
        return "project"
    if is_global:
        return "global"
    return default


def _run_verify(name: str) -> None:
    """Probe a profile and print a one-line OK/FAIL line; never raises."""
    from dhis2w_core.v42.plugins.profile import service

    result = asyncio.run(service.verify_profile(name))
    if result.ok:
        line = f"  verified: version={result.version} user={result.username} ({result.latency_ms} ms)"
        typer.secho(line, fg=typer.colors.GREEN)
    else:
        typer.secho(f"  verify failed: {result.error}", err=True, fg=typer.colors.YELLOW)
        typer.echo("  (profile was saved; run `d2w profile verify` later to re-check)")


@app.command("default")
def default_command(
    name: Annotated[
        str | None,
        typer.Argument(help="Profile name to set as default. Omit to pick interactively from a list."),
    ] = None,
    global_scope: Annotated[
        bool,
        typer.Option("--global", help="Write to ~/.config/dhis2/profiles.toml (default)."),
    ] = False,
    local_scope: Annotated[
        bool,
        typer.Option("--local", help="Write to ./.dhis2/profiles.toml instead."),
    ] = False,
    verify: Annotated[
        bool,
        typer.Option("--verify", help="Probe the instance after switching."),
    ] = False,
) -> None:
    """Set `default = <name>` in the global (default) or project profiles.toml.

    When `name` is omitted and stdin is a TTY, the command renders the
    profile list + prompts for a numbered selection. Pass `--global` or
    `--local` to pick the profiles.toml to write (`--global` is the
    default).
    """
    from dhis2w_core.v42.plugins.profile import service

    scope = _resolve_scope(is_global=global_scope, is_local=local_scope)
    if name is None:
        name = _prompt_for_profile_name()
    try:
        path = service.set_default_profile(name, scope=scope)
    except UnknownProfileError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"default profile in {scope} scope set to {name!r} ({path})")
    if verify:
        _run_verify(name)


def _prompt_for_profile_name() -> str:
    """Arrow-key picker over available profiles; pre-selects the current default.

    Uses `questionary.select` for the interactive TUI — arrow keys +
    Enter. Cancelling with Ctrl+C / ESC exits cleanly. Bails out with a
    clear error on non-TTY stdin so CI / pipes don't hang.
    """
    import sys

    import questionary

    from dhis2w_core.v42.plugins.profile import service

    summaries = service.list_profiles(include_shadowed=False)
    if not summaries:
        typer.echo("no profiles found — run `d2w profile add <name>` to create one.", err=True)
        raise typer.Exit(1)
    if not sys.stdin.isatty():
        typer.echo(
            "error: no profile name given and stdin is not a TTY — pass a name explicitly (see `d2w profile list`).",
            err=True,
        )
        raise typer.Exit(1)

    choices = [questionary.Choice(title=_picker_label(summary), value=summary.name) for summary in summaries]
    default_name = next((s.name for s in summaries if s.is_default), summaries[0].name)
    selection = questionary.select(
        "pick a profile to set as default:",
        choices=choices,
        default=default_name,
        use_arrow_keys=True,
        use_shortcuts=False,
    ).ask()
    if selection is None:  # Ctrl+C / ESC
        typer.echo("cancelled", err=True)
        raise typer.Exit(1)
    return str(selection)


def _picker_label(summary: service.ProfileSummary) -> str:
    """Single-line picker label: `* name  auth  base_url  source` for default rows."""
    star = "*" if summary.is_default else " "
    source = _friendly_source(summary.source)
    return f"{star} {summary.name:<16} {summary.auth:<8} {summary.base_url:<32} {source}"


@app.command("add")
def add_command(
    name: Annotated[str, typer.Argument()],
    base_url: Annotated[str | None, typer.Option("--url", help="DHIS2 base URL (also: DHIS2_URL env).")] = None,
    auth: Annotated[str, typer.Option("--auth", help="pat | basic | oauth2 | session")] = "pat",
    username: Annotated[str | None, typer.Option("--username", help="Basic-auth username.")] = None,
    client_id: Annotated[str | None, typer.Option("--client-id", help="OAuth2 client_id.")] = None,
    oauth_scope: Annotated[
        str,
        typer.Option("--scope", help="OAuth2 scope (DHIS2 only recognises `ALL`)."),
    ] = "ALL",
    redirect_uri: Annotated[
        str,
        typer.Option("--redirect-uri", help="OAuth2 redirect URI (must match the registered client)."),
    ] = DEFAULT_REDIRECT_URI,
    from_env: Annotated[
        bool,
        typer.Option(
            "--from-env",
            help=(
                "Pull OAuth2 fields from DHIS2_OAUTH_CLIENT_ID / DHIS2_OAUTH_CLIENT_SECRET / "
                "DHIS2_OAUTH_REDIRECT_URI / DHIS2_OAUTH_SCOPES env vars (seeded .env.auth)."
            ),
        ),
    ] = False,
    global_scope: Annotated[
        bool,
        typer.Option(
            "--global",
            help="Save to ~/.config/dhis2/profiles.toml (default — user-wide, applies everywhere).",
        ),
    ] = False,
    local_scope: Annotated[
        bool,
        typer.Option(
            "--local",
            help="Save to ./.dhis2/profiles.toml instead (project-scoped, overrides global).",
        ),
    ] = False,
    make_default: Annotated[bool, typer.Option("--default", help="Set as default after adding.")] = False,
    verify: Annotated[
        bool,
        typer.Option("--verify", help="Probe /api/system/info + /api/me after saving."),
    ] = False,
    version: Annotated[str | None, typer.Option("--version", help=_VERSION_HELP)] = None,
) -> None:
    """Add (or upsert) a profile.

    Secrets are never accepted as command-line flags (they'd leak into shell history).
    Read from env (`DHIS2_PAT`, `DHIS2_PASSWORD`, `DHIS2_OAUTH_CLIENT_SECRET`,
    `DHIS2_SESSION_COOKIE`) or prompted interactively when missing.
    """
    from dhis2w_core.v42.plugins.profile import service

    scope = _resolve_scope(is_global=global_scope, is_local=local_scope)
    pinned_version = _validate_version(version)
    if from_env and auth == "oauth2":
        client_id = client_id or os.environ.get("DHIS2_OAUTH_CLIENT_ID")
        redirect_uri = os.environ.get("DHIS2_OAUTH_REDIRECT_URI", redirect_uri)
        oauth_scope = os.environ.get("DHIS2_OAUTH_SCOPES", oauth_scope)
        base_url = base_url or os.environ.get("DHIS2_URL")
    resolved_url: str = (
        base_url
        or os.environ.get("DHIS2_URL")
        or typer.prompt(
            "DHIS2 base URL",
            default="http://localhost:8080",
        )
    )
    if auth == "pat":
        token = os.environ.get("DHIS2_PAT") or typer.prompt("Personal Access Token", hide_input=True)
        profile = Profile(base_url=resolved_url, auth="pat", token=token, version=pinned_version)
    elif auth == "basic":
        username = username or typer.prompt("Username", default="admin")
        password = os.environ.get("DHIS2_PASSWORD") or typer.prompt(
            "Password",
            hide_input=True,
            default="district",
            show_default=False,
        )
        profile = Profile(
            base_url=resolved_url,
            auth="basic",
            username=username,
            password=password,
            version=pinned_version,
        )
    elif auth == "session":
        cookie = (
            os.environ.get("DHIS2_SESSION_COOKIE")
            or typer.prompt("Session cookie (e.g. JSESSIONID=...)", hide_input=True)
        ).strip()
        profile = Profile(base_url=resolved_url, auth="session", cookie=cookie, version=pinned_version)
    elif auth == "oauth2":
        client_id = client_id or typer.prompt("OAuth2 client_id", default="dhis2-utils-local")
        client_secret = os.environ.get("DHIS2_OAUTH_CLIENT_SECRET") or typer.prompt(
            "OAuth2 client_secret",
            hide_input=True,
        )
        profile = Profile(
            base_url=resolved_url,
            auth="oauth2",
            client_id=client_id,
            client_secret=client_secret,
            scope=oauth_scope,
            redirect_uri=redirect_uri,
            version=pinned_version,
        )
    else:
        raise typer.BadParameter(f"unsupported auth {auth!r}; use pat, basic, oauth2, or session")
    result = service.add_profile(name, profile, scope=scope, make_default=make_default)
    typer.echo(f"profile {name!r} saved to {result.path}")
    if result.shadowed_scope == "global":
        typer.secho(
            f"  warning: a profile named {name!r} also exists in the global scope; "
            "the project-scoped one will override it when you're in this directory.",
            err=True,
            fg=typer.colors.YELLOW,
        )
    elif result.shadowed_scope == "project":
        typer.secho(
            f"  warning: a profile named {name!r} also exists in a project scope; "
            "the project-scoped one will still override this global entry in that directory.",
            err=True,
            fg=typer.colors.YELLOW,
        )
    if verify:
        _run_verify(name)


@app.command("remove")
def remove_command(
    name: Annotated[str, typer.Argument()],
    global_scope: Annotated[
        bool,
        typer.Option("--global", help="Remove from ~/.config/dhis2/profiles.toml specifically."),
    ] = False,
    local_scope: Annotated[
        bool,
        typer.Option("--local", help="Remove from ./.dhis2/profiles.toml specifically."),
    ] = False,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip the confirmation prompt.")] = False,
) -> None:
    """Remove a profile. Without --global/--local, removes from whichever file holds it."""
    from dhis2w_core.v42.plugins.profile import service

    if global_scope and local_scope:
        raise typer.BadParameter("--global and --local are mutually exclusive")
    if not yes:
        typer.confirm(
            f"remove profile {name!r}? If it holds a PAT or client_secret that DHIS2 showed "
            "only once, that credential cannot be recovered after removal.",
            abort=True,
        )
    scope: str | None = None
    if local_scope:
        scope = "project"
    elif global_scope:
        scope = "global"
    try:
        path = service.remove_profile(name, scope=scope)
    except UnknownProfileError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"removed {name!r} from {path}")


@app.command("rename")
def rename_command(
    old_name: Annotated[str, typer.Argument(help="Current profile name.")],
    new_name: Annotated[str, typer.Argument(help="New profile name (letters, digits, underscores).")],
    verify: Annotated[
        bool,
        typer.Option("--verify", help="Probe the instance after renaming."),
    ] = False,
) -> None:
    """Rename a profile in-place. Preserves scope and updates default if needed."""
    from dhis2w_core.v42.plugins.profile import service

    path = service.rename_profile(old_name, new_name)
    typer.echo(f"renamed {old_name!r} -> {new_name!r} in {path}")
    if verify:
        _run_verify(new_name)


@app.command("login")
def login_command(
    name: Annotated[str | None, typer.Argument(help="Profile name; omit to use the default.")] = None,
    no_browser: Annotated[
        bool,
        typer.Option(
            "--no-browser",
            help=(
                "Print the DHIS2 authorization URL instead of launching the system browser. "
                "Useful over SSH, under Playwright, or when logging in via a different browser. "
                "Also accepts DHIS2_OAUTH_NO_BROWSER=1 as default."
            ),
        ),
    ] = False,
) -> None:
    """Run the OAuth2 authorization-code flow for a profile and persist its tokens.

    Opens a browser to DHIS2's authorization endpoint, listens on the profile's
    `redirect_uri` (local FastAPI+uvicorn), exchanges the code for tokens,
    and writes them to the scope-appropriate tokens.sqlite. OAuth2 profiles only.

    Pass `--no-browser` (or `DHIS2_OAUTH_NO_BROWSER=1`) to print the URL to
    stderr instead of launching the system browser.
    """
    from dhis2w_core.v42.client_context import build_auth, scope_from_resolved

    resolved = resolve(name)
    if resolved.profile.auth != "oauth2":
        typer.secho(
            f"error: profile {resolved.name!r} uses auth={resolved.profile.auth!r}; "
            "login only applies to oauth2 profiles",
            err=True,
            fg=typer.colors.RED,
        )
        raise typer.Exit(1)
    preflight_error = asyncio.run(check_oauth2_server(resolved.profile.base_url))
    if preflight_error is not None:
        typer.secho(f"error: {preflight_error}", err=True, fg=typer.colors.RED)
        raise typer.Exit(1)
    # Drop any stored tokens first so refresh_if_needed falls through to the
    # full authorization flow — otherwise `profile login` on an existing
    # profile with a stale refresh_token would try to refresh and 400.
    from dhis2w_core.v42.token_store import token_store_for_scope

    scope_name = scope_from_resolved(resolved)
    token_store = token_store_for_scope(scope_name)
    store_key = f"profile:{resolved.name}"
    asyncio.run(token_store.delete(store_key))

    open_browser = not (no_browser or os.environ.get("DHIS2_OAUTH_NO_BROWSER", "0") == "1")
    auth = build_auth(
        resolved.profile,
        profile_name=resolved.name,
        scope=scope_name,
        open_browser=open_browser,
    )
    if open_browser:
        typer.echo(f"opening browser for {resolved.name!r} -> {resolved.profile.base_url} ...")
    else:
        typer.echo(f"starting OAuth2 login for {resolved.name!r} -> {resolved.profile.base_url} (no-browser mode) ...")
    asyncio.run(auth.refresh_if_needed())
    _run_verify(resolved.name)


@app.command("logout")
def logout_command(
    name: Annotated[str | None, typer.Argument(help="Profile name; omit to use the default.")] = None,
) -> None:
    """Clear persisted OAuth2 tokens for a profile.

    Removes the row from the scope-appropriate `tokens.sqlite`. Next API call
    triggers a fresh `profile login` flow. OAuth2 profiles only.
    """
    from dhis2w_core.v42.client_context import scope_from_resolved
    from dhis2w_core.v42.token_store import token_store_for_scope

    resolved = resolve(name)
    if resolved.profile.auth != "oauth2":
        typer.secho(
            f"error: profile {resolved.name!r} uses auth={resolved.profile.auth!r}; logout only applies to oauth2",
            err=True,
            fg=typer.colors.RED,
        )
        raise typer.Exit(1)
    store = token_store_for_scope(scope_from_resolved(resolved))

    async def _clear() -> Path:
        await store.delete(f"profile:{resolved.name}")
        path = store.db_path
        await store.close()
        return path

    store_path = asyncio.run(_clear())
    typer.echo(f"logged out {resolved.name!r} (cleared token row in {store_path})")


def _resolve_admin_auth(admin_user: str | None) -> Any:
    """Pick admin-auth creds — env first, then interactive prompt. Never argv secrets."""
    from dhis2w_core.v42.oauth2_registration import build_admin_auth

    admin_pat = os.environ.get("DHIS2_ADMIN_PAT")
    admin_pass = os.environ.get("DHIS2_ADMIN_PASSWORD")
    if not admin_pat and not admin_pass:
        if admin_user or typer.confirm("Bootstrap with username+password? (no = PAT)", default=True):
            if not admin_user:
                admin_user = typer.prompt("Admin username", default="admin")
            admin_pass = typer.prompt("Admin password", hide_input=True)
        else:
            admin_pat = typer.prompt("Admin PAT", hide_input=True)
    return build_admin_auth(pat=admin_pat, username=admin_user, password=admin_pass)


@app.command("bootstrap")
def bootstrap_command(
    name: Annotated[str, typer.Argument(help="Profile name to create.")],
    auth: Annotated[str, typer.Option("--auth", help="pat | oauth2 — which kind of profile to set up.")] = "oauth2",
    url: Annotated[str | None, typer.Option("--url", help="DHIS2 base URL (also: DHIS2_URL env).")] = None,
    admin_user: Annotated[
        str | None, typer.Option("--admin-user", help="Admin username (for basic bootstrap).")
    ] = None,
    client_id: Annotated[
        str, typer.Option("--client-id", help="OAuth2 client_id to register (auth=oauth2).")
    ] = "dhis2-utils-local",
    redirect_uri: Annotated[str, typer.Option("--redirect-uri", help="OAuth2 redirect URI.")] = DEFAULT_REDIRECT_URI,
    scope: Annotated[str, typer.Option("--scope", help="OAuth2 scope.")] = "ALL",
    pat_description: Annotated[
        str | None, typer.Option("--pat-description", help="PAT description (auth=pat).")
    ] = None,
    pat_expires_in_days: Annotated[
        int | None, typer.Option("--pat-expires-in-days", help="PAT lifetime in days; omit for no expiry.")
    ] = None,
    global_scope: Annotated[
        bool, typer.Option("--global", help="Save to ~/.config/dhis2/profiles.toml (default).")
    ] = False,
    local_scope: Annotated[bool, typer.Option("--local", help="Save to ./.dhis2/profiles.toml instead.")] = False,
    login: Annotated[
        bool,
        typer.Option(
            "--login/--no-login",
            help="For auth=oauth2, run `profile login` after saving. Ignored for auth=pat.",
        ),
    ] = True,
    version: Annotated[str | None, typer.Option("--version", help=_VERSION_HELP)] = None,
) -> None:
    """One-shot: provision a PAT or OAuth2 client on DHIS2, save a profile, (for oauth2) log in.

    Secrets never come in via argv. Read from env
    (`DHIS2_ADMIN_PAT`, `DHIS2_ADMIN_PASSWORD`, `DHIS2_OAUTH_CLIENT_SECRET`)
    or prompted interactively when missing. Admin creds are used once to POST
    `/api/apiToken` (pat) or `/api/oAuth2Clients` (oauth2), then discarded.

    Re-runs for `auth=oauth2` fail at POST /api/oAuth2Clients if `client_id` is
    taken — pass a different `--client-id` in that case. PAT bootstraps never
    collide (DHIS2 mints a fresh server-side UID).
    """
    from dhis2w_core.v42.oauth2_registration import register_oauth2_client
    from dhis2w_core.v42.pat_registration import register_pat
    from dhis2w_core.v42.plugins.profile import service

    if global_scope and local_scope:
        raise typer.BadParameter("--global and --local are mutually exclusive")
    profile_scope = "project" if local_scope else "global"
    pinned_version = _validate_version(version)

    resolved_url: str = url or os.environ.get("DHIS2_URL") or typer.prompt("DHIS2 base URL")
    admin_auth = _resolve_admin_auth(admin_user)

    if auth == "pat":
        typer.echo(f"creating PAT at {resolved_url} ...")
        pat_creds = asyncio.run(
            register_pat(
                base_url=resolved_url,
                admin_auth=admin_auth,
                description=pat_description or f"profile {name}",
                expires_in_days=pat_expires_in_days,
            )
        )
        typer.echo(f"  registered (uid={pat_creds.uid})")
        profile = Profile(base_url=resolved_url, auth="pat", token=pat_creds.token, version=pinned_version)
    elif auth == "oauth2":
        client_secret = os.environ.get("DHIS2_OAUTH_CLIENT_SECRET") or typer.prompt(
            f"New OAuth2 client_secret to set for {client_id!r}", hide_input=True
        )
        typer.echo(f"registering OAuth2 client {client_id!r} at {resolved_url} ...")
        oauth_creds = asyncio.run(
            register_oauth2_client(
                base_url=resolved_url,
                admin_auth=admin_auth,
                client_id=client_id,
                client_secret=client_secret,
                redirect_uri=redirect_uri,
                scope=scope,
            )
        )
        typer.echo(f"  registered (uid={oauth_creds.uid})")
        profile = Profile(
            base_url=resolved_url,
            auth="oauth2",
            client_id=oauth_creds.client_id,
            client_secret=oauth_creds.client_secret,
            scope=oauth_creds.scope,
            redirect_uri=oauth_creds.redirect_uri,
            version=pinned_version,
        )
    else:
        raise typer.BadParameter(f"unsupported auth {auth!r}; use pat or oauth2")

    result = service.add_profile(name, profile, scope=profile_scope, make_default=True)
    typer.echo(f"  profile {name!r} saved to {result.path}")

    if auth == "oauth2" and login:
        typer.echo(f"  starting OAuth2 login for {name!r} ...")
        login_command(name=name)
    elif auth == "pat":
        _run_verify(name)


@app.command("oidc-config")
def oidc_config_command(
    url: Annotated[
        str,
        typer.Argument(help="DHIS2 base URL or full /.well-known/openid-configuration URL."),
    ],
    name: Annotated[str, typer.Option("--name", "-n", help="Profile name to save as.")],
    client_id: Annotated[str, typer.Option("--client-id", help="OAuth2 client_id (from your registration).")],
    client_secret: Annotated[
        str | None,
        typer.Option(
            "--client-secret",
            help="OAuth2 client_secret. Omit to read DHIS2_OAUTH_CLIENT_SECRET env or a hidden prompt.",
        ),
    ] = None,
    scope_value: Annotated[
        str,
        typer.Option("--scope", help="OAuth2 scope (DHIS2 only recognises `ALL`)."),
    ] = "ALL",
    redirect_uri: Annotated[
        str,
        typer.Option(
            "--redirect-uri",
            help="OAuth2 redirect URI (match your registered client — default is the CLI's loopback listener).",
        ),
    ] = DEFAULT_REDIRECT_URI,
    global_scope: Annotated[
        bool,
        typer.Option("--global", help="Save to ~/.config/dhis2/profiles.toml (default, user-wide)."),
    ] = False,
    local_scope: Annotated[
        bool,
        typer.Option("--local", help="Save to ./.dhis2/profiles.toml instead (project-scoped)."),
    ] = False,
    make_default: Annotated[bool, typer.Option("--default", help="Set as default after saving.")] = False,
    login_now: Annotated[
        bool,
        typer.Option("--login", help="Trigger `d2w profile login <name>` immediately after saving."),
    ] = False,
    version: Annotated[str | None, typer.Option("--version", help=_VERSION_HELP)] = None,
) -> None:
    """Populate an OAuth2 profile by discovering a DHIS2 instance's OIDC endpoints.

    Fetches `/.well-known/openid-configuration` from the given URL, validates the
    response, and writes a profile with `auth=oauth2` + your client credentials.
    Removes the "hand-edit profiles.toml with the right issuer/auth/token URLs"
    step from the OAuth2 setup walkthrough.

    The URL can be either the DHIS2 base URL (discovery path is appended
    automatically) or the full discovery URL.

    The client_secret never comes in via argv (it would leak to shell history / `ps`).
    Read it from the `DHIS2_OAUTH_CLIENT_SECRET` env var or a hidden prompt when the
    `--client-secret` flag is omitted.
    """
    from dhis2w_core.oauth2_preflight import OidcDiscoveryError
    from dhis2w_core.v42.plugins.profile import service

    scope = _resolve_scope(is_global=global_scope, is_local=local_scope)
    pinned_version = _validate_version(version)
    resolved_secret = (
        client_secret
        or os.environ.get("DHIS2_OAUTH_CLIENT_SECRET")
        or typer.prompt("OAuth2 client_secret", hide_input=True)
    )
    try:
        discovered = asyncio.run(
            service.discover_oidc_profile(
                url,
                client_id=client_id,
                client_secret=resolved_secret,
                scope=scope_value,
                redirect_uri=redirect_uri,
                version=pinned_version,
            )
        )
    except OidcDiscoveryError as exc:
        typer.secho(f"error: {exc}", err=True, fg=typer.colors.RED)
        raise typer.Exit(1) from exc

    if is_json_output():
        typer.echo(discovered.model_dump_json(indent=2, exclude_none=True))
    else:
        typer.secho(f"discovered OIDC config at {discovered.discovery_url}", fg=typer.colors.GREEN)
        typer.echo(f"  issuer:                 {discovered.issuer}")
        typer.echo(f"  authorization_endpoint: {discovered.authorization_endpoint}")
        typer.echo(f"  token_endpoint:         {discovered.token_endpoint}")
        typer.echo(f"  jwks_uri:               {discovered.jwks_uri}")
        if discovered.scopes_supported:
            typer.echo(f"  scopes_supported:       {discovered.scopes_supported}")

    result = service.add_profile(name, discovered.profile, scope=scope, make_default=make_default)
    typer.secho(f"saved profile {name!r} → {result.path}", fg=typer.colors.GREEN)
    if result.shadowed_scope:
        typer.secho(
            f"  note: this profile also exists in the {result.shadowed_scope} scope (it's shadowed).",
            fg=typer.colors.YELLOW,
        )

    if login_now:
        typer.echo("\n>>> running `d2w profile login` now...")
        # Reuse the login command in-process — mirrors what a second CLI invocation would do.
        login_command(name)


app.add_typer(pat_module.app, name="pat")
app.add_typer(oauth2_module.app, name="oauth2")


def register(root_app: Any) -> None:
    """Mount under `d2w profile`."""
    root_app.add_typer(app, name="profile", help="Manage DHIS2 profiles.")
