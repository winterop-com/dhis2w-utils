# Workspace layout

The repo is a `uv` workspace with a virtual root (the root `pyproject.toml` has no `[project]`, only `[tool.uv.workspace]`). Every shippable unit of code is its own member under `packages/`.

## Why a workspace instead of one package

Three reasons:

- **`dhis2w-client` has to be publishable on its own.** A single-package layout would force PyPI users of the client to pull in Typer, FastMCP, Playwright — none of which they need. A workspace lets us ship the client lean.
- **CLI and MCP shouldn't be the same install.** A server running `dhis2w-mcp` in a Docker image doesn't need the CLI's Typer tree. A developer running `d2w` locally doesn't need the MCP stdio loop. Separate members, separate wheels.
- **New surfaces land cleanly.** A future FastAPI web UI or a TUI is a new folder, not a conditional import inside an existing package.

## Layout

```
dhis2w-utils/
├── pyproject.toml                # virtual workspace root + shared tool config
├── uv.lock                       # single workspace-wide lock
├── Makefile                      # drives install/lint/test/docs/build/publish
├── mkdocs.yml                    # docs config (claude theme, left-side nav)
├── CLAUDE.md                     # non-negotiable project rules
├── docs/                         # this site's source
├── site/                         # mkdocs output (gitignored)
├── examples/
└── packages/
    ├── dhis2w-client/             # httpx + pydantic lib + Profile + open_client (PAT/Basic) (PyPI)
    ├── dhis2w-core/               # TOML profile resolution + OAuth2 token store + plugin runtime + plugins (PyPI)
    ├── dhis2w-cli/                # Typer console script `d2w` (PyPI)
    ├── dhis2w-mcp/                # FastMCP server (PyPI)
    ├── dhis2w-browser/            # Playwright helpers (PyPI)
    └── dhis2w-codegen/            # generator — registers `d2w dev codegen` subcommand (workspace-only)
```

## Configuration split

All lint/type/test tooling (ruff, mypy, pyright, pytest, coverage) is configured **once** at the workspace root. Members inherit these settings automatically — no per-member `ruff.toml` or duplicated mypy stanzas.

Each member's `pyproject.toml` has just:

- `[project]` — name, version, description, Python floor, dependencies
- `[project.scripts]` — console entrypoints (only `dhis2w-cli` and `dhis2w-mcp`)
- `[project.entry-points."dhis2.plugins"]` — plugin registration (for `dhis2w-codegen` and future plugin packages)
- `[build-system]` — `uv_build` backend

## Build + publish

`make build` produces wheels for all members. PyPI publishing is automated — tag a `vX.Y.Z` and `.github/workflows/pypi-publish.yml` builds + uploads every publishable member via PyPI Trusted Publishing (OIDC). Six members ship: `dhis2w-client`, `dhis2w-core`, `dhis2w-cli`, `dhis2w-mcp`, `dhis2w-mcp-bridge`, `dhis2w-browser`. The seventh, `dhis2w-codegen`, stays workspace-only — it's a developer tool that emits committed code into `dhis2w-client`'s tree, with no value to PyPI consumers. See [Releasing to PyPI](../releasing.md) for the full bump-and-tag flow.

## Open questions

- **Docs per-member or one site?** Currently one site. If per-member doc surfaces grow significantly, we may split to one mkdocs config per member stitched together, but starting unified is simpler.
