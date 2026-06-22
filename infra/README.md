# dhis2-docker

![DHIS2](https://img.shields.io/badge/DHIS2%20Core-42%20%7C%2043-2C6693?style=flat-square)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-17-336791?style=flat-square&logo=postgresql&logoColor=white)
![Glowroot](https://img.shields.io/badge/Glowroot-0.14.6-5C4D7D?style=flat-square)
![pgAdmin](https://img.shields.io/badge/pgAdmin-4-326690?style=flat-square&logo=postgresql&logoColor=white)
![Docker Compose](https://img.shields.io/badge/Docker%20Compose-enabled-2496ED?style=flat-square&logo=docker&logoColor=white)
![Last Commit](https://img.shields.io/github/last-commit/mortenoh/dhis2-docker?style=flat-square)

Local DHIS2 development stack: **PostgreSQL + DHIS2 + Glowroot APM + pgAdmin**, orchestrated with Docker Compose. Designed for fast iteration on a local machine with a seeded dump of real DHIS2 data. One command brings everything up with zero prompts, and every DHIS2 user's password is reset to `district` so you can log in as anyone.

## What's in the box

| Service | Image | Purpose |
|---|---|---|
| `postgresql` | custom (postgis + wal2json + python3-bcrypt) | DHIS2 database, pre-loaded from `$(DHIS2_VERSION)/dump.sql.gz` |
| `glowroot-installer` | `alpine:3.20` | Runs once at stack-up to download the Glowroot APM agent into `home/glowroot/` |
| `dhis2` | `dhis2/core:43` | DHIS2 web app with `-javaagent:/opt/dhis2/glowroot/glowroot.jar` attached |
| `pgadmin4` | `dpage/pgadmin4:latest` | Pre-configured browser-based DB client |
| `analytics-trigger` | `curlimages/curl:latest` | One-shot: hits `/api/resourceTables/analytics` after DHIS2 becomes healthy, polls to completion |

## Prerequisites

- **Docker Desktop** with **at least 12 GB** memory allocated (16 GB recommended). DHIS2 needs ~5 GB just for the analytics populate phase, and starving the Docker Desktop VM will get the JVM SIGKILL'd mid-populate.
- **`make`, `curl`, `bash`** on the host (standard on macOS and most Linux distros).
- A **DHIS2 database dump** at `./$(DHIS2_VERSION)/dump.sql.gz` (gzipped `pg_dump` output). The repo ships a seeded `v42/dump.sql.gz` and an empty placeholder at `v43/dump.sql.gz`; build a fresh dump for any version with `make build-e2e-dump DHIS2_VERSION=vN`.

## Quick start

```bash
make run
```

No `.env` file needed — every variable has a sensible default baked into `compose.yml`. Only create a `.env` if you want to override something (`cp .env.example .env`).

That's it. `make run` will:

1. Wipe `home/logs/*`.
2. `docker compose down -v` — nuke any previous state, including the `pgdata` volume so postgres reinitializes from scratch.
3. `docker compose up` with both `compose.yml` and `compose.pgadmin.yml`, streaming logs in the foreground.

First startup takes **5–10 minutes**: postgres imports the dump, DHIS2 runs schema migrations and app discovery, then `analytics-trigger` populates the analytics tables before exiting. Every `make run` does this from scratch — image layers are reused (fast rebuild), but the postgres volume is always wiped (`down -v`), so you get a clean dataset every time. Press `Ctrl+C` to stop.

When it's done you'll have three services ready to browse:

| URL | Service |
|---|---|
| [http://localhost:8080](http://localhost:8080) | DHIS2 |
| [http://localhost:4000](http://localhost:4000) | Glowroot APM |
| [http://localhost:5050](http://localhost:5050) | pgAdmin |

## Accessing the services

### DHIS2 — http://localhost:8080

Log in as `admin` / `district`. **Any existing username in the dump also works with the password `district`** — `initdb.sh` rewrites every row in `userinfo` on a fresh init (see [Password reset](#password-reset) below).

If the page doesn't load immediately, DHIS2 is still booting. Tomcat takes ~30–90 seconds after postgres becomes healthy. Follow `docker compose logs -f dhis2` to watch it come up.

### Glowroot APM — http://localhost:4000

Just open the URL — no login screen. `glowroot/admin.json` pre-declares an anonymous Administrator user, so you land straight on the dashboard. Hit a few DHIS2 pages to generate traffic, then explore:

- **Transactions > Web** — per-endpoint response times, sample traces, slow query breakdown
- **Errors** — exceptions with full stacks
- **JVM > Gauges** — heap, GC, threads
- **JVM > MBean tree / Thread dump / Heap dump** — live introspection

Glowroot stores its own data under `home/glowroot/data/` (H2 embedded). Because `home/glowroot/` is a host bind mount, `make run`'s `down -v` doesn't touch it, so your traces and configuration persist across restarts. For a blank-slate glowroot, `rm -rf home/glowroot/ && make run` — the `glowroot-installer` sidecar will re-download the agent.

> **Warning** — local dev only. The anonymous-admin shortcut means anyone who can reach port 4000 has full APM access. Never expose this port on a shared machine or network.

### pgAdmin — http://localhost:5050

Open the URL and click the **DHIS2** server in the left tree (expand `Servers` > `DHIS2`). Three normally-annoying prompts are pre-disabled:

| Prompt | Disabled by |
|---|---|
| Master password on first launch | `PGADMIN_CONFIG_MASTER_PASSWORD_REQUIRED: "False"` |
| pgAdmin login | `PGADMIN_CONFIG_SERVER_MODE: "False"` (desktop mode) |
| Database password | `pgadmin4/pgpass` (chmod 600) bind-mounted at `/pgpass` and referenced via `"PassFile": "/pgpass"` in `pgadmin4/servers.json` |

If you want to add more servers, either (a) do it in the UI and accept that they live only for the lifetime of the pgadmin container, or (b) edit `pgadmin4/servers.json` so they re-seed on every startup.

## Make targets

```
make run         clean start: wipe volumes + logs, then start the stack
make run-force   wipe volumes + logs, rebuild images from scratch, and start
make build       build images (no cache bust)
make pull        pull latest images from Docker Hub
make down        stop the stack (keeps volumes)
make help        show this help
```

`make run` is the right default — it reuses cached image layers so the build step is ~instant, but still wipes the postgres volume for a clean DB. Use `make run-force` only when you've edited `Dockerfile` and need `--no-cache`, since it adds several minutes to re-run `apt-get upgrade` from scratch.

## Password reset

`initdb.sh` runs once on fresh postgres init and rewrites every row in the `userinfo` table:

```sql
UPDATE userinfo SET password = <bcrypt($DHIS2_PASSWORD)>, disabled = false;
```

This means:

- **Every DHIS2 user** — not just `admin` — can log in with their existing username and the password from `.env` (default `district`).
- **Every disabled account is re-enabled** (`disabled = false`), which matters because real dumps often ship with historical users disabled.
- **Change the password** by editing `DHIS2_PASSWORD` in `.env` and running `make run` again.

Hashing happens inside the postgres container via `python3-bcrypt` (installed in the `Dockerfile`), so `DHIS2_PASSWORD` can be any plaintext string — no pre-computed hash needed.

This is a local-dev convenience and should never be run against a real database.

## Glowroot APM

Glowroot is a Java agent (`-javaagent`). It has to be present before the JVM starts, so it's **baked into the base compose** rather than offered as an overlay. The `glowroot-installer` service runs first, downloads the agent into `home/glowroot/` (bind-mounted into the DHIS2 container as `/opt/dhis2/glowroot/`), and exits. DHIS2 then starts with `JAVA_OPTS=... -javaagent:/opt/dhis2/glowroot/glowroot.jar`.

The installer is idempotent: if `home/glowroot/glowroot.jar` already exists, it skips the download and just refreshes `admin.json` from the seed template (`glowroot/admin.json`), so bumping auth config is fast.

## pgAdmin — zero-prompt DB access

`compose.pgadmin.yml` is an overlay that carries the `pgadmin4` service. Every Makefile target wraps both files via a `COMPOSE := docker compose -f compose.yml -f compose.pgadmin.yml` variable, so day-to-day it behaves as if it were in the base. The split exists so `docker compose up` (without `-f compose.pgadmin.yml`) gives you a leaner stack if you ever want one.

## Environment

`.env` is **fully optional**. Every variable has a default baked into `compose.yml` via `${VAR:-default}` substitution, so `make run` works out of the box with no configuration. If you want to override any default, `cp .env.example .env` and uncomment the lines you care about — docker compose automatically reads `.env` from the project root for variable substitution.

| Variable | Default | What it does |
|---|---|---|
| `POSTGRES_USER` | `dhis` | Postgres superuser created on first init |
| `POSTGRES_PASSWORD` | `dhis` | Postgres superuser password |
| `POSTGRES_DB` | `dhis` | Postgres database created on first init |
| `TZ` | `Europe/Oslo` | Container timezone for both postgres and pgadmin |
| `PGADMIN_DEFAULT_EMAIL` | `admin@admin.com` | pgAdmin master identity (invisible in desktop mode) |
| `PGADMIN_DEFAULT_PASSWORD` | `root` | pgAdmin master password (invisible in desktop mode) |
| `DHIS2_USER` | `admin` | Used only for display / logging; `initdb.sh` resets *every* row in `userinfo` regardless |
| `DHIS2_PASSWORD` | `district` | Bcrypt-hashed at init time and applied to every DHIS2 user |

## File layout

```
compose.yml               # base stack: postgres, glowroot-installer, dhis2, analytics-trigger
compose.pgadmin.yml       # pgadmin4 overlay (always included by Makefile targets)
Dockerfile                # postgis/postgis:17-3.4 + wal2json + python3-bcrypt
initdb.sh                 # one-shot init: loads dump, resets passwords, enables accounts
v42/dump.sql.gz           # committed e2e dump for DHIS2 42 (Sierra Leone immunization seed)
v43/dump.sql.gz           # placeholder empty dump for v43 — build a real one with `make build-e2e-dump DHIS2_VERSION=v43`
v{N}/dump.sql.gz          # add a per-version subdir + dump for any other DHIS2 major

glowroot/admin.json       # committed seed for glowroot auth config
pgadmin4/servers.json     # pgAdmin pre-registered server entry
pgadmin4/pgpass           # chmod-600 pgpass (referenced from servers.json via PassFile)

home/                     # bind-mounted into dhis2 container as /opt/dhis2
├── dhis.conf             # DHIS2 config (committed)
├── dhis-google-auth.json # gitignored
├── files/                # DHIS2 runtime files (gitignored)
├── logs/                 # DHIS2 logs (gitignored, wiped by make run)
└── glowroot/             # downloaded by glowroot-installer (gitignored)

Makefile
README.md                 # you are here
CLAUDE.md                 # project rules (no emojis, no Claude attribution, Conventional Commits)
.env                      # local config (gitignored)
.env.example              # canonical reference for .env
.gitignore
```

For a walk-through of the DHIS2 `analytics_*` tables (schema, cross-verification of the inheritance chain, and practical example queries) see [analytics.md](../docs/architecture/analytics.md).

## Troubleshooting

**DHIS2 restarts mid-startup, analytics-trigger loops forever.** Docker Desktop VM is out of memory and the host kernel is SIGKILL'ing the JVM during the analytics populate phase. Bump Docker Desktop > Resources > Memory to 16 GB. The JVM's `-Xmx4g` plus analytics workers plus the postgres buffer pool easily blows past 8 GB on real data.

**analytics-trigger keeps printing `Still running...` and never completes.** Check `docker logs dhis2 | grep -i 'added root logger'` — if you see that line *after* analytics started, DHIS2 silently restarted and the task notifications buffer was lost. Same cause as above (memory). `analytics-trigger` hardcodes `admin` / `district`, so if you've deleted the `admin` user from the dump, you'll see `401 Unauthorized` instead.

**pgAdmin complains the server is out of date.** `pull_policy: always` on `dpage/pgadmin4:latest` refreshes the image on every `make run`, but Docker Hub's `:latest` tag occasionally lags. Pin to a specific version in `compose.pgadmin.yml` if needed.

**`make run-force` takes forever.** The `--no-cache` flag re-runs `apt-get upgrade` from scratch inside the postgres image build. Use `make run` unless you've actually edited the `Dockerfile`.

**Port 8080 / 4000 / 5050 already in use.** Something else is bound to one of those ports on the host. `lsof -i :8080` to find the culprit, or change the published port in the relevant compose file.

## Licensing

Glowroot is Apache 2.0, pgAdmin is PostgreSQL License, DHIS2 is BSD-3-Clause. This stack is a local dev convenience inside the `dhis2w-utils` workspace.
