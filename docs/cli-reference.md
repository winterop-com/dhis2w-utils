# CLI reference

d2w — command-line interface for DHIS2 (discovers plugins from dhis2w-core).

**Usage**:

```console
$ d2w [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `-p, --profile <str>`: DHIS2 profile name (overrides DHIS2_PROFILE env + TOML default).
* `-d, --debug`: Verbose output on stderr — HTTP method/URL/status/elapsed for every request.
* `-j, --json`: Emit raw JSON to stdout instead of Rich tables (uniform across all commands).
* `-V, --version`: Print the CLI version + active plugin tree and exit.
* `--help`: Show this message and exit.

**Commands**:

* `schema`: Describe a generated type&#x27;s fields...
* `analytics`: DHIS2 analytics queries.
* `apps`: DHIS2 apps — /api/apps + /api/appHub.
* `browser`: Playwright-driven DHIS2 UI automation.
* `customize`: Brand + theme a DHIS2 instance (logos,...
* `data`: DHIS2 data values (aggregate + tracker).
* `datastore`: DHIS2 key-value data store.
* `dev`: Developer/operator tools.
* `doctor`: Probe a DHIS2 instance for known gotchas +...
* `files`: Manage DHIS2 documents + file resources.
* `maintenance`: DHIS2 maintenance (tasks, cache,...
* `messaging`: DHIS2 internal messaging.
* `metadata`: DHIS2 metadata inspection.
* `profile`: Manage DHIS2 profiles.
* `query`: d2ql query + transform language.
* `route`: DHIS2 integration routes.
* `security`: DHIS2 security posture (read-only).
* `system`: DHIS2 system info.
* `user`: DHIS2 user administration.
* `fhir`: FHIR Implementation Guide generation from...

## `d2w schema`

Describe a generated type&#x27;s fields (metadata or instance-side; prefers the OpenAPI tree).

**Usage**:

```console
$ d2w schema [OPTIONS] {type_name}
```

**Arguments**:

* `type_name`: Type name, e.g. dataElement or TrackedEntity (case-insensitive; plural wire names ok).  [required]

**Options**:

* `--source <str>`: Which generated tree to read: auto (prefer oas), oas, or schemas.  [default: auto]
* `--help`: Show this message and exit.

## `d2w analytics`

DHIS2 analytics queries.

**Usage**:

```console
$ d2w analytics [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `query`: Run an aggregate analytics query (requires...
* `outlier-detection`: Run `/api/analytics/outlierDetection` —...
* `events`: Event analytics — line-lists events or...
* `enrollments`: Enrollment analytics — line-lists...
* `tracked-entities`: Tracked-entity analytics — line-list TEs...

### `d2w analytics query`

Run an aggregate analytics query (requires at least dx + pe dimensions).

Example: analytics query --dim dx:Uvn6LCg7dVU --dim pe:LAST_12_MONTHS --dim ou:ImspTQPwCqd

Use `--shape` to pick `table`, `raw`, or `dvs`.

**Usage**:

```console
$ d2w analytics query [OPTIONS]
```

**Options**:

* `--dimension, --dim <str>`: Repeatable &#x27;axis:value&#x27;: dx:&lt;UID&gt;, pe:&lt;period&gt; (both required), ou:&lt;UID&gt;.  [required]
* `--shape <str>`: Response shape: `table` (default, aggregated), `raw` (/api/analytics/rawData), `dvs` (/api/analytics/dataValueSet — DataValueSet shape).  [default: table]
* `--filter <str>`: Filter string (repeatable), same syntax as --dimension.
* `--agg <str>`: SUM | AVERAGE | COUNT | MIN | MAX | AVERAGE_SUM_ORG_UNIT ...
* `--output-id-scheme <str>`: UID | NAME | CODE | ID — how UIDs appear in the response
* `--num-den / --no-num-den`: Include indicator numerator/denominator columns.  [default: no-num-den]
* `--display-property <str>`: NAME | SHORTNAME — which label to render metadata with.
* `--start-date <str>`: Fixed window start, ISO date YYYY-MM-DD (alternative to a pe: dimension).
* `--end-date <str>`: Fixed window end, ISO date YYYY-MM-DD.
* `--skip-meta`
* `--help`: Show this message and exit.

### `d2w analytics outlier-detection`

Run `/api/analytics/outlierDetection` — flag statistical anomalies in data values.

**Usage**:

```console
$ d2w analytics outlier-detection [OPTIONS]
```

**Options**:

* `--data-element, --de <str>`: Data-element UID (repeatable).
* `--data-set, --ds <str>`: Data-set UID (repeatable) — expanded to its dataElements.
* `--org-unit, --ou <str>`: Org-unit UID (repeatable).
* `--period, --pe <str>`: Period identifier (e.g. LAST_12_MONTHS, 202401).
* `--start-date <str>`: ISO date YYYY-MM-DD.
* `--end-date <str>`: ISO date YYYY-MM-DD.
* `--algorithm <str>`: Z_SCORE (default) | MODIFIED_Z_SCORE | MIN_MAX. (Upstream OAS still shows MOD_Z_SCORE but the server rejects that value — see BUGS.md.)
* `--threshold <float>`: Standard-deviation cutoff (default 3.0).
* `--max-results <int>`: Cap the number of outliers returned (default 500).
* `--order-by <str>`: ABS_DEV | STANDARD_DEVIATION | Z_SCORE | ...
* `--sort-order <str>`: ASC | DESC.
* `--help`: Show this message and exit.

### `d2w analytics events`

Event analytics — line-lists events or aggregates them.

**Usage**:

```console
$ d2w analytics events [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `query`: Run an event analytics query.

#### `d2w analytics events query`

Run an event analytics query.

Example: analytics events query &lt;PROGRAM_UID&gt; --mode query --dim pe:LAST_12_MONTHS --dim ou:&lt;ouUID&gt;

PROGRAM is a program UID; --mode is query (line list) or aggregate.

**Usage**:

```console
$ d2w analytics events query [OPTIONS] {program}
```

**Arguments**:

* `program`: Program UID.  [required]

**Options**:

* `--mode <str>`: `query` (line-listed events) or `aggregate` (grouped counts).  [default: query]
* `--dimension, --dim <str>`: Repeatable &#x27;axis:value&#x27;: pe:&lt;period&gt;, ou:&lt;UID&gt;. Aggregate value dim = &lt;stage&gt;.&lt;de&gt; (no dx:).
* `--filter <str>`: Filter string (repeatable), same syntax as --dimension.
* `--stage <str>`: Program stage UID to narrow events.
* `--output-type <str>`: EVENT | ENROLLMENT | TRACKED_ENTITY_INSTANCE (row shape).
* `--start-date <str>`: Fixed window start, ISO date YYYY-MM-DD (alternative to a pe: dimension).
* `--end-date <str>`: Fixed window end, ISO date YYYY-MM-DD.
* `--skip-meta`
* `--page <int>`
* `--page-size <int>`
* `--help`: Show this message and exit.

### `d2w analytics enrollments`

Enrollment analytics — line-lists enrollments.

**Usage**:

```console
$ d2w analytics enrollments [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `query`: Run an enrollment analytics query...

#### `d2w analytics enrollments query`

Run an enrollment analytics query (`/api/analytics/enrollments/query/{program}`).

**Usage**:

```console
$ d2w analytics enrollments query [OPTIONS] {program}
```

**Arguments**:

* `program`: Program UID.  [required]

**Options**:

* `--dimension, --dim <str>`: Dimension string (repeatable).
* `--filter <str>`: Filter string (repeatable).
* `--start-date <str>`: Fixed window start, ISO date YYYY-MM-DD (alternative to a pe: dimension).
* `--end-date <str>`: Fixed window end, ISO date YYYY-MM-DD.
* `--skip-meta`
* `--page <int>`
* `--page-size <int>`
* `--help`: Show this message and exit.

### `d2w analytics tracked-entities`

Tracked-entity analytics — line-list TEs for a given type.

**Usage**:

```console
$ d2w analytics tracked-entities [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `query`: Line-list tracked entities via...

#### `d2w analytics tracked-entities query`

Line-list tracked entities via `/api/analytics/trackedEntities/query/{TET_UID}`.

**Usage**:

```console
$ d2w analytics tracked-entities query [OPTIONS] {tracked_entity_type}
```

**Arguments**:

* `tracked_entity_type`: TrackedEntityType UID.  [required]

**Options**:

* `--dimension, --dim <str>`: Dimension string (repeatable).
* `--filter <str>`: Filter string (repeatable).
* `--program <str>`: Program UID (repeatable) to narrow results.
* `--start-date <str>`: Fixed window start, ISO date YYYY-MM-DD (alternative to a pe: dimension).
* `--end-date <str>`: Fixed window end, ISO date YYYY-MM-DD.
* `--ou-mode <str>`: SELECTED|CHILDREN|DESCENDANTS|ACCESSIBLE|ALL (default SELECTED; DESCENDANTS reaches facilities).
* `--display-property <str>`: NAME | SHORTNAME.
* `--skip-meta`
* `--skip-data`
* `--include-metadata-details`: Include nested objects in the metaData map.
* `--page <int>`
* `--page-size <int>`
* `--asc <str>`: Field to sort ascending (repeatable).
* `--desc <str>`: Field to sort descending (repeatable).
* `--help`: Show this message and exit.

## `d2w apps`

DHIS2 apps — /api/apps + /api/appHub.

**Usage**:

```console
$ d2w apps [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `ls`: List every installed app (`GET /api/apps`).
* `list`: List every installed app (`GET /api/apps`).
* `add`: Install an app from a local zip, an App...
* `rm`: Uninstall an app by key (`DELETE...
* `remove`: Uninstall an app by key (`DELETE...
* `update`: Update one app or every installed app to...
* `reload`: Ask DHIS2 to re-read every app from disk...
* `restore`: Reinstall every hub-backed entry from a...
* `snapshot`: Capture every installed app into a...
* `hub-list`: List apps available in the configured App...
* `hub-versions`: List every published version of one App...
* `hub-url`: Read or write DHIS2&#x27;s configured App Hub...

### `d2w apps ls`

List every installed app (`GET /api/apps`).

**Usage**:

```console
$ d2w apps ls [OPTIONS]
```

**Options**:

* `--help`: Show this message and exit.

### `d2w apps list`

List every installed app (`GET /api/apps`).

**Usage**:

```console
$ d2w apps list [OPTIONS]
```

**Options**:

* `--help`: Show this message and exit.

### `d2w apps add`

Install an app from a local zip, an App Hub version id, or an App Hub app id.

Auto-dispatches on `source`: an existing file on disk → multipart upload to
`/api/apps`; otherwise the id is resolved against the configured App Hub
catalog and installed via `POST /api/appHub/{versionId}`. A version id
installs directly; an app id resolves to that app&#x27;s latest version (App Hub
app ids and version ids are both bare UUIDs and easy to confuse — see
BUGS.md #46). DHIS2 overwrites an existing install of the same app.

**Usage**:

```console
$ d2w apps add [OPTIONS] {source}
```

**Arguments**:

* `source`: A path to a local `.zip` (installs via /api/apps), an App Hub version id, or an App Hub app id (the latest version is resolved).  [required]

**Options**:

* `--help`: Show this message and exit.

### `d2w apps rm`

Uninstall an app by key (`DELETE /api/apps/{key}`).

**Usage**:

```console
$ d2w apps rm [OPTIONS] {key}
```

**Arguments**:

* `key`: App key (folder name) from `apps list`.  [required]

**Options**:

* `-y, --yes`: Skip the confirmation prompt.
* `--help`: Show this message and exit.

### `d2w apps remove`

Uninstall an app by key (`DELETE /api/apps/{key}`).

**Usage**:

```console
$ d2w apps remove [OPTIONS] {key}
```

**Arguments**:

* `key`: App key (folder name) from `apps list`.  [required]

**Options**:

* `-y, --yes`: Skip the confirmation prompt.
* `--help`: Show this message and exit.

### `d2w apps update`

Update one app or every installed app to its latest App Hub version.

Apps without an `app_hub_id` (typically side-loaded zips) are reported
as `SKIPPED` — they&#x27;re not installable via the hub. Bundled core apps
(`bundled=True`) still carry an `app_hub_id` and can be updated in
place, so they&#x27;re treated like any other hub-updatable app. With
`--dry-run`, every available update prints as
`AVAILABLE` and no install call is made, so you can preview the delta
first.

**Usage**:

```console
$ d2w apps update [OPTIONS] [key]
```

**Arguments**:

* `key`: App key; omit with --all to update every app.

**Options**:

* `--all`: Update every installed app.
* `--dry-run`: Show what would change without installing — report the newer hub version for every app with an update available, tagged AVAILABLE.
* `--help`: Show this message and exit.

### `d2w apps reload`

Ask DHIS2 to re-read every app from disk (`PUT /api/apps`).

**Usage**:

```console
$ d2w apps reload [OPTIONS]
```

**Options**:

* `--help`: Show this message and exit.

### `d2w apps restore`

Reinstall every hub-backed entry from a snapshot JSON.

The flip side of `d2w apps snapshot`. Reads the JSON produced by
`snapshot`, walks each entry, and calls `/api/appHub/{versionId}`
for every app whose `hub_version_id` is set and whose currently
installed version differs from the snapshot&#x27;s. Side-loaded entries
(no `hub_version_id`) report as `SKIPPED` — the snapshot doesn&#x27;t
carry their zips.

**Usage**:

```console
$ d2w apps restore [OPTIONS] {manifest}
```

**Arguments**:

* `manifest`: Path to a snapshot JSON file produced by `d2w apps snapshot`.  [required]

**Options**:

* `--dry-run`: Show what would install without running the /api/appHub POSTs — entries that would install are tagged AVAILABLE.
* `--help`: Show this message and exit.

### `d2w apps snapshot`

Capture every installed app into a portable JSON snapshot.

One entry per installed app — key, name, version, `app_hub_id`, and
(when the app came from the App Hub) the hub `versionId` +
`downloadUrl` needed to re-install it on another instance. Apps
without an `app_hub_id` are captured as `source=side-loaded`; they
appear in the snapshot but can&#x27;t be rehydrated without their zip.

Useful as a &quot;pin my apps catalog at this point in time&quot; operation —
diff two snapshots to see drift, or re-apply on staging after a
bulk-install on production.

**Usage**:

```console
$ d2w apps snapshot [OPTIONS]
```

**Options**:

* `-o, --output <path>`: Write the snapshot JSON to this file. Omit to print to stdout.
* `--help`: Show this message and exit.

### `d2w apps hub-list`

List apps available in the configured App Hub (`GET /api/appHub`).

Pass `--search &lt;query&gt;` to filter the catalog by app name or
description substring. The filter runs client-side — DHIS2&#x27;s
`/api/appHub` proxy doesn&#x27;t expose a server-side query parameter
on v42, so the full catalog is fetched and filtered after.

**Usage**:

```console
$ d2w apps hub-list [OPTIONS]
```

**Options**:

* `-s, --search <str>`: Case-insensitive substring filter on name + description (client-side).
* `--limit <int>`: Cap the number of rows shown.  [default: 50]
* `--help`: Show this message and exit.

### `d2w apps hub-versions`

List every published version of one App Hub app (`GET /api/appHub`).

Prints `version / id / channel / DHIS2 min-&gt;max` for each version, newest
first. The `id` values are the version ids `d2w apps add &lt;id&gt;` installs
directly (pinning that exact version) — use this to pick a version instead
of letting `apps add &lt;app-id&gt;` resolve to the latest.

**Usage**:

```console
$ d2w apps hub-versions [OPTIONS] {app_id}
```

**Arguments**:

* `app_id`: App Hub app id (the `id` column from `apps hub-list`).  [required]

**Options**:

* `--help`: Show this message and exit.

### `d2w apps hub-url`

Read or write DHIS2&#x27;s configured App Hub URL (`keyAppHubUrl` system setting).

The App Hub is open source (https://github.com/dhis2/app-hub); teams
running a self-hosted hub can point DHIS2 at it by setting this.
Pass `--set &lt;url&gt;` to update, `--clear` to revert to DHIS2&#x27;s
hard-coded default (typically `https://apps.dhis2.org/api`).

**Usage**:

```console
$ d2w apps hub-url [OPTIONS]
```

**Options**:

* `--set <str>`: Point this DHIS2 instance at a different App Hub (writes the `keyAppHubUrl` system setting).
* `--clear`: Clear the `keyAppHubUrl` setting so DHIS2 reverts to its default hub.
* `--help`: Show this message and exit.

## `d2w browser`

Playwright-driven DHIS2 UI automation.

**Usage**:

```console
$ d2w browser [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `pat`: Mint a Personal Access Token V2 via...
* `dashboard`: Dashboard capture workflows.
* `viz`: Visualization capture workflows.
* `map`: Map capture workflows.

### `d2w browser pat`

Mint a Personal Access Token V2 via Playwright and print the token value to stdout.

DHIS2 only returns the token value once, at creation — store it somewhere
persistent immediately. Subsequent `GET /api/apiToken/{id}` calls return
metadata but not the secret.

**Usage**:

```console
$ d2w browser pat [OPTIONS]
```

**Options**:

* `--url <str>`: Base URL of the DHIS2 instance.  [required]
* `--username <str>`: Login username.  [required]
* `--password <str>`: Login password.  [required]
* `--name <str>`: Friendly display name for the token.
* `--expires-in-days <int>`: Token lifetime in days; omit for no expiry.
* `--allowed-ip <str>`: CIDR/IP allowlist entry; repeat for multiple.
* `--allowed-method <str>`: HTTP method allowlist; repeat for each method.
* `--allowed-referrer <str>`: Referer URL allowlist; repeat for each.
* `--headless / --headful`: Run browser headlessly (default: visible, so you can watch the flow).  [default: headful]
* `--help`: Show this message and exit.

### `d2w browser dashboard`

Dashboard capture workflows.

**Usage**:

```console
$ d2w browser dashboard [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `screenshot`: Capture full-page PNGs of every DHIS2...

#### `d2w browser dashboard screenshot`

Capture full-page PNGs of every DHIS2 dashboard (or just the ones named via --only).

Shares a single Playwright context across dashboards — one login, one
dashboard-app load, then hash-only navigation between dashboards. The
capture loop waits for each item&#x27;s plugin iframe to render substantial
content (canvas / svg / leaflet / highcharts / img / long text) with
a plateau detector so one stuck item doesn&#x27;t stall the batch.

**Usage**:

```console
$ d2w browser dashboard screenshot [OPTIONS]
```

**Options**:

* `-o, --output-dir <path>`: Directory for the PNG output. Defaults to `./screenshots`. Each run auto-creates an `{instance-slug}/` subdirectory keyed on the profile&#x27;s base URL so multi-stack captures don&#x27;t overwrite.
* `--only <str>`: Capture only these dashboard UIDs; repeat for multiple.
* `--headless / --headful`: Run browser headlessly (default: yes — automation-friendly).  [default: headless]
* `--banner / --no-banner`: Prepend an info banner (instance / user / timestamp) to each PNG.  [default: banner]
* `--trim / --no-trim`: Crop uniform-colour edges off the bottom + right of each PNG.  [default: trim]
* `--help`: Show this message and exit.

### `d2w browser viz`

Visualization capture workflows.

**Usage**:

```console
$ d2w browser viz [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `screenshot`: Capture a PNG of each Visualization (or...

#### `d2w browser viz screenshot`

Capture a PNG of each Visualization (or just the UIDs named via --only).

Each capture navigates the DHIS2 Data Visualizer app
(`/dhis-web-data-visualizer/#/&lt;uid&gt;`) inside a shared Playwright
context — one login, one app-shell load, hash-only navigation
between vizes. Renders wait for the chart to materialise (SVG /
canvas / pivot table / long text) with a plateau detector so one
stuck viz doesn&#x27;t stall the batch.

DHIS2 has no native `/api/visualizations/{uid}.png` endpoint, so
every PNG goes through Chromium. Install the extra via
`uv add &#x27;dhis2w-cli&#x27;` + `playwright install
chromium` first.

**Usage**:

```console
$ d2w browser viz screenshot [OPTIONS]
```

**Options**:

* `-o, --output-dir <path>`: Directory for the PNG output. Defaults to `./screenshots`. Each run auto-creates an `{instance-slug}/` subdirectory keyed on the profile&#x27;s base URL so multi-stack captures don&#x27;t overwrite.
* `--only <str>`: Capture only these Visualization UIDs; repeat for multiple.
* `--headless / --headful`: Run browser headlessly (default: yes — automation-friendly).  [default: headless]
* `--banner / --no-banner`: Prepend an info banner (name / type / instance / user / timestamp) to each PNG.  [default: banner]
* `--trim / --no-trim`: Crop uniform-colour edges off the bottom + right of each PNG.  [default: trim]
* `--help`: Show this message and exit.

### `d2w browser map`

Map capture workflows.

**Usage**:

```console
$ d2w browser map [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `screenshot`: Capture a PNG of each Map (or the UIDs...

#### `d2w browser map screenshot`

Capture a PNG of each Map (or the UIDs named via --only).

Navigates the DHIS2 Maps app (`/dhis-web-maps/#/&lt;uid&gt;`) in a shared
Playwright context — one login, one app-shell load, hash-nav between
maps. Waits for MapLibre canvas + vector overlays to render before
snapping. Requires the `` extra (install with
`uv add &#x27;dhis2w-cli&#x27;` + `playwright install chromium`).

**Usage**:

```console
$ d2w browser map screenshot [OPTIONS]
```

**Options**:

* `-o, --output-dir <path>`: Directory for the PNG output. Defaults to `./screenshots`. Each run auto-creates an `{instance-slug}/` subdirectory keyed on the profile&#x27;s base URL so multi-stack captures don&#x27;t overwrite.
* `--only <str>`: Capture only these Map UIDs; repeat for multiple.
* `--headless / --headful`: Run browser headlessly (default: yes — automation-friendly).  [default: headless]
* `--banner / --no-banner`: Prepend an info banner (name / layer count / instance / user / timestamp) to each PNG.  [default: banner]
* `--trim / --no-trim`: Crop uniform-colour edges off the bottom + right of each PNG.  [default: trim]
* `--help`: Show this message and exit.

## `d2w customize`

Brand + theme a DHIS2 instance (logos, copy, CSS).

**Usage**:

```console
$ d2w customize [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `logo-front`: Upload the login-page splash / upper-right...
* `logo-banner`: Upload the top-menu banner logo (appears...
* `style`: Upload a CSS stylesheet that DHIS2 serves...
* `apply`: Apply a committed preset directory in one...
* `show`: Show DHIS2&#x27;s current `/api/loginConfig`...

### `d2w customize logo-front`

Upload the login-page splash / upper-right logo.

**Usage**:

```console
$ d2w customize logo-front [OPTIONS] {file}
```

**Arguments**:

* `file`: PNG/JPG/SVG to upload as the login splash logo.  [required]

**Options**:

* `--help`: Show this message and exit.

### `d2w customize logo-banner`

Upload the top-menu banner logo (appears on every authenticated page).

**Usage**:

```console
$ d2w customize logo-banner [OPTIONS] {file}
```

**Arguments**:

* `file`: PNG/JPG/SVG to upload as the top-menu banner.  [required]

**Options**:

* `--help`: Show this message and exit.

### `d2w customize style`

Upload a CSS stylesheet that DHIS2 serves on every authenticated page.

NOTE: DHIS2&#x27;s standalone login app (`/dhis-web-login/`) does NOT include this
stylesheet. Post-auth pages do.

**Usage**:

```console
$ d2w customize style [OPTIONS] {file}
```

**Arguments**:

* `file`: CSS file to upload as `/api/files/style`.  [required]

**Options**:

* `--help`: Show this message and exit.

### `d2w customize apply`

Apply a committed preset directory in one call (skips files that don&#x27;t exist).

**Usage**:

```console
$ d2w customize apply [OPTIONS] {directory}
```

**Arguments**:

* `directory`: Directory containing optional logo_front.png, logo_banner.png, style.css, preset.json.  [required]

**Options**:

* `--help`: Show this message and exit.

### `d2w customize show`

Show DHIS2&#x27;s current `/api/loginConfig` snapshot (what the login app sees).

**Usage**:

```console
$ d2w customize show [OPTIONS]
```

**Options**:

* `--help`: Show this message and exit.

## `d2w data`

DHIS2 data values (aggregate + tracker).

**Usage**:

```console
$ d2w data [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `aggregate`: Aggregate data values (dataValueSets).
* `tracker`: Tracker (entities, enrollments, events,...

### `d2w data aggregate`

Aggregate data values (dataValueSets).

**Usage**:

```console
$ d2w data aggregate [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `get`: Fetch a data value set.
* `push`: Bulk push data values from a JSON file.
* `set`: Set a single data value.
* `delete`: Delete a single data value.
* `followup`: Set or clear the follow-up flag on a...

#### `d2w data aggregate get`

Fetch a data value set. Needs --ds plus a period (--pe or --start-date/--end-date) and --ou.

Example: data aggregate get --ds &lt;dataSetUID&gt; --pe 202401 --ou &lt;ouUID&gt; --children

**Usage**:

```console
$ d2w data aggregate get [OPTIONS]
```

**Options**:

* `--data-set, --ds <str>`: DataSet UID.
* `--period, --pe <str>`: Period; match the dataSet&#x27;s periodType (Monthly=202401, Yearly=2024, Weekly=2024W12).
* `--start-date <str>`: ISO date (YYYY-MM-DD).
* `--end-date <str>`: ISO date (YYYY-MM-DD).
* `--org-unit, --ou <str>`: OrganisationUnit UID.
* `--org-unit-group, --oug <str>`: OrganisationUnitGroup UID (alternative to --ou).
* `--children`: Include descendant org units (values usually live at facility level).
* `--data-element-group, --deg <str>`: DataElementGroup UID (narrows to its member DEs).
* `--include-deleted`: Also return soft-deleted values.
* `--last-updated <str>`: Only values modified since a date (YYYY-MM-DD) or duration (e.g. 7d).
* `--limit <int>`: Max rows to include in output.
* `--help`: Show this message and exit.

#### `d2w data aggregate push`

Bulk push data values from a JSON file.

**Usage**:

```console
$ d2w data aggregate push [OPTIONS] {file}
```

**Arguments**:

* `file`: Path to a JSON file containing a dataValues array or envelope.  [required]

**Options**:

* `--data-set, --ds <str>`
* `--period, --pe <str>`
* `--org-unit, --ou <str>`
* `--dry-run`
* `--strategy <str>`: CREATE | UPDATE | CREATE_AND_UPDATE | DELETE
* `--help`: Show this message and exit.

#### `d2w data aggregate set`

Set a single data value.

An attribute option combo is addressed by its CategoryCombo UID (--cc) plus
the category-option UIDs (--cp, repeatable) — DHIS2 has no attributeOptionCombo
query param, so pass the two together.

**Usage**:

```console
$ d2w data aggregate set [OPTIONS]
```

**Options**:

* `--data-element, --de <str>`: DataElement UID.  [required]
* `--period, --pe <str>`: Period (e.g. 202401).  [required]
* `--org-unit, --ou <str>`: OrganisationUnit UID.  [required]
* `--value <str>`: The value to set (as a string).  [required]
* `--coc <str>`: CategoryOptionCombo UID.
* `--attribute-combo, --cc <str>`: Attribute CategoryCombo UID (pair with --attribute-option).
* `--attribute-option, --cp <str>`: Attribute category-option UID; repeat for each. Pair with --attribute-combo.
* `--comment <str>`
* `--help`: Show this message and exit.

#### `d2w data aggregate delete`

Delete a single data value.

Address an attribute option combo via --cc (its CategoryCombo UID) plus --cp
(its category-option UIDs, repeatable) — DHIS2 has no attributeOptionCombo param.

**Usage**:

```console
$ d2w data aggregate delete [OPTIONS]
```

**Options**:

* `--data-element, --de <str>`: [required]
* `--period, --pe <str>`: [required]
* `--org-unit, --ou <str>`: [required]
* `--coc <str>`
* `--attribute-combo, --cc <str>`: Attribute CategoryCombo UID.
* `--attribute-option, --cp <str>`: Attribute category-option UID; repeat for each.
* `--help`: Show this message and exit.

#### `d2w data aggregate followup`

Set or clear the follow-up flag on a single data value.

**Usage**:

```console
$ d2w data aggregate followup [OPTIONS]
```

**Options**:

* `--data-element, --de <str>`: [required]
* `--period, --pe <str>`: [required]
* `--org-unit, --ou <str>`: [required]
* `--on / --off`: Set (--on) or clear (--off) the follow-up flag.  [default: on]
* `--coc <str>`
* `--aoc <str>`
* `--help`: Show this message and exit.

### `d2w data tracker`

Tracker (entities, enrollments, events, relationships).

**Usage**:

```console
$ d2w data tracker [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `ls`: List tracked entities by TrackedEntityType...
* `list`: List tracked entities by TrackedEntityType...
* `get`: Fetch one tracked entity by UID...
* `type`: List every configured TrackedEntityType on...
* `push`: Bulk import via POST /api/tracker.
* `delete`: Delete tracked entities by UID (cascades...
* `register`: Register a tracked entity + enroll in one...
* `outstanding`: List ACTIVE enrollments missing events on...
* `enrollment`: Enrollments.
* `event`: Events.
* `relationship`: Relationships.

#### `d2w data tracker ls`

List tracked entities by TrackedEntityType (TYPE) or by --program — give exactly one.

Example: d2w data tracker list Person --ou ImspTQPwCqd

**Usage**:

```console
$ d2w data tracker ls [OPTIONS] [type]
```

**Arguments**:

* `type`: TrackedEntityType name (case-insensitive) or UID — e.g. &#x27;Person&#x27; or &#x27;tet01234567&#x27;. Give this OR --program (not both).

**Options**:

* `--program <str>`: Program UID — list the program&#x27;s tracked entities. Alternative to TYPE; DHIS2 rejects a program and a TrackedEntityType together.
* `--te-uids <str>`: Comma-separated tracked-entity UIDs to fetch directly.
* `--org-unit, --ou <str>`: OrganisationUnit UID to scope the listing.
* `--ou-mode <str>`: Org-unit scope: SELECTED | CHILDREN | DESCENDANTS | ACCESSIBLE | ALL (default DESCENDANTS).  [default: DESCENDANTS]
* `--fields <str>`: DHIS2 field selector (comma-separated; nest with []).
* `--filter <str>`: Attribute filter &#x27;ATTR_UID:op:value&#x27; (repeatable).
* `--page-size <int>`: [default: 50]
* `--page <int>`: 1-based page number.
* `--updated-after <str>`: ISO-8601 cutoff — only entities updated after this.
* `--help`: Show this message and exit.

#### `d2w data tracker list`

List tracked entities by TrackedEntityType (TYPE) or by --program — give exactly one.

Example: d2w data tracker list Person --ou ImspTQPwCqd

**Usage**:

```console
$ d2w data tracker list [OPTIONS] [type]
```

**Arguments**:

* `type`: TrackedEntityType name (case-insensitive) or UID — e.g. &#x27;Person&#x27; or &#x27;tet01234567&#x27;. Give this OR --program (not both).

**Options**:

* `--program <str>`: Program UID — list the program&#x27;s tracked entities. Alternative to TYPE; DHIS2 rejects a program and a TrackedEntityType together.
* `--te-uids <str>`: Comma-separated tracked-entity UIDs to fetch directly.
* `--org-unit, --ou <str>`: OrganisationUnit UID to scope the listing.
* `--ou-mode <str>`: Org-unit scope: SELECTED | CHILDREN | DESCENDANTS | ACCESSIBLE | ALL (default DESCENDANTS).  [default: DESCENDANTS]
* `--fields <str>`: DHIS2 field selector (comma-separated; nest with []).
* `--filter <str>`: Attribute filter &#x27;ATTR_UID:op:value&#x27; (repeatable).
* `--page-size <int>`: [default: 50]
* `--page <int>`: 1-based page number.
* `--updated-after <str>`: ISO-8601 cutoff — only entities updated after this.
* `--help`: Show this message and exit.

#### `d2w data tracker get`

Fetch one tracked entity by UID (TrackedEntityType inferred from the entity).

**Usage**:

```console
$ d2w data tracker get [OPTIONS] {uid}
```

**Arguments**:

* `uid`: Tracked entity UID.  [required]

**Options**:

* `--program <str>`: Program UID.
* `--fields <str>`: DHIS2 field selector (comma-separated; nest with []).
* `--help`: Show this message and exit.

#### `d2w data tracker type`

List every configured TrackedEntityType on the connected instance (name + UID).

The `list` and `get` commands accept either a name or a UID in their `&lt;type&gt;`
positional — run this first to see what&#x27;s configured.

**Usage**:

```console
$ d2w data tracker type [OPTIONS]
```

**Options**:

* `--help`: Show this message and exit.

#### `d2w data tracker push`

Bulk import via POST /api/tracker.

**Usage**:

```console
$ d2w data tracker push [OPTIONS] {file}
```

**Arguments**:

* `file`: JSON file containing the tracker bundle.  [required]

**Options**:

* `--strategy <str>`: CREATE | UPDATE | CREATE_AND_UPDATE | DELETE
* `--atomic <str>`: ALL | OBJECT
* `--dry-run`
* `--async`
* `--help`: Show this message and exit.

#### `d2w data tracker delete`

Delete tracked entities by UID (cascades to their enrollments + events).

**Usage**:

```console
$ d2w data tracker delete [OPTIONS] {uids}...
```

**Arguments**:

* `uids...`: Tracked entity UID(s) to delete.  [required]

**Options**:

* `--async`: Return a job reference immediately instead of waiting.
* `-y, --yes`: Skip confirmation.
* `--help`: Show this message and exit.

#### `d2w data tracker register`

Register a tracked entity + enroll in one program in one call.

The typical clinic-intake flow: fills the TrackedEntityAttribute form,
stamps an enrollment into the program, all atomic via POST /api/tracker.
Prints the new tracked-entity + enrollment UIDs so the caller can
reference them downstream.

**Usage**:

```console
$ d2w data tracker register [OPTIONS] {program}
```

**Arguments**:

* `program`: Program UID to enroll into.  [required]

**Options**:

* `--org-unit, --ou <str>`: OrgUnit UID where the TE lives + is enrolled.  [required]
* `--tet <str>`: TrackedEntityType UID. Defaults to the program&#x27;s trackedEntityType if unset.
* `--attr <str>`: TrackedEntityAttribute UID=value. Repeatable. Example: --attr w75KJ2mc4zz=Jane
* `--enrolled-at <str>`: Enrollment date (ISO, e.g. 2024-06-01). Defaults to today server-side.
* `--help`: Show this message and exit.

#### `d2w data tracker outstanding`

List ACTIVE enrollments missing events on any non-repeatable program stage.

Renders each hit with its tracked-entity UID, OU, and the program-stage
UIDs that still need an event. A &quot;what&#x27;s due&quot; report for tracker
follow-ups.

&quot;Required&quot; here means `repeatable=false` on the program stage —
repeatable stages (weekly checkups, periodic screenings) don&#x27;t have
a single outstanding semantic and are skipped.

**Usage**:

```console
$ d2w data tracker outstanding [OPTIONS] {program}
```

**Arguments**:

* `program`: Program UID — the scope for the &#x27;what&#x27;s due&#x27; report.  [required]

**Options**:

* `--org-unit, --ou <str>`: Narrow to one OU subtree. Default: every active enrollment on the program.
* `--ou-mode <str>`: SELECTED | CHILDREN | DESCENDANTS | ALL  [default: DESCENDANTS]
* `--page-size <int>`: Max enrollments scanned (default 200).  [default: 200]
* `--help`: Show this message and exit.

#### `d2w data tracker enrollment`

Enrollments.

**Usage**:

```console
$ d2w data tracker enrollment [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `ls`: List enrollments (tracker programs only).
* `list`: List enrollments (tracker programs only).
* `delete`: Delete enrollments by UID (cascades to...
* `create`: Enroll an existing tracked entity in a...

##### `d2w data tracker enrollment ls`

List enrollments (tracker programs only).

**Usage**:

```console
$ d2w data tracker enrollment ls [OPTIONS]
```

**Options**:

* `--program <str>`: Program UID.
* `--org-unit, --ou <str>`: OrganisationUnit UID to scope the listing.
* `--ou-mode <str>`: Org-unit scope: SELECTED | CHILDREN | DESCENDANTS | ACCESSIBLE | ALL (default DESCENDANTS).  [default: DESCENDANTS]
* `--te <str>`: TrackedEntity UID.
* `--status <str>`: ACTIVE | COMPLETED | CANCELLED
* `--fields <str>`: DHIS2 field selector (comma-separated; nest with []).
* `--page-size <int>`: [default: 50]
* `--page <int>`
* `--updated-after <str>`
* `--help`: Show this message and exit.

##### `d2w data tracker enrollment list`

List enrollments (tracker programs only).

**Usage**:

```console
$ d2w data tracker enrollment list [OPTIONS]
```

**Options**:

* `--program <str>`: Program UID.
* `--org-unit, --ou <str>`: OrganisationUnit UID to scope the listing.
* `--ou-mode <str>`: Org-unit scope: SELECTED | CHILDREN | DESCENDANTS | ACCESSIBLE | ALL (default DESCENDANTS).  [default: DESCENDANTS]
* `--te <str>`: TrackedEntity UID.
* `--status <str>`: ACTIVE | COMPLETED | CANCELLED
* `--fields <str>`: DHIS2 field selector (comma-separated; nest with []).
* `--page-size <int>`: [default: 50]
* `--page <int>`
* `--updated-after <str>`
* `--help`: Show this message and exit.

##### `d2w data tracker enrollment delete`

Delete enrollments by UID (cascades to their events).

**Usage**:

```console
$ d2w data tracker enrollment delete [OPTIONS] {uids}...
```

**Arguments**:

* `uids...`: Enrollment UID(s) to delete.  [required]

**Options**:

* `--async`: Return a job reference immediately instead of waiting.
* `-y, --yes`: Skip confirmation.
* `--help`: Show this message and exit.

##### `d2w data tracker enrollment create`

Enroll an existing tracked entity in a program.

**Usage**:

```console
$ d2w data tracker enrollment create [OPTIONS] {tracked_entity} {program}
```

**Arguments**:

* `tracked_entity`: Existing TrackedEntity UID to enroll.  [required]
* `program`: Program UID to enroll into.  [required]

**Options**:

* `--at <str>`: OrgUnit UID where the enrollment lives.  [required]
* `--enrolled-at <str>`: ISO date; defaults to today server-side.
* `--help`: Show this message and exit.

#### `d2w data tracker event`

Events.

**Usage**:

```console
$ d2w data tracker event [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `ls`: List events (event and tracker programs).
* `list`: List events (event and tracker programs).
* `delete`: Delete events by UID.
* `create`: Add one event — tracker (with enrollment)...

##### `d2w data tracker event ls`

List events (event and tracker programs). Scope with --program and/or --org-unit.

Example: data tracker event list --program &lt;programUID&gt; --ou &lt;ouUID&gt;

**Usage**:

```console
$ d2w data tracker event ls [OPTIONS]
```

**Options**:

* `--program <str>`: Program UID.
* `--program-stage <str>`: ProgramStage UID to narrow to one stage.
* `--org-unit, --ou <str>`: OrganisationUnit UID to scope the listing.
* `--ou-mode <str>`: Org-unit scope: SELECTED | CHILDREN | DESCENDANTS | ACCESSIBLE | ALL (default DESCENDANTS).  [default: DESCENDANTS]
* `--te <str>`: TrackedEntity UID.
* `--enrollment <str>`: Enrollment UID to list its events.
* `--status <str>`: Event status: ACTIVE | COMPLETED | VISITED | SCHEDULE | OVERDUE | SKIPPED.
* `--after <str>`: Only events on/after this ISO date (YYYY-MM-DD).
* `--before <str>`: Only events on/before this ISO date (YYYY-MM-DD).
* `--fields <str>`: DHIS2 field selector (comma-separated; nest with []).
* `--page-size <int>`: [default: 50]
* `--page <int>`
* `--help`: Show this message and exit.

##### `d2w data tracker event list`

List events (event and tracker programs). Scope with --program and/or --org-unit.

Example: data tracker event list --program &lt;programUID&gt; --ou &lt;ouUID&gt;

**Usage**:

```console
$ d2w data tracker event list [OPTIONS]
```

**Options**:

* `--program <str>`: Program UID.
* `--program-stage <str>`: ProgramStage UID to narrow to one stage.
* `--org-unit, --ou <str>`: OrganisationUnit UID to scope the listing.
* `--ou-mode <str>`: Org-unit scope: SELECTED | CHILDREN | DESCENDANTS | ACCESSIBLE | ALL (default DESCENDANTS).  [default: DESCENDANTS]
* `--te <str>`: TrackedEntity UID.
* `--enrollment <str>`: Enrollment UID to list its events.
* `--status <str>`: Event status: ACTIVE | COMPLETED | VISITED | SCHEDULE | OVERDUE | SKIPPED.
* `--after <str>`: Only events on/after this ISO date (YYYY-MM-DD).
* `--before <str>`: Only events on/before this ISO date (YYYY-MM-DD).
* `--fields <str>`: DHIS2 field selector (comma-separated; nest with []).
* `--page-size <int>`: [default: 50]
* `--page <int>`
* `--help`: Show this message and exit.

##### `d2w data tracker event delete`

Delete events by UID.

**Usage**:

```console
$ d2w data tracker event delete [OPTIONS] {uids}...
```

**Arguments**:

* `uids...`: Event UID(s) to delete.  [required]

**Options**:

* `--async`: Return a job reference immediately instead of waiting.
* `-y, --yes`: Skip confirmation.
* `--help`: Show this message and exit.

##### `d2w data tracker event create`

Add one event — tracker (with enrollment) or event-only (standalone).

For tracker programs, pass --enrollment (the event binds to the
enrollment&#x27;s timeline). For event programs (WITHOUT_REGISTRATION —
community surveys, case-investigation forms), omit --enrollment; the
event stands alone, scoped by program + stage + org unit.

**Usage**:

```console
$ d2w data tracker event create [OPTIONS]
```

**Options**:

* `--program <str>`: Program UID.  [required]
* `--stage <str>`: ProgramStage UID.  [required]
* `--at <str>`: OrgUnit UID where the event happened.  [required]
* `--enrollment <str>`: Enrollment UID for tracker (WITH_REGISTRATION) programs. Omit for event (WITHOUT_REGISTRATION) programs.
* `--te <str>`: TrackedEntity UID (tracker programs only). Optional — DHIS2 derives from the enrollment.
* `--dv <str>`: DataElement UID=value. Repeatable. Example: --dv fClA2Erf6IO=5
* `--occurred-at <str>`: ISO event date; defaults to today server-side.
* `--help`: Show this message and exit.

#### `d2w data tracker relationship`

Relationships.

**Usage**:

```console
$ d2w data tracker relationship [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `ls`: List relationships (one of...
* `list`: List relationships (one of...

##### `d2w data tracker relationship ls`

List relationships (one of --te/--enrollment/--event required).

**Usage**:

```console
$ d2w data tracker relationship ls [OPTIONS]
```

**Options**:

* `--te <str>`: TrackedEntity UID.
* `--enrollment <str>`: Enrollment UID to list its events.
* `--event <str>`
* `--fields <str>`: DHIS2 field selector (comma-separated; nest with []).
* `--page-size <int>`: [default: 50]
* `--help`: Show this message and exit.

##### `d2w data tracker relationship list`

List relationships (one of --te/--enrollment/--event required).

**Usage**:

```console
$ d2w data tracker relationship list [OPTIONS]
```

**Options**:

* `--te <str>`: TrackedEntity UID.
* `--enrollment <str>`: Enrollment UID to list its events.
* `--event <str>`
* `--fields <str>`: DHIS2 field selector (comma-separated; nest with []).
* `--page-size <int>`: [default: 50]
* `--help`: Show this message and exit.

## `d2w datastore`

DHIS2 key-value data store.

**Usage**:

```console
$ d2w datastore [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `namespaces`: List every namespace in the store.
* `keys`: List every key in a namespace.
* `get`: Print the value stored at `namespace/key`...
* `set`: Create or update `namespace/key`.
* `delete`: Delete `namespace/key`.
* `delete-namespace`: Delete an entire namespace and every key...

### `d2w datastore namespaces`

List every namespace in the store.

**Usage**:

```console
$ d2w datastore namespaces [OPTIONS]
```

**Options**:

* `--user`: Target the per-user store (/api/userDataStore) instead of the shared one.
* `--help`: Show this message and exit.

### `d2w datastore keys`

List every key in a namespace.

**Usage**:

```console
$ d2w datastore keys [OPTIONS] {namespace}
```

**Arguments**:

* `namespace`: Namespace to list keys in.  [required]

**Options**:

* `--user`: Target the per-user store (/api/userDataStore) instead of the shared one.
* `--help`: Show this message and exit.

### `d2w datastore get`

Print the value stored at `namespace/key` (JSON).

**Usage**:

```console
$ d2w datastore get [OPTIONS] {namespace} {key}
```

**Arguments**:

* `namespace`: Namespace.  [required]
* `key`: Key.  [required]

**Options**:

* `--user`: Target the per-user store (/api/userDataStore) instead of the shared one.
* `--help`: Show this message and exit.

### `d2w datastore set`

Create or update `namespace/key`.

**Usage**:

```console
$ d2w datastore set [OPTIONS] {namespace} {key} {value}
```

**Arguments**:

* `namespace`: Namespace.  [required]
* `key`: Key.  [required]
* `value`: Value — parsed as JSON, or stored as a string if not valid JSON.  [required]

**Options**:

* `--user`: Target the per-user store (/api/userDataStore) instead of the shared one.
* `--help`: Show this message and exit.

### `d2w datastore delete`

Delete `namespace/key`.

**Usage**:

```console
$ d2w datastore delete [OPTIONS] {namespace} {key}
```

**Arguments**:

* `namespace`: Namespace.  [required]
* `key`: Key.  [required]

**Options**:

* `--user`: Target the per-user store (/api/userDataStore) instead of the shared one.
* `-y, --yes`: Skip the interactive confirmation.
* `--help`: Show this message and exit.

### `d2w datastore delete-namespace`

Delete an entire namespace and every key in it.

**Usage**:

```console
$ d2w datastore delete-namespace [OPTIONS] {namespace}
```

**Arguments**:

* `namespace`: Namespace to delete (all its keys go with it).  [required]

**Options**:

* `--user`: Target the per-user store (/api/userDataStore) instead of the shared one.
* `-y, --yes`: Skip the interactive confirmation.
* `--help`: Show this message and exit.

## `d2w dev`

Developer/operator tools.

**Usage**:

```console
$ d2w dev [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `codegen`: Generate version-aware DHIS2 client code...
* `uid`: Generate 11-char DHIS2 UIDs.
* `sample`: Inject known-good fixtures to verify the...

### `d2w dev codegen`

Generate version-aware DHIS2 client code from /api/schemas.

**Usage**:

```console
$ d2w dev codegen [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `generate`: Generate the client for the DHIS2 version...
* `rebuild`: Regenerate the client from saved...
* `oas-rebuild`: Emit OpenAPI-derived pydantic models into...
* `diff`: Diff two committed `schemas_manifest.json`...

#### `d2w dev codegen generate`

Generate the client for the DHIS2 version reported by `--url`.

**Usage**:

```console
$ d2w dev codegen generate [OPTIONS]
```

**Options**:

* `--url <str>`: Base URL of the DHIS2 instance.  [required]
* `--username <str>`: Basic-auth username.
* `--password <str>`: Basic-auth password.
* `--pat <str>`: Personal Access Token.
* `--output-root <path>`: Directory containing versioned subfolders; defaults to dhis2w-client&#x27;s generated/ folder.
* `--help`: Show this message and exit.

#### `d2w dev codegen rebuild`

Regenerate the client from saved schemas_manifest.json files (no network).

Useful after touching emit.py / templates when you want every committed
version refreshed without spinning up a live DHIS2 for each. If `--manifest`
is omitted, walks the output root and rebuilds each version whose
schemas_manifest.json is checked in.

**Usage**:

```console
$ d2w dev codegen rebuild [OPTIONS]
```

**Options**:

* `--manifest <path>`: Path to a committed schemas_manifest.json. Defaults to every version under the generated root.
* `--output-root <path>`: Directory of versioned subfolders; defaults to dhis2w-client generated/.
* `--help`: Show this message and exit.

#### `d2w dev codegen oas-rebuild`

Emit OpenAPI-derived pydantic models into `generated/v{N}/oas/`.

Reads the committed `openapi.json` + `schemas_manifest.json` from each
version directory (no network). Output lands alongside the `/api/schemas`
emitter&#x27;s output under `schemas/`.

**Usage**:

```console
$ d2w dev codegen oas-rebuild [OPTIONS]
```

**Options**:

* `--version <str>`: Version key (e.g. v42). Defaults to every committed version.
* `--output-root <path>`: Directory of versioned subfolders; defaults to dhis2w-client generated/.
* `--help`: Show this message and exit.

#### `d2w dev codegen diff`

Diff two committed `schemas_manifest.json` files and report drift.

Lists schemas added, removed, and per-property changes (type, klass,
bounds, owner/required/etc). Useful for spotting upstream API drift
when bumping DHIS2 majors.

**Usage**:

```console
$ d2w dev codegen diff [OPTIONS] {from_version} {to_version}
```

**Arguments**:

* `from_version`: Source version key (e.g. v42).  [required]
* `to_version`: Target version key (e.g. v43).  [required]

**Options**:

* `--output-root <path>`: Directory of versioned subfolders; defaults to dhis2w-client generated/.
* `--json`: Emit a JSON dump instead of the human-readable report.
* `--help`: Show this message and exit.

### `d2w dev uid`

Generate 11-char DHIS2 UIDs.

**Usage**:

```console
$ d2w dev uid [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `-n, --count <int range>`: How many UIDs to generate.  [default: 1; 1&lt;=x&lt;=10000]
* `--help`: Show this message and exit.

### `d2w dev sample`

Inject known-good fixtures to verify the stack end-to-end (route, data, pat, oauth2-client).

**Usage**:

```console
$ d2w dev sample [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `route`: Create a sample route, run it, and (unless...
* `pat`: Create a sample PAT, use it to call...
* `data-value`: Write a sample data value, read it back,...
* `oauth2-client`: Create a sample OAuth2 client on DHIS2,...
* `all`: Run every sample in sequence — route,...

#### `d2w dev sample route`

Create a sample route, run it, and (unless --keep) delete it.

Verifies the full /api/routes lifecycle end-to-end: create -&gt; run (proxy
to target URL) -&gt; delete.

**Usage**:

```console
$ d2w dev sample route [OPTIONS]
```

**Options**:

* `--url <str>`: URL the sample route will proxy to.  [default: https://httpbin.org/get]
* `--code <str>`: [default: SMOKE_ROUTE]
* `--keep`: Don&#x27;t delete the sample route afterwards.
* `--help`: Show this message and exit.

#### `d2w dev sample pat`

Create a sample PAT, use it to call /api/me, then (unless --keep) delete it.

**Usage**:

```console
$ d2w dev sample pat [OPTIONS]
```

**Options**:

* `--url <str>`: DHIS2 base URL (also: DHIS2_URL env).
* `--admin-user <str>`
* `--keep`: Don&#x27;t delete the sample PAT afterwards.
* `--help`: Show this message and exit.

#### `d2w dev sample data-value`

Write a sample data value, read it back, and (unless --keep) delete it.

Uses the Sierra Leone seed fixture by default:
`fClA2Erf6IO` (&quot;Penta1 doses given&quot;) at `Rp268JB6Ne4`
(Adonkia CHP, facility level) for `202406` (within the seeded 2024
data window). The DE is in the seeded `BfMAe6Itzgt` (&quot;Child
Health&quot;) dataset, so DHIS2&#x27;s dataset-detection on import
accepts the write. Override with `--de` / `--ou` / `--pe` for
other scopes.

**Usage**:

```console
$ d2w dev sample data-value [OPTIONS]
```

**Options**:

* `--data-element, --de <str>`: DataElement UID.  [default: fClA2Erf6IO]
* `--org-unit, --ou <str>`: OrganisationUnit UID.  [default: Rp268JB6Ne4]
* `--period, --pe <str>`: Period (e.g. 202406).  [default: 202406]
* `--value <str>`: [default: 42]
* `--keep`: Don&#x27;t delete the sample data value afterwards.
* `--help`: Show this message and exit.

#### `d2w dev sample oauth2-client`

Create a sample OAuth2 client on DHIS2, verify it persisted, then (unless --keep) delete it.

Lifecycle: POST /api/oAuth2Clients -&gt; GET /api/oAuth2Clients/{uid}
-&gt; DELETE /api/oAuth2Clients/{uid}. The admin user is the owner DHIS2
records on the client; no user-impersonation happens.

**Usage**:

```console
$ d2w dev sample oauth2-client [OPTIONS]
```

**Options**:

* `--url <str>`: DHIS2 base URL (also: DHIS2_URL env).
* `--admin-user <str>`
* `--client-id <str>`: OAuth2 client_id; default = smoke-&lt;epoch&gt;.
* `--keep`: Don&#x27;t delete the sample OAuth2 client afterwards.
* `--help`: Show this message and exit.

#### `d2w dev sample all`

Run every sample in sequence — route, data-value, pat, oauth2-client.

**Usage**:

```console
$ d2w dev sample all [OPTIONS]
```

**Options**:

* `--url <str>`: DHIS2 base URL (also: DHIS2_URL env).
* `--admin-user <str>`
* `--keep`: Don&#x27;t delete the fixtures afterwards.
* `--help`: Show this message and exit.

## `d2w doctor`

Probe a DHIS2 instance for known gotchas + requirements.

**Usage**:

```console
$ d2w doctor [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--all`: Run every category (metadata + integrity + bugs).
* `--help`: Show this message and exit.

**Commands**:

* `metadata`: Run workspace metadata-health probes only...
* `integrity`: Run DHIS2&#x27;s own...
* `bugs`: Run BUGS.md workaround drift detection...

### `d2w doctor metadata`

Run workspace metadata-health probes only (data sets without DEs, programs without stages, ...).

**Usage**:

```console
$ d2w doctor metadata [OPTIONS]
```

**Options**:

* `--help`: Show this message and exit.

### `d2w doctor integrity`

Run DHIS2&#x27;s own `/api/dataIntegrity/summary` and surface each check as a probe.

**Usage**:

```console
$ d2w doctor integrity [OPTIONS]
```

**Options**:

* `--help`: Show this message and exit.

### `d2w doctor bugs`

Run BUGS.md workaround drift detection (workspace maintenance, not operator-facing).

**Usage**:

```console
$ d2w doctor bugs [OPTIONS]
```

**Options**:

* `--help`: Show this message and exit.

## `d2w files`

Manage DHIS2 documents + file resources.

**Usage**:

```console
$ d2w files [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `documents`: Documents (/api/documents).
* `resources`: File resources (/api/fileResources).

### `d2w files documents`

Documents (/api/documents).

**Usage**:

```console
$ d2w files documents [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `ls`: List documents — external URL links and...
* `list`: List documents — external URL links and...
* `get`: Show metadata for one document.
* `upload`: Upload a binary document — prints the new...
* `upload-url`: Create an EXTERNAL_URL document — no bytes...
* `download`: Download the binary payload to `destination`.
* `delete`: Delete one document.

#### `d2w files documents ls`

List documents — external URL links and UPLOAD_FILE blobs.

Pass `--details` to inline each UPLOAD_FILE&#x27;s fileResource contentType / size /
storageStatus. NOTE: `/api/documents` does not expose the fileResource UID, so details
are only available where a document&#x27;s `url` is itself an 11-char UID (older data); for
filename-style `url`s the detail columns show `-`.

**Usage**:

```console
$ d2w files documents ls [OPTIONS]
```

**Options**:

* `--filter <str>`: DHIS2 filter, e.g. `name:like:Annual`.
* `--page <int>`: 1-indexed page number.
* `--page-size <int>`: Rows per page (default 50).
* `--details`: For each UPLOAD_FILE, also fetch the backing fileResource&#x27;s contentType / size / storageStatus (one extra request per row).
* `--help`: Show this message and exit.

#### `d2w files documents list`

List documents — external URL links and UPLOAD_FILE blobs.

Pass `--details` to inline each UPLOAD_FILE&#x27;s fileResource contentType / size /
storageStatus. NOTE: `/api/documents` does not expose the fileResource UID, so details
are only available where a document&#x27;s `url` is itself an 11-char UID (older data); for
filename-style `url`s the detail columns show `-`.

**Usage**:

```console
$ d2w files documents list [OPTIONS]
```

**Options**:

* `--filter <str>`: DHIS2 filter, e.g. `name:like:Annual`.
* `--page <int>`: 1-indexed page number.
* `--page-size <int>`: Rows per page (default 50).
* `--details`: For each UPLOAD_FILE, also fetch the backing fileResource&#x27;s contentType / size / storageStatus (one extra request per row).
* `--help`: Show this message and exit.

#### `d2w files documents get`

Show metadata for one document.

**Usage**:

```console
$ d2w files documents get [OPTIONS] {uid}
```

**Arguments**:

* `uid`: Document UID.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w files documents upload`

Upload a binary document — prints the new UID.

**Usage**:

```console
$ d2w files documents upload [OPTIONS] {file}
```

**Arguments**:

* `file`: File to upload.  [required]

**Options**:

* `--name <str>`: Document name (defaults to filename).
* `--help`: Show this message and exit.

#### `d2w files documents upload-url`

Create an EXTERNAL_URL document — no bytes uploaded; DHIS2 links out to `url`.

**Usage**:

```console
$ d2w files documents upload-url [OPTIONS] {name} {url}
```

**Arguments**:

* `name`: Document display name.  [required]
* `url`: External URL DHIS2 will link to.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w files documents download`

Download the binary payload to `destination`.

**Usage**:

```console
$ d2w files documents download [OPTIONS] {uid} {destination}
```

**Arguments**:

* `uid`: Document UID.  [required]
* `destination`: Output file path.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w files documents delete`

Delete one document.

**Usage**:

```console
$ d2w files documents delete [OPTIONS] {uid}
```

**Arguments**:

* `uid`: Document UID.  [required]

**Options**:

* `-y, --yes`: Skip the confirmation prompt.
* `--help`: Show this message and exit.

### `d2w files resources`

File resources (/api/fileResources).

**Usage**:

```console
$ d2w files resources [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `upload`: Upload a file resource; prints the new UID...
* `get`: Show metadata for one file resource.
* `download`: Download the file-resource payload to...

#### `d2w files resources upload`

Upload a file resource; prints the new UID (reference it from the owning metadata object).

**Usage**:

```console
$ d2w files resources upload [OPTIONS] {file}
```

**Arguments**:

* `file`: File to upload as a fileResource.  [required]

**Options**:

* `--domain <data_value|push_analysis|document|message_attachment|user_avatar|org_unit|icon|job_data>`: FileResource domain (DATA_VALUE, ICON, MESSAGE_ATTACHMENT, ...).  [default: DATA_VALUE]
* `--help`: Show this message and exit.

#### `d2w files resources get`

Show metadata for one file resource.

**Usage**:

```console
$ d2w files resources get [OPTIONS] {uid}
```

**Arguments**:

* `uid`: FileResource UID.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w files resources download`

Download the file-resource payload to `destination`.

**Usage**:

```console
$ d2w files resources download [OPTIONS] {uid} {destination}
```

**Arguments**:

* `uid`: FileResource UID.  [required]
* `destination`: Output file path.  [required]

**Options**:

* `--help`: Show this message and exit.

## `d2w maintenance`

DHIS2 maintenance (tasks, cache, integrity, cleanup, refresh).

**Usage**:

```console
$ d2w maintenance [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `cache`: Clear every server-side cache (Hibernate +...
* `task`: Background-task polling (all long-running...
* `cleanup`: Hard-remove soft-deleted rows (unblocks...
* `dataintegrity`: DHIS2 data-integrity checks.
* `refresh`: Regenerate analytics / resource /...
* `validation`: Run validation rules + inspect violations...
* `predictors`: Run predictor expressions (CRUD on...

### `d2w maintenance cache`

Clear every server-side cache (Hibernate + app caches).

**Usage**:

```console
$ d2w maintenance cache [OPTIONS]
```

**Options**:

* `--help`: Show this message and exit.

### `d2w maintenance task`

Background-task polling (all long-running DHIS2 ops).

**Usage**:

```console
$ d2w maintenance task [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `types`: List every background-job type DHIS2...
* `ls`: List every task UID recorded for a given...
* `list`: List every task UID recorded for a given...
* `status`: Print every notification emitted by a...
* `watch`: Poll a task until it reports...

#### `d2w maintenance task types`

List every background-job type DHIS2 tracks (ANALYTICS_TABLE, DATA_INTEGRITY, ...).

**Usage**:

```console
$ d2w maintenance task types [OPTIONS]
```

**Options**:

* `--help`: Show this message and exit.

#### `d2w maintenance task ls`

List every task UID recorded for a given job type.

**Usage**:

```console
$ d2w maintenance task ls [OPTIONS] {task_type}
```

**Arguments**:

* `task_type`: Task type, e.g. ANALYTICS_TABLE.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w maintenance task list`

List every task UID recorded for a given job type.

**Usage**:

```console
$ d2w maintenance task list [OPTIONS] {task_type}
```

**Arguments**:

* `task_type`: Task type, e.g. ANALYTICS_TABLE.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w maintenance task status`

Print every notification emitted by a task, oldest first.

**Usage**:

```console
$ d2w maintenance task status [OPTIONS] {task_type} {task_uid}
```

**Arguments**:

* `task_type`: Task type, e.g. ANALYTICS_TABLE.  [required]
* `task_uid`: Task UID returned by the async POST.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w maintenance task watch`

Poll a task until it reports `completed=true`, streaming each new notification.

**Usage**:

```console
$ d2w maintenance task watch [OPTIONS] {task_type} {task_uid}
```

**Arguments**:

* `task_type`: Task type, e.g. DATA_INTEGRITY.  [required]
* `task_uid`: Task UID returned by the async POST.  [required]

**Options**:

* `--interval <float>`: Poll interval in seconds.  [default: 2.0]
* `--timeout <float>`: Abort after N seconds (default 600).  [default: 600.0]
* `--help`: Show this message and exit.

### `d2w maintenance cleanup`

Hard-remove soft-deleted rows (unblocks metadata deletion).

**Usage**:

```console
$ d2w maintenance cleanup [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `data-values`: Hard-remove soft-deleted data values from...
* `events`: Hard-remove soft-deleted tracker events.
* `enrollments`: Hard-remove soft-deleted tracker enrollments.
* `tracked-entities`: Hard-remove soft-deleted tracked entities.

#### `d2w maintenance cleanup data-values`

Hard-remove soft-deleted data values from `/api/dataValueSets` imports.

**Usage**:

```console
$ d2w maintenance cleanup data-values [OPTIONS]
```

**Options**:

* `-y, --yes`: Skip the confirmation prompt.
* `--help`: Show this message and exit.

#### `d2w maintenance cleanup events`

Hard-remove soft-deleted tracker events.

**Usage**:

```console
$ d2w maintenance cleanup events [OPTIONS]
```

**Options**:

* `-y, --yes`: Skip the confirmation prompt.
* `--help`: Show this message and exit.

#### `d2w maintenance cleanup enrollments`

Hard-remove soft-deleted tracker enrollments.

**Usage**:

```console
$ d2w maintenance cleanup enrollments [OPTIONS]
```

**Options**:

* `-y, --yes`: Skip the confirmation prompt.
* `--help`: Show this message and exit.

#### `d2w maintenance cleanup tracked-entities`

Hard-remove soft-deleted tracked entities.

**Usage**:

```console
$ d2w maintenance cleanup tracked-entities [OPTIONS]
```

**Options**:

* `-y, --yes`: Skip the confirmation prompt.
* `--help`: Show this message and exit.

### `d2w maintenance dataintegrity`

DHIS2 data-integrity checks.

**Usage**:

```console
$ d2w maintenance dataintegrity [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `ls`: List every built-in data-integrity check...
* `list`: List every built-in data-integrity check...
* `run`: Kick off a data-integrity run; with...
* `result`: Read the stored result of a completed...

#### `d2w maintenance dataintegrity ls`

List every built-in data-integrity check (name, section, severity).

**Usage**:

```console
$ d2w maintenance dataintegrity ls [OPTIONS]
```

**Options**:

* `--help`: Show this message and exit.

#### `d2w maintenance dataintegrity list`

List every built-in data-integrity check (name, section, severity).

**Usage**:

```console
$ d2w maintenance dataintegrity list [OPTIONS]
```

**Options**:

* `--help`: Show this message and exit.

#### `d2w maintenance dataintegrity run`

Kick off a data-integrity run; with --watch, stream progress to completion.

**Usage**:

```console
$ d2w maintenance dataintegrity run [OPTIONS] [check]...
```

**Arguments**:

* `check...`: Check name(s); omit to run every check.

**Options**:

* `--details`: Hit /details (populates issues[]) instead of /summary.
* `--slow`: Include the ~19 `isSlow` checks DHIS2 skips by default. Resolves the full check list via /api/dataIntegrity and passes every name explicitly — DHIS2 only runs a slow check when it&#x27;s named in the `checks` filter.
* `-w, --watch`: After kicking off the job, poll /api/system/tasks until it reports completed=true.
* `--interval <float>`: Poll interval in seconds when --watch is set.  [default: 2.0]
* `--timeout <float>`: Abort polling after N seconds (default 600).  [default: 600.0]
* `--help`: Show this message and exit.

#### `d2w maintenance dataintegrity result`

Read the stored result of a completed data-integrity run (summary or details mode).

**Usage**:

```console
$ d2w maintenance dataintegrity result [OPTIONS] [check]...
```

**Arguments**:

* `check...`: Check name(s) to read; omit for all.

**Options**:

* `--details`: Hit /details (issues[]) instead of /summary (count only).
* `--help`: Show this message and exit.

### `d2w maintenance refresh`

Regenerate analytics / resource / monitoring backing tables.

**Usage**:

```console
$ d2w maintenance refresh [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `analytics`: Regenerate the full analytics star schema...
* `resource-tables`: Regenerate resource tables only...
* `monitoring`: Regenerate monitoring tables...

#### `d2w maintenance refresh analytics`

Regenerate the full analytics star schema (`/api/resourceTables/analytics`, job=`ANALYTICS_TABLE`).

Primary workflow after pushing new data values: DHIS2&#x27;s analytics queries
read from these tables, so they must be rebuilt for fresh data to show up.
Also refreshes resource tables unless `--skip-resource-tables` is set.

**Usage**:

```console
$ d2w maintenance refresh analytics [OPTIONS]
```

**Options**:

* `--last-years <int>`
* `--skip-resource-tables`
* `-w, --watch`: After kicking off the job, poll /api/system/tasks until it reports completed=true.
* `--interval <float>`: Poll interval in seconds when --watch is set.  [default: 2.0]
* `--timeout <float>`: Abort polling after N seconds (default 600).  [default: 600.0]
* `--help`: Show this message and exit.

#### `d2w maintenance refresh resource-tables`

Regenerate resource tables only (`/api/resourceTables`, job=`RESOURCE_TABLE`).

Rebuilds the supporting OU / category hierarchy tables without touching
the analytics star schema. Use when OU / category metadata changed but
no new data values landed — faster than a full `refresh analytics` run.

**Usage**:

```console
$ d2w maintenance refresh resource-tables [OPTIONS]
```

**Options**:

* `-w, --watch`: After kicking off the job, poll /api/system/tasks until it reports completed=true.
* `--interval <float>`: Poll interval in seconds when --watch is set.  [default: 2.0]
* `--timeout <float>`: Abort polling after N seconds (default 600).  [default: 600.0]
* `--help`: Show this message and exit.

#### `d2w maintenance refresh monitoring`

Regenerate monitoring tables (`/api/resourceTables/monitoring`, job=`MONITORING`).

Rebuilds the tables backing DHIS2&#x27;s data-quality / validation-rule
monitoring. Independent of the analytics + resource tables.

**Usage**:

```console
$ d2w maintenance refresh monitoring [OPTIONS]
```

**Options**:

* `-w, --watch`: After kicking off the job, poll /api/system/tasks until it reports completed=true.
* `--interval <float>`: Poll interval in seconds when --watch is set.  [default: 2.0]
* `--timeout <float>`: Abort polling after N seconds (default 600).  [default: 600.0]
* `--help`: Show this message and exit.

### `d2w maintenance validation`

Run validation rules + inspect violations (CRUD on rules: `d2w metadata list validationRules`).

**Usage**:

```console
$ d2w maintenance validation [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `run`: Run a validation-rule analysis + render...
* `send-notifications`: Fire configured notification templates for...
* `validate-expression`: Parse-check an expression + render a human...
* `result`: List / get / delete persisted validation...

#### `d2w maintenance validation run`

Run a validation-rule analysis + render the violations.

**Usage**:

```console
$ d2w maintenance validation run [OPTIONS] {org_unit}
```

**Arguments**:

* `org_unit`: Org-unit UID to evaluate rules under (DHIS2 walks the sub-tree).  [required]

**Options**:

* `--start-date <str>`: Period start, YYYY-MM-DD.  [required]
* `--end-date <str>`: Period end, YYYY-MM-DD.  [required]
* `--group <str>`: ValidationRuleGroup UID to narrow the rules evaluated.
* `--max-results <int>`: Cap on violations returned (DHIS2 default ~500).
* `--notification`: Fire configured notification templates for each triggered rule.
* `--persist`: Write violations into `/api/validationResults` (otherwise ephemeral).
* `--help`: Show this message and exit.

#### `d2w maintenance validation send-notifications`

Fire configured notification templates for every current validation violation.

**Usage**:

```console
$ d2w maintenance validation send-notifications [OPTIONS]
```

**Options**:

* `--help`: Show this message and exit.

#### `d2w maintenance validation validate-expression`

Parse-check an expression + render a human description.

**Usage**:

```console
$ d2w maintenance validation validate-expression [OPTIONS] {expression}
```

**Arguments**:

* `expression`: DHIS2 expression to parse-check.  [required]

**Options**:

* `--context <str>`: Expression parser context: one of generic, validation-rule, indicator, predictor, program-indicator.  [default: generic]
* `--help`: Show this message and exit.

#### `d2w maintenance validation result`

List / get / delete persisted validation results.

**Usage**:

```console
$ d2w maintenance validation result [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `ls`: List persisted validation results.
* `list`: List persisted validation results.
* `get`: Show one persisted validation result by id.
* `delete`: Bulk-delete validation results by filter.

##### `d2w maintenance validation result ls`

List persisted validation results.

**Usage**:

```console
$ d2w maintenance validation result ls [OPTIONS]
```

**Options**:

* `--org-unit, --ou <str>`: Org-unit UID filter.
* `--period, --pe <str>`: Period filter (e.g. 202501).
* `--vr <str>`: Validation-rule UID filter.
* `--page <int>`
* `--page-size <int>`
* `--help`: Show this message and exit.

##### `d2w maintenance validation result list`

List persisted validation results.

**Usage**:

```console
$ d2w maintenance validation result list [OPTIONS]
```

**Options**:

* `--org-unit, --ou <str>`: Org-unit UID filter.
* `--period, --pe <str>`: Period filter (e.g. 202501).
* `--vr <str>`: Validation-rule UID filter.
* `--page <int>`
* `--page-size <int>`
* `--help`: Show this message and exit.

##### `d2w maintenance validation result get`

Show one persisted validation result by id.

**Usage**:

```console
$ d2w maintenance validation result get [OPTIONS] {result_id}
```

**Arguments**:

* `result_id`: Numeric validation-result id.  [required]

**Options**:

* `--help`: Show this message and exit.

##### `d2w maintenance validation result delete`

Bulk-delete validation results by filter. At least one filter is required.

**Usage**:

```console
$ d2w maintenance validation result delete [OPTIONS]
```

**Options**:

* `--org-unit, --ou <str>`: Org-unit UID filter. Repeatable.
* `--period, --pe <str>`: Period filter. Repeatable.
* `--vr <str>`: Validation-rule UID filter. Repeatable.
* `--help`: Show this message and exit.

### `d2w maintenance predictors`

Run predictor expressions (CRUD on predictors: `d2w metadata list predictors`).

**Usage**:

```console
$ d2w maintenance predictors [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `run`: Run predictor expressions + emit data...

#### `d2w maintenance predictors run`

Run predictor expressions + emit data values for the given date range.

**Usage**:

```console
$ d2w maintenance predictors run [OPTIONS]
```

**Options**:

* `--start-date <str>`: Period start, YYYY-MM-DD.  [required]
* `--end-date <str>`: Period end, YYYY-MM-DD.  [required]
* `--predictor <str>`: Run one predictor by UID. Mutually exclusive with --group.
* `--group <str>`: Run all predictors in a PredictorGroup by UID.
* `--help`: Show this message and exit.

## `d2w messaging`

DHIS2 internal messaging.

**Usage**:

```console
$ d2w messaging [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `ls`: List conversations the authenticated user...
* `list`: List conversations the authenticated user...
* `get`: Show one conversation&#x27;s metadata + message...
* `send`: Create a new conversation with an initial...
* `reply`: Reply to an existing conversation with a...
* `mark-read`: Mark one or more conversations as read.
* `mark-unread`: Mark one or more conversations as unread.
* `delete`: Delete a conversation (soft-delete for the...
* `set-priority`: Set a conversation&#x27;s ticket-workflow...
* `set-status`: Set a conversation&#x27;s ticket-workflow status.
* `assign`: Assign a conversation to a user (ticket...
* `unassign`: Remove the assignee from a conversation.

### `d2w messaging ls`

List conversations the authenticated user is part of.

**Usage**:

```console
$ d2w messaging ls [OPTIONS]
```

**Options**:

* `--filter <str>`: DHIS2 filter. Example: `read:eq:false` for unread only.
* `--page <int>`: 1-indexed page number.
* `--page-size <int>`: Rows per page (default 50).
* `--help`: Show this message and exit.

### `d2w messaging list`

List conversations the authenticated user is part of.

**Usage**:

```console
$ d2w messaging list [OPTIONS]
```

**Options**:

* `--filter <str>`: DHIS2 filter. Example: `read:eq:false` for unread only.
* `--page <int>`: 1-indexed page number.
* `--page-size <int>`: Rows per page (default 50).
* `--help`: Show this message and exit.

### `d2w messaging get`

Show one conversation&#x27;s metadata + message thread.

**Usage**:

```console
$ d2w messaging get [OPTIONS] {uid}
```

**Arguments**:

* `uid`: Conversation UID.  [required]

**Options**:

* `--help`: Show this message and exit.

### `d2w messaging send`

Create a new conversation with an initial message.

**Usage**:

```console
$ d2w messaging send [OPTIONS] {subject} {text}
```

**Arguments**:

* `subject`: Subject line.  [required]
* `text`: Message body.  [required]

**Options**:

* `-u, --user <str>`: User UID recipient. Repeatable.
* `-g, --user-group <str>`: User-group UID recipient. Repeatable.
* `--org-unit, --ou <str>`: Organisation-unit UID recipient. Repeatable.
* `-a, --attachment <str>`: FileResource UID to attach (upload via `d2w files resources upload --domain MESSAGE_ATTACHMENT` first). Repeatable.
* `--help`: Show this message and exit.

### `d2w messaging reply`

Reply to an existing conversation with a plain-text message.

DHIS2&#x27;s reply endpoint takes text/plain only on v42 — attachments +
internal-note flag only work on the initial `send` call.

**Usage**:

```console
$ d2w messaging reply [OPTIONS] {uid} {text}
```

**Arguments**:

* `uid`: Conversation UID.  [required]
* `text`: Reply body (plain text).  [required]

**Options**:

* `--help`: Show this message and exit.

### `d2w messaging mark-read`

Mark one or more conversations as read.

**Usage**:

```console
$ d2w messaging mark-read [OPTIONS] {uid}...
```

**Arguments**:

* `uid...`: Conversation UID(s). One or more.  [required]

**Options**:

* `--help`: Show this message and exit.

### `d2w messaging mark-unread`

Mark one or more conversations as unread.

**Usage**:

```console
$ d2w messaging mark-unread [OPTIONS] {uid}...
```

**Arguments**:

* `uid...`: Conversation UID(s). One or more.  [required]

**Options**:

* `--help`: Show this message and exit.

### `d2w messaging delete`

Delete a conversation (soft-delete for the calling user; other participants keep it).

**Usage**:

```console
$ d2w messaging delete [OPTIONS] {uid}
```

**Arguments**:

* `uid`: Conversation UID.  [required]

**Options**:

* `--help`: Show this message and exit.

### `d2w messaging set-priority`

Set a conversation&#x27;s ticket-workflow priority.

Values: NONE / LOW / MEDIUM / HIGH. Applies to any messageType — most
meaningful on TICKET conversations, stored on PRIVATE threads too.

**Usage**:

```console
$ d2w messaging set-priority [OPTIONS] {uid} {priority}
```

**Arguments**:

* `uid`: Conversation UID.  [required]
* `priority`: Priority — NONE / LOW / MEDIUM / HIGH.  [required]

**Options**:

* `--help`: Show this message and exit.

### `d2w messaging set-status`

Set a conversation&#x27;s ticket-workflow status.

Values: NONE / OPEN / PENDING / INVALID / SOLVED. Not wired into the
initial `send` — DHIS2&#x27;s API requires a separate POST on the
`/status` sub-resource.

**Usage**:

```console
$ d2w messaging set-status [OPTIONS] {uid} {status}
```

**Arguments**:

* `uid`: Conversation UID.  [required]
* `status`: Status — NONE / OPEN / PENDING / INVALID / SOLVED.  [required]

**Options**:

* `--help`: Show this message and exit.

### `d2w messaging assign`

Assign a conversation to a user (ticket workflows).

**Usage**:

```console
$ d2w messaging assign [OPTIONS] {uid} {user}
```

**Arguments**:

* `uid`: Conversation UID.  [required]
* `user`: User UID to assign the conversation to.  [required]

**Options**:

* `--help`: Show this message and exit.

### `d2w messaging unassign`

Remove the assignee from a conversation.

**Usage**:

```console
$ d2w messaging unassign [OPTIONS] {uid}
```

**Arguments**:

* `uid`: Conversation UID.  [required]

**Options**:

* `--help`: Show this message and exit.

## `d2w metadata`

DHIS2 metadata inspection.

**Usage**:

```console
$ d2w metadata [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `ls`: List instances of a metadata resource.
* `list`: List instances of a metadata resource.
* `search`: Cross-resource metadata search.
* `usage`: Reverse lookup — find every object that...
* `get`: Fetch one metadata object by UID.
* `export`: Download a metadata bundle from `GET...
* `import`: Upload a metadata bundle via `POST...
* `patch`: Apply an RFC 6902 JSON Patch to a metadata...
* `rename`: Bulk-rename metadata objects by RFC 6902...
* `retag`: Bulk-rewrite ref / enum fields on metadata...
* `share`: Merge a sharing change across many UIDs of...
* `diff`: Compare two metadata bundles (or one...
* `diff-profiles`: Diff a metadata slice between two...
* `merge`: Export resources from one profile and...
* `merge-bundle`: Import a saved bundle file into a target...
* `type`: Metadata resource types (the catalog).
* `option-sets`: OptionSet workflows (get / find / sync).
* `attributes`: Cross-resource AttributeValue workflows...
* `program-rules`: Program rule workflows (get / vars-for /...
* `sql-views`: SQL view workflows (get / execute /...
* `visualizations`: Visualization authoring (get / create /...
* `dashboards`: Dashboard composition (get / add-item /...
* `maps`: Map authoring (get / create / clone /...
* `data-elements`: DataElement authoring (get / create /...
* `data-element-groups`: DataElementGroup workflows (get / members...
* `data-element-group-sets`: DataElementGroupSet workflows (get /...
* `indicators`: Indicator authoring (get / create / rename...
* `indicator-groups`: IndicatorGroup workflows (get / members /...
* `indicator-group-sets`: IndicatorGroupSet workflows (get / create...
* `program-indicators`: ProgramIndicator authoring (get / create /...
* `program-indicator-groups`: ProgramIndicatorGroup workflows (get /...
* `category-options`: CategoryOption authoring (get / create /...
* `category-option-groups`: CategoryOptionGroup workflows (get /...
* `category-option-group-sets`: CategoryOptionGroupSet workflows (get /...
* `categories`: Category authoring (get / create / rename...
* `category-combos`: CategoryCombo authoring (get / create /...
* `category-option-combos`: CategoryOptionCombo read access (get /...
* `data-sets`: DataSet authoring (get / create / rename /...
* `sections`: Section authoring (get / create / rename /...
* `validation-rules`: ValidationRule authoring (get / create /...
* `validation-rule-groups`: ValidationRuleGroup workflows (get /...
* `predictors`: Predictor authoring (get / create / rename...
* `predictor-groups`: PredictorGroup workflows (get / members /...
* `tracked-entity-attributes`: TrackedEntityAttribute authoring (get /...
* `tracked-entity-types`: TrackedEntityType authoring (get / create...
* `programs`: Program authoring (get / create / rename /...
* `program-stages`: ProgramStage authoring (get / create /...
* `organisation-units`: OrganisationUnit hierarchy workflows (get...
* `organisation-unit-groups`: OrganisationUnitGroup workflows (get /...
* `organisation-unit-group-sets`: OrganisationUnitGroupSet workflows (get /...
* `organisation-unit-levels`: OrganisationUnitLevel naming (get / rename).
* `legend-sets`: LegendSet authoring (get / create / clone...

### `d2w metadata ls`

List instances of a metadata resource.

**Usage**:

```console
$ d2w metadata ls [OPTIONS] {resource}
```

**Arguments**:

* `resource`: Resource type, e.g. dataElements, indicators  [required]

**Options**:

* `--fields <str>`: DHIS2 field selector: plain (&#x27;id,name&#x27;), presets (&#x27;:identifiable&#x27;, &#x27;:nameable&#x27;, &#x27;:owner&#x27;, &#x27;:all&#x27;), nested (&#x27;children&#x27;), or exclusions (&#x27;:all,!lastUpdated&#x27;).  [default: id,name]
* `--filter <str>`: Filter as `property:operator:value`. Repeatable — AND&#x27;d by default, use --root-junction OR. Operators: eq (exact), ilike (contains), $ilike (starts-with), ilike$ (ends-with), token (word), gt/ge/lt/le (numbers/dates), in: (any-of), null / !null (presence); drop the `i` for case-sensitive. Nested paths use dots, e.g. dataSetElements.dataSet.id:eq:&lt;uid&gt; or categoryCombo.id:eq:&lt;uid&gt;. E.g. name:$ilike:anc lists names starting with &#x27;anc&#x27;.
* `--root-junction <str>`: Combine repeated --filter as AND (default) or OR.  [default: AND]
* `--order <str>`: Sort clause like &#x27;name:asc&#x27; or &#x27;created:desc&#x27;. Repeatable (later clauses tie-break).
* `--page <int>`: Server-side page number (1-based). With NO paging flag the FULL collection is returned; passing --page switches to paged mode (pageSize defaults to 50). Ignored when --all is set.
* `--page-size <int>`: Rows per page; applies only in paged mode (when --page/--page-size is given), default 50. Omit all paging flags to get everything. Ignored when --all is set.
* `--all`: Stream every page server-side (ignores --page/--page-size). Useful for dumping a full catalog.
* `--translate / --no-translate`: Return server-side translations for i18n fields.
* `--locale <str>`: Locale for --translate, e.g. &#x27;fr&#x27;.
* `--count`: Print only the total number of matching items (DHIS2 pager total), not the rows. Respects --filter; ignores --fields / --page / --page-size / --all.
* `-o, --output <path>`: Write the result JSON to this file and print a one-line summary instead of the rows. Combine with --fields / --filter / --all to dump a full slice without flooding the caller.
* `--help`: Show this message and exit.

### `d2w metadata list`

List instances of a metadata resource.

**Usage**:

```console
$ d2w metadata list [OPTIONS] {resource}
```

**Arguments**:

* `resource`: Resource type, e.g. dataElements, indicators  [required]

**Options**:

* `--fields <str>`: DHIS2 field selector: plain (&#x27;id,name&#x27;), presets (&#x27;:identifiable&#x27;, &#x27;:nameable&#x27;, &#x27;:owner&#x27;, &#x27;:all&#x27;), nested (&#x27;children&#x27;), or exclusions (&#x27;:all,!lastUpdated&#x27;).  [default: id,name]
* `--filter <str>`: Filter as `property:operator:value`. Repeatable — AND&#x27;d by default, use --root-junction OR. Operators: eq (exact), ilike (contains), $ilike (starts-with), ilike$ (ends-with), token (word), gt/ge/lt/le (numbers/dates), in: (any-of), null / !null (presence); drop the `i` for case-sensitive. Nested paths use dots, e.g. dataSetElements.dataSet.id:eq:&lt;uid&gt; or categoryCombo.id:eq:&lt;uid&gt;. E.g. name:$ilike:anc lists names starting with &#x27;anc&#x27;.
* `--root-junction <str>`: Combine repeated --filter as AND (default) or OR.  [default: AND]
* `--order <str>`: Sort clause like &#x27;name:asc&#x27; or &#x27;created:desc&#x27;. Repeatable (later clauses tie-break).
* `--page <int>`: Server-side page number (1-based). With NO paging flag the FULL collection is returned; passing --page switches to paged mode (pageSize defaults to 50). Ignored when --all is set.
* `--page-size <int>`: Rows per page; applies only in paged mode (when --page/--page-size is given), default 50. Omit all paging flags to get everything. Ignored when --all is set.
* `--all`: Stream every page server-side (ignores --page/--page-size). Useful for dumping a full catalog.
* `--translate / --no-translate`: Return server-side translations for i18n fields.
* `--locale <str>`: Locale for --translate, e.g. &#x27;fr&#x27;.
* `--count`: Print only the total number of matching items (DHIS2 pager total), not the rows. Respects --filter; ignores --fields / --page / --page-size / --all.
* `-o, --output <path>`: Write the result JSON to this file and print a one-line summary instead of the rows. Combine with --fields / --filter / --all to dump a full slice without flooding the caller.
* `--help`: Show this message and exit.

### `d2w metadata search`

Cross-resource metadata search.

Three concurrent `/api/metadata?filter=&lt;field&gt;:&lt;op&gt;:&lt;q&gt;` calls (one
per match axis: id, code, name) merged client-side with UID dedup.
Paste whatever you have — UID, partial UID, business code, or name
fragment — to find every matching object grouped by resource.

`--resource dataElements` narrows to one resource kind. `--fields
id,name,code,valueType` asks DHIS2 for extra columns (rendered
after the standard four). `--exact` switches from ilike substring
to `eq` strict match — useful when a partial UID would otherwise
match too many siblings.

**Usage**:

```console
$ d2w metadata search [OPTIONS] {query}
```

**Arguments**:

* `query`: UID, code, or name fragment to search for.  [required]

**Options**:

* `--page-size <int>`: Max hits per resource type (default 50).  [default: 50]
* `--resource <str>`: Narrow to one DHIS2 resource (e.g. dataElements, dashboards).
* `--fields <str>`: DHIS2 fields selector; extras land on SearchHit.extras (rendered as trailing columns).
* `--exact`: Use `:eq:` instead of `:ilike:` — strict UID / code match.
* `--help`: Show this message and exit.

### `d2w metadata usage`

Reverse lookup — find every object that references the given UID.

Useful as a deletion-safety check: any dataset / visualization / map /
dashboard / program that references the UID shows up in the table.
Empty result means no reference was found on any covered path, but
is not a hard proof that the UID is safe to delete — coverage is
best-effort (see `_USAGE_PATTERNS` in the client).

Internally: resolves the UID&#x27;s owning resource via
`/api/identifiableObjects/{uid}` first, then fans out concurrent
`/api/&lt;target&gt;?filter=&lt;path&gt;:eq:&lt;uid&gt;` calls over every known
reference-shape for that owning type.

**Usage**:

```console
$ d2w metadata usage [OPTIONS] {uid}
```

**Arguments**:

* `uid`: UID to reverse-lookup — find every object that references it.  [required]

**Options**:

* `--page-size <int>`: Max hits per reference path (default 100).  [default: 100]
* `--help`: Show this message and exit.

### `d2w metadata get`

Fetch one metadata object by UID.

Prints a concise Rich summary by default (id, name, code, common metadata +
notable extras). Use `--json` for the full payload when debugging or
piping into jq. Pass `--fields` to narrow what DHIS2 returns.

**Usage**:

```console
$ d2w metadata get [OPTIONS] {resource} {uid}
```

**Arguments**:

* `resource`: Resource type, e.g. dataElements  [required]
* `uid`: Object UID  [required]

**Options**:

* `--fields <str>`: DHIS2 fields selector.
* `--help`: Show this message and exit.

### `d2w metadata export`

Download a metadata bundle from `GET /api/metadata`.

Prints a per-resource count summary to stderr so stdout stays pipe-friendly
when `--output` is omitted. With `--check-references` (default), walks the
exported bundle and warns on any reference to a UID not in the bundle —
so a filtered `--resource dataElements` export doesn&#x27;t silently produce a
bundle that won&#x27;t round-trip because categoryCombos / optionSets / ...
are missing.

**Usage**:

```console
$ d2w metadata export [OPTIONS]
```

**Options**:

* `--resource <str>`: Resource type to include (repeatable). Omit for every type DHIS2 exports by default.
* `--fields <str>`: DHIS2 field selector. Defaults to &#x27;:owner&#x27; for a lossless round-trip import.  [default: :owner]
* `--filter <str>`: Per-resource filter in the form `RESOURCE:property:operator:value`. Repeatable. Example: `--filter dataElements:name:like:ANC`. Same DSL as `d2w metadata list --filter`, prefixed with the resource name.
* `--resource-fields <str>`: Per-resource field selector in the form `RESOURCE:SELECTOR`. Repeatable. Overrides the global `--fields` for the named resource. Example: `--resource-fields dataElements::identifiable`.
* `--skip-sharing`: Exclude sharing blocks from exported objects.
* `--skip-translation`: Exclude translation blocks.
* `--skip-validation`: Skip validation during export (matches DHIS2&#x27;s server-side option).
* `--check-references / --no-check-references`: After export, walk the bundle and warn on references to UIDs not in the bundle (e.g. a dataElement&#x27;s categoryCombo missing from a filtered export). On by default.  [default: check-references]
* `-o, --output <path>`: Write the bundle to this file (JSON). A full-catalog export is tens of MB (org-unit geometry) — prefer this; omitting prints the whole bundle to stdout.
* `--pretty / --no-pretty`: Indent JSON output (default: pretty).  [default: pretty]
* `--help`: Show this message and exit.

### `d2w metadata import`

Upload a metadata bundle via `POST /api/metadata` and print the import report.

**Usage**:

```console
$ d2w metadata import [OPTIONS] {file}
```

**Arguments**:

* `file`: Path to the metadata bundle JSON.  [required]

**Options**:

* `--strategy <str>`: CREATE | UPDATE | CREATE_AND_UPDATE | DELETE (default CREATE_AND_UPDATE).  [default: CREATE_AND_UPDATE]
* `--atomic-mode <str>`: ALL (rollback on any failure) or NONE (commit surviving objects).  [default: ALL]
* `--dry-run`: Validate + preheat without committing. Output is the import report DHIS2 would have produced.
* `--identifier <str>`: UID | CODE | AUTO (default UID).  [default: UID]
* `--skip-sharing`
* `--skip-translation`
* `--skip-validation`
* `--merge-mode <str>`: REPLACE (overwrite) or MERGE (patch) existing objects.
* `--preheat-mode <str>`: REFERENCE (default), ALL, or NONE.
* `--flush-mode <str>`: AUTO (default) or OBJECT.
* `--help`: Show this message and exit.

### `d2w metadata patch`

Apply an RFC 6902 JSON Patch to a metadata object (`PATCH /api/&lt;resource&gt;/{uid}`).

Two input modes:

- `--file patch.json` — full patch array on disk, one op per entry:
  `[{&quot;op&quot;: &quot;replace&quot;, &quot;path&quot;: &quot;/name&quot;, &quot;value&quot;: &quot;New&quot;}, ...]`
- `--set path=value` / `--remove path` (each repeatable) — inline shorthand
  for the common replace/remove cases. Values parse as JSON when possible
  (so `--set /valueType=INTEGER` sends a string, `--set /disabled=true`
  sends a boolean).

**Usage**:

```console
$ d2w metadata patch [OPTIONS] {resource} {uid}
```

**Arguments**:

* `resource`: Resource type, e.g. dataElements, indicators.  [required]
* `uid`: UID of the object to patch.  [required]

**Options**:

* `--file <path>`: JSON file with a RFC 6902 patch array. Mutually exclusive with --set/--remove.
* `--set <str>`: Inline `replace` op as `path=value`. Repeatable. Values are JSON-decoded when they parse as JSON (`{&quot;a&quot;:1}`, `true`, `42`) and treated as strings otherwise.
* `--remove <str>`: Inline `remove` op as `path`. Repeatable.
* `--help`: Show this message and exit.

### `d2w metadata rename`

Bulk-rename metadata objects by RFC 6902 patch.

Fans out concurrent `PATCH /api/&lt;resource&gt;/{uid}` requests via the
shared `client.metadata.patch_bulk` primitive (#187); per-UID
failures render through the same conflict table used by
`metadata import` instead of raising. Prefix / suffix flags are
idempotent — re-running won&#x27;t double-prefix already-prefixed
objects.

Use `--dry-run` to preview which objects match + what the
before/after labels would be, then drop the flag to apply.

**Usage**:

```console
$ d2w metadata rename [OPTIONS] {resource}
```

**Arguments**:

* `resource`: Resource type, e.g. dataElements, indicators.  [required]

**Options**:

* `--filter <str>`: DHIS2 filter DSL (`&lt;prop&gt;:&lt;op&gt;:&lt;value&gt;`), repeatable. Example: `--filter code:like:DE_ANC` to narrow the cohort.
* `--root-junction <str>`: Combine repeated --filter as AND (default) or OR.
* `--name-prefix <str>`: Prefix each matched object&#x27;s `name` (idempotent).
* `--name-suffix <str>`: Suffix each matched object&#x27;s `name` (idempotent).
* `--name-strip-prefix <str>`: Remove this non-empty prefix from each matched object&#x27;s `name` (idempotent; no-op when absent).
* `--name-strip-suffix <str>`: Remove this non-empty suffix from each matched object&#x27;s `name` (idempotent; no-op when absent).
* `--short-name-prefix <str>`: Prefix each matched object&#x27;s `shortName` (idempotent).
* `--short-name-suffix <str>`: Suffix each matched object&#x27;s `shortName` (idempotent).
* `--short-name-strip-prefix <str>`: Remove this non-empty prefix from each matched object&#x27;s `shortName` (idempotent).
* `--short-name-strip-suffix <str>`: Remove this non-empty suffix from each matched object&#x27;s `shortName` (idempotent).
* `--set-description <str>`: Replace every matched object&#x27;s `description` with this string.
* `--concurrency <int>`: Max concurrent PATCH requests (default 8).  [default: 8]
* `--dry-run`: Preview the planned patches without sending them.
* `--all`: Opt into renaming EVERY object when no --filter is given (asks to confirm).
* `-y, --yes`: Skip the confirmation prompt for a catalog-wide (--all) rename.
* `--help`: Show this message and exit.

### `d2w metadata retag`

Bulk-rewrite ref / enum fields on metadata objects.

Sister verb to `metadata rename`. Flags map to RFC 6902 patches:
`--category-combo &lt;uid&gt;` → `replace /categoryCombo`, `--option-set
&lt;uid&gt;` → `replace /optionSet`, `--clear-option-set` → `remove
/optionSet`, `--aggregation-type TYPE` → `replace
/aggregationType`, `--legend-set &lt;uid&gt;` (repeatable) → `replace
/legendSets` with the whole list, `--clear-legend-sets` → empty
that list. Stack multiple flags in one invocation.

Per-UID failures render through the shared `ConflictRow` renderer
— e.g. `--domain-type TRACKER` against an Indicator surfaces as
409s instead of raising.

**Usage**:

```console
$ d2w metadata retag [OPTIONS] {resource}
```

**Arguments**:

* `resource`: Resource type, e.g. dataElements, indicators.  [required]

**Options**:

* `--filter <str>`: DHIS2 filter DSL (`&lt;prop&gt;:&lt;op&gt;:&lt;value&gt;`), repeatable.
* `--root-junction <str>`: Combine repeated --filter as AND (default) or OR.
* `--category-combo <str>`: Replace `/categoryCombo` with the given CategoryCombo UID.
* `--option-set <str>`: Replace `/optionSet` with the given OptionSet UID.
* `--clear-option-set`: Remove `/optionSet` (null out the ref).
* `--aggregation-type <str>`: Replace `/aggregationType` (e.g. SUM, AVERAGE).
* `--domain-type <str>`: Replace `/domainType` (AGGREGATE / TRACKER).
* `--legend-set <str>`: Replace `/legendSets` with the given UIDs (repeatable).
* `--clear-legend-sets`: Empty `/legendSets`.
* `--concurrency <int>`: Max concurrent PATCH requests (default 8).  [default: 8]
* `--dry-run`: Preview without sending patches.
* `--all`: Opt into retagging EVERY object when no --filter is given (asks to confirm).
* `-y, --yes`: Skip the confirmation prompt for a catalog-wide (--all) retag.
* `--help`: Show this message and exit.

### `d2w metadata share`

Merge a sharing change across many UIDs of one resource.

Read-merge-write: each UID&#x27;s current sharing block is fetched first,
the new grants are merged into the existing ones (existing grants are
preserved; a grant for an already-granted UID replaces its access
string), and `--public-access` only changes `publicAccess` when given.
Per-UID failures render through the same row table used by
`metadata rename` instead of raising.

Use `--dry-run` to preview the merged sharing per UID, then drop the
flag to apply. UIDs come from positional args or stdin (`-`); pipe from
`d2w --json metadata list ... | jq -r &#x27;.[].id&#x27;` to filter-then-share without
leaving the shell.

**Usage**:

```console
$ d2w metadata share [OPTIONS] {resource_type} [uids]...
```

**Arguments**:

* `resource_type`: DHIS2 resource type — singular or plural, e.g. `dataElement`/`dataElements`, `dataSet`/`dataSets`, `program`. Normalized to the singular `/api/sharing?type=` form.  [required]
* `uids...`: UIDs to share. Pass `-` to read one UID per line from stdin.

**Options**:

* `--public-access <str>`: Replace the public-access string. 8-char DHIS2 pattern (`rwrw----`, `r-------`, `--------`). Omit to keep each object&#x27;s current public access unchanged.
* `--user-access <str>`: Repeatable; grant a user access in `UID:access` form (e.g. `U_ALICE:rw------`).
* `--user-group-access <str>`: Repeatable; grant a user-group access in `UID:access` form.
* `--concurrency <int>`: Max concurrent POSTs (default 8).  [default: 8]
* `--dry-run`: Preview the planned grants without sending them.
* `--help`: Show this message and exit.

### `d2w metadata diff`

Compare two metadata bundles (or one bundle against the live instance).

Per-resource counts of create/update/delete. Objects that differ only on
DHIS2&#x27;s per-instance noise (lastUpdated, createdBy, etc.) are treated as
unchanged by default — `--ignore` extends that list.

**Usage**:

```console
$ d2w metadata diff [OPTIONS] {left} [right]
```

**Arguments**:

* `left`: Left-hand bundle — the &#x27;source of truth&#x27; you&#x27;re comparing against.  [required]
* `right`: Right-hand bundle. Omit with `--live` to diff against the connected DHIS2 instance.

**Options**:

* `--live`: Use the connected DHIS2 instance as the right-hand side. Exports only the resource types present in the left bundle (no full-catalog fetch). Incompatible with a positional right arg.
* `--show-uids`: List up to 5 offending UIDs per per-resource row.
* `--ignore <str>`: Fields to skip when deciding if an object changed. Repeatable. Defaults cover DHIS2&#x27;s per-instance noise (lastUpdated, createdBy, access, ...); pass `--ignore sharing` etc. to extend.
* `--help`: Show this message and exit.

### `d2w metadata diff-profiles`

Diff a metadata slice between two registered profiles (staging vs prod drift).

Runs both exports in parallel, narrows to `--resource` types, optionally
filters each resource (`--filter resource:prop:op:val`), then structurally
diffs the two bundles ignoring DHIS2&#x27;s per-instance noise
(timestamps, createdBy, access strings, …).

A whole-instance diff is almost never useful — staging and prod diverge on
user accounts, org-unit assignments, and incidental settings by design. Pick
a narrow resource slice (`-r dataElements -r indicators`), filter further
with `--filter`, and extend `--ignore` for anything else that&#x27;s expected to
differ.

Exit code is `0` by default regardless of drift (so operators running this
interactively aren&#x27;t tripped by per-command-exit conventions). Pass
`--exit-on-drift` for the CI shape.

**Usage**:

```console
$ d2w metadata diff-profiles [OPTIONS] {profile_a} {profile_b}
```

**Arguments**:

* `profile_a`: Name of the &#x27;left&#x27; profile (source of truth).  [required]
* `profile_b`: Name of the &#x27;right&#x27; profile (candidate).  [required]

**Options**:

* `-r, --resource <str>`: Resource type to compare (e.g. dataElements, indicators). Repeatable. Required — whole-instance diffs are almost always noise.
* `--filter <str>`: Per-resource filter in `resource:property:operator:value` form. Repeatable. Example: `--filter dataElements:name:like:ANC` only compares data elements whose name contains &#x27;ANC&#x27;. Same DHIS2 filter DSL as `d2w metadata list --filter`.
* `--fields <str>`: DHIS2 field selector applied on both profiles. Defaults to &#x27;:owner&#x27; — the selector DHIS2 itself uses for cross-instance imports (preserves every field needed for a faithful round-trip).  [default: :owner]
* `--ignore <str>`: Additional fields to skip when deciding if an object changed. Repeatable. Defaults already cover DHIS2&#x27;s per-instance noise (lastUpdated, createdBy, access, ...). Common extensions for drift checks: `--ignore sharing --ignore translations`.
* `--show-uids`: List up to 5 offending UIDs per per-resource row.
* `--exit-on-drift`: Exit 1 when any object differs. CI-friendly (default is always exit 0).
* `--help`: Show this message and exit.

### `d2w metadata merge`

Export resources from one profile and import them into another.

Pairs with `d2w metadata diff-profiles` (which reads the same shape
of narrow resource slice + filters). Preview first with
`diff-profiles`, then apply the same `--resource` + `--filter` args
through `merge` to land the changes on the target.

Require `--resource` — a whole-instance merge would overwrite users,
org units, and incidental settings that staging and prod routinely
differ on for non-drift reasons.

`--dry-run` flips the target import into `importMode=VALIDATE`.
DHIS2 walks the bundle, reports conflicts + stats, and commits
nothing. Use to catch &quot;this object references a user UID that
doesn&#x27;t exist on the target&quot; before the real run.

**Usage**:

```console
$ d2w metadata merge [OPTIONS] {source_profile} {target_profile}
```

**Arguments**:

* `source_profile`: Source profile — the `--from` side of the merge.  [required]
* `target_profile`: Target profile — where the source&#x27;s resources land.  [required]

**Options**:

* `-r, --resource <str>`: Resource type to merge (e.g. dataElements, indicators). Repeatable. Required — whole-instance merges are almost never what you want.
* `--filter <str>`: Per-resource filter in `resource:property:operator:value` form. Repeatable. Same DSL as `d2w metadata list --filter` and `d2w metadata diff-profiles`.
* `--fields <str>`: DHIS2 field selector applied on the source export. Defaults to &#x27;:owner&#x27; (faithful round-trip).  [default: :owner]
* `--strategy <str>`: Import strategy — CREATE / UPDATE / CREATE_AND_UPDATE / DELETE (default: CREATE_AND_UPDATE).  [default: CREATE_AND_UPDATE]
* `--atomic <str>`: atomicMode — ALL / NONE (default: ALL; one broken object aborts the whole import).  [default: ALL]
* `--include-sharing / --skip-sharing`: Carry sharing blocks across. OFF by default — different instances typically have different user / group UIDs and sharing imports fail with false-positive conflicts.  [default: skip-sharing]
* `--dry-run`: Send `importMode=VALIDATE` to the target; reports conflicts + counts without committing.
* `--help`: Show this message and exit.

### `d2w metadata merge-bundle`

Import a saved bundle file into a target profile.

The bundle-source variant of `d2w metadata merge`: instead of
exporting from a source profile, read the bundle from disk. Useful
when the bundle came from a saved `metadata export`, was hand-crafted
by an operator, or was produced by a non-DHIS2 tool. All other
semantics match `merge` — atomic + sharing skipped by default,
`--dry-run` flips to `importMode=VALIDATE`.

**Usage**:

```console
$ d2w metadata merge-bundle [OPTIONS] {target_profile} {bundle}
```

**Arguments**:

* `target_profile`: Target profile — where the bundle&#x27;s resources land.  [required]
* `bundle`: Path to a JSON metadata bundle (the shape `GET /api/metadata` returns).  [required]

**Options**:

* `-r, --resource <str>`: Resource type to import from the bundle (e.g. dataElements). Repeatable. The bundle is filtered to these collections before the POST, so the count summary reports exactly what was written. Optional — when omitted, the whole bundle is imported.
* `--strategy <str>`: Import strategy — CREATE / UPDATE / CREATE_AND_UPDATE / DELETE (default: CREATE_AND_UPDATE).  [default: CREATE_AND_UPDATE]
* `--atomic <str>`: atomicMode — ALL / NONE (default: ALL; one broken object aborts the whole import).  [default: ALL]
* `--include-sharing / --skip-sharing`: Carry sharing blocks across. OFF by default — different instances typically have different user / group UIDs and sharing imports fail with false-positive conflicts.  [default: skip-sharing]
* `--dry-run`: Send `importMode=VALIDATE` to the target; reports conflicts + counts without committing.
* `--help`: Show this message and exit.

### `d2w metadata type`

Metadata resource types (the catalog).

**Usage**:

```console
$ d2w metadata type [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `ls`: List the metadata resource types exposed...
* `list`: List the metadata resource types exposed...

#### `d2w metadata type ls`

List the metadata resource types exposed by the connected DHIS2 instance.

**Usage**:

```console
$ d2w metadata type ls [OPTIONS]
```

**Options**:

* `--help`: Show this message and exit.

#### `d2w metadata type list`

List the metadata resource types exposed by the connected DHIS2 instance.

**Usage**:

```console
$ d2w metadata type list [OPTIONS]
```

**Options**:

* `--help`: Show this message and exit.

### `d2w metadata option-sets`

OptionSet workflows (get / find / sync).

**Usage**:

```console
$ d2w metadata option-sets [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `get`: Show one OptionSet with its options...
* `find`: Locate a single option inside a set by...
* `create`: Create an OptionSet (then add its options...
* `delete`: Delete an OptionSet by UID.
* `sync`: Idempotently sync an OptionSet to match a...
* `attributes`: External-system code mapping on Options...

#### `d2w metadata option-sets get`

Show one OptionSet with its options resolved inline.

**Usage**:

```console
$ d2w metadata option-sets get [OPTIONS] {uid_or_code}
```

**Arguments**:

* `uid_or_code`: OptionSet UID (11 chars) or business code.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w metadata option-sets find`

Locate a single option inside a set by code or name; exit 1 if no match.

**Usage**:

```console
$ d2w metadata option-sets find [OPTIONS]
```

**Options**:

* `--set <str>`: OptionSet UID or business code.  [required]
* `--code <str>`: Business code of the option to locate.
* `--name <str>`: Display name of the option (exact match).
* `--help`: Show this message and exit.

#### `d2w metadata option-sets create`

Create an OptionSet (then add its options with `options sync`).

**Usage**:

```console
$ d2w metadata option-sets create [OPTIONS]
```

**Options**:

* `--name <str>`: OptionSet name.  [required]
* `--value-type <str>`: DHIS2 ValueType, e.g. TEXT / NUMBER / INTEGER.  [required]
* `--code <str>`: Business code.
* `--uid <str>`: Explicit 11-char UID.
* `--help`: Show this message and exit.

#### `d2w metadata option-sets delete`

Delete an OptionSet by UID.

**Usage**:

```console
$ d2w metadata option-sets delete [OPTIONS] {uid}
```

**Arguments**:

* `uid`: OptionSet UID.  [required]

**Options**:

* `-y, --yes`: Skip the confirmation prompt.
* `--help`: Show this message and exit.

#### `d2w metadata option-sets sync`

Idempotently sync an OptionSet to match a JSON spec file.

The spec is a JSON array of `{code, name, sort_order?}` objects. Codes
not currently in the set get **added**; codes present but with changed
names or sort order get **updated**; exact matches are **skipped**.
Pass `--remove-missing` to also drop options whose code isn&#x27;t in the
spec. `--dry-run` previews the diff without writing.

**Usage**:

```console
$ d2w metadata option-sets sync [OPTIONS] {set_ref} {spec_file}
```

**Arguments**:

* `set_ref`: OptionSet UID or business code.  [required]
* `spec_file`: JSON file — list of `{code, name, sort_order?}` objects.  [required]

**Options**:

* `--remove-missing`: Also delete options whose code isn&#x27;t in the spec. Off by default — safer for partial refreshes.
* `--dry-run`: Compute the diff without writing anything.
* `--help`: Show this message and exit.

#### `d2w metadata option-sets attributes`

External-system code mapping on Options via Attribute values.

**Usage**:

```console
$ d2w metadata option-sets attributes [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `get`: Read one attribute value off an Option;...
* `set`: Set / replace an attribute value on an...
* `find`: Reverse lookup — find the Option whose...

##### `d2w metadata option-sets attributes get`

Read one attribute value off an Option; exit 1 if unset.

**Usage**:

```console
$ d2w metadata option-sets attributes get [OPTIONS] {option_uid} {attribute}
```

**Arguments**:

* `option_uid`: Option UID (11 chars).  [required]
* `attribute`: Attribute UID or business code (e.g. &#x27;SNOMED_CODE&#x27;).  [required]

**Options**:

* `--help`: Show this message and exit.

##### `d2w metadata option-sets attributes set`

Set / replace an attribute value on an Option.

Reads the full Option, merges the new value (replaces any prior value
for the same attribute UID), PUTs the payload back. DHIS2&#x27;s
attribute-value list is identity-keyed by attribute UID, so this is
idempotent — calling twice with the same value is a no-op.

**Usage**:

```console
$ d2w metadata option-sets attributes set [OPTIONS] {option_uid} {attribute} {value}
```

**Arguments**:

* `option_uid`: Option UID (11 chars).  [required]
* `attribute`: Attribute UID or business code (e.g. &#x27;SNOMED_CODE&#x27;).  [required]
* `value`: New attribute value.  [required]

**Options**:

* `--help`: Show this message and exit.

##### `d2w metadata option-sets attributes find`

Reverse lookup — find the Option whose attribute matches a value.

The killer integration helper: external systems know a SNOMED / ICD /
LOINC code; this command returns the DHIS2 Option it maps to. Exits 1
on miss with a stderr hint.

**Usage**:

```console
$ d2w metadata option-sets attributes find [OPTIONS]
```

**Options**:

* `--set <str>`: OptionSet UID or business code.  [required]
* `--attribute <str>`: Attribute UID or business code (e.g. &#x27;SNOMED_CODE&#x27;).  [required]
* `--value <str>`: Attribute value to match exactly.  [required]
* `--help`: Show this message and exit.

### `d2w metadata attributes`

Cross-resource AttributeValue workflows (get / set / delete / find).

**Usage**:

```console
$ d2w metadata attributes [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `get`: Read one attribute value off any resource;...
* `set`: Set / replace one attribute value on any...
* `delete`: Remove one attribute value from any...
* `find`: Reverse lookup across any resource — list...

#### `d2w metadata attributes get`

Read one attribute value off any resource; exit 1 if unset.

**Usage**:

```console
$ d2w metadata attributes get [OPTIONS] {resource} {resource_uid} {attribute}
```

**Arguments**:

* `resource`: Plural DHIS2 resource name (e.g. `dataElements`, `options`, `organisationUnits`).  [required]
* `resource_uid`: UID of the resource instance.  [required]
* `attribute`: Attribute UID or business code (e.g. `ICD10_CODE`).  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w metadata attributes set`

Set / replace one attribute value on any resource (read-merge-write).

**Usage**:

```console
$ d2w metadata attributes set [OPTIONS] {resource} {resource_uid} {attribute} {value}
```

**Arguments**:

* `resource`: Plural DHIS2 resource name.  [required]
* `resource_uid`: UID of the resource instance.  [required]
* `attribute`: Attribute UID or business code.  [required]
* `value`: New attribute value.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w metadata attributes delete`

Remove one attribute value from any resource; exit 0 regardless of whether it existed.

**Usage**:

```console
$ d2w metadata attributes delete [OPTIONS] {resource} {resource_uid} {attribute}
```

**Arguments**:

* `resource`: Plural DHIS2 resource name.  [required]
* `resource_uid`: UID of the resource instance.  [required]
* `attribute`: Attribute UID or business code.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w metadata attributes find`

Reverse lookup across any resource — list every UID whose attribute value matches.

Returns UIDs only (one per line) to keep the helper generic across
resource types. Pipe into `d2w metadata get &lt;resource&gt; &lt;uid&gt;` or
`d2w metadata list &lt;resource&gt; --filter id:in:[...]` for typed
follow-ups.

**Usage**:

```console
$ d2w metadata attributes find [OPTIONS] {resource} {attribute} {value}
```

**Arguments**:

* `resource`: Plural DHIS2 resource name.  [required]
* `attribute`: Attribute UID or business code.  [required]
* `value`: Attribute value to match exactly.  [required]

**Options**:

* `--filter <str>`: Extra DHIS2 filter constraints to narrow the search (e.g. `domainType:eq:AGGREGATE`). Repeatable.
* `--help`: Show this message and exit.

### `d2w metadata program-rules`

Program rule workflows (get / vars-for / validate / where-de-is-used).

**Usage**:

```console
$ d2w metadata program-rules [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `get`: Show one ProgramRule with its condition,...
* `vars-for`: List every `ProgramRuleVariable` in scope...
* `validate-expression`: Parse-check a program-rule condition...
* `where-de-is-used`: Impact analysis — list every rule whose...

#### `d2w metadata program-rules get`

Show one ProgramRule with its condition, priority, and every action.

**Usage**:

```console
$ d2w metadata program-rules get [OPTIONS] {rule_uid}
```

**Arguments**:

* `rule_uid`: ProgramRule UID.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w metadata program-rules vars-for`

List every `ProgramRuleVariable` in scope for a program, sorted by name.

**Usage**:

```console
$ d2w metadata program-rules vars-for [OPTIONS] {program_uid}
```

**Arguments**:

* `program_uid`: Program UID.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w metadata program-rules validate-expression`

Parse-check a program-rule condition expression.

DHIS2 doesn&#x27;t expose a dedicated program-rule expression validator —
the closest is the program-indicator parser (used by default here),
which enforces stricter `#{stage.de}` syntax than program rules
accept. For the common `#{variableName}` shorthand program rules
use, the PI validator flags &quot;Invalid Program Stage / DataElement
syntax&quot; — not a real error, just the parser mismatch. Trust a clean
OK as definitely valid; read the specific message on ERROR to
distinguish parser mismatches from real syntax problems.

**Usage**:

```console
$ d2w metadata program-rules validate-expression [OPTIONS] {expression}
```

**Arguments**:

* `expression`: Program-rule condition expression.  [required]

**Options**:

* `--context <str>`: Which DHIS2 expression parser to use: program-indicator (default), validation-rule, indicator, predictor, or generic.  [default: program-indicator]
* `--help`: Show this message and exit.

#### `d2w metadata program-rules where-de-is-used`

Impact analysis — list every rule whose actions reference this DataElement.

Useful before renaming / removing a DE: catches rules that&#x27;d stop
firing once the reference breaks. Exit 1 if nothing matches (safe
shorthand for `grep -q` pipelines).

**Usage**:

```console
$ d2w metadata program-rules where-de-is-used [OPTIONS] {data_element_uid}
```

**Arguments**:

* `data_element_uid`: DataElement UID.  [required]

**Options**:

* `--help`: Show this message and exit.

### `d2w metadata sql-views`

SQL view workflows (get / execute / refresh / adhoc).

**Usage**:

```console
$ d2w metadata sql-views [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `get`: Show one SqlView&#x27;s metadata + its stored...
* `execute`: Run a SqlView and render its rows as a...
* `refresh`: Refresh a MATERIALIZED_VIEW or lazily...
* `adhoc`: Register a throwaway SqlView from a .sql...

#### `d2w metadata sql-views get`

Show one SqlView&#x27;s metadata + its stored SQL body.

**Usage**:

```console
$ d2w metadata sql-views get [OPTIONS] {view_uid}
```

**Arguments**:

* `view_uid`: SqlView UID.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w metadata sql-views execute`

Run a SqlView and render its rows as a table, JSON array, or CSV.

**Usage**:

```console
$ d2w metadata sql-views execute [OPTIONS] {view_uid}
```

**Arguments**:

* `view_uid`: SqlView UID.  [required]

**Options**:

* `--var <str>`: `${name}` substitution for QUERY views, in `name:value` form. Repeatable. DHIS2 strips non-alphanumeric characters from values server-side — wildcards belong in the SQL.
* `--criteria <str>`: Column filter for VIEW / MATERIALIZED_VIEW results, in `column:value` form. Repeatable.
* `--format <str>`: Output format: table (default), json, or csv.  [default: table]
* `--help`: Show this message and exit.

#### `d2w metadata sql-views refresh`

Refresh a MATERIALIZED_VIEW or lazily create a VIEW&#x27;s DB object.

`POST /api/sqlViews/{uid}/execute` is idempotent for VIEW types — the
first call creates the Postgres view; subsequent calls are no-ops.
MATERIALIZED_VIEW types re-run the underlying SQL each call.

**Usage**:

```console
$ d2w metadata sql-views refresh [OPTIONS] {view_uid}
```

**Arguments**:

* `view_uid`: SqlView UID.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w metadata sql-views adhoc`

Register a throwaway SqlView from a .sql file, execute once, delete it on the way out.

Designed for iterating on SQL without leaving test metadata behind.
Subject to DHIS2&#x27;s SQL allowlist — for fully free-form queries, see
the Postgres injector example.

**Usage**:

```console
$ d2w metadata sql-views adhoc [OPTIONS] {name} {sql_path}
```

**Arguments**:

* `name`: Display name for the throwaway view.  [required]
* `sql_path`: .sql file containing the query body.  [required]

**Options**:

* `--type <str>`: SqlViewType — QUERY (default), VIEW, or MATERIALIZED_VIEW.  [default: QUERY]
* `--keep`: Leave the view in place afterwards instead of deleting.
* `--var <str>`: `${name}` substitution in `name:value` form. Repeatable.
* `--format <str>`: Output format: table (default), json, or csv.  [default: table]
* `--help`: Show this message and exit.

### `d2w metadata visualizations`

Visualization authoring (get / create / clone / delete).

**Usage**:

```console
$ d2w metadata visualizations [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `get`: Show one Visualization with axes + data...
* `create`: Create a Visualization from flags — one...
* `clone`: Clone an existing Visualization with a...
* `delete`: Delete a Visualization.

#### `d2w metadata visualizations get`

Show one Visualization with axes + data dimensions + period / ou selection.

**Usage**:

```console
$ d2w metadata visualizations get [OPTIONS] {viz_uid}
```

**Arguments**:

* `viz_uid`: Visualization UID.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w metadata visualizations create`

Create a Visualization from flags — one command, no hand-rolled JSON.

Uses `VisualizationSpec` defaults per chart type: LINE / COLUMN / BAR /
etc. default to rows= / columns= / filters=; PIVOT_TABLE
defaults to rows= / columns= / filters=; SINGLE_VALUE
collapses to columns= / filters=. Override any slot with
--category-dim / --series-dim / --filter-dim.

**Usage**:

```console
$ d2w metadata visualizations create [OPTIONS]
```

**Options**:

* `--name <str>`: Display name for the new Visualization.  [required]
* `--type <str>`: VisualizationType: LINE, COLUMN, STACKED_COLUMN, BAR, PIVOT_TABLE, SINGLE_VALUE, etc.  [required]
* `--data-element, --de <str>`: DataElement UID (repeat for multi-DE charts).  [required]
* `--period, --pe <str>`: Period ID (e.g. 202401, 2024Q1, 2024). Repeat for multi-period.  [required]
* `--org-unit, --ou <str>`: OrganisationUnit UID. Repeat for multi-OU.  [required]
* `--description <str>`: Optional long description.
* `--uid <str>`: Explicit UID (11 chars). Auto-generates when omitted.
* `--category-dim <str>`: Override category axis: dx / pe / ou.
* `--series-dim <str>`: Override series dimension: dx / pe / ou.
* `--filter-dim <str>`: Override filter dimension: dx / pe / ou.
* `--help`: Show this message and exit.

#### `d2w metadata visualizations clone`

Clone an existing Visualization with a fresh UID + new name.

**Usage**:

```console
$ d2w metadata visualizations clone [OPTIONS] {source_uid}
```

**Arguments**:

* `source_uid`: Source Visualization UID.  [required]

**Options**:

* `--new-name <str>`: Display name for the cloned Visualization.  [required]
* `--new-uid <str>`: Explicit UID for the clone (11 chars). Auto-generates when omitted.
* `--new-description <str>`: Override the source&#x27;s description on the clone.
* `--help`: Show this message and exit.

#### `d2w metadata visualizations delete`

Delete a Visualization.

**Usage**:

```console
$ d2w metadata visualizations delete [OPTIONS] {viz_uid}
```

**Arguments**:

* `viz_uid`: Visualization UID to delete.  [required]

**Options**:

* `-y, --yes`: Skip the confirmation prompt.
* `--help`: Show this message and exit.

### `d2w metadata dashboards`

Dashboard composition (get / add-item / remove-item).

**Usage**:

```console
$ d2w metadata dashboards [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `get`: Show one Dashboard with every...
* `add-item`: Add a Visualization or Map item to a...
* `remove-item`: Remove one dashboardItem by its UID.

#### `d2w metadata dashboards get`

Show one Dashboard with every dashboardItem resolved inline.

**Usage**:

```console
$ d2w metadata dashboards get [OPTIONS] {dashboard_uid}
```

**Arguments**:

* `dashboard_uid`: Dashboard UID.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w metadata dashboards add-item`

Add a Visualization or Map item to a dashboard.

Pass --viz to add a VISUALIZATION item or --map to add a MAP item
(exactly one required). Omit --x / --y / --width / --height to
auto-stack below existing items (full width); supply them when
you want side-by-side tiling.

**Usage**:

```console
$ d2w metadata dashboards add-item [OPTIONS] {dashboard_uid}
```

**Arguments**:

* `dashboard_uid`: Dashboard UID.  [required]

**Options**:

* `--viz <str>`: Visualization UID (mutually exclusive with --map).
* `--map <str>`: Map UID to add as a MAP-type dashboard item.
* `--x <int>`: Grid x coordinate (0-60). Auto-stacks when omitted.
* `--y <int>`: Grid y coordinate. Auto-stacks below existing when omitted.
* `--width <int>`: Slot width (1-60). Defaults to 60 when auto.
* `--height <int>`: Slot height. Defaults to 20 when auto.
* `--help`: Show this message and exit.

#### `d2w metadata dashboards remove-item`

Remove one dashboardItem by its UID.

**Usage**:

```console
$ d2w metadata dashboards remove-item [OPTIONS] {dashboard_uid} {item_uid}
```

**Arguments**:

* `dashboard_uid`: Dashboard UID.  [required]
* `item_uid`: DashboardItem UID to remove.  [required]

**Options**:

* `--help`: Show this message and exit.

### `d2w metadata maps`

Map authoring (get / create / clone / delete).

**Usage**:

```console
$ d2w metadata maps [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `get`: Show one Map with its viewport + every...
* `create`: Create a single-layer thematic choropleth...
* `clone`: Clone an existing Map with a fresh UID +...
* `delete`: Delete a Map.

#### `d2w metadata maps get`

Show one Map with its viewport + every mapViews layer.

**Usage**:

```console
$ d2w metadata maps get [OPTIONS] {map_uid}
```

**Arguments**:

* `map_uid`: Map UID.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w metadata maps create`

Create a single-layer thematic choropleth Map from flags.

Multi-layer maps need raw `Map` / `MapView` construction — use
`client.maps.create_from_spec(MapSpec(layers=[...]))` from the
library side and extend the spec to include boundary / facility
/ event layers.

**Usage**:

```console
$ d2w metadata maps create [OPTIONS]
```

**Options**:

* `--name <str>`: Display name for the new Map.  [required]
* `--data-element, --de <str>`: DataElement UID for the thematic layer.  [required]
* `--period, --pe <str>`: Period ID. Repeat for multi-period.  [required]
* `--org-unit, --ou <str>`: OrganisationUnit UID (usually the parent boundary). Repeat for multi.  [required]
* `--ou-level <int>`: OU hierarchy level(s) to render (e.g. 2 for provinces). Repeat for multi.  [required]
* `--description <str>`
* `--uid <str>`: Explicit UID (11 chars). Auto-generates when omitted.
* `--longitude <float>`: [default: 15.0]
* `--latitude <float>`: [default: 0.0]
* `--zoom <int>`: [default: 4]
* `--basemap <str>`: [default: openStreetMap]
* `--classes <int>`: Number of color classes on the choropleth.  [default: 5]
* `--color-low <str>`: Choropleth low-value colour (#hex).  [default: #fef0d9]
* `--color-high <str>`: Choropleth high-value colour (#hex).  [default: #b30000]
* `--help`: Show this message and exit.

#### `d2w metadata maps clone`

Clone an existing Map with a fresh UID + new name.

**Usage**:

```console
$ d2w metadata maps clone [OPTIONS] {source_uid}
```

**Arguments**:

* `source_uid`: Source Map UID.  [required]

**Options**:

* `--new-name <str>`: Display name for the cloned Map.  [required]
* `--new-uid <str>`: Explicit UID for the clone.
* `--new-description <str>`
* `--help`: Show this message and exit.

#### `d2w metadata maps delete`

Delete a Map.

**Usage**:

```console
$ d2w metadata maps delete [OPTIONS] {map_uid}
```

**Arguments**:

* `map_uid`: Map UID to delete.  [required]

**Options**:

* `-y, --yes`: Skip the confirmation prompt.
* `--help`: Show this message and exit.

### `d2w metadata data-elements`

DataElement authoring (get / create / rename / delete + legend-sets).

**Usage**:

```console
$ d2w metadata data-elements [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `get`: Show one DataElement with its references...
* `create`: Create a DataElement (defaults aggregate +...
* `rename`: Partial-update the label fields on a...
* `set-legend-sets`: Replace the legend-set refs on one...
* `delete`: Delete a DataElement — DHIS2 rejects...

#### `d2w metadata data-elements get`

Show one DataElement with its references resolved inline.

**Usage**:

```console
$ d2w metadata data-elements get [OPTIONS] {uid}
```

**Arguments**:

* `uid`: DataElement UID.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w metadata data-elements create`

Create a DataElement (defaults aggregate + SUM + instance default categoryCombo).

**Usage**:

```console
$ d2w metadata data-elements create [OPTIONS]
```

**Options**:

* `--name <str>`: Full name (&lt;=230 chars).  [required]
* `--short-name <str>`: Short name (&lt;=50 chars).  [required]
* `--value-type <str>`: DHIS2 ValueType, e.g. NUMBER / TEXT / INTEGER_POSITIVE.  [required]
* `--domain-type <str>`: AGGREGATE or TRACKER.  [default: AGGREGATE]
* `--aggregation-type <str>`: Default SUM.  [default: SUM]
* `--category-combo <str>`: CategoryCombo UID (defaults to the instance default).
* `--option-set <str>`: OptionSet UID.
* `--legend-set <str>`: LegendSet UID. Repeat for multiple.
* `--code <str>`: Business code.
* `--form-name <str>`: Form name override.
* `--description <str>`: Free text.
* `--uid <str>`: Explicit 11-char UID.
* `--zero-significant / --no-zero-significant`: Treat 0 as data, not absence.  [default: no-zero-significant]
* `--help`: Show this message and exit.

#### `d2w metadata data-elements rename`

Partial-update the label fields on a DataElement (read, mutate, PUT).

**Usage**:

```console
$ d2w metadata data-elements rename [OPTIONS] {uid}
```

**Arguments**:

* `uid`: DataElement UID.  [required]

**Options**:

* `--name <str>`: New name.
* `--short-name <str>`: New short name.
* `--form-name <str>`: New form name.
* `--description <str>`: New description.
* `--help`: Show this message and exit.

#### `d2w metadata data-elements set-legend-sets`

Replace the legend-set refs on one DataElement.

**Usage**:

```console
$ d2w metadata data-elements set-legend-sets [OPTIONS] {uid}
```

**Arguments**:

* `uid`: DataElement UID.  [required]

**Options**:

* `--legend-set <str>`: LegendSet UID to attach. Repeat for multiple. Empty list clears.  [required]
* `--help`: Show this message and exit.

#### `d2w metadata data-elements delete`

Delete a DataElement — DHIS2 rejects deletes on DEs with saved values.

**Usage**:

```console
$ d2w metadata data-elements delete [OPTIONS] {uid}
```

**Arguments**:

* `uid`: DataElement UID.  [required]

**Options**:

* `-y, --yes`: Skip confirmation.
* `--help`: Show this message and exit.

### `d2w metadata data-element-groups`

DataElementGroup workflows (get / members / create / add-members / remove-members / delete).

**Usage**:

```console
$ d2w metadata data-element-groups [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `get`: Show one group with its member refs and...
* `members`: Page through DataElements inside one group.
* `create`: Create an empty DataElementGroup.
* `add-members`: Add `--data-element` members via the...
* `remove-members`: Drop `--data-element` members via the...
* `delete`: Delete the grouping row — member DEs stay.

#### `d2w metadata data-element-groups get`

Show one group with its member refs and group-sets it belongs to.

**Usage**:

```console
$ d2w metadata data-element-groups get [OPTIONS] {uid}
```

**Arguments**:

* `uid`: DataElementGroup UID.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w metadata data-element-groups members`

Page through DataElements inside one group.

**Usage**:

```console
$ d2w metadata data-element-groups members [OPTIONS] {uid}
```

**Arguments**:

* `uid`: DataElementGroup UID.  [required]

**Options**:

* `--page <int>`: 1-based page number.  [default: 1]
* `--page-size <int>`: Rows per page.  [default: 50]
* `--help`: Show this message and exit.

#### `d2w metadata data-element-groups create`

Create an empty DataElementGroup.

**Usage**:

```console
$ d2w metadata data-element-groups create [OPTIONS]
```

**Options**:

* `--name <str>`: Full name.  [required]
* `--short-name <str>`: Short name.  [required]
* `--uid <str>`: Explicit 11-char UID.
* `--code <str>`: Business code.
* `--description <str>`: Free text.
* `--help`: Show this message and exit.

#### `d2w metadata data-element-groups add-members`

Add `--data-element` members via the per-item POST shortcut.

**Usage**:

```console
$ d2w metadata data-element-groups add-members [OPTIONS] {uid}
```

**Arguments**:

* `uid`: DataElementGroup UID.  [required]

**Options**:

* `-e, --data-element <str>`: DataElement UID to add. Repeat for multiple.  [required]
* `--help`: Show this message and exit.

#### `d2w metadata data-element-groups remove-members`

Drop `--data-element` members via the per-item DELETE shortcut.

**Usage**:

```console
$ d2w metadata data-element-groups remove-members [OPTIONS] {uid}
```

**Arguments**:

* `uid`: DataElementGroup UID.  [required]

**Options**:

* `-e, --data-element <str>`: DataElement UID to drop. Repeat for multiple.  [required]
* `--help`: Show this message and exit.

#### `d2w metadata data-element-groups delete`

Delete the grouping row — member DEs stay.

**Usage**:

```console
$ d2w metadata data-element-groups delete [OPTIONS] {uid}
```

**Arguments**:

* `uid`: DataElementGroup UID.  [required]

**Options**:

* `-y, --yes`: Skip confirmation.
* `--help`: Show this message and exit.

### `d2w metadata data-element-group-sets`

DataElementGroupSet workflows (get / create / add-groups / remove-groups / delete).

**Usage**:

```console
$ d2w metadata data-element-group-sets [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `get`: Show one group set with its groups.
* `create`: Create an empty DataElementGroupSet.
* `add-groups`: Add `--group` members to a group set.
* `remove-groups`: Drop `--group` members from a group set.
* `delete`: Delete a DataElementGroupSet — member...

#### `d2w metadata data-element-group-sets get`

Show one group set with its groups.

**Usage**:

```console
$ d2w metadata data-element-group-sets get [OPTIONS] {uid}
```

**Arguments**:

* `uid`: DataElementGroupSet UID.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w metadata data-element-group-sets create`

Create an empty DataElementGroupSet.

**Usage**:

```console
$ d2w metadata data-element-group-sets create [OPTIONS]
```

**Options**:

* `--name <str>`: Full name.  [required]
* `--short-name <str>`: Short name.  [required]
* `--uid <str>`: Explicit 11-char UID.
* `--code <str>`: Business code.
* `--description <str>`: Free text.
* `--compulsory / --not-compulsory`: Require DEs to land in exactly one member group.  [default: not-compulsory]
* `--data-dimension / --no-data-dimension`: Expose as analytics axis.  [default: data-dimension]
* `--help`: Show this message and exit.

#### `d2w metadata data-element-group-sets add-groups`

Add `--group` members to a group set.

**Usage**:

```console
$ d2w metadata data-element-group-sets add-groups [OPTIONS] {uid}
```

**Arguments**:

* `uid`: DataElementGroupSet UID.  [required]

**Options**:

* `--group <str>`: DataElementGroup UID to add. Repeat for multiple.  [required]
* `--help`: Show this message and exit.

#### `d2w metadata data-element-group-sets remove-groups`

Drop `--group` members from a group set.

**Usage**:

```console
$ d2w metadata data-element-group-sets remove-groups [OPTIONS] {uid}
```

**Arguments**:

* `uid`: DataElementGroupSet UID.  [required]

**Options**:

* `--group <str>`: DataElementGroup UID to drop. Repeat for multiple.  [required]
* `--help`: Show this message and exit.

#### `d2w metadata data-element-group-sets delete`

Delete a DataElementGroupSet — member groups stay.

**Usage**:

```console
$ d2w metadata data-element-group-sets delete [OPTIONS] {uid}
```

**Arguments**:

* `uid`: DataElementGroupSet UID.  [required]

**Options**:

* `-y, --yes`: Skip confirmation.
* `--help`: Show this message and exit.

### `d2w metadata indicators`

Indicator authoring (get / create / rename / validate-expression / delete).

**Usage**:

```console
$ d2w metadata indicators [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `get`: Show one Indicator with expression pair +...
* `create`: Create an Indicator from a numerator /...
* `rename`: Partial-update label fields on an Indicator.
* `validate-expression`: Parse-check one indicator expression —...
* `set-legend-sets`: Replace the legend-set refs on one Indicator.
* `delete`: Delete an Indicator — DHIS2 rejects...

#### `d2w metadata indicators get`

Show one Indicator with expression pair + indicatorType resolved inline.

**Usage**:

```console
$ d2w metadata indicators get [OPTIONS] {uid}
```

**Arguments**:

* `uid`: Indicator UID.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w metadata indicators create`

Create an Indicator from a numerator / denominator expression pair.

**Usage**:

```console
$ d2w metadata indicators create [OPTIONS]
```

**Options**:

* `--name <str>`: Full name (&lt;=230 chars).  [required]
* `--short-name <str>`: Short name (&lt;=50 chars).  [required]
* `--indicator-type <str>`: IndicatorType UID (pins the output scale).  [required]
* `--numerator <str>`: DHIS2 numerator expression, e.g. &#x27;#{deUid}&#x27;.  [required]
* `--denominator <str>`: DHIS2 denominator expression.  [required]
* `--numerator-desc <str>`: Human label for the numerator.
* `--denominator-desc <str>`: Human label for the denominator.
* `--legend-set <str>`: LegendSet UID. Repeat for multiple.
* `--annualized / --not-annualized`: Multiply by 365 / period days on aggregation.  [default: not-annualized]
* `--decimals <int>`: Rendered decimal places.
* `--code <str>`: Business code.
* `--description <str>`: Free text.
* `--uid <str>`: Explicit 11-char UID.
* `--help`: Show this message and exit.

#### `d2w metadata indicators rename`

Partial-update label fields on an Indicator.

**Usage**:

```console
$ d2w metadata indicators rename [OPTIONS] {uid}
```

**Arguments**:

* `uid`: Indicator UID.  [required]

**Options**:

* `--name <str>`: New name.
* `--short-name <str>`: New short name.
* `--description <str>`: New description.
* `--help`: Show this message and exit.

#### `d2w metadata indicators validate-expression`

Parse-check one indicator expression — fast pre-flight before create.

**Usage**:

```console
$ d2w metadata indicators validate-expression [OPTIONS] {expression}
```

**Arguments**:

* `expression`: Numerator / denominator expression to validate.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w metadata indicators set-legend-sets`

Replace the legend-set refs on one Indicator.

**Usage**:

```console
$ d2w metadata indicators set-legend-sets [OPTIONS] {uid}
```

**Arguments**:

* `uid`: Indicator UID.  [required]

**Options**:

* `--legend-set <str>`: LegendSet UID to attach. Empty list clears.  [required]
* `--help`: Show this message and exit.

#### `d2w metadata indicators delete`

Delete an Indicator — DHIS2 rejects deletes on indicators used in viz/dashboards.

**Usage**:

```console
$ d2w metadata indicators delete [OPTIONS] {uid}
```

**Arguments**:

* `uid`: Indicator UID.  [required]

**Options**:

* `-y, --yes`: Skip confirmation.
* `--help`: Show this message and exit.

### `d2w metadata indicator-groups`

IndicatorGroup workflows (get / members / create / add-members / remove-members / delete).

**Usage**:

```console
$ d2w metadata indicator-groups [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `get`: Show one group with its member refs.
* `members`: Page through Indicators inside one group.
* `create`: Create an empty IndicatorGroup.
* `add-members`: Add `--indicator` members via the per-item...
* `remove-members`: Drop `--indicator` members via the...
* `delete`: Delete the grouping row — member...

#### `d2w metadata indicator-groups get`

Show one group with its member refs.

**Usage**:

```console
$ d2w metadata indicator-groups get [OPTIONS] {uid}
```

**Arguments**:

* `uid`: IndicatorGroup UID.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w metadata indicator-groups members`

Page through Indicators inside one group.

**Usage**:

```console
$ d2w metadata indicator-groups members [OPTIONS] {uid}
```

**Arguments**:

* `uid`: IndicatorGroup UID.  [required]

**Options**:

* `--page <int>`: 1-based page number.  [default: 1]
* `--page-size <int>`: Rows per page.  [default: 50]
* `--help`: Show this message and exit.

#### `d2w metadata indicator-groups create`

Create an empty IndicatorGroup.

**Usage**:

```console
$ d2w metadata indicator-groups create [OPTIONS]
```

**Options**:

* `--name <str>`: Full name.  [required]
* `--short-name <str>`: Short name.  [required]
* `--uid <str>`: Explicit 11-char UID.
* `--code <str>`: Business code.
* `--description <str>`: Free text.
* `--help`: Show this message and exit.

#### `d2w metadata indicator-groups add-members`

Add `--indicator` members via the per-item POST shortcut.

**Usage**:

```console
$ d2w metadata indicator-groups add-members [OPTIONS] {uid}
```

**Arguments**:

* `uid`: IndicatorGroup UID.  [required]

**Options**:

* `-i, --indicator <str>`: Indicator UID to add. Repeat for multiple.  [required]
* `--help`: Show this message and exit.

#### `d2w metadata indicator-groups remove-members`

Drop `--indicator` members via the per-item DELETE shortcut.

**Usage**:

```console
$ d2w metadata indicator-groups remove-members [OPTIONS] {uid}
```

**Arguments**:

* `uid`: IndicatorGroup UID.  [required]

**Options**:

* `-i, --indicator <str>`: Indicator UID to drop. Repeat for multiple.  [required]
* `--help`: Show this message and exit.

#### `d2w metadata indicator-groups delete`

Delete the grouping row — member indicators stay.

**Usage**:

```console
$ d2w metadata indicator-groups delete [OPTIONS] {uid}
```

**Arguments**:

* `uid`: IndicatorGroup UID.  [required]

**Options**:

* `-y, --yes`: Skip confirmation.
* `--help`: Show this message and exit.

### `d2w metadata indicator-group-sets`

IndicatorGroupSet workflows (get / create / add-groups / remove-groups / delete).

**Usage**:

```console
$ d2w metadata indicator-group-sets [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `get`: Show one group set with its groups.
* `create`: Create an empty IndicatorGroupSet.
* `add-groups`: Add `--group` members to a group set.
* `remove-groups`: Drop `--group` members from a group set.
* `delete`: Delete an IndicatorGroupSet — member...

#### `d2w metadata indicator-group-sets get`

Show one group set with its groups.

**Usage**:

```console
$ d2w metadata indicator-group-sets get [OPTIONS] {uid}
```

**Arguments**:

* `uid`: IndicatorGroupSet UID.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w metadata indicator-group-sets create`

Create an empty IndicatorGroupSet.

**Usage**:

```console
$ d2w metadata indicator-group-sets create [OPTIONS]
```

**Options**:

* `--name <str>`: Full name.  [required]
* `--short-name <str>`: Short name.  [required]
* `--uid <str>`: Explicit 11-char UID.
* `--code <str>`: Business code.
* `--description <str>`: Free text.
* `--compulsory / --not-compulsory`: Require indicators to land in exactly one member group.  [default: not-compulsory]
* `--help`: Show this message and exit.

#### `d2w metadata indicator-group-sets add-groups`

Add `--group` members to a group set.

**Usage**:

```console
$ d2w metadata indicator-group-sets add-groups [OPTIONS] {uid}
```

**Arguments**:

* `uid`: IndicatorGroupSet UID.  [required]

**Options**:

* `--group <str>`: IndicatorGroup UID to add. Repeat for multiple.  [required]
* `--help`: Show this message and exit.

#### `d2w metadata indicator-group-sets remove-groups`

Drop `--group` members from a group set.

**Usage**:

```console
$ d2w metadata indicator-group-sets remove-groups [OPTIONS] {uid}
```

**Arguments**:

* `uid`: IndicatorGroupSet UID.  [required]

**Options**:

* `--group <str>`: IndicatorGroup UID to drop. Repeat for multiple.  [required]
* `--help`: Show this message and exit.

#### `d2w metadata indicator-group-sets delete`

Delete an IndicatorGroupSet — member groups stay.

**Usage**:

```console
$ d2w metadata indicator-group-sets delete [OPTIONS] {uid}
```

**Arguments**:

* `uid`: IndicatorGroupSet UID.  [required]

**Options**:

* `-y, --yes`: Skip confirmation.
* `--help`: Show this message and exit.

### `d2w metadata program-indicators`

ProgramIndicator authoring (get / create / rename / validate-expression / delete).

**Usage**:

```console
$ d2w metadata program-indicators [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `get`: Show one ProgramIndicator with its...
* `create`: Create a ProgramIndicator for a given...
* `rename`: Partial-update label fields on a...
* `validate-expression`: Parse-check one program-indicator...
* `set-legend-sets`: Replace the legend-set refs on one...
* `delete`: Delete a ProgramIndicator — DHIS2 rejects...

#### `d2w metadata program-indicators get`

Show one ProgramIndicator with its expression + filter resolved inline.

**Usage**:

```console
$ d2w metadata program-indicators get [OPTIONS] {uid}
```

**Arguments**:

* `uid`: ProgramIndicator UID.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w metadata program-indicators create`

Create a ProgramIndicator for a given program.

**Usage**:

```console
$ d2w metadata program-indicators create [OPTIONS]
```

**Options**:

* `--name <str>`: Full name (&lt;=230 chars).  [required]
* `--short-name <str>`: Short name (&lt;=50 chars).  [required]
* `--program <str>`: Program UID — required.  [required]
* `--expression <str>`: DHIS2 expression (e.g. &#x27;#{deUid}&#x27;).  [required]
* `--analytics-type <str>`: EVENT (default) or ENROLLMENT.  [default: EVENT]
* `--filter <str>`: Boolean filter expression narrowing the rows.
* `--description <str>`: Free text.
* `--aggregation-type <str>`: Override the default SUM.
* `--decimals <int>`: Rendered decimal places.
* `--legend-set <str>`: LegendSet UID. Repeat for multiple.
* `--code <str>`: Business code.
* `--uid <str>`: Explicit 11-char UID.
* `--help`: Show this message and exit.

#### `d2w metadata program-indicators rename`

Partial-update label fields on a ProgramIndicator.

**Usage**:

```console
$ d2w metadata program-indicators rename [OPTIONS] {uid}
```

**Arguments**:

* `uid`: ProgramIndicator UID.  [required]

**Options**:

* `--name <str>`: New name.
* `--short-name <str>`: New short name.
* `--description <str>`: New description.
* `--help`: Show this message and exit.

#### `d2w metadata program-indicators validate-expression`

Parse-check one program-indicator expression — fast pre-flight before create.

**Usage**:

```console
$ d2w metadata program-indicators validate-expression [OPTIONS] {expression}
```

**Arguments**:

* `expression`: Program-indicator expression to validate.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w metadata program-indicators set-legend-sets`

Replace the legend-set refs on one ProgramIndicator.

**Usage**:

```console
$ d2w metadata program-indicators set-legend-sets [OPTIONS] {uid}
```

**Arguments**:

* `uid`: ProgramIndicator UID.  [required]

**Options**:

* `--legend-set <str>`: LegendSet UID to attach. Empty list clears.  [required]
* `--help`: Show this message and exit.

#### `d2w metadata program-indicators delete`

Delete a ProgramIndicator — DHIS2 rejects deletes on PIs used in viz / dashboards.

**Usage**:

```console
$ d2w metadata program-indicators delete [OPTIONS] {uid}
```

**Arguments**:

* `uid`: ProgramIndicator UID.  [required]

**Options**:

* `-y, --yes`: Skip confirmation.
* `--help`: Show this message and exit.

### `d2w metadata program-indicator-groups`

ProgramIndicatorGroup workflows (get / members / create / add-members / remove-members / delete).

**Usage**:

```console
$ d2w metadata program-indicator-groups [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `get`: Show one group with its member refs.
* `members`: Page through ProgramIndicators inside one...
* `create`: Create an empty ProgramIndicatorGroup.
* `add-members`: Add `--program-indicator` members via the...
* `remove-members`: Drop `--program-indicator` members via the...
* `delete`: Delete the grouping row — member program...

#### `d2w metadata program-indicator-groups get`

Show one group with its member refs.

**Usage**:

```console
$ d2w metadata program-indicator-groups get [OPTIONS] {uid}
```

**Arguments**:

* `uid`: ProgramIndicatorGroup UID.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w metadata program-indicator-groups members`

Page through ProgramIndicators inside one group.

**Usage**:

```console
$ d2w metadata program-indicator-groups members [OPTIONS] {uid}
```

**Arguments**:

* `uid`: ProgramIndicatorGroup UID.  [required]

**Options**:

* `--page <int>`: 1-based page number.  [default: 1]
* `--page-size <int>`: Rows per page.  [default: 50]
* `--help`: Show this message and exit.

#### `d2w metadata program-indicator-groups create`

Create an empty ProgramIndicatorGroup.

**Usage**:

```console
$ d2w metadata program-indicator-groups create [OPTIONS]
```

**Options**:

* `--name <str>`: Full name.  [required]
* `--short-name <str>`: Short name.  [required]
* `--uid <str>`: Explicit 11-char UID.
* `--code <str>`: Business code.
* `--description <str>`: Free text.
* `--help`: Show this message and exit.

#### `d2w metadata program-indicator-groups add-members`

Add `--program-indicator` members via the per-item POST shortcut.

**Usage**:

```console
$ d2w metadata program-indicator-groups add-members [OPTIONS] {uid}
```

**Arguments**:

* `uid`: ProgramIndicatorGroup UID.  [required]

**Options**:

* `-i, --program-indicator <str>`: ProgramIndicator UID to add. Repeat for multiple.  [required]
* `--help`: Show this message and exit.

#### `d2w metadata program-indicator-groups remove-members`

Drop `--program-indicator` members via the per-item DELETE shortcut.

**Usage**:

```console
$ d2w metadata program-indicator-groups remove-members [OPTIONS] {uid}
```

**Arguments**:

* `uid`: ProgramIndicatorGroup UID.  [required]

**Options**:

* `-i, --program-indicator <str>`: ProgramIndicator UID to drop. Repeat for multiple.  [required]
* `--help`: Show this message and exit.

#### `d2w metadata program-indicator-groups delete`

Delete the grouping row — member program indicators stay.

**Usage**:

```console
$ d2w metadata program-indicator-groups delete [OPTIONS] {uid}
```

**Arguments**:

* `uid`: ProgramIndicatorGroup UID.  [required]

**Options**:

* `-y, --yes`: Skip confirmation.
* `--help`: Show this message and exit.

### `d2w metadata category-options`

CategoryOption authoring (get / create / rename / set-validity / delete).

**Usage**:

```console
$ d2w metadata category-options [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `get`: Show one CategoryOption with its...
* `create`: Create a CategoryOption.
* `rename`: Partial-update the label fields on a...
* `set-validity`: Set the `startDate` / `endDate` validity...
* `delete`: Delete a CategoryOption — DHIS2 rejects...

#### `d2w metadata category-options get`

Show one CategoryOption with its categories + groups inline.

**Usage**:

```console
$ d2w metadata category-options get [OPTIONS] {uid}
```

**Arguments**:

* `uid`: CategoryOption UID.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w metadata category-options create`

Create a CategoryOption. Omit `--start-date`/`--end-date` for an always-valid option.

**Usage**:

```console
$ d2w metadata category-options create [OPTIONS]
```

**Options**:

* `--name <str>`: Full name (&lt;=230 chars).  [required]
* `--short-name <str>`: Short name (&lt;=50 chars).  [required]
* `--code <str>`: Business code.
* `--description <str>`: Free text.
* `--form-name <str>`: Form name override.
* `--start-date <str>`: ISO-8601 date — beginning of validity window.
* `--end-date <str>`: ISO-8601 date — end of validity window.
* `--uid <str>`: Explicit 11-char UID.
* `--help`: Show this message and exit.

#### `d2w metadata category-options rename`

Partial-update the label fields on a CategoryOption.

**Usage**:

```console
$ d2w metadata category-options rename [OPTIONS] {uid}
```

**Arguments**:

* `uid`: CategoryOption UID.  [required]

**Options**:

* `--name <str>`: New name.
* `--short-name <str>`: New short name.
* `--form-name <str>`: New form name.
* `--description <str>`: New description.
* `--help`: Show this message and exit.

#### `d2w metadata category-options set-validity`

Set the `startDate` / `endDate` validity window on a CategoryOption.

**Usage**:

```console
$ d2w metadata category-options set-validity [OPTIONS] {uid}
```

**Arguments**:

* `uid`: CategoryOption UID.  [required]

**Options**:

* `--start-date <str>`: ISO-8601 date (empty to clear).
* `--end-date <str>`: ISO-8601 date (empty to clear).
* `--help`: Show this message and exit.

#### `d2w metadata category-options delete`

Delete a CategoryOption — DHIS2 rejects deletes on options in use.

**Usage**:

```console
$ d2w metadata category-options delete [OPTIONS] {uid}
```

**Arguments**:

* `uid`: CategoryOption UID.  [required]

**Options**:

* `-y, --yes`: Skip confirmation.
* `--help`: Show this message and exit.

### `d2w metadata category-option-groups`

CategoryOptionGroup workflows (get / members / create / add-members / remove-members / delete).

**Usage**:

```console
$ d2w metadata category-option-groups [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `get`: Show one group with its member + group-set...
* `members`: Page through CategoryOptions inside one...
* `create`: Create an empty CategoryOptionGroup.
* `add-members`: Add `--category-option` members via the...
* `remove-members`: Drop `--category-option` members via the...
* `delete`: Delete the grouping row — member category...

#### `d2w metadata category-option-groups get`

Show one group with its member + group-set refs.

**Usage**:

```console
$ d2w metadata category-option-groups get [OPTIONS] {uid}
```

**Arguments**:

* `uid`: CategoryOptionGroup UID.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w metadata category-option-groups members`

Page through CategoryOptions inside one group.

**Usage**:

```console
$ d2w metadata category-option-groups members [OPTIONS] {uid}
```

**Arguments**:

* `uid`: CategoryOptionGroup UID.  [required]

**Options**:

* `--page <int>`: 1-based page number.  [default: 1]
* `--page-size <int>`: Rows per page.  [default: 50]
* `--help`: Show this message and exit.

#### `d2w metadata category-option-groups create`

Create an empty CategoryOptionGroup.

**Usage**:

```console
$ d2w metadata category-option-groups create [OPTIONS]
```

**Options**:

* `--name <str>`: Full name.  [required]
* `--short-name <str>`: Short name.  [required]
* `--data-dimension-type <str>`: DISAGGREGATION (default) or ATTRIBUTE.  [default: DISAGGREGATION]
* `--uid <str>`: Explicit 11-char UID.
* `--code <str>`: Business code.
* `--description <str>`: Free text.
* `--help`: Show this message and exit.

#### `d2w metadata category-option-groups add-members`

Add `--category-option` members via the per-item POST shortcut.

**Usage**:

```console
$ d2w metadata category-option-groups add-members [OPTIONS] {uid}
```

**Arguments**:

* `uid`: CategoryOptionGroup UID.  [required]

**Options**:

* `-c, --category-option <str>`: CategoryOption UID to add. Repeat for multiple.  [required]
* `--help`: Show this message and exit.

#### `d2w metadata category-option-groups remove-members`

Drop `--category-option` members via the per-item DELETE shortcut.

**Usage**:

```console
$ d2w metadata category-option-groups remove-members [OPTIONS] {uid}
```

**Arguments**:

* `uid`: CategoryOptionGroup UID.  [required]

**Options**:

* `-c, --category-option <str>`: CategoryOption UID to drop. Repeat for multiple.  [required]
* `--help`: Show this message and exit.

#### `d2w metadata category-option-groups delete`

Delete the grouping row — member category options stay.

**Usage**:

```console
$ d2w metadata category-option-groups delete [OPTIONS] {uid}
```

**Arguments**:

* `uid`: CategoryOptionGroup UID.  [required]

**Options**:

* `-y, --yes`: Skip confirmation.
* `--help`: Show this message and exit.

### `d2w metadata category-option-group-sets`

CategoryOptionGroupSet workflows (get / create / add-groups / remove-groups / delete).

**Usage**:

```console
$ d2w metadata category-option-group-sets [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `get`: Show one group set with its groups.
* `create`: Create an empty CategoryOptionGroupSet.
* `add-groups`: Add `--group` members to a group set.
* `remove-groups`: Drop `--group` members from a group set.
* `delete`: Delete a CategoryOptionGroupSet — member...

#### `d2w metadata category-option-group-sets get`

Show one group set with its groups.

**Usage**:

```console
$ d2w metadata category-option-group-sets get [OPTIONS] {uid}
```

**Arguments**:

* `uid`: CategoryOptionGroupSet UID.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w metadata category-option-group-sets create`

Create an empty CategoryOptionGroupSet.

**Usage**:

```console
$ d2w metadata category-option-group-sets create [OPTIONS]
```

**Options**:

* `--name <str>`: Full name.  [required]
* `--short-name <str>`: Short name.  [required]
* `--data-dimension-type <str>`: DISAGGREGATION (default) or ATTRIBUTE.  [default: DISAGGREGATION]
* `--data-dimension / --no-data-dimension`: Expose as analytics axis.  [default: data-dimension]
* `--uid <str>`: Explicit 11-char UID.
* `--code <str>`: Business code.
* `--description <str>`: Free text.
* `--help`: Show this message and exit.

#### `d2w metadata category-option-group-sets add-groups`

Add `--group` members to a group set.

**Usage**:

```console
$ d2w metadata category-option-group-sets add-groups [OPTIONS] {uid}
```

**Arguments**:

* `uid`: CategoryOptionGroupSet UID.  [required]

**Options**:

* `--group <str>`: CategoryOptionGroup UID to add. Repeat for multiple.  [required]
* `--help`: Show this message and exit.

#### `d2w metadata category-option-group-sets remove-groups`

Drop `--group` members from a group set.

**Usage**:

```console
$ d2w metadata category-option-group-sets remove-groups [OPTIONS] {uid}
```

**Arguments**:

* `uid`: CategoryOptionGroupSet UID.  [required]

**Options**:

* `--group <str>`: CategoryOptionGroup UID to drop. Repeat for multiple.  [required]
* `--help`: Show this message and exit.

#### `d2w metadata category-option-group-sets delete`

Delete a CategoryOptionGroupSet — member groups stay.

**Usage**:

```console
$ d2w metadata category-option-group-sets delete [OPTIONS] {uid}
```

**Arguments**:

* `uid`: CategoryOptionGroupSet UID.  [required]

**Options**:

* `-y, --yes`: Skip confirmation.
* `--help`: Show this message and exit.

### `d2w metadata categories`

Category authoring (get / create / rename / add-option / remove-option / delete).

**Usage**:

```console
$ d2w metadata categories [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `get`: Show one Category with its options inline.
* `create`: Create a Category, optionally wiring...
* `rename`: Partial-update the label fields on a...
* `add-option`: Append a CategoryOption to this Category&#x27;s...
* `remove-option`: Remove a CategoryOption from this...
* `delete`: Delete a Category — DHIS2 rejects deletes...

#### `d2w metadata categories get`

Show one Category with its options inline.

**Usage**:

```console
$ d2w metadata categories get [OPTIONS] {uid}
```

**Arguments**:

* `uid`: Category UID.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w metadata categories create`

Create a Category, optionally wiring CategoryOption members on create.

**Usage**:

```console
$ d2w metadata categories create [OPTIONS]
```

**Options**:

* `--name <str>`: Full name (&lt;=230 chars).  [required]
* `--short-name <str>`: Short name (&lt;=50 chars).  [required]
* `--code <str>`: Business code.
* `--description <str>`: Free text.
* `--type <str>`: DISAGGREGATION (default) or ATTRIBUTE.  [default: DISAGGREGATION]
* `--option <str>`: CategoryOption UID to wire on create. Repeatable; order is preserved on save.
* `--uid <str>`: Explicit 11-char UID.
* `--help`: Show this message and exit.

#### `d2w metadata categories rename`

Partial-update the label fields on a Category.

**Usage**:

```console
$ d2w metadata categories rename [OPTIONS] {uid}
```

**Arguments**:

* `uid`: Category UID.  [required]

**Options**:

* `--name <str>`: New name.
* `--short-name <str>`: New short name.
* `--description <str>`: New description.
* `--help`: Show this message and exit.

#### `d2w metadata categories add-option`

Append a CategoryOption to this Category&#x27;s ordered membership.

**Usage**:

```console
$ d2w metadata categories add-option [OPTIONS] {uid} {option_uid}
```

**Arguments**:

* `uid`: Category UID.  [required]
* `option_uid`: CategoryOption UID to append.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w metadata categories remove-option`

Remove a CategoryOption from this Category&#x27;s membership.

**Usage**:

```console
$ d2w metadata categories remove-option [OPTIONS] {uid} {option_uid}
```

**Arguments**:

* `uid`: Category UID.  [required]
* `option_uid`: CategoryOption UID to remove.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w metadata categories delete`

Delete a Category — DHIS2 rejects deletes on categories referenced by a CategoryCombo.

**Usage**:

```console
$ d2w metadata categories delete [OPTIONS] {uid}
```

**Arguments**:

* `uid`: Category UID.  [required]

**Options**:

* `-y, --yes`: Skip confirmation.
* `--help`: Show this message and exit.

### `d2w metadata category-combos`

CategoryCombo authoring (get / create / rename / add-category / remove-category / wait-for-cocs / delete).

**Usage**:

```console
$ d2w metadata category-combos [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `get`: Show one CategoryCombo with its category +...
* `create`: Create a CategoryCombo with an ordered...
* `rename`: Partial-update label fields on a...
* `add-category`: Append a Category to this combo&#x27;s ordered...
* `remove-category`: Remove a Category from this combo&#x27;s...
* `wait-for-cocs`: Block until the COC matrix on this combo...
* `delete`: Delete a CategoryCombo — DHIS2 rejects the...
* `build`: One-pass create-or-reuse for the full...

#### `d2w metadata category-combos get`

Show one CategoryCombo with its category + COC refs inline.

**Usage**:

```console
$ d2w metadata category-combos get [OPTIONS] {uid}
```

**Arguments**:

* `uid`: CategoryCombo UID.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w metadata category-combos create`

Create a CategoryCombo with an ordered list of Category UIDs.

**Usage**:

```console
$ d2w metadata category-combos create [OPTIONS]
```

**Options**:

* `--name <str>`: Full name (&lt;=230 chars).  [required]
* `--category <str>`: Category UID. Repeatable; order is preserved on save and shapes the COC matrix.  [required]
* `--code <str>`: Business code.
* `--type <str>`: DISAGGREGATION (default) or ATTRIBUTE.  [default: DISAGGREGATION]
* `--skip-total / --with-total`: Omit the total aggregation row downstream tables draw from this combo.  [default: with-total]
* `--uid <str>`: Explicit 11-char UID.
* `--help`: Show this message and exit.

#### `d2w metadata category-combos rename`

Partial-update label fields on a CategoryCombo.

**Usage**:

```console
$ d2w metadata category-combos rename [OPTIONS] {uid}
```

**Arguments**:

* `uid`: CategoryCombo UID.  [required]

**Options**:

* `--name <str>`: New name.
* `--code <str>`: New code.
* `--help`: Show this message and exit.

#### `d2w metadata category-combos add-category`

Append a Category to this combo&#x27;s ordered membership.

DHIS2 regenerates the COC matrix server-side. Re-fetch the combo + use
`wait-for-cocs` if you need to block until the new matrix lands.

**Usage**:

```console
$ d2w metadata category-combos add-category [OPTIONS] {uid} {category_uid}
```

**Arguments**:

* `uid`: CategoryCombo UID.  [required]
* `category_uid`: Category UID to append.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w metadata category-combos remove-category`

Remove a Category from this combo&#x27;s membership.

**Usage**:

```console
$ d2w metadata category-combos remove-category [OPTIONS] {uid} {category_uid}
```

**Arguments**:

* `uid`: CategoryCombo UID.  [required]
* `category_uid`: Category UID to remove.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w metadata category-combos wait-for-cocs`

Block until the COC matrix on this combo reaches `--expected`.

Cold-start regen of a large combo can take tens of seconds, especially
under arm64 emulation. Use after `create` or `add-category` when the
next step depends on the matrix being ready.

**Usage**:

```console
$ d2w metadata category-combos wait-for-cocs [OPTIONS] {uid}
```

**Arguments**:

* `uid`: CategoryCombo UID.  [required]

**Options**:

* `--expected <int>`: Expected total of CategoryOptionCombos materialised by this combo.  [required]
* `--timeout <float>`: Seconds to wait before giving up (default 60).  [default: 60.0]
* `--poll <float>`: Seconds between polls (default 1).  [default: 1.0]
* `--help`: Show this message and exit.

#### `d2w metadata category-combos delete`

Delete a CategoryCombo — DHIS2 rejects the default combo + combos in use.

**Usage**:

```console
$ d2w metadata category-combos delete [OPTIONS] {uid}
```

**Arguments**:

* `uid`: CategoryCombo UID.  [required]

**Options**:

* `-y, --yes`: Skip confirmation.
* `--help`: Show this message and exit.

#### `d2w metadata category-combos build`

One-pass create-or-reuse for the full Category dimension stack.

Walks a declarative `CategoryComboBuildSpec`, ensuring every
`CategoryOption` -&gt; `Category` -&gt; `CategoryCombo` referenced exists
on the target. Idempotent — re-running the same spec is a no-op
modulo new options getting wired into existing categories. Polls
the COC matrix until the cross-product count lands.

Lookup is by `name` (DHIS2 enforces unique names on each layer).
Existing entries are reused; only missing entries get created.

**Usage**:

```console
$ d2w metadata category-combos build [OPTIONS]
```

**Options**:

* `--spec <str>`: Path to a JSON CategoryComboBuildSpec, or `-` to read from stdin. Shape: `{name, categories: [{name, options: [{name, ...}, ...]}, ...]}`.  [required]
* `--timeout <float>`: Seconds to wait for the COC matrix to settle (default 120).  [default: 120.0]
* `--poll <float>`: Seconds between matrix polls (default 1).  [default: 1.0]
* `--help`: Show this message and exit.

### `d2w metadata category-option-combos`

CategoryOptionCombo read access (get / list-for-combo). DHIS2 owns writes.

**Usage**:

```console
$ d2w metadata category-option-combos [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `get`: Show one CategoryOptionCombo with its...
* `list-for-combo`: List every CategoryOptionCombo...

#### `d2w metadata category-option-combos get`

Show one CategoryOptionCombo with its parent combo + option refs.

**Usage**:

```console
$ d2w metadata category-option-combos get [OPTIONS] {uid}
```

**Arguments**:

* `uid`: CategoryOptionCombo UID.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w metadata category-option-combos list-for-combo`

List every CategoryOptionCombo materialised by one CategoryCombo.

**Usage**:

```console
$ d2w metadata category-option-combos list-for-combo [OPTIONS] {combo_uid}
```

**Arguments**:

* `combo_uid`: CategoryCombo UID.  [required]

**Options**:

* `--help`: Show this message and exit.

### `d2w metadata data-sets`

DataSet authoring (get / create / rename / add-element / remove-element / delete).

**Usage**:

```console
$ d2w metadata data-sets [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `get`: Show one DataSet with its DSE + section +...
* `create`: Create a DataSet.
* `rename`: Partial-update the label fields on a DataSet.
* `add-element`: Attach a DataElement to the DataSet...
* `remove-element`: Detach a DataElement from the DataSet.
* `delete`: Delete a DataSet — DHIS2 rejects deletes...

#### `d2w metadata data-sets get`

Show one DataSet with its DSE + section + OU counts inline.

**Usage**:

```console
$ d2w metadata data-sets get [OPTIONS] {uid}
```

**Arguments**:

* `uid`: DataSet UID.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w metadata data-sets create`

Create a DataSet.

**Usage**:

```console
$ d2w metadata data-sets create [OPTIONS]
```

**Options**:

* `--name <str>`: Full name (&lt;=230 chars).  [required]
* `--short-name <str>`: Short name (&lt;=50 chars).  [required]
* `--period-type <str>`: Period type (Monthly, Weekly, Daily, Quarterly, Yearly, …).  [required]
* `-cc, --category-combo <str>`: CategoryCombo UID (defaults to the instance default).
* `--code <str>`: Business code.
* `--form-name <str>`: Form-name override.
* `--description <str>`: Free text.
* `--open-future-periods <int>`: Number of future periods open for entry.
* `--expiry-days <int>`: Days after period-end that entry remains open.
* `--timely-days <int>`: Days after period-start considered on-time.
* `--uid <str>`: Explicit 11-char UID.
* `--help`: Show this message and exit.

#### `d2w metadata data-sets rename`

Partial-update the label fields on a DataSet.

**Usage**:

```console
$ d2w metadata data-sets rename [OPTIONS] {uid}
```

**Arguments**:

* `uid`: DataSet UID.  [required]

**Options**:

* `--name <str>`: New name.
* `--short-name <str>`: New short name.
* `--form-name <str>`: New form name.
* `--description <str>`: New description.
* `--help`: Show this message and exit.

#### `d2w metadata data-sets add-element`

Attach a DataElement to the DataSet (optionally with a per-set CategoryCombo override).

**Usage**:

```console
$ d2w metadata data-sets add-element [OPTIONS] {data_set_uid} {data_element_uid}
```

**Arguments**:

* `data_set_uid`: DataSet UID.  [required]
* `data_element_uid`: DataElement UID to attach.  [required]

**Options**:

* `-cc, --category-combo <str>`: CategoryCombo UID override for this DSE.
* `--help`: Show this message and exit.

#### `d2w metadata data-sets remove-element`

Detach a DataElement from the DataSet.

**Usage**:

```console
$ d2w metadata data-sets remove-element [OPTIONS] {data_set_uid} {data_element_uid}
```

**Arguments**:

* `data_set_uid`: DataSet UID.  [required]
* `data_element_uid`: DataElement UID to detach.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w metadata data-sets delete`

Delete a DataSet — DHIS2 rejects deletes on DataSets with saved values.

**Usage**:

```console
$ d2w metadata data-sets delete [OPTIONS] {uid}
```

**Arguments**:

* `uid`: DataSet UID.  [required]

**Options**:

* `-y, --yes`: Skip confirmation.
* `--help`: Show this message and exit.

### `d2w metadata sections`

Section authoring (get / create / rename / add-element / remove-element / reorder / delete).

**Usage**:

```console
$ d2w metadata sections [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `get`: Show one Section with its ordered DE list...
* `create`: Create a Section attached to a DataSet.
* `rename`: Partial-update the label / sort-order...
* `add-element`: Append (or insert at `--position`) a...
* `remove-element`: Remove a DataElement from the Section...
* `reorder`: Replace the Section&#x27;s `dataElements` with...
* `delete`: Delete a Section — DEs stay on the parent...

#### `d2w metadata sections get`

Show one Section with its ordered DE list inline.

**Usage**:

```console
$ d2w metadata sections get [OPTIONS] {uid}
```

**Arguments**:

* `uid`: Section UID.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w metadata sections create`

Create a Section attached to a DataSet. Repeat `--data-element` to seed the ordered DE list.

**Usage**:

```console
$ d2w metadata sections create [OPTIONS]
```

**Options**:

* `--name <str>`: Section name (&lt;=230 chars).  [required]
* `-ds, --data-set <str>`: Parent DataSet UID.  [required]
* `--sort-order <int>`: Ordering within the DataSet (ascending).
* `--description <str>`: Free text.
* `--code <str>`: Business code.
* `-de, --data-element <str>`: DataElement UID (repeatable, order preserved).
* `-i, --indicator <str>`: Indicator UID to show in the side pane (repeatable).
* `--show-column-totals / --no-show-column-totals`: Render column totals.
* `--show-row-totals / --no-show-row-totals`: Render row totals.
* `--uid <str>`: Explicit 11-char UID.
* `--help`: Show this message and exit.

#### `d2w metadata sections rename`

Partial-update the label / sort-order fields on a Section.

**Usage**:

```console
$ d2w metadata sections rename [OPTIONS] {uid}
```

**Arguments**:

* `uid`: Section UID.  [required]

**Options**:

* `--name <str>`: New name.
* `--description <str>`: New description.
* `--sort-order <int>`: New sort order.
* `--help`: Show this message and exit.

#### `d2w metadata sections add-element`

Append (or insert at `--position`) a DataElement to the Section.

**Usage**:

```console
$ d2w metadata sections add-element [OPTIONS] {section_uid} {data_element_uid}
```

**Arguments**:

* `section_uid`: Section UID.  [required]
* `data_element_uid`: DataElement UID.  [required]

**Options**:

* `--position <int>`: 0-indexed insertion position. Omit to append.
* `--help`: Show this message and exit.

#### `d2w metadata sections remove-element`

Remove a DataElement from the Section (stays on the parent DataSet).

**Usage**:

```console
$ d2w metadata sections remove-element [OPTIONS] {section_uid} {data_element_uid}
```

**Arguments**:

* `section_uid`: Section UID.  [required]
* `data_element_uid`: DataElement UID.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w metadata sections reorder`

Replace the Section&#x27;s `dataElements` with exactly the given UIDs in order.

**Usage**:

```console
$ d2w metadata sections reorder [OPTIONS] {section_uid} {data_element_uids}...
```

**Arguments**:

* `section_uid`: Section UID.  [required]
* `data_element_uids...`: DataElement UIDs in the desired order.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w metadata sections delete`

Delete a Section — DEs stay on the parent DataSet.

**Usage**:

```console
$ d2w metadata sections delete [OPTIONS] {uid}
```

**Arguments**:

* `uid`: Section UID.  [required]

**Options**:

* `-y, --yes`: Skip confirmation.
* `--help`: Show this message and exit.

### `d2w metadata validation-rules`

ValidationRule authoring (get / create / rename / delete).

**Usage**:

```console
$ d2w metadata validation-rules [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `get`: Show one ValidationRule with both...
* `create`: Create a ValidationRule.
* `rename`: Partial-update the label fields on a...
* `delete`: Delete a ValidationRule — any outstanding...

#### `d2w metadata validation-rules get`

Show one ValidationRule with both expression sides inline.

**Usage**:

```console
$ d2w metadata validation-rules get [OPTIONS] {uid}
```

**Arguments**:

* `uid`: ValidationRule UID.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w metadata validation-rules create`

Create a ValidationRule.

**Usage**:

```console
$ d2w metadata validation-rules create [OPTIONS]
```

**Options**:

* `--name <str>`: Rule name (&lt;=230 chars).  [required]
* `--short-name <str>`: Short name (&lt;=50 chars).  [required]
* `--left <str>`: Left-side expression (e.g. #{deUid}).  [required]
* `--operator <str>`: Comparison operator.  [required]
* `--right <str>`: Right-side expression.  [required]
* `--period-type <str>`: Period type.  [default: Monthly]
* `--importance <str>`: LOW / MEDIUM / HIGH.  [default: MEDIUM]
* `--missing-value-strategy <str>`: How to treat absent operands.  [default: SKIP_IF_ALL_VALUES_MISSING]
* `--description <str>`: Free-text description.
* `--code <str>`: Business code.
* `--ou-level <int>`: OU depth (repeatable). E.g. `--ou-level 4` for facilities.
* `--uid <str>`: Explicit 11-char UID.
* `--help`: Show this message and exit.

#### `d2w metadata validation-rules rename`

Partial-update the label fields on a ValidationRule.

**Usage**:

```console
$ d2w metadata validation-rules rename [OPTIONS] {uid}
```

**Arguments**:

* `uid`: ValidationRule UID.  [required]

**Options**:

* `--name <str>`: New name.
* `--short-name <str>`: New short name.
* `--description <str>`: New description.
* `--help`: Show this message and exit.

#### `d2w metadata validation-rules delete`

Delete a ValidationRule — any outstanding results are purged.

**Usage**:

```console
$ d2w metadata validation-rules delete [OPTIONS] {uid}
```

**Arguments**:

* `uid`: ValidationRule UID.  [required]

**Options**:

* `-y, --yes`: Skip confirmation.
* `--help`: Show this message and exit.

### `d2w metadata validation-rule-groups`

ValidationRuleGroup workflows (get / members / create / add-members / remove-members / delete).

**Usage**:

```console
$ d2w metadata validation-rule-groups [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `get`: Show one group with its rule refs.
* `members`: Page through ValidationRules inside a group.
* `create`: Create an empty ValidationRuleGroup.
* `add-members`: Attach ValidationRules to a group.
* `remove-members`: Detach ValidationRules from a group.
* `delete`: Delete a ValidationRuleGroup — member...

#### `d2w metadata validation-rule-groups get`

Show one group with its rule refs.

**Usage**:

```console
$ d2w metadata validation-rule-groups get [OPTIONS] {uid}
```

**Arguments**:

* `uid`: ValidationRuleGroup UID.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w metadata validation-rule-groups members`

Page through ValidationRules inside a group.

**Usage**:

```console
$ d2w metadata validation-rule-groups members [OPTIONS] {uid}
```

**Arguments**:

* `uid`: ValidationRuleGroup UID.  [required]

**Options**:

* `--page <int>`: 1-based page.  [default: 1]
* `--page-size <int>`: Rows per page.  [default: 50]
* `--help`: Show this message and exit.

#### `d2w metadata validation-rule-groups create`

Create an empty ValidationRuleGroup.

**Usage**:

```console
$ d2w metadata validation-rule-groups create [OPTIONS]
```

**Options**:

* `--name <str>`: Group name.  [required]
* `--short-name <str>`: Short name.
* `--code <str>`: Business code.
* `--description <str>`: Free text.
* `--uid <str>`: Explicit 11-char UID.
* `--help`: Show this message and exit.

#### `d2w metadata validation-rule-groups add-members`

Attach ValidationRules to a group.

**Usage**:

```console
$ d2w metadata validation-rule-groups add-members [OPTIONS] {uid}
```

**Arguments**:

* `uid`: ValidationRuleGroup UID.  [required]

**Options**:

* `-r, --rule <str>`: ValidationRule UID (repeatable).  [required]
* `--help`: Show this message and exit.

#### `d2w metadata validation-rule-groups remove-members`

Detach ValidationRules from a group.

**Usage**:

```console
$ d2w metadata validation-rule-groups remove-members [OPTIONS] {uid}
```

**Arguments**:

* `uid`: ValidationRuleGroup UID.  [required]

**Options**:

* `-r, --rule <str>`: ValidationRule UID (repeatable).  [required]
* `--help`: Show this message and exit.

#### `d2w metadata validation-rule-groups delete`

Delete a ValidationRuleGroup — member rules stay.

**Usage**:

```console
$ d2w metadata validation-rule-groups delete [OPTIONS] {uid}
```

**Arguments**:

* `uid`: ValidationRuleGroup UID.  [required]

**Options**:

* `-y, --yes`: Skip confirmation.
* `--help`: Show this message and exit.

### `d2w metadata predictors`

Predictor authoring (get / create / rename / delete).

**Usage**:

```console
$ d2w metadata predictors [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `get`: Show one Predictor with generator + output...
* `create`: Create a Predictor.
* `rename`: Partial-update the label fields on a...
* `delete`: Delete a Predictor.

#### `d2w metadata predictors get`

Show one Predictor with generator + output inline.

**Usage**:

```console
$ d2w metadata predictors get [OPTIONS] {uid}
```

**Arguments**:

* `uid`: Predictor UID.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w metadata predictors create`

Create a Predictor.

**Usage**:

```console
$ d2w metadata predictors create [OPTIONS]
```

**Options**:

* `--name <str>`: Predictor name.  [required]
* `--short-name <str>`: Short name.  [required]
* `--expression <str>`: Generator expression (e.g. #{deUid}).  [required]
* `-o, --output <str>`: Output DataElement UID.  [required]
* `--period-type <str>`: Period type.  [default: Monthly]
* `--sequential <int>`: Sequential sample count (e.g. 3 for 3-month rolling).  [default: 3]
* `--annual <int>`: Annual sample count.  [default: 0]
* `--ou-level <str>`: OrganisationUnitLevel UID (repeatable).
* `--output-combo <str>`: Output CategoryOptionCombo UID.
* `--description <str>`: Free text.
* `--code <str>`: Business code.
* `--uid <str>`: Explicit 11-char UID.
* `--help`: Show this message and exit.

#### `d2w metadata predictors rename`

Partial-update the label fields on a Predictor.

**Usage**:

```console
$ d2w metadata predictors rename [OPTIONS] {uid}
```

**Arguments**:

* `uid`: Predictor UID.  [required]

**Options**:

* `--name <str>`: New name.
* `--short-name <str>`: New short name.
* `--description <str>`: New description.
* `--help`: Show this message and exit.

#### `d2w metadata predictors delete`

Delete a Predictor. DHIS2 keeps any data values it has already written.

**Usage**:

```console
$ d2w metadata predictors delete [OPTIONS] {uid}
```

**Arguments**:

* `uid`: Predictor UID.  [required]

**Options**:

* `-y, --yes`: Skip confirmation.
* `--help`: Show this message and exit.

### `d2w metadata predictor-groups`

PredictorGroup workflows (get / members / create / add-members / remove-members / delete).

**Usage**:

```console
$ d2w metadata predictor-groups [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `get`: Show one group with its predictor refs.
* `members`: Page through Predictors in a group.
* `create`: Create an empty PredictorGroup.
* `add-members`: Attach Predictors to a group.
* `remove-members`: Detach Predictors from a group.
* `delete`: Delete a PredictorGroup — member...

#### `d2w metadata predictor-groups get`

Show one group with its predictor refs.

**Usage**:

```console
$ d2w metadata predictor-groups get [OPTIONS] {uid}
```

**Arguments**:

* `uid`: PredictorGroup UID.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w metadata predictor-groups members`

Page through Predictors in a group.

**Usage**:

```console
$ d2w metadata predictor-groups members [OPTIONS] {uid}
```

**Arguments**:

* `uid`: PredictorGroup UID.  [required]

**Options**:

* `--page <int>`: 1-based page.  [default: 1]
* `--page-size <int>`: Rows per page.  [default: 50]
* `--help`: Show this message and exit.

#### `d2w metadata predictor-groups create`

Create an empty PredictorGroup.

**Usage**:

```console
$ d2w metadata predictor-groups create [OPTIONS]
```

**Options**:

* `--name <str>`: Group name.  [required]
* `--short-name <str>`: Short name.
* `--code <str>`: Business code.
* `--description <str>`: Free text.
* `--uid <str>`: Explicit 11-char UID.
* `--help`: Show this message and exit.

#### `d2w metadata predictor-groups add-members`

Attach Predictors to a group.

**Usage**:

```console
$ d2w metadata predictor-groups add-members [OPTIONS] {uid}
```

**Arguments**:

* `uid`: PredictorGroup UID.  [required]

**Options**:

* `-p, --predictor <str>`: Predictor UID (repeatable).  [required]
* `--help`: Show this message and exit.

#### `d2w metadata predictor-groups remove-members`

Detach Predictors from a group.

**Usage**:

```console
$ d2w metadata predictor-groups remove-members [OPTIONS] {uid}
```

**Arguments**:

* `uid`: PredictorGroup UID.  [required]

**Options**:

* `-p, --predictor <str>`: Predictor UID (repeatable).  [required]
* `--help`: Show this message and exit.

#### `d2w metadata predictor-groups delete`

Delete a PredictorGroup — member predictors stay.

**Usage**:

```console
$ d2w metadata predictor-groups delete [OPTIONS] {uid}
```

**Arguments**:

* `uid`: PredictorGroup UID.  [required]

**Options**:

* `-y, --yes`: Skip confirmation.
* `--help`: Show this message and exit.

### `d2w metadata tracked-entity-attributes`

TrackedEntityAttribute authoring (get / create / rename / delete).

**Usage**:

```console
$ d2w metadata tracked-entity-attributes [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `get`: Show one TrackedEntityAttribute with its...
* `create`: Create a TrackedEntityAttribute.
* `rename`: Partial-update the label fields on a...
* `delete`: Delete a TrackedEntityAttribute — DHIS2...

#### `d2w metadata tracked-entity-attributes get`

Show one TrackedEntityAttribute with its toggles inline.

**Usage**:

```console
$ d2w metadata tracked-entity-attributes get [OPTIONS] {uid}
```

**Arguments**:

* `uid`: TrackedEntityAttribute UID.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w metadata tracked-entity-attributes create`

Create a TrackedEntityAttribute.

**Usage**:

```console
$ d2w metadata tracked-entity-attributes create [OPTIONS]
```

**Options**:

* `--name <str>`: Attribute name (&lt;=230 chars).  [required]
* `--short-name <str>`: Short name (&lt;=50 chars).  [required]
* `--value-type <str>`: TEXT / NUMBER / DATE / …  [default: TEXT]
* `--aggregation-type <str>`: DHIS2 aggregation type.  [default: NONE]
* `--option-set <str>`: Constraining OptionSet UID.
* `--legend-set <str>`: LegendSet UID (repeatable).
* `--unique / --no-unique`: Unique across the instance.  [default: no-unique]
* `--generated / --no-generated`: Auto-generate via --pattern on the tracked entity register.  [default: no-generated]
* `--confidential / --no-confidential`: Sensitive.  [default: no-confidential]
* `--inherit / --no-inherit`: Inherit on the parent/child tracked entity link.  [default: no-inherit]
* `--display-in-list-no-program / --no-display-in-list-no-program`: Show in the list when no program is selected.  [default: no-display-in-list-no-program]
* `--orgunit-scope / --no-orgunit-scope`: Scope values to the capturing OU.  [default: no-orgunit-scope]
* `--pattern <str>`: Generator pattern (with --generated).
* `--field-mask <str>`: Input mask for the data-entry field.
* `--code <str>`: Business code.
* `--form-name <str>`: Form-name override.
* `--description <str>`: Free text.
* `--uid <str>`: Explicit 11-char UID.
* `--help`: Show this message and exit.

#### `d2w metadata tracked-entity-attributes rename`

Partial-update the label fields on a TrackedEntityAttribute.

**Usage**:

```console
$ d2w metadata tracked-entity-attributes rename [OPTIONS] {uid}
```

**Arguments**:

* `uid`: TrackedEntityAttribute UID.  [required]

**Options**:

* `--name <str>`: New name.
* `--short-name <str>`: New short name.
* `--form-name <str>`: New form name.
* `--description <str>`: New description.
* `--help`: Show this message and exit.

#### `d2w metadata tracked-entity-attributes delete`

Delete a TrackedEntityAttribute — DHIS2 rejects deletes on TEAs wired into a TET or program.

**Usage**:

```console
$ d2w metadata tracked-entity-attributes delete [OPTIONS] {uid}
```

**Arguments**:

* `uid`: TrackedEntityAttribute UID.  [required]

**Options**:

* `-y, --yes`: Skip confirmation.
* `--help`: Show this message and exit.

### `d2w metadata tracked-entity-types`

TrackedEntityType authoring (get / create / rename / add-attribute / remove-attribute / delete).

**Usage**:

```console
$ d2w metadata tracked-entity-types [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `get`: Show one TrackedEntityType with its...
* `create`: Create a TrackedEntityType.
* `rename`: Partial-update the label fields on a...
* `add-attribute`: Attach a TrackedEntityAttribute to a...
* `remove-attribute`: Detach a TrackedEntityAttribute from a...
* `delete`: Delete a TrackedEntityType — DHIS2 rejects...

#### `d2w metadata tracked-entity-types get`

Show one TrackedEntityType with its attribute link-table counts.

**Usage**:

```console
$ d2w metadata tracked-entity-types get [OPTIONS] {uid}
```

**Arguments**:

* `uid`: TrackedEntityType UID.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w metadata tracked-entity-types create`

Create a TrackedEntityType.

**Usage**:

```console
$ d2w metadata tracked-entity-types create [OPTIONS]
```

**Options**:

* `--name <str>`: TET name (&lt;=230 chars).  [required]
* `--short-name <str>`: Short name (&lt;=50 chars).  [required]
* `--description <str>`: Free text.
* `--code <str>`: Business code.
* `--form-name <str>`: Form-name override.
* `--allow-audit-log / --no-allow-audit-log`: Enable the per-tracked-entity audit trail.
* `--feature-type <str>`: NONE / POINT / POLYGON — geometry captured per tracked entity.
* `--min-attrs <int>`: Min attributes required to search tracked entities.
* `--max-tei <int>`: Max tracked entity count to return per search.
* `--uid <str>`: Explicit 11-char UID.
* `--help`: Show this message and exit.

#### `d2w metadata tracked-entity-types rename`

Partial-update the label fields on a TrackedEntityType.

**Usage**:

```console
$ d2w metadata tracked-entity-types rename [OPTIONS] {uid}
```

**Arguments**:

* `uid`: TrackedEntityType UID.  [required]

**Options**:

* `--name <str>`: New name.
* `--short-name <str>`: New short name.
* `--form-name <str>`: New form name.
* `--description <str>`: New description.
* `--help`: Show this message and exit.

#### `d2w metadata tracked-entity-types add-attribute`

Attach a TrackedEntityAttribute to a TrackedEntityType.

**Usage**:

```console
$ d2w metadata tracked-entity-types add-attribute [OPTIONS] {tet_uid} {attribute_uid}
```

**Arguments**:

* `tet_uid`: TrackedEntityType UID.  [required]
* `attribute_uid`: TrackedEntityAttribute UID to wire in.  [required]

**Options**:

* `--mandatory / --no-mandatory`: Require on enrollment.  [default: no-mandatory]
* `--searchable / --no-searchable`: Include in tracked entity search.  [default: no-searchable]
* `--display-in-list / --no-display-in-list`: Show in the enrolled tracked entity list.  [default: display-in-list]
* `--help`: Show this message and exit.

#### `d2w metadata tracked-entity-types remove-attribute`

Detach a TrackedEntityAttribute from a TrackedEntityType.

**Usage**:

```console
$ d2w metadata tracked-entity-types remove-attribute [OPTIONS] {tet_uid} {attribute_uid}
```

**Arguments**:

* `tet_uid`: TrackedEntityType UID.  [required]
* `attribute_uid`: TrackedEntityAttribute UID to detach.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w metadata tracked-entity-types delete`

Delete a TrackedEntityType — DHIS2 rejects deletes on types in use by enrolled tracked entities.

**Usage**:

```console
$ d2w metadata tracked-entity-types delete [OPTIONS] {uid}
```

**Arguments**:

* `uid`: TrackedEntityType UID.  [required]

**Options**:

* `-y, --yes`: Skip confirmation.
* `--help`: Show this message and exit.

### `d2w metadata programs`

Program authoring (get / create / rename / add-attribute / remove-attribute / add-to-ou / remove-from-ou / delete).

**Usage**:

```console
$ d2w metadata programs [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `get`: Show one Program with counts inline.
* `create`: Create a Program.
* `rename`: Partial-update the label fields on a Program.
* `add-attribute`: Attach a TrackedEntityAttribute to the...
* `remove-attribute`: Detach a TrackedEntityAttribute from the...
* `add-to-ou`: Scope the Program to another...
* `remove-from-ou`: Drop an OrganisationUnit from the...
* `delete`: Delete a Program — DHIS2 rejects deletes...

#### `d2w metadata programs get`

Show one Program with counts inline.

**Usage**:

```console
$ d2w metadata programs get [OPTIONS] {uid}
```

**Arguments**:

* `uid`: Program UID.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w metadata programs create`

Create a Program. `--program-type WITH_REGISTRATION` requires `--tracked-entity-type`.

**Usage**:

```console
$ d2w metadata programs create [OPTIONS]
```

**Options**:

* `--name <str>`: Program name (&lt;=230 chars).  [required]
* `--short-name <str>`: Short name (&lt;=50 chars).  [required]
* `--program-type <str>`: WITH_REGISTRATION (tracker) or WITHOUT_REGISTRATION (event).  [default: WITH_REGISTRATION]
* `-tet, --tracked-entity-type <str>`: TET UID. Required for WITH_REGISTRATION.
* `-cc, --category-combo <str>`: CategoryCombo UID (defaults to the instance default).
* `--description <str>`: Free text.
* `--code <str>`: Business code.
* `--form-name <str>`: Form-name override.
* `--display-incident-date / --no-display-incident-date`: Capture an incident date.
* `--enrollment-date-label <str>`: Custom enrollment-date label.
* `--incident-date-label <str>`: Custom incident-date label.
* `--feature-type <str>`: Geometry captured per enrollment (NONE / POINT / POLYGON).
* `--only-enroll-once / --no-only-enroll-once`: Block re-enrollment of the same tracked entity.
* `--expiry-days <int>`: Days after which enrollments expire for edit.
* `--min-attrs <int>`: Min attributes required for tracked entity search.
* `--max-tei <int>`: Max tracked entity count per search.
* `--use-first-stage-during-registration / --no-use-first-stage-during-registration`: Run the first ProgramStage inside the enrollment flow.
* `--uid <str>`: Explicit 11-char UID.
* `--help`: Show this message and exit.

#### `d2w metadata programs rename`

Partial-update the label fields on a Program.

**Usage**:

```console
$ d2w metadata programs rename [OPTIONS] {uid}
```

**Arguments**:

* `uid`: Program UID.  [required]

**Options**:

* `--name <str>`: New name.
* `--short-name <str>`: New short name.
* `--form-name <str>`: New form name.
* `--description <str>`: New description.
* `--help`: Show this message and exit.

#### `d2w metadata programs add-attribute`

Attach a TrackedEntityAttribute to the Program&#x27;s enrollment form.

**Usage**:

```console
$ d2w metadata programs add-attribute [OPTIONS] {program_uid} {attribute_uid}
```

**Arguments**:

* `program_uid`: Program UID.  [required]
* `attribute_uid`: TrackedEntityAttribute UID.  [required]

**Options**:

* `--mandatory / --no-mandatory`: Require on enrollment.  [default: no-mandatory]
* `--searchable / --no-searchable`: Include in search.  [default: no-searchable]
* `--display-in-list / --no-display-in-list`: Show in the enrolled tracked entity list.  [default: display-in-list]
* `--sort-order <int>`: Position on enrollment form.
* `--allow-future-date / --no-allow-future-date`: Permit dates past today.  [default: no-allow-future-date]
* `--render-options-as-radio / --no-render-options-as-radio`: Render option-set choices as radios instead of a dropdown.  [default: no-render-options-as-radio]
* `--help`: Show this message and exit.

#### `d2w metadata programs remove-attribute`

Detach a TrackedEntityAttribute from the Program&#x27;s enrollment form.

**Usage**:

```console
$ d2w metadata programs remove-attribute [OPTIONS] {program_uid} {attribute_uid}
```

**Arguments**:

* `program_uid`: Program UID.  [required]
* `attribute_uid`: TrackedEntityAttribute UID.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w metadata programs add-to-ou`

Scope the Program to another OrganisationUnit.

**Usage**:

```console
$ d2w metadata programs add-to-ou [OPTIONS] {program_uid} {organisation_unit_uid}
```

**Arguments**:

* `program_uid`: Program UID.  [required]
* `organisation_unit_uid`: OrganisationUnit UID.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w metadata programs remove-from-ou`

Drop an OrganisationUnit from the Program&#x27;s scope.

**Usage**:

```console
$ d2w metadata programs remove-from-ou [OPTIONS] {program_uid} {organisation_unit_uid}
```

**Arguments**:

* `program_uid`: Program UID.  [required]
* `organisation_unit_uid`: OrganisationUnit UID.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w metadata programs delete`

Delete a Program — DHIS2 rejects deletes on programs with enrollments or events.

**Usage**:

```console
$ d2w metadata programs delete [OPTIONS] {uid}
```

**Arguments**:

* `uid`: Program UID.  [required]

**Options**:

* `-y, --yes`: Skip confirmation.
* `--help`: Show this message and exit.

### `d2w metadata program-stages`

ProgramStage authoring (get / create / rename / add-element / remove-element / reorder / delete).

**Usage**:

```console
$ d2w metadata program-stages [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `get`: Show one ProgramStage with its PSDE list...
* `create`: Create a ProgramStage under `--program`.
* `rename`: Partial-update the label fields on a...
* `add-element`: Attach a DataElement to the ProgramStage.
* `remove-element`: Detach a DataElement from the ProgramStage.
* `reorder`: Replace the ProgramStage&#x27;s PSDE list with...
* `delete`: Delete a ProgramStage — DHIS2 rejects...

#### `d2w metadata program-stages get`

Show one ProgramStage with its PSDE list summary inline.

**Usage**:

```console
$ d2w metadata program-stages get [OPTIONS] {uid}
```

**Arguments**:

* `uid`: ProgramStage UID.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w metadata program-stages create`

Create a ProgramStage under `--program`.

**Usage**:

```console
$ d2w metadata program-stages create [OPTIONS]
```

**Options**:

* `--name <str>`: ProgramStage name (&lt;=230 chars).  [required]
* `-p, --program <str>`: Parent Program UID.  [required]
* `--short-name <str>`: Short name.
* `--description <str>`: Free text.
* `--code <str>`: Business code.
* `--sort-order <int>`: Stage order inside the Program.
* `--repeatable / --no-repeatable`: Allow the stage to reoccur within one enrollment.
* `--auto-generate-event / --no-auto-generate-event`: Auto-create an event when the enrollment starts.
* `--generated-by-enrollment-date / --no-generated-by-enrollment-date`: Base due-date math on enrollment date (vs incident date).
* `--feature-type <str>`: Geometry captured per event (NONE / POINT / POLYGON).
* `--period-type <str>`: Period type for scheduled events.
* `--validation-strategy <str>`: ON_COMPLETE / ON_UPDATE_AND_INSERT.
* `--min-days <int>`: Minimum days from enrollment start before the stage opens.
* `--standard-interval <int>`: Default days between scheduled repeats.
* `--uid <str>`: Explicit 11-char UID.
* `--help`: Show this message and exit.

#### `d2w metadata program-stages rename`

Partial-update the label fields on a ProgramStage.

**Usage**:

```console
$ d2w metadata program-stages rename [OPTIONS] {uid}
```

**Arguments**:

* `uid`: ProgramStage UID.  [required]

**Options**:

* `--name <str>`: New name.
* `--short-name <str>`: New short name.
* `--form-name <str>`: New form name.
* `--description <str>`: New description.
* `--help`: Show this message and exit.

#### `d2w metadata program-stages add-element`

Attach a DataElement to the ProgramStage.

**Usage**:

```console
$ d2w metadata program-stages add-element [OPTIONS] {stage_uid} {data_element_uid}
```

**Arguments**:

* `stage_uid`: ProgramStage UID.  [required]
* `data_element_uid`: DataElement UID to attach.  [required]

**Options**:

* `--compulsory / --no-compulsory`: Required on save.  [default: no-compulsory]
* `--allow-future-date / --no-allow-future-date`: Permit dates past today.  [default: no-allow-future-date]
* `--display-in-reports / --no-display-in-reports`: Show in event reports.  [default: display-in-reports]
* `--allow-provided-elsewhere / --no-allow-provided-elsewhere`: Mark the value as provided by a different OU.  [default: no-allow-provided-elsewhere]
* `--render-options-as-radio / --no-render-options-as-radio`: Render option-set picklists as radios.  [default: no-render-options-as-radio]
* `--sort-order <int>`: Position inside the stage data-entry form.
* `--help`: Show this message and exit.

#### `d2w metadata program-stages remove-element`

Detach a DataElement from the ProgramStage.

**Usage**:

```console
$ d2w metadata program-stages remove-element [OPTIONS] {stage_uid} {data_element_uid}
```

**Arguments**:

* `stage_uid`: ProgramStage UID.  [required]
* `data_element_uid`: DataElement UID.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w metadata program-stages reorder`

Replace the ProgramStage&#x27;s PSDE list with exactly the given DE UIDs in order.

**Usage**:

```console
$ d2w metadata program-stages reorder [OPTIONS] {stage_uid} {data_element_uids}...
```

**Arguments**:

* `stage_uid`: ProgramStage UID.  [required]
* `data_element_uids...`: DataElement UIDs in the desired order.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w metadata program-stages delete`

Delete a ProgramStage — DHIS2 rejects deletes on stages with recorded events.

**Usage**:

```console
$ d2w metadata program-stages delete [OPTIONS] {uid}
```

**Arguments**:

* `uid`: ProgramStage UID.  [required]

**Options**:

* `-y, --yes`: Skip confirmation.
* `--help`: Show this message and exit.

### `d2w metadata organisation-units`

OrganisationUnit hierarchy workflows (get / tree / create / move / delete).

**Usage**:

```console
$ d2w metadata organisation-units [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `get`: Show one OU with parent + core hierarchy...
* `tree`: Render a bounded-depth subtree indented by...
* `create`: Create a child OU under `parent_uid`.
* `move`: Reparent an OU.
* `delete`: Delete an OU.

#### `d2w metadata organisation-units get`

Show one OU with parent + core hierarchy fields.

**Usage**:

```console
$ d2w metadata organisation-units get [OPTIONS] {uid}
```

**Arguments**:

* `uid`: OrganisationUnit UID.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w metadata organisation-units tree`

Render a bounded-depth subtree indented by hierarchy level.

**Usage**:

```console
$ d2w metadata organisation-units tree [OPTIONS] {root_uid}
```

**Arguments**:

* `root_uid`: Root OU UID — render this + descendants.  [required]

**Options**:

* `--max-depth <int>`: Depth of descendants to include (0 = just the root).  [default: 3]
* `--help`: Show this message and exit.

#### `d2w metadata organisation-units create`

Create a child OU under `parent_uid`.

**Usage**:

```console
$ d2w metadata organisation-units create [OPTIONS] {parent_uid}
```

**Arguments**:

* `parent_uid`: Parent OU UID to create under.  [required]

**Options**:

* `--name <str>`: Full name (&lt;=230 chars).  [required]
* `--short-name <str>`: Short name (&lt;=50 chars).  [required]
* `--opening-date <str>`: ISO-8601 date, e.g. 2024-01-01.  [required]
* `--uid <str>`: Explicit 11-char UID (generated when omitted).
* `--code <str>`: Business code.
* `--description <str>`: Free-text description.
* `--help`: Show this message and exit.

#### `d2w metadata organisation-units move`

Reparent an OU. DHIS2 recomputes `path` + `hierarchyLevel`.

**Usage**:

```console
$ d2w metadata organisation-units move [OPTIONS] {uid} {new_parent_uid}
```

**Arguments**:

* `uid`: OU UID to reparent.  [required]
* `new_parent_uid`: New parent OU UID.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w metadata organisation-units delete`

Delete an OU. DHIS2 rejects deletes on units with children or data.

**Usage**:

```console
$ d2w metadata organisation-units delete [OPTIONS] {uid}
```

**Arguments**:

* `uid`: OU UID to delete.  [required]

**Options**:

* `-y, --yes`: Skip the confirmation prompt.
* `--help`: Show this message and exit.

### `d2w metadata organisation-unit-groups`

OrganisationUnitGroup workflows (get / members / create / add-members / remove-members / delete).

**Usage**:

```console
$ d2w metadata organisation-unit-groups [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `get`: Show one group with its member refs and...
* `members`: Page through the OUs inside one group.
* `create`: Create an empty OrganisationUnitGroup.
* `add-members`: Add `--ou` members to a group via the...
* `remove-members`: Drop `--ou` members from a group via the...
* `delete`: Delete an OrganisationUnitGroup — members...

#### `d2w metadata organisation-unit-groups get`

Show one group with its member refs and the group-sets it belongs to.

**Usage**:

```console
$ d2w metadata organisation-unit-groups get [OPTIONS] {uid}
```

**Arguments**:

* `uid`: OrganisationUnitGroup UID.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w metadata organisation-unit-groups members`

Page through the OUs inside one group.

**Usage**:

```console
$ d2w metadata organisation-unit-groups members [OPTIONS] {uid}
```

**Arguments**:

* `uid`: OrganisationUnitGroup UID.  [required]

**Options**:

* `--page <int>`: 1-based page number.  [default: 1]
* `--page-size <int>`: Rows per page.  [default: 50]
* `--help`: Show this message and exit.

#### `d2w metadata organisation-unit-groups create`

Create an empty OrganisationUnitGroup.

**Usage**:

```console
$ d2w metadata organisation-unit-groups create [OPTIONS]
```

**Options**:

* `--name <str>`: Full name (&lt;=230 chars, unique).  [required]
* `--short-name <str>`: Short name (&lt;=50 chars, unique).  [required]
* `--uid <str>`: Explicit 11-char UID (generated when omitted).
* `--code <str>`: Business code.
* `--description <str>`: Free-text description.
* `--color <str>`: Hex colour (#RRGGBB).
* `--help`: Show this message and exit.

#### `d2w metadata organisation-unit-groups add-members`

Add `--ou` members to a group via the per-item POST shortcut.

**Usage**:

```console
$ d2w metadata organisation-unit-groups add-members [OPTIONS] {uid}
```

**Arguments**:

* `uid`: OrganisationUnitGroup UID.  [required]

**Options**:

* `--ou <str>`: OU UID to add. Repeat for multiple.  [required]
* `--help`: Show this message and exit.

#### `d2w metadata organisation-unit-groups remove-members`

Drop `--ou` members from a group via the per-item DELETE shortcut.

**Usage**:

```console
$ d2w metadata organisation-unit-groups remove-members [OPTIONS] {uid}
```

**Arguments**:

* `uid`: OrganisationUnitGroup UID.  [required]

**Options**:

* `--ou <str>`: OU UID to remove. Repeat for multiple.  [required]
* `--help`: Show this message and exit.

#### `d2w metadata organisation-unit-groups delete`

Delete an OrganisationUnitGroup — members stay.

**Usage**:

```console
$ d2w metadata organisation-unit-groups delete [OPTIONS] {uid}
```

**Arguments**:

* `uid`: OrganisationUnitGroup UID to delete.  [required]

**Options**:

* `-y, --yes`: Skip the confirmation prompt.
* `--help`: Show this message and exit.

### `d2w metadata organisation-unit-group-sets`

OrganisationUnitGroupSet workflows (get / create / add-groups / remove-groups / delete).

**Usage**:

```console
$ d2w metadata organisation-unit-group-sets [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `get`: Show one group set with its groups +...
* `create`: Create an empty OrganisationUnitGroupSet.
* `add-groups`: Add `--group` members to a group set.
* `remove-groups`: Drop `--group` members from a group set.
* `delete`: Delete an OrganisationUnitGroupSet —...

#### `d2w metadata organisation-unit-group-sets get`

Show one group set with its groups + per-group member counts.

**Usage**:

```console
$ d2w metadata organisation-unit-group-sets get [OPTIONS] {uid}
```

**Arguments**:

* `uid`: OrganisationUnitGroupSet UID.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w metadata organisation-unit-group-sets create`

Create an empty OrganisationUnitGroupSet.

**Usage**:

```console
$ d2w metadata organisation-unit-group-sets create [OPTIONS]
```

**Options**:

* `--name <str>`: Full name (&lt;=230 chars, unique).  [required]
* `--short-name <str>`: Short name (&lt;=50 chars, unique).  [required]
* `--uid <str>`: Explicit 11-char UID (generated when omitted).
* `--code <str>`: Business code.
* `--description <str>`: Free-text description.
* `--compulsory / --not-compulsory`: Require OUs to land in exactly one group of this set.  [default: not-compulsory]
* `--data-dimension / --no-data-dimension`: Expose as a pivot/visualisation axis.  [default: data-dimension]
* `--help`: Show this message and exit.

#### `d2w metadata organisation-unit-group-sets add-groups`

Add `--group` members to a group set.

**Usage**:

```console
$ d2w metadata organisation-unit-group-sets add-groups [OPTIONS] {uid}
```

**Arguments**:

* `uid`: OrganisationUnitGroupSet UID.  [required]

**Options**:

* `--group <str>`: OrganisationUnitGroup UID to add. Repeat for multiple.  [required]
* `--help`: Show this message and exit.

#### `d2w metadata organisation-unit-group-sets remove-groups`

Drop `--group` members from a group set.

**Usage**:

```console
$ d2w metadata organisation-unit-group-sets remove-groups [OPTIONS] {uid}
```

**Arguments**:

* `uid`: OrganisationUnitGroupSet UID.  [required]

**Options**:

* `--group <str>`: OrganisationUnitGroup UID to drop. Repeat for multiple.  [required]
* `--help`: Show this message and exit.

#### `d2w metadata organisation-unit-group-sets delete`

Delete an OrganisationUnitGroupSet — groups stay.

**Usage**:

```console
$ d2w metadata organisation-unit-group-sets delete [OPTIONS] {uid}
```

**Arguments**:

* `uid`: OrganisationUnitGroupSet UID to delete.  [required]

**Options**:

* `-y, --yes`: Skip the confirmation prompt.
* `--help`: Show this message and exit.

### `d2w metadata organisation-unit-levels`

OrganisationUnitLevel naming (get / rename).

**Usage**:

```console
$ d2w metadata organisation-unit-levels [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `get`: Show one level row — by UID (default) or...
* `rename`: Give a level a human label — turns &#x27;level...

#### `d2w metadata organisation-unit-levels get`

Show one level row — by UID (default) or by numeric depth.

**Usage**:

```console
$ d2w metadata organisation-unit-levels get [OPTIONS] {uid}
```

**Arguments**:

* `uid`: OrganisationUnitLevel UID (or pass --by-level).  [required]

**Options**:

* `--by-level`: Treat UID as the numeric level (1 = roots).
* `--help`: Show this message and exit.

#### `d2w metadata organisation-unit-levels rename`

Give a level a human label — turns &#x27;level 2&#x27; into &#x27;Province&#x27;.

**Usage**:

```console
$ d2w metadata organisation-unit-levels rename [OPTIONS] {uid}
```

**Arguments**:

* `uid`: OrganisationUnitLevel UID (or the numeric level with --by-level).  [required]

**Options**:

* `--name <str>`: New human label (e.g. &#x27;Country&#x27;, &#x27;District&#x27;, &#x27;Facility&#x27;).  [required]
* `--by-level`: Treat UID as the numeric level (1 = roots).
* `--code <str>`: Optionally update the business code.
* `--offline-levels <int>`: How many levels to cache offline from this one.
* `--help`: Show this message and exit.

### `d2w metadata legend-sets`

LegendSet authoring (get / create / clone / delete).

**Usage**:

```console
$ d2w metadata legend-sets [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `get`: Show one LegendSet with its ordered...
* `create`: Create a LegendSet with ordered...
* `clone`: Duplicate an existing LegendSet with the...
* `delete`: Delete a LegendSet.

#### `d2w metadata legend-sets get`

Show one LegendSet with its ordered legends (colour ranges).

**Usage**:

```console
$ d2w metadata legend-sets get [OPTIONS] {uid}
```

**Arguments**:

* `uid`: LegendSet UID.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w metadata legend-sets create`

Create a LegendSet with ordered colour-range legends.

Each `--legend start🔚color[:name]` defines one entry — `start`
must be strictly less than `end`, `color` is a `#RRGGBB` /
`#RRGGBBAA` hex string, `name` is optional (auto-generated from the
numeric range when omitted). At least one `--legend` is required.

Posts through `/api/metadata` so the LegendSet + its child Legends
land atomically. Returns the freshly-fetched record so DHIS2&#x27;s
computed fields are populated.

**Usage**:

```console
$ d2w metadata legend-sets create [OPTIONS]
```

**Options**:

* `--name <str>`: Display name for the new LegendSet.  [required]
* `--legend <str>`: One legend (colour range) in `start🔚color[:name]` form. Repeatable, at least one required. Example: `--legend 0:1000:#d73027:Low --legend 1000:5000:#1a9850:High`.  [required]
* `--code <str>`: Business code (unique).
* `--uid <str>`: Fixed 11-char UID. Omit to let the client generate one.
* `--help`: Show this message and exit.

#### `d2w metadata legend-sets clone`

Duplicate an existing LegendSet with the same bands + fresh UIDs.

Useful for forking a base set (&quot;Coverage 0-100&quot;) into a variant
without rebuilding the bands by hand.

**Usage**:

```console
$ d2w metadata legend-sets clone [OPTIONS] {source_uid}
```

**Arguments**:

* `source_uid`: Source LegendSet UID to clone.  [required]

**Options**:

* `--new-name <str>`: Name of the clone (default: append &#x27; (clone)&#x27; to the source&#x27;s name).
* `--new-uid <str>`: Fixed 11-char UID for the clone. Omit for auto-generated.
* `--new-code <str>`: Business code on the clone.
* `--help`: Show this message and exit.

#### `d2w metadata legend-sets delete`

Delete a LegendSet.

**Usage**:

```console
$ d2w metadata legend-sets delete [OPTIONS] {uid}
```

**Arguments**:

* `uid`: LegendSet UID to delete.  [required]

**Options**:

* `-y, --yes`: Skip the confirmation prompt.
* `--help`: Show this message and exit.

## `d2w profile`

Manage DHIS2 profiles.

**Usage**:

```console
$ d2w profile [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `ls`: List every known profile with its source...
* `list`: List every known profile with its source...
* `verify`: Verify one profile or all profiles by...
* `show`: Print one profile (secrets redacted by...
* `env`: Print `export DHIS2_*` lines for a...
* `default`: Set `default = &lt;name&gt;` in the global...
* `add`: Add (or upsert) a profile.
* `remove`: Remove a profile.
* `rename`: Rename a profile in-place.
* `login`: Run the OAuth2 authorization-code flow for...
* `logout`: Clear persisted OAuth2 tokens for a profile.
* `bootstrap`: One-shot: provision a PAT or OAuth2 client...
* `oidc-config`: Populate an OAuth2 profile by discovering...
* `pat`: Personal Access Tokens — provision PATs on...
* `oauth2`: Manage DHIS2 OAuth2 clients on the server...

### `d2w profile ls`

List every known profile with its source and default status.

**Usage**:

```console
$ d2w profile ls [OPTIONS]
```

**Options**:

* `-a, --all`: Include shadowed profiles (global entries hidden by project ones).
* `--help`: Show this message and exit.

### `d2w profile list`

List every known profile with its source and default status.

**Usage**:

```console
$ d2w profile list [OPTIONS]
```

**Options**:

* `-a, --all`: Include shadowed profiles (global entries hidden by project ones).
* `--help`: Show this message and exit.

### `d2w profile verify`

Verify one profile or all profiles by hitting /api/system/info + /api/me.

**Usage**:

```console
$ d2w profile verify [OPTIONS] [name]
```

**Arguments**:

* `name`: Profile name to verify; omit to verify all.

**Options**:

* `--help`: Show this message and exit.

### `d2w profile show`

Print one profile (secrets redacted by default).

**Usage**:

```console
$ d2w profile show [OPTIONS] {name}
```

**Arguments**:

* `name`: [required]

**Options**:

* `--secrets`: Include sensitive values.
* `--help`: Show this message and exit.

### `d2w profile env`

Print `export DHIS2_*` lines for a profile, for `eval`.

Offline read — no instance probe; the wire client auto-detects the version on connect.
Values are printed as-is (the password / token is already plaintext in `profiles.toml`),
so the output is directly usable: `eval &quot;$(d2w profile env local_basic)&quot;`. The command
only prints to stdout — it cannot mutate the caller&#x27;s shell. For a redacted view (e.g.
screen-sharing) use `d2w profile show` instead.

**Usage**:

```console
$ d2w profile env [OPTIONS] [name]
```

**Arguments**:

* `name`: Profile name; defaults to the active profile.

**Options**:

* `--help`: Show this message and exit.

### `d2w profile default`

Set `default = &lt;name&gt;` in the global (default) or project profiles.toml.

When `name` is omitted and stdin is a TTY, the command renders the
profile list + prompts for a numbered selection. Pass `--global` or
`--local` to pick the profiles.toml to write (`--global` is the
default).

**Usage**:

```console
$ d2w profile default [OPTIONS] [name]
```

**Arguments**:

* `name`: Profile name to set as default. Omit to pick interactively from a list.

**Options**:

* `--global`: Write to ~/.config/dhis2/profiles.toml (default).
* `--local`: Write to ./.dhis2/profiles.toml instead.
* `--verify`: Probe the instance after switching.
* `--help`: Show this message and exit.

### `d2w profile add`

Add (or upsert) a profile.

Secrets are never accepted as command-line flags (they&#x27;d leak into shell history).
Read from env (`DHIS2_PAT`, `DHIS2_PASSWORD`, `DHIS2_OAUTH_CLIENT_SECRET`,
`DHIS2_SESSION_COOKIE`, `DHIS2_SESSION_XSRF`) or prompted interactively when missing.

**Usage**:

```console
$ d2w profile add [OPTIONS] {name}
```

**Arguments**:

* `name`: [required]

**Options**:

* `--url <str>`: DHIS2 base URL (also: DHIS2_URL env).
* `--auth <str>`: pat | basic | oauth2 | session  [default: pat]
* `--username <str>`: Basic-auth username.
* `--client-id <str>`: OAuth2 client_id.
* `--scope <str>`: OAuth2 scope (DHIS2 only recognises `ALL`).  [default: ALL]
* `--redirect-uri <str>`: OAuth2 redirect URI (must match the registered client).  [default: http://localhost:8765]
* `--from-env`: Pull OAuth2 fields from DHIS2_OAUTH_CLIENT_ID / DHIS2_OAUTH_CLIENT_SECRET / DHIS2_OAUTH_REDIRECT_URI / DHIS2_OAUTH_SCOPES env vars (seeded .env.auth).
* `--global`: Save to ~/.config/dhis2/profiles.toml (default — user-wide, applies everywhere).
* `--local`: Save to ./.dhis2/profiles.toml instead (project-scoped, overrides global).
* `--default`: Set as default after adding.
* `--verify`: Probe /api/system/info + /api/me after saving.
* `--version <str>`: Expected DHIS2 major for this profile (v41 | v42 | v43). Used by CLI/MCP to pick which version&#x27;s plugin tree to load; the wire client always auto-detects on connect.
* `--help`: Show this message and exit.

### `d2w profile remove`

Remove a profile. Without --global/--local, removes from whichever file holds it.

**Usage**:

```console
$ d2w profile remove [OPTIONS] {name}
```

**Arguments**:

* `name`: [required]

**Options**:

* `--global`: Remove from ~/.config/dhis2/profiles.toml specifically.
* `--local`: Remove from ./.dhis2/profiles.toml specifically.
* `-y, --yes`: Skip the confirmation prompt.
* `--help`: Show this message and exit.

### `d2w profile rename`

Rename a profile in-place. Preserves scope and updates default if needed.

**Usage**:

```console
$ d2w profile rename [OPTIONS] {old_name} {new_name}
```

**Arguments**:

* `old_name`: Current profile name.  [required]
* `new_name`: New profile name (letters, digits, underscores).  [required]

**Options**:

* `--verify`: Probe the instance after renaming.
* `--help`: Show this message and exit.

### `d2w profile login`

Run the OAuth2 authorization-code flow for a profile and persist its tokens.

Opens a browser to DHIS2&#x27;s authorization endpoint, listens on the profile&#x27;s
`redirect_uri` (local FastAPI+uvicorn), exchanges the code for tokens,
and writes them to the scope-appropriate tokens.sqlite. OAuth2 profiles only.

Pass `--no-browser` (or `DHIS2_OAUTH_NO_BROWSER=1`) to print the URL to
stderr instead of launching the system browser.

**Usage**:

```console
$ d2w profile login [OPTIONS] [name]
```

**Arguments**:

* `name`: Profile name; omit to use the default.

**Options**:

* `--no-browser`: Print the DHIS2 authorization URL instead of launching the system browser. Useful over SSH, under Playwright, or when logging in via a different browser. Also accepts DHIS2_OAUTH_NO_BROWSER=1 as default.
* `--help`: Show this message and exit.

### `d2w profile logout`

Clear persisted OAuth2 tokens for a profile.

Removes the row from the scope-appropriate `tokens.sqlite`. Next API call
triggers a fresh `profile login` flow. OAuth2 profiles only.

**Usage**:

```console
$ d2w profile logout [OPTIONS] [name]
```

**Arguments**:

* `name`: Profile name; omit to use the default.

**Options**:

* `--help`: Show this message and exit.

### `d2w profile bootstrap`

One-shot: provision a PAT or OAuth2 client on DHIS2, save a profile, (for oauth2) log in.

Secrets never come in via argv. Read from env
(`DHIS2_ADMIN_PAT`, `DHIS2_ADMIN_PASSWORD`, `DHIS2_OAUTH_CLIENT_SECRET`)
or prompted interactively when missing. Admin creds are used once to POST
`/api/apiToken` (pat) or `/api/oAuth2Clients` (oauth2), then discarded.

Re-runs for `auth=oauth2` fail at POST /api/oAuth2Clients if `client_id` is
taken — pass a different `--client-id` in that case. PAT bootstraps never
collide (DHIS2 mints a fresh server-side UID).

**Usage**:

```console
$ d2w profile bootstrap [OPTIONS] {name}
```

**Arguments**:

* `name`: Profile name to create.  [required]

**Options**:

* `--auth <str>`: pat | oauth2 — which kind of profile to set up.  [default: oauth2]
* `--url <str>`: DHIS2 base URL (also: DHIS2_URL env).
* `--admin-user <str>`: Admin username (for basic bootstrap).
* `--client-id <str>`: OAuth2 client_id to register (auth=oauth2).  [default: dhis2-utils-local]
* `--redirect-uri <str>`: OAuth2 redirect URI.  [default: http://localhost:8765]
* `--scope <str>`: OAuth2 scope.  [default: ALL]
* `--pat-description <str>`: PAT description (auth=pat).
* `--pat-expires-in-days <int>`: PAT lifetime in days; omit for no expiry.
* `--global`: Save to ~/.config/dhis2/profiles.toml (default).
* `--local`: Save to ./.dhis2/profiles.toml instead.
* `--login / --no-login`: For auth=oauth2, run `profile login` after saving. Ignored for auth=pat.  [default: login]
* `--version <str>`: Expected DHIS2 major for this profile (v41 | v42 | v43). Used by CLI/MCP to pick which version&#x27;s plugin tree to load; the wire client always auto-detects on connect.
* `--help`: Show this message and exit.

### `d2w profile oidc-config`

Populate an OAuth2 profile by discovering a DHIS2 instance&#x27;s OIDC endpoints.

Fetches `/.well-known/openid-configuration` from the given URL, validates the
response, and writes a profile with `auth=oauth2` + your client credentials.
Removes the &quot;hand-edit profiles.toml with the right issuer/auth/token URLs&quot;
step from the OAuth2 setup walkthrough.

The URL can be either the DHIS2 base URL (discovery path is appended
automatically) or the full discovery URL.

The client_secret never comes in via argv (it would leak to shell history / `ps`).
Read it from the `DHIS2_OAUTH_CLIENT_SECRET` env var or a hidden prompt when the
`--client-secret` flag is omitted.

**Usage**:

```console
$ d2w profile oidc-config [OPTIONS] {url}
```

**Arguments**:

* `url`: DHIS2 base URL or full /.well-known/openid-configuration URL.  [required]

**Options**:

* `-n, --name <str>`: Profile name to save as.  [required]
* `--client-id <str>`: OAuth2 client_id (from your registration).  [required]
* `--client-secret <str>`: OAuth2 client_secret. Omit to read DHIS2_OAUTH_CLIENT_SECRET env or a hidden prompt.
* `--scope <str>`: OAuth2 scope (DHIS2 only recognises `ALL`).  [default: ALL]
* `--redirect-uri <str>`: OAuth2 redirect URI (match your registered client — default is the CLI&#x27;s loopback listener).  [default: http://localhost:8765]
* `--global`: Save to ~/.config/dhis2/profiles.toml (default, user-wide).
* `--local`: Save to ./.dhis2/profiles.toml instead (project-scoped).
* `--default`: Set as default after saving.
* `--login`: Trigger `d2w profile login &lt;name&gt;` immediately after saving.
* `--version <str>`: Expected DHIS2 major for this profile (v41 | v42 | v43). Used by CLI/MCP to pick which version&#x27;s plugin tree to load; the wire client always auto-detects on connect.
* `--help`: Show this message and exit.

### `d2w profile pat`

Personal Access Tokens — provision PATs on DHIS2.

**Usage**:

```console
$ d2w profile pat [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `create`: Create a DHIS2 Personal Access Token via...

#### `d2w profile pat create`

Create a DHIS2 Personal Access Token via POST /api/apiToken.

Admin creds come from env or prompt (never argv). The PAT value is only
returned once by DHIS2 — capture it here and pipe into a profile:

    export DHIS2_PAT=$(d2w dev pat create --url $URL -q)
    d2w profile add local --url $URL --auth pat

Or use `d2w profile bootstrap --auth pat` for a one-shot setup.

**Usage**:

```console
$ d2w profile pat create [OPTIONS]
```

**Options**:

* `--url <str>`: DHIS2 base URL (also: DHIS2_URL env).
* `--admin-user <str>`
* `--description <str>`
* `--expires-in-days <int>`
* `--allowed-ip <str>`: IP allowlist entry; repeat for multiple.
* `--allowed-method <str>`: HTTP method allowlist; repeat for each method.
* `--allowed-referrer <str>`: Referer allowlist entry; repeat for multiple.
* `-q, --quiet`: Print only the PAT value, suitable for $(command substitution).
* `--help`: Show this message and exit.

### `d2w profile oauth2`

Manage DHIS2 OAuth2 clients on the server (admin ops).

**Usage**:

```console
$ d2w profile oauth2 [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `client`: OAuth2 client registrations at...

#### `d2w profile oauth2 client`

OAuth2 client registrations at /api/oAuth2Clients.

**Usage**:

```console
$ d2w profile oauth2 client [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `register`: Register an OAuth2 client on DHIS2 via...

##### `d2w profile oauth2 client register`

Register an OAuth2 client on DHIS2 via POST /api/oAuth2Clients.

Secrets (admin credentials, client_secret) come from env or interactive
prompt — never argv.

Prints `client_id` + metadata UID so they can be piped into
`d2w profile add --auth oauth2 ...`. For a one-shot bootstrap (register
+ save profile + log in) use `d2w profile bootstrap` instead.

**Usage**:

```console
$ d2w profile oauth2 client register [OPTIONS]
```

**Options**:

* `--url <str>`: DHIS2 base URL (also: DHIS2_URL env).
* `--admin-user <str>`
* `--client-id <str>`: [default: dhis2-utils-local]
* `--redirect-uri <str>`: [default: http://localhost:8765]
* `--scope <str>`: [default: ALL]
* `--name <str>`
* `--help`: Show this message and exit.

## `d2w query`

d2ql query + transform language.

**Usage**:

```console
$ d2w query [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `eval`: Run a d2ql program (inline or `--file`)...
* `run`: Run a d2ql program read from a file.
* `explain`: Show how a d2ql pipeline (inline or...
* `ast`: Print the parsed d2ql AST (no profile...
* `d2path`: Evaluate a bare d2path expression over a...
* `repl`: Interactive d2ql REPL.

### `d2w query eval`

Run a d2ql program (inline or `--file`) against the active profile and render the rows.

**Usage**:

```console
$ d2w query eval [OPTIONS] [text]
```

**Arguments**:

* `text`: A d2ql program (quote it); or read one with --file.

**Options**:

* `-f, --file <path>`: Read the d2ql program from this file.
* `-d, --define <str>`: Run/explain this named definition.
* `-o, --out <str>`: Write rows to this file (json/ndjson/csv).
* `--help`: Show this message and exit.

### `d2w query run`

Run a d2ql program read from a file.

**Usage**:

```console
$ d2w query run [OPTIONS] {file}
```

**Arguments**:

* `file`: Path to a .d2ql program file.  [required]

**Options**:

* `-d, --define <str>`: Run/explain this named definition.
* `-o, --out <str>`: Write rows to this file (json/ndjson/csv).
* `--help`: Show this message and exit.

### `d2w query explain`

Show how a d2ql pipeline (inline or `--file`) splits between DHIS2 pushdown and local evaluation.

**Usage**:

```console
$ d2w query explain [OPTIONS] [text]
```

**Arguments**:

* `text`: A d2ql program (quote it); or read one with --file.

**Options**:

* `-f, --file <path>`: Read the d2ql program from this file.
* `-d, --define <str>`: Run/explain this named definition.
* `--help`: Show this message and exit.

### `d2w query ast`

Print the parsed d2ql AST (no profile needed; inline program or `--file`).

**Usage**:

```console
$ d2w query ast [OPTIONS] [text]
```

**Arguments**:

* `text`: A d2ql program (quote it); or read one with --file.

**Options**:

* `-f, --file <path>`: Read the d2ql program from this file.
* `--help`: Show this message and exit.

### `d2w query d2path`

Evaluate a bare d2path expression over a local JSON document (no profile needed).

**Usage**:

```console
$ d2w query d2path [OPTIONS] {expression}
```

**Arguments**:

* `expression`: A d2path expression (quote it).  [required]

**Options**:

* `-i, --input <path>`: JSON file to evaluate against.  [required]
* `--help`: Show this message and exit.

### `d2w query repl`

Interactive d2ql REPL. Uses the Textual TUI when the `tui` extra is installed, else line mode.

**Usage**:

```console
$ d2w query repl [OPTIONS]
```

**Options**:

* `--help`: Show this message and exit.

## `d2w route`

DHIS2 integration routes.

**Usage**:

```console
$ d2w route [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `ls`: List registered routes.
* `list`: List registered routes.
* `get`: Fetch one route by UID or code.
* `create`: Create a route via POST /api/routes.
* `update`: Replace a route via PUT /api/routes/{uid}.
* `patch`: Apply a JSON Patch to a route via PATCH...
* `delete`: Delete a route.
* `run`: Execute a route — DHIS2 proxies the...

### `d2w route ls`

List registered routes.

**Usage**:

```console
$ d2w route ls [OPTIONS]
```

**Options**:

* `--fields <str>`: [default: id,code,name,url,disabled,auth]
* `--help`: Show this message and exit.

### `d2w route list`

List registered routes.

**Usage**:

```console
$ d2w route list [OPTIONS]
```

**Options**:

* `--fields <str>`: [default: id,code,name,url,disabled,auth]
* `--help`: Show this message and exit.

### `d2w route get`

Fetch one route by UID or code.

**Usage**:

```console
$ d2w route get [OPTIONS] {route}
```

**Arguments**:

* `route`: Route UID (e.g. E8OPcc45A22) or code (e.g. chap).  [required]

**Options**:

* `--fields <str>`
* `--help`: Show this message and exit.

### `d2w route create`

Create a route via POST /api/routes.

With `--file`: a full JSON spec. Omit `auth` (or set it to null) for no upstream auth.

Flag form: pass --code/--name/--url. Add --no-auth for an unauthenticated route (required
when not running in a TTY — the auth wizard needs interactive input). Secrets never come via
argv — they&#x27;re read from env (`DHIS2_ROUTE_UPSTREAM_*`) or hidden prompts in the wizard.

**Usage**:

```console
$ d2w route create [OPTIONS]
```

**Options**:

* `--file <path>`: JSON file with the route definition (bypass the interactive wizard).
* `--code <str>`
* `--name <str>`
* `--url <str>`: Target URL the route proxies to.
* `--authorities <str>`: Comma-separated DHIS2 authorities allowed to run this route.
* `--no-auth`: Create an unauthenticated route (skip the auth wizard) — for headless/bridge use.
* `--help`: Show this message and exit.

### `d2w route update`

Replace a route via PUT /api/routes/{uid}.

DHIS2 PUT expects the complete object. For partial updates use `patch`.

**Usage**:

```console
$ d2w route update [OPTIONS] {route}
```

**Arguments**:

* `route`: Route UID (e.g. E8OPcc45A22) or code (e.g. chap).  [required]

**Options**:

* `--file <path>`: JSON file with the full route spec (PUT semantics).  [required]
* `--help`: Show this message and exit.

### `d2w route patch`

Apply a JSON Patch to a route via PATCH /api/routes/{uid}.

**Usage**:

```console
$ d2w route patch [OPTIONS] {route}
```

**Arguments**:

* `route`: Route UID (e.g. E8OPcc45A22) or code (e.g. chap).  [required]

**Options**:

* `--file <path>`: JSON Patch array (RFC 6902).  [required]
* `--help`: Show this message and exit.

### `d2w route delete`

Delete a route.

**Usage**:

```console
$ d2w route delete [OPTIONS] {route}
```

**Arguments**:

* `route`: Route UID (e.g. E8OPcc45A22) or code (e.g. chap).  [required]

**Options**:

* `-y, --yes`: Skip the confirmation prompt.
* `--help`: Show this message and exit.

### `d2w route run`

Execute a route — DHIS2 proxies the request to the configured target URL.

`route` accepts the route&#x27;s UID or its `code`. When the route&#x27;s target
URL ends in a wildcard (`/**`), `--path SEGMENT` is required: it is
what DHIS2 substitutes into the wildcard before calling upstream.

**Usage**:

```console
$ d2w route run [OPTIONS] {route}
```

**Arguments**:

* `route`: Route UID (e.g. E8OPcc45A22) or code (e.g. chap).  [required]

**Options**:

* `-X, --method <str>`: [default: GET]
* `--body <path>`: JSON body file for POST/PUT.
* `--path <str>`: Additional path segment appended to the route&#x27;s target URL.
* `--help`: Show this message and exit.

## `d2w security`

DHIS2 security posture (read-only).

**Usage**:

```console
$ d2w security [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `settings`: Show the server&#x27;s security-relevant system...
* `authorities`: Show my effective authorities, categorised...
* `audit`: Run the security checks step by step and...
* `report`: Re-render an existing run&#x27;s report files...

### `d2w security settings`

Show the server&#x27;s security-relevant system settings. `--json` for the full payload.

**Usage**:

```console
$ d2w security settings [OPTIONS]
```

**Options**:

* `--help`: Show this message and exit.

### `d2w security authorities`

Show my effective authorities, categorised by security risk. `--json` for the full payload.

**Usage**:

```console
$ d2w security authorities [OPTIONS]
```

**Options**:

* `--help`: Show this message and exit.

### `d2w security audit`

Run the security checks step by step and stream a report to a folder. `--json` prints the report.

**Usage**:

```console
$ d2w security audit [OPTIONS]
```

**Options**:

* `--output-dir <directory>`: Parent directory for the run folder (default: current dir).
* `--format <str>`: Comma-separated formats: md,txt,csv,html (default: all).
* `--checks <str>`: Comma-separated check keys to run (default: all). Valid keys: version, transport, settings, authorities, roles, hygiene, credential-probe, guest, apps, sharing, auth-methods, tokens, routes, audit-config.
* `--skip <str>`: Comma-separated check keys to skip.
* `--progress / --no-progress`: Animate step-by-step progress on a TTY.  [default: progress]
* `--credential-probe / --no-credential-probe`: Actively test the default admin/district login against /api/me (on by default).  [default: credential-probe]
* `--stale-days <int range>`: Days without login before a privileged account is stale.  [default: 90; x&gt;=1]
* `--max-password-age <int range>`: Days before an unchanged password is treated as stale.  [default: 365; x&gt;=1]
* `--two-factor-detail / --no-two-factor-detail`: On v42+, also list each superuser lacking 2FA (per-user /api/users/twoFactor read).  [default: no-two-factor-detail]
* `--max-objects <int range>`: Max objects the sharing scan inspects across all types before stopping (default 5000; truncation is loud).  [x&gt;=1]
* `--sharing-graph, --visualize`: Also write the interactive d3 sharing explorer (sharing-explorer.html) into the run folder.
* `--resume <directory>`: Resume an interrupted run folder.
* `--dhis-conf <file>`: Path to a local COPY of the server&#x27;s dhis.conf for the audit-config check. The audit posture is not API-readable; secrets are reported set/not-set only and never echoed.  [env var: DHIS2_CONF_LOCATION]
* `--version-fallback / --no-version-fallback`: When the server&#x27;s exact generated tree is not shipped (e.g. a dev/master build), bind the nearest lower generated tree instead of failing.  [default: no-version-fallback]
* `--help`: Show this message and exit.

### `d2w security report`

Re-render an existing run&#x27;s report files from its JSONL spine, without re-scanning.

**Usage**:

```console
$ d2w security report [OPTIONS] {folder}
```

**Arguments**:

* `folder`: An existing run folder to re-render.  [required]

**Options**:

* `--format <str>`: Comma-separated formats (default: all).
* `--help`: Show this message and exit.

## `d2w system`

DHIS2 system info.

**Usage**:

```console
$ d2w system [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `whoami`: Expose everything DHIS2 reports about the...
* `info`: Print DHIS2 system info (version, build,...
* `calendar`: Print the active DHIS2 calendar, or change...
* `settings`: Read/write DHIS2 system settings.

### `d2w system whoami`

Expose everything DHIS2 reports about the authenticated user. `--json` for the raw object.

**Usage**:

```console
$ d2w system whoami [OPTIONS]
```

**Options**:

* `--help`: Show this message and exit.

### `d2w system info`

Print DHIS2 system info (version, build, analytics state, env).

**Usage**:

```console
$ d2w system info [OPTIONS]
```

**Options**:

* `--help`: Show this message and exit.

### `d2w system calendar`

Print the active DHIS2 calendar, or change it when a value is supplied.

`keyCalendar` is the system-wide calendar DHIS2 uses to interpret periods.
The default is `iso8601`. Changing it is rare and risky — most instances
pick a calendar at deploy time and never touch it again. Switching the
calendar after data collection has started can leave existing periods
unreadable and break analytics, so this command requires interactive
confirmation (or `--yes`).

**Usage**:

```console
$ d2w system calendar [OPTIONS] [value]:<coptic|ethiopian|gregorian|islamic|iso8601|julian|nepali|persian|thai>
```

**Arguments**:

* `value:<coptic|ethiopian|gregorian|islamic|iso8601|julian|nepali|persian|thai>`: When supplied, write `keyCalendar` (one of: coptic, ethiopian, gregorian, islamic, iso8601, julian, nepali, persian, thai). Omit to print the current calendar.

**Options**:

* `-y, --yes`: Skip the interactive confirmation. Required for non-interactive callers (CI, scripts).
* `--help`: Show this message and exit.

### `d2w system settings`

Read/write DHIS2 system settings.

**Usage**:

```console
$ d2w system settings [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `set`: Set a single system setting.
* `set-many`: Bulk-set system settings from a JSON file.
* `get`: Print one system setting&#x27;s value; exit 1...
* `ls`: List every system setting (key = value).
* `list`: List every system setting (key = value).

#### `d2w system settings set`

Set a single system setting.

**Usage**:

```console
$ d2w system settings set [OPTIONS] {key} {value}
```

**Arguments**:

* `key`: System setting key (e.g. applicationTitle, keyApplicationFooter).  [required]
* `value`: New value.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w system settings set-many`

Bulk-set system settings from a JSON file.

JSON scalars are coerced to the string form DHIS2 expects: booleans map to
lowercase `true` / `false`, numbers to their plain form, strings pass
through, and structured values (lists / objects) are re-serialized as JSON.

**Usage**:

```console
$ d2w system settings set-many [OPTIONS] {file}
```

**Arguments**:

* `file`: JSON file containing a {key: value} object.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w system settings get`

Print one system setting&#x27;s value; exit 1 if it is unset.

**Usage**:

```console
$ d2w system settings get [OPTIONS] {key}
```

**Arguments**:

* `key`: System setting key (e.g. applicationTitle).  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w system settings ls`

List every system setting (key = value).

**Usage**:

```console
$ d2w system settings ls [OPTIONS]
```

**Options**:

* `--help`: Show this message and exit.

#### `d2w system settings list`

List every system setting (key = value).

**Usage**:

```console
$ d2w system settings list [OPTIONS]
```

**Options**:

* `--help`: Show this message and exit.

## `d2w user`

DHIS2 user administration.

**Usage**:

```console
$ d2w user [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `ls`: List users.
* `list`: List users.
* `get`: Fetch one user by UID or username.
* `invite`: Create a user and send the invitation email.
* `reinvite`: Re-send the invitation email for a pending...
* `reset-password`: Trigger DHIS2&#x27;s password-reset email (POST...
* `group`: Manage DHIS2 user groups.
* `role`: Manage DHIS2 user roles.

### `d2w user ls`

List users.

Examples:
  d2w user list
  d2w user list --filter &#x27;disabled:eq:true&#x27; --order &#x27;username:asc&#x27;
  d2w user list --filter &#x27;username:like:admin&#x27;

**Usage**:

```console
$ d2w user ls [OPTIONS]
```

**Options**:

* `--fields <str>`: DHIS2 field selector. Supports plain lists (&#x27;id,username,email&#x27;), presets (&#x27;:identifiable&#x27;, &#x27;:nameable&#x27;, &#x27;:owner&#x27;, &#x27;:all&#x27;), and exclusions (&#x27;:all,!password&#x27;).  [default: id,username,displayName,email,disabled,lastLogin]
* `--filter <str>`: Filter &#x27;property:operator:value&#x27; (repeatable).
* `--root-junction <str>`: Combine repeated --filter as AND (default) or OR.  [default: AND]
* `--order <str>`: Sort clause &#x27;property:asc|desc&#x27; (repeatable).
* `--page <int>`: Server-side page number (1-based).
* `--page-size <int>`: Server-side page size (default 50).
* `--help`: Show this message and exit.

### `d2w user list`

List users.

Examples:
  d2w user list
  d2w user list --filter &#x27;disabled:eq:true&#x27; --order &#x27;username:asc&#x27;
  d2w user list --filter &#x27;username:like:admin&#x27;

**Usage**:

```console
$ d2w user list [OPTIONS]
```

**Options**:

* `--fields <str>`: DHIS2 field selector. Supports plain lists (&#x27;id,username,email&#x27;), presets (&#x27;:identifiable&#x27;, &#x27;:nameable&#x27;, &#x27;:owner&#x27;, &#x27;:all&#x27;), and exclusions (&#x27;:all,!password&#x27;).  [default: id,username,displayName,email,disabled,lastLogin]
* `--filter <str>`: Filter &#x27;property:operator:value&#x27; (repeatable).
* `--root-junction <str>`: Combine repeated --filter as AND (default) or OR.  [default: AND]
* `--order <str>`: Sort clause &#x27;property:asc|desc&#x27; (repeatable).
* `--page <int>`: Server-side page number (1-based).
* `--page-size <int>`: Server-side page size (default 50).
* `--help`: Show this message and exit.

### `d2w user get`

Fetch one user by UID or username. Prints a concise summary; `--json` for full payload.

**Usage**:

```console
$ d2w user get [OPTIONS] {uid_or_username}
```

**Arguments**:

* `uid_or_username`: User UID (11 chars) or username.  [required]

**Options**:

* `--fields <str>`: DHIS2 field selector.
* `--help`: Show this message and exit.

### `d2w user invite`

Create a user and send the invitation email.

Hits POST /api/users/invite. DHIS2&#x27;s configured mailer sends the link;
the new user sets their password on accept. Prints the new user&#x27;s UID.

**Usage**:

```console
$ d2w user invite [OPTIONS] {email}
```

**Arguments**:

* `email`: Email address for the new user (receives the invitation link).  [required]

**Options**:

* `--first-name <str>`: User&#x27;s given name.  [required]
* `--surname <str>`: User&#x27;s surname.  [required]
* `--username <str>`: Desired username. Omit to let DHIS2 derive from the email prefix.
* `--user-role <str>`: User-role UID (repeatable). Grants the role on accept.
* `--org-unit, --ou <str>`: Organisation-unit UID for capture scope (repeatable).
* `--help`: Show this message and exit.

### `d2w user reinvite`

Re-send the invitation email for a pending user (POST /api/users/{uid}/invite).

**Usage**:

```console
$ d2w user reinvite [OPTIONS] {uid}
```

**Arguments**:

* `uid`: UID of a user who hasn&#x27;t yet completed their invite.  [required]

**Options**:

* `--help`: Show this message and exit.

### `d2w user reset-password`

Trigger DHIS2&#x27;s password-reset email (POST /api/users/{uid}/reset).

**Usage**:

```console
$ d2w user reset-password [OPTIONS] {uid}
```

**Arguments**:

* `uid`: UID of the user to reset.  [required]

**Options**:

* `--help`: Show this message and exit.

### `d2w user group`

Manage DHIS2 user groups.

**Usage**:

```console
$ d2w user group [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `ls`: List user groups.
* `list`: List user groups.
* `get`: Fetch one user group by UID.
* `create`: Create a user group (then add members with...
* `delete`: Delete a user group by UID.
* `add-member`: Add a user to a group (POST...
* `remove-member`: Remove a user from a group (DELETE...
* `sharing-get`: Print the current sharing block for one...
* `sharing-grant-user`: Grant one user access to a group (shortcut...

#### `d2w user group ls`

List user groups.

**Usage**:

```console
$ d2w user group ls [OPTIONS]
```

**Options**:

* `--fields <str>`: DHIS2 field selector.  [default: id,name,displayName,users]
* `--filter <str>`: Filter &#x27;property:operator:value&#x27; (repeatable).
* `--order <str>`: Sort clause &#x27;property:asc|desc&#x27; (repeatable).
* `--page-size <int>`: Server-side page size.
* `--help`: Show this message and exit.

#### `d2w user group list`

List user groups.

**Usage**:

```console
$ d2w user group list [OPTIONS]
```

**Options**:

* `--fields <str>`: DHIS2 field selector.  [default: id,name,displayName,users]
* `--filter <str>`: Filter &#x27;property:operator:value&#x27; (repeatable).
* `--order <str>`: Sort clause &#x27;property:asc|desc&#x27; (repeatable).
* `--page-size <int>`: Server-side page size.
* `--help`: Show this message and exit.

#### `d2w user group get`

Fetch one user group by UID. Prints a concise summary; `--json` for full payload.

**Usage**:

```console
$ d2w user group get [OPTIONS] {uid}
```

**Arguments**:

* `uid`: User-group UID.  [required]

**Options**:

* `--fields <str>`: DHIS2 field selector.
* `--help`: Show this message and exit.

#### `d2w user group create`

Create a user group (then add members with `add-member`).

**Usage**:

```console
$ d2w user group create [OPTIONS]
```

**Options**:

* `--name <str>`: User-group name.  [required]
* `--code <str>`: Business code.
* `--uid <str>`: Explicit 11-char UID.
* `--help`: Show this message and exit.

#### `d2w user group delete`

Delete a user group by UID.

**Usage**:

```console
$ d2w user group delete [OPTIONS] {uid}
```

**Arguments**:

* `uid`: User-group UID.  [required]

**Options**:

* `-y, --yes`: Skip the confirmation prompt.
* `--help`: Show this message and exit.

#### `d2w user group add-member`

Add a user to a group (POST /api/userGroups/&lt;gid&gt;/users/&lt;uid&gt;).

**Usage**:

```console
$ d2w user group add-member [OPTIONS] {group_uid} {user_uid}
```

**Arguments**:

* `group_uid`: User-group UID.  [required]
* `user_uid`: User UID to add.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w user group remove-member`

Remove a user from a group (DELETE /api/userGroups/&lt;gid&gt;/users/&lt;uid&gt;).

**Usage**:

```console
$ d2w user group remove-member [OPTIONS] {group_uid} {user_uid}
```

**Arguments**:

* `group_uid`: User-group UID.  [required]
* `user_uid`: User UID to remove.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w user group sharing-get`

Print the current sharing block for one user group. `--json` for full payload.

**Usage**:

```console
$ d2w user group sharing-get [OPTIONS] {uid}
```

**Arguments**:

* `uid`: User-group UID.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w user group sharing-grant-user`

Grant one user access to a group (shortcut over `/api/sharing`).

Preserves existing userAccesses/userGroupAccesses by fetching the current
sharing block first, then appending the new grant.

**Usage**:

```console
$ d2w user group sharing-grant-user [OPTIONS] {group_uid} {user_uid}
```

**Arguments**:

* `group_uid`: User-group UID.  [required]
* `user_uid`: User UID to grant.  [required]

**Options**:

* `--metadata-write / --metadata-read`: Grant metadata write (default) or read-only.  [default: metadata-write]
* `--help`: Show this message and exit.

### `d2w user role`

Manage DHIS2 user roles.

**Usage**:

```console
$ d2w user role [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `ls`: List user roles.
* `list`: List user roles.
* `get`: Fetch one user role by UID.
* `authority-list`: Print the sorted authorities carried by...
* `add-user`: Grant a user a role (POST...
* `remove-user`: Revoke a role from a user (DELETE...

#### `d2w user role ls`

List user roles.

**Usage**:

```console
$ d2w user role ls [OPTIONS]
```

**Options**:

* `--fields <str>`: DHIS2 field selector.  [default: id,name,displayName,authorities,users]
* `--filter <str>`: Filter (repeatable).
* `--order <str>`: Sort clause (repeatable).
* `--page-size <int>`: Server-side page size.
* `--help`: Show this message and exit.

#### `d2w user role list`

List user roles.

**Usage**:

```console
$ d2w user role list [OPTIONS]
```

**Options**:

* `--fields <str>`: DHIS2 field selector.  [default: id,name,displayName,authorities,users]
* `--filter <str>`: Filter (repeatable).
* `--order <str>`: Sort clause (repeatable).
* `--page-size <int>`: Server-side page size.
* `--help`: Show this message and exit.

#### `d2w user role get`

Fetch one user role by UID. Prints a concise summary; `--json` for full payload.

**Usage**:

```console
$ d2w user role get [OPTIONS] {uid}
```

**Arguments**:

* `uid`: User-role UID.  [required]

**Options**:

* `--fields <str>`: DHIS2 field selector.
* `--help`: Show this message and exit.

#### `d2w user role authority-list`

Print the sorted authorities carried by one role, one per line.

**Usage**:

```console
$ d2w user role authority-list [OPTIONS] {uid}
```

**Arguments**:

* `uid`: User-role UID.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w user role add-user`

Grant a user a role (POST /api/userRoles/&lt;rid&gt;/users/&lt;uid&gt;).

**Usage**:

```console
$ d2w user role add-user [OPTIONS] {role_uid} {user_uid}
```

**Arguments**:

* `role_uid`: User-role UID.  [required]
* `user_uid`: User UID to grant the role to.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w user role remove-user`

Revoke a role from a user (DELETE /api/userRoles/&lt;rid&gt;/users/&lt;uid&gt;).

**Usage**:

```console
$ d2w user role remove-user [OPTIONS] {role_uid} {user_uid}
```

**Arguments**:

* `role_uid`: User-role UID.  [required]
* `user_uid`: User UID to revoke the role from.  [required]

**Options**:

* `--help`: Show this message and exit.

## `d2w fhir`

FHIR Implementation Guide generation from DHIS2 metadata.

**Usage**:

```console
$ d2w fhir [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `init`: Scaffold a dockerized SUSHI IG project...
* `validate`: Check the instance&#x27;s codes for...
* `check-artifacts`: Refuse the build before it begins: scan...
* `serve`: Serve the project&#x27;s IG as a FHIR read and...
* `forward`: Drain the capture spool into DHIS2 -...
* `spool`: List the capture spool - how many receipts...
* `requeue`: Move receipts DHIS2 refused back into the...
* `withdraw`: Retract from DHIS2 the events named...
* `doctor`: Run the whole FHIR toolchain against this...
* `generate`: Generate the whole IG source from DHIS2...

### `d2w fhir init`

Scaffold a dockerized SUSHI IG project with a fhir.toml for `d2w fhir generate`.

**Usage**:

```console
$ d2w fhir init [OPTIONS] [directory]
```

**Arguments**:

* `directory`: Project directory (default: current directory).  [default: .]

**Options**:

* `--id <str>`: IG package id.  [default: dhis2.fhir.example]
* `--canonical <str>`: Canonical base URL for the IG (no trailing slash).  [default: http://example.org/fhir]
* `--name <str>`: SUSHI name (default: derived from --id).
* `--title <str>`: IG title (default: derived from --name).
* `--publisher <str>`: Publisher name.  [default: Example Organisation]
* `--status <draft|active>`: IG life cycle. Drives the sushi-config status, and the status and experimental flag on every generated definitional resource.  [default: draft]
* `--publisher-url <str>`: Publisher home page. Omit it unless you have a real site: the IG publisher links it from every generated page, and pointing it at the canonical yields one broken link per page.
* `--profile <str>`: DHIS2 profile to seed the `profile` key of the scaffolded fhir.toml with, so `d2w fhir generate` reads that instance without a flag. Offline: the name is written as given, never resolved against profiles.toml.
* `--sushi-timeout <int>`: Seconds the IG publisher gives its internal SUSHI run, written to `[FSH] timeout` of ig/fsh.ini. It bounds the FSH targets alone - the registry and the terminology ship as pre-built JSON - and an overrun fails the build with exit 143.  [default: 1800]
* `--max-level <int>`: Deepest organisation-unit level to generate, seeding `[generate.organisation_units]` max_level. A hierarchy fans out at the bottom and every unit emits two instances, so this is the dial that bounds how much the IG publisher renders. Offline: written as given.
* `--data-set <str>`: Data set UID to seed `[generate.data_sets]` include_ids with (repeatable). Offline: the UID is written to fhir.toml as given, never checked against an instance.
* `--event-program <str>`: Event program UID to seed `[generate.event_programs]` include_ids with (repeatable). Offline: the UID is written to fhir.toml as given, never checked against an instance.
* `--tracker-program <str>`: Tracker program UID to seed `[generate.tracker_programs]` include_ids with (repeatable); the program emits one Questionnaire per program stage. Offline: the UID is written to fhir.toml as given, never checked against an instance.
* `--force`: Overwrite scaffold files that already exist.
* `--refresh`: Bring an existing project&#x27;s scaffold-managed files up to date. Identity comes from the project&#x27;s own fhir.toml, which a refresh never writes, and a file carrying a line the scaffold would not produce is left alone and reported, so your edits survive. Rejects --force.
* `--help`: Show this message and exit.

### `d2w fhir validate`

Check the instance&#x27;s codes for FHIR-safety, writing md/csv/pdf reports grouped by type.

Severity means build impact on the configured IG: an error aborts your build (generate refuses
the same codes), a warning degrades an emitted resource, and an info is instance hygiene on
objects the build never reads. Each finding carries that verdict as its scope - `selection`
for objects the configured selection emits, `instance` for the rest.

The terminal says what the state is: a summary, a count per severity, scope, and category, and
every error by name, because an error is what gates the build and the user has to know which
object holds it. The written report is where a warning is read one row at a time; `--details`
puts every row on the terminal too.

**Usage**:

```console
$ d2w fhir validate [OPTIONS]
```

**Options**:

* `--output-dir <directory>`: Directory to write the report files into, one per format, all named fhir-validate-report (default: reports/ under the project root, else the working directory).
* `--format <str>`: Comma-separated report formats to write: md, csv, pdf.  [default: md,csv,pdf]
* `--code-source <id|code>`: Override `[generate]` concept_code_source for this run. In id mode the option code findings are informational; run with code to see what switching would cost.
* `--details`: List every finding individually instead of the rolled-up category counts.
* `--fail / --no-fail`: Exit 1 when errors are found.  [default: fail]
* `--progress / --no-progress`: Narrate each step on stderr as it completes.  [default: progress]
* `--help`: Show this message and exit.

### `d2w fhir check-artifacts`

Refuse the build before it begins: scan the artifacts on disk for what aborts the IG publisher.

`d2w fhir generate` refuses a run whose selected DHIS2 names or codes carry a `&lt;`. A build reads
no such gate - it publishes whatever `ig/fsh-generated/` and `ig/input/` hold - so output written
before the gate existed, output from an older pinned toolchain, and hand-authored FSH all reach
the publisher, and cost its full run before failing in its final pass.

This is that refusal applied to the files themselves, through the very predicates the generate
gate uses. It names the file, the resource, the element, and the value, so what comes back is the
object rather than the page the publisher happened to die on.

No connection, no profile, no compile - the artifacts are the whole input, so it answers in
seconds. Exit 1 when anything is found, which is what `make build` runs it for.

**Usage**:

```console
$ d2w fhir check-artifacts [OPTIONS] [directory]
```

**Arguments**:

* `directory`: Project to scan (default: the nearest fhir.toml, walking up from the working directory).

**Options**:

* `--fail / --no-fail`: Exit 1 when findings are found.  [default: fail]
* `--help`: Show this message and exit.

### `d2w fhir serve`

Serve the project&#x27;s IG as a FHIR read and capture facade over HTTP.

Reads answer from what the IG publishes.

Received QuestionnaireResponses are stored as receipts, so reading one back says what was submitted.

`--live` builds the store from the instance at startup, as the profile `d2w -p` names.

`--ui` also serves the capture UI at `/`, same-origin with the FHIR routes it reads.

`--basemap` offers another tile layer on the organisation-unit map, and `--basemap none` offers none.

`--auth` says who is served: `none`, `token` (D2W_FHIR_SERVE_TOKENS), `dhis2` (the caller&#x27;s own
credentials), or `jwt` (a token from the OpenID Connect issuer named in `[serve.jwt] issuer`,
verified against that issuer&#x27;s published keys).

Host, port, authentication, strict codes, the UI, and basemaps come from `[serve]` unless a flag beats them.

Two more `[serve]` keys have no flag: `capture = false` serves the guide and receives nothing, and
`spool_dir` says where the receipts live - the same directory `d2w fhir forward` drains.

**Usage**:

```console
$ d2w fhir serve [OPTIONS] [directory]
```

**Arguments**:

* `directory`: Project directory (default: current directory).  [default: .]

**Options**:

* `--live`: Build the served resources from a DHIS2 instance at startup instead of reading the compiled IG off disk. The store is a snapshot of the instance the server started against, and the one client that built it stays open for the life of the process, because the register routes read the instance per request.
* `--host <str>`: Interface to bind, overriding `[serve] host`. The default is loopback. Binding anything else while neither --auth nor `[serve] auth` states a posture is refused: who reaches this facade and who it answers are one decision.
* `--port <int>`: Port to listen on, overriding `[serve] port` (default 8080).
* `--auth <none|token|dhis2|jwt>`: Who this facade serves, overriding `[serve] auth`. `none` serves every caller; `token` takes a static bearer token out of D2W_FHIR_SERVE_TOKENS; `dhis2` takes the caller&#x27;s own DHIS2 credentials and checks them against the instance this run reads, which needs --live; `jwt` takes a token from the OpenID Connect issuer named in `[serve.jwt] issuer`, verified against that issuer&#x27;s published keys. Binding an interface other than loopback while neither this flag nor fhir.toml states a posture is refused.
* `--auth-scope <write|all>`: How much of the surface the posture covers, overriding `[serve] auth_scope`. `write` asks for credentials on `POST /QuestionnaireResponse` and leaves every read open; `all` asks for them everywhere except `/metadata`, which stays open so a client can read the posture it has to meet.
* `--strict-codes / --no-strict-codes`: Refuse a received answer whose code is outside the served terminology, overriding `[serve] strict_codes`. The default records the drift as a warning and stores the submission, because an option added to the instance since the IG was built is a fact about the instance, not a client mistake.
* `--ui / --no-ui`: Serve the capture UI at `/` alongside the FHIR routes, overriding `[serve] ui`. The bundle is mounted around them and shadows none of them; a checkout that has never run `make build-frontend` is refused rather than served blank.
* `--basemap <str>`: Raster tile layer the capture UI&#x27;s organisation-unit map offers under the boundaries, overriding `[serve.basemaps]` (default: OpenStreetMap&#x27;s standard tiles). Repeat it to offer several: `Name=https://.../{z}/{x}/{y}.png`, or a bare template named after its host. The map&#x27;s layer control always carries a None entry beside them, and `--basemap none` offers nothing else - which is what an air-gapped deployment wants, the tiles being the only thing in the UI that reaches an origin other than this server.
* `--help`: Show this message and exit.

### `d2w fhir forward`

Drain the capture spool into DHIS2 - translate every received response and post it.

DRY RUN IS THE DEFAULT. Every payload is posted to the real instance under the endpoint&#x27;s own
validate-only mode, so DHIS2&#x27;s rules decide the answer and nothing is written; `--import` commits.

The posture comes from `[forward]` in fhir.toml - `import`, `register_completeness`,
`overwrites`, `corrections`, and `withdrawals` - unless a flag here overrides it for this run,
and from the defaults above when the file states none. Which spool is drained is
`[serve] spool_dir`, the same key the server writes receipts under.

`corrections` and `withdrawals` are the deployment&#x27;s posture towards a submission that names what
it amends or retracts, and the run states them rather than acting on them: a drain imports, and
`d2w fhir withdraw` is what reads `withdrawals`.

An imported response moves from the spool&#x27;s received/ to forwarded/, a DHIS2-rejected one to
rejected/ beside a report, and a translator-refused one stays put - fix and forward again.

Every payload names its own DHIS2 object - an event&#x27;s UID is derived from the receipt&#x27;s logical id -
so one receipt forwarded twice is refused as an object the instance holds, never imported twice.

An aggregate response whose status is `completed` also registers the data set complete for the
period, organisation unit, and attribute option combo its values landed under - a second write,
made only after DHIS2 has taken the values. `in-progress` imports the values and registers
nothing, and `--no-register-completeness` turns the second write off for the whole run.

A value an earlier submission already sent is named in the run, with the receipt that sent it and
when that receipt arrived. DHIS2 replaces such a value in place and counts the write exactly as it
counts a first entry, so no import summary can say it happened; a dry run says it too, while there
is still time to act on it. `--overwrites refuse` leaves any response holding one in the queue,
with each covered value written down beside it, instead of posting it.

A DHIS2 rejection exits 1. A dry run counts a stage event whose enrollment a registration of the
same run creates as unverifiable rather than rejected - a dry run writes nothing, so there is no
enrollment to check it against - and a run whose only failures are those exits 0.

Outcomes land in reports/fhir-forward-report.md; `--details` prints them here instead.

**Usage**:

```console
$ d2w fhir forward [OPTIONS] [directory]
```

**Arguments**:

* `directory`: Project directory (default: current directory).  [default: .]

**Options**:

* `--import / --dry-run`: Commit the payloads to DHIS2 and move the receipts, overriding `[forward] import`. The default is a dry run: every payload still goes to the real endpoint under its own validate-only mode, and nothing is written and nothing moves.
* `--strict-codes / --no-strict-codes`: Refuse a coded answer whose code is outside the served terminology, overriding `[serve] strict_codes`. Lenient resolves the DHIS2 option UID and code too, and notes it.
* `--register-completeness / --no-register-completeness`: Register the data set complete for every aggregate response whose status is `completed`, once DHIS2 has taken its values, overriding `[forward] register_completeness`. On by default - the response said it was finished.
* `--overwrites <allow|refuse>`: What to do with an aggregate value a forwarded receipt already sent, overriding `[forward] overwrites`. `allow` - the default - posts it and names it; `refuse` leaves the whole response in the queue with the covered values written down beside it.
* `--corrections <off|amend>`: Whether this deployment accepts a submission that names the receipt it corrects, overriding `[forward] corrections`. Off by default. Stated by the run rather than acted on by it - a drain imports, and a correction lands on the corrected receipt&#x27;s identity.
* `--withdrawals <off|retract>`: Whether this deployment retracts what it forwarded, overriding `[forward] withdrawals`. Off by default, and read by `d2w fhir withdraw` rather than by the drain, which never deletes anything.
* `--details`: Print every response&#x27;s outcome instead of writing them to the report.
* `--progress / --no-progress`: Narrate each step on stderr as it completes.  [default: progress]
* `--help`: Show this message and exit.

### `d2w fhir spool`

List the capture spool - how many receipts wait for DHIS2, and what became of the rest.

Reads the project&#x27;s own .serve/responses/ directory and nothing else: no DHIS2 connection, no
profile, no network. Which directory a receipt&#x27;s file is in is its state, and the report DHIS2&#x27;s
answer was written into says why a drained one is where it is.

A file that does not read as a receipt is moved to .serve/responses/malformed/ with its reason
beside it and counted there, so one unreadable file costs one row rather than the listing.

**Usage**:

```console
$ d2w fhir spool [OPTIONS] [directory]
```

**Arguments**:

* `directory`: Project directory (default: current directory).  [default: .]

**Options**:

* `--details`: List every receipt, not just how many are in each state.
* `--help`: Show this message and exit.

### `d2w fhir requeue`

Move receipts DHIS2 refused back into the queue, so the next forward posts them again.

The one reverse move the spool has, and it is a decision rather than a repair: a rejection is
DHIS2 stating that this payload is wrong, so nothing moves it back until a person who has changed
the instance, the guide, or their mind says so.

The import report stays in rejected/ as the record of what DHIS2 last answered about the payload.
The next drain writes a fresh one wherever the receipt lands.

Needs no DHIS2 connection and no profile - it is a rename inside the project directory.

**Usage**:

```console
$ d2w fhir requeue [OPTIONS] [response_ids]...
```

**Arguments**:

* `response_ids...`: Receipt ids to move back into the queue.

**Options**:

* `--directory <directory>`: Project directory (default: current directory).  [default: .]
* `--all-rejected`: Move every receipt DHIS2 refused back into the queue.
* `--help`: Show this message and exit.

### `d2w fhir withdraw`

Retract from DHIS2 the events named forwarded receipts landed, and file each receipt as withdrawn.

WITHDRAWAL IS TERMINAL. DHIS2 burns the UID of a tracker object it deletes and refuses it under
every import strategy afterwards, so a withdrawn receipt can never be forwarded again. What
remains in the instance is a hidden copy of the event carrying its values, which no ordinary read
returns - not the nothing that the word &quot;deleted&quot; implies.

DRY RUN IS THE DEFAULT. The delete goes to the real instance under the tracker endpoint&#x27;s own
validate-only mode, so DHIS2 answers whether it would take it while nothing is written; `--import`
commits.

`[forward] withdrawals` gates the whole command and is off unless this project says otherwise -
a project that publishes forms and forwards them is not thereby one that reaches back into what
DHIS2 already holds. `--withdrawals retract` states it for one run.

The receipt is never rewritten. Its file moves from forwarded/ to withdrawn/ with a sidecar
holding what DHIS2 answered the delete, and the import report that recorded what it landed stays
in forwarded/, because that document is still true of that import.

Only a receipt in forwarded/ that landed a single event can be withdrawn, and every id is checked
before anything is posted. `d2w data aggregate delete` and `d2w data tracker delete` are the raw
escape hatches for the other kinds, outside the FHIR path.

**Usage**:

```console
$ d2w fhir withdraw [OPTIONS] {response_ids}...
```

**Arguments**:

* `response_ids...`: Forwarded receipt ids to retract from DHIS2.  [required]

**Options**:

* `--directory <directory>`: Project directory (default: current directory).  [default: .]
* `--import / --dry-run`: Delete the events in DHIS2 and file the receipts under withdrawn/. The default is a dry run: the delete goes to the real endpoint under its own validate-only mode, and nothing is written and nothing moves.  [default: dry-run]
* `--withdrawals <off|retract>`: Whether this project retracts what it forwarded, overriding `[forward] withdrawals`. Off by default, and `retract` is what this command requires.
* `--help`: Show this message and exit.

### `d2w fhir doctor`

Run the whole FHIR toolchain against this profile&#x27;s instance and report what the instance breaks.

Nine phases in a throwaway workspace: connect, scaffold, generate, compile, validate, serve,
capture, forward, oracle. Each reports pass, warn, fail, skipped, or blocked with its reason.

The instance comes from `d2w -p &lt;name&gt;` and the ambient profile resolution, as `d2w fhir serve` does.

A phase that fails never stops one that does not depend on it, and only a failure exits 1.

Compiling needs a FSH compiler on the machine; without one the phase is skipped and the served
store is built by the live builders instead, so every later phase still runs.

`--live` adds the oracle: the DHIS2 objects behind a seeded sample of the served resources are
fetched back and the instance decides whether the served output still derives from them.

The run writes reports/fhir-doctor-report.md, into the workspace when one was named and into the
working directory otherwise.

**Usage**:

```console
$ d2w fhir doctor [OPTIONS]
```

**Options**:

* `--workspace <directory>`: Directory to run in, kept after the run. The default is a temporary directory, removed when the run ends unless --keep says otherwise.
* `--keep`: Keep the temporary workspace, so the generated project can be read afterwards.
* `--all-targets`: Scaffold empty selection tables, which takes every data set, every program, and every organisation-unit level. The default is a small representative probe.
* `--live`: Run the oracle phase: fetch the DHIS2 objects behind a sample of the served resources and let the instance judge whether each one still derives from current instance state.
* `--samples <int range>`: How many resources per family the oracle deep-compares.  [default: 5; x&gt;=0]
* `--progress / --no-progress`: Narrate each step on stderr as it completes.  [default: progress]
* `--help`: Show this message and exit.

### `d2w fhir generate`

Generate the whole IG source from DHIS2 metadata, or one named target of it.

Bare `d2w fhir generate` runs every target off a single pass over the instance.

The foundation runs first because it reads nothing, the pages last because they narrate the rest.

Notes land in reports/fhir-generate-notes.md; `--details` prints them here instead.

Name a target to run that one alone; the flags here belong to the bare run.

**Usage**:

```console
$ d2w fhir generate [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--details`: Print every note inline instead of writing them to the notes report.
* `--progress / --no-progress`: Narrate each step on stderr as it completes.  [default: progress]
* `--help`: Show this message and exit.

**Commands**:

* `foundation`: Generate the DHIS2 identifier aliases, the...
* `option-sets`: Generate CodeSystem/ValueSet JSON from...
* `categories`: Generate CodeSystem/ValueSet JSON from...
* `questionnaires`: Generate Questionnaire FSH into...
* `examples`: Generate example QuestionnaireResponses...
* `org-units`: Generate Organization/Location FSH from...
* `pages`: Generate the narrative site pages and the...
* `load-set`: Write a synthetic QuestionnaireResponse...

#### `d2w fhir generate foundation`

Generate the DHIS2 identifier aliases, the extensions, and the capture contract into the FHIR project.

**Usage**:

```console
$ d2w fhir generate foundation [OPTIONS]
```

**Options**:

* `--progress / --no-progress`: Narrate each step on stderr as it completes.  [default: progress]
* `--help`: Show this message and exit.

#### `d2w fhir generate option-sets`

Generate CodeSystem/ValueSet JSON from DHIS2 option sets into the nearest FHIR project.

**Usage**:

```console
$ d2w fhir generate option-sets [OPTIONS]
```

**Options**:

* `--progress / --no-progress`: Narrate each step on stderr as it completes.  [default: progress]
* `--help`: Show this message and exit.

#### `d2w fhir generate categories`

Generate CodeSystem/ValueSet JSON from DHIS2 categories into the nearest FHIR project.

**Usage**:

```console
$ d2w fhir generate categories [OPTIONS]
```

**Options**:

* `--progress / --no-progress`: Narrate each step on stderr as it completes.  [default: progress]
* `--help`: Show this message and exit.

#### `d2w fhir generate questionnaires`

Generate Questionnaire FSH into data-sets/, event-programs/, tracker-programs/, and data-dictionary/.

A data set and an event program are one Questionnaire each.

A tracker program is one Questionnaire per program stage, filed under its program&#x27;s UID.

A form whose DHIS2 organisation-unit assignment narrows the published registry also gets one
List of the Locations it admits, into resources/assignments/.

**Usage**:

```console
$ d2w fhir generate questionnaires [OPTIONS]
```

**Options**:

* `--progress / --no-progress`: Narrate each step on stderr as it completes.  [default: progress]
* `--help`: Show this message and exit.

#### `d2w fhir generate examples`

Generate example QuestionnaireResponses for every configured data set, event program, and tracker stage.

**Usage**:

```console
$ d2w fhir generate examples [OPTIONS]
```

**Options**:

* `--progress / --no-progress`: Narrate each step on stderr as it completes.  [default: progress]
* `--help`: Show this message and exit.

#### `d2w fhir generate org-units`

Generate Organization/Location FSH from DHIS2 organisation units into the nearest FHIR project.

**Usage**:

```console
$ d2w fhir generate org-units [OPTIONS]
```

**Options**:

* `--progress / --no-progress`: Narrate each step on stderr as it completes.  [default: progress]
* `--help`: Show this message and exit.

#### `d2w fhir generate pages`

Generate the narrative site pages and the per-artifact intros into ig/input/pagecontent/.

**Usage**:

```console
$ d2w fhir generate pages [OPTIONS]
```

**Options**:

* `--progress / --no-progress`: Narrate each step on stderr as it completes.  [default: progress]
* `--help`: Show this message and exit.

#### `d2w fhir generate load-set`

Write a synthetic QuestionnaireResponse corpus into load/ for posting at a running `d2w fhir serve`.

A load set is test data, not IG source: it lands beside `ig/` rather than inside it.

The scaffold gitignores it, and `d2w fhir generate` never writes it.

A corpus mints the DHIS2 identities it names, so it imports once: DHIS2 refuses a second import
of the same corpus with E1002 and E1080 because those UIDs already exist. Pass `--salt` to mint
a fresh corpus for a second import; the same salt reproduces the same corpus.

**Usage**:

```console
$ d2w fhir generate load-set [OPTIONS]
```

**Options**:

* `--per-target <int range>`: How many synthetic responses each questionnaire target contributes.  [default: 25; x&gt;=1]
* `--salt <str>`: Mint a different corpus from the same metadata - name any string to move every drawn value.
* `--output-dir <directory>`: Directory to write the `load/` corpus into (default: the project root).
* `--progress / --no-progress`: Narrate each step on stderr as it completes.  [default: progress]
* `--help`: Show this message and exit.
