# Data store — key/value accessor

Typed helper over DHIS2's namespaced key/value stores. Accessed via `Dhis2Client.datastore`.

DHIS2 has two stores with the same shape:

- `/api/dataStore` — the instance/app store (shared, sharing-controlled). The default.
- `/api/userDataStore` — the per-user store. Reach it by passing `user=True` to any method.

(There is no `/api/systemDataStore`; instance-wide system config is `systemSettings`, exposed by
`d2w system settings`.)

Stored values are arbitrary user JSON — object, array, or scalar — so `get` returns `Any` and
`set` accepts `Any`. `set` is create-or-update: DHIS2 splits create (POST) from update (PUT), so
the accessor checks existence first and dispatches accordingly.

See also:
- CLI + MCP surface: `d2w datastore` (namespaces / keys / get / set / delete) and the
  `datastore_*` tools.

::: dhis2w_client.v42.datastore
