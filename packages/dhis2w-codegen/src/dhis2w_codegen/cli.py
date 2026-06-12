"""Typer sub-app for `dhis2w-codegen` — also mounted under `d2w codegen`."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated

import typer
from dhis2w_client import AuthProvider, BasicAuth, PatAuth
from rich.console import Console

from dhis2w_codegen.diff import diff_manifest_paths, render_text
from dhis2w_codegen.discover import SchemasManifest, discover
from dhis2w_codegen.emit import emit
from dhis2w_codegen.oas_emit import emit_from_openapi

app = typer.Typer(help="Generate version-aware DHIS2 client code from /api/schemas.", no_args_is_help=True)
_console = Console()


@app.command("generate")
def generate(
    url: Annotated[str, typer.Option("--url", help="Base URL of the DHIS2 instance.")],
    username: Annotated[str | None, typer.Option("--username", help="Basic-auth username.")] = None,
    password: Annotated[str | None, typer.Option("--password", help="Basic-auth password.")] = None,
    pat: Annotated[str | None, typer.Option("--pat", help="Personal Access Token.")] = None,
    output_root: Annotated[
        Path | None,
        typer.Option(
            "--output-root",
            help="Directory containing versioned subfolders; defaults to dhis2w-client's generated/ folder.",
        ),
    ] = None,
) -> None:
    """Generate the client for the DHIS2 version reported by `--url`."""
    auth: AuthProvider
    if pat:
        auth = PatAuth(token=pat)
    elif username and password:
        auth = BasicAuth(username=username, password=password)
    else:
        raise typer.BadParameter("provide either --pat or --username + --password")

    target_root = output_root or _default_output_root()
    asyncio.run(_run(url=url, auth=auth, output_root=target_root))


async def _run(*, url: str, auth: AuthProvider, output_root: Path) -> None:
    _console.print(f"[bold]discovering[/bold] {url}")
    manifest = await discover(url, auth)
    destination = output_root / manifest.version_key
    _console.print(f"  version: {manifest.raw_version} (→ {manifest.version_key})")
    _console.print(f"  schemas: {len(manifest.schemas)}")
    _console.print(f"[bold]emitting[/bold] {destination}")
    emit(manifest, destination)
    _console.print(f"[green]done[/green] — generated {len(manifest.schemas)} schemas into {destination}")


@app.command("rebuild")
def rebuild(
    manifest_path: Annotated[
        Path | None,
        typer.Option(
            "--manifest",
            help="Path to a committed schemas_manifest.json. Defaults to every version under the generated root.",
        ),
    ] = None,
    output_root: Annotated[
        Path | None,
        typer.Option("--output-root", help="Directory of versioned subfolders; defaults to dhis2w-client generated/."),
    ] = None,
) -> None:
    """Regenerate the client from saved schemas_manifest.json files (no network).

    Useful after touching emit.py / templates when you want every committed
    version refreshed without spinning up a live DHIS2 for each. If `--manifest`
    is omitted, walks the output root and rebuilds each version whose
    schemas_manifest.json is checked in.
    """
    target_root = output_root or _default_output_root()
    if manifest_path is not None:
        manifests = [manifest_path]
    else:
        manifests = sorted(target_root.glob("v*/schemas_manifest.json"))
        if not manifests:
            raise typer.BadParameter(f"no schemas_manifest.json found under {target_root}")
    for path in manifests:
        manifest = SchemasManifest.model_validate_json(path.read_text(encoding="utf-8"))
        destination = target_root / manifest.version_key
        _console.print(f"[bold]rebuilding[/bold] {manifest.version_key} from {path.name}")
        emit(manifest, destination)
        _console.print(f"[green]  done[/green] — {len(manifest.schemas)} schemas -> {destination}")


def _default_output_root() -> Path:
    """Locate `packages/dhis2w-client/src/dhis2w_client/generated/` relative to this file."""
    here = Path(__file__).resolve()
    repo_root = here
    for _ in range(6):
        repo_root = repo_root.parent
        candidate = repo_root / "packages" / "dhis2w-client" / "src" / "dhis2w_client" / "generated"
        if candidate.exists():
            return candidate
    raise RuntimeError("could not locate dhis2w-client generated/ directory; pass --output-root explicitly")


@app.command("oas-rebuild")
def oas_rebuild(
    version_key: Annotated[
        str | None,
        typer.Option("--version", help="Version key (e.g. v42). Defaults to every committed version."),
    ] = None,
    output_root: Annotated[
        Path | None,
        typer.Option("--output-root", help="Directory of versioned subfolders; defaults to dhis2w-client generated/."),
    ] = None,
) -> None:
    """Emit OpenAPI-derived pydantic models into `generated/v{N}/oas/`.

    Reads the committed `openapi.json` + `schemas_manifest.json` from each
    version directory (no network). Output lands alongside the `/api/schemas`
    emitter's output under `schemas/`.
    """
    target_root = output_root or _default_output_root()
    candidates: list[Path] = [target_root / version_key] if version_key else sorted(target_root.glob("v*"))
    for version_dir in candidates:
        openapi_path = version_dir / "openapi.json"
        manifest_path = version_dir / "schemas_manifest.json"
        if not openapi_path.exists():
            _console.print(f"[yellow]skip[/yellow] {version_dir.name}: no openapi.json")
            continue
        raw_version = ""
        if manifest_path.exists():
            raw_version = SchemasManifest.model_validate_json(manifest_path.read_text(encoding="utf-8")).raw_version
        _console.print(f"[bold]oas-rebuilding[/bold] {version_dir.name} from openapi.json")
        result = emit_from_openapi(
            openapi_path,
            version_dir,
            version_key=version_dir.name,
            raw_version=raw_version,
        )
        _console.print(
            f"[green]  done[/green] — {result.components_emitted}/{result.components_total} components "
            f"({result.enums_count} enums, {result.aliases_count} aliases, {result.objects_count} classes)"
        )


@app.command("diff")
def diff_cmd(
    from_version: Annotated[str, typer.Argument(help="Source version key (e.g. v42).")],
    to_version: Annotated[str, typer.Argument(help="Target version key (e.g. v43).")],
    output_root: Annotated[
        Path | None,
        typer.Option("--output-root", help="Directory of versioned subfolders; defaults to dhis2w-client generated/."),
    ] = None,
    json_output: Annotated[
        bool, typer.Option("--json", help="Emit a JSON dump instead of the human-readable report.")
    ] = False,
) -> None:
    """Diff two committed `schemas_manifest.json` files and report drift.

    Lists schemas added, removed, and per-property changes (type, klass,
    bounds, owner/required/etc). Useful for spotting upstream API drift
    when bumping DHIS2 majors.
    """
    target_root = output_root or _default_output_root()
    before_path = target_root / from_version / "schemas_manifest.json"
    after_path = target_root / to_version / "schemas_manifest.json"
    if not before_path.exists():
        raise typer.BadParameter(f"no manifest at {before_path}")
    if not after_path.exists():
        raise typer.BadParameter(f"no manifest at {after_path}")
    diff = diff_manifest_paths(before_path, after_path)
    if json_output:
        typer.echo(diff.model_dump_json(indent=2))
    else:
        typer.echo(render_text(diff))


if __name__ == "__main__":
    app()
