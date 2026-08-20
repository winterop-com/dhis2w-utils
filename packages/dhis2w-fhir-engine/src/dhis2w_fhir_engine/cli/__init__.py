"""Command line interface for FHIRPath, CQL, and ELM."""

import typer

from .cql import app as cql_app
from .elm import app as elm_app
from .fhirpath import app as fhirpath_app

app = typer.Typer(
    name="d2w-fhir-engine",
    help="FHIRPath, CQL, and ELM parsing, analysis, and evaluation.",
    no_args_is_help=True,
)
app.add_typer(fhirpath_app, name="fhirpath")
app.add_typer(cql_app, name="cql")
app.add_typer(elm_app, name="elm")

__all__ = ["app"]
