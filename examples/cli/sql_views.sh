#!/usr/bin/env bash
# `d2w metadata sql-views ...` — SQL view execution workflows.
#
# DHIS2 SQL views are saved queries exposed via `/api/sqlViews`. Three flavours:
# - VIEW — a standard Postgres view, materialised in the DB on first execute.
# - MATERIALIZED_VIEW — persisted result set, refreshable on demand.
# - QUERY — SQL executed ad-hoc with optional `${var}` substitutions.
#
# The workspace seed ships three such views so every command here has a target:
# - OU per level (VIEW, UID SqvOuLvl001)
# - DE by name pattern (QUERY, UID SqvDeByNm01)
# - DE counts per value type (MATERIALIZED_VIEW, UID SqvDeVtMV01)
set -euo pipefail

OU_LEVEL_VIEW=SqvOuLvl001
DE_BY_NAME_QUERY=SqvDeByNm01
DE_VALUETYPE_MV=SqvDeVtMV01

# --- Catalog ----------------------------------------------------------------
# Every view, grouped by type. Pipe `--type QUERY` to list only dynamic ones.

d2w metadata list sqlViews
d2w metadata list sqlViews --filter type:eq:QUERY

# --- Inspect ----------------------------------------------------------------
# Show the SQL body for a saved view — handy before executing something new.

d2w metadata sql-views get "$OU_LEVEL_VIEW"
d2w --json metadata sql-views get "$DE_BY_NAME_QUERY" | jq '.sqlQuery'

# --- Execute ----------------------------------------------------------------
# Table rendering (default) for terminal use.

d2w metadata sql-views execute "$OU_LEVEL_VIEW"

# JSON output for piping into jq / downstream scripts.

d2w metadata sql-views execute "$OU_LEVEL_VIEW" --format json | jq '.'

# CSV output for pasting into a spreadsheet.

d2w metadata sql-views execute "$OU_LEVEL_VIEW" --format csv

# QUERY views accept `${var}` substitutions via repeated `--var name:value`.
# DHIS2 sanitises values server-side to alphanumerics only — wildcards go in
# the SQL template, not the variable.

d2w metadata sql-views execute "$DE_BY_NAME_QUERY" --var pattern:anc

# VIEW / MATERIALIZED_VIEW executions filter by column with `--criteria`.
# (The seeded VIEW has no criteria use case; this line illustrates the flag.)

d2w metadata sql-views execute "$OU_LEVEL_VIEW" --criteria level:3

# --- Refresh ----------------------------------------------------------------
# MATERIALIZED_VIEW types re-run the underlying SQL; plain VIEW types are no-ops
# once the DB view exists. The seeded MV refresh is instant on a fresh dump.

d2w metadata sql-views refresh "$DE_VALUETYPE_MV"

# --- Ad-hoc iteration -------------------------------------------------------
# `adhoc` registers a throwaway SqlView from a .sql file, runs it once, and
# deletes it afterwards. Use `--keep` to leave the view in place for UI review.

cat >/tmp/probe_ou_count.sql <<'SQL'
SELECT hierarchylevel AS "level",
       COUNT(*)       AS "count"
FROM organisationunit
GROUP BY hierarchylevel
ORDER BY hierarchylevel DESC
SQL

d2w metadata sql-views adhoc "OU level count desc" /tmp/probe_ou_count.sql --format table

# Parametrised ad-hoc: pass `${...}` substitutions with repeated --var.
cat >/tmp/probe_de_search.sql <<'SQL'
SELECT name, valuetype
FROM dataelement
WHERE LOWER(name) LIKE LOWER('%${query}%')
ORDER BY name
SQL

d2w metadata sql-views adhoc "DE search" /tmp/probe_de_search.sql --var query:visit

rm -f /tmp/probe_ou_count.sql /tmp/probe_de_search.sql

# --- Generic surface (for CRUD) ---------------------------------------------
# `get / execute / refresh / adhoc` layer on top of the generic metadata
# endpoints. Raw CRUD stays on `d2w metadata list / get sqlViews`.

d2w metadata list sqlViews --fields 'id,name,type'
