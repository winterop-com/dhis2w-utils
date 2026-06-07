# SQL views

`SqlViewsAccessor` on `Dhis2Client.sql_views` covers the workflow surface over `/api/sqlViews` — `list_all`, `get`, `execute`, `refresh`, `create`, `delete`. `SqlViewRunner` (also reachable as `client.sql_views.runner`) is a thin facade for iterative SQL debugging: `run(uid, **vars)` for saved views, `adhoc(name, sql, **vars)` for throwaway register-execute-delete flows.

`SqlViewResult` is the typed parser over DHIS2's `listGrid` response: `columns` names the headers, `rows` keeps them as positional `list[list[Any]]` (SQL column shape is inherently dynamic), `.as_dicts()` pivots into name-keyed dicts for ad-hoc inspection, `.column_values(name)` projects a single column.

DHIS2 quirks worth remembering:

- Variable and criteria values are sanitised to alphanumeric characters only — wildcards live in the SQL template (`'%${q}%'`), not the variable value.
- `VIEW` and `MATERIALIZED_VIEW` creation is lazy: the DB object doesn't exist until the first `POST /execute`. Call `refresh()` right after `create()` when a caller plans to read `/data` immediately afterwards.
- The DHIS2 SQL allowlist blocks `DELETE` / `UPDATE` / `INSERT` / `DROP` / etc. For fully free-form queries, connect to Postgres directly.

::: dhis2w_client.v42.sql_views
