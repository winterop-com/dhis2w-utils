"""Typer sub-app for the `route` plugin (mounted under `d2w route`)."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Annotated, Any

import typer
from dhis2w_client.v43 import JsonPatchOpAdapter
from dhis2w_client.v43.auth_schemes import (
    ApiHeadersAuthScheme,
    ApiQueryParamsAuthScheme,
    ApiTokenAuthScheme,
    AuthScheme,
    HttpBasicAuthScheme,
    OAuth2ClientCredentialsAuthScheme,
)
from pydantic import ValidationError

from dhis2w_core.profile import profile_from_env
from dhis2w_core.v43.cli_output import (
    ColumnSpec,
    DetailRow,
    format_disabled,
    is_json_output,
    render_detail,
    render_list,
    render_webmessage,
)
from dhis2w_core.v43.plugins.route import service
from dhis2w_core.v43.plugins.route.service import RoutePayload

app = typer.Typer(
    help="DHIS2 Route API — register + run integration routes (proxies to external services).",
    no_args_is_help=True,
)

_AUTH_TYPES: dict[str, str] = {
    "none": "No upstream authentication. DHIS2 forwards the request as-is.",
    "http-basic": (
        "HTTP Basic auth (username + password). DHIS2 adds an `Authorization: Basic base64(user:pw)` "
        "header to each upstream call. Classic and widely supported."
    ),
    "api-token": (
        "Static API token in the `Authorization` header. DHIS2 sends "
        "`Authorization: ApiToken <token>` — a DHIS2-specific scheme, NOT standard `Bearer`. "
        "Upstream services must accept the ApiToken scheme, or you'll get 401s. See BUGS.md #4e."
    ),
    "api-headers": (
        "Arbitrary custom HTTP headers (e.g. `X-Api-Key: abc`). "
        "Use when the upstream wants auth in a non-standard header."
    ),
    "api-query-params": (
        "Auth via URL query-string parameters (e.g. `?api_key=abc`). "
        "Common on older APIs; less secure because values land in server logs."
    ),
    "oauth2-client-credentials": (
        "OAuth2 Client Credentials grant. DHIS2 POSTs to an upstream `tokenUri` with client_id+secret, "
        "caches the access token, uses it for subsequent upstream calls. Use for machine-to-machine auth — "
        "the upstream is often another DHIS2 or any OAuth2-protected resource server."
    ),
}


def _print(payload: Any) -> None:
    typer.echo(json.dumps(payload, indent=2, default=str))


@app.command("list")
@app.command("ls", hidden=True)
def list_command(
    fields: Annotated[str, typer.Option("--fields")] = "id,code,name,url,disabled,auth",
) -> None:
    """List registered routes."""
    routes = asyncio.run(service.list_routes(profile_from_env(), fields=fields))
    dumped = [r.model_dump(exclude_none=True, mode="json") for r in routes]
    if is_json_output():
        _print(dumped)
        return
    if not dumped:
        typer.echo("(no routes)")
        return
    render_list(
        "routes",
        dumped,
        [
            ColumnSpec("id", "id", style="cyan", no_wrap=True),
            ColumnSpec("code", "code"),
            ColumnSpec("name", "name"),
            ColumnSpec("url", "url"),
            ColumnSpec("auth", "auth", formatter=_auth_label),
            ColumnSpec("disabled", "disabled", formatter=format_disabled),
        ],
    )


_ROUTE_REF_HELP = "Route UID (e.g. E8OPcc45A22) or code (e.g. chap)."


@app.command("get")
def get_command(
    route: Annotated[str, typer.Argument(help=_ROUTE_REF_HELP)],
    fields: Annotated[str | None, typer.Option("--fields")] = None,
) -> None:
    """Fetch one route by UID or code."""
    fetched = asyncio.run(service.get_route(profile_from_env(), route, fields=fields))
    if is_json_output():
        _print(fetched.model_dump(exclude_none=True, mode="json"))
        return
    auth = getattr(fetched, "auth", None)
    auth_type = auth.get("type") if isinstance(auth, dict) else getattr(auth, "type", None) if auth else None
    rows = [
        DetailRow("id", str(fetched.id or "-")),
        DetailRow("code", str(getattr(fetched, "code", None) or "-")),
        DetailRow("name", str(getattr(fetched, "name", None) or "-")),
        DetailRow("url", str(getattr(fetched, "url", None) or "-")),
        DetailRow("disabled", format_disabled(getattr(fetched, "disabled", None))),
        DetailRow("auth", str(auth_type) if auth_type else "-"),
    ]
    authorities = getattr(fetched, "authorities", None)
    if authorities:
        rows.append(DetailRow(f"authorities ({len(authorities)})", ", ".join(authorities)))
    render_detail(f"route {getattr(fetched, 'name', None) or fetched.id}", rows)


def _auth_label(value: Any) -> str:
    """Render the auth sub-block as its `type` tag for list tables."""
    if value is None:
        return "-"
    if isinstance(value, dict):
        return str(value.get("type") or "-")
    return str(getattr(value, "type", None) or "-")


def _prompt_auth() -> AuthScheme | None:
    """Interactively build the `auth` block for a route. Returns None for no auth."""
    typer.echo("")
    typer.secho("Upstream authentication — how DHIS2 talks to the target:", bold=True)
    for name, description in _AUTH_TYPES.items():
        typer.echo(f"  {name}")
        for line in _wrap_help(description):
            typer.echo(f"      {line}")
    typer.echo("")
    auth_type = typer.prompt("auth type", default="none").strip()
    if auth_type == "none":
        return None
    if auth_type == "http-basic":
        username = typer.prompt("upstream username")
        password = os.environ.get("DHIS2_ROUTE_UPSTREAM_PASSWORD") or typer.prompt("upstream password", hide_input=True)
        return HttpBasicAuthScheme(username=username, password=password)
    if auth_type == "api-token":
        token = os.environ.get("DHIS2_ROUTE_UPSTREAM_TOKEN") or typer.prompt("upstream token", hide_input=True)
        return ApiTokenAuthScheme(token=token)
    if auth_type == "api-headers":
        header_name = typer.prompt("header name (e.g. X-Api-Key)")
        header_value = os.environ.get("DHIS2_ROUTE_UPSTREAM_HEADER_VALUE") or typer.prompt(
            f"value for {header_name}", hide_input=True
        )
        return ApiHeadersAuthScheme(headers={header_name: header_value})
    if auth_type == "api-query-params":
        param_name = typer.prompt("query-param name (e.g. api_key)")
        param_value = os.environ.get("DHIS2_ROUTE_UPSTREAM_QUERY_VALUE") or typer.prompt(
            f"value for {param_name}", hide_input=True
        )
        return ApiQueryParamsAuthScheme(queryParams={param_name: param_value})
    if auth_type == "oauth2-client-credentials":
        token_uri = typer.prompt("upstream tokenUri (e.g. https://auth.example/oauth2/token)")
        client_id = typer.prompt("upstream client_id")
        client_secret = os.environ.get("DHIS2_ROUTE_UPSTREAM_CLIENT_SECRET") or typer.prompt(
            "upstream client_secret", hide_input=True
        )
        scopes = typer.prompt("scopes (space-separated; blank for none)", default="").strip() or None
        return OAuth2ClientCredentialsAuthScheme(
            tokenUri=token_uri,
            clientId=client_id,
            clientSecret=client_secret,
            scopes=scopes,
        )
    raise typer.BadParameter(f"unknown auth type {auth_type!r}; valid: {', '.join(_AUTH_TYPES)}")


def _wrap_help(text: str, width: int = 74) -> list[str]:
    """Soft-wrap a help string for the auth-type menu."""
    words = text.split()
    lines: list[str] = []
    current: list[str] = []
    length = 0
    for word in words:
        if current and length + 1 + len(word) > width:
            lines.append(" ".join(current))
            current = [word]
            length = len(word)
        else:
            current.append(word)
            length = length + 1 + len(word) if current else len(word)
    if current:
        lines.append(" ".join(current))
    return lines


@app.command("create")
def create_command(
    file: Annotated[
        Path | None,
        typer.Option(
            "--file",
            help="JSON file with the route definition (bypass the interactive wizard).",
        ),
    ] = None,
    code: Annotated[str | None, typer.Option("--code")] = None,
    name: Annotated[str | None, typer.Option("--name")] = None,
    url: Annotated[str | None, typer.Option("--url", help="Target URL the route proxies to.")] = None,
    authorities: Annotated[
        str | None,
        typer.Option("--authorities", help="Comma-separated DHIS2 authorities allowed to run this route."),
    ] = None,
    no_auth: Annotated[
        bool,
        typer.Option(
            "--no-auth", help="Create an unauthenticated route (skip the auth wizard) — for headless/bridge use."
        ),
    ] = False,
) -> None:
    """Create a route via POST /api/routes.

    With `--file`: a full JSON spec. Omit `auth` (or set it to null) for no upstream auth.

    Flag form: pass --code/--name/--url. Add --no-auth for an unauthenticated route (required
    when not running in a TTY — the auth wizard needs interactive input). Secrets never come via
    argv — they're read from env (`DHIS2_ROUTE_UPSTREAM_*`) or hidden prompts in the wizard.
    """
    if file is not None:
        raw = json.loads(file.read_text(encoding="utf-8"))
        if isinstance(raw, dict) and isinstance(raw.get("auth"), dict) and raw["auth"].get("type") in (None, "none"):
            raw.pop("auth")  # the auth union has no `none` variant — omit it for an unauthenticated route
        try:
            payload = RoutePayload.model_validate(raw)
        except ValidationError as exc:
            errs = exc.errors()
            if errs:
                loc = ".".join(str(p) for p in errs[0]["loc"])
                detail = f"{loc}: {errs[0]['msg']}"
            else:
                detail = str(exc)
            typer.secho(
                f"error: invalid route spec ({exc.error_count()} error(s)): {detail}",
                err=True,
                fg=typer.colors.RED,
            )
            raise typer.Exit(2) from exc
    else:
        interactive = sys.stdin.isatty()
        missing = [flag for flag, val in (("--code", code), ("--name", name), ("--url", url)) if not val]
        if missing and not interactive:
            typer.secho(
                f"error: {', '.join(missing)} required (or use --file) when not running interactively",
                err=True,
                fg=typer.colors.RED,
            )
            raise typer.Exit(2)
        if not code:
            code = typer.prompt("Route code (stable identifier)")
        if not name:
            name = typer.prompt("Route display name")
        if not url:
            url = typer.prompt("Target URL")
        parsed_authorities = [a.strip() for a in authorities.split(",") if a.strip()] if authorities else None
        if no_auth:
            auth = None
        elif interactive:
            auth = _prompt_auth()
        else:
            auth = None
            typer.secho(
                "note: no --no-auth and not a TTY — creating an unauthenticated route (use --file for upstream auth).",
                err=True,
                fg=typer.colors.YELLOW,
            )
        payload = RoutePayload(code=code, name=name, url=url, authorities=parsed_authorities, auth=auth)
    response = asyncio.run(service.add_route(profile_from_env(), payload))
    render_webmessage(response, action="created")


@app.command("update")
def update_command(
    route: Annotated[str, typer.Argument(help=_ROUTE_REF_HELP)],
    file: Annotated[Path, typer.Option("--file", help="JSON file with the full route spec (PUT semantics).")],
) -> None:
    """Replace a route via PUT /api/routes/{uid}.

    DHIS2 PUT expects the complete object. For partial updates use `patch`.
    """
    payload = RoutePayload.model_validate(json.loads(file.read_text(encoding="utf-8")))
    response = asyncio.run(service.update_route(profile_from_env(), route, payload))
    render_webmessage(response, action=f"updated {route}")


@app.command("patch")
def patch_command(
    route: Annotated[str, typer.Argument(help=_ROUTE_REF_HELP)],
    file: Annotated[Path, typer.Option("--file", help="JSON Patch array (RFC 6902).")],
) -> None:
    """Apply a JSON Patch to a route via PATCH /api/routes/{uid}."""
    raw_ops = json.loads(file.read_text(encoding="utf-8"))
    if not isinstance(raw_ops, list):
        raise typer.BadParameter(f"{file} must contain a JSON Patch array (got {type(raw_ops).__name__})")
    patch = [JsonPatchOpAdapter.validate_python(op) for op in raw_ops]
    response = asyncio.run(service.patch_route(profile_from_env(), route, patch))
    render_webmessage(response, action=f"patched {route}")


@app.command("delete")
def delete_command(
    route: Annotated[str, typer.Argument(help=_ROUTE_REF_HELP)],
) -> None:
    """Delete a route."""
    response = asyncio.run(service.delete_route(profile_from_env(), route))
    render_webmessage(response, action=f"deleted {route}")


@app.command("run")
def run_command(
    route: Annotated[str, typer.Argument(help=_ROUTE_REF_HELP)],
    method: Annotated[str, typer.Option("--method", "-X")] = "GET",
    body_file: Annotated[
        Path | None,
        typer.Option("--body", help="JSON body file for POST/PUT."),
    ] = None,
    sub_path: Annotated[
        str | None,
        typer.Option("--path", help="Additional path segment appended to the route's target URL."),
    ] = None,
) -> None:
    """Execute a route — DHIS2 proxies the request to the configured target URL.

    `route` accepts the route's UID or its `code`. When the route's target
    URL ends in a wildcard (`/**`), `--path SEGMENT` is required: it is
    what DHIS2 substitutes into the wildcard before calling upstream.
    """
    body = json.loads(body_file.read_text(encoding="utf-8")) if body_file is not None else None
    _print(asyncio.run(service.run_route(profile_from_env(), route, method=method, body=body, sub_path=sub_path)))


def register(root_app: Any) -> None:
    """Mount under `d2w route`."""
    root_app.add_typer(app, name="route", help="DHIS2 integration routes.")
