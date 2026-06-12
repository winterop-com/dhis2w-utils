# Apps

`AppsAccessor` on `Dhis2Client.apps` — install / uninstall / update DHIS2 apps via `/api/apps` and the configured App Hub (`/api/appHub`). The `App` model is generated from the OpenAPI schema; `AppHubApp` + `AppHubVersion` are thin wrappers with `extra="allow"` over the hub's proxied JSON, so new hub fields ride through without a codegen bump.

Typical flow:

1. `client.apps.list_apps()` — enumerate installed apps.
2. `client.apps.hub_list()` — enumerate App Hub catalog.
3. `client.apps.install_from_hub(version_id)` or `install_from_file(path)` to install.
4. `client.apps.uninstall(key)` to remove.

For update orchestration (compare installed version to hub latest, install newer), see `dhis2w_core.v42.plugins.apps.service.update_all` — also exposed as the `d2w apps update --all` CLI verb with a `--dry-run` preview mode.

::: dhis2w_client.v42.apps
