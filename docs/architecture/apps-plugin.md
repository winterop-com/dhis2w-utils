# Apps plugin

`d2w apps` covers the two surfaces DHIS2 exposes for managing installed
web apps: the local `/api/apps` endpoint (every app the running instance
has loaded — bundled core apps, custom uploads, hub-installed) and the
remote `/api/appHub` proxy (DHIS2's catalog of community-published apps).

```
d2w apps {list,add,remove,update,reload,restore,snapshot,hub-list,hub-versions,hub-url}
```

MCP mirrors the read + state-changing tools as `apps_list`, `apps_get`,
`apps_install_from_file`, `apps_install_from_hub`, `apps_uninstall`,
`apps_update`, `apps_update_all`, `apps_reload`, `apps_snapshot`,
`apps_restore`, `apps_hub_list`, `apps_hub_versions`, `apps_hub_url_get`, `apps_hub_url_set`.

## The two surfaces

### `/api/apps`

Every web app currently loaded by the running DHIS2 instance — bundled
core apps (`bundled=True`, e.g. Data Entry, Maintenance), custom uploads,
and hub-installed apps. The plugin treats the three uniformly: bundled
apps keep their `app_hub_id`, the hub can overwrite a bundled copy in
place, and `apps update --all` surfaces newer hub versions for bundled
apps the same way it does for non-bundled.

```bash
# List everything installed (bundled + custom):
d2w apps list

# Install / replace from a local zip:
d2w apps add ./path/to/app.zip

# Install from the App Hub. The id is resolved against the catalog: a
# version id installs that exact version; an app id resolves to the app's
# latest version (both are bare UUIDs and easy to confuse — BUGS.md #46):
d2w apps add <version-uuid>
d2w apps add <app-uuid>

# Remove by app key (the folder name DHIS2 uses):
d2w apps remove <key>

# Force DHIS2 to re-read every app from disk (no version changes):
d2w apps reload
```

### `/api/appHub`

The community catalog. DHIS2 proxies the call server-side, so the CLI
hits the local instance — useful when the workstation can't reach the
public hub directly (corporate proxies, air-gapped fixtures pointed at a
mirror via `keyAppHubUrl`).

```bash
# List + filter the catalog (each row shows an app id + a version count):
d2w apps hub-list --search dashboard

# List every published version of one app (version / id / channel / DHIS2
# min->max), newest first. The id values are `apps add <id>` targets:
d2w apps hub-versions <app-id>

# Read / write the keyAppHubUrl system setting (point at a self-hosted hub):
d2w apps hub-url
d2w apps hub-url --set https://hub.example.org
```

## Update workflow

`d2w apps update --all` is the one non-trivial bit of logic. The
service walks every installed app, matches each to a hub catalog entry
via `app_hub_id`, picks the version with the highest numeric semver,
and either installs it (if newer than the local version) or marks the
app `UP_TO_DATE` / `SKIPPED` / `FAILED`. The CLI renders the resulting
`UpdateSummary` as a Rich table:

```
key       name            from    to      status
analytics Analytics       2.34.1  2.35.0  UPDATED
appstore  App Management  2.30.0  2.30.0  UP_TO_DATE
custom    Side-loaded     1.0     -       SKIPPED  (no app_hub_id)
broken    Broken Hub App  1.0     2.0     FAILED   (HTTP 500)
```

`--dry-run` runs the same walk but reports `AVAILABLE` instead of
installing — useful to preview what `--all` would do.

## Snapshot / restore

`apps snapshot` writes a typed `AppsSnapshot` JSON manifest of every
installed app to a file, recording `key`, `version`, and `app_hub_id` for
each. `apps restore <manifest>` reinstalls every hub-backed entry via
`install_from_hub` — bundled and side-loaded apps are skipped because
they aren't reproducible from the hub.

The manifest is portable: take a snapshot from one DHIS2 instance,
restore on another to mirror the app inventory. Useful for promoting
staging → prod without round-tripping every zip.

```bash
d2w apps snapshot --output snapshot.json
d2w apps restore snapshot.json --dry-run    # preview
d2w apps restore snapshot.json              # apply
```

## Library API

```python
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import profile_from_env

async with open_client(profile_from_env()) as client:
    apps = await client.apps.list_apps()
    one = await client.apps.get("analytics")
    await client.apps.install_from_file("./build/my-app.zip")
    await client.apps.install_from_hub("<version-uuid>")
    await client.apps.uninstall("my-app")
    await client.apps.reload()

    catalog = await client.apps.hub_list(query="dashboard")
    snapshot = await client.apps.snapshot()
    summary = await client.apps.restore(snapshot, dry_run=False)
```

`UpdateSummary` + `UpdateOutcome` are plugin-internal view-models
(`dhis2w_core.v42.plugins.apps.models`); the typed wire shapes (`App`,
`AppHubApp`, `AppsSnapshot`, `RestoreSummary`) live in `dhis2w-client` so
PyPI consumers get them too.

## Not covered here

- **App-level configuration / settings** — DHIS2 stores per-app
  `dataStore` namespaces; reach for `client.get_raw("/api/dataStore/...")`
  directly.
- **Direct hub-side publishing** — the App Hub has its own auth + upload
  surface that isn't part of `/api/apps`. Out of scope.
- **Granular update strategies** — `apps update --all` is "everything
  with a newer version, in one pass". Per-app pinning isn't modeled.
