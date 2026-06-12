"""`d2w dev oauth2` — manage DHIS2 OAuth2 clients via admin auth."""

from __future__ import annotations

import asyncio
import os
from typing import Annotated

import typer
from dhis2w_client.v43.auth.oauth2 import DEFAULT_REDIRECT_URI

from dhis2w_core.v43.admin_auth import resolve_admin_auth
from dhis2w_core.v43.oauth2_registration import register_oauth2_client

app = typer.Typer(help="Manage DHIS2 OAuth2 clients on the server (admin ops).", no_args_is_help=True)
client_app = typer.Typer(help="OAuth2 client registrations at /api/oAuth2Clients.", no_args_is_help=True)
app.add_typer(client_app, name="client")


@client_app.command("register")
def oauth2_client_register_command(
    url: Annotated[str | None, typer.Option("--url", help="DHIS2 base URL (also: DHIS2_URL env).")] = None,
    admin_user: Annotated[str | None, typer.Option("--admin-user")] = None,
    client_id: Annotated[str, typer.Option("--client-id")] = "dhis2-utils-local",
    redirect_uri: Annotated[str, typer.Option("--redirect-uri")] = DEFAULT_REDIRECT_URI,
    scope: Annotated[str, typer.Option("--scope")] = "ALL",
    display_name: Annotated[str | None, typer.Option("--name")] = None,
) -> None:
    """Register an OAuth2 client on DHIS2 via POST /api/oAuth2Clients.

    Secrets (admin credentials, client_secret) come from env or interactive
    prompt — never argv.

    Prints `client_id` + metadata UID so they can be piped into
    `d2w profile add --auth oauth2 ...`. For a one-shot bootstrap (register
    + save profile + log in) use `d2w profile bootstrap` instead.
    """
    resolved_url: str = url or os.environ.get("DHIS2_URL") or typer.prompt("DHIS2 base URL")
    admin_auth = resolve_admin_auth(admin_user)
    client_secret = os.environ.get("DHIS2_OAUTH_CLIENT_SECRET") or typer.prompt(
        f"New client_secret for {client_id!r}", hide_input=True
    )
    creds = asyncio.run(
        register_oauth2_client(
            base_url=resolved_url,
            admin_auth=admin_auth,
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            scope=scope,
            display_name=display_name,
        )
    )
    typer.echo(f"registered oauth2 client at {resolved_url}")
    typer.echo(f"  uid={creds.uid}")
    typer.echo(f"  client_id={creds.client_id}")
    typer.echo(f"  redirect_uri={creds.redirect_uri}")
    typer.echo(f"  scope={creds.scope}")
    typer.secho(
        "  client_secret not echoed — export as DHIS2_OAUTH_CLIENT_SECRET or use profile add", fg=typer.colors.YELLOW
    )
