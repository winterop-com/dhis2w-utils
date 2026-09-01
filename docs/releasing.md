# Releasing to PyPI

The eleven publishable workspace members ship to PyPI in lockstep — every release tags every package at the same version. The internal `dhis2w-codegen` and `dhis2w-bench` packages are workspace-only and do not ship. `dhis2w-mcp-router` first ships in 1.2.0, `dhis2w-fhir` and `dhis2w-fhir-serve` in 1.5.0, and `dhis2w-fhir-engine` in 1.7.0; because each is new to PyPI, register its pending Trusted Publisher on pypi.org before that tag (see [First release of a new package](#first-release-of-a-new-package) below).

| Package | PyPI |
| --- | --- |
| `dhis2w-client` | https://pypi.org/project/dhis2w-client/ |
| `dhis2w-core` | https://pypi.org/project/dhis2w-core/ |
| `dhis2w-ql` | https://pypi.org/project/dhis2w-ql/ |
| `dhis2w-cli` | https://pypi.org/project/dhis2w-cli/ |
| `dhis2w-browser` | https://pypi.org/project/dhis2w-browser/ |
| `dhis2w-mcp` | https://pypi.org/project/dhis2w-mcp/ |
| `dhis2w-mcp-bridge` | https://pypi.org/project/dhis2w-mcp-bridge/ |
| `dhis2w-mcp-router` | https://pypi.org/project/dhis2w-mcp-router/ (from 1.2.0) |
| `dhis2w-fhir` | https://pypi.org/project/dhis2w-fhir/ (from 1.5.0) |
| `dhis2w-fhir-serve` | https://pypi.org/project/dhis2w-fhir-serve/ (from 1.5.0) |
| `dhis2w-fhir-engine` | https://pypi.org/project/dhis2w-fhir-engine/ (from 1.7.0) |

## Versioning policy

- **Lockstep.** All ten publishable packages share the same `version =` value in their `pyproject.toml`. Bump them together, never one at a time.
- **SemVer.** `MAJOR.MINOR.PATCH` for stable releases; pre-releases use SemVer suffixes (`0.6.0a1`, `0.6.0rc1`). Pre-1.0 means breaking changes can land on minor bumps.
- **Inter-package deps** are pinned to `>=<current>,<<next-major>` (e.g. `dhis2w-client>=0.5.0,<0.6`). When the next minor lands, every consumer's pin needs the same shift.

## How to cut a release

1. **Decide the version**: pick a SemVer next from the current `version =` in any `packages/*/pyproject.toml`. For 0.5.0 → 0.5.1 (patch), 0.5.0 → 0.6.0 (minor with possibly-breaking changes), 0.5.0 → 1.0.0 (committed stable surface).

2. **Bump every `packages/*/pyproject.toml`** in lockstep. Update both:
   - The package's own `version = "X.Y.Z"`.
   - Every workspace dep pin like `"dhis2w-core>=0.5.0,<0.6"`. The lower bound should match the new release; the upper bound shifts to the next major (`<0.6` → `<0.7` only on minor bumps, never on patch).

3. **Refresh the lockfile**:

   ```bash
   uv lock
   make lint && make test
   ```

4. **Commit the bump** with a short conventional-commit message — `chore(release): v0.6.0`.

5. **Tag the commit** and push (annotated — the repo's git config requires a tag message):

   ```bash
   git tag -a v0.6.0 -m v0.6.0
   git push origin main v0.6.0
   ```

6. **Watch the workflow**. The tag triggers `.github/workflows/pypi-publish.yml`. One `build` job per publishable member produces wheels in parallel; one `publish` job uploads them all via PyPI Trusted Publishing (OIDC, no API token), with `skip-existing` so a re-run after a partial publish is safe.

7. **Create the GitHub release** (the tag alone does not — the Releases page stays on the previous version otherwise). Write the notes by hand — grouped by user-visible theme, release voice — and pass them as a file. Never `--generate-notes`: an auto-generated PR list is not release notes.

   ```bash
   gh release create v0.6.0 --verify-tag --title v0.6.0 --notes-file notes.md --latest
   ```

8. **Verify**:
   - https://github.com/winterop-com/dhis2w-utils/actions — all green.
   - `uvx --refresh --from 'dhis2w-client==0.6.0' python -c 'import dhis2w_client; print(dhis2w_client.__file__)'` pulls and imports the new wheel.
   - `uv tool list` (or `uv tool upgrade dhis2w-cli`) shows the right version.

## Releasing from the terminal

`make publish-all` uploads every publishable member from the checkout in front of you, in
dependency order — `client`, `ql`, `core`, `browser`, `fhir`, `fhir-engine`, `fhir-serve`, `cli`,
`mcp`, `mcp-bridge`, `mcp-router` — so a resolver reading PyPI mid-release never meets a package
naming a sibling version the index has not seen yet. `make publish-<member>` does one of them:

```bash
export UV_PUBLISH_TOKEN=...   # a PyPI API token; both targets refuse to run without one
make ui           # or the dhis2w-fhir-serve wheel ships no capture UI
make publish-all
```

Each target builds the member's wheel and sdist with `uv build --package dhis2w-<member>` and
uploads that pair alone, removing the member's earlier artifacts from `dist/` first so a stale
version cannot ride along. `dhis2w-fhir-engine` has a target ahead of its first upload; it is not
in the tag workflow's matrix until its PyPI project exists.

This path and the tag are two ways to the same index, and the tag is the one to reach for: it
builds on a clean runner and authenticates with Trusted Publishing, no token on anyone's machine.

## First release of a new package

A brand-new `dhis2w-*` project does not exist on PyPI yet, and OIDC cannot create it from a
non-user identity. Before its first release, add a **pending publisher** on PyPI (one-time, web UI
only): https://pypi.org/manage/account/publishing/ → "Add a new pending publisher":

- PyPI Project Name: `dhis2w-<name>`
- Owner: `winterop-com` · Repository: `dhis2w-utils`
- Workflow filename: `pypi-publish.yml` · Environment: `pypi`

Without it, the `publish` job 400s on that wheel (`Non-user identities cannot create new projects`).
The siblings that sort earlier still upload, so the publish step is `skip-existing`: once the
pending publisher exists, re-run with `gh workflow run pypi-publish.yml -f version=<X.Y.Z>` and only
the missing package uploads.

## Pre-release flow

For dry runs without committing to a SemVer slot:

```bash
# In every pyproject.toml: version = "0.6.0a1"
git tag v0.6.0a1
git push origin v0.6.0a1
```

The workflow accepts the pre-release pattern and uploads as a pre-release to PyPI. Consumers get it only with `uv tool install dhis2w-cli --prerelease=allow` (or `uv add dhis2w-client --prerelease=allow` inside a project).

## Yanking a release

Don't delete published wheels — yank them instead. Yanking keeps the file available so existing pins still resolve, but new resolves skip it:

```bash
uv run twine yank dhis2w-client==0.6.0 --reason "broken release; use 0.6.1"
```

(Or do it through PyPI's web UI under each project's Manage page.)

## Major bumps (2.0 and beyond)

1.0.0 committed the public surface: the imported names from `dhis2w_client`, the `d2w` command
names and flags, and the MCP tool catalogue. Under SemVer, backward-compatible additions ship on
minor bumps and any breaking change to that surface requires a new major.
