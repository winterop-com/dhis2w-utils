#!/usr/bin/env bash
# `d2w dev sample ...` — inject known-good fixtures and verify end-to-end.
#
# Each sub-command walks a full lifecycle (create -> verify -> clean up) so a
# fresh DHIS2 install can be smoke-tested in one pass. Useful after:
#   - spinning up a new stack (`make dhis2-run`)
#   - rolling a config change (e.g. route.remote_servers_allowed)
#   - applying a DHIS2 version upgrade
#
# Each step prints structured PASS/FAIL lines with timings.
set -euo pipefail

export DHIS2_ADMIN_PASSWORD="${DHIS2_ADMIN_PASSWORD:-district}"
export DHIS2_URL="${DHIS2_URL:-http://localhost:8080}"

# Exercise the /api/routes integration API (create -> run -> delete).
# Proxies to httpbin.org by default; pass --url to target something else.
# Skipped here because the outbound request to httpbin.org makes this
# flaky in offline / sandboxed environments — run it manually when you
# want to exercise the route lifecycle.
# d2w dev sample route

# Write a data value, read it back, soft-delete. Uses the seeded Sierra
# Leone play42 fixture by default:
#   - DE  bvoJ1MGZKQv ("Example indicator", INTEGER_ZERO_OR_POSITIVE)
#   - OU  Rp268JB6Ne4 (Adonkia CHP, facility level)
#   - Pe  202406 (within the 2024 data window)
d2w dev sample data-value

# Create a fresh PAT, call /api/me with it, delete it.
d2w dev sample pat --admin-user admin

# Create a throwaway OAuth2 client, verify it persists via GET, delete it.
d2w dev sample oauth2-client --admin-user admin

# Or: run everything in one go.
# d2w dev sample all --admin-user admin

# Add `--keep` to leave a fixture behind for manual inspection:
# d2w dev sample route --keep
# d2w route list      # shows SMOKE_ROUTE until you delete it
