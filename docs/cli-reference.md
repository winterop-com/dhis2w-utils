# CLI reference

d2w — command-line interface for DHIS2 (discovers plugins from dhis2w-core).

**Usage**:

```console
$ d2w [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `-p, --profile TEXT`: DHIS2 profile name (overrides DHIS2_PROFILE env + TOML default).
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

## `d2w schema`

Describe a generated type&#x27;s fields (metadata or instance-side; prefers the OpenAPI tree).

**Usage**:

```console
$ d2w schema [OPTIONS] TYPE_NAME
```

**Arguments**:

* `TYPE_NAME`: Type name, e.g. dataElement or TrackedEntity (case-insensitive; plural wire names ok).  [required]

**Options**:

* `--source TEXT`: Which generated tree to read: auto (prefer oas), oas, or schemas.  [default: auto]
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

* `--dimension, --dim TEXT`: Repeatable &#x27;axis:value&#x27;: dx:&lt;UID&gt;, pe:&lt;period&gt; (both required), ou:&lt;UID&gt;.  [required]
* `--shape TEXT`: Response shape: `table` (default, aggregated), `raw` (/api/analytics/rawData), `dvs` (/api/analytics/dataValueSet — DataValueSet shape).  [default: table]
* `--filter TEXT`: Filter string (repeatable), same syntax as --dimension.
* `--agg TEXT`: SUM | AVERAGE | COUNT | MIN | MAX | AVERAGE_SUM_ORG_UNIT ...
* `--output-id-scheme TEXT`: UID | NAME | CODE | ID — how UIDs appear in the response
* `--num-den / --no-num-den`: Include indicator numerator/denominator columns.  [default: no-num-den]
* `--display-property TEXT`: NAME | SHORTNAME — which label to render metadata with.
* `--start-date TEXT`: Fixed window start, ISO date YYYY-MM-DD (alternative to a pe: dimension).
* `--end-date TEXT`: Fixed window end, ISO date YYYY-MM-DD.
* `--skip-meta`
* `--help`: Show this message and exit.

### `d2w analytics outlier-detection`

Run `/api/analytics/outlierDetection` — flag statistical anomalies in data values.

**Usage**:

```console
$ d2w analytics outlier-detection [OPTIONS]
```

**Options**:

* `--data-element, --de TEXT`: Data-element UID (repeatable).
* `--data-set, --ds TEXT`: Data-set UID (repeatable) — expanded to its dataElements.
* `--org-unit, --ou TEXT`: Org-unit UID (repeatable).
* `--period, --pe TEXT`: Period identifier (e.g. LAST_12_MONTHS, 202401).
* `--start-date TEXT`: ISO date YYYY-MM-DD.
* `--end-date TEXT`: ISO date YYYY-MM-DD.
* `--algorithm TEXT`: Z_SCORE (default) | MODIFIED_Z_SCORE | MIN_MAX. (Upstream OAS still shows MOD_Z_SCORE but the server rejects that value — see BUGS.md.)
* `--threshold FLOAT`: Standard-deviation cutoff (default 3.0).
* `--max-results INTEGER`: Cap the number of outliers returned (default 500).
* `--order-by TEXT`: ABS_DEV | STANDARD_DEVIATION | Z_SCORE | ...
* `--sort-order TEXT`: ASC | DESC.
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
$ d2w analytics events query [OPTIONS] PROGRAM
```

**Arguments**:

* `PROGRAM`: Program UID.  [required]

**Options**:

* `--mode TEXT`: `query` (line-listed events) or `aggregate` (grouped counts).  [default: query]
* `--dimension, --dim TEXT`: Repeatable &#x27;axis:value&#x27;: pe:&lt;period&gt;, ou:&lt;UID&gt;. Aggregate value dim = &lt;stage&gt;.&lt;de&gt; (no dx:).
* `--filter TEXT`: Filter string (repeatable), same syntax as --dimension.
* `--stage TEXT`: Program stage UID to narrow events.
* `--output-type TEXT`: EVENT | ENROLLMENT | TRACKED_ENTITY_INSTANCE (row shape).
* `--start-date TEXT`: Fixed window start, ISO date YYYY-MM-DD (alternative to a pe: dimension).
* `--end-date TEXT`: Fixed window end, ISO date YYYY-MM-DD.
* `--skip-meta`
* `--page INTEGER`
* `--page-size INTEGER`
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
$ d2w analytics enrollments query [OPTIONS] PROGRAM
```

**Arguments**:

* `PROGRAM`: Program UID.  [required]

**Options**:

* `--dimension, --dim TEXT`: Dimension string (repeatable).
* `--filter TEXT`: Filter string (repeatable).
* `--start-date TEXT`: Fixed window start, ISO date YYYY-MM-DD (alternative to a pe: dimension).
* `--end-date TEXT`: Fixed window end, ISO date YYYY-MM-DD.
* `--skip-meta`
* `--page INTEGER`
* `--page-size INTEGER`
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
$ d2w analytics tracked-entities query [OPTIONS] TRACKED_ENTITY_TYPE
```

**Arguments**:

* `TRACKED_ENTITY_TYPE`: TrackedEntityType UID.  [required]

**Options**:

* `--dimension, --dim TEXT`: Dimension string (repeatable).
* `--filter TEXT`: Filter string (repeatable).
* `--program TEXT`: Program UID (repeatable) to narrow results.
* `--start-date TEXT`: Fixed window start, ISO date YYYY-MM-DD (alternative to a pe: dimension).
* `--end-date TEXT`: Fixed window end, ISO date YYYY-MM-DD.
* `--ou-mode TEXT`: SELECTED|CHILDREN|DESCENDANTS|ACCESSIBLE|ALL (default SELECTED; DESCENDANTS reaches facilities).
* `--display-property TEXT`: NAME | SHORTNAME.
* `--skip-meta`
* `--skip-data`
* `--include-metadata-details`: Include nested objects in the metaData map.
* `--page INTEGER`
* `--page-size INTEGER`
* `--asc TEXT`: Field to sort ascending (repeatable).
* `--desc TEXT`: Field to sort descending (repeatable).
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
$ d2w apps add [OPTIONS] SOURCE
```

**Arguments**:

* `SOURCE`: A path to a local `.zip` (installs via /api/apps), an App Hub version id, or an App Hub app id (the latest version is resolved).  [required]

**Options**:

* `--help`: Show this message and exit.

### `d2w apps rm`

Uninstall an app by key (`DELETE /api/apps/{key}`).

**Usage**:

```console
$ d2w apps rm [OPTIONS] KEY
```

**Arguments**:

* `KEY`: App key (folder name) from `apps list`.  [required]

**Options**:

* `-y, --yes`: Skip the confirmation prompt.
* `--help`: Show this message and exit.

### `d2w apps remove`

Uninstall an app by key (`DELETE /api/apps/{key}`).

**Usage**:

```console
$ d2w apps remove [OPTIONS] KEY
```

**Arguments**:

* `KEY`: App key (folder name) from `apps list`.  [required]

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
$ d2w apps update [OPTIONS] [KEY]
```

**Arguments**:

* `[KEY]`: App key; omit with --all to update every app.

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
$ d2w apps restore [OPTIONS] MANIFEST
```

**Arguments**:

* `MANIFEST`: Path to a snapshot JSON file produced by `d2w apps snapshot`.  [required]

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

* `-o, --output PATH`: Write the snapshot JSON to this file. Omit to print to stdout.
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

* `-s, --search TEXT`: Case-insensitive substring filter on name + description (client-side).
* `--limit INTEGER`: Cap the number of rows shown.  [default: 50]
* `--help`: Show this message and exit.

### `d2w apps hub-versions`

List every published version of one App Hub app (`GET /api/appHub`).

Prints `version / id / channel / DHIS2 min-&gt;max` for each version, newest
first. The `id` values are the version ids `d2w apps add &lt;id&gt;` installs
directly (pinning that exact version) — use this to pick a version instead
of letting `apps add &lt;app-id&gt;` resolve to the latest.

**Usage**:

```console
$ d2w apps hub-versions [OPTIONS] APP_ID
```

**Arguments**:

* `APP_ID`: App Hub app id (the `id` column from `apps hub-list`).  [required]

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

* `--set TEXT`: Point this DHIS2 instance at a different App Hub (writes the `keyAppHubUrl` system setting).
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

* `--url TEXT`: Base URL of the DHIS2 instance.  [required]
* `--username TEXT`: Login username.  [required]
* `--password TEXT`: Login password.  [required]
* `--name TEXT`: Friendly display name for the token.
* `--expires-in-days INTEGER`: Token lifetime in days; omit for no expiry.
* `--allowed-ip TEXT`: CIDR/IP allowlist entry; repeat for multiple.
* `--allowed-method TEXT`: HTTP method allowlist; repeat for each method.
* `--allowed-referrer TEXT`: Referer URL allowlist; repeat for each.
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

* `-o, --output-dir PATH`: Directory for the PNG output. Defaults to `./screenshots`. Each run auto-creates an `{instance-slug}/` subdirectory keyed on the profile&#x27;s base URL so multi-stack captures don&#x27;t overwrite.
* `--only TEXT`: Capture only these dashboard UIDs; repeat for multiple.
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

* `-o, --output-dir PATH`: Directory for the PNG output. Defaults to `./screenshots`. Each run auto-creates an `{instance-slug}/` subdirectory keyed on the profile&#x27;s base URL so multi-stack captures don&#x27;t overwrite.
* `--only TEXT`: Capture only these Visualization UIDs; repeat for multiple.
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

* `-o, --output-dir PATH`: Directory for the PNG output. Defaults to `./screenshots`. Each run auto-creates an `{instance-slug}/` subdirectory keyed on the profile&#x27;s base URL so multi-stack captures don&#x27;t overwrite.
* `--only TEXT`: Capture only these Map UIDs; repeat for multiple.
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
$ d2w customize logo-front [OPTIONS] FILE
```

**Arguments**:

* `FILE`: PNG/JPG/SVG to upload as the login splash logo.  [required]

**Options**:

* `--help`: Show this message and exit.

### `d2w customize logo-banner`

Upload the top-menu banner logo (appears on every authenticated page).

**Usage**:

```console
$ d2w customize logo-banner [OPTIONS] FILE
```

**Arguments**:

* `FILE`: PNG/JPG/SVG to upload as the top-menu banner.  [required]

**Options**:

* `--help`: Show this message and exit.

### `d2w customize style`

Upload a CSS stylesheet that DHIS2 serves on every authenticated page.

NOTE: DHIS2&#x27;s standalone login app (`/dhis-web-login/`) does NOT include this
stylesheet. Post-auth pages do.

**Usage**:

```console
$ d2w customize style [OPTIONS] FILE
```

**Arguments**:

* `FILE`: CSS file to upload as `/api/files/style`.  [required]

**Options**:

* `--help`: Show this message and exit.

### `d2w customize apply`

Apply a committed preset directory in one call (skips files that don&#x27;t exist).

**Usage**:

```console
$ d2w customize apply [OPTIONS] DIRECTORY
```

**Arguments**:

* `DIRECTORY`: Directory containing optional logo_front.png, logo_banner.png, style.css, preset.json.  [required]

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

* `--data-set, --ds TEXT`: DataSet UID.
* `--period, --pe TEXT`: Period; match the dataSet&#x27;s periodType (Monthly=202401, Yearly=2024, Weekly=2024W12).
* `--start-date TEXT`: ISO date (YYYY-MM-DD).
* `--end-date TEXT`: ISO date (YYYY-MM-DD).
* `--org-unit, --ou TEXT`: OrganisationUnit UID.
* `--org-unit-group, --oug TEXT`: OrganisationUnitGroup UID (alternative to --ou).
* `--children`: Include descendant org units (values usually live at facility level).
* `--data-element-group, --deg TEXT`: DataElementGroup UID (narrows to its member DEs).
* `--include-deleted`: Also return soft-deleted values.
* `--last-updated TEXT`: Only values modified since a date (YYYY-MM-DD) or duration (e.g. 7d).
* `--limit INTEGER`: Max rows to include in output.
* `--help`: Show this message and exit.

#### `d2w data aggregate push`

Bulk push data values from a JSON file.

**Usage**:

```console
$ d2w data aggregate push [OPTIONS] FILE
```

**Arguments**:

* `FILE`: Path to a JSON file containing a dataValues array or envelope.  [required]

**Options**:

* `--data-set, --ds TEXT`
* `--period, --pe TEXT`
* `--org-unit, --ou TEXT`
* `--dry-run`
* `--strategy TEXT`: CREATE | UPDATE | CREATE_AND_UPDATE | DELETE
* `--help`: Show this message and exit.

#### `d2w data aggregate set`

Set a single data value.

**Usage**:

```console
$ d2w data aggregate set [OPTIONS]
```

**Options**:

* `--data-element, --de TEXT`: DataElement UID.  [required]
* `--period, --pe TEXT`: Period (e.g. 202401).  [required]
* `--org-unit, --ou TEXT`: OrganisationUnit UID.  [required]
* `--value TEXT`: The value to set (as a string).  [required]
* `--coc TEXT`: CategoryOptionCombo UID.
* `--aoc TEXT`: AttributeOptionCombo UID (category-combo attributes).
* `--comment TEXT`
* `--help`: Show this message and exit.

#### `d2w data aggregate delete`

Delete a single data value.

**Usage**:

```console
$ d2w data aggregate delete [OPTIONS]
```

**Options**:

* `--data-element, --de TEXT`: [required]
* `--period, --pe TEXT`: [required]
* `--org-unit, --ou TEXT`: [required]
* `--coc TEXT`
* `--aoc TEXT`
* `--help`: Show this message and exit.

#### `d2w data aggregate followup`

Set or clear the follow-up flag on a single data value.

**Usage**:

```console
$ d2w data aggregate followup [OPTIONS]
```

**Options**:

* `--data-element, --de TEXT`: [required]
* `--period, --pe TEXT`: [required]
* `--org-unit, --ou TEXT`: [required]
* `--on / --off`: Set (--on) or clear (--off) the follow-up flag.  [default: on]
* `--coc TEXT`
* `--aoc TEXT`
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
$ d2w data tracker ls [OPTIONS] [TYPE]
```

**Arguments**:

* `[TYPE]`: TrackedEntityType name (case-insensitive) or UID — e.g. &#x27;Person&#x27; or &#x27;tet01234567&#x27;. Give this OR --program (not both).

**Options**:

* `--program TEXT`: Program UID — list the program&#x27;s tracked entities. Alternative to TYPE; DHIS2 rejects a program and a TrackedEntityType together.
* `--te-uids TEXT`: Comma-separated tracked-entity UIDs to fetch directly.
* `--org-unit, --ou TEXT`: OrganisationUnit UID to scope the listing.
* `--ou-mode TEXT`: Org-unit scope: SELECTED | CHILDREN | DESCENDANTS | ACCESSIBLE | ALL (default DESCENDANTS).  [default: DESCENDANTS]
* `--fields TEXT`: DHIS2 field selector (comma-separated; nest with []).
* `--filter TEXT`: Attribute filter &#x27;ATTR_UID:op:value&#x27; (repeatable).
* `--page-size INTEGER`: [default: 50]
* `--page INTEGER`: 1-based page number.
* `--updated-after TEXT`: ISO-8601 cutoff — only entities updated after this.
* `--help`: Show this message and exit.

#### `d2w data tracker list`

List tracked entities by TrackedEntityType (TYPE) or by --program — give exactly one.

Example: d2w data tracker list Person --ou ImspTQPwCqd

**Usage**:

```console
$ d2w data tracker list [OPTIONS] [TYPE]
```

**Arguments**:

* `[TYPE]`: TrackedEntityType name (case-insensitive) or UID — e.g. &#x27;Person&#x27; or &#x27;tet01234567&#x27;. Give this OR --program (not both).

**Options**:

* `--program TEXT`: Program UID — list the program&#x27;s tracked entities. Alternative to TYPE; DHIS2 rejects a program and a TrackedEntityType together.
* `--te-uids TEXT`: Comma-separated tracked-entity UIDs to fetch directly.
* `--org-unit, --ou TEXT`: OrganisationUnit UID to scope the listing.
* `--ou-mode TEXT`: Org-unit scope: SELECTED | CHILDREN | DESCENDANTS | ACCESSIBLE | ALL (default DESCENDANTS).  [default: DESCENDANTS]
* `--fields TEXT`: DHIS2 field selector (comma-separated; nest with []).
* `--filter TEXT`: Attribute filter &#x27;ATTR_UID:op:value&#x27; (repeatable).
* `--page-size INTEGER`: [default: 50]
* `--page INTEGER`: 1-based page number.
* `--updated-after TEXT`: ISO-8601 cutoff — only entities updated after this.
* `--help`: Show this message and exit.

#### `d2w data tracker get`

Fetch one tracked entity by UID (TrackedEntityType inferred from the entity).

**Usage**:

```console
$ d2w data tracker get [OPTIONS] UID
```

**Arguments**:

* `UID`: Tracked entity UID.  [required]

**Options**:

* `--program TEXT`: Program UID.
* `--fields TEXT`: DHIS2 field selector (comma-separated; nest with []).
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
$ d2w data tracker push [OPTIONS] FILE
```

**Arguments**:

* `FILE`: JSON file containing the tracker bundle.  [required]

**Options**:

* `--strategy TEXT`: CREATE | UPDATE | CREATE_AND_UPDATE | DELETE
* `--atomic TEXT`: ALL | OBJECT
* `--dry-run`
* `--async`
* `--help`: Show this message and exit.

#### `d2w data tracker delete`

Delete tracked entities by UID (cascades to their enrollments + events).

**Usage**:

```console
$ d2w data tracker delete [OPTIONS] UIDS...
```

**Arguments**:

* `UIDS...`: Tracked entity UID(s) to delete.  [required]

**Options**:

* `--async`: Return a job reference immediately instead of waiting.
* `--help`: Show this message and exit.

#### `d2w data tracker register`

Register a tracked entity + enroll in one program in one call.

The typical clinic-intake flow: fills the TrackedEntityAttribute form,
stamps an enrollment into the program, all atomic via POST /api/tracker.
Prints the new tracked-entity + enrollment UIDs so the caller can
reference them downstream.

**Usage**:

```console
$ d2w data tracker register [OPTIONS] PROGRAM
```

**Arguments**:

* `PROGRAM`: Program UID to enroll into.  [required]

**Options**:

* `--org-unit, --ou TEXT`: OrgUnit UID where the TE lives + is enrolled.  [required]
* `--tet TEXT`: TrackedEntityType UID. Defaults to the program&#x27;s trackedEntityType if unset.
* `--attr TEXT`: TrackedEntityAttribute UID=value. Repeatable. Example: --attr w75KJ2mc4zz=Jane
* `--enrolled-at TEXT`: Enrollment date (ISO, e.g. 2024-06-01). Defaults to today server-side.
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
$ d2w data tracker outstanding [OPTIONS] PROGRAM
```

**Arguments**:

* `PROGRAM`: Program UID — the scope for the &#x27;what&#x27;s due&#x27; report.  [required]

**Options**:

* `--org-unit, --ou TEXT`: Narrow to one OU subtree. Default: every active enrollment on the program.
* `--ou-mode TEXT`: SELECTED | CHILDREN | DESCENDANTS | ALL  [default: DESCENDANTS]
* `--page-size INTEGER`: Max enrollments scanned (default 200).  [default: 200]
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
* `delete`: Delete enrollments by UID.
* `create`: Enroll an existing tracked entity in a...

##### `d2w data tracker enrollment ls`

List enrollments (tracker programs only).

**Usage**:

```console
$ d2w data tracker enrollment ls [OPTIONS]
```

**Options**:

* `--program TEXT`: Program UID.
* `--org-unit, --ou TEXT`: OrganisationUnit UID to scope the listing.
* `--ou-mode TEXT`: Org-unit scope: SELECTED | CHILDREN | DESCENDANTS | ACCESSIBLE | ALL (default DESCENDANTS).  [default: DESCENDANTS]
* `--te TEXT`: TrackedEntity UID.
* `--status TEXT`: ACTIVE | COMPLETED | CANCELLED
* `--fields TEXT`: DHIS2 field selector (comma-separated; nest with []).
* `--page-size INTEGER`: [default: 50]
* `--page INTEGER`
* `--updated-after TEXT`
* `--help`: Show this message and exit.

##### `d2w data tracker enrollment list`

List enrollments (tracker programs only).

**Usage**:

```console
$ d2w data tracker enrollment list [OPTIONS]
```

**Options**:

* `--program TEXT`: Program UID.
* `--org-unit, --ou TEXT`: OrganisationUnit UID to scope the listing.
* `--ou-mode TEXT`: Org-unit scope: SELECTED | CHILDREN | DESCENDANTS | ACCESSIBLE | ALL (default DESCENDANTS).  [default: DESCENDANTS]
* `--te TEXT`: TrackedEntity UID.
* `--status TEXT`: ACTIVE | COMPLETED | CANCELLED
* `--fields TEXT`: DHIS2 field selector (comma-separated; nest with []).
* `--page-size INTEGER`: [default: 50]
* `--page INTEGER`
* `--updated-after TEXT`
* `--help`: Show this message and exit.

##### `d2w data tracker enrollment delete`

Delete enrollments by UID.

**Usage**:

```console
$ d2w data tracker enrollment delete [OPTIONS] UIDS...
```

**Arguments**:

* `UIDS...`: Enrollment UID(s) to delete.  [required]

**Options**:

* `--async`: Return a job reference immediately instead of waiting.
* `--help`: Show this message and exit.

##### `d2w data tracker enrollment create`

Enroll an existing tracked entity in a program.

**Usage**:

```console
$ d2w data tracker enrollment create [OPTIONS] TRACKED_ENTITY PROGRAM
```

**Arguments**:

* `TRACKED_ENTITY`: Existing TrackedEntity UID to enroll.  [required]
* `PROGRAM`: Program UID to enroll into.  [required]

**Options**:

* `--at TEXT`: OrgUnit UID where the enrollment lives.  [required]
* `--enrolled-at TEXT`: ISO date; defaults to today server-side.
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

* `--program TEXT`: Program UID.
* `--program-stage TEXT`: ProgramStage UID to narrow to one stage.
* `--org-unit, --ou TEXT`: OrganisationUnit UID to scope the listing.
* `--ou-mode TEXT`: Org-unit scope: SELECTED | CHILDREN | DESCENDANTS | ACCESSIBLE | ALL (default DESCENDANTS).  [default: DESCENDANTS]
* `--te TEXT`: TrackedEntity UID.
* `--enrollment TEXT`: Enrollment UID to list its events.
* `--status TEXT`: Event status: ACTIVE | COMPLETED | VISITED | SCHEDULE | OVERDUE | SKIPPED.
* `--after TEXT`: Only events on/after this ISO date (YYYY-MM-DD).
* `--before TEXT`: Only events on/before this ISO date (YYYY-MM-DD).
* `--fields TEXT`: DHIS2 field selector (comma-separated; nest with []).
* `--page-size INTEGER`: [default: 50]
* `--page INTEGER`
* `--help`: Show this message and exit.

##### `d2w data tracker event list`

List events (event and tracker programs). Scope with --program and/or --org-unit.

Example: data tracker event list --program &lt;programUID&gt; --ou &lt;ouUID&gt;

**Usage**:

```console
$ d2w data tracker event list [OPTIONS]
```

**Options**:

* `--program TEXT`: Program UID.
* `--program-stage TEXT`: ProgramStage UID to narrow to one stage.
* `--org-unit, --ou TEXT`: OrganisationUnit UID to scope the listing.
* `--ou-mode TEXT`: Org-unit scope: SELECTED | CHILDREN | DESCENDANTS | ACCESSIBLE | ALL (default DESCENDANTS).  [default: DESCENDANTS]
* `--te TEXT`: TrackedEntity UID.
* `--enrollment TEXT`: Enrollment UID to list its events.
* `--status TEXT`: Event status: ACTIVE | COMPLETED | VISITED | SCHEDULE | OVERDUE | SKIPPED.
* `--after TEXT`: Only events on/after this ISO date (YYYY-MM-DD).
* `--before TEXT`: Only events on/before this ISO date (YYYY-MM-DD).
* `--fields TEXT`: DHIS2 field selector (comma-separated; nest with []).
* `--page-size INTEGER`: [default: 50]
* `--page INTEGER`
* `--help`: Show this message and exit.

##### `d2w data tracker event delete`

Delete events by UID.

**Usage**:

```console
$ d2w data tracker event delete [OPTIONS] UIDS...
```

**Arguments**:

* `UIDS...`: Event UID(s) to delete.  [required]

**Options**:

* `--async`: Return a job reference immediately instead of waiting.
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

* `--program TEXT`: Program UID.  [required]
* `--stage TEXT`: ProgramStage UID.  [required]
* `--at TEXT`: OrgUnit UID where the event happened.  [required]
* `--enrollment TEXT`: Enrollment UID for tracker (WITH_REGISTRATION) programs. Omit for event (WITHOUT_REGISTRATION) programs.
* `--te TEXT`: TrackedEntity UID (tracker programs only). Optional — DHIS2 derives from the enrollment.
* `--dv TEXT`: DataElement UID=value. Repeatable. Example: --dv fClA2Erf6IO=5
* `--occurred-at TEXT`: ISO event date; defaults to today server-side.
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

* `--te TEXT`: TrackedEntity UID.
* `--enrollment TEXT`: Enrollment UID to list its events.
* `--event TEXT`
* `--fields TEXT`: DHIS2 field selector (comma-separated; nest with []).
* `--page-size INTEGER`: [default: 50]
* `--help`: Show this message and exit.

##### `d2w data tracker relationship list`

List relationships (one of --te/--enrollment/--event required).

**Usage**:

```console
$ d2w data tracker relationship list [OPTIONS]
```

**Options**:

* `--te TEXT`: TrackedEntity UID.
* `--enrollment TEXT`: Enrollment UID to list its events.
* `--event TEXT`
* `--fields TEXT`: DHIS2 field selector (comma-separated; nest with []).
* `--page-size INTEGER`: [default: 50]
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
$ d2w datastore keys [OPTIONS] NAMESPACE
```

**Arguments**:

* `NAMESPACE`: Namespace to list keys in.  [required]

**Options**:

* `--user`: Target the per-user store (/api/userDataStore) instead of the shared one.
* `--help`: Show this message and exit.

### `d2w datastore get`

Print the value stored at `namespace/key` (JSON).

**Usage**:

```console
$ d2w datastore get [OPTIONS] NAMESPACE KEY
```

**Arguments**:

* `NAMESPACE`: Namespace.  [required]
* `KEY`: Key.  [required]

**Options**:

* `--user`: Target the per-user store (/api/userDataStore) instead of the shared one.
* `--help`: Show this message and exit.

### `d2w datastore set`

Create or update `namespace/key`.

**Usage**:

```console
$ d2w datastore set [OPTIONS] NAMESPACE KEY VALUE
```

**Arguments**:

* `NAMESPACE`: Namespace.  [required]
* `KEY`: Key.  [required]
* `VALUE`: Value — parsed as JSON, or stored as a string if not valid JSON.  [required]

**Options**:

* `--user`: Target the per-user store (/api/userDataStore) instead of the shared one.
* `--help`: Show this message and exit.

### `d2w datastore delete`

Delete `namespace/key`.

**Usage**:

```console
$ d2w datastore delete [OPTIONS] NAMESPACE KEY
```

**Arguments**:

* `NAMESPACE`: Namespace.  [required]
* `KEY`: Key.  [required]

**Options**:

* `--user`: Target the per-user store (/api/userDataStore) instead of the shared one.
* `-y, --yes`: Skip the interactive confirmation.
* `--help`: Show this message and exit.

### `d2w datastore delete-namespace`

Delete an entire namespace and every key in it.

**Usage**:

```console
$ d2w datastore delete-namespace [OPTIONS] NAMESPACE
```

**Arguments**:

* `NAMESPACE`: Namespace to delete (all its keys go with it).  [required]

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

* `--url TEXT`: Base URL of the DHIS2 instance.  [required]
* `--username TEXT`: Basic-auth username.
* `--password TEXT`: Basic-auth password.
* `--pat TEXT`: Personal Access Token.
* `--output-root PATH`: Directory containing versioned subfolders; defaults to dhis2w-client&#x27;s generated/ folder.
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

* `--manifest PATH`: Path to a committed schemas_manifest.json. Defaults to every version under the generated root.
* `--output-root PATH`: Directory of versioned subfolders; defaults to dhis2w-client generated/.
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

* `--version TEXT`: Version key (e.g. v42). Defaults to every committed version.
* `--output-root PATH`: Directory of versioned subfolders; defaults to dhis2w-client generated/.
* `--help`: Show this message and exit.

#### `d2w dev codegen diff`

Diff two committed `schemas_manifest.json` files and report drift.

Lists schemas added, removed, and per-property changes (type, klass,
bounds, owner/required/etc). Useful for spotting upstream API drift
when bumping DHIS2 majors.

**Usage**:

```console
$ d2w dev codegen diff [OPTIONS] FROM_VERSION TO_VERSION
```

**Arguments**:

* `FROM_VERSION`: Source version key (e.g. v42).  [required]
* `TO_VERSION`: Target version key (e.g. v43).  [required]

**Options**:

* `--output-root PATH`: Directory of versioned subfolders; defaults to dhis2w-client generated/.
* `--json`: Emit a JSON dump instead of the human-readable report.
* `--help`: Show this message and exit.

### `d2w dev uid`

Generate 11-char DHIS2 UIDs.

**Usage**:

```console
$ d2w dev uid [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `-n, --count INTEGER RANGE`: How many UIDs to generate.  [default: 1; 1&lt;=x&lt;=10000]
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

* `--url TEXT`: URL the sample route will proxy to.  [default: https://httpbin.org/get]
* `--code TEXT`: [default: SMOKE_ROUTE]
* `--keep`: Don&#x27;t delete the sample route afterwards.
* `--help`: Show this message and exit.

#### `d2w dev sample pat`

Create a sample PAT, use it to call /api/me, then (unless --keep) delete it.

**Usage**:

```console
$ d2w dev sample pat [OPTIONS]
```

**Options**:

* `--url TEXT`: DHIS2 base URL (also: DHIS2_URL env).
* `--admin-user TEXT`
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

* `--data-element, --de TEXT`: DataElement UID.  [default: fClA2Erf6IO]
* `--org-unit, --ou TEXT`: OrganisationUnit UID.  [default: Rp268JB6Ne4]
* `--period, --pe TEXT`: Period (e.g. 202406).  [default: 202406]
* `--value TEXT`: [default: 42]
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

* `--url TEXT`: DHIS2 base URL (also: DHIS2_URL env).
* `--admin-user TEXT`
* `--client-id TEXT`: OAuth2 client_id; default = smoke-&lt;epoch&gt;.
* `--keep`: Don&#x27;t delete the sample OAuth2 client afterwards.
* `--help`: Show this message and exit.

#### `d2w dev sample all`

Run every sample in sequence — route, data-value, pat, oauth2-client.

**Usage**:

```console
$ d2w dev sample all [OPTIONS]
```

**Options**:

* `--url TEXT`: DHIS2 base URL (also: DHIS2_URL env).
* `--admin-user TEXT`
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

* `--filter TEXT`: DHIS2 filter, e.g. `name:like:Annual`.
* `--page INTEGER`: 1-indexed page number.
* `--page-size INTEGER`: Rows per page (default 50).
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

* `--filter TEXT`: DHIS2 filter, e.g. `name:like:Annual`.
* `--page INTEGER`: 1-indexed page number.
* `--page-size INTEGER`: Rows per page (default 50).
* `--details`: For each UPLOAD_FILE, also fetch the backing fileResource&#x27;s contentType / size / storageStatus (one extra request per row).
* `--help`: Show this message and exit.

#### `d2w files documents get`

Show metadata for one document.

**Usage**:

```console
$ d2w files documents get [OPTIONS] UID
```

**Arguments**:

* `UID`: Document UID.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w files documents upload`

Upload a binary document — prints the new UID.

**Usage**:

```console
$ d2w files documents upload [OPTIONS] FILE
```

**Arguments**:

* `FILE`: File to upload.  [required]

**Options**:

* `--name TEXT`: Document name (defaults to filename).
* `--help`: Show this message and exit.

#### `d2w files documents upload-url`

Create an EXTERNAL_URL document — no bytes uploaded; DHIS2 links out to `url`.

**Usage**:

```console
$ d2w files documents upload-url [OPTIONS] NAME URL
```

**Arguments**:

* `NAME`: Document display name.  [required]
* `URL`: External URL DHIS2 will link to.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w files documents download`

Download the binary payload to `destination`.

**Usage**:

```console
$ d2w files documents download [OPTIONS] UID DESTINATION
```

**Arguments**:

* `UID`: Document UID.  [required]
* `DESTINATION`: Output file path.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w files documents delete`

Delete one document.

**Usage**:

```console
$ d2w files documents delete [OPTIONS] UID
```

**Arguments**:

* `UID`: Document UID.  [required]

**Options**:

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
$ d2w files resources upload [OPTIONS] FILE
```

**Arguments**:

* `FILE`: File to upload as a fileResource.  [required]

**Options**:

* `--domain [data_value|push_analysis|document|message_attachment|user_avatar|org_unit|icon|job_data]`: FileResource domain (DATA_VALUE, ICON, MESSAGE_ATTACHMENT, ...).  [default: DATA_VALUE]
* `--help`: Show this message and exit.

#### `d2w files resources get`

Show metadata for one file resource.

**Usage**:

```console
$ d2w files resources get [OPTIONS] UID
```

**Arguments**:

* `UID`: FileResource UID.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w files resources download`

Download the file-resource payload to `destination`.

**Usage**:

```console
$ d2w files resources download [OPTIONS] UID DESTINATION
```

**Arguments**:

* `UID`: FileResource UID.  [required]
* `DESTINATION`: Output file path.  [required]

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
$ d2w maintenance task ls [OPTIONS] TASK_TYPE
```

**Arguments**:

* `TASK_TYPE`: Task type, e.g. ANALYTICS_TABLE.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w maintenance task list`

List every task UID recorded for a given job type.

**Usage**:

```console
$ d2w maintenance task list [OPTIONS] TASK_TYPE
```

**Arguments**:

* `TASK_TYPE`: Task type, e.g. ANALYTICS_TABLE.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w maintenance task status`

Print every notification emitted by a task, oldest first.

**Usage**:

```console
$ d2w maintenance task status [OPTIONS] TASK_TYPE TASK_UID
```

**Arguments**:

* `TASK_TYPE`: Task type, e.g. ANALYTICS_TABLE.  [required]
* `TASK_UID`: Task UID returned by the async POST.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w maintenance task watch`

Poll a task until it reports `completed=true`, streaming each new notification.

**Usage**:

```console
$ d2w maintenance task watch [OPTIONS] TASK_TYPE TASK_UID
```

**Arguments**:

* `TASK_TYPE`: Task type, e.g. DATA_INTEGRITY.  [required]
* `TASK_UID`: Task UID returned by the async POST.  [required]

**Options**:

* `--interval FLOAT`: Poll interval in seconds.  [default: 2.0]
* `--timeout FLOAT`: Abort after N seconds (default 600).  [default: 600.0]
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

* `--help`: Show this message and exit.

#### `d2w maintenance cleanup events`

Hard-remove soft-deleted tracker events.

**Usage**:

```console
$ d2w maintenance cleanup events [OPTIONS]
```

**Options**:

* `--help`: Show this message and exit.

#### `d2w maintenance cleanup enrollments`

Hard-remove soft-deleted tracker enrollments.

**Usage**:

```console
$ d2w maintenance cleanup enrollments [OPTIONS]
```

**Options**:

* `--help`: Show this message and exit.

#### `d2w maintenance cleanup tracked-entities`

Hard-remove soft-deleted tracked entities.

**Usage**:

```console
$ d2w maintenance cleanup tracked-entities [OPTIONS]
```

**Options**:

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
$ d2w maintenance dataintegrity run [OPTIONS] [CHECK]...
```

**Arguments**:

* `[CHECK]...`: Check name(s); omit to run every check.

**Options**:

* `--details`: Hit /details (populates issues[]) instead of /summary.
* `--slow`: Include the ~19 `isSlow` checks DHIS2 skips by default. Resolves the full check list via /api/dataIntegrity and passes every name explicitly — DHIS2 only runs a slow check when it&#x27;s named in the `checks` filter.
* `-w, --watch`: After kicking off the job, poll /api/system/tasks until it reports completed=true.
* `--interval FLOAT`: Poll interval in seconds when --watch is set.  [default: 2.0]
* `--timeout FLOAT`: Abort polling after N seconds (default 600).  [default: 600.0]
* `--help`: Show this message and exit.

#### `d2w maintenance dataintegrity result`

Read the stored result of a completed data-integrity run (summary or details mode).

**Usage**:

```console
$ d2w maintenance dataintegrity result [OPTIONS] [CHECK]...
```

**Arguments**:

* `[CHECK]...`: Check name(s) to read; omit for all.

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

* `--last-years INTEGER`
* `--skip-resource-tables`
* `-w, --watch`: After kicking off the job, poll /api/system/tasks until it reports completed=true.
* `--interval FLOAT`: Poll interval in seconds when --watch is set.  [default: 2.0]
* `--timeout FLOAT`: Abort polling after N seconds (default 600).  [default: 600.0]
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
* `--interval FLOAT`: Poll interval in seconds when --watch is set.  [default: 2.0]
* `--timeout FLOAT`: Abort polling after N seconds (default 600).  [default: 600.0]
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
* `--interval FLOAT`: Poll interval in seconds when --watch is set.  [default: 2.0]
* `--timeout FLOAT`: Abort polling after N seconds (default 600).  [default: 600.0]
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
$ d2w maintenance validation run [OPTIONS] ORG_UNIT
```

**Arguments**:

* `ORG_UNIT`: Org-unit UID to evaluate rules under (DHIS2 walks the sub-tree).  [required]

**Options**:

* `--start-date TEXT`: Period start, YYYY-MM-DD.  [required]
* `--end-date TEXT`: Period end, YYYY-MM-DD.  [required]
* `--group TEXT`: ValidationRuleGroup UID to narrow the rules evaluated.
* `--max-results INTEGER`: Cap on violations returned (DHIS2 default ~500).
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
$ d2w maintenance validation validate-expression [OPTIONS] EXPRESSION
```

**Arguments**:

* `EXPRESSION`: DHIS2 expression to parse-check.  [required]

**Options**:

* `--context TEXT`: Expression parser context: one of generic, validation-rule, indicator, predictor, program-indicator.  [default: generic]
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

* `--org-unit, --ou TEXT`: Org-unit UID filter.
* `--period, --pe TEXT`: Period filter (e.g. 202501).
* `--vr TEXT`: Validation-rule UID filter.
* `--page INTEGER`
* `--page-size INTEGER`
* `--help`: Show this message and exit.

##### `d2w maintenance validation result list`

List persisted validation results.

**Usage**:

```console
$ d2w maintenance validation result list [OPTIONS]
```

**Options**:

* `--org-unit, --ou TEXT`: Org-unit UID filter.
* `--period, --pe TEXT`: Period filter (e.g. 202501).
* `--vr TEXT`: Validation-rule UID filter.
* `--page INTEGER`
* `--page-size INTEGER`
* `--help`: Show this message and exit.

##### `d2w maintenance validation result get`

Show one persisted validation result by id.

**Usage**:

```console
$ d2w maintenance validation result get [OPTIONS] RESULT_ID
```

**Arguments**:

* `RESULT_ID`: Numeric validation-result id.  [required]

**Options**:

* `--help`: Show this message and exit.

##### `d2w maintenance validation result delete`

Bulk-delete validation results by filter. At least one filter is required.

**Usage**:

```console
$ d2w maintenance validation result delete [OPTIONS]
```

**Options**:

* `--org-unit, --ou TEXT`: Org-unit UID filter. Repeatable.
* `--period, --pe TEXT`: Period filter. Repeatable.
* `--vr TEXT`: Validation-rule UID filter. Repeatable.
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

* `--start-date TEXT`: Period start, YYYY-MM-DD.  [required]
* `--end-date TEXT`: Period end, YYYY-MM-DD.  [required]
* `--predictor TEXT`: Run one predictor by UID. Mutually exclusive with --group.
* `--group TEXT`: Run all predictors in a PredictorGroup by UID.
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

* `--filter TEXT`: DHIS2 filter. Example: `read:eq:false` for unread only.
* `--page INTEGER`: 1-indexed page number.
* `--page-size INTEGER`: Rows per page (default 50).
* `--help`: Show this message and exit.

### `d2w messaging list`

List conversations the authenticated user is part of.

**Usage**:

```console
$ d2w messaging list [OPTIONS]
```

**Options**:

* `--filter TEXT`: DHIS2 filter. Example: `read:eq:false` for unread only.
* `--page INTEGER`: 1-indexed page number.
* `--page-size INTEGER`: Rows per page (default 50).
* `--help`: Show this message and exit.

### `d2w messaging get`

Show one conversation&#x27;s metadata + message thread.

**Usage**:

```console
$ d2w messaging get [OPTIONS] UID
```

**Arguments**:

* `UID`: Conversation UID.  [required]

**Options**:

* `--help`: Show this message and exit.

### `d2w messaging send`

Create a new conversation with an initial message.

**Usage**:

```console
$ d2w messaging send [OPTIONS] SUBJECT TEXT
```

**Arguments**:

* `SUBJECT`: Subject line.  [required]
* `TEXT`: Message body.  [required]

**Options**:

* `-u, --user TEXT`: User UID recipient. Repeatable.
* `-g, --user-group TEXT`: User-group UID recipient. Repeatable.
* `--org-unit, --ou TEXT`: Organisation-unit UID recipient. Repeatable.
* `-a, --attachment TEXT`: FileResource UID to attach (upload via `d2w files resources upload --domain MESSAGE_ATTACHMENT` first). Repeatable.
* `--help`: Show this message and exit.

### `d2w messaging reply`

Reply to an existing conversation with a plain-text message.

DHIS2&#x27;s reply endpoint takes text/plain only on v42 — attachments +
internal-note flag only work on the initial `send` call.

**Usage**:

```console
$ d2w messaging reply [OPTIONS] UID TEXT
```

**Arguments**:

* `UID`: Conversation UID.  [required]
* `TEXT`: Reply body (plain text).  [required]

**Options**:

* `--help`: Show this message and exit.

### `d2w messaging mark-read`

Mark one or more conversations as read.

**Usage**:

```console
$ d2w messaging mark-read [OPTIONS] UID...
```

**Arguments**:

* `UID...`: Conversation UID(s). One or more.  [required]

**Options**:

* `--help`: Show this message and exit.

### `d2w messaging mark-unread`

Mark one or more conversations as unread.

**Usage**:

```console
$ d2w messaging mark-unread [OPTIONS] UID...
```

**Arguments**:

* `UID...`: Conversation UID(s). One or more.  [required]

**Options**:

* `--help`: Show this message and exit.

### `d2w messaging delete`

Delete a conversation (soft-delete for the calling user; other participants keep it).

**Usage**:

```console
$ d2w messaging delete [OPTIONS] UID
```

**Arguments**:

* `UID`: Conversation UID.  [required]

**Options**:

* `--help`: Show this message and exit.

### `d2w messaging set-priority`

Set a conversation&#x27;s ticket-workflow priority.

Values: NONE / LOW / MEDIUM / HIGH. Applies to any messageType — most
meaningful on TICKET conversations, stored on PRIVATE threads too.

**Usage**:

```console
$ d2w messaging set-priority [OPTIONS] UID PRIORITY
```

**Arguments**:

* `UID`: Conversation UID.  [required]
* `PRIORITY`: Priority — NONE / LOW / MEDIUM / HIGH.  [required]

**Options**:

* `--help`: Show this message and exit.

### `d2w messaging set-status`

Set a conversation&#x27;s ticket-workflow status.

Values: NONE / OPEN / PENDING / INVALID / SOLVED. Not wired into the
initial `send` — DHIS2&#x27;s API requires a separate POST on the
`/status` sub-resource.

**Usage**:

```console
$ d2w messaging set-status [OPTIONS] UID STATUS
```

**Arguments**:

* `UID`: Conversation UID.  [required]
* `STATUS`: Status — NONE / OPEN / PENDING / INVALID / SOLVED.  [required]

**Options**:

* `--help`: Show this message and exit.

### `d2w messaging assign`

Assign a conversation to a user (ticket workflows).

**Usage**:

```console
$ d2w messaging assign [OPTIONS] UID USER
```

**Arguments**:

* `UID`: Conversation UID.  [required]
* `USER`: User UID to assign the conversation to.  [required]

**Options**:

* `--help`: Show this message and exit.

### `d2w messaging unassign`

Remove the assignee from a conversation.

**Usage**:

```console
$ d2w messaging unassign [OPTIONS] UID
```

**Arguments**:

* `UID`: Conversation UID.  [required]

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
$ d2w metadata ls [OPTIONS] RESOURCE
```

**Arguments**:

* `RESOURCE`: Resource type, e.g. dataElements, indicators  [required]

**Options**:

* `--fields TEXT`: DHIS2 field selector: plain (&#x27;id,name&#x27;), presets (&#x27;:identifiable&#x27;, &#x27;:nameable&#x27;, &#x27;:owner&#x27;, &#x27;:all&#x27;), nested (&#x27;children&#x27;), or exclusions (&#x27;:all,!lastUpdated&#x27;).  [default: id,name]
* `--filter TEXT`: Filter as `property:operator:value`. Repeatable — AND&#x27;d by default, use --root-junction OR. Operators: eq (exact), ilike (contains), $ilike (starts-with), ilike$ (ends-with), token (word), gt/ge/lt/le (numbers/dates), in: (any-of), null / !null (presence); drop the `i` for case-sensitive. Nested paths use dots, e.g. dataSetElements.dataSet.id:eq:&lt;uid&gt; or categoryCombo.id:eq:&lt;uid&gt;. E.g. name:$ilike:anc lists names starting with &#x27;anc&#x27;.
* `--root-junction TEXT`: Combine repeated --filter as AND (default) or OR.  [default: AND]
* `--order TEXT`: Sort clause like &#x27;name:asc&#x27; or &#x27;created:desc&#x27;. Repeatable (later clauses tie-break).
* `--page INTEGER`: Server-side page number (1-based). With NO paging flag the FULL collection is returned; passing --page switches to paged mode (pageSize defaults to 50). Ignored when --all is set.
* `--page-size INTEGER`: Rows per page; applies only in paged mode (when --page/--page-size is given), default 50. Omit all paging flags to get everything. Ignored when --all is set.
* `--all`: Stream every page server-side (ignores --page/--page-size). Useful for dumping a full catalog.
* `--translate / --no-translate`: Return server-side translations for i18n fields.
* `--locale TEXT`: Locale for --translate, e.g. &#x27;fr&#x27;.
* `--count`: Print only the total number of matching items (DHIS2 pager total), not the rows. Respects --filter; ignores --fields / --page / --page-size / --all.
* `-o, --output PATH`: Write the result JSON to this file and print a one-line summary instead of the rows. Combine with --fields / --filter / --all to dump a full slice without flooding the caller.
* `--help`: Show this message and exit.

### `d2w metadata list`

List instances of a metadata resource.

**Usage**:

```console
$ d2w metadata list [OPTIONS] RESOURCE
```

**Arguments**:

* `RESOURCE`: Resource type, e.g. dataElements, indicators  [required]

**Options**:

* `--fields TEXT`: DHIS2 field selector: plain (&#x27;id,name&#x27;), presets (&#x27;:identifiable&#x27;, &#x27;:nameable&#x27;, &#x27;:owner&#x27;, &#x27;:all&#x27;), nested (&#x27;children&#x27;), or exclusions (&#x27;:all,!lastUpdated&#x27;).  [default: id,name]
* `--filter TEXT`: Filter as `property:operator:value`. Repeatable — AND&#x27;d by default, use --root-junction OR. Operators: eq (exact), ilike (contains), $ilike (starts-with), ilike$ (ends-with), token (word), gt/ge/lt/le (numbers/dates), in: (any-of), null / !null (presence); drop the `i` for case-sensitive. Nested paths use dots, e.g. dataSetElements.dataSet.id:eq:&lt;uid&gt; or categoryCombo.id:eq:&lt;uid&gt;. E.g. name:$ilike:anc lists names starting with &#x27;anc&#x27;.
* `--root-junction TEXT`: Combine repeated --filter as AND (default) or OR.  [default: AND]
* `--order TEXT`: Sort clause like &#x27;name:asc&#x27; or &#x27;created:desc&#x27;. Repeatable (later clauses tie-break).
* `--page INTEGER`: Server-side page number (1-based). With NO paging flag the FULL collection is returned; passing --page switches to paged mode (pageSize defaults to 50). Ignored when --all is set.
* `--page-size INTEGER`: Rows per page; applies only in paged mode (when --page/--page-size is given), default 50. Omit all paging flags to get everything. Ignored when --all is set.
* `--all`: Stream every page server-side (ignores --page/--page-size). Useful for dumping a full catalog.
* `--translate / --no-translate`: Return server-side translations for i18n fields.
* `--locale TEXT`: Locale for --translate, e.g. &#x27;fr&#x27;.
* `--count`: Print only the total number of matching items (DHIS2 pager total), not the rows. Respects --filter; ignores --fields / --page / --page-size / --all.
* `-o, --output PATH`: Write the result JSON to this file and print a one-line summary instead of the rows. Combine with --fields / --filter / --all to dump a full slice without flooding the caller.
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
$ d2w metadata search [OPTIONS] QUERY
```

**Arguments**:

* `QUERY`: UID, code, or name fragment to search for.  [required]

**Options**:

* `--page-size INTEGER`: Max hits per resource type (default 50).  [default: 50]
* `--resource TEXT`: Narrow to one DHIS2 resource (e.g. dataElements, dashboards).
* `--fields TEXT`: DHIS2 fields selector; extras land on SearchHit.extras (rendered as trailing columns).
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
$ d2w metadata usage [OPTIONS] UID
```

**Arguments**:

* `UID`: UID to reverse-lookup — find every object that references it.  [required]

**Options**:

* `--page-size INTEGER`: Max hits per reference path (default 100).  [default: 100]
* `--help`: Show this message and exit.

### `d2w metadata get`

Fetch one metadata object by UID.

Prints a concise Rich summary by default (id, name, code, common metadata +
notable extras). Use `--json` for the full payload when debugging or
piping into jq. Pass `--fields` to narrow what DHIS2 returns.

**Usage**:

```console
$ d2w metadata get [OPTIONS] RESOURCE UID
```

**Arguments**:

* `RESOURCE`: Resource type, e.g. dataElements  [required]
* `UID`: Object UID  [required]

**Options**:

* `--fields TEXT`: DHIS2 fields selector.
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

* `--resource TEXT`: Resource type to include (repeatable). Omit for every type DHIS2 exports by default.
* `--fields TEXT`: DHIS2 field selector. Defaults to &#x27;:owner&#x27; for a lossless round-trip import.  [default: :owner]
* `--filter TEXT`: Per-resource filter in the form `RESOURCE:property:operator:value`. Repeatable. Example: `--filter dataElements:name:like:ANC`. Same DSL as `d2w metadata list --filter`, prefixed with the resource name.
* `--resource-fields TEXT`: Per-resource field selector in the form `RESOURCE:SELECTOR`. Repeatable. Overrides the global `--fields` for the named resource. Example: `--resource-fields dataElements::identifiable`.
* `--skip-sharing`: Exclude sharing blocks from exported objects.
* `--skip-translation`: Exclude translation blocks.
* `--skip-validation`: Skip validation during export (matches DHIS2&#x27;s server-side option).
* `--check-references / --no-check-references`: After export, walk the bundle and warn on references to UIDs not in the bundle (e.g. a dataElement&#x27;s categoryCombo missing from a filtered export). On by default.  [default: check-references]
* `-o, --output PATH`: Write the bundle to this file (JSON). A full-catalog export is tens of MB (org-unit geometry) — prefer this; omitting prints the whole bundle to stdout.
* `--pretty / --no-pretty`: Indent JSON output (default: pretty).  [default: pretty]
* `--help`: Show this message and exit.

### `d2w metadata import`

Upload a metadata bundle via `POST /api/metadata` and print the import report.

**Usage**:

```console
$ d2w metadata import [OPTIONS] FILE
```

**Arguments**:

* `FILE`: Path to the metadata bundle JSON.  [required]

**Options**:

* `--strategy TEXT`: CREATE | UPDATE | CREATE_AND_UPDATE | DELETE (default CREATE_AND_UPDATE).  [default: CREATE_AND_UPDATE]
* `--atomic-mode TEXT`: ALL (rollback on any failure) or NONE (commit surviving objects).  [default: ALL]
* `--dry-run`: Validate + preheat without committing. Output is the import report DHIS2 would have produced.
* `--identifier TEXT`: UID | CODE | AUTO (default UID).  [default: UID]
* `--skip-sharing`
* `--skip-translation`
* `--skip-validation`
* `--merge-mode TEXT`: REPLACE (overwrite) or MERGE (patch) existing objects.
* `--preheat-mode TEXT`: REFERENCE (default), ALL, or NONE.
* `--flush-mode TEXT`: AUTO (default) or OBJECT.
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
$ d2w metadata patch [OPTIONS] RESOURCE UID
```

**Arguments**:

* `RESOURCE`: Resource type, e.g. dataElements, indicators.  [required]
* `UID`: UID of the object to patch.  [required]

**Options**:

* `--file PATH`: JSON file with a RFC 6902 patch array. Mutually exclusive with --set/--remove.
* `--set TEXT`: Inline `replace` op as `path=value`. Repeatable. Values are JSON-decoded when they parse as JSON (`{&quot;a&quot;:1}`, `true`, `42`) and treated as strings otherwise.
* `--remove TEXT`: Inline `remove` op as `path`. Repeatable.
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
$ d2w metadata rename [OPTIONS] RESOURCE
```

**Arguments**:

* `RESOURCE`: Resource type, e.g. dataElements, indicators.  [required]

**Options**:

* `--filter TEXT`: DHIS2 filter DSL (`&lt;prop&gt;:&lt;op&gt;:&lt;value&gt;`), repeatable. Example: `--filter code:like:DE_ANC` to narrow the cohort.
* `--root-junction TEXT`: Combine repeated --filter as AND (default) or OR.
* `--name-prefix TEXT`: Prefix each matched object&#x27;s `name` (idempotent).
* `--name-suffix TEXT`: Suffix each matched object&#x27;s `name` (idempotent).
* `--name-strip-prefix TEXT`: Remove this non-empty prefix from each matched object&#x27;s `name` (idempotent; no-op when absent).
* `--name-strip-suffix TEXT`: Remove this non-empty suffix from each matched object&#x27;s `name` (idempotent; no-op when absent).
* `--short-name-prefix TEXT`: Prefix each matched object&#x27;s `shortName` (idempotent).
* `--short-name-suffix TEXT`: Suffix each matched object&#x27;s `shortName` (idempotent).
* `--short-name-strip-prefix TEXT`: Remove this non-empty prefix from each matched object&#x27;s `shortName` (idempotent).
* `--short-name-strip-suffix TEXT`: Remove this non-empty suffix from each matched object&#x27;s `shortName` (idempotent).
* `--set-description TEXT`: Replace every matched object&#x27;s `description` with this string.
* `--concurrency INTEGER`: Max concurrent PATCH requests (default 8).  [default: 8]
* `--dry-run`: Preview the planned patches without sending them.
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
$ d2w metadata retag [OPTIONS] RESOURCE
```

**Arguments**:

* `RESOURCE`: Resource type, e.g. dataElements, indicators.  [required]

**Options**:

* `--filter TEXT`: DHIS2 filter DSL (`&lt;prop&gt;:&lt;op&gt;:&lt;value&gt;`), repeatable.
* `--root-junction TEXT`: Combine repeated --filter as AND (default) or OR.
* `--category-combo TEXT`: Replace `/categoryCombo` with the given CategoryCombo UID.
* `--option-set TEXT`: Replace `/optionSet` with the given OptionSet UID.
* `--clear-option-set`: Remove `/optionSet` (null out the ref).
* `--aggregation-type TEXT`: Replace `/aggregationType` (e.g. SUM, AVERAGE).
* `--domain-type TEXT`: Replace `/domainType` (AGGREGATE / TRACKER).
* `--legend-set TEXT`: Replace `/legendSets` with the given UIDs (repeatable).
* `--clear-legend-sets`: Empty `/legendSets`.
* `--concurrency INTEGER`: Max concurrent PATCH requests (default 8).  [default: 8]
* `--dry-run`: Preview without sending patches.
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
$ d2w metadata share [OPTIONS] RESOURCE_TYPE [UIDS]...
```

**Arguments**:

* `RESOURCE_TYPE`: DHIS2 resource type — singular or plural, e.g. `dataElement`/`dataElements`, `dataSet`/`dataSets`, `program`. Normalized to the singular `/api/sharing?type=` form.  [required]
* `[UIDS]...`: UIDs to share. Pass `-` to read one UID per line from stdin.

**Options**:

* `--public-access TEXT`: Replace the public-access string. 8-char DHIS2 pattern (`rwrw----`, `r-------`, `--------`). Omit to keep each object&#x27;s current public access unchanged.
* `--user-access TEXT`: Repeatable; grant a user access in `UID:access` form (e.g. `U_ALICE:rw------`).
* `--user-group-access TEXT`: Repeatable; grant a user-group access in `UID:access` form.
* `--concurrency INTEGER`: Max concurrent POSTs (default 8).  [default: 8]
* `--dry-run`: Preview the planned grants without sending them.
* `--help`: Show this message and exit.

### `d2w metadata diff`

Compare two metadata bundles (or one bundle against the live instance).

Per-resource counts of create/update/delete. Objects that differ only on
DHIS2&#x27;s per-instance noise (lastUpdated, createdBy, etc.) are treated as
unchanged by default — `--ignore` extends that list.

**Usage**:

```console
$ d2w metadata diff [OPTIONS] LEFT [RIGHT]
```

**Arguments**:

* `LEFT`: Left-hand bundle — the &#x27;source of truth&#x27; you&#x27;re comparing against.  [required]
* `[RIGHT]`: Right-hand bundle. Omit with `--live` to diff against the connected DHIS2 instance.

**Options**:

* `--live`: Use the connected DHIS2 instance as the right-hand side. Exports only the resource types present in the left bundle (no full-catalog fetch). Incompatible with a positional right arg.
* `--show-uids`: List up to 5 offending UIDs per per-resource row.
* `--ignore TEXT`: Fields to skip when deciding if an object changed. Repeatable. Defaults cover DHIS2&#x27;s per-instance noise (lastUpdated, createdBy, access, ...); pass `--ignore sharing` etc. to extend.
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
$ d2w metadata diff-profiles [OPTIONS] PROFILE_A PROFILE_B
```

**Arguments**:

* `PROFILE_A`: Name of the &#x27;left&#x27; profile (source of truth).  [required]
* `PROFILE_B`: Name of the &#x27;right&#x27; profile (candidate).  [required]

**Options**:

* `-r, --resource TEXT`: Resource type to compare (e.g. dataElements, indicators). Repeatable. Required — whole-instance diffs are almost always noise.
* `--filter TEXT`: Per-resource filter in `resource:property:operator:value` form. Repeatable. Example: `--filter dataElements:name:like:ANC` only compares data elements whose name contains &#x27;ANC&#x27;. Same DHIS2 filter DSL as `d2w metadata list --filter`.
* `--fields TEXT`: DHIS2 field selector applied on both profiles. Defaults to &#x27;:owner&#x27; — the selector DHIS2 itself uses for cross-instance imports (preserves every field needed for a faithful round-trip).  [default: :owner]
* `--ignore TEXT`: Additional fields to skip when deciding if an object changed. Repeatable. Defaults already cover DHIS2&#x27;s per-instance noise (lastUpdated, createdBy, access, ...). Common extensions for drift checks: `--ignore sharing --ignore translations`.
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
$ d2w metadata merge [OPTIONS] SOURCE_PROFILE TARGET_PROFILE
```

**Arguments**:

* `SOURCE_PROFILE`: Source profile — the `--from` side of the merge.  [required]
* `TARGET_PROFILE`: Target profile — where the source&#x27;s resources land.  [required]

**Options**:

* `-r, --resource TEXT`: Resource type to merge (e.g. dataElements, indicators). Repeatable. Required — whole-instance merges are almost never what you want.
* `--filter TEXT`: Per-resource filter in `resource:property:operator:value` form. Repeatable. Same DSL as `d2w metadata list --filter` and `d2w metadata diff-profiles`.
* `--fields TEXT`: DHIS2 field selector applied on the source export. Defaults to &#x27;:owner&#x27; (faithful round-trip).  [default: :owner]
* `--strategy TEXT`: Import strategy — CREATE / UPDATE / CREATE_AND_UPDATE / DELETE (default: CREATE_AND_UPDATE).  [default: CREATE_AND_UPDATE]
* `--atomic TEXT`: atomicMode — ALL / NONE (default: ALL; one broken object aborts the whole import).  [default: ALL]
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
$ d2w metadata merge-bundle [OPTIONS] TARGET_PROFILE BUNDLE
```

**Arguments**:

* `TARGET_PROFILE`: Target profile — where the bundle&#x27;s resources land.  [required]
* `BUNDLE`: Path to a JSON metadata bundle (the shape `GET /api/metadata` returns).  [required]

**Options**:

* `-r, --resource TEXT`: Resource type to import from the bundle (e.g. dataElements). Repeatable. The bundle is filtered to these collections before the POST, so the count summary reports exactly what was written. Optional — when omitted, the whole bundle is imported.
* `--strategy TEXT`: Import strategy — CREATE / UPDATE / CREATE_AND_UPDATE / DELETE (default: CREATE_AND_UPDATE).  [default: CREATE_AND_UPDATE]
* `--atomic TEXT`: atomicMode — ALL / NONE (default: ALL; one broken object aborts the whole import).  [default: ALL]
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
$ d2w metadata option-sets get [OPTIONS] UID_OR_CODE
```

**Arguments**:

* `UID_OR_CODE`: OptionSet UID (11 chars) or business code.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w metadata option-sets find`

Locate a single option inside a set by code or name; exit 1 if no match.

**Usage**:

```console
$ d2w metadata option-sets find [OPTIONS]
```

**Options**:

* `--set TEXT`: OptionSet UID or business code.  [required]
* `--code TEXT`: Business code of the option to locate.
* `--name TEXT`: Display name of the option (exact match).
* `--help`: Show this message and exit.

#### `d2w metadata option-sets create`

Create an OptionSet (then add its options with `options sync`).

**Usage**:

```console
$ d2w metadata option-sets create [OPTIONS]
```

**Options**:

* `--name TEXT`: OptionSet name.  [required]
* `--value-type TEXT`: DHIS2 ValueType, e.g. TEXT / NUMBER / INTEGER.  [required]
* `--code TEXT`: Business code.
* `--uid TEXT`: Explicit 11-char UID.
* `--help`: Show this message and exit.

#### `d2w metadata option-sets delete`

Delete an OptionSet by UID.

**Usage**:

```console
$ d2w metadata option-sets delete [OPTIONS] UID
```

**Arguments**:

* `UID`: OptionSet UID.  [required]

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
$ d2w metadata option-sets sync [OPTIONS] SET_REF SPEC_FILE
```

**Arguments**:

* `SET_REF`: OptionSet UID or business code.  [required]
* `SPEC_FILE`: JSON file — list of `{code, name, sort_order?}` objects.  [required]

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
$ d2w metadata option-sets attributes get [OPTIONS] OPTION_UID ATTRIBUTE
```

**Arguments**:

* `OPTION_UID`: Option UID (11 chars).  [required]
* `ATTRIBUTE`: Attribute UID or business code (e.g. &#x27;SNOMED_CODE&#x27;).  [required]

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
$ d2w metadata option-sets attributes set [OPTIONS] OPTION_UID ATTRIBUTE VALUE
```

**Arguments**:

* `OPTION_UID`: Option UID (11 chars).  [required]
* `ATTRIBUTE`: Attribute UID or business code (e.g. &#x27;SNOMED_CODE&#x27;).  [required]
* `VALUE`: New attribute value.  [required]

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

* `--set TEXT`: OptionSet UID or business code.  [required]
* `--attribute TEXT`: Attribute UID or business code (e.g. &#x27;SNOMED_CODE&#x27;).  [required]
* `--value TEXT`: Attribute value to match exactly.  [required]
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
$ d2w metadata attributes get [OPTIONS] RESOURCE RESOURCE_UID ATTRIBUTE
```

**Arguments**:

* `RESOURCE`: Plural DHIS2 resource name (e.g. `dataElements`, `options`, `organisationUnits`).  [required]
* `RESOURCE_UID`: UID of the resource instance.  [required]
* `ATTRIBUTE`: Attribute UID or business code (e.g. `ICD10_CODE`).  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w metadata attributes set`

Set / replace one attribute value on any resource (read-merge-write).

**Usage**:

```console
$ d2w metadata attributes set [OPTIONS] RESOURCE RESOURCE_UID ATTRIBUTE VALUE
```

**Arguments**:

* `RESOURCE`: Plural DHIS2 resource name.  [required]
* `RESOURCE_UID`: UID of the resource instance.  [required]
* `ATTRIBUTE`: Attribute UID or business code.  [required]
* `VALUE`: New attribute value.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w metadata attributes delete`

Remove one attribute value from any resource; exit 0 regardless of whether it existed.

**Usage**:

```console
$ d2w metadata attributes delete [OPTIONS] RESOURCE RESOURCE_UID ATTRIBUTE
```

**Arguments**:

* `RESOURCE`: Plural DHIS2 resource name.  [required]
* `RESOURCE_UID`: UID of the resource instance.  [required]
* `ATTRIBUTE`: Attribute UID or business code.  [required]

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
$ d2w metadata attributes find [OPTIONS] RESOURCE ATTRIBUTE VALUE
```

**Arguments**:

* `RESOURCE`: Plural DHIS2 resource name.  [required]
* `ATTRIBUTE`: Attribute UID or business code.  [required]
* `VALUE`: Attribute value to match exactly.  [required]

**Options**:

* `--filter TEXT`: Extra DHIS2 filter constraints to narrow the search (e.g. `domainType:eq:AGGREGATE`). Repeatable.
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
$ d2w metadata program-rules get [OPTIONS] RULE_UID
```

**Arguments**:

* `RULE_UID`: ProgramRule UID.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w metadata program-rules vars-for`

List every `ProgramRuleVariable` in scope for a program, sorted by name.

**Usage**:

```console
$ d2w metadata program-rules vars-for [OPTIONS] PROGRAM_UID
```

**Arguments**:

* `PROGRAM_UID`: Program UID.  [required]

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
$ d2w metadata program-rules validate-expression [OPTIONS] EXPRESSION
```

**Arguments**:

* `EXPRESSION`: Program-rule condition expression.  [required]

**Options**:

* `--context TEXT`: Which DHIS2 expression parser to use: program-indicator (default), validation-rule, indicator, predictor, or generic.  [default: program-indicator]
* `--help`: Show this message and exit.

#### `d2w metadata program-rules where-de-is-used`

Impact analysis — list every rule whose actions reference this DataElement.

Useful before renaming / removing a DE: catches rules that&#x27;d stop
firing once the reference breaks. Exit 1 if nothing matches (safe
shorthand for `grep -q` pipelines).

**Usage**:

```console
$ d2w metadata program-rules where-de-is-used [OPTIONS] DATA_ELEMENT_UID
```

**Arguments**:

* `DATA_ELEMENT_UID`: DataElement UID.  [required]

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
$ d2w metadata sql-views get [OPTIONS] VIEW_UID
```

**Arguments**:

* `VIEW_UID`: SqlView UID.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w metadata sql-views execute`

Run a SqlView and render its rows as a table, JSON array, or CSV.

**Usage**:

```console
$ d2w metadata sql-views execute [OPTIONS] VIEW_UID
```

**Arguments**:

* `VIEW_UID`: SqlView UID.  [required]

**Options**:

* `--var TEXT`: `${name}` substitution for QUERY views, in `name:value` form. Repeatable. DHIS2 strips non-alphanumeric characters from values server-side — wildcards belong in the SQL.
* `--criteria TEXT`: Column filter for VIEW / MATERIALIZED_VIEW results, in `column:value` form. Repeatable.
* `--format TEXT`: Output format: table (default), json, or csv.  [default: table]
* `--help`: Show this message and exit.

#### `d2w metadata sql-views refresh`

Refresh a MATERIALIZED_VIEW or lazily create a VIEW&#x27;s DB object.

`POST /api/sqlViews/{uid}/execute` is idempotent for VIEW types — the
first call creates the Postgres view; subsequent calls are no-ops.
MATERIALIZED_VIEW types re-run the underlying SQL each call.

**Usage**:

```console
$ d2w metadata sql-views refresh [OPTIONS] VIEW_UID
```

**Arguments**:

* `VIEW_UID`: SqlView UID.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w metadata sql-views adhoc`

Register a throwaway SqlView from a .sql file, execute once, delete it on the way out.

Designed for iterating on SQL without leaving test metadata behind.
Subject to DHIS2&#x27;s SQL allowlist — for fully free-form queries, see
the Postgres injector example.

**Usage**:

```console
$ d2w metadata sql-views adhoc [OPTIONS] NAME SQL_PATH
```

**Arguments**:

* `NAME`: Display name for the throwaway view.  [required]
* `SQL_PATH`: .sql file containing the query body.  [required]

**Options**:

* `--type TEXT`: SqlViewType — QUERY (default), VIEW, or MATERIALIZED_VIEW.  [default: QUERY]
* `--keep`: Leave the view in place afterwards instead of deleting.
* `--var TEXT`: `${name}` substitution in `name:value` form. Repeatable.
* `--format TEXT`: Output format: table (default), json, or csv.  [default: table]
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
$ d2w metadata visualizations get [OPTIONS] VIZ_UID
```

**Arguments**:

* `VIZ_UID`: Visualization UID.  [required]

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

* `--name TEXT`: Display name for the new Visualization.  [required]
* `--type TEXT`: VisualizationType: LINE, COLUMN, STACKED_COLUMN, BAR, PIVOT_TABLE, SINGLE_VALUE, etc.  [required]
* `--data-element, --de TEXT`: DataElement UID (repeat for multi-DE charts).  [required]
* `--period, --pe TEXT`: Period ID (e.g. 202401, 2024Q1, 2024). Repeat for multi-period.  [required]
* `--org-unit, --ou TEXT`: OrganisationUnit UID. Repeat for multi-OU.  [required]
* `--description TEXT`: Optional long description.
* `--uid TEXT`: Explicit UID (11 chars). Auto-generates when omitted.
* `--category-dim TEXT`: Override category axis: dx / pe / ou.
* `--series-dim TEXT`: Override series dimension: dx / pe / ou.
* `--filter-dim TEXT`: Override filter dimension: dx / pe / ou.
* `--help`: Show this message and exit.

#### `d2w metadata visualizations clone`

Clone an existing Visualization with a fresh UID + new name.

**Usage**:

```console
$ d2w metadata visualizations clone [OPTIONS] SOURCE_UID
```

**Arguments**:

* `SOURCE_UID`: Source Visualization UID.  [required]

**Options**:

* `--new-name TEXT`: Display name for the cloned Visualization.  [required]
* `--new-uid TEXT`: Explicit UID for the clone (11 chars). Auto-generates when omitted.
* `--new-description TEXT`: Override the source&#x27;s description on the clone.
* `--help`: Show this message and exit.

#### `d2w metadata visualizations delete`

Delete a Visualization.

**Usage**:

```console
$ d2w metadata visualizations delete [OPTIONS] VIZ_UID
```

**Arguments**:

* `VIZ_UID`: Visualization UID to delete.  [required]

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
$ d2w metadata dashboards get [OPTIONS] DASHBOARD_UID
```

**Arguments**:

* `DASHBOARD_UID`: Dashboard UID.  [required]

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
$ d2w metadata dashboards add-item [OPTIONS] DASHBOARD_UID
```

**Arguments**:

* `DASHBOARD_UID`: Dashboard UID.  [required]

**Options**:

* `--viz TEXT`: Visualization UID (mutually exclusive with --map).
* `--map TEXT`: Map UID to add as a MAP-type dashboard item.
* `--x INTEGER`: Grid x coordinate (0-60). Auto-stacks when omitted.
* `--y INTEGER`: Grid y coordinate. Auto-stacks below existing when omitted.
* `--width INTEGER`: Slot width (1-60). Defaults to 60 when auto.
* `--height INTEGER`: Slot height. Defaults to 20 when auto.
* `--help`: Show this message and exit.

#### `d2w metadata dashboards remove-item`

Remove one dashboardItem by its UID.

**Usage**:

```console
$ d2w metadata dashboards remove-item [OPTIONS] DASHBOARD_UID ITEM_UID
```

**Arguments**:

* `DASHBOARD_UID`: Dashboard UID.  [required]
* `ITEM_UID`: DashboardItem UID to remove.  [required]

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
$ d2w metadata maps get [OPTIONS] MAP_UID
```

**Arguments**:

* `MAP_UID`: Map UID.  [required]

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

* `--name TEXT`: Display name for the new Map.  [required]
* `--data-element, --de TEXT`: DataElement UID for the thematic layer.  [required]
* `--period, --pe TEXT`: Period ID. Repeat for multi-period.  [required]
* `--org-unit, --ou TEXT`: OrganisationUnit UID (usually the parent boundary). Repeat for multi.  [required]
* `--ou-level INTEGER`: OU hierarchy level(s) to render (e.g. 2 for provinces). Repeat for multi.  [required]
* `--description TEXT`
* `--uid TEXT`: Explicit UID (11 chars). Auto-generates when omitted.
* `--longitude FLOAT`: [default: 15.0]
* `--latitude FLOAT`: [default: 0.0]
* `--zoom INTEGER`: [default: 4]
* `--basemap TEXT`: [default: openStreetMap]
* `--classes INTEGER`: Number of color classes on the choropleth.  [default: 5]
* `--color-low TEXT`: Choropleth low-value colour (#hex).  [default: #fef0d9]
* `--color-high TEXT`: Choropleth high-value colour (#hex).  [default: #b30000]
* `--help`: Show this message and exit.

#### `d2w metadata maps clone`

Clone an existing Map with a fresh UID + new name.

**Usage**:

```console
$ d2w metadata maps clone [OPTIONS] SOURCE_UID
```

**Arguments**:

* `SOURCE_UID`: Source Map UID.  [required]

**Options**:

* `--new-name TEXT`: Display name for the cloned Map.  [required]
* `--new-uid TEXT`: Explicit UID for the clone.
* `--new-description TEXT`
* `--help`: Show this message and exit.

#### `d2w metadata maps delete`

Delete a Map.

**Usage**:

```console
$ d2w metadata maps delete [OPTIONS] MAP_UID
```

**Arguments**:

* `MAP_UID`: Map UID to delete.  [required]

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
$ d2w metadata data-elements get [OPTIONS] UID
```

**Arguments**:

* `UID`: DataElement UID.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w metadata data-elements create`

Create a DataElement (defaults aggregate + SUM + instance default categoryCombo).

**Usage**:

```console
$ d2w metadata data-elements create [OPTIONS]
```

**Options**:

* `--name TEXT`: Full name (&lt;=230 chars).  [required]
* `--short-name TEXT`: Short name (&lt;=50 chars).  [required]
* `--value-type TEXT`: DHIS2 ValueType, e.g. NUMBER / TEXT / INTEGER_POSITIVE.  [required]
* `--domain-type TEXT`: AGGREGATE or TRACKER.  [default: AGGREGATE]
* `--aggregation-type TEXT`: Default SUM.  [default: SUM]
* `--category-combo TEXT`: CategoryCombo UID (defaults to the instance default).
* `--option-set TEXT`: OptionSet UID.
* `--legend-set TEXT`: LegendSet UID. Repeat for multiple.
* `--code TEXT`: Business code.
* `--form-name TEXT`: Form name override.
* `--description TEXT`: Free text.
* `--uid TEXT`: Explicit 11-char UID.
* `--zero-significant / --no-zero-significant`: Treat 0 as data, not absence.  [default: no-zero-significant]
* `--help`: Show this message and exit.

#### `d2w metadata data-elements rename`

Partial-update the label fields on a DataElement (read, mutate, PUT).

**Usage**:

```console
$ d2w metadata data-elements rename [OPTIONS] UID
```

**Arguments**:

* `UID`: DataElement UID.  [required]

**Options**:

* `--name TEXT`: New name.
* `--short-name TEXT`: New short name.
* `--form-name TEXT`: New form name.
* `--description TEXT`: New description.
* `--help`: Show this message and exit.

#### `d2w metadata data-elements set-legend-sets`

Replace the legend-set refs on one DataElement.

**Usage**:

```console
$ d2w metadata data-elements set-legend-sets [OPTIONS] UID
```

**Arguments**:

* `UID`: DataElement UID.  [required]

**Options**:

* `--legend-set TEXT`: LegendSet UID to attach. Repeat for multiple. Empty list clears.  [required]
* `--help`: Show this message and exit.

#### `d2w metadata data-elements delete`

Delete a DataElement — DHIS2 rejects deletes on DEs with saved values.

**Usage**:

```console
$ d2w metadata data-elements delete [OPTIONS] UID
```

**Arguments**:

* `UID`: DataElement UID.  [required]

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
$ d2w metadata data-element-groups get [OPTIONS] UID
```

**Arguments**:

* `UID`: DataElementGroup UID.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w metadata data-element-groups members`

Page through DataElements inside one group.

**Usage**:

```console
$ d2w metadata data-element-groups members [OPTIONS] UID
```

**Arguments**:

* `UID`: DataElementGroup UID.  [required]

**Options**:

* `--page INTEGER`: 1-based page number.  [default: 1]
* `--page-size INTEGER`: Rows per page.  [default: 50]
* `--help`: Show this message and exit.

#### `d2w metadata data-element-groups create`

Create an empty DataElementGroup.

**Usage**:

```console
$ d2w metadata data-element-groups create [OPTIONS]
```

**Options**:

* `--name TEXT`: Full name.  [required]
* `--short-name TEXT`: Short name.  [required]
* `--uid TEXT`: Explicit 11-char UID.
* `--code TEXT`: Business code.
* `--description TEXT`: Free text.
* `--help`: Show this message and exit.

#### `d2w metadata data-element-groups add-members`

Add `--data-element` members via the per-item POST shortcut.

**Usage**:

```console
$ d2w metadata data-element-groups add-members [OPTIONS] UID
```

**Arguments**:

* `UID`: DataElementGroup UID.  [required]

**Options**:

* `-e, --data-element TEXT`: DataElement UID to add. Repeat for multiple.  [required]
* `--help`: Show this message and exit.

#### `d2w metadata data-element-groups remove-members`

Drop `--data-element` members via the per-item DELETE shortcut.

**Usage**:

```console
$ d2w metadata data-element-groups remove-members [OPTIONS] UID
```

**Arguments**:

* `UID`: DataElementGroup UID.  [required]

**Options**:

* `-e, --data-element TEXT`: DataElement UID to drop. Repeat for multiple.  [required]
* `--help`: Show this message and exit.

#### `d2w metadata data-element-groups delete`

Delete the grouping row — member DEs stay.

**Usage**:

```console
$ d2w metadata data-element-groups delete [OPTIONS] UID
```

**Arguments**:

* `UID`: DataElementGroup UID.  [required]

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
$ d2w metadata data-element-group-sets get [OPTIONS] UID
```

**Arguments**:

* `UID`: DataElementGroupSet UID.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w metadata data-element-group-sets create`

Create an empty DataElementGroupSet.

**Usage**:

```console
$ d2w metadata data-element-group-sets create [OPTIONS]
```

**Options**:

* `--name TEXT`: Full name.  [required]
* `--short-name TEXT`: Short name.  [required]
* `--uid TEXT`: Explicit 11-char UID.
* `--code TEXT`: Business code.
* `--description TEXT`: Free text.
* `--compulsory / --not-compulsory`: Require DEs to land in exactly one member group.  [default: not-compulsory]
* `--data-dimension / --no-data-dimension`: Expose as analytics axis.  [default: data-dimension]
* `--help`: Show this message and exit.

#### `d2w metadata data-element-group-sets add-groups`

Add `--group` members to a group set.

**Usage**:

```console
$ d2w metadata data-element-group-sets add-groups [OPTIONS] UID
```

**Arguments**:

* `UID`: DataElementGroupSet UID.  [required]

**Options**:

* `--group TEXT`: DataElementGroup UID to add. Repeat for multiple.  [required]
* `--help`: Show this message and exit.

#### `d2w metadata data-element-group-sets remove-groups`

Drop `--group` members from a group set.

**Usage**:

```console
$ d2w metadata data-element-group-sets remove-groups [OPTIONS] UID
```

**Arguments**:

* `UID`: DataElementGroupSet UID.  [required]

**Options**:

* `--group TEXT`: DataElementGroup UID to drop. Repeat for multiple.  [required]
* `--help`: Show this message and exit.

#### `d2w metadata data-element-group-sets delete`

Delete a DataElementGroupSet — member groups stay.

**Usage**:

```console
$ d2w metadata data-element-group-sets delete [OPTIONS] UID
```

**Arguments**:

* `UID`: DataElementGroupSet UID.  [required]

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
$ d2w metadata indicators get [OPTIONS] UID
```

**Arguments**:

* `UID`: Indicator UID.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w metadata indicators create`

Create an Indicator from a numerator / denominator expression pair.

**Usage**:

```console
$ d2w metadata indicators create [OPTIONS]
```

**Options**:

* `--name TEXT`: Full name (&lt;=230 chars).  [required]
* `--short-name TEXT`: Short name (&lt;=50 chars).  [required]
* `--indicator-type TEXT`: IndicatorType UID (pins the output scale).  [required]
* `--numerator TEXT`: DHIS2 numerator expression, e.g. &#x27;#{deUid}&#x27;.  [required]
* `--denominator TEXT`: DHIS2 denominator expression.  [required]
* `--numerator-desc TEXT`: Human label for the numerator.
* `--denominator-desc TEXT`: Human label for the denominator.
* `--legend-set TEXT`: LegendSet UID. Repeat for multiple.
* `--annualized / --not-annualized`: Multiply by 365 / period days on aggregation.  [default: not-annualized]
* `--decimals INTEGER`: Rendered decimal places.
* `--code TEXT`: Business code.
* `--description TEXT`: Free text.
* `--uid TEXT`: Explicit 11-char UID.
* `--help`: Show this message and exit.

#### `d2w metadata indicators rename`

Partial-update label fields on an Indicator.

**Usage**:

```console
$ d2w metadata indicators rename [OPTIONS] UID
```

**Arguments**:

* `UID`: Indicator UID.  [required]

**Options**:

* `--name TEXT`: New name.
* `--short-name TEXT`: New short name.
* `--description TEXT`: New description.
* `--help`: Show this message and exit.

#### `d2w metadata indicators validate-expression`

Parse-check one indicator expression — fast pre-flight before create.

**Usage**:

```console
$ d2w metadata indicators validate-expression [OPTIONS] EXPRESSION
```

**Arguments**:

* `EXPRESSION`: Numerator / denominator expression to validate.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w metadata indicators set-legend-sets`

Replace the legend-set refs on one Indicator.

**Usage**:

```console
$ d2w metadata indicators set-legend-sets [OPTIONS] UID
```

**Arguments**:

* `UID`: Indicator UID.  [required]

**Options**:

* `--legend-set TEXT`: LegendSet UID to attach. Empty list clears.  [required]
* `--help`: Show this message and exit.

#### `d2w metadata indicators delete`

Delete an Indicator — DHIS2 rejects deletes on indicators used in viz/dashboards.

**Usage**:

```console
$ d2w metadata indicators delete [OPTIONS] UID
```

**Arguments**:

* `UID`: Indicator UID.  [required]

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
$ d2w metadata indicator-groups get [OPTIONS] UID
```

**Arguments**:

* `UID`: IndicatorGroup UID.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w metadata indicator-groups members`

Page through Indicators inside one group.

**Usage**:

```console
$ d2w metadata indicator-groups members [OPTIONS] UID
```

**Arguments**:

* `UID`: IndicatorGroup UID.  [required]

**Options**:

* `--page INTEGER`: 1-based page number.  [default: 1]
* `--page-size INTEGER`: Rows per page.  [default: 50]
* `--help`: Show this message and exit.

#### `d2w metadata indicator-groups create`

Create an empty IndicatorGroup.

**Usage**:

```console
$ d2w metadata indicator-groups create [OPTIONS]
```

**Options**:

* `--name TEXT`: Full name.  [required]
* `--short-name TEXT`: Short name.  [required]
* `--uid TEXT`: Explicit 11-char UID.
* `--code TEXT`: Business code.
* `--description TEXT`: Free text.
* `--help`: Show this message and exit.

#### `d2w metadata indicator-groups add-members`

Add `--indicator` members via the per-item POST shortcut.

**Usage**:

```console
$ d2w metadata indicator-groups add-members [OPTIONS] UID
```

**Arguments**:

* `UID`: IndicatorGroup UID.  [required]

**Options**:

* `-i, --indicator TEXT`: Indicator UID to add. Repeat for multiple.  [required]
* `--help`: Show this message and exit.

#### `d2w metadata indicator-groups remove-members`

Drop `--indicator` members via the per-item DELETE shortcut.

**Usage**:

```console
$ d2w metadata indicator-groups remove-members [OPTIONS] UID
```

**Arguments**:

* `UID`: IndicatorGroup UID.  [required]

**Options**:

* `-i, --indicator TEXT`: Indicator UID to drop. Repeat for multiple.  [required]
* `--help`: Show this message and exit.

#### `d2w metadata indicator-groups delete`

Delete the grouping row — member indicators stay.

**Usage**:

```console
$ d2w metadata indicator-groups delete [OPTIONS] UID
```

**Arguments**:

* `UID`: IndicatorGroup UID.  [required]

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
$ d2w metadata indicator-group-sets get [OPTIONS] UID
```

**Arguments**:

* `UID`: IndicatorGroupSet UID.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w metadata indicator-group-sets create`

Create an empty IndicatorGroupSet.

**Usage**:

```console
$ d2w metadata indicator-group-sets create [OPTIONS]
```

**Options**:

* `--name TEXT`: Full name.  [required]
* `--short-name TEXT`: Short name.  [required]
* `--uid TEXT`: Explicit 11-char UID.
* `--code TEXT`: Business code.
* `--description TEXT`: Free text.
* `--compulsory / --not-compulsory`: Require indicators to land in exactly one member group.  [default: not-compulsory]
* `--help`: Show this message and exit.

#### `d2w metadata indicator-group-sets add-groups`

Add `--group` members to a group set.

**Usage**:

```console
$ d2w metadata indicator-group-sets add-groups [OPTIONS] UID
```

**Arguments**:

* `UID`: IndicatorGroupSet UID.  [required]

**Options**:

* `--group TEXT`: IndicatorGroup UID to add. Repeat for multiple.  [required]
* `--help`: Show this message and exit.

#### `d2w metadata indicator-group-sets remove-groups`

Drop `--group` members from a group set.

**Usage**:

```console
$ d2w metadata indicator-group-sets remove-groups [OPTIONS] UID
```

**Arguments**:

* `UID`: IndicatorGroupSet UID.  [required]

**Options**:

* `--group TEXT`: IndicatorGroup UID to drop. Repeat for multiple.  [required]
* `--help`: Show this message and exit.

#### `d2w metadata indicator-group-sets delete`

Delete an IndicatorGroupSet — member groups stay.

**Usage**:

```console
$ d2w metadata indicator-group-sets delete [OPTIONS] UID
```

**Arguments**:

* `UID`: IndicatorGroupSet UID.  [required]

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
$ d2w metadata program-indicators get [OPTIONS] UID
```

**Arguments**:

* `UID`: ProgramIndicator UID.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w metadata program-indicators create`

Create a ProgramIndicator for a given program.

**Usage**:

```console
$ d2w metadata program-indicators create [OPTIONS]
```

**Options**:

* `--name TEXT`: Full name (&lt;=230 chars).  [required]
* `--short-name TEXT`: Short name (&lt;=50 chars).  [required]
* `--program TEXT`: Program UID — required.  [required]
* `--expression TEXT`: DHIS2 expression (e.g. &#x27;#{deUid}&#x27;).  [required]
* `--analytics-type TEXT`: EVENT (default) or ENROLLMENT.  [default: EVENT]
* `--filter TEXT`: Boolean filter expression narrowing the rows.
* `--description TEXT`: Free text.
* `--aggregation-type TEXT`: Override the default SUM.
* `--decimals INTEGER`: Rendered decimal places.
* `--legend-set TEXT`: LegendSet UID. Repeat for multiple.
* `--code TEXT`: Business code.
* `--uid TEXT`: Explicit 11-char UID.
* `--help`: Show this message and exit.

#### `d2w metadata program-indicators rename`

Partial-update label fields on a ProgramIndicator.

**Usage**:

```console
$ d2w metadata program-indicators rename [OPTIONS] UID
```

**Arguments**:

* `UID`: ProgramIndicator UID.  [required]

**Options**:

* `--name TEXT`: New name.
* `--short-name TEXT`: New short name.
* `--description TEXT`: New description.
* `--help`: Show this message and exit.

#### `d2w metadata program-indicators validate-expression`

Parse-check one program-indicator expression — fast pre-flight before create.

**Usage**:

```console
$ d2w metadata program-indicators validate-expression [OPTIONS] EXPRESSION
```

**Arguments**:

* `EXPRESSION`: Program-indicator expression to validate.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w metadata program-indicators set-legend-sets`

Replace the legend-set refs on one ProgramIndicator.

**Usage**:

```console
$ d2w metadata program-indicators set-legend-sets [OPTIONS] UID
```

**Arguments**:

* `UID`: ProgramIndicator UID.  [required]

**Options**:

* `--legend-set TEXT`: LegendSet UID to attach. Empty list clears.  [required]
* `--help`: Show this message and exit.

#### `d2w metadata program-indicators delete`

Delete a ProgramIndicator — DHIS2 rejects deletes on PIs used in viz / dashboards.

**Usage**:

```console
$ d2w metadata program-indicators delete [OPTIONS] UID
```

**Arguments**:

* `UID`: ProgramIndicator UID.  [required]

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
$ d2w metadata program-indicator-groups get [OPTIONS] UID
```

**Arguments**:

* `UID`: ProgramIndicatorGroup UID.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w metadata program-indicator-groups members`

Page through ProgramIndicators inside one group.

**Usage**:

```console
$ d2w metadata program-indicator-groups members [OPTIONS] UID
```

**Arguments**:

* `UID`: ProgramIndicatorGroup UID.  [required]

**Options**:

* `--page INTEGER`: 1-based page number.  [default: 1]
* `--page-size INTEGER`: Rows per page.  [default: 50]
* `--help`: Show this message and exit.

#### `d2w metadata program-indicator-groups create`

Create an empty ProgramIndicatorGroup.

**Usage**:

```console
$ d2w metadata program-indicator-groups create [OPTIONS]
```

**Options**:

* `--name TEXT`: Full name.  [required]
* `--short-name TEXT`: Short name.  [required]
* `--uid TEXT`: Explicit 11-char UID.
* `--code TEXT`: Business code.
* `--description TEXT`: Free text.
* `--help`: Show this message and exit.

#### `d2w metadata program-indicator-groups add-members`

Add `--program-indicator` members via the per-item POST shortcut.

**Usage**:

```console
$ d2w metadata program-indicator-groups add-members [OPTIONS] UID
```

**Arguments**:

* `UID`: ProgramIndicatorGroup UID.  [required]

**Options**:

* `-i, --program-indicator TEXT`: ProgramIndicator UID to add. Repeat for multiple.  [required]
* `--help`: Show this message and exit.

#### `d2w metadata program-indicator-groups remove-members`

Drop `--program-indicator` members via the per-item DELETE shortcut.

**Usage**:

```console
$ d2w metadata program-indicator-groups remove-members [OPTIONS] UID
```

**Arguments**:

* `UID`: ProgramIndicatorGroup UID.  [required]

**Options**:

* `-i, --program-indicator TEXT`: ProgramIndicator UID to drop. Repeat for multiple.  [required]
* `--help`: Show this message and exit.

#### `d2w metadata program-indicator-groups delete`

Delete the grouping row — member program indicators stay.

**Usage**:

```console
$ d2w metadata program-indicator-groups delete [OPTIONS] UID
```

**Arguments**:

* `UID`: ProgramIndicatorGroup UID.  [required]

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
$ d2w metadata category-options get [OPTIONS] UID
```

**Arguments**:

* `UID`: CategoryOption UID.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w metadata category-options create`

Create a CategoryOption. Omit `--start-date`/`--end-date` for an always-valid option.

**Usage**:

```console
$ d2w metadata category-options create [OPTIONS]
```

**Options**:

* `--name TEXT`: Full name (&lt;=230 chars).  [required]
* `--short-name TEXT`: Short name (&lt;=50 chars).  [required]
* `--code TEXT`: Business code.
* `--description TEXT`: Free text.
* `--form-name TEXT`: Form name override.
* `--start-date TEXT`: ISO-8601 date — beginning of validity window.
* `--end-date TEXT`: ISO-8601 date — end of validity window.
* `--uid TEXT`: Explicit 11-char UID.
* `--help`: Show this message and exit.

#### `d2w metadata category-options rename`

Partial-update the label fields on a CategoryOption.

**Usage**:

```console
$ d2w metadata category-options rename [OPTIONS] UID
```

**Arguments**:

* `UID`: CategoryOption UID.  [required]

**Options**:

* `--name TEXT`: New name.
* `--short-name TEXT`: New short name.
* `--form-name TEXT`: New form name.
* `--description TEXT`: New description.
* `--help`: Show this message and exit.

#### `d2w metadata category-options set-validity`

Set the `startDate` / `endDate` validity window on a CategoryOption.

**Usage**:

```console
$ d2w metadata category-options set-validity [OPTIONS] UID
```

**Arguments**:

* `UID`: CategoryOption UID.  [required]

**Options**:

* `--start-date TEXT`: ISO-8601 date (empty to clear).
* `--end-date TEXT`: ISO-8601 date (empty to clear).
* `--help`: Show this message and exit.

#### `d2w metadata category-options delete`

Delete a CategoryOption — DHIS2 rejects deletes on options in use.

**Usage**:

```console
$ d2w metadata category-options delete [OPTIONS] UID
```

**Arguments**:

* `UID`: CategoryOption UID.  [required]

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
$ d2w metadata category-option-groups get [OPTIONS] UID
```

**Arguments**:

* `UID`: CategoryOptionGroup UID.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w metadata category-option-groups members`

Page through CategoryOptions inside one group.

**Usage**:

```console
$ d2w metadata category-option-groups members [OPTIONS] UID
```

**Arguments**:

* `UID`: CategoryOptionGroup UID.  [required]

**Options**:

* `--page INTEGER`: 1-based page number.  [default: 1]
* `--page-size INTEGER`: Rows per page.  [default: 50]
* `--help`: Show this message and exit.

#### `d2w metadata category-option-groups create`

Create an empty CategoryOptionGroup.

**Usage**:

```console
$ d2w metadata category-option-groups create [OPTIONS]
```

**Options**:

* `--name TEXT`: Full name.  [required]
* `--short-name TEXT`: Short name.  [required]
* `--data-dimension-type TEXT`: DISAGGREGATION (default) or ATTRIBUTE.  [default: DISAGGREGATION]
* `--uid TEXT`: Explicit 11-char UID.
* `--code TEXT`: Business code.
* `--description TEXT`: Free text.
* `--help`: Show this message and exit.

#### `d2w metadata category-option-groups add-members`

Add `--category-option` members via the per-item POST shortcut.

**Usage**:

```console
$ d2w metadata category-option-groups add-members [OPTIONS] UID
```

**Arguments**:

* `UID`: CategoryOptionGroup UID.  [required]

**Options**:

* `-c, --category-option TEXT`: CategoryOption UID to add. Repeat for multiple.  [required]
* `--help`: Show this message and exit.

#### `d2w metadata category-option-groups remove-members`

Drop `--category-option` members via the per-item DELETE shortcut.

**Usage**:

```console
$ d2w metadata category-option-groups remove-members [OPTIONS] UID
```

**Arguments**:

* `UID`: CategoryOptionGroup UID.  [required]

**Options**:

* `-c, --category-option TEXT`: CategoryOption UID to drop. Repeat for multiple.  [required]
* `--help`: Show this message and exit.

#### `d2w metadata category-option-groups delete`

Delete the grouping row — member category options stay.

**Usage**:

```console
$ d2w metadata category-option-groups delete [OPTIONS] UID
```

**Arguments**:

* `UID`: CategoryOptionGroup UID.  [required]

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
$ d2w metadata category-option-group-sets get [OPTIONS] UID
```

**Arguments**:

* `UID`: CategoryOptionGroupSet UID.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w metadata category-option-group-sets create`

Create an empty CategoryOptionGroupSet.

**Usage**:

```console
$ d2w metadata category-option-group-sets create [OPTIONS]
```

**Options**:

* `--name TEXT`: Full name.  [required]
* `--short-name TEXT`: Short name.  [required]
* `--data-dimension-type TEXT`: DISAGGREGATION (default) or ATTRIBUTE.  [default: DISAGGREGATION]
* `--data-dimension / --no-data-dimension`: Expose as analytics axis.  [default: data-dimension]
* `--uid TEXT`: Explicit 11-char UID.
* `--code TEXT`: Business code.
* `--description TEXT`: Free text.
* `--help`: Show this message and exit.

#### `d2w metadata category-option-group-sets add-groups`

Add `--group` members to a group set.

**Usage**:

```console
$ d2w metadata category-option-group-sets add-groups [OPTIONS] UID
```

**Arguments**:

* `UID`: CategoryOptionGroupSet UID.  [required]

**Options**:

* `--group TEXT`: CategoryOptionGroup UID to add. Repeat for multiple.  [required]
* `--help`: Show this message and exit.

#### `d2w metadata category-option-group-sets remove-groups`

Drop `--group` members from a group set.

**Usage**:

```console
$ d2w metadata category-option-group-sets remove-groups [OPTIONS] UID
```

**Arguments**:

* `UID`: CategoryOptionGroupSet UID.  [required]

**Options**:

* `--group TEXT`: CategoryOptionGroup UID to drop. Repeat for multiple.  [required]
* `--help`: Show this message and exit.

#### `d2w metadata category-option-group-sets delete`

Delete a CategoryOptionGroupSet — member groups stay.

**Usage**:

```console
$ d2w metadata category-option-group-sets delete [OPTIONS] UID
```

**Arguments**:

* `UID`: CategoryOptionGroupSet UID.  [required]

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
$ d2w metadata categories get [OPTIONS] UID
```

**Arguments**:

* `UID`: Category UID.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w metadata categories create`

Create a Category, optionally wiring CategoryOption members on create.

**Usage**:

```console
$ d2w metadata categories create [OPTIONS]
```

**Options**:

* `--name TEXT`: Full name (&lt;=230 chars).  [required]
* `--short-name TEXT`: Short name (&lt;=50 chars).  [required]
* `--code TEXT`: Business code.
* `--description TEXT`: Free text.
* `--type TEXT`: DISAGGREGATION (default) or ATTRIBUTE.  [default: DISAGGREGATION]
* `--option TEXT`: CategoryOption UID to wire on create. Repeatable; order is preserved on save.
* `--uid TEXT`: Explicit 11-char UID.
* `--help`: Show this message and exit.

#### `d2w metadata categories rename`

Partial-update the label fields on a Category.

**Usage**:

```console
$ d2w metadata categories rename [OPTIONS] UID
```

**Arguments**:

* `UID`: Category UID.  [required]

**Options**:

* `--name TEXT`: New name.
* `--short-name TEXT`: New short name.
* `--description TEXT`: New description.
* `--help`: Show this message and exit.

#### `d2w metadata categories add-option`

Append a CategoryOption to this Category&#x27;s ordered membership.

**Usage**:

```console
$ d2w metadata categories add-option [OPTIONS] UID OPTION_UID
```

**Arguments**:

* `UID`: Category UID.  [required]
* `OPTION_UID`: CategoryOption UID to append.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w metadata categories remove-option`

Remove a CategoryOption from this Category&#x27;s membership.

**Usage**:

```console
$ d2w metadata categories remove-option [OPTIONS] UID OPTION_UID
```

**Arguments**:

* `UID`: Category UID.  [required]
* `OPTION_UID`: CategoryOption UID to remove.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w metadata categories delete`

Delete a Category — DHIS2 rejects deletes on categories referenced by a CategoryCombo.

**Usage**:

```console
$ d2w metadata categories delete [OPTIONS] UID
```

**Arguments**:

* `UID`: Category UID.  [required]

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
$ d2w metadata category-combos get [OPTIONS] UID
```

**Arguments**:

* `UID`: CategoryCombo UID.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w metadata category-combos create`

Create a CategoryCombo with an ordered list of Category UIDs.

**Usage**:

```console
$ d2w metadata category-combos create [OPTIONS]
```

**Options**:

* `--name TEXT`: Full name (&lt;=230 chars).  [required]
* `--category TEXT`: Category UID. Repeatable; order is preserved on save and shapes the COC matrix.  [required]
* `--code TEXT`: Business code.
* `--type TEXT`: DISAGGREGATION (default) or ATTRIBUTE.  [default: DISAGGREGATION]
* `--skip-total / --with-total`: Omit the total aggregation row downstream tables draw from this combo.  [default: with-total]
* `--uid TEXT`: Explicit 11-char UID.
* `--help`: Show this message and exit.

#### `d2w metadata category-combos rename`

Partial-update label fields on a CategoryCombo.

**Usage**:

```console
$ d2w metadata category-combos rename [OPTIONS] UID
```

**Arguments**:

* `UID`: CategoryCombo UID.  [required]

**Options**:

* `--name TEXT`: New name.
* `--code TEXT`: New code.
* `--help`: Show this message and exit.

#### `d2w metadata category-combos add-category`

Append a Category to this combo&#x27;s ordered membership.

DHIS2 regenerates the COC matrix server-side. Re-fetch the combo + use
`wait-for-cocs` if you need to block until the new matrix lands.

**Usage**:

```console
$ d2w metadata category-combos add-category [OPTIONS] UID CATEGORY_UID
```

**Arguments**:

* `UID`: CategoryCombo UID.  [required]
* `CATEGORY_UID`: Category UID to append.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w metadata category-combos remove-category`

Remove a Category from this combo&#x27;s membership.

**Usage**:

```console
$ d2w metadata category-combos remove-category [OPTIONS] UID CATEGORY_UID
```

**Arguments**:

* `UID`: CategoryCombo UID.  [required]
* `CATEGORY_UID`: Category UID to remove.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w metadata category-combos wait-for-cocs`

Block until the COC matrix on this combo reaches `--expected`.

Cold-start regen of a large combo can take tens of seconds, especially
under arm64 emulation. Use after `create` or `add-category` when the
next step depends on the matrix being ready.

**Usage**:

```console
$ d2w metadata category-combos wait-for-cocs [OPTIONS] UID
```

**Arguments**:

* `UID`: CategoryCombo UID.  [required]

**Options**:

* `--expected INTEGER`: Expected total of CategoryOptionCombos materialised by this combo.  [required]
* `--timeout FLOAT`: Seconds to wait before giving up (default 60).  [default: 60.0]
* `--poll FLOAT`: Seconds between polls (default 1).  [default: 1.0]
* `--help`: Show this message and exit.

#### `d2w metadata category-combos delete`

Delete a CategoryCombo — DHIS2 rejects the default combo + combos in use.

**Usage**:

```console
$ d2w metadata category-combos delete [OPTIONS] UID
```

**Arguments**:

* `UID`: CategoryCombo UID.  [required]

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

* `--spec TEXT`: Path to a JSON CategoryComboBuildSpec, or `-` to read from stdin. Shape: `{name, categories: [{name, options: [{name, ...}, ...]}, ...]}`.  [required]
* `--timeout FLOAT`: Seconds to wait for the COC matrix to settle (default 120).  [default: 120.0]
* `--poll FLOAT`: Seconds between matrix polls (default 1).  [default: 1.0]
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
$ d2w metadata category-option-combos get [OPTIONS] UID
```

**Arguments**:

* `UID`: CategoryOptionCombo UID.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w metadata category-option-combos list-for-combo`

List every CategoryOptionCombo materialised by one CategoryCombo.

**Usage**:

```console
$ d2w metadata category-option-combos list-for-combo [OPTIONS] COMBO_UID
```

**Arguments**:

* `COMBO_UID`: CategoryCombo UID.  [required]

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
$ d2w metadata data-sets get [OPTIONS] UID
```

**Arguments**:

* `UID`: DataSet UID.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w metadata data-sets create`

Create a DataSet.

**Usage**:

```console
$ d2w metadata data-sets create [OPTIONS]
```

**Options**:

* `--name TEXT`: Full name (&lt;=230 chars).  [required]
* `--short-name TEXT`: Short name (&lt;=50 chars).  [required]
* `--period-type TEXT`: Period type (Monthly, Weekly, Daily, Quarterly, Yearly, …).  [required]
* `-cc, --category-combo TEXT`: CategoryCombo UID (defaults to the instance default).
* `--code TEXT`: Business code.
* `--form-name TEXT`: Form-name override.
* `--description TEXT`: Free text.
* `--open-future-periods INTEGER`: Number of future periods open for entry.
* `--expiry-days INTEGER`: Days after period-end that entry remains open.
* `--timely-days INTEGER`: Days after period-start considered on-time.
* `--uid TEXT`: Explicit 11-char UID.
* `--help`: Show this message and exit.

#### `d2w metadata data-sets rename`

Partial-update the label fields on a DataSet.

**Usage**:

```console
$ d2w metadata data-sets rename [OPTIONS] UID
```

**Arguments**:

* `UID`: DataSet UID.  [required]

**Options**:

* `--name TEXT`: New name.
* `--short-name TEXT`: New short name.
* `--form-name TEXT`: New form name.
* `--description TEXT`: New description.
* `--help`: Show this message and exit.

#### `d2w metadata data-sets add-element`

Attach a DataElement to the DataSet (optionally with a per-set CategoryCombo override).

**Usage**:

```console
$ d2w metadata data-sets add-element [OPTIONS] DATA_SET_UID DATA_ELEMENT_UID
```

**Arguments**:

* `DATA_SET_UID`: DataSet UID.  [required]
* `DATA_ELEMENT_UID`: DataElement UID to attach.  [required]

**Options**:

* `-cc, --category-combo TEXT`: CategoryCombo UID override for this DSE.
* `--help`: Show this message and exit.

#### `d2w metadata data-sets remove-element`

Detach a DataElement from the DataSet.

**Usage**:

```console
$ d2w metadata data-sets remove-element [OPTIONS] DATA_SET_UID DATA_ELEMENT_UID
```

**Arguments**:

* `DATA_SET_UID`: DataSet UID.  [required]
* `DATA_ELEMENT_UID`: DataElement UID to detach.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w metadata data-sets delete`

Delete a DataSet — DHIS2 rejects deletes on DataSets with saved values.

**Usage**:

```console
$ d2w metadata data-sets delete [OPTIONS] UID
```

**Arguments**:

* `UID`: DataSet UID.  [required]

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
$ d2w metadata sections get [OPTIONS] UID
```

**Arguments**:

* `UID`: Section UID.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w metadata sections create`

Create a Section attached to a DataSet. Repeat `--data-element` to seed the ordered DE list.

**Usage**:

```console
$ d2w metadata sections create [OPTIONS]
```

**Options**:

* `--name TEXT`: Section name (&lt;=230 chars).  [required]
* `-ds, --data-set TEXT`: Parent DataSet UID.  [required]
* `--sort-order INTEGER`: Ordering within the DataSet (ascending).
* `--description TEXT`: Free text.
* `--code TEXT`: Business code.
* `-de, --data-element TEXT`: DataElement UID (repeatable, order preserved).
* `-i, --indicator TEXT`: Indicator UID to show in the side pane (repeatable).
* `--show-column-totals / --no-show-column-totals`: Render column totals.
* `--show-row-totals / --no-show-row-totals`: Render row totals.
* `--uid TEXT`: Explicit 11-char UID.
* `--help`: Show this message and exit.

#### `d2w metadata sections rename`

Partial-update the label / sort-order fields on a Section.

**Usage**:

```console
$ d2w metadata sections rename [OPTIONS] UID
```

**Arguments**:

* `UID`: Section UID.  [required]

**Options**:

* `--name TEXT`: New name.
* `--description TEXT`: New description.
* `--sort-order INTEGER`: New sort order.
* `--help`: Show this message and exit.

#### `d2w metadata sections add-element`

Append (or insert at `--position`) a DataElement to the Section.

**Usage**:

```console
$ d2w metadata sections add-element [OPTIONS] SECTION_UID DATA_ELEMENT_UID
```

**Arguments**:

* `SECTION_UID`: Section UID.  [required]
* `DATA_ELEMENT_UID`: DataElement UID.  [required]

**Options**:

* `--position INTEGER`: 0-indexed insertion position. Omit to append.
* `--help`: Show this message and exit.

#### `d2w metadata sections remove-element`

Remove a DataElement from the Section (stays on the parent DataSet).

**Usage**:

```console
$ d2w metadata sections remove-element [OPTIONS] SECTION_UID DATA_ELEMENT_UID
```

**Arguments**:

* `SECTION_UID`: Section UID.  [required]
* `DATA_ELEMENT_UID`: DataElement UID.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w metadata sections reorder`

Replace the Section&#x27;s `dataElements` with exactly the given UIDs in order.

**Usage**:

```console
$ d2w metadata sections reorder [OPTIONS] SECTION_UID DATA_ELEMENT_UIDS...
```

**Arguments**:

* `SECTION_UID`: Section UID.  [required]
* `DATA_ELEMENT_UIDS...`: DataElement UIDs in the desired order.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w metadata sections delete`

Delete a Section — DEs stay on the parent DataSet.

**Usage**:

```console
$ d2w metadata sections delete [OPTIONS] UID
```

**Arguments**:

* `UID`: Section UID.  [required]

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
$ d2w metadata validation-rules get [OPTIONS] UID
```

**Arguments**:

* `UID`: ValidationRule UID.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w metadata validation-rules create`

Create a ValidationRule.

**Usage**:

```console
$ d2w metadata validation-rules create [OPTIONS]
```

**Options**:

* `--name TEXT`: Rule name (&lt;=230 chars).  [required]
* `--short-name TEXT`: Short name (&lt;=50 chars).  [required]
* `--left TEXT`: Left-side expression (e.g. #{deUid}).  [required]
* `--operator TEXT`: Comparison operator.  [required]
* `--right TEXT`: Right-side expression.  [required]
* `--period-type TEXT`: Period type.  [default: Monthly]
* `--importance TEXT`: LOW / MEDIUM / HIGH.  [default: MEDIUM]
* `--missing-value-strategy TEXT`: How to treat absent operands.  [default: SKIP_IF_ALL_VALUES_MISSING]
* `--description TEXT`: Free-text description.
* `--code TEXT`: Business code.
* `--ou-level INTEGER`: OU depth (repeatable). E.g. `--ou-level 4` for facilities.
* `--uid TEXT`: Explicit 11-char UID.
* `--help`: Show this message and exit.

#### `d2w metadata validation-rules rename`

Partial-update the label fields on a ValidationRule.

**Usage**:

```console
$ d2w metadata validation-rules rename [OPTIONS] UID
```

**Arguments**:

* `UID`: ValidationRule UID.  [required]

**Options**:

* `--name TEXT`: New name.
* `--short-name TEXT`: New short name.
* `--description TEXT`: New description.
* `--help`: Show this message and exit.

#### `d2w metadata validation-rules delete`

Delete a ValidationRule — any outstanding results are purged.

**Usage**:

```console
$ d2w metadata validation-rules delete [OPTIONS] UID
```

**Arguments**:

* `UID`: ValidationRule UID.  [required]

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
$ d2w metadata validation-rule-groups get [OPTIONS] UID
```

**Arguments**:

* `UID`: ValidationRuleGroup UID.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w metadata validation-rule-groups members`

Page through ValidationRules inside a group.

**Usage**:

```console
$ d2w metadata validation-rule-groups members [OPTIONS] UID
```

**Arguments**:

* `UID`: ValidationRuleGroup UID.  [required]

**Options**:

* `--page INTEGER`: 1-based page.  [default: 1]
* `--page-size INTEGER`: Rows per page.  [default: 50]
* `--help`: Show this message and exit.

#### `d2w metadata validation-rule-groups create`

Create an empty ValidationRuleGroup.

**Usage**:

```console
$ d2w metadata validation-rule-groups create [OPTIONS]
```

**Options**:

* `--name TEXT`: Group name.  [required]
* `--short-name TEXT`: Short name.
* `--code TEXT`: Business code.
* `--description TEXT`: Free text.
* `--uid TEXT`: Explicit 11-char UID.
* `--help`: Show this message and exit.

#### `d2w metadata validation-rule-groups add-members`

Attach ValidationRules to a group.

**Usage**:

```console
$ d2w metadata validation-rule-groups add-members [OPTIONS] UID
```

**Arguments**:

* `UID`: ValidationRuleGroup UID.  [required]

**Options**:

* `-r, --rule TEXT`: ValidationRule UID (repeatable).  [required]
* `--help`: Show this message and exit.

#### `d2w metadata validation-rule-groups remove-members`

Detach ValidationRules from a group.

**Usage**:

```console
$ d2w metadata validation-rule-groups remove-members [OPTIONS] UID
```

**Arguments**:

* `UID`: ValidationRuleGroup UID.  [required]

**Options**:

* `-r, --rule TEXT`: ValidationRule UID (repeatable).  [required]
* `--help`: Show this message and exit.

#### `d2w metadata validation-rule-groups delete`

Delete a ValidationRuleGroup — member rules stay.

**Usage**:

```console
$ d2w metadata validation-rule-groups delete [OPTIONS] UID
```

**Arguments**:

* `UID`: ValidationRuleGroup UID.  [required]

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
$ d2w metadata predictors get [OPTIONS] UID
```

**Arguments**:

* `UID`: Predictor UID.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w metadata predictors create`

Create a Predictor.

**Usage**:

```console
$ d2w metadata predictors create [OPTIONS]
```

**Options**:

* `--name TEXT`: Predictor name.  [required]
* `--short-name TEXT`: Short name.  [required]
* `--expression TEXT`: Generator expression (e.g. #{deUid}).  [required]
* `-o, --output TEXT`: Output DataElement UID.  [required]
* `--period-type TEXT`: Period type.  [default: Monthly]
* `--sequential INTEGER`: Sequential sample count (e.g. 3 for 3-month rolling).  [default: 3]
* `--annual INTEGER`: Annual sample count.  [default: 0]
* `--ou-level TEXT`: OrganisationUnitLevel UID (repeatable).
* `--output-combo TEXT`: Output CategoryOptionCombo UID.
* `--description TEXT`: Free text.
* `--code TEXT`: Business code.
* `--uid TEXT`: Explicit 11-char UID.
* `--help`: Show this message and exit.

#### `d2w metadata predictors rename`

Partial-update the label fields on a Predictor.

**Usage**:

```console
$ d2w metadata predictors rename [OPTIONS] UID
```

**Arguments**:

* `UID`: Predictor UID.  [required]

**Options**:

* `--name TEXT`: New name.
* `--short-name TEXT`: New short name.
* `--description TEXT`: New description.
* `--help`: Show this message and exit.

#### `d2w metadata predictors delete`

Delete a Predictor. DHIS2 keeps any data values it has already written.

**Usage**:

```console
$ d2w metadata predictors delete [OPTIONS] UID
```

**Arguments**:

* `UID`: Predictor UID.  [required]

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
$ d2w metadata predictor-groups get [OPTIONS] UID
```

**Arguments**:

* `UID`: PredictorGroup UID.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w metadata predictor-groups members`

Page through Predictors in a group.

**Usage**:

```console
$ d2w metadata predictor-groups members [OPTIONS] UID
```

**Arguments**:

* `UID`: PredictorGroup UID.  [required]

**Options**:

* `--page INTEGER`: 1-based page.  [default: 1]
* `--page-size INTEGER`: Rows per page.  [default: 50]
* `--help`: Show this message and exit.

#### `d2w metadata predictor-groups create`

Create an empty PredictorGroup.

**Usage**:

```console
$ d2w metadata predictor-groups create [OPTIONS]
```

**Options**:

* `--name TEXT`: Group name.  [required]
* `--short-name TEXT`: Short name.
* `--code TEXT`: Business code.
* `--description TEXT`: Free text.
* `--uid TEXT`: Explicit 11-char UID.
* `--help`: Show this message and exit.

#### `d2w metadata predictor-groups add-members`

Attach Predictors to a group.

**Usage**:

```console
$ d2w metadata predictor-groups add-members [OPTIONS] UID
```

**Arguments**:

* `UID`: PredictorGroup UID.  [required]

**Options**:

* `-p, --predictor TEXT`: Predictor UID (repeatable).  [required]
* `--help`: Show this message and exit.

#### `d2w metadata predictor-groups remove-members`

Detach Predictors from a group.

**Usage**:

```console
$ d2w metadata predictor-groups remove-members [OPTIONS] UID
```

**Arguments**:

* `UID`: PredictorGroup UID.  [required]

**Options**:

* `-p, --predictor TEXT`: Predictor UID (repeatable).  [required]
* `--help`: Show this message and exit.

#### `d2w metadata predictor-groups delete`

Delete a PredictorGroup — member predictors stay.

**Usage**:

```console
$ d2w metadata predictor-groups delete [OPTIONS] UID
```

**Arguments**:

* `UID`: PredictorGroup UID.  [required]

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
$ d2w metadata tracked-entity-attributes get [OPTIONS] UID
```

**Arguments**:

* `UID`: TrackedEntityAttribute UID.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w metadata tracked-entity-attributes create`

Create a TrackedEntityAttribute.

**Usage**:

```console
$ d2w metadata tracked-entity-attributes create [OPTIONS]
```

**Options**:

* `--name TEXT`: Attribute name (&lt;=230 chars).  [required]
* `--short-name TEXT`: Short name (&lt;=50 chars).  [required]
* `--value-type TEXT`: TEXT / NUMBER / DATE / …  [default: TEXT]
* `--aggregation-type TEXT`: DHIS2 aggregation type.  [default: NONE]
* `--option-set TEXT`: Constraining OptionSet UID.
* `--legend-set TEXT`: LegendSet UID (repeatable).
* `--unique / --no-unique`: Unique across the instance.  [default: no-unique]
* `--generated / --no-generated`: Auto-generate via --pattern on TEI register.  [default: no-generated]
* `--confidential / --no-confidential`: Sensitive.  [default: no-confidential]
* `--inherit / --no-inherit`: Inherit on parent/child TEI link.  [default: no-inherit]
* `--display-in-list-no-program / --no-display-in-list-no-program`: Show in the list when no program is selected.  [default: no-display-in-list-no-program]
* `--orgunit-scope / --no-orgunit-scope`: Scope values to the capturing OU.  [default: no-orgunit-scope]
* `--pattern TEXT`: Generator pattern (with --generated).
* `--field-mask TEXT`: Input mask for the data-entry field.
* `--code TEXT`: Business code.
* `--form-name TEXT`: Form-name override.
* `--description TEXT`: Free text.
* `--uid TEXT`: Explicit 11-char UID.
* `--help`: Show this message and exit.

#### `d2w metadata tracked-entity-attributes rename`

Partial-update the label fields on a TrackedEntityAttribute.

**Usage**:

```console
$ d2w metadata tracked-entity-attributes rename [OPTIONS] UID
```

**Arguments**:

* `UID`: TrackedEntityAttribute UID.  [required]

**Options**:

* `--name TEXT`: New name.
* `--short-name TEXT`: New short name.
* `--form-name TEXT`: New form name.
* `--description TEXT`: New description.
* `--help`: Show this message and exit.

#### `d2w metadata tracked-entity-attributes delete`

Delete a TrackedEntityAttribute — DHIS2 rejects deletes on TEAs wired into a TET or program.

**Usage**:

```console
$ d2w metadata tracked-entity-attributes delete [OPTIONS] UID
```

**Arguments**:

* `UID`: TrackedEntityAttribute UID.  [required]

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
$ d2w metadata tracked-entity-types get [OPTIONS] UID
```

**Arguments**:

* `UID`: TrackedEntityType UID.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w metadata tracked-entity-types create`

Create a TrackedEntityType.

**Usage**:

```console
$ d2w metadata tracked-entity-types create [OPTIONS]
```

**Options**:

* `--name TEXT`: TET name (&lt;=230 chars).  [required]
* `--short-name TEXT`: Short name (&lt;=50 chars).  [required]
* `--description TEXT`: Free text.
* `--code TEXT`: Business code.
* `--form-name TEXT`: Form-name override.
* `--allow-audit-log / --no-allow-audit-log`: Enable the per-TEI audit trail.
* `--feature-type TEXT`: NONE / POINT / POLYGON — geometry captured per TEI.
* `--min-attrs INTEGER`: Min attributes required to search TEIs.
* `--max-tei INTEGER`: Max TEI count to return per search.
* `--uid TEXT`: Explicit 11-char UID.
* `--help`: Show this message and exit.

#### `d2w metadata tracked-entity-types rename`

Partial-update the label fields on a TrackedEntityType.

**Usage**:

```console
$ d2w metadata tracked-entity-types rename [OPTIONS] UID
```

**Arguments**:

* `UID`: TrackedEntityType UID.  [required]

**Options**:

* `--name TEXT`: New name.
* `--short-name TEXT`: New short name.
* `--form-name TEXT`: New form name.
* `--description TEXT`: New description.
* `--help`: Show this message and exit.

#### `d2w metadata tracked-entity-types add-attribute`

Attach a TrackedEntityAttribute to a TrackedEntityType.

**Usage**:

```console
$ d2w metadata tracked-entity-types add-attribute [OPTIONS] TET_UID ATTRIBUTE_UID
```

**Arguments**:

* `TET_UID`: TrackedEntityType UID.  [required]
* `ATTRIBUTE_UID`: TrackedEntityAttribute UID to wire in.  [required]

**Options**:

* `--mandatory / --no-mandatory`: Require on enrollment.  [default: no-mandatory]
* `--searchable / --no-searchable`: Include in TEI search.  [default: no-searchable]
* `--display-in-list / --no-display-in-list`: Show in the enrolled-TEI list.  [default: display-in-list]
* `--help`: Show this message and exit.

#### `d2w metadata tracked-entity-types remove-attribute`

Detach a TrackedEntityAttribute from a TrackedEntityType.

**Usage**:

```console
$ d2w metadata tracked-entity-types remove-attribute [OPTIONS] TET_UID ATTRIBUTE_UID
```

**Arguments**:

* `TET_UID`: TrackedEntityType UID.  [required]
* `ATTRIBUTE_UID`: TrackedEntityAttribute UID to detach.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w metadata tracked-entity-types delete`

Delete a TrackedEntityType — DHIS2 rejects deletes on TETs in use by enrolled TEIs.

**Usage**:

```console
$ d2w metadata tracked-entity-types delete [OPTIONS] UID
```

**Arguments**:

* `UID`: TrackedEntityType UID.  [required]

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
$ d2w metadata programs get [OPTIONS] UID
```

**Arguments**:

* `UID`: Program UID.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w metadata programs create`

Create a Program. `--program-type WITH_REGISTRATION` requires `--tracked-entity-type`.

**Usage**:

```console
$ d2w metadata programs create [OPTIONS]
```

**Options**:

* `--name TEXT`: Program name (&lt;=230 chars).  [required]
* `--short-name TEXT`: Short name (&lt;=50 chars).  [required]
* `--program-type TEXT`: WITH_REGISTRATION (tracker) or WITHOUT_REGISTRATION (event).  [default: WITH_REGISTRATION]
* `-tet, --tracked-entity-type TEXT`: TET UID. Required for WITH_REGISTRATION.
* `-cc, --category-combo TEXT`: CategoryCombo UID (defaults to the instance default).
* `--description TEXT`: Free text.
* `--code TEXT`: Business code.
* `--form-name TEXT`: Form-name override.
* `--display-incident-date / --no-display-incident-date`: Capture an incident date.
* `--enrollment-date-label TEXT`: Custom enrollment-date label.
* `--incident-date-label TEXT`: Custom incident-date label.
* `--feature-type TEXT`: Geometry captured per enrollment (NONE / POINT / POLYGON).
* `--only-enroll-once / --no-only-enroll-once`: Block re-enrollment of the same TEI.
* `--expiry-days INTEGER`: Days after which enrollments expire for edit.
* `--min-attrs INTEGER`: Min attributes required for TEI search.
* `--max-tei INTEGER`: Max TEI count per search.
* `--use-first-stage-during-registration / --no-use-first-stage-during-registration`: Run the first ProgramStage inside the enrollment flow.
* `--uid TEXT`: Explicit 11-char UID.
* `--help`: Show this message and exit.

#### `d2w metadata programs rename`

Partial-update the label fields on a Program.

**Usage**:

```console
$ d2w metadata programs rename [OPTIONS] UID
```

**Arguments**:

* `UID`: Program UID.  [required]

**Options**:

* `--name TEXT`: New name.
* `--short-name TEXT`: New short name.
* `--form-name TEXT`: New form name.
* `--description TEXT`: New description.
* `--help`: Show this message and exit.

#### `d2w metadata programs add-attribute`

Attach a TrackedEntityAttribute to the Program&#x27;s enrollment form.

**Usage**:

```console
$ d2w metadata programs add-attribute [OPTIONS] PROGRAM_UID ATTRIBUTE_UID
```

**Arguments**:

* `PROGRAM_UID`: Program UID.  [required]
* `ATTRIBUTE_UID`: TrackedEntityAttribute UID.  [required]

**Options**:

* `--mandatory / --no-mandatory`: Require on enrollment.  [default: no-mandatory]
* `--searchable / --no-searchable`: Include in search.  [default: no-searchable]
* `--display-in-list / --no-display-in-list`: Show in enrolled-TEI list.  [default: display-in-list]
* `--sort-order INTEGER`: Position on enrollment form.
* `--allow-future-date / --no-allow-future-date`: Permit dates past today.  [default: no-allow-future-date]
* `--render-options-as-radio / --no-render-options-as-radio`: Render option-set choices as radios instead of a dropdown.  [default: no-render-options-as-radio]
* `--help`: Show this message and exit.

#### `d2w metadata programs remove-attribute`

Detach a TrackedEntityAttribute from the Program&#x27;s enrollment form.

**Usage**:

```console
$ d2w metadata programs remove-attribute [OPTIONS] PROGRAM_UID ATTRIBUTE_UID
```

**Arguments**:

* `PROGRAM_UID`: Program UID.  [required]
* `ATTRIBUTE_UID`: TrackedEntityAttribute UID.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w metadata programs add-to-ou`

Scope the Program to another OrganisationUnit.

**Usage**:

```console
$ d2w metadata programs add-to-ou [OPTIONS] PROGRAM_UID ORGANISATION_UNIT_UID
```

**Arguments**:

* `PROGRAM_UID`: Program UID.  [required]
* `ORGANISATION_UNIT_UID`: OrganisationUnit UID.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w metadata programs remove-from-ou`

Drop an OrganisationUnit from the Program&#x27;s scope.

**Usage**:

```console
$ d2w metadata programs remove-from-ou [OPTIONS] PROGRAM_UID ORGANISATION_UNIT_UID
```

**Arguments**:

* `PROGRAM_UID`: Program UID.  [required]
* `ORGANISATION_UNIT_UID`: OrganisationUnit UID.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w metadata programs delete`

Delete a Program — DHIS2 rejects deletes on programs with enrollments or events.

**Usage**:

```console
$ d2w metadata programs delete [OPTIONS] UID
```

**Arguments**:

* `UID`: Program UID.  [required]

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
$ d2w metadata program-stages get [OPTIONS] UID
```

**Arguments**:

* `UID`: ProgramStage UID.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w metadata program-stages create`

Create a ProgramStage under `--program`.

**Usage**:

```console
$ d2w metadata program-stages create [OPTIONS]
```

**Options**:

* `--name TEXT`: ProgramStage name (&lt;=230 chars).  [required]
* `-p, --program TEXT`: Parent Program UID.  [required]
* `--short-name TEXT`: Short name.
* `--description TEXT`: Free text.
* `--code TEXT`: Business code.
* `--sort-order INTEGER`: Stage order inside the Program.
* `--repeatable / --no-repeatable`: Allow the stage to reoccur within one enrollment.
* `--auto-generate-event / --no-auto-generate-event`: Auto-create an event when the enrollment starts.
* `--generated-by-enrollment-date / --no-generated-by-enrollment-date`: Base due-date math on enrollment date (vs incident date).
* `--feature-type TEXT`: Geometry captured per event (NONE / POINT / POLYGON).
* `--period-type TEXT`: Period type for scheduled events.
* `--validation-strategy TEXT`: ON_COMPLETE / ON_UPDATE_AND_INSERT.
* `--min-days INTEGER`: Minimum days from enrollment start before the stage opens.
* `--standard-interval INTEGER`: Default days between scheduled repeats.
* `--uid TEXT`: Explicit 11-char UID.
* `--help`: Show this message and exit.

#### `d2w metadata program-stages rename`

Partial-update the label fields on a ProgramStage.

**Usage**:

```console
$ d2w metadata program-stages rename [OPTIONS] UID
```

**Arguments**:

* `UID`: ProgramStage UID.  [required]

**Options**:

* `--name TEXT`: New name.
* `--short-name TEXT`: New short name.
* `--form-name TEXT`: New form name.
* `--description TEXT`: New description.
* `--help`: Show this message and exit.

#### `d2w metadata program-stages add-element`

Attach a DataElement to the ProgramStage.

**Usage**:

```console
$ d2w metadata program-stages add-element [OPTIONS] STAGE_UID DATA_ELEMENT_UID
```

**Arguments**:

* `STAGE_UID`: ProgramStage UID.  [required]
* `DATA_ELEMENT_UID`: DataElement UID to attach.  [required]

**Options**:

* `--compulsory / --no-compulsory`: Required on save.  [default: no-compulsory]
* `--allow-future-date / --no-allow-future-date`: Permit dates past today.  [default: no-allow-future-date]
* `--display-in-reports / --no-display-in-reports`: Show in event reports.  [default: display-in-reports]
* `--allow-provided-elsewhere / --no-allow-provided-elsewhere`: Mark the value as provided by a different OU.  [default: no-allow-provided-elsewhere]
* `--render-options-as-radio / --no-render-options-as-radio`: Render option-set picklists as radios.  [default: no-render-options-as-radio]
* `--sort-order INTEGER`: Position inside the stage data-entry form.
* `--help`: Show this message and exit.

#### `d2w metadata program-stages remove-element`

Detach a DataElement from the ProgramStage.

**Usage**:

```console
$ d2w metadata program-stages remove-element [OPTIONS] STAGE_UID DATA_ELEMENT_UID
```

**Arguments**:

* `STAGE_UID`: ProgramStage UID.  [required]
* `DATA_ELEMENT_UID`: DataElement UID.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w metadata program-stages reorder`

Replace the ProgramStage&#x27;s PSDE list with exactly the given DE UIDs in order.

**Usage**:

```console
$ d2w metadata program-stages reorder [OPTIONS] STAGE_UID DATA_ELEMENT_UIDS...
```

**Arguments**:

* `STAGE_UID`: ProgramStage UID.  [required]
* `DATA_ELEMENT_UIDS...`: DataElement UIDs in the desired order.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w metadata program-stages delete`

Delete a ProgramStage — DHIS2 rejects deletes on stages with recorded events.

**Usage**:

```console
$ d2w metadata program-stages delete [OPTIONS] UID
```

**Arguments**:

* `UID`: ProgramStage UID.  [required]

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
$ d2w metadata organisation-units get [OPTIONS] UID
```

**Arguments**:

* `UID`: OrganisationUnit UID.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w metadata organisation-units tree`

Render a bounded-depth subtree indented by hierarchy level.

**Usage**:

```console
$ d2w metadata organisation-units tree [OPTIONS] ROOT_UID
```

**Arguments**:

* `ROOT_UID`: Root OU UID — render this + descendants.  [required]

**Options**:

* `--max-depth INTEGER`: Depth of descendants to include (0 = just the root).  [default: 3]
* `--help`: Show this message and exit.

#### `d2w metadata organisation-units create`

Create a child OU under `parent_uid`.

**Usage**:

```console
$ d2w metadata organisation-units create [OPTIONS] PARENT_UID
```

**Arguments**:

* `PARENT_UID`: Parent OU UID to create under.  [required]

**Options**:

* `--name TEXT`: Full name (&lt;=230 chars).  [required]
* `--short-name TEXT`: Short name (&lt;=50 chars).  [required]
* `--opening-date TEXT`: ISO-8601 date, e.g. 2024-01-01.  [required]
* `--uid TEXT`: Explicit 11-char UID (generated when omitted).
* `--code TEXT`: Business code.
* `--description TEXT`: Free-text description.
* `--help`: Show this message and exit.

#### `d2w metadata organisation-units move`

Reparent an OU. DHIS2 recomputes `path` + `hierarchyLevel`.

**Usage**:

```console
$ d2w metadata organisation-units move [OPTIONS] UID NEW_PARENT_UID
```

**Arguments**:

* `UID`: OU UID to reparent.  [required]
* `NEW_PARENT_UID`: New parent OU UID.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w metadata organisation-units delete`

Delete an OU. DHIS2 rejects deletes on units with children or data.

**Usage**:

```console
$ d2w metadata organisation-units delete [OPTIONS] UID
```

**Arguments**:

* `UID`: OU UID to delete.  [required]

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
$ d2w metadata organisation-unit-groups get [OPTIONS] UID
```

**Arguments**:

* `UID`: OrganisationUnitGroup UID.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w metadata organisation-unit-groups members`

Page through the OUs inside one group.

**Usage**:

```console
$ d2w metadata organisation-unit-groups members [OPTIONS] UID
```

**Arguments**:

* `UID`: OrganisationUnitGroup UID.  [required]

**Options**:

* `--page INTEGER`: 1-based page number.  [default: 1]
* `--page-size INTEGER`: Rows per page.  [default: 50]
* `--help`: Show this message and exit.

#### `d2w metadata organisation-unit-groups create`

Create an empty OrganisationUnitGroup.

**Usage**:

```console
$ d2w metadata organisation-unit-groups create [OPTIONS]
```

**Options**:

* `--name TEXT`: Full name (&lt;=230 chars, unique).  [required]
* `--short-name TEXT`: Short name (&lt;=50 chars, unique).  [required]
* `--uid TEXT`: Explicit 11-char UID (generated when omitted).
* `--code TEXT`: Business code.
* `--description TEXT`: Free-text description.
* `--color TEXT`: Hex colour (#RRGGBB).
* `--help`: Show this message and exit.

#### `d2w metadata organisation-unit-groups add-members`

Add `--ou` members to a group via the per-item POST shortcut.

**Usage**:

```console
$ d2w metadata organisation-unit-groups add-members [OPTIONS] UID
```

**Arguments**:

* `UID`: OrganisationUnitGroup UID.  [required]

**Options**:

* `--ou TEXT`: OU UID to add. Repeat for multiple.  [required]
* `--help`: Show this message and exit.

#### `d2w metadata organisation-unit-groups remove-members`

Drop `--ou` members from a group via the per-item DELETE shortcut.

**Usage**:

```console
$ d2w metadata organisation-unit-groups remove-members [OPTIONS] UID
```

**Arguments**:

* `UID`: OrganisationUnitGroup UID.  [required]

**Options**:

* `--ou TEXT`: OU UID to remove. Repeat for multiple.  [required]
* `--help`: Show this message and exit.

#### `d2w metadata organisation-unit-groups delete`

Delete an OrganisationUnitGroup — members stay.

**Usage**:

```console
$ d2w metadata organisation-unit-groups delete [OPTIONS] UID
```

**Arguments**:

* `UID`: OrganisationUnitGroup UID to delete.  [required]

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
$ d2w metadata organisation-unit-group-sets get [OPTIONS] UID
```

**Arguments**:

* `UID`: OrganisationUnitGroupSet UID.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w metadata organisation-unit-group-sets create`

Create an empty OrganisationUnitGroupSet.

**Usage**:

```console
$ d2w metadata organisation-unit-group-sets create [OPTIONS]
```

**Options**:

* `--name TEXT`: Full name (&lt;=230 chars, unique).  [required]
* `--short-name TEXT`: Short name (&lt;=50 chars, unique).  [required]
* `--uid TEXT`: Explicit 11-char UID (generated when omitted).
* `--code TEXT`: Business code.
* `--description TEXT`: Free-text description.
* `--compulsory / --not-compulsory`: Require OUs to land in exactly one group of this set.  [default: not-compulsory]
* `--data-dimension / --no-data-dimension`: Expose as a pivot/visualisation axis.  [default: data-dimension]
* `--help`: Show this message and exit.

#### `d2w metadata organisation-unit-group-sets add-groups`

Add `--group` members to a group set.

**Usage**:

```console
$ d2w metadata organisation-unit-group-sets add-groups [OPTIONS] UID
```

**Arguments**:

* `UID`: OrganisationUnitGroupSet UID.  [required]

**Options**:

* `--group TEXT`: OrganisationUnitGroup UID to add. Repeat for multiple.  [required]
* `--help`: Show this message and exit.

#### `d2w metadata organisation-unit-group-sets remove-groups`

Drop `--group` members from a group set.

**Usage**:

```console
$ d2w metadata organisation-unit-group-sets remove-groups [OPTIONS] UID
```

**Arguments**:

* `UID`: OrganisationUnitGroupSet UID.  [required]

**Options**:

* `--group TEXT`: OrganisationUnitGroup UID to drop. Repeat for multiple.  [required]
* `--help`: Show this message and exit.

#### `d2w metadata organisation-unit-group-sets delete`

Delete an OrganisationUnitGroupSet — groups stay.

**Usage**:

```console
$ d2w metadata organisation-unit-group-sets delete [OPTIONS] UID
```

**Arguments**:

* `UID`: OrganisationUnitGroupSet UID to delete.  [required]

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
$ d2w metadata organisation-unit-levels get [OPTIONS] UID
```

**Arguments**:

* `UID`: OrganisationUnitLevel UID (or pass --by-level).  [required]

**Options**:

* `--by-level`: Treat UID as the numeric level (1 = roots).
* `--help`: Show this message and exit.

#### `d2w metadata organisation-unit-levels rename`

Give a level a human label — turns &#x27;level 2&#x27; into &#x27;Province&#x27;.

**Usage**:

```console
$ d2w metadata organisation-unit-levels rename [OPTIONS] UID
```

**Arguments**:

* `UID`: OrganisationUnitLevel UID (or the numeric level with --by-level).  [required]

**Options**:

* `--name TEXT`: New human label (e.g. &#x27;Country&#x27;, &#x27;District&#x27;, &#x27;Facility&#x27;).  [required]
* `--by-level`: Treat UID as the numeric level (1 = roots).
* `--code TEXT`: Optionally update the business code.
* `--offline-levels INTEGER`: How many levels to cache offline from this one.
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
$ d2w metadata legend-sets get [OPTIONS] UID
```

**Arguments**:

* `UID`: LegendSet UID.  [required]

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

* `--name TEXT`: Display name for the new LegendSet.  [required]
* `--legend TEXT`: One legend (colour range) in `start🔚color[:name]` form. Repeatable, at least one required. Example: `--legend 0:1000:#d73027:Low --legend 1000:5000:#1a9850:High`.  [required]
* `--code TEXT`: Business code (unique).
* `--uid TEXT`: Fixed 11-char UID. Omit to let the client generate one.
* `--help`: Show this message and exit.

#### `d2w metadata legend-sets clone`

Duplicate an existing LegendSet with the same bands + fresh UIDs.

Useful for forking a base set (&quot;Coverage 0-100&quot;) into a variant
without rebuilding the bands by hand.

**Usage**:

```console
$ d2w metadata legend-sets clone [OPTIONS] SOURCE_UID
```

**Arguments**:

* `SOURCE_UID`: Source LegendSet UID to clone.  [required]

**Options**:

* `--new-name TEXT`: Name of the clone (default: append &#x27; (clone)&#x27; to the source&#x27;s name).
* `--new-uid TEXT`: Fixed 11-char UID for the clone. Omit for auto-generated.
* `--new-code TEXT`: Business code on the clone.
* `--help`: Show this message and exit.

#### `d2w metadata legend-sets delete`

Delete a LegendSet.

**Usage**:

```console
$ d2w metadata legend-sets delete [OPTIONS] UID
```

**Arguments**:

* `UID`: LegendSet UID to delete.  [required]

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
$ d2w profile verify [OPTIONS] [NAME]
```

**Arguments**:

* `[NAME]`: Profile name to verify; omit to verify all.

**Options**:

* `--help`: Show this message and exit.

### `d2w profile show`

Print one profile (secrets redacted by default).

**Usage**:

```console
$ d2w profile show [OPTIONS] NAME
```

**Arguments**:

* `NAME`: [required]

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
$ d2w profile env [OPTIONS] [NAME]
```

**Arguments**:

* `[NAME]`: Profile name; defaults to the active profile.

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
$ d2w profile default [OPTIONS] [NAME]
```

**Arguments**:

* `[NAME]`: Profile name to set as default. Omit to pick interactively from a list.

**Options**:

* `--global`: Write to ~/.config/dhis2/profiles.toml (default).
* `--local`: Write to ./.dhis2/profiles.toml instead.
* `--verify`: Probe the instance after switching.
* `--help`: Show this message and exit.

### `d2w profile add`

Add (or upsert) a profile.

Secrets are never accepted as command-line flags (they&#x27;d leak into shell history).
Read from env (`DHIS2_PAT`, `DHIS2_PASSWORD`, `DHIS2_OAUTH_CLIENT_SECRET`,
`DHIS2_SESSION_COOKIE`) or prompted interactively when missing.

**Usage**:

```console
$ d2w profile add [OPTIONS] NAME
```

**Arguments**:

* `NAME`: [required]

**Options**:

* `--url TEXT`: DHIS2 base URL (also: DHIS2_URL env).
* `--auth TEXT`: pat | basic | oauth2 | session  [default: pat]
* `--username TEXT`: Basic-auth username.
* `--client-id TEXT`: OAuth2 client_id.
* `--scope TEXT`: OAuth2 scope (DHIS2 only recognises `ALL`).  [default: ALL]
* `--redirect-uri TEXT`: OAuth2 redirect URI (must match the registered client).  [default: http://localhost:8765]
* `--from-env`: Pull OAuth2 fields from DHIS2_OAUTH_CLIENT_ID / DHIS2_OAUTH_CLIENT_SECRET / DHIS2_OAUTH_REDIRECT_URI / DHIS2_OAUTH_SCOPES env vars (seeded .env.auth).
* `--global`: Save to ~/.config/dhis2/profiles.toml (default — user-wide, applies everywhere).
* `--local`: Save to ./.dhis2/profiles.toml instead (project-scoped, overrides global).
* `--default`: Set as default after adding.
* `--verify`: Probe /api/system/info + /api/me after saving.
* `--version TEXT`: Expected DHIS2 major for this profile (v41 | v42 | v43). Used by CLI/MCP to pick which version&#x27;s plugin tree to load; the wire client always auto-detects on connect.
* `--help`: Show this message and exit.

### `d2w profile remove`

Remove a profile. Without --global/--local, removes from whichever file holds it.

**Usage**:

```console
$ d2w profile remove [OPTIONS] NAME
```

**Arguments**:

* `NAME`: [required]

**Options**:

* `--global`: Remove from ~/.config/dhis2/profiles.toml specifically.
* `--local`: Remove from ./.dhis2/profiles.toml specifically.
* `--help`: Show this message and exit.

### `d2w profile rename`

Rename a profile in-place. Preserves scope and updates default if needed.

**Usage**:

```console
$ d2w profile rename [OPTIONS] OLD_NAME NEW_NAME
```

**Arguments**:

* `OLD_NAME`: Current profile name.  [required]
* `NEW_NAME`: New profile name (letters, digits, underscores).  [required]

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
$ d2w profile login [OPTIONS] [NAME]
```

**Arguments**:

* `[NAME]`: Profile name; omit to use the default.

**Options**:

* `--no-browser`: Print the DHIS2 authorization URL instead of launching the system browser. Useful over SSH, under Playwright, or when logging in via a different browser. Also accepts DHIS2_OAUTH_NO_BROWSER=1 as default.
* `--help`: Show this message and exit.

### `d2w profile logout`

Clear persisted OAuth2 tokens for a profile.

Removes the row from the scope-appropriate `tokens.sqlite`. Next API call
triggers a fresh `profile login` flow. OAuth2 profiles only.

**Usage**:

```console
$ d2w profile logout [OPTIONS] [NAME]
```

**Arguments**:

* `[NAME]`: Profile name; omit to use the default.

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
$ d2w profile bootstrap [OPTIONS] NAME
```

**Arguments**:

* `NAME`: Profile name to create.  [required]

**Options**:

* `--auth TEXT`: pat | oauth2 — which kind of profile to set up.  [default: oauth2]
* `--url TEXT`: DHIS2 base URL (also: DHIS2_URL env).
* `--admin-user TEXT`: Admin username (for basic bootstrap).
* `--client-id TEXT`: OAuth2 client_id to register (auth=oauth2).  [default: dhis2-utils-local]
* `--redirect-uri TEXT`: OAuth2 redirect URI.  [default: http://localhost:8765]
* `--scope TEXT`: OAuth2 scope.  [default: ALL]
* `--pat-description TEXT`: PAT description (auth=pat).
* `--pat-expires-in-days INTEGER`: PAT lifetime in days; omit for no expiry.
* `--global`: Save to ~/.config/dhis2/profiles.toml (default).
* `--local`: Save to ./.dhis2/profiles.toml instead.
* `--login / --no-login`: For auth=oauth2, run `profile login` after saving. Ignored for auth=pat.  [default: login]
* `--version TEXT`: Expected DHIS2 major for this profile (v41 | v42 | v43). Used by CLI/MCP to pick which version&#x27;s plugin tree to load; the wire client always auto-detects on connect.
* `--help`: Show this message and exit.

### `d2w profile oidc-config`

Populate an OAuth2 profile by discovering a DHIS2 instance&#x27;s OIDC endpoints.

Fetches `/.well-known/openid-configuration` from the given URL, validates the
response, and writes a profile with `auth=oauth2` + your client credentials.
Removes the &quot;hand-edit profiles.toml with the right issuer/auth/token URLs&quot;
step from the OAuth2 setup walkthrough.

The URL can be either the DHIS2 base URL (discovery path is appended
automatically) or the full discovery URL.

**Usage**:

```console
$ d2w profile oidc-config [OPTIONS] URL
```

**Arguments**:

* `URL`: DHIS2 base URL or full /.well-known/openid-configuration URL.  [required]

**Options**:

* `-n, --name TEXT`: Profile name to save as.  [required]
* `--client-id TEXT`: OAuth2 client_id (from your registration).  [required]
* `--client-secret TEXT`: OAuth2 client_secret.  [required]
* `--scope TEXT`: OAuth2 scope (DHIS2 only recognises `ALL`).  [default: ALL]
* `--redirect-uri TEXT`: OAuth2 redirect URI (match your registered client — default is the CLI&#x27;s loopback listener).  [default: http://localhost:8765]
* `--global`: Save to ~/.config/dhis2/profiles.toml (default, user-wide).
* `--local`: Save to ./.dhis2/profiles.toml instead (project-scoped).
* `--default`: Set as default after saving.
* `--login`: Trigger `d2w profile login &lt;name&gt;` immediately after saving.
* `--version TEXT`: Expected DHIS2 major for this profile (v41 | v42 | v43). Used by CLI/MCP to pick which version&#x27;s plugin tree to load; the wire client always auto-detects on connect.
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

* `--url TEXT`: DHIS2 base URL (also: DHIS2_URL env).
* `--admin-user TEXT`
* `--description TEXT`
* `--expires-in-days INTEGER`
* `--allowed-ip TEXT`: IP allowlist entry; repeat for multiple.
* `--allowed-method TEXT`: HTTP method allowlist; repeat for each method.
* `--allowed-referrer TEXT`: Referer allowlist entry; repeat for multiple.
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

* `--url TEXT`: DHIS2 base URL (also: DHIS2_URL env).
* `--admin-user TEXT`
* `--client-id TEXT`: [default: dhis2-utils-local]
* `--redirect-uri TEXT`: [default: http://localhost:8765]
* `--scope TEXT`: [default: ALL]
* `--name TEXT`
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
$ d2w query eval [OPTIONS] [TEXT]
```

**Arguments**:

* `[TEXT]`: A d2ql program (quote it); or read one with --file.

**Options**:

* `-f, --file PATH`: Read the d2ql program from this file.
* `-d, --define TEXT`: Run/explain this named definition.
* `-o, --out TEXT`: Write rows to this file (json/ndjson/csv).
* `--help`: Show this message and exit.

### `d2w query run`

Run a d2ql program read from a file.

**Usage**:

```console
$ d2w query run [OPTIONS] FILE
```

**Arguments**:

* `FILE`: Path to a .d2ql program file.  [required]

**Options**:

* `-d, --define TEXT`: Run/explain this named definition.
* `-o, --out TEXT`: Write rows to this file (json/ndjson/csv).
* `--help`: Show this message and exit.

### `d2w query explain`

Show how a d2ql pipeline (inline or `--file`) splits between DHIS2 pushdown and local evaluation.

**Usage**:

```console
$ d2w query explain [OPTIONS] [TEXT]
```

**Arguments**:

* `[TEXT]`: A d2ql program (quote it); or read one with --file.

**Options**:

* `-f, --file PATH`: Read the d2ql program from this file.
* `-d, --define TEXT`: Run/explain this named definition.
* `--help`: Show this message and exit.

### `d2w query ast`

Print the parsed d2ql AST (no profile needed; inline program or `--file`).

**Usage**:

```console
$ d2w query ast [OPTIONS] [TEXT]
```

**Arguments**:

* `[TEXT]`: A d2ql program (quote it); or read one with --file.

**Options**:

* `-f, --file PATH`: Read the d2ql program from this file.
* `--help`: Show this message and exit.

### `d2w query d2path`

Evaluate a bare d2path expression over a local JSON document (no profile needed).

**Usage**:

```console
$ d2w query d2path [OPTIONS] EXPRESSION
```

**Arguments**:

* `EXPRESSION`: A d2path expression (quote it).  [required]

**Options**:

* `-i, --input PATH`: JSON file to evaluate against.  [required]
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

* `--fields TEXT`: [default: id,code,name,url,disabled,auth]
* `--help`: Show this message and exit.

### `d2w route list`

List registered routes.

**Usage**:

```console
$ d2w route list [OPTIONS]
```

**Options**:

* `--fields TEXT`: [default: id,code,name,url,disabled,auth]
* `--help`: Show this message and exit.

### `d2w route get`

Fetch one route by UID or code.

**Usage**:

```console
$ d2w route get [OPTIONS] ROUTE
```

**Arguments**:

* `ROUTE`: Route UID (e.g. E8OPcc45A22) or code (e.g. chap).  [required]

**Options**:

* `--fields TEXT`
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

* `--file PATH`: JSON file with the route definition (bypass the interactive wizard).
* `--code TEXT`
* `--name TEXT`
* `--url TEXT`: Target URL the route proxies to.
* `--authorities TEXT`: Comma-separated DHIS2 authorities allowed to run this route.
* `--no-auth`: Create an unauthenticated route (skip the auth wizard) — for headless/bridge use.
* `--help`: Show this message and exit.

### `d2w route update`

Replace a route via PUT /api/routes/{uid}.

DHIS2 PUT expects the complete object. For partial updates use `patch`.

**Usage**:

```console
$ d2w route update [OPTIONS] ROUTE
```

**Arguments**:

* `ROUTE`: Route UID (e.g. E8OPcc45A22) or code (e.g. chap).  [required]

**Options**:

* `--file PATH`: JSON file with the full route spec (PUT semantics).  [required]
* `--help`: Show this message and exit.

### `d2w route patch`

Apply a JSON Patch to a route via PATCH /api/routes/{uid}.

**Usage**:

```console
$ d2w route patch [OPTIONS] ROUTE
```

**Arguments**:

* `ROUTE`: Route UID (e.g. E8OPcc45A22) or code (e.g. chap).  [required]

**Options**:

* `--file PATH`: JSON Patch array (RFC 6902).  [required]
* `--help`: Show this message and exit.

### `d2w route delete`

Delete a route.

**Usage**:

```console
$ d2w route delete [OPTIONS] ROUTE
```

**Arguments**:

* `ROUTE`: Route UID (e.g. E8OPcc45A22) or code (e.g. chap).  [required]

**Options**:

* `--help`: Show this message and exit.

### `d2w route run`

Execute a route — DHIS2 proxies the request to the configured target URL.

`route` accepts the route&#x27;s UID or its `code`. When the route&#x27;s target
URL ends in a wildcard (`/**`), `--path SEGMENT` is required: it is
what DHIS2 substitutes into the wildcard before calling upstream.

**Usage**:

```console
$ d2w route run [OPTIONS] ROUTE
```

**Arguments**:

* `ROUTE`: Route UID (e.g. E8OPcc45A22) or code (e.g. chap).  [required]

**Options**:

* `-X, --method TEXT`: [default: GET]
* `--body PATH`: JSON body file for POST/PUT.
* `--path TEXT`: Additional path segment appended to the route&#x27;s target URL.
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
$ d2w system calendar [OPTIONS] [VALUE]:[coptic|ethiopian|gregorian|islamic|iso8601|julian|nepali|persian|thai]
```

**Arguments**:

* `[VALUE]:[coptic|ethiopian|gregorian|islamic|iso8601|julian|nepali|persian|thai]`: When supplied, write `keyCalendar` (one of: coptic, ethiopian, gregorian, islamic, iso8601, julian, nepali, persian, thai). Omit to print the current calendar.

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
$ d2w system settings set [OPTIONS] KEY VALUE
```

**Arguments**:

* `KEY`: System setting key (e.g. applicationTitle, keyApplicationFooter).  [required]
* `VALUE`: New value.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w system settings set-many`

Bulk-set system settings from a JSON file.

**Usage**:

```console
$ d2w system settings set-many [OPTIONS] FILE
```

**Arguments**:

* `FILE`: JSON file containing a {key: value} object.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w system settings get`

Print one system setting&#x27;s value; exit 1 if it is unset.

**Usage**:

```console
$ d2w system settings get [OPTIONS] KEY
```

**Arguments**:

* `KEY`: System setting key (e.g. applicationTitle).  [required]

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

* `--fields TEXT`: DHIS2 field selector. Supports plain lists (&#x27;id,username,email&#x27;), presets (&#x27;:identifiable&#x27;, &#x27;:nameable&#x27;, &#x27;:owner&#x27;, &#x27;:all&#x27;), and exclusions (&#x27;:all,!password&#x27;).  [default: id,username,displayName,email,disabled,lastLogin]
* `--filter TEXT`: Filter &#x27;property:operator:value&#x27; (repeatable).
* `--root-junction TEXT`: Combine repeated --filter as AND (default) or OR.  [default: AND]
* `--order TEXT`: Sort clause &#x27;property:asc|desc&#x27; (repeatable).
* `--page INTEGER`: Server-side page number (1-based).
* `--page-size INTEGER`: Server-side page size (default 50).
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

* `--fields TEXT`: DHIS2 field selector. Supports plain lists (&#x27;id,username,email&#x27;), presets (&#x27;:identifiable&#x27;, &#x27;:nameable&#x27;, &#x27;:owner&#x27;, &#x27;:all&#x27;), and exclusions (&#x27;:all,!password&#x27;).  [default: id,username,displayName,email,disabled,lastLogin]
* `--filter TEXT`: Filter &#x27;property:operator:value&#x27; (repeatable).
* `--root-junction TEXT`: Combine repeated --filter as AND (default) or OR.  [default: AND]
* `--order TEXT`: Sort clause &#x27;property:asc|desc&#x27; (repeatable).
* `--page INTEGER`: Server-side page number (1-based).
* `--page-size INTEGER`: Server-side page size (default 50).
* `--help`: Show this message and exit.

### `d2w user get`

Fetch one user by UID or username. Prints a concise summary; `--json` for full payload.

**Usage**:

```console
$ d2w user get [OPTIONS] UID_OR_USERNAME
```

**Arguments**:

* `UID_OR_USERNAME`: User UID (11 chars) or username.  [required]

**Options**:

* `--fields TEXT`: DHIS2 field selector.
* `--help`: Show this message and exit.

### `d2w user invite`

Create a user and send the invitation email.

Hits POST /api/users/invite. DHIS2&#x27;s configured mailer sends the link;
the new user sets their password on accept. Prints the new user&#x27;s UID.

**Usage**:

```console
$ d2w user invite [OPTIONS] EMAIL
```

**Arguments**:

* `EMAIL`: Email address for the new user (receives the invitation link).  [required]

**Options**:

* `--first-name TEXT`: User&#x27;s given name.  [required]
* `--surname TEXT`: User&#x27;s surname.  [required]
* `--username TEXT`: Desired username. Omit to let DHIS2 derive from the email prefix.
* `--user-role TEXT`: User-role UID (repeatable). Grants the role on accept.
* `--org-unit, --ou TEXT`: Organisation-unit UID for capture scope (repeatable).
* `--help`: Show this message and exit.

### `d2w user reinvite`

Re-send the invitation email for a pending user (POST /api/users/{uid}/invite).

**Usage**:

```console
$ d2w user reinvite [OPTIONS] UID
```

**Arguments**:

* `UID`: UID of a user who hasn&#x27;t yet completed their invite.  [required]

**Options**:

* `--help`: Show this message and exit.

### `d2w user reset-password`

Trigger DHIS2&#x27;s password-reset email (POST /api/users/{uid}/reset).

**Usage**:

```console
$ d2w user reset-password [OPTIONS] UID
```

**Arguments**:

* `UID`: UID of the user to reset.  [required]

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

* `--fields TEXT`: DHIS2 field selector.  [default: id,name,displayName,users]
* `--filter TEXT`: Filter &#x27;property:operator:value&#x27; (repeatable).
* `--order TEXT`: Sort clause &#x27;property:asc|desc&#x27; (repeatable).
* `--page-size INTEGER`: Server-side page size.
* `--help`: Show this message and exit.

#### `d2w user group list`

List user groups.

**Usage**:

```console
$ d2w user group list [OPTIONS]
```

**Options**:

* `--fields TEXT`: DHIS2 field selector.  [default: id,name,displayName,users]
* `--filter TEXT`: Filter &#x27;property:operator:value&#x27; (repeatable).
* `--order TEXT`: Sort clause &#x27;property:asc|desc&#x27; (repeatable).
* `--page-size INTEGER`: Server-side page size.
* `--help`: Show this message and exit.

#### `d2w user group get`

Fetch one user group by UID. Prints a concise summary; `--json` for full payload.

**Usage**:

```console
$ d2w user group get [OPTIONS] UID
```

**Arguments**:

* `UID`: User-group UID.  [required]

**Options**:

* `--fields TEXT`: DHIS2 field selector.
* `--help`: Show this message and exit.

#### `d2w user group create`

Create a user group (then add members with `add-member`).

**Usage**:

```console
$ d2w user group create [OPTIONS]
```

**Options**:

* `--name TEXT`: User-group name.  [required]
* `--code TEXT`: Business code.
* `--uid TEXT`: Explicit 11-char UID.
* `--help`: Show this message and exit.

#### `d2w user group delete`

Delete a user group by UID.

**Usage**:

```console
$ d2w user group delete [OPTIONS] UID
```

**Arguments**:

* `UID`: User-group UID.  [required]

**Options**:

* `-y, --yes`: Skip the confirmation prompt.
* `--help`: Show this message and exit.

#### `d2w user group add-member`

Add a user to a group (POST /api/userGroups/&lt;gid&gt;/users/&lt;uid&gt;).

**Usage**:

```console
$ d2w user group add-member [OPTIONS] GROUP_UID USER_UID
```

**Arguments**:

* `GROUP_UID`: User-group UID.  [required]
* `USER_UID`: User UID to add.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w user group remove-member`

Remove a user from a group (DELETE /api/userGroups/&lt;gid&gt;/users/&lt;uid&gt;).

**Usage**:

```console
$ d2w user group remove-member [OPTIONS] GROUP_UID USER_UID
```

**Arguments**:

* `GROUP_UID`: User-group UID.  [required]
* `USER_UID`: User UID to remove.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w user group sharing-get`

Print the current sharing block for one user group. `--json` for full payload.

**Usage**:

```console
$ d2w user group sharing-get [OPTIONS] UID
```

**Arguments**:

* `UID`: User-group UID.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w user group sharing-grant-user`

Grant one user access to a group (shortcut over `/api/sharing`).

Preserves existing userAccesses/userGroupAccesses by fetching the current
sharing block first, then appending the new grant.

**Usage**:

```console
$ d2w user group sharing-grant-user [OPTIONS] GROUP_UID USER_UID
```

**Arguments**:

* `GROUP_UID`: User-group UID.  [required]
* `USER_UID`: User UID to grant.  [required]

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

* `--fields TEXT`: DHIS2 field selector.  [default: id,name,displayName,authorities,users]
* `--filter TEXT`: Filter (repeatable).
* `--order TEXT`: Sort clause (repeatable).
* `--page-size INTEGER`: Server-side page size.
* `--help`: Show this message and exit.

#### `d2w user role list`

List user roles.

**Usage**:

```console
$ d2w user role list [OPTIONS]
```

**Options**:

* `--fields TEXT`: DHIS2 field selector.  [default: id,name,displayName,authorities,users]
* `--filter TEXT`: Filter (repeatable).
* `--order TEXT`: Sort clause (repeatable).
* `--page-size INTEGER`: Server-side page size.
* `--help`: Show this message and exit.

#### `d2w user role get`

Fetch one user role by UID. Prints a concise summary; `--json` for full payload.

**Usage**:

```console
$ d2w user role get [OPTIONS] UID
```

**Arguments**:

* `UID`: User-role UID.  [required]

**Options**:

* `--fields TEXT`: DHIS2 field selector.
* `--help`: Show this message and exit.

#### `d2w user role authority-list`

Print the sorted authorities carried by one role, one per line.

**Usage**:

```console
$ d2w user role authority-list [OPTIONS] UID
```

**Arguments**:

* `UID`: User-role UID.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w user role add-user`

Grant a user a role (POST /api/userRoles/&lt;rid&gt;/users/&lt;uid&gt;).

**Usage**:

```console
$ d2w user role add-user [OPTIONS] ROLE_UID USER_UID
```

**Arguments**:

* `ROLE_UID`: User-role UID.  [required]
* `USER_UID`: User UID to grant the role to.  [required]

**Options**:

* `--help`: Show this message and exit.

#### `d2w user role remove-user`

Revoke a role from a user (DELETE /api/userRoles/&lt;rid&gt;/users/&lt;uid&gt;).

**Usage**:

```console
$ d2w user role remove-user [OPTIONS] ROLE_UID USER_UID
```

**Arguments**:

* `ROLE_UID`: User-role UID.  [required]
* `USER_UID`: User UID to revoke the role from.  [required]

**Options**:

* `--help`: Show this message and exit.
