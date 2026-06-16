# `d2w` CLI: step-by-step tutorial

> **Learning path · step 3 of 8** — Operator tutorial. Prev: [Walkthrough](../walkthrough.md). Next: [Python library tutorial](client-tutorial.md). For the full command catalogue see [CLI reference](../cli-reference.md); for runnable snippets per plugin see the [Examples index](../examples.md).

A narrative walkthrough of the `d2w` command-line interface aimed at day-to-day operators. The first sections (profile / metadata / analytics / users) take you through the most-used workflows; the later sections (maintenance / files / messaging / apps / tracker) round out coverage of every operator-facing plugin. Each block shows the exact command shape — replace placeholder UIDs (`<uid>`, `<group-uid>`, `ROLEuidHere`, `OUuidHere`, `abcdefghij`, etc.) with values from your DHIS2 instance.

For the exhaustive list of every command and flag, see the [CLI reference](../cli-reference.md). For runnable examples per topic, see the [examples index](../examples.md).

- [Prerequisites](#prerequisites)
- [Install + profile setup](#install-profile-setup)
- [Your first call: `whoami`](#your-first-call-whoami)
- [Inspecting metadata](#inspecting-metadata)
- [Changing metadata: patch vs import](#changing-metadata-patch-vs-import)
- [Cross-instance workflows: export + diff + import](#cross-instance-workflows-export-diff-import)
- [Running analytics + watching jobs](#running-analytics-watching-jobs)
- [Administering users + groups + roles](#administering-users-groups-roles)
- [Operating on background jobs: `d2w maintenance`](#operating-on-background-jobs-d2w-maintenance)
- [Working with files + documents: `d2w files`](#working-with-files-documents-d2w-files)
- [Messaging: `d2w messaging`](#messaging-d2w-messaging)
- [Apps + Routes + Browser: special-purpose plugins](#apps-routes-browser-special-purpose-plugins)
- [Tracker authoring: `d2w metadata tracked-entity-* / programs / program-stages`](#tracker-authoring-d2w-metadata-tracked-entity-programs-program-stages)
- [A note on tutorial coverage](#a-note-on-tutorial-coverage)
- [Probing instance health: `d2w doctor`](#probing-instance-health-d2w-doctor)
- [Global flags: `--profile` and `--debug`](#global-flags-profile-and-debug)
- [Where to go next](#where-to-go-next)

## Prerequisites

- Python 3.13+ with `uv` installed.
- A reachable DHIS2 instance (v41, v42, or v43). Local: `make dhis2-run` (starts DHIS2 + Postgres + seeds auth). Remote: your own install or one of the `https://play.im.dhis2.org/dev-2-{41,42,43}` instances.
- Credentials — a Personal Access Token (PAT), Basic auth, or OAuth2 client config. `make dhis2-run` writes PATs to `infra/home/credentials/.env.auth`.

## Install + profile setup

The CLI ships with every workspace member. From a checkout:

```bash
uv sync
source .venv/bin/activate   # so `d2w` resolves without `uv run` prefix
```

Profiles are how the CLI knows *where* to talk and *how* to authenticate. Create one that targets your local instance:

```bash
# Load the seeded PAT into env so it never hits argv or the TOML file
set -a; source infra/home/credentials/.env.auth; set +a

d2w profile add local --url http://localhost:8080 --auth pat --default --verify
```

The `--verify` flag makes a quick `/api/me` call so you know the profile works before you leave the command. `--default` marks this as the default so you can skip `--profile` on every call.

You can also target via env without a profile at all — the CLI will fall back to `DHIS2_URL` + `DHIS2_PAT` / `DHIS2_USERNAME` + `DHIS2_PASSWORD`.

Useful profile commands:

```bash
d2w profile list                          # show every registered profile
d2w profile verify                        # re-check the default profile
d2w --json profile verify local           # machine-readable verify
d2w profile show local                    # sanitised TOML dump (secrets redacted)
```

## Your first call: `whoami`

Prove the profile works:

```bash
d2w system whoami
# admin (admin admin)

d2w system info
# version: 2.42.4
# revision: abc1234
# systemName: DHIS2 Play
# ...
```

Every subsequent command reuses the same profile resolution.

## Inspecting metadata

Metadata is DHIS2's term for the "dictionary" — data elements, indicators, datasets, organisation units, programs, etc. List the resource types the instance exposes:

```bash
d2w metadata type list
# aggregateDataExchanges
# analyticsTableHooks
# ...
# 139 types available
```

List instances of any type, with the full DHIS2 query surface:

```bash
# Top 5 by name
d2w metadata list dataElements --order "name:asc" --page-size 5

# Filter (repeatable, AND by default):
d2w metadata list dataElements \
  --filter "valueType:eq:INTEGER_POSITIVE" \
  --filter "domainType:eq:AGGREGATE"

# OR multiple filters:
d2w metadata list dataElements \
  --filter "name:like:Penta" --filter "code:eq:DE_PENTA1" --root-junction OR

# Dump the whole catalog server-side (no paging):
d2w metadata list indicators --all --fields ":identifiable"
```

Fetch a single object:

```bash
d2w metadata get dataElements fClA2Erf6IO
# ┌────────────────────┬─────────────────────────────────┐
# │ id                 │ fClA2Erf6IO                     │
# │ name               │ Penta1 doses given              │
# │ shortName          │ PENTA1                          │
# │ valueType          │ INTEGER_POSITIVE                │
# │ ...                │ ...                             │
# └────────────────────┴─────────────────────────────────┘

# JSON for debugging / piping:
d2w --json metadata get dataElements fClA2Erf6IO | jq '.valueType'
```

For library-code use, see `examples/v42/client/list_data_elements.py` — same result through the Python typed accessor.

## Changing metadata: patch vs import

**Patch** is for targeted, single-object updates — change a name or toggle a flag. It uses RFC 6902 JSON Patch, so it's surgical:

```bash
# Inline: replace + remove in one call. Values JSON-decode automatically.
d2w metadata patch dataElements fClA2Erf6IO \
  --set '/description=Updated via CLI' \
  --set '/zeroIsSignificant=false' \
  --remove '/legacyField'

# File-based for full RFC 6902 expressiveness:
cat > patch.json <<'JSON'
[
  {"op": "replace", "path": "/name", "value": "New name"},
  {"op": "copy", "path": "/shortName", "from": "/name"},
  {"op": "test", "path": "/valueType", "value": "INTEGER"}
]
JSON
d2w metadata patch dataElements fClA2Erf6IO --file patch.json
```

**Import** is for bulk metadata — upload a whole bundle at once, typically after editing an exported file. Use the `--dry-run` flag to preview:

```bash
d2w metadata import bundle.json --dry-run        # preview: parses + validates, nothing persists
d2w metadata import bundle.json                  # real import
```

See [metadata plugin docs](../architecture/metadata-plugin.md) for every import flag (`--strategy`, `--atomic-mode`, `--identifier`, etc.) mapped to DHIS2's wire-level options.

## Cross-instance workflows: export + diff + import

The canonical "copy metadata from A to B" pattern:

```bash
# 1. Export a filtered slice from profile A. `:owner` is DHIS2's own full-fidelity selector.
d2w --profile staging metadata export \
  --resource dataElements --resource indicators \
  --filter "dataElements:name:like:Penta" \
  --output anc-bundle.json

# 2. Check what's dangling — references to UIDs not in the bundle.
#    (The export already warned you; this is just inspection.)
cat anc-bundle.json | jq '.dataElements[0].categoryCombo'

# 3. Diff against the target before committing anything.
d2w --profile prod metadata diff anc-bundle.json --live --show-uids

# 4. Dry-run import on the target to catch server-side validation issues.
d2w --profile prod metadata import anc-bundle.json --dry-run

# 5. Real import.
d2w --profile prod metadata import anc-bundle.json
```

`metadata diff` also works bundle-vs-bundle (both positional args) for comparing two exports without hitting DHIS2 at all.

The full pipeline is in `examples/v42/cli/metadata_round_trip.sh` — the script applies a jq transformation between export and import, showing the story end-to-end.

## Running analytics + watching jobs

DHIS2 analytics lives in pre-computed tables. Refresh them + query:

```bash
# Refresh in the background (takes minutes on a full instance)
d2w maintenance refresh analytics

# Refresh and block until done, streaming progress:
d2w maintenance refresh analytics --watch

# Query aggregated analytics:
d2w analytics query \
  --dimension "dx:fClA2Erf6IO" \
  --dimension "pe:LAST_12_MONTHS" \
  --dimension "ou:ImspTQPwCqd"

# Outlier detection on a data scope:
d2w analytics outlier-detection \
  --data-set BfMAe6Itzgt --org-unit PMa2VCrupOd --algorithm MODIFIED_Z_SCORE
```

`--watch` is the standard pattern for any DHIS2 command that kicks off a background job. It polls DHIS2's `/api/system/tasks/<type>/<uid>` and renders a Rich progress bar until the job completes or errors. Same flag works on `maintenance dataintegrity run --watch` and other slow operations.

> **CSV / XML / XLSX output**: the CLI's `analytics query` returns JSON. The library-level [`client.analytics.stream_to(Path, ...)`](../api/analytics-stream.md) supports `.csv`, `.xml`, `.xlsx` format overrides — wire those through a small Python script when you need a non-JSON shape. The [Analytics plugin architecture](../architecture/analytics.md#not-yet-exposed) page lists this under "Not yet exposed" as a CLI surface to fill in.

## Administering users + groups + roles

Read and write the user surface:

```bash
# Read
d2w user list --filter "disabled:eq:false" --page-size 10
d2w user get admin                                    # by username
d2w system whoami                                           # the authenticated user
d2w --json system whoami                                    # full /api/me payload

# Invite a new user (DHIS2 emails them a signup link)
d2w user invite new.user@example.com \
  --first-name New --surname User \
  --user-role ROLEuidHere \
  --org-unit OUuidHere

# Password reset (mails the user a link)
d2w user reset-password <uid>
```

Groups and roles have their own plugins:

```bash
# User groups
d2w user group list
d2w user group add-member <group-uid> <user-uid>
d2w user group sharing-grant-user <group-uid> <user-uid> --metadata-write

# User roles (authorities, not DHIS2's "roles" = groups)
d2w user role list
d2w user role authority-list <role-uid>           # inspect which authorities the role grants
d2w user role add-user <role-uid> <user-uid>      # grant role to user
```

## Operating on background jobs: `d2w maintenance`

DHIS2's analytics tables, predictors, data-integrity scans, and cache maintenance all run as async server-side jobs. The maintenance plugin wraps the trigger + polling pair:

```bash
# Trigger analytics-table regeneration; --watch polls notifications until done
d2w maintenance refresh analytics --watch

# Validation-rule run on an org-unit subtree
d2w maintenance validation run ImspTQPwCqd \
    --start-date 2024-01-01 --end-date 2024-06-30 \
    --group VrGImmun001 --persist

# Data-integrity scan (DHIS2's built-in 81-check suite)
d2w maintenance dataintegrity run --watch

# Predictor runs (synthetic data values from historical data)
d2w maintenance predictors run --start-date 2024-04-01 --end-date 2024-06-30

# Clear server-side caches after a metadata change
d2w maintenance cache-clear
```

`--watch` (or `-w`) is the universal "stream notifications until done" flag — see [Polling long-running tasks](../architecture/cli.md#polling-long-running-tasks-watch). Without it, the command returns the moment DHIS2 queues the job; with it, you see a rich spinner + per-stage progress lines until the job hits a terminal status.

## Working with files + documents: `d2w files`

The `files` plugin spans two DHIS2 surfaces — `Document` metadata (URL or binary) and `FileResource` (the upload-and-attach-later flow for messages and data values):

```bash
# List + filter documents
d2w files documents list --filter 'external:eq:true'

# Create an external-URL document (no upload — DHIS2 just links out)
d2w files documents upload-url "Country health plan" https://example.org/plan.pdf

# Upload a binary into the FileResource store (for MESSAGE_ATTACHMENT, data value images, etc.).
# Domain comes from the file's intended use; the CLI prints the new resource UID.
d2w files resources upload ./report.pdf --domain MESSAGE_ATTACHMENT
```

The CLI does the DHIS2 two-step (create file resource → reference its UID from the owning metadata) under the hood: you pass a local path, you get back the UID ready to attach to a message / data value / document.

## Messaging: `d2w messaging`

`/api/messageConversations` with the full ticket-workflow fields (status, priority, assignee):

```bash
d2w messaging list --status OPEN

# `send` takes SUBJECT TEXT positionally + recipient flag(s).
d2w messaging send "Audit ping" "Please confirm..." --user abcdefghij

# `reply` takes the conversation UID + the text positionally (DHIS2's reply endpoint is plain-text-only).
d2w messaging reply <conversation-uid> "Confirmed."

# `set-status` takes UID + status (NONE / OPEN / PENDING / INVALID / SOLVED) positionally.
d2w messaging set-status <conversation-uid> SOLVED
```

Attachments take a `FileResource` UID from `d2w files resources upload` and attach via the `send` flow (see above).

## Apps + Routes + Browser: special-purpose plugins

Three plugins worth knowing by name even if you don't use them daily:

- **`d2w apps`** — `/api/apps` + App Hub catalogue. `d2w apps list` enumerates installed apps; `d2w apps add <source>` installs (the `source` arg auto-dispatches between a local `.zip` path, an App Hub version id, and an App Hub app id — an app id resolves to the app's latest version); `d2w apps update --all` refreshes every hub-managed install. Useful for keeping an instance's app footprint reproducible.
- **`d2w route`** — `/api/routes` integration proxies (DHIS2's outbound-HTTP feature for hitting other systems). CRUD over routes plus `d2w route run <uid>` to invoke one.
- **`d2w browser`** — Playwright-driven UI automation. `d2w browser pat` mints a Personal Access Token via the DHIS2 UI as an admin (handy for bootstrapping CI); `d2w browser viz screenshot` + `d2w browser map screenshot` capture PNGs of dashboards. Requires the `[browser]` extra (`uv tool install 'dhis2w-cli[browser]'`).

## Tracker authoring: `d2w metadata tracked-entity-* / programs / program-stages`

Programs, ProgramStages, TrackedEntityTypes, and TrackedEntityAttributes are full first-party authoring sub-apps under `d2w metadata` (plural sub-app names — matches the rest of the authoring triples):

```bash
d2w metadata tracked-entity-types create --name "Person" --short-name "Person"
d2w metadata tracked-entity-attributes create --name "Given name" --short-name "Given name" --value-type TEXT
d2w metadata tracked-entity-types add-attribute <tet-uid> <tea-uid>

d2w metadata programs create --name "ANC" --short-name "ANC" \
    --program-type WITH_REGISTRATION --tracked-entity-type <tet-uid>
d2w metadata programs add-attribute <program-uid> <tea-uid> --searchable --mandatory
d2w metadata program-stages create --program <program-uid> --name "Initial visit"
```

End-to-end demos: `examples/v42/cli/tracker_schema.sh` (TET + TEA wiring), `examples/v42/cli/tracker_programs.sh` (Program + PTEA), `examples/v42/cli/tracker_program_stages.sh` (ProgramStage + PSDE).

## A note on tutorial coverage

This tutorial walks operator workflows: profile setup, metadata reads + writes, analytics, users, maintenance, files, messaging, apps, route, browser, tracker authoring, doctor, global flags. Every other plugin command + flag combination — the long tail of search axes, the v43-only setters, the data-import flags, every authoring triple's edge cases — is in [CLI reference](../cli-reference.md). Treat this guide as the on-ramp and the auto-generated reference as the authoritative surface.

## Probing instance health: `d2w doctor`

One read-only command, roughly 100 checks — 20 metadata-health probes + 81 DHIS2 data-integrity checks + every BUGS.md tripwire. Run it on any DHIS2 instance before integrating with it:

```bash
d2w doctor                            # all probes; fail on any fail/warn
d2w doctor --category metadata        # just the metadata probes
d2w doctor --category integrity       # DHIS2's built-in data-integrity scan
d2w doctor --category bugs            # known-bug tripwires only
d2w doctor --slow                     # include the isSlow DHIS2 checks (full coverage)
d2w --json doctor                     # machine-readable output for CI
```

Use it in CI as a gate before running migrations or imports — non-zero exit when there are any `fail` probes. See [doctor plugin](../architecture/doctor-plugin.md) for the full probe list.

## Global flags: `--profile` and `--debug`

Two flags on the root `d2w` app (**before** the subcommand):

```bash
# Override the active profile for one call
d2w --profile prod metadata list dataElements

# Short form
d2w -p staging user list
```

```bash
# Verbose HTTP trace on stderr — method, URL, status, bytes, elapsed
d2w -d system whoami
# 10:54:05  dhis2w_client.http         GET http://localhost:8080/api/system/info -> 200 (2165 bytes, 9ms)
# 10:54:05  dhis2w_client.http         GET http://localhost:8080/api/me -> 200 (2760 bytes, 17ms)
# admin (admin admin)
```

Debug output lands on stderr so stdout stays pipe-friendly — you can still `d2w --json -d metadata list dataElements > out.json` and get clean JSON.

## Where to go next

- **Full command reference**: [CLI reference](../cli-reference.md) — every subcommand, every flag, auto-generated from the Typer app so it never drifts.
- **Runnable examples**: [examples index](../examples.md) — the canonical v42 set (~55 CLI + ~73 client + ~40 MCP scripts). v41 and v43 mirror most of them.
- **Library usage**: [`dhis2w-client` tutorial](client-tutorial.md) — when you want to drive DHIS2 from Python instead of the shell.
- **Plugin architecture**: [overview](../architecture/overview.md) — how plugins, profiles, auth providers, and codegen fit together.

The CLI is intentionally thin — every command ends up in a plugin's `service.py`, and the same service layer is what the FastMCP server exposes as tools. If you find the CLI missing a flag you expect, it's almost always a service-layer parameter that just needs wiring to a Typer option — see `packages/dhis2w-core/src/dhis2w_core/v42/plugins/<plugin>/cli.py` for the pattern.
