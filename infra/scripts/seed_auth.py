"""Seed a running DHIS2 instance with the standard PAT + OAuth2 client set.

Usage (from repo root): `make dhis2-seed` or `uv run python infra/scripts/seed_auth.py`.
Splits config into `_seed_auth_variations.py` and `_seed_auth_oauth2.py` so either
can be edited in isolation without touching the runner.

All PATs are linked to the admin user (auto). The OAuth2 client is upserted by
clientId, so re-runs update the existing client rather than piling up duplicates.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _seed_auth_oauth2 import (  # noqa: E402 — path-prepend above is intentional
    OAUTH2_CLIENT_ID,
    OAUTH2_CLIENT_SECRET,
    OAUTH2_GRANT_TYPES,
    OAUTH2_REDIRECT_URI,
    OAUTH2_SCOPES,
    oauth2_payload,
)
from _seed_auth_variations import PAT_VARIATIONS  # noqa: E402
from _seed_login_customization import apply_login_customization  # noqa: E402
from dhis2w_client import BasicAuth, Dhis2Client  # noqa: E402
from dhis2w_client.errors import Dhis2ApiError  # noqa: E402


async def wait_for_ready(url: str, username: str, password: str, *, max_wait_seconds: int = 180) -> None:
    """Block until /api/me returns successfully or time out."""
    deadline = time.time() + max_wait_seconds
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            async with Dhis2Client(
                url, BasicAuth(username=username, password=password), allow_version_fallback=True
            ) as client:
                await client.system.me()
                return
        except Exception as exc:  # noqa: BLE001 — any failure is a retry reason
            last_error = exc
            await asyncio.sleep(2)
    raise RuntimeError(f"DHIS2 at {url} did not become ready within {max_wait_seconds}s (last error: {last_error})")


async def create_pat(client: Dhis2Client, payload: dict[str, Any]) -> str:
    """POST /api/apiToken and return the generated token value."""
    response = await client.post_raw("/api/apiToken", payload)
    key = (response.get("response") or {}).get("key")
    if not isinstance(key, str) or not key:
        raise RuntimeError(f"unexpected PAT response: {json.dumps(response)[:500]}")
    return key


async def upsert_oauth2_client(client: Dhis2Client) -> None:
    """Create or update the standard OAuth2 client by clientId.

    v41's `/api/schemas/oAuth2Client` doesn't expose `clientId` as a
    filterable property — `?filter=clientId:eq:X` returns 400 E1003
    "Unknown path property: clientId". v42 + v43 accept it. Workaround:
    list all clients (the set is small in practice) and filter
    client-side. Works uniformly across the three majors.
    """
    listed = await client.get_raw(
        "/api/oAuth2Clients",
        params={"fields": "id,cid,clientId", "paging": "false"},
    )
    items = [
        item
        for item in (listed.get("oAuth2Clients") or [])
        if isinstance(item, dict) and (item.get("cid") == OAUTH2_CLIENT_ID or item.get("clientId") == OAUTH2_CLIENT_ID)
    ]
    payload = oauth2_payload()
    if items:
        uid = items[0]["id"]
        await client.put_raw(f"/api/oAuth2Clients/{uid}", payload)
        print(f"    updated existing client {uid}")
    else:
        await client.post_raw("/api/oAuth2Clients", payload)
        print("    created new client")


async def ensure_user_openid_mapping(client: Dhis2Client, username: str) -> None:
    """Set `openId = <username>` on the given user so JWTs with `sub=<username>` map cleanly.

    DHIS2's OIDC user lookup (`Dhis2JwtAuthenticationManagerResolver`) matches the
    JWT's `mapping_claim` value against the `openid` column on `userinfo`. Without
    this step, a fresh admin user has an empty `openId` and the minted access
    token is rejected with "Found no matching DHIS2 user".
    """
    me = await client.system.me()
    user_uid = me.id
    await client.patch_raw(
        f"/api/users/{user_uid}",
        [{"op": "add", "path": "/openId", "value": username}],
    )
    print(f"    openId={username!r} mapped on user {user_uid}")


def _resolve_payload(variation: dict[str, Any]) -> dict[str, Any]:
    """Strip runner-only hints (like `_inject_expiry_days`) and materialise absolute fields."""
    payload = {k: v for k, v in variation["payload"].items() if not k.startswith("_")}
    inject_days = variation["payload"].get("_inject_expiry_days")
    if inject_days is not None:
        payload["expire"] = int(time.time() * 1000) + int(inject_days) * 86_400_000
    return payload


async def seed(url: str, username: str, password: str, output_path: Path) -> None:
    """Run the full seed: readiness → PATs → OAuth2 client → write credentials file."""
    print(f">>> Waiting for {url}")
    await wait_for_ready(url, username, password)

    pat_values: dict[str, str] = {}
    async with Dhis2Client(url, BasicAuth(username=username, password=password)) as client:
        info = await client.system.info()
        me = await client.system.me()
        print(f">>> Seeding {url} (version={info.version}, user={me.username})")

        for variation in PAT_VARIATIONS:
            print(f"  PAT  {variation['suffix']:16} {variation['description']}")
            payload = _resolve_payload(variation)
            try:
                pat_values[variation["suffix"]] = await create_pat(client, payload)
            except Dhis2ApiError as exc:
                print(f"    FAILED: {exc}")
                if exc.body:
                    print(f"    body: {json.dumps(exc.body)[:300]}")
                raise

        print(f"  OAUTH2 {OAUTH2_CLIENT_ID}")
        await upsert_oauth2_client(client)
        await ensure_user_openid_mapping(client, username)

        print("  BRANDING login customization")
        await apply_login_customization(client)

    _write_env_file(output_path, url, username, password, pat_values)
    print(f">>> Wrote {output_path}")


def _write_env_file(
    path: Path,
    url: str,
    username: str,
    password: str,
    pat_values: dict[str, str],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = [
        "# Seeded by infra/scripts/seed_auth.py. Do not commit — regenerate with `make dhis2-seed`.",
        "",
        "# Core connection",
        f"DHIS2_URL={url}",
        f"DHIS2_USERNAME={username}",
        f"DHIS2_PASSWORD={password}",
        "",
        "# PATs (all linked to the admin user)",
    ]
    for suffix in sorted(pat_values):
        lines.append(f"DHIS2_PAT_{suffix}={pat_values[suffix]}")
    lines.extend(
        [
            "",
            "# Canonical default PAT — most code paths look at DHIS2_PAT (no suffix).",
            f"DHIS2_PAT={pat_values['DEFAULT']}",
            f"DHIS2_LOCAL_PAT={pat_values['DEFAULT']}",
            "",
            "# OAuth2 client (deterministic, overwritten on re-seed)",
            f"DHIS2_OAUTH_CLIENT_ID={OAUTH2_CLIENT_ID}",
            f"DHIS2_OAUTH_CLIENT_SECRET={OAUTH2_CLIENT_SECRET}",
            f"DHIS2_OAUTH_REDIRECT_URI={OAUTH2_REDIRECT_URI}",
            f"DHIS2_OAUTH_SCOPES={OAUTH2_SCOPES}",
            f"DHIS2_OAUTH_GRANT_TYPES={OAUTH2_GRANT_TYPES}",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    path.chmod(0o600)


def main() -> int:
    """Parse args and run the seed flow."""
    parser = argparse.ArgumentParser(description="Seed DHIS2 with standard PATs + OAuth2 client.")
    parser.add_argument("--url", default="http://localhost:8080")
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password", default="district")
    parser.add_argument(
        "--output",
        default="infra/home/credentials/.env.auth",
        help="where to write the generated env file (relative to workspace root)",
    )
    args = parser.parse_args()

    output_path = Path(args.output)
    if not output_path.is_absolute():
        workspace_root = Path(__file__).resolve().parents[2]
        output_path = workspace_root / output_path

    asyncio.run(seed(args.url, args.username, args.password, output_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
