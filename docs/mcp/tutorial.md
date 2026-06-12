# MCP tutorial

A walk through driving `dhis2w-mcp` from an LLM agent — from "the server isn't loaded" to a real end-to-end DHIS2 workflow with one controlled mutation and a rollback. Assumes you've installed the server per the [overview](index.md) and wired it into your MCP host.

This covers the **full server** (typed tools). The single-tool **bridge** for local models is driven differently (the model calls `dhis2_cli([...])` and discovers commands via `--help`) — see its [usage guide](bridge.md).

Each step shows what you ask the agent, which tool it should invoke, the shape of the response you should see, and how to recover when something goes wrong.

## 1. Confirm the server is loaded

In Claude Desktop / Claude Code / Cursor, ask the agent:

> List the MCP tools you have for DHIS2.

Expect: a count plus a sampled list grouped by plugin (analytics, apps, customize, data, doctor, files, maintenance, messaging, metadata, profile, route, system, user — roughly 304 tools total).

**Recovery — "zero tools":**

- The host hasn't loaded the server. Reload the MCP panel (Claude Desktop: quit + reopen; Claude Code: `/mcp`).
- Check the host's MCP log for a startup error — usually "command not found" (binary not on `PATH`) or a Python import failure (uv environment broken).
- Run `dhis2w-mcp --version` yourself in a terminal. If that works but the host can't launch it, the host's `command:` path is wrong.

## 2. Smoke-test the server without touching DHIS2

> Call `system_server_info` and show me the result.

The tool takes no arguments. Expected response (your version numbers will differ):

```json
{
  "active_plugin_tree": "v43",
  "active_plugin_tree_source": "DHIS2_VERSION='43' env",
  "dhis2w_core_version": "0.10.0",
  "dhis2w_mcp_version": "0.10.0",
  "dhis2w_cli_version": null
}
```

This is a process-local introspection — no DHIS2 client is opened, no auth required. Use it to confirm which plugin tree the server bound + which versions are installed. Always run this first when you're not sure where the server is pointed.

## 3. Touch DHIS2 — the auth smoke test

> Call `system_whoami` to check who the active profile is logged in as.

Expected response: a typed `Me` model with the agent's perspective on the DHIS2 user (username, displayName, authorities, OU scopes, group memberships).

**Recovery — auth error:**

The agent gets a typed `Dhis2ApiError` envelope. The interesting fields:

- `status_code`: `401` (bad credentials), `403` (good auth, wrong permission), `404` (wrong base URL — usually).
- `message`: human-readable line from DHIS2.
- `conflicts`: per-row error list (only on writes — empty on `whoami`).

The same envelope shape comes back from every tool, so an agent learns it once.

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| 401 with "User account is locked" | Account disabled in DHIS2 | Have an admin unlock; or use a different profile |
| 401 with "Bad credentials" | PAT expired / password rotated | Re-run `d2w profile add NAME --auth pat` to update |
| 403 on every tool | Profile has zero DHIS2 authorities | Profile is using the wrong user — `d2w profile verify` to confirm |
| `NoProfileError: no DHIS2 profile is configured` | Server started before any profile was saved | Run `d2w profile add NAME --url ... --auth pat --default` once; restart the MCP host |
| `UnknownProfileError` from a `profile=...` call | Profile name doesn't exist in TOML | `d2w profile list` to see real names |

## 4. A real read-only workflow

Suppose you want the agent to find "how many WITH_REGISTRATION programs the active DHIS2 has, and which org units the first one is scoped to":

> Use `metadata_program_list` with `program_type="WITH_REGISTRATION"` and `page_size=1`, then take the first result's `id` and call `metadata_program_get` with `fields="id,name,organisationUnits[id,displayName]"`.

What the agent should do (and what you should see in the MCP host's tool-call log):

1. **Tool**: `metadata_program_list`
   **Args**: `{"program_type": "WITH_REGISTRATION", "page_size": 1}`
   **Response shape**: `list[Program]` — one element on success.

2. **Tool**: `metadata_program_get`
   **Args**: `{"uid": "<id from step 1>", "fields": "id,name,organisationUnits[id,displayName]"}`
   **Response shape**: a typed `Program` with `.organisationUnits` populated as a list of references.

The agent narrates the result in prose; you can inspect the raw payloads via the MCP host's log if something looks off.

## 5. Targeting a different profile per call

The agent's default profile comes from `DHIS2_PROFILE` (set on the server's `env:` block) or the project / global TOML default. Override per call:

> Same lookup, but on staging: pass `profile="staging"` to both tools.

Every MCP tool accepts an optional `profile: str | None` kwarg. One running MCP server can target multiple DHIS2 stacks (local + staging + a play instance) without restart. `d2w profile list` shows what's available.

## 6. A controlled mutation + rollback

Read-only is safe; the first write is where you want to see the agent narrate before it acts.

> Pick any DataElement on the active DHIS2 (`metadata_data_element_list` with `page_size=5`). Show me its current `name`, then `metadata_data_element_rename` it to append " (test)". Wait for me to confirm before reverting.

Sequence:

1. **Tool**: `metadata_data_element_list`
   **Args**: `{"page_size": 5, "fields": "id,name,shortName"}`
   **Response**: a list of `DataElement` models — note the first row's `id` and `name` so you can revert.

2. **Tool**: `metadata_data_element_rename`
   **Args**: `{"uid": "<de-id>", "name": "<original> (test)"}`
   **Response**: the updated `DataElement` model with the new name.

3. **Verify**: have the agent call `metadata_data_element_get` on the same uid and confirm the rename landed.

4. **Rollback**: `metadata_data_element_rename` again with `{"uid": "<de-id>", "name": "<original>"}`.

The rename verb is implemented for most metadata-authoring resources (DataElement, Indicator, Program, Category, CategoryCombo, OrganisationUnitLevel, …); `metadata_<resource>_rename` is the safest "minimal mutation" surface for trying out an agent's write path. Resources without a dedicated `rename` (e.g. plain OrganisationUnit) need a fuller `update` or `patch` call instead.

**Recovery — write failure:**

DHIS2 returns a `WebMessageResponse` with `status="WARNING"` or `"ERROR"`. The agent sees a `Dhis2ApiError` whose `.conflicts` list contains per-field rejection reasons (e.g. `"name must be unique"`). Read the conflict, fix the args, retry — `rename` is idempotent on (uid, new_name), so retrying with the same args is safe.

If the agent can't reach DHIS2 mid-flow (network timeout), the first call may have succeeded — the verify step will show the rename did land. Always run the verify step before deciding to retry.

## 7. Version-sensitive tools

Some tools only register when the active plugin tree matches the DHIS2 server. The v43-only setters are the largest cluster:

- `metadata_program_set_labels(uid, enrollments_label, events_label, program_stages_label)`
- `metadata_program_set_change_log_enabled(uid, enabled)`
- `metadata_program_set_enrollment_category_combo(uid, category_combo_uid)`

These are absent from the tool list on a v42-bound server. If the agent says "I don't see a `metadata_program_set_labels` tool", call `system_server_info` to confirm the active plugin tree, then either point the server at a v43 DHIS2 (with `DHIS2_VERSION=43` in the host's `env:` block) or use the v42 alternatives.

## 8. Watching long-running jobs

DHIS2 has several async endpoints (analytics refresh, metadata import, predictor runs, data-integrity scans). The MCP tools that kick those off return a `TaskRef` immediately; the agent should poll for completion before declaring success:

> Run `maintenance_refresh_analytics`, then poll `maintenance_task_status` every 5 seconds until it reports `COMPLETED` or `FAILED`. Tell me the elapsed time.

The poll body shape: `{"job_type": "ANALYTICS_TABLE", "job_id": "<id from refresh response>"}`. Returns the latest `TaskCompletion` snapshot — status + per-stage notification list.

If the agent doesn't poll, it'll report "refresh started" but the analytics tables won't actually be ready yet — subsequent queries will hit stale data.

## Where next

- [Reference](../mcp-reference.md) — every tool with its parameter schema + description.
- [Architecture](../architecture/mcp.md) — return-shape conventions, error handling, profile resolution.
- [Examples](../examples.md) — Python scripts that drive the in-process MCP server end-to-end (useful for snapshot-testing agent flows). Each `examples/v{N}/mcp/*.py` invokes a real tool sequence — copy one as a template for your own scripted agent flow.
