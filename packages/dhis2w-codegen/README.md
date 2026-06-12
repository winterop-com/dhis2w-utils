# dhis2w-codegen

Version-aware DHIS2 client generator. Hits a live DHIS2 instance's `/api/schemas` and `/api/openapi.json`, emits pydantic models + `StrEnum`s + typed CRUD accessors into `packages/dhis2w-client/src/dhis2w_client/generated/v{N}/`.

**Workspace-only** — not published to PyPI. The generated code is committed to `dhis2w-client` so PyPI consumers of the client don't need to run the generator. Install `dhis2w-codegen` only if you're working in the `dhis2w-utils` workspace and want to regenerate against a new DHIS2 instance / version.

## Subcommands

Mounted as `d2w dev codegen` when working from the workspace.

- `d2w dev codegen generate --url <DHIS2> --username <u> --password <p>` — full flow against a live DHIS2. Discovers version from `/api/system/info`, fetches `/api/schemas`, emits into `generated/v{N}/`.
- `d2w dev codegen rebuild` — regenerate from the committed `schemas_manifest.json` (no network).
- `d2w dev codegen oas-rebuild [--version vN]` — re-emit `generated/v{N}/oas/` from the committed `openapi.json`.
- `d2w dev codegen diff <from> <to>` — structural diff between two committed manifests (e.g. `v42` vs `v43`). Surfaces schemas added, removed, and per-property type changes.

## Convenience targets

`make dhis2-codegen-play` regenerates v42 + v43 against `play.im.dhis2.org/dev-2-{42,43}` — the canonical sources. `make dhis2-codegen-all` spins up local docker stacks for every supported version in turn (~40 min).

## Architecture

`discover.py` fetches `/api/schemas` and normalises the response into a `SchemasManifest`. `emit.py` walks the manifest and renders one pydantic model file per schema via Jinja templates (in `templates/`). `oas_emit.py` does the same for the OpenAPI spec (instance-side shapes — tracker writes, envelopes, auth schemes). `diff.py` powers the cross-version diff command.

Spec patches (e.g. injecting auth-scheme discriminators that DHIS2 omits — see BUGS.md #14) live in `spec_patches.py` and apply during emission.

Full architecture: https://winterop-com.github.io/dhis2w-utils/codegen/.

`dhis2w-codegen` is one member of the [`dhis2w-utils`](https://github.com/winterop-com/dhis2w-utils) workspace.
