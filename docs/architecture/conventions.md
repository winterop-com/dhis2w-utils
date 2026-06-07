# Naming conventions

This page documents the verb vocabulary used across CLI commands, MCP tools, and service-layer methods. The rules here are descriptive of what's already in the tree — not aspirational. New plugins should pick from this verb set; deviating needs a real reason.

## Top-line rule

**The verb describes the wire shape DHIS2 expects, not the user's intent.** A `create` is a POST that mints a new uid; an `add` attaches an existing thing to a parent's collection; a `set` writes a singleton value. The verb tells you which DHIS2 endpoint shape you are seeing.

## Tool / command naming

- **MCP tool functions**: `<plugin>_<resource>_<verb>` in snake_case, verb-last. Examples: `metadata_data_element_create`, `user_role_authority_list`, `system_calendar_get`.
- **CLI sub-commands**: `dhis2 <plugin> <resource> <verb>` with hyphens for word boundaries. Examples: `dhis2 metadata data-element create`, `dhis2 user-role authority-list`, `dhis2 system calendar`.
- **Service methods** (in `service.py`): verb-first is fine because the module name is the namespace — `service.create_data_element()`, `service.set_calendar()`. The verb-last rule applies only to the MCP-tool function name where there is no surrounding object.
- **Client accessors** (`client.<resource>.<verb>()`): same as services. `client.data_elements.create()`, `client.system.set_calendar()`.

There is no canonical convention in the MCP spec — what you see in the wild correlates with the server's implementation language. Python servers (FastMCP-based, like ours; Playwright; the Anthropic reference servers) use snake_case verb-last because Python function names already are. TypeScript servers (Atlassian's Jira: `getJiraIssue`, `searchJiraIssuesUsingJql`) use camelCase verb-first. We chose snake_case verb-last because it falls out of FastMCP+Python and clusters tools by resource when sorted alphabetically.

## The verb table

| Verb suffix | Use it for | Example | DHIS2 endpoint shape |
|---|---|---|---|
| `_list` | Many of a type | `metadata_indicator_list` | `GET /api/<resource>` |
| `_get` | One by uid | `metadata_indicator_get`, `route_get`, `user_get` | `GET /api/<resource>/{uid}` |
| `_create` | POST a brand-new top-level resource | `metadata_data_element_create` | `POST /api/<resource>` |
| `_delete` | DELETE a top-level resource | `metadata_data_element_delete` | `DELETE /api/<resource>/{uid}` |
| `_rename` | Patch only the `name` field | `metadata_indicator_rename` | `PATCH /api/<resource>/{uid}` (name only) |
| `_update` | PUT the whole resource | `route_update` | `PUT /api/<resource>/{uid}` |
| `_patch` | JSON-patch operations | `route_patch`, `metadata_patch` | `PATCH /api/<resource>/{uid}` |
| `_set` | Write a singleton value (no separate "create") | `system_calendar_set`, `apps_hub_url_set` | `POST /api/systemSettings/<key>`, etc. |
| `_add_<thing>` | Attach an existing thing to a parent collection | `user_group_add_member` | `POST /api/<parent>/{uid}/<collection>/<thing-uid>` |
| `_remove_<thing>` | Detach a thing from a parent collection | `user_group_remove_member` | `DELETE /api/<parent>/{uid}/<collection>/<thing-uid>` |

## The hot pairs

### `add` vs `create`

- **`_create`** mints a brand-new resource. DHIS2 generates a uid. You provide the full payload. Top-level CRUD on `/api/<resource>`.
- **`_add_<thing>`** attaches an existing object (already has its own uid) to a parent's collection. Nothing new is born — a relationship is recorded. Endpoint shape: `POST /api/<parent>/{uid}/<collection>/<thing-uid>` or a PATCH that mutates the collection field.

A bare `_add` MCP tool (no `_<thing>` suffix) is reserved for never. Always either `_create` (mints a resource) or `_add_<thing>` (attaches existing).

### `remove` vs `delete`

Mirror image of add/create:

- **`_delete`** destroys the resource itself. The uid stops resolving.
- **`_remove_<thing>`** detaches from a collection. Both parent and thing still exist; the relationship goes away.

The 22 `_add_<thing>` tools have 22 matching `_remove_<thing>` tools — perfect symmetry across `metadata_*_group_*`, `user_group_*_member`, `metadata_data_set_*_element`, `metadata_program_*_attribute`, etc.

The CLI exposes `rm` as a hidden alias for `delete` on most resources (`dhis2 metadata data-element delete` and `dhis2 metadata data-element rm` are the same).

### `get` vs `show` vs `list`

- **`_list`** returns many of a type. No uid in the path; returns an array.
- **`_get`** reads one by uid. Used everywhere — metadata plugin (`metadata_indicator_get`), non-metadata plugins (`route_get`, `user_get`), and the generic top-level `metadata_get` escape hatch.
- **`_show`** is not a CRUD verb. Two surviving occurrences (`customize_show`, `profile_show`) are no-uid readers that summarise the current state of a singleton — `customize_show` returns `/api/loginConfig`, `profile_show` displays a profile entry — and `_get` would read oddly without a uid argument.
- **`_read`** is not a CRUD verb either. The only occurrence is `messaging_mark_read`, where "read" is a message state, not a CRUD operation.

### `set` vs `update` vs `patch` vs `rename`

Four shapes for "modify an existing thing":

- **`_set`** is an idempotent write of a singleton value. The resource has no uid (or the uid is implicit / part of the URL). Examples: `system_calendar_set` (one slot in `keyCalendar`), `apps_hub_url_set` (one config knob), `system_settings_set` (one system setting), `data_aggregate_set` (one data value at a fixed coordinate), `metadata_attribute_set` (one attribute value on a resource).
- **`_update`** is a PUT of the whole resource. Replace-style. Used by `route_update` because routes are small enough to round-trip the full payload.
- **`_patch`** is JSON-patch operations on a resource — partial, surgical. `route_patch`, `metadata_patch`.
- **`_rename`** is sugar over `_patch` for the common case of changing only `name`. 16 tools, all in the metadata plugin.

**Rule of thumb:** no uid (config / singleton) → `_set`. Has a uid and you're sending the whole shape → `_update`. Has a uid and you're surgically changing fields → `_patch` (or `_rename` for the name-only case).

## Defensible deviations

A few tools deliberately do not follow the verb table. They are listed here so future readers do not "fix" them:

- `customize_apply`, `metadata_option_set_sync` — one-shot operations whose verb is the entire point.
- `data_aggregate_push`, `data_tracker_push` — DHIS2-vernacular term for bulk write to `/api/dataValueSets` and `/api/tracker`. `_create_many` would be technically correct but `push` is what every DHIS2 doc and SDK uses.
- `messaging_send`, `messaging_reply`, `messaging_assign`, `messaging_unassign` — domain verbs that map to specific DHIS2 message-conversation endpoints.
- `analytics_query`, `analytics_events_query`, `analytics_outlier_detection`, `route_run` — read-shaped POSTs. `query` and `run` describe what the call is, not the HTTP verb.
- `system_info`, `system_whoami`, `whoami` — DHIS2 endpoint vernacular (`/api/system/info`, `/api/me`). `system_info_get` would be technically more consistent, but no DHIS2 reader would call it that.

## Plurality

Resource names use the singular form of the DHIS2 path: `/api/dataElements` → `metadata_data_element_*`, `client.data_elements`. The collection method is plural on the client (`client.data_elements.list()`) because it operates on the collection; the per-instance methods are singular semantically but the accessor is the collection (`client.data_elements.get(uid)`). MCP tool names always use the singular resource (`metadata_data_element_list`, not `metadata_data_elements_list`) — the `_list` suffix already expresses plurality.

## Where this is enforced

Nowhere automatically. There is no linter check; new tools are reviewed by hand. The `make docs-mcp` target (which regenerates `docs/mcp-reference.md`) sorts every tool alphabetically and groups by plugin — that is the easiest place to spot a new tool that breaks the pattern.
