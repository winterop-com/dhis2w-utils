# Manual testing guide — every CLI + MCP surface in one pass

Purpose: a copy-pasteable sequence that exercises every `d2w` CLI command and every MCP tool against a live stack. Use this when you want to sanity-check the surface after a refactor, or to track down a regression.

Assumes:
- `make dhis2-run` is up and `admin/district` works.
- You've run `make dhis2-seed` at least once so `infra/home/credentials/.env.auth` is populated.
- `uv sync --all-packages` has been run so `d2w` is on `$PATH` (inside `.venv/bin`).

Secrets never go on argv. Every command that needs a PAT, password, or client secret reads from env vars or prompts. Load the seeded credentials into your shell once:

```bash
set -a; source infra/home/credentials/.env.auth; set +a
```

That defines the end-user credentials (`DHIS2_PAT`, `DHIS2_PASSWORD`) plus the OAuth2 client config (`DHIS2_OAUTH_CLIENT_ID`, `DHIS2_OAUTH_CLIENT_SECRET`, `DHIS2_OAUTH_REDIRECT_URI`, `DHIS2_OAUTH_SCOPES`). Admin bootstrap commands (`profile bootstrap`, `profile pat create`, `profile oauth2 client register`, `dev sample *`) read `DHIS2_ADMIN_PAT` / `DHIS2_ADMIN_PASSWORD` — those are NOT in `.env.auth`. For local testing the easiest path is:

```bash
export DHIS2_ADMIN_PASSWORD=district   # matches the seeded admin/district user
```

Report issues as you go — one line per red flag, file path + what went wrong.

---

## 0. Baseline — `d2w --help` should show every first-party plugin

```bash
uv run d2w --help
```

Expect 16 namespaces on a clean install:

```
analytics   apps     browser   data       dev
doctor      files    maintenance  messaging  metadata
profile     route    system    user       user-group
user-role
```

Any additional namespace = an externally-installed plugin registered through `importlib.metadata.entry_points(group="dhis2.plugins")` (see [external plugins](architecture/external-plugin.md)); missing first-party names = a plugin-discovery regression.

---

## 1. `profile` — config management + auth flows

```bash
# Offline commands first.
uv run d2w profile list
uv run d2w profile ls                      # hidden alias of `list`
uv run d2w profile show local
uv run d2w profile show local --secrets    # secrets visible
uv run d2w profile default local --verify
uv run d2w profile verify                  # verifies every profile
uv run d2w profile verify local            # single profile
uv run d2w --json profile verify local

# Add / rename / remove (idempotent — cleans up after itself).
# `profile add --auth pat` reads DHIS2_PAT from env.
uv run d2w profile add smoketest --url http://localhost:8080 --auth pat --verify
uv run d2w profile rename smoketest smoketest2 --verify
uv run d2w profile remove smoketest2

# OAuth2 login flow (opens a browser).
uv run d2w profile add local_oidc --auth oauth2 --from-env --default --verify
uv run d2w profile login local_oidc        # browser pops, complete consent
uv run d2w profile verify local_oidc
uv run d2w profile logout local_oidc       # clears tokens.sqlite row
uv run d2w profile verify local_oidc       # now fails until re-login

# Bootstrap — one-shot (provisions server-side credential + saves profile).
# Admin creds + client_secret come from DHIS2_ADMIN_PASSWORD / DHIS2_ADMIN_PAT
# / DHIS2_OAUTH_CLIENT_SECRET env vars; no argv secrets.
uv run d2w profile bootstrap fresh_oidc \
  --auth oauth2 \
  --url http://localhost:8080 \
  --admin-user admin \
  --client-id "smoketest-$(date +%s)" \
  --login
uv run d2w profile remove fresh_oidc

uv run d2w profile bootstrap fresh_pat \
  --auth pat \
  --url http://localhost:8080 \
  --admin-user admin \
  --pat-description "smoke test PAT"
uv run d2w profile remove fresh_pat
```

---

## 2. `system` — remote introspection

```bash
uv run d2w system whoami
uv run d2w system info
uv run d2w --profile local system whoami   # named-profile path
```

---

## 3. `metadata` — type catalog + instance list/get

```bash
# The catalog.
uv run d2w metadata type list
uv run d2w metadata type ls                # hidden alias

# Basic instance list + get.
uv run d2w metadata list dataElements --page-size 5
uv run d2w --json metadata list dataElements --page-size 5
uv run d2w metadata ls dataElements --page-size 5          # alias
uv run d2w metadata get dataElements fClA2Erf6IO
uv run d2w metadata get organisationUnits ImspTQPwCqd

# Full filter/field surface (see docs/architecture/metadata-plugin.md).
uv run d2w metadata list dataElements \
  --filter 'name:like:Penta' --fields 'id,name,valueType'

# Multi-filter, OR-joined.
uv run d2w metadata list dataElements \
  --filter 'name:like:Penta' --filter 'code:eq:DE_PENTA1' --root-junction OR \
  --fields 'id,name,code'

# Ordered + paged.
uv run d2w metadata list organisationUnits \
  --order 'level:asc' --order 'name:asc' --page-size 5 --page 2

# `--all` streams every page server-side (ignores --page/--page-size).
uv run d2w --json metadata list dataElements --all --fields ':identifiable' | jq 'length'

# i18n fields.
uv run d2w metadata list dataElements --translate --locale fr --page-size 3
```

---

## 4. `data aggregate` — read/write aggregate data values

```bash
uv run d2w data aggregate get --data-set BfMAe6Itzgt --org-unit PMa2VCrupOd --period 202601
uv run d2w data aggregate set --de fClA2Erf6IO --pe 202603 --ou PMa2VCrupOd --value 88
uv run d2w data aggregate get --data-set BfMAe6Itzgt --org-unit PMa2VCrupOd --period 202603
uv run d2w data aggregate delete --de fClA2Erf6IO --pe 202603 --ou PMa2VCrupOd

# Bulk push from a file (create a one-value file on the fly).
# Pick a period inside the open-future window for `BfMAe6Itzgt` — the seeded
# dataset caps future-open at 3 months. 202603 is safe when running in 2026.
cat > /tmp/dv.json <<'JSON'
{"dataValues": [{"dataElement":"fClA2Erf6IO","period":"202603","orgUnit":"PMa2VCrupOd","value":"77"}]}
JSON
uv run d2w data aggregate push /tmp/dv.json --strategy CREATE_AND_UPDATE --dry-run
uv run d2w data aggregate push /tmp/dv.json --strategy CREATE_AND_UPDATE
uv run d2w data aggregate delete --de fClA2Erf6IO --pe 202603 --ou PMa2VCrupOd
```

---

## 5. `data tracker` — tracked entities, enrollments, events, relationships

The seeded e2e fixture has no tracker programs, so most of these will return `200 {}`. Verify each subcommand at least parses + dispatches cleanly.

Against a tracker-populated instance the list calls return typed pydantic models from `dhis2w_client.generated.v42.tracker` (`TrackerEvent`, `TrackerEnrollment`, `TrackerTrackedEntity`, `TrackerRelationship`). Status fields are `StrEnum` (`EventStatus.COMPLETED`, `EnrollmentStatus.ACTIVE`, etc.). Tracker models are version-scoped because `/api/tracker/*` shapes drift across DHIS2 majors. See [Typed schemas](architecture/typed-schemas.md).

`d2w data tracker --help` should list four top-level commands (`list`, `get`, `type`, `push`) plus three sub-typers (`enrollment`, `event`, `relationship`).

```bash
uv run d2w data tracker --help
uv run d2w data tracker list --help
uv run d2w data tracker get --help
uv run d2w data tracker type                  # empty list on seeded stack
uv run d2w data tracker push --help
uv run d2w data tracker enrollment list --help
uv run d2w data tracker event list --help
uv run d2w data tracker relationship list --help
```

Against a tracker-populated instance (e.g. `play.dhis2.org/dev`):

```bash
uv run d2w --profile play data tracker type                                 # discover configured types
uv run d2w --profile play data tracker list Person --program <PROG_UID> --page-size 5
uv run d2w --profile play data tracker event list --program <PROG_UID> --updated-after 2024-01-01
```

---

## 6. `analytics` — query + refresh

```bash
# All three shapes.
uv run d2w analytics query \
  --dim dx:fClA2Erf6IO\;UOlfIjgN8X6 --dim pe:LAST_12_MONTHS --dim ou:ImspTQPwCqd\;LEVEL-2 --skip-meta

uv run d2w analytics query --shape raw \
  --dim dx:fClA2Erf6IO --dim pe:LAST_12_MONTHS --dim ou:ImspTQPwCqd

uv run d2w analytics query --shape dvs \
  --dim dx:fClA2Erf6IO --dim pe:LAST_12_MONTHS --dim ou:ImspTQPwCqd

# Kick off an analytics-table refresh (moved under `maintenance` alongside
# the other resource-table refresh verbs).
uv run d2w maintenance refresh analytics --last-years 2
```

---

## 7. `route` — integration routes

`d2w route list` emits JSON, so use `jq` to pull fields out.

```bash
uv run d2w route list
uv run d2w route ls                      # alias

# Create a trivial route pointing at httpbin. `route create` without --file is a
# guided interactive wizard — for scripted/automated use pass a JSON spec.
cat > /tmp/route.json <<'JSON'
{"code":"SMOKETEST","name":"smoke test","url":"https://httpbin.org/get"}
JSON
uv run d2w route create --file /tmp/route.json

# Grab the UID with jq and inspect. UID is a bash readonly; use ROUTE_UID.
ROUTE_UID=$(uv run d2w route list | jq -r '.[] | select(.code=="SMOKETEST") | .id')
uv run d2w route get "$ROUTE_UID"
uv run d2w route run "$ROUTE_UID"
uv run d2w route delete "$ROUTE_UID"
```

(If `route create` fails with 409 "route already exists", delete the old `SMOKETEST` code first.)

---

## 8. `dev` — codegen, uid, pat, oauth2, sample fixtures

```bash
# UID generation.
uv run d2w dev uid
uv run d2w dev uid -n 5

# Codegen — rebuilds committed schemas without touching the network.
uv run d2w dev codegen rebuild

# PAT provisioning (reads DHIS2_ADMIN_PAT / DHIS2_ADMIN_PASSWORD from env).
uv run d2w profile pat create --url http://localhost:8080 --admin-user admin \
  --description "smoke test PAT"

# OAuth2 client registration (admin creds + client_secret via env only).
uv run d2w profile oauth2 client register \
  --url http://localhost:8080 --admin-user admin \
  --client-id "standalone-$(date +%s)"

# Sample fixtures — each creates, verifies, cleans up (unless --keep).
uv run d2w dev sample route
uv run d2w dev sample data-value
uv run d2w dev sample pat
uv run d2w dev sample oauth2-client
uv run d2w dev sample all
```

---

## 8b. `maintenance` — tasks, cache, cleanup, data-integrity

See [Maintenance plugin](architecture/maintenance-plugin.md) for the full surface.

```bash
# Task polling (every async DHIS2 op feeds this — analytics refresh, metadata import, etc.).
uv run d2w maintenance task types
uv run d2w maintenance task list ANALYTICS_TABLE
uv run d2w maintenance task status ANALYTICS_TABLE "$(uv run d2w maintenance task list ANALYTICS_TABLE | head -1)"

# Cache — Hibernate + app caches.
uv run d2w maintenance cache

# Soft-delete cleanup (unblocks parent-metadata removal; see BUGS.md #2).
uv run d2w maintenance cleanup data-values
uv run d2w maintenance cleanup events
uv run d2w maintenance cleanup enrollments
uv run d2w maintenance cleanup tracked-entities

# Data-integrity checks.
uv run d2w maintenance dataintegrity list | head
TASK_UID="$(uv run d2w maintenance dataintegrity run orgunits_invalid_geometry | jq -r '.response.id')"
uv run d2w maintenance task watch DATA_INTEGRITY "$TASK_UID" --interval 1 --timeout 60
uv run d2w maintenance dataintegrity result orgunits_invalid_geometry
```

---

## 9. MCP — every tool via `fastmcp.Client` in-process

Run every `examples/v42/mcp/*.py` to cover the full surface (`python infra/scripts/verify_examples.py` does this for you plus the CLI + client sides). Or enumerate the tool list directly:

```bash
uv run python - <<'PY'
import asyncio
from collections import Counter
from fastmcp import Client
from dhis2w_mcp.server import build_server

async def main():
    async with Client(build_server()) as c:
        tools = await c.list_tools()
        groups = Counter(t.name.split("_", 1)[0] for t in tools)
        print(f"{len(tools)} tools across {len(groups)} groups:")
        for group, count in sorted(groups.items()):
            print(f"  {group}: {count}")
asyncio.run(main())
PY
```

Expect roughly 304 tools across 13 groups (regenerated counts live in `docs/mcp-reference.md`; the per-group breakdown ages with each release):

```
analytics: 5     messaging: 11
apps: 13         metadata: 230
customize: 7     profile: 4
data: 15         route: 7
doctor: 4        system: 5
files: 5         user: 16
maintenance: 15
```

A missing group = regression in plugin wiring. The `metadata` group is the largest because every authoring triple (`organisation-units`, `data-elements`, `indicators`, `program-indicators`, `category-options`) plus `legend-sets` and the workflow sub-apps (`options`, `attribute`, `program-rule`, `sql-view`, `viz`, `dashboard`, `map`) all register tools under it. [MCP reference](mcp-reference.md) has the full tool list with signatures + docstrings.

---

## 10. Error paths worth hitting

```bash
# Bad profile name.
uv run d2w profile show does_not_exist                # expect non-zero, informative

# login on a non-oauth2 profile.
uv run d2w profile login local                        # expect "login only applies to oauth2"

# Invalid analytics shape.
uv run d2w analytics query --shape garbage --dim dx:x --dim pe:y --dim ou:z

# Route run against a non-existent UID.
uv run d2w route run fake1234uid
```

---

## Reporting

Format issues as:

```
[cli|mcp] <command path>: <what went wrong>
  <paste of the actual output / stack trace>
```

Drop them into a scratch file or comment on the PR — easier to triage in batch than one-by-one.
