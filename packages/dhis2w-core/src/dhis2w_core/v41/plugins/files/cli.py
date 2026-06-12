"""Typer sub-app for `d2w files` — documents + fileResources management."""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Annotated, Any

import typer
from dhis2w_client.v41 import FileResourceDomain
from rich.console import Console
from rich.table import Table

from dhis2w_core.profile import profile_from_env
from dhis2w_core.v41.cli_output import is_json_output
from dhis2w_core.v41.plugins.files import service

_console = Console()

documents_app = typer.Typer(
    help="DHIS2 /api/documents — user-uploaded attachments + external URL links.",
    no_args_is_help=True,
)

resources_app = typer.Typer(
    help="DHIS2 /api/fileResources — typed binary blobs (DATA_VALUE, ICON, MESSAGE_ATTACHMENT).",
    no_args_is_help=True,
)

app = typer.Typer(
    help="DHIS2 file management — documents + file resources.",
    no_args_is_help=True,
)
app.add_typer(documents_app, name="documents", help="Documents (/api/documents).")
app.add_typer(resources_app, name="resources", help="File resources (/api/fileResources).")


# ---- documents ------------------------------------------------------


@documents_app.command("list")
@documents_app.command("ls", hidden=True)
def documents_list_command(
    filter_expr: Annotated[
        str | None,
        typer.Option("--filter", help="DHIS2 filter, e.g. `name:like:Annual`."),
    ] = None,
    page: Annotated[int | None, typer.Option("--page", help="1-indexed page number.")] = None,
    page_size: Annotated[int | None, typer.Option("--page-size", help="Rows per page (default 50).")] = None,
    details: Annotated[
        bool,
        typer.Option(
            "--details",
            help=(
                "For each UPLOAD_FILE, also fetch the backing fileResource's "
                "contentType / size / storageStatus (one extra request per row)."
            ),
        ),
    ] = False,
) -> None:
    """List documents — external URL links and UPLOAD_FILE blobs.

    Pass `--details` to inline each UPLOAD_FILE's fileResource contentType / size /
    storageStatus. NOTE: `/api/documents` does not expose the fileResource UID, so details
    are only available where a document's `url` is itself an 11-char UID (older data); for
    filename-style `url`s the detail columns show `-`.
    """
    docs = asyncio.run(
        service.list_documents(profile_from_env(), filter=filter_expr, page=page, page_size=page_size),
    )
    if is_json_output():
        typer.echo("[" + ",".join(doc.model_dump_json(exclude_none=True) for doc in docs) + "]")
        return
    if not docs:
        typer.echo("no documents found")
        return

    fr_index: dict[str, Any] = {}
    if details:
        fr_uids = [
            doc.url
            for doc in docs
            if not doc.external and doc.url and re.fullmatch(r"[A-Za-z][A-Za-z0-9]{10}", doc.url)
        ]
        fr_index = asyncio.run(service.get_file_resources_bulk(profile_from_env(), fr_uids))

    table = Table(title=f"DHIS2 documents ({len(docs)})")
    table.add_column("id", style="cyan", no_wrap=True)
    table.add_column("type")
    table.add_column("name", overflow="fold")
    table.add_column("target", overflow="fold")
    if details:
        table.add_column("contentType", overflow="fold")
        table.add_column("size", justify="right")
        table.add_column("storage")
    for doc in docs:
        kind = "[blue]EXTERNAL_URL[/blue]" if doc.external else "[green]UPLOAD_FILE[/green]"
        target = doc.url or "-"
        row = [doc.id or "", kind, doc.name or "", target]
        if details:
            fr = fr_index.get(doc.url or "") if not doc.external else None
            if fr is None:
                row.extend(["-", "-", "-"])
            else:
                row.extend(
                    [
                        fr.contentType or "-",
                        _format_size(fr.contentLength),
                        _colorize_storage(fr.storageStatus),
                    ]
                )
        table.add_row(*row)
    _console.print(table)


def _format_size(num_bytes: int | None) -> str:
    """Human-readable byte size (KB / MB / GB)."""
    if num_bytes is None:
        return "-"
    if num_bytes < 1024:
        return f"{num_bytes} B"
    if num_bytes < 1024 * 1024:
        return f"{num_bytes / 1024:.1f} KB"
    if num_bytes < 1024 * 1024 * 1024:
        return f"{num_bytes / (1024 * 1024):.1f} MB"
    return f"{num_bytes / (1024 * 1024 * 1024):.1f} GB"


def _colorize_storage(status: str | None) -> str:
    """Color-code a fileResource's storageStatus (`STORED` green, `PENDING` yellow, others red)."""
    if not status:
        return "-"
    upper = status.upper()
    if upper == "STORED":
        return f"[green]{status}[/green]"
    if upper in ("PENDING", "UPLOADING"):
        return f"[yellow]{status}[/yellow]"
    return f"[red]{status}[/red]"


@documents_app.command("get")
def documents_get_command(uid: Annotated[str, typer.Argument(help="Document UID.")]) -> None:
    """Show metadata for one document."""
    doc = asyncio.run(service.get_document(profile_from_env(), uid))
    typer.echo(doc.model_dump_json(indent=2, exclude_none=True))


@documents_app.command("upload")
def documents_upload_command(
    file: Annotated[Path, typer.Argument(help="File to upload.")],
    name: Annotated[
        str | None,
        typer.Option("--name", help="Document name (defaults to filename)."),
    ] = None,
) -> None:
    """Upload a binary document — prints the new UID."""
    if not file.is_file():
        raise typer.BadParameter(f"{file} is not a file")
    doc = asyncio.run(service.upload_document(profile_from_env(), file, name=name))
    typer.echo(f"uploaded {doc.id}  {doc.name}")


@documents_app.command("upload-url")
def documents_upload_url_command(
    name: Annotated[str, typer.Argument(help="Document display name.")],
    url: Annotated[str, typer.Argument(help="External URL DHIS2 will link to.")],
) -> None:
    """Create an EXTERNAL_URL document — no bytes uploaded; DHIS2 links out to `url`."""
    doc = asyncio.run(service.create_external_document(profile_from_env(), name=name, url=url))
    typer.echo(f"created {doc.id}  {doc.name}  -> {url}")


@documents_app.command("download")
def documents_download_command(
    uid: Annotated[str, typer.Argument(help="Document UID.")],
    destination: Annotated[Path, typer.Argument(help="Output file path.")],
) -> None:
    """Download the binary payload to `destination`."""
    written = asyncio.run(service.download_document(profile_from_env(), uid, destination))
    typer.echo(f"wrote {written} bytes to {destination}")


@documents_app.command("delete")
def documents_delete_command(uid: Annotated[str, typer.Argument(help="Document UID.")]) -> None:
    """Delete one document."""
    asyncio.run(service.delete_document(profile_from_env(), uid))
    typer.echo(f"deleted {uid}")


# ---- file resources -------------------------------------------------


@resources_app.command("upload")
def resources_upload_command(
    file: Annotated[Path, typer.Argument(help="File to upload as a fileResource.")],
    domain: Annotated[
        FileResourceDomain,
        typer.Option(
            "--domain",
            help="FileResource domain (DATA_VALUE, ICON, MESSAGE_ATTACHMENT, ...).",
            case_sensitive=False,
        ),
    ] = FileResourceDomain.DATA_VALUE,
) -> None:
    """Upload a file resource; prints the new UID (reference it from the owning metadata object)."""
    if not file.is_file():
        raise typer.BadParameter(f"{file} is not a file")
    fr = asyncio.run(service.upload_file_resource(profile_from_env(), file, domain=domain))
    typer.echo(f"uploaded {fr.id}  domain={fr.domain}  name={fr.name}")


@resources_app.command("get")
def resources_get_command(uid: Annotated[str, typer.Argument(help="FileResource UID.")]) -> None:
    """Show metadata for one file resource."""
    fr = asyncio.run(service.get_file_resource(profile_from_env(), uid))
    typer.echo(fr.model_dump_json(indent=2, exclude_none=True))


@resources_app.command("download")
def resources_download_command(
    uid: Annotated[str, typer.Argument(help="FileResource UID.")],
    destination: Annotated[Path, typer.Argument(help="Output file path.")],
) -> None:
    """Download the file-resource payload to `destination`."""
    written = asyncio.run(service.download_file_resource(profile_from_env(), uid, destination))
    typer.echo(f"wrote {written} bytes to {destination}")


def register(parent_app: Any) -> None:
    """Mount `d2w files` on the root CLI."""
    parent_app.add_typer(app, name="files", help="Manage DHIS2 documents + file resources.")
