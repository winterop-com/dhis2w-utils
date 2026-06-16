# Apps

`AppsAccessor` on `Dhis2Client.apps` — install / uninstall / update DHIS2 apps via `/api/apps` and the configured App Hub (`/api/appHub`). The `App` model is generated from the OpenAPI schema; `AppHubApp` + `AppHubVersion` are thin wrappers with `extra="allow"` over the hub's proxied JSON, so new hub fields ride through without a codegen bump.

Typical flow:

1. `client.apps.list_apps()` — enumerate installed apps.
2. `client.apps.hub_list()` — enumerate App Hub catalog.
3. `client.apps.install_from_hub(version_id)` or `install_from_file(path)` to install.
4. `client.apps.uninstall(key)` to remove.

`install_from_hub(version_id)` takes a *version* id; App Hub app ids and version ids are both bare UUIDs and easy to confuse (handing the endpoint an app id 404s — BUGS.md #46). The client method itself only accepts a version id; the `d2w apps add` CLI verb and `apps_install_from_hub` MCP tool additionally accept an app id and resolve it to the app's latest version (`dhis2w_core.v42.plugins.apps.service.install_from_hub`).

For update orchestration (compare installed version to hub latest, install newer), see `dhis2w_core.v42.plugins.apps.service.update_all` — also exposed as the `d2w apps update --all` CLI verb with a `--dry-run` preview mode.

::: dhis2w_client.v42.apps
