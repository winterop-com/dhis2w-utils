"""Typer sub-app for `d2w data` — mounts aggregate + tracker domain trees."""

from __future__ import annotations

from typing import Any

import typer


def register(root_app: Any) -> None:
    """Mount under `d2w data`."""
    from dhis2w_core.v43.plugins.aggregate import cli as aggregate_cli
    from dhis2w_core.v43.plugins.tracker import cli as tracker_cli

    app = typer.Typer(help="DHIS2 data values (aggregate + tracker).", no_args_is_help=True)
    app.add_typer(aggregate_cli.app, name="aggregate", help="Aggregate data values (dataValueSets).")
    app.add_typer(tracker_cli.app, name="tracker", help="Tracker (entities, enrollments, events, relationships).")
    root_app.add_typer(app, name="data", help="DHIS2 data values (aggregate + tracker).")
