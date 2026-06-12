# Running DHIS2 locally

`infra/` holds everything needed to stand up a local DHIS2 instance (plus pgAdmin and Glowroot APM) for development and integration tests. It's the workspace's answer to "how do I run a real DHIS2 I can point the client at?"

## Prerequisites

- Docker Desktop (or `docker compose` on Linux)
- `infra/v{version}/dump.sql.gz` — a PostgreSQL dump of DHIS2 metadata + data for the targeted version. The repo ships `infra/v42/dump.sql.gz` (Sierra Leone tree + seeded data + tracker + analytics) and an empty placeholder at `infra/v43/dump.sql.gz`. Point `DHIS2_VERSION` at another value and drop a matching dump at `infra/v{DHIS2_VERSION}/dump.sql.gz`. Without one, Postgres starts empty and DHIS2 bootstraps its own schema via Flyway.
- Workspace installed: `make install`

## Quick start

```bash
# one-shot: bring it up, wait for readiness, seed standard PATs + OAuth2 client
make dhis2-run DHIS2_VERSION=42

# credentials file written to:
cat infra/home/credentials/.env.auth

# stop when done
make dhis2-down
```

Or step-by-step from `infra/`:

```bash
cd infra

# what DHIS2 images can I pull from Docker Hub?
make versions

# pull + start the base stack (DHIS2 + pgAdmin) on http://localhost:8080
make up DHIS2_VERSION=42

# block until /api/me responds
make wait

# seed standard auth (6 PAT variations + OAuth2 client)
make seed

# watch the logs
make logs

# verify it's up
make status

# stop when done
make down
```

You talk to **one** DHIS2 instance at a time. `DHIS2_VERSION` just picks which Docker image to run — it has nothing to do with URL paths. DHIS2 APIs are always at `/api/...`, never `/api/v42/...`. Version differences are in payload/response shapes, and those are handled by `dhis2w-client`'s per-version generated modules (see [Version-aware clients](architecture/versioning.md)).

Defaults: DHIS2 43, admin / district, http://localhost:8080. Pass `DHIS2_VERSION=42` to run the seeded v42 stack instead.

## Targets

| Target | What it does |
| --- | --- |
| `make versions` | Queries Docker Hub for `dhis2/core:*` tags |
| `make pull DHIS2_VERSION=X` | Pulls the selected DHIS2 image |
| `make build` | Builds the supporting images (postgres + glowroot-installer) |
| `make up DHIS2_VERSION=X` | Starts the stack in the background (keeps volumes) |
| `make up-fresh DHIS2_VERSION=X` | Wipes volumes + logs and starts clean |
| `make down` | Stops the stack (keeps volumes) |
| `make clean` | Nukes volumes, logs, and runtime data |
| `make status` | `docker compose ps` + DHIS2 reachability probe |
| `make ps` | `docker compose ps` only |
| `make logs` | Follows DHIS2 + Postgres logs |
| `make pat` | Mints a single Playwright PAT against the running instance (delegates to `dhis2w-browser`) |
| `make wait` | Blocks until `/api/me` responds — readiness gate before seeding |
| `make seed` | Creates 6 PAT variations + OAuth2 client; writes `infra/home/credentials/.env.auth` |
| `make up-seeded` | `up` + `wait` + `seed` — one-shot DHIS2 with auth ready to use |

All targets honor `DHIS2_VERSION`, `DHIS2_URL`, `DHIS2_USER`, `DHIS2_PASS` environment overrides.

## What's in `infra/`

```
infra/
├── Makefile                 # top-level targets listed above
├── compose.yml              # core: postgres + dhis2 + glowroot-installer + analytics-trigger
├── compose.pgadmin.yml      # adds pgAdmin on :5050
├── Dockerfile               # custom postgres image with bcrypt
├── initdb.sh                # first-boot Postgres init: load dump, reset all user passwords
├── run.sh                   # convenience wrapper (pre-existing)
├── scripts/
│   ├── list_versions.py     # queries Docker Hub for dhis2/core tags
│   └── startup.sh           # DHIS2 runtime entry (from source repo)
├── glowroot/admin.json      # glowroot JVM profiler seed config
├── pgadmin4/                # pgAdmin bootstrap (pre-registered server, masked pgpass)
├── home/                    # bind-mounted into DHIS2 container (dhis.conf, logs, glowroot jar)
├── .env.example             # template for overrides (never commit filled-in .env)
└── .gitignore               # ignores logs, .env, local SQL dumps, generated PNGs
```

## How this ties into the workspace

- Integration tests (`make test-slow`) that hit `DHIS2_LOCAL_URL` (default `http://localhost:8080`) rely on the stack being up.
- The `local_pat` pytest fixture minting PATs via Playwright works against whatever URL you've set — so point it at this stack, or any other local DHIS2.
- `make pat` inside `infra/` is the quickest way to mint a PAT for the running stack and print it.

## Seeded auth

`make seed` creates these credentials on each run (all tied to the admin user):

| Variable | What it is |
| --- | --- |
| `DHIS2_PAT_DEFAULT` | Unrestricted PAT, no expiry |
| `DHIS2_PAT_READ_ONLY` | GET-only method allowlist |
| `DHIS2_PAT_WRITE` | GET/POST/PUT/PATCH/DELETE allowlist |
| `DHIS2_PAT_SHORT_EXPIRY` | Expires in 1 day — exercise refresh handling |
| `DHIS2_PAT_LOCAL_ONLY` | IP allowlist: loopback only |
| `DHIS2_PAT_REFERRER_BOUND` | Referrer allowlist for `https://example.com` |
| `DHIS2_PAT`, `DHIS2_LOCAL_PAT` | Aliases for `DEFAULT` — what most code looks at |
| `DHIS2_OAUTH_CLIENT_ID` | `dhis2-utils-local` — deterministic client id |
| `DHIS2_OAUTH_CLIENT_SECRET` | Deterministic local-only secret |
| `DHIS2_OAUTH_REDIRECT_URI` | `http://localhost:8765` — matches dhis2w-client's OAuth2 default |
| `DHIS2_OAUTH_SCOPES` | `ALL` — DHIS2 only recognises the single `ALL` scope |

The variation list is in `infra/scripts/_seed_auth_variations.py`; the OAuth2 client config is in `infra/scripts/_seed_auth_oauth2.py`. Edit either to change what gets seeded.

Source an integration test's env with:

```bash
set -a; source infra/home/credentials/.env.auth; set +a
make test-slow
```

### OAuth2 / OIDC requires extra `dhis.conf` keys

The PAT variants work out of the box against a vanilla DHIS2 instance. **OAuth2 does not.** DHIS2 ships Spring Authorization Server but ships it switched off, and its `/api` JWT validator only trusts issuers registered in `dhis.conf`. The seeded `make dhis2-seed` creates the OAuth2 client but cannot toggle server-side config — you need the following in `dhis.conf` before `d2w profile login <name>` will work end-to-end.

For the full walkthrough, including troubleshooting and why each key matters, see [Connecting to DHIS2 § OAuth2 / OIDC](guides/connecting-to-dhis2.md#option-3-oauth2-oidc).

```properties
oauth2.server.enabled                  = on
server.base.url                        = http://localhost:8080
oidc.jwt.token.authentication.enabled  = on
oidc.oauth2.login.enabled              = on

oidc.provider.dhis2.client_id         = dhis2-utils-local
oidc.provider.dhis2.client_secret     = dhis2-utils-local-secret-do-not-use-in-prod
oidc.provider.dhis2.issuer_uri        = http://localhost:8080
oidc.provider.dhis2.authorization_uri = http://localhost:8080/oauth2/authorize
oidc.provider.dhis2.token_uri         = http://localhost:8080/oauth2/token
oidc.provider.dhis2.jwk_uri           = http://localhost:8080/oauth2/jwks
oidc.provider.dhis2.user_info_uri     = http://localhost:8080/userinfo
oidc.provider.dhis2.redirect_url      = http://localhost:8765
oidc.provider.dhis2.scopes            = ALL
oidc.provider.dhis2.mapping_claim     = sub
```

See `docs/architecture/auth.md` for what each key does and which failure mode it unblocks. After editing `dhis.conf`, restart the stack (`make dhis2-down && make dhis2-run`).

## The committed `v{version}/dump.sql.gz`

**`infra/v{version}/dump.sql.gz` is the one exception** to the usual "no DB dumps in repo" rule. It's the committed end-to-end dump that makes a fresh clone usable without any external data. The committed default is `infra/v42/dump.sql.gz`; create a sibling `infra/v43/dump.sql.gz` (or any other DHIS2 major) when you start supporting it.

The dump mirrors DHIS2 Play's Sierra Leone immunization demo with workspace-local additions. After `make dhis2-run` it gives you:

- **Org unit tree** — 1,332 org units (Sierra Leone Country → Province → District → Facility) with GeoJSON geometries, plus 4 named OrganisationUnitLevel records.
- **67 data elements** (immunization + supervision domain), **3 indicators**, **2 datasets**.
- **Tracker + event programs** — Child Programme (WITH_REGISTRATION, immunization stages), Antenatal (WITH_REGISTRATION), Supervision visit (WITHOUT_REGISTRATION). 500 tracked entities, 12 sample supervision events covering 2024 monthly.
- **6 program rules + 10 program indicators**.
- **~188k aggregate data values** so analytics queries return non-empty grids.
- **3 dashboards, 23 visualizations** built via `VisualizationSpec` + 1 `EventVisualization` for the supervision program; **8 maps** built via `MapSpec`.
- **Workspace fixtures** layered on top: `SNOMED_CODE` attribute, `VACCINE_TYPE` option set with 5 fixed-UID options, 3 SqlViews (VIEW / QUERY / MATERIALIZED_VIEW), 2 BCG predictors + PredictorGroup + 2 output DEs, 2 BCG validation rules + ValidationRuleGroup, 1 LegendSet (`LsDoseBand1`) attached to the Measles + Penta-1 monthly column charts.
- **Pre-populated analytics tables** so dashboards render immediately.
- **Pre-seeded OAuth2 client** `dhis2-utils-local` (see [Connecting to DHIS2 guide](guides/connecting-to-dhis2.md)).
- **Admin user** with `openId=admin` already set so OIDC JWTs validate.

`make refresh-and-verify` wipes the stack, rebuilds the dump, and runs every non-interactive example end-to-end against it as the regression gate.

### Committed credentials

These are deterministic and documented here on purpose — the dump is a synthetic test fixture, not a real instance. Never reuse these values outside local dev.

| What | Value |
| --- | --- |
| DHIS2 URL | `http://localhost:8080` |
| Login | `admin` / `district` |
| OAuth2 client id | `dhis2-utils-local` |
| OAuth2 client secret (plaintext) | `dhis2-utils-local-secret-do-not-use-in-prod` |
| OAuth2 redirect URI | `http://localhost:8765` |
| OAuth2 scope | `ALL` |

PATs are **not** committed (DHIS2 generates them per-request, so there's nothing deterministic to bake in). Run `make dhis2-run` (brings up the stack detached and seeds in one shot) — PATs land in `infra/home/credentials/.env.auth`.

### Regenerating the dump

```bash
make dhis2-build-e2e-dump
```

Wipes the postgres volume, brings up an empty DHIS2, runs `infra/scripts/build_e2e_dump.py` (metadata + data + analytics + tracker + OAuth2 client + openId mapping), then `pg_dump`'s the result into `infra/v$(DHIS2_VERSION)/dump.sql.gz` (defaults to `v43/dump.sql.gz`). Commit the resulting diff.

**Only re-run when you intentionally want the committed dump to change** — for example, to add more data elements, extend the date range, or refresh the OAuth2 client config. Everyday workflows use the existing dump.

## What's intentionally not committed

- `*.sql.gz` dumps outside the `dhis-*.sql.gz` whitelist — production or customer dumps (e.g. `prod.sql.gz`) stay ignored.
- `.env` — may contain real credentials.
- `home/logs/`, `home/glowroot/`, `home/files/` — runtime state that a fresh clone shouldn't inherit.
- `home/credentials/` — the seeded `.env.auth` file lives here; regenerate with `make dhis2-seed`.
- `home/dhis-google-auth.json` — OAuth client secrets for DHIS2's Google integration.

## Origin

`infra/` was imported from `github.com/mortenoh/dhis2-docker` on 2026-04-17. The original repo remains the upstream; changes made here may later be pushed back if we stick to that arrangement.
