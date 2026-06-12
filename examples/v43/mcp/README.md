# MCP examples

Examples that connect to the `d2w` FastMCP server in-process and call its tools. Useful both as a reference for integrating the MCP server into an agent framework and as a quick sanity-check of what tools each plugin registers.

> **Canonical catalogue**: [`docs/examples.md`](../../../docs/examples.md) — curated v42 example index — headline examples per topic across CLI / client / MCP with links to the concept docs that explain each one.

Every example uses FastMCP's in-process `Client(server)` — no stdio transport, no subprocess. Same pattern used by `packages/dhis2w-mcp/tests/*_integration.py`.

## Prerequisites

```bash
make dhis2-run                       # DHIS2 + seeded auth
set -a; source infra/home/credentials/.env.auth; set +a
```

The MCP tools read the same `DHIS2_URL` / `DHIS2_PAT` / `DHIS2_PROFILE` env contract as the CLI.

## Scripts

| File | MCP tools exercised |
|------|---------------------|
| `whoami.py` | `system_whoami`, `system_info` |
| `profile_tools.py` | `profile_list`, `profile_verify`, `profile_show` |
| `metadata.py` | `metadata_type_list`, `metadata_list`, `metadata_get` |
| `metadata_search.py` | `metadata_search` — cross-resource UID / code / name lookup |
| `metadata_usage.py` | `metadata_program_rule_where_de_is_used`, attribute-value reverse lookup |
| `metadata_diff.py` | `metadata_diff`, `metadata_diff_profiles` |
| `metadata_export_import.py` | `metadata_export`, `metadata_import` |
| `metadata_patch.py` | `metadata_patch` (RFC 6902) |
| `analytics_query.py` | `analytics_query` |
| `analytics_outlier_tracked_entities.py` | `analytics_outlier_detection` + tracked-entity analytics |
| `maintenance.py` | `maintenance_task_*`, `maintenance_dataintegrity_*`, `maintenance_cache_clear` |
| `aggregate_data_values.py` | `data_aggregate_get / set / delete` |
| `tracker_reads.py` | `data_tracker_type_list / list / event_list / enrollment_list` |
| `tracker_workflow.py` | `data_tracker_register`, `data_tracker_enroll`, `data_tracker_event_create`, `data_tracker_outstanding` |
| `route_register_and_run.py` | `route_list / add / run / delete` |
| `user_administration.py` | `user_list / get / me / invite / reinvite / reset-password` |
| `user_groups.py` | `user_group_list`, `user_group_sharing_get` |
| `user_roles.py` | `user_role_list`, `user_role_authority_list` |
| `user_role.py` | `user_role_*` (legacy duplicate of `user_roles.py`; both ship until consolidated) |
| `apps.py` | `apps_list`, `apps_hub_list` (+ `apps_install_from_file / install_from_hub / uninstall / update / update_all / hub_url_{get,set}`) |
| `customize_login.py` | `customize_*` — branding + login-page settings |
| `doctor.py` | `doctor_run`, `doctor_bugs`, `doctor_integrity`, `doctor_metadata` |
