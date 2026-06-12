"""Typer router for `d2w dev` — mounts each sub-module (uid, codegen, sample)."""

from __future__ import annotations

from typing import Any

import typer

from dhis2w_core.v42.plugins.dev import sample as sample_module
from dhis2w_core.v42.plugins.dev import uid as uid_module

app = typer.Typer(help="Developer/operator tools.", no_args_is_help=True)

# `dhis2w-codegen` is workspace-internal and not shipped to PyPI; gracefully
# omit the `d2w dev codegen` sub-app when it isn't installed (e.g. for
# users who `pip install dhis2w-cli` from PyPI without the workspace).
try:
    from dhis2w_codegen.cli import app as codegen_app
except ImportError:
    pass
else:
    app.add_typer(codegen_app, name="codegen", help="Generate version-aware DHIS2 client code from /api/schemas.")

app.add_typer(uid_module.app, name="uid")
app.add_typer(sample_module.app, name="sample")


def register(root_app: Any) -> None:
    """Mount under `d2w dev`."""
    root_app.add_typer(app, name="dev", help="Developer/operator tools.")
