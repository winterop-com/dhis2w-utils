"""`dhis2 dev pat` — provision DHIS2 Personal Access Tokens via admin auth."""

from __future__ import annotations

import asyncio
import os
from typing import Annotated

import typer

from dhis2w_core.v41.admin_auth import resolve_admin_auth
from dhis2w_core.v41.pat_registration import register_pat

app = typer.Typer(help="Personal Access Tokens — provision PATs on DHIS2.", no_args_is_help=True)


@app.command("create")
def pat_create_command(
    url: Annotated[str | None, typer.Option("--url", help="DHIS2 base URL (also: DHIS2_URL env).")] = None,
    admin_user: Annotated[str | None, typer.Option("--admin-user")] = None,
    description: Annotated[str | None, typer.Option("--description")] = None,
    expires_in_days: Annotated[int | None, typer.Option("--expires-in-days")] = None,
    allowed_ip: Annotated[
        list[str] | None,
        typer.Option("--allowed-ip", help="IP allowlist entry; repeat for multiple."),
    ] = None,
    allowed_method: Annotated[
        list[str] | None,
        typer.Option("--allowed-method", help="HTTP method allowlist; repeat for each method."),
    ] = None,
    allowed_referrer: Annotated[
        list[str] | None,
        typer.Option("--allowed-referrer", help="Referer allowlist entry; repeat for multiple."),
    ] = None,
    quiet: Annotated[
        bool,
        typer.Option("--quiet", "-q", help="Print only the PAT value, suitable for $(command substitution)."),
    ] = False,
) -> None:
    """Create a DHIS2 Personal Access Token via POST /api/apiToken.

    Admin creds come from env or prompt (never argv). The PAT value is only
    returned once by DHIS2 — capture it here and pipe into a profile:

        export DHIS2_PAT=$(dhis2 dev pat create --url $URL -q)
        dhis2 profile add local --url $URL --auth pat

    Or use `dhis2 profile bootstrap --auth pat` for a one-shot setup.
    """
    resolved_url: str = url or os.environ.get("DHIS2_URL") or typer.prompt("DHIS2 base URL")
    admin_auth = resolve_admin_auth(admin_user)
    creds = asyncio.run(
        register_pat(
            base_url=resolved_url,
            admin_auth=admin_auth,
            description=description,
            expires_in_days=expires_in_days,
            allowed_ips=allowed_ip,
            allowed_methods=allowed_method,
            allowed_referrers=allowed_referrer,
        )
    )
    if quiet:
        typer.echo(creds.token)
    else:
        typer.echo(f"registered PAT at {resolved_url}")
        typer.echo(f"  uid={creds.uid}")
        if creds.description:
            typer.echo(f"  description={creds.description}")
        typer.echo(f"  token={creds.token}")
        typer.secho(
            "  this value is shown ONCE by DHIS2 — save it now (export DHIS2_PAT=... or profile add)",
            fg=typer.colors.YELLOW,
        )
