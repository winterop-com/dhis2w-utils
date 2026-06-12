"""`d2w dev uid` — mint fresh DHIS2 UIDs client-side (offline, CSPRNG)."""

from __future__ import annotations

from typing import Annotated

import typer
from dhis2w_client.v43 import generate_uids

app = typer.Typer(help="Generate 11-char DHIS2 UIDs.", invoke_without_command=True)


@app.callback(invoke_without_command=True)
def uid_command(
    count: Annotated[
        int,
        typer.Option("--count", "-n", min=1, max=10000, help="How many UIDs to generate."),
    ] = 1,
) -> None:
    """Generate fresh 11-char DHIS2 UIDs — one per line. Offline, no DHIS2 call needed."""
    for code in generate_uids(count):
        typer.echo(code)
