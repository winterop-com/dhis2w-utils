# Workspace layout

The repo is a `uv` workspace with a virtual root (the root `pyproject.toml` has no `[project]`, only `[tool.uv.workspace]`). Every shippable unit of code is its own member under `packages/`.

## Why a workspace instead of one package

Three reasons:

- **`dhis2w-client` has to be publishable on its own.** A single-package layout would force PyPI users of the client to pull in Typer, FastMCP, Playwright — none of which they need. A workspace lets us ship the client lean.
- **CLI and MCP shouldn't be the same install.** A server running `dhis2w-mcp` in a Docker image doesn't need the CLI's Typer tree. A developer running `d2w` locally doesn't need the MCP stdio loop. Separate members, separate wheels.
- **New surfaces land cleanly.** A new HTTP surface is a new folder, not a conditional import inside an existing package. `dhis2w-fhir-serve` is the worked example: `d2w fhir serve` needs FastAPI and uvicorn, `dhis2w-fhir` generates a file tree and needs neither, so the server is its own member and an API-only install of the generator stays free of both.

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
    ├── dhis2w-client/             # httpx + pydantic lib + Profile + open_client (PAT/Basic/session) (PyPI)
    ├── dhis2w-core/               # TOML profile resolution + OAuth2 token store + plugin runtime + plugins (PyPI)
    ├── dhis2w-ql/                 # d2ql query + transform engine, FHIRPath-compatible expression core (PyPI)
    ├── dhis2w-cli/                # Typer console script `d2w` (PyPI)
    ├── dhis2w-mcp/                # FastMCP server (PyPI)
    ├── dhis2w-mcp-bridge/         # single-tool MCP bridge for small local models (PyPI)
    ├── dhis2w-browser/            # Playwright helpers (PyPI)
    ├── dhis2w-codegen/            # generator — registers `d2w dev codegen` subcommand (workspace-only)
    ├── dhis2w-bench/              # local-LLM benchmark harness (workspace-only)
    ├── dhis2w-mcp-router/         # domain-neutral MCP search + dispatch router (ships from 1.2.0)
    ├── dhis2w-fhir/               # FHIR IG generation plugin — mounts `d2w fhir` (ships from 1.5.0)
    └── dhis2w-fhir-serve/         # FastAPI FHIR facade behind `d2w fhir serve` (ships from 1.5.0)
```

## Configuration split

All lint/type/test tooling (ruff, mypy, pyright, pytest, coverage) is configured **once** at the workspace root. Members inherit these settings automatically — no per-member `ruff.toml` or duplicated mypy stanzas.

Each member's `pyproject.toml` has just:

- `[project]` — name, version, description, Python floor, dependencies
- `[project.scripts]` — console entrypoints (only `dhis2w-cli` and `dhis2w-mcp`)
- `[project.entry-points."dhis2.plugins"]` — plugin registration (for `dhis2w-codegen` and future plugin packages)
- `[build-system]` — `uv_build` backend

## Build + publish

`make build` produces wheels for all members. PyPI publishing is automated — tag a `vX.Y.Z` and `.github/workflows/pypi-publish.yml` builds + uploads every publishable member via PyPI Trusted Publishing (OIDC). Ten members ship: `dhis2w-client`, `dhis2w-core`, `dhis2w-ql`, `dhis2w-cli`, `dhis2w-mcp`, `dhis2w-mcp-bridge`, `dhis2w-browser`, `dhis2w-mcp-router` (the MCP search + dispatch router, first published in 1.2.0), `dhis2w-fhir` (the FHIR IG generation plugin, first published in 1.5.0), and `dhis2w-fhir-serve` (the FHIR facade behind `d2w fhir serve`, first published in 1.5.0 and installed through the `dhis2w-cli[serve]` extra). Two stay workspace-only: `dhis2w-codegen` (a developer tool that emits committed code into `dhis2w-client`'s tree) and `dhis2w-bench` (the local-LLM benchmark harness). See [Releasing to PyPI](../releasing.md) for the full bump-and-tag flow.

## Open questions

- **Docs per-member or one site?** Currently one site. If per-member doc surfaces grow significantly, we may split to one mkdocs config per member stitched together, but starting unified is simpler.
