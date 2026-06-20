"""Build the committed e2e DHIS2 dump from the Sierra Leone immunization snapshot.

Usage (from repo root): `make dhis2-build-e2e-dump` — brings up an empty
DHIS2, loads the typed metadata / geometry / data-value / tracker fixtures
under `infra/fixtures/play/` via the client's pydantic validators, triggers
analytics, seeds OAuth2 + admin openId mapping + login-page branding, and
pg_dump's the result into `infra/{DHIS2_VERSION}/dump.sql.gz`.

The actual metadata + data is pulled once from play.dhis2.org (Sierra
Leone) by `infra/scripts/pull_play_fixtures.py` and committed to
`infra/fixtures/play/`. This script only imports those fixtures —
`make dhis2-build-e2e-dump` is fully offline after the fixtures land on
disk. Re-run the puller to refresh against play drift.

Produces a gzipped dump small enough to commit next to the compose file,
so `make dhis2-up` on a fresh clone gives a ready-to-login DHIS2 with
1332 org units, 188 k aggregate values, 500 tracker entities, 3
immunization dashboards, 23 visualizations, 8 maps, and every piece of
metadata transitively wired through them.
"""

from __future__ import annotations

import argparse
import asyncio
import gzip
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _seed_login_customization import apply_login_customization  # noqa: E402
from dhis2w_client import BasicAuth, Dhis2Client  # noqa: E402
from seed import seed_play  # noqa: E402
from seed_auth import ensure_user_openid_mapping, upsert_oauth2_client, wait_for_ready  # noqa: E402

POSTGRES_CONTAINER_DEFAULT = "dhis2-docker-postgresql-1"

_BUILD_START_MONOTONIC = time.monotonic()


def _log(message: str) -> None:
    """Print `message` prefixed with wall-clock time + elapsed-since-start."""
    elapsed = time.monotonic() - _BUILD_START_MONOTONIC
    print(f"[{time.strftime('%H:%M:%S')}  +{elapsed:6.1f}s] {message}", flush=True)


def default_dump_path(dhis2_version: str) -> Path:
    """Return the canonical committed-dump path for a given DHIS2 major (vXX)."""
    return Path(__file__).resolve().parents[1] / dhis2_version / "dump.sql.gz"


def run_analytics(analytics_container: str = "analytics-trigger") -> None:
    """Trigger a fresh analytics rebuild by restarting the `analytics-trigger` sidecar.

    Compose brings the sidecar up automatically when DHIS2 turns healthy
    and it fires its first POST `/api/resourceTables/analytics` 20 seconds
    later — well before the seed has loaded any data. That first run is
    cheap (empty database, ~10s on the server) but DHIS2 keeps the task
    on its scheduler. Restarting the sidecar while that task is still
    running spawns a *second* analytics-rebuild that contends with the
    first on `analytics_rs_*` table locks; under linux/amd64 emulation
    on arm64 macOS the resulting deadlock can hang Postgres for 20+
    minutes before either side gives up. Wait for the compose-time task
    to clean-exit *before* restarting, then poll the new task to
    completion.
    """
    _log(f"    waiting for compose-time {analytics_container} to finish first...")
    subprocess.run(["docker", "wait", analytics_container], check=True, capture_output=True)
    _log(f"    restarting {analytics_container} to populate analytics tables against the seeded data")
    subprocess.run(["docker", "restart", analytics_container], check=True, capture_output=True)
    _log("    waiting for the post-seed analytics task to finish (docker wait)...")
    result = subprocess.run(
        ["docker", "wait", analytics_container],
        check=True,
        capture_output=True,
        text=True,
    )
    exit_code = int(result.stdout.strip() or "1")
    if exit_code != 0:
        logs = subprocess.run(
            ["docker", "logs", "--tail", "50", analytics_container],
            capture_output=True,
            text=True,
            check=False,
        ).stdout
        raise RuntimeError(f"analytics-trigger exited with {exit_code}:\n{logs}")
    _log("    analytics tables populated")


def pg_dump(container: str, output: Path, *, postgres_user: str, postgres_db: str) -> None:
    """Run `pg_dump | gzip` via `docker exec` and write the result to `output`."""
    _log(f">>> Dumping database to {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "docker",
        "exec",
        container,
        "pg_dump",
        "--no-owner",
        "--no-privileges",
        "--no-sync",
        "--clean",
        "--if-exists",
        # Keep `analytics_rs_*` resource-structure tables in the dump
        # (orgunit / period / category cross-products). They're tiny
        # (~few MB) and pre-shipping them means a cold `dhis2-up` against
        # the committed dump skips the slow resource-table rebuild on
        # boot. Without them, the post-load analytics-trigger has to
        # build the cross-product from scratch — under linux/amd64
        # emulation on arm64 macOS that's a ~15-minute Postgres burn at
        # 100 % CPU.
        # Exclude only the year-partitioned fact tables and temp tables
        # (those are rebuilt fast once the resource structures exist).
        "--exclude-table=analytics_temp",
        "--exclude-table=analytics_*_temp",
        "--exclude-table=analytics_20*",
        "--exclude-table=aggregated_*",
        "--exclude-table=completeness_*",
        "-U",
        postgres_user,
        "-d",
        postgres_db,
    ]
    with output.open("wb") as gz_handle, gzip.GzipFile(fileobj=gz_handle, mode="wb", compresslevel=9) as gz:
        proc = subprocess.run(cmd, check=True, capture_output=True)
        gz.write(proc.stdout)
    size = output.stat().st_size
    _log(f">>> Wrote {size:,} bytes to {output}")


def detect_postgres_container(default: str) -> str:
    """Return the running postgres container name, falling back to `default`."""
    if shutil.which("docker") is None:
        raise RuntimeError("`docker` CLI not found — need it for pg_dump")
    result = subprocess.run(
        ["docker", "ps", "--format", "{{.Names}}"],
        capture_output=True,
        text=True,
        check=True,
    )
    names = [line.strip() for line in result.stdout.splitlines()]
    candidates = [n for n in names if "postgres" in n.lower()]
    if default in names:
        return default
    if len(candidates) == 1:
        return candidates[0]
    if candidates:
        print(f"!!! multiple postgres containers found: {candidates}; defaulting to {candidates[0]}")
        return candidates[0]
    raise RuntimeError(f"no running postgres container detected; expected {default!r}")


async def build(url: str, username: str, password: str, output: Path, container: str) -> None:
    """End-to-end: seed Sierra Leone fixtures + auth + branding → pg_dump."""
    _log(f">>> Waiting for DHIS2 at {url}")
    await wait_for_ready(url, username, password)
    # Bump read timeout to 5 minutes — DHIS2 v43's stricter validation paths
    # and amd64 emulation under arm64 macOS can push individual chunked
    # /api/dataValueSets and /api/tracker calls past the 30s default.
    async with Dhis2Client(
        url,
        BasicAuth(username=username, password=password),
        timeout=300.0,
    ) as client:
        info = await client.system.info()
        _log(f">>> Connected to DHIS2 {info.version} as {username}")

        _log(">>> Seeding Sierra Leone immunization fixture (infra/fixtures/play/)")
        await seed_play(client)

        _log(">>> Running analytics")
        run_analytics()

        _log(">>> Seeding OAuth2 client + admin openId mapping")
        await upsert_oauth2_client(client)
        await ensure_user_openid_mapping(client, username)

        _log(">>> Applying login-page branding preset")
        await apply_login_customization(client)

    pg_dump(container, output, postgres_user="dhis", postgres_db="dhis")


def main() -> int:
    """Parse args and run the build."""
    default_version = os.environ.get("DHIS2_VERSION", "v42")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://localhost:8080")
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password", default="district")
    parser.add_argument(
        "--dhis2-version",
        default=default_version,
        help="DHIS2 major in vXX form, used to name the dump (default: env DHIS2_VERSION or 'v42')",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="where to write the gzipped dump (default: infra/{dhis2-version}/dump.sql.gz)",
    )
    parser.add_argument(
        "--container",
        default=POSTGRES_CONTAINER_DEFAULT,
        help="name of the running postgres container (auto-detected if not found)",
    )
    args = parser.parse_args()

    output_path = Path(args.output).resolve() if args.output else default_dump_path(args.dhis2_version)
    container = detect_postgres_container(args.container)

    try:
        asyncio.run(build(args.url, args.username, args.password, output_path, container))
    except Exception as exc:  # noqa: BLE001 — top-level runner
        print(f"!!! build failed: {exc}", file=sys.stderr)
        return 1
    _log(">>> Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
