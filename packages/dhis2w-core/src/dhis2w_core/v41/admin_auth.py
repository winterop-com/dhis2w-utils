"""Shared helper for the `dev` CLI — never-argv admin credential resolution."""

from __future__ import annotations

import os

import typer
from dhis2w_client.v41.auth.base import AuthProvider

from dhis2w_core.v41.oauth2_registration import build_admin_auth


def resolve_admin_auth(admin_user: str | None) -> AuthProvider:
    """Select admin creds from env + interactive prompt. NEVER accepts argv secrets.

    Resolution order:
      1. `DHIS2_ADMIN_PAT` env var -> PAT auth
      2. `DHIS2_ADMIN_PASSWORD` env var + `--admin-user` (or prompt) -> Basic auth
      3. Interactive confirm + prompts (hidden input) if nothing in env

    Secrets are never read from `argv` because CLI args leak into shell history.
    """
    admin_pat = os.environ.get("DHIS2_ADMIN_PAT")
    admin_pass = os.environ.get("DHIS2_ADMIN_PASSWORD")
    if not admin_pat and not admin_pass:
        if admin_user or typer.confirm("Bootstrap with username+password? (no = PAT)", default=True):
            if not admin_user:
                admin_user = typer.prompt("Admin username", default="admin")
            admin_pass = typer.prompt("Admin password", hide_input=True)
        else:
            admin_pat = typer.prompt("Admin PAT", hide_input=True)
    if admin_pass and not admin_user:
        admin_user = "admin"
    return build_admin_auth(pat=admin_pat, username=admin_user, password=admin_pass)
