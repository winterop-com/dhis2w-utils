"""`dhis2 dev sample` — inject known-good fixtures and verify them end-to-end.

Each command walks a full lifecycle (create -> verify -> clean up) so a fresh
DHIS2 install can be smoke-tested in one pass. `--keep` skips the cleanup step
so operators can inspect the fixture afterwards. Each command prints structured
`- step` / `  OK  ...` / `  FAIL  ...` lines plus a trailing `PASS (Nms)`.
"""

from __future__ import annotations

import asyncio
import os
import time
from typing import Annotated

import typer
from dhis2w_client.v43 import Dhis2Client, PatAuth, WebMessageResponse
from dhis2w_client.v43.auth.oauth2 import DEFAULT_REDIRECT_URI

from dhis2w_core.profile import profile_from_env
from dhis2w_core.v43.admin_auth import resolve_admin_auth
from dhis2w_core.v43.client_context import open_client
from dhis2w_core.v43.oauth2_registration import register_oauth2_client
from dhis2w_core.v43.pat_registration import register_pat
from dhis2w_core.v43.plugins.route import service as route_service
from dhis2w_core.v43.plugins.route.service import RoutePayload

app = typer.Typer(
    help="Inject known-good fixtures to verify the stack end-to-end (route, data, pat, oauth2-client).",
    no_args_is_help=True,
)


def _ok(msg: str) -> None:
    typer.secho(f"  OK  {msg}", fg=typer.colors.GREEN)


def _fail(msg: str) -> None:
    typer.secho(f"  FAIL  {msg}", fg=typer.colors.RED)


def _step(label: str) -> None:
    typer.secho(f"- {label}", fg=typer.colors.CYAN)


def _pass(started: float) -> None:
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    typer.secho(f"PASS ({elapsed_ms} ms)", fg=typer.colors.GREEN, bold=True)


def _resolve_url(url: str | None) -> str:
    return url or os.environ.get("DHIS2_URL") or profile_from_env().base_url or typer.prompt("DHIS2 base URL")


@app.command("route")
def sample_route_command(
    target_url: Annotated[
        str, typer.Option("--url", help="URL the sample route will proxy to.")
    ] = "https://httpbin.org/get",
    code: Annotated[str, typer.Option("--code")] = "SMOKE_ROUTE",
    keep: Annotated[bool, typer.Option("--keep", help="Don't delete the sample route afterwards.")] = False,
) -> None:
    """Create a sample route, run it, and (unless --keep) delete it.

    Verifies the full /api/routes lifecycle end-to-end: create -> run (proxy
    to target URL) -> delete.
    """
    started = time.perf_counter()
    profile = profile_from_env()
    _step(f"create route code={code!r} -> {target_url}")
    created = asyncio.run(
        route_service.add_route(
            profile,
            RoutePayload(code=code, name=f"sample {code}", url=target_url),
        )
    )
    uid = created.created_uid
    if not uid:
        _fail(f"no uid in POST response: {created.model_dump_json()}")
        raise typer.Exit(1)
    _ok(f"created uid={uid}")

    try:
        _step("run route (DHIS2 proxies to target)")
        response = asyncio.run(route_service.run_route(profile, uid))
        preview = str(response)[:200]
        _ok(f"ran -> {preview}{'...' if len(str(response)) > 200 else ''}")
    finally:
        if keep:
            _ok(f"--keep set; route {uid} left in place (delete with `dhis2 route delete {uid}`)")
        else:
            _step(f"delete route {uid}")
            asyncio.run(route_service.delete_route(profile, uid))
            _ok("deleted")
    _pass(started)


@app.command("pat")
def sample_pat_command(
    url: Annotated[str | None, typer.Option("--url", help="DHIS2 base URL (also: DHIS2_URL env).")] = None,
    admin_user: Annotated[str | None, typer.Option("--admin-user")] = None,
    keep: Annotated[bool, typer.Option("--keep", help="Don't delete the sample PAT afterwards.")] = False,
) -> None:
    """Create a sample PAT, use it to call /api/me, then (unless --keep) delete it."""
    started = time.perf_counter()
    resolved_url = _resolve_url(url)
    admin_auth = resolve_admin_auth(admin_user)

    _step("create PAT via /api/apiToken")
    creds = asyncio.run(
        register_pat(base_url=resolved_url, admin_auth=admin_auth, description="dhis2 dev sample pat (smoke test)")
    )
    _ok(f"uid={creds.uid}, token={creds.token[:12]}... (redacted)")

    async def _use_and_maybe_delete() -> None:
        _step("call /api/me with the new PAT")
        async with Dhis2Client(resolved_url, auth=PatAuth(token=creds.token)) as probe:
            me = await probe.get_raw("/api/me")
        _ok(f"authenticated as {me.get('username')!r} via the new PAT")
        if keep:
            _ok(f"--keep set; PAT {creds.uid} left in place")
            return
        _step(f"delete PAT {creds.uid}")
        async with Dhis2Client(resolved_url, auth=admin_auth) as admin:
            await admin.delete_raw(f"/api/apiToken/{creds.uid}")
        _ok("deleted")

    asyncio.run(_use_and_maybe_delete())
    _pass(started)


@app.command("data-value")
def sample_data_value_command(
    data_element: Annotated[str, typer.Option("--data-element", "--de", help="DataElement UID.")] = "fClA2Erf6IO",
    org_unit: Annotated[str, typer.Option("--org-unit", "--ou", help="OrganisationUnit UID.")] = "Rp268JB6Ne4",
    period: Annotated[str, typer.Option("--period", "--pe", help="Period (e.g. 202406).")] = "202406",
    value: Annotated[str, typer.Option("--value")] = "42",
    keep: Annotated[bool, typer.Option("--keep", help="Don't delete the sample data value afterwards.")] = False,
) -> None:
    """Write a sample data value, read it back, and (unless --keep) delete it.

    Uses the Sierra Leone seed fixture by default:
    `fClA2Erf6IO` ("Penta1 doses given") at `Rp268JB6Ne4`
    (Adonkia CHP, facility level) for `202406` (within the seeded 2024
    data window). The DE is in the seeded `BfMAe6Itzgt` ("Child
    Health") dataset, so v43's stricter dataset-detection on import
    accepts the write. Override with `--de` / `--ou` / `--pe` for
    other scopes.
    """
    started = time.perf_counter()
    profile = profile_from_env()

    async def _run() -> None:
        async with open_client(profile) as client:
            _step(f"POST /api/dataValueSets  {data_element}/{period}/{org_unit} = {value}")
            payload = {
                "dataValues": [{"dataElement": data_element, "period": period, "orgUnit": org_unit, "value": value}]
            }
            envelope = await client.post("/api/dataValueSets", payload, model=WebMessageResponse)
            # DHIS2 wraps ImportSummary under `response.importCount` here, not at the top level.
            import_count = (envelope.response or {}).get("importCount", {})
            _ok(f"import_count={import_count}")

            _step("GET /api/dataValueSets.json (read-back)")
            read = await client.get_raw(
                "/api/dataValueSets.json",
                params={"dataElement": data_element, "orgUnit": org_unit, "period": period},
            )
            matched = [v for v in read.get("dataValues", []) if v.get("value") == value]
            if not matched:
                _fail(f"wrote {value!r} but did not see it in {read.get('dataValues', [])}")
                raise typer.Exit(1)
            _ok(f"read-back contains value={matched[0].get('value')!r}")

            if keep:
                _ok("--keep set; data value left in place")
                return
            _step("delete via importStrategy=DELETE")
            await client.post_raw("/api/dataValueSets", payload, params={"importStrategy": "DELETE"})
            _ok("deleted (soft-delete — DHIS2 keeps the row marked deleted=true; see BUGS.md #2)")

    asyncio.run(_run())
    _pass(started)


@app.command("oauth2-client")
def sample_oauth2_client_command(
    url: Annotated[str | None, typer.Option("--url", help="DHIS2 base URL (also: DHIS2_URL env).")] = None,
    admin_user: Annotated[str | None, typer.Option("--admin-user")] = None,
    client_id: Annotated[
        str | None,
        typer.Option("--client-id", help="OAuth2 client_id; default = smoke-<epoch>."),
    ] = None,
    keep: Annotated[bool, typer.Option("--keep", help="Don't delete the sample OAuth2 client afterwards.")] = False,
) -> None:
    """Create a sample OAuth2 client on DHIS2, verify it persisted, then (unless --keep) delete it.

    Lifecycle: POST /api/oAuth2Clients -> GET /api/oAuth2Clients/{uid}
    -> DELETE /api/oAuth2Clients/{uid}. The admin user is the owner DHIS2
    records on the client; no user-impersonation happens.
    """
    started = time.perf_counter()
    resolved_url = _resolve_url(url)
    admin_auth = resolve_admin_auth(admin_user)
    resolved_client_id = client_id or f"smoke-{int(time.time())}"

    async def _run() -> None:
        _step(f"POST /api/oAuth2Clients (client_id={resolved_client_id!r})")
        creds = await register_oauth2_client(
            base_url=resolved_url,
            admin_auth=admin_auth,
            client_id=resolved_client_id,
            client_secret="smoke-secret-do-not-use",
            redirect_uri=DEFAULT_REDIRECT_URI,
            scope="ALL",
            display_name="dhis2 dev sample oauth2-client (smoke test)",
        )
        _ok(f"created uid={creds.uid}")

        _step(f"GET /api/oAuth2Clients/{creds.uid} (verify persistence)")
        async with Dhis2Client(resolved_url, auth=admin_auth) as admin:
            fetched = await admin.get_raw(f"/api/oAuth2Clients/{creds.uid}")
            if fetched.get("clientId") != resolved_client_id:
                _fail(f"round-trip mismatch: expected clientId={resolved_client_id!r}, got {fetched!r}")
                raise typer.Exit(1)
            _ok(f"round-trip: clientId={fetched.get('clientId')!r}, redirectUris={fetched.get('redirectUris')!r}")
            if keep:
                _ok(f"--keep set; OAuth2 client {creds.uid} left in place")
                return
            _step(f"delete /api/oAuth2Clients/{creds.uid}")
            await admin.delete_raw(f"/api/oAuth2Clients/{creds.uid}")
            _ok("deleted")

    asyncio.run(_run())
    _pass(started)


@app.command("all")
def sample_all_command(
    url: Annotated[str | None, typer.Option("--url", help="DHIS2 base URL (also: DHIS2_URL env).")] = None,
    admin_user: Annotated[str | None, typer.Option("--admin-user")] = None,
    keep: Annotated[bool, typer.Option("--keep", help="Don't delete the fixtures afterwards.")] = False,
) -> None:
    """Run every sample in sequence — route, data-value, pat, oauth2-client."""
    typer.secho("=== dhis2 dev sample route ===", fg=typer.colors.MAGENTA, bold=True)
    sample_route_command(keep=keep)
    typer.echo()
    typer.secho("=== dhis2 dev sample data-value ===", fg=typer.colors.MAGENTA, bold=True)
    sample_data_value_command(keep=keep)
    typer.echo()
    typer.secho("=== dhis2 dev sample pat ===", fg=typer.colors.MAGENTA, bold=True)
    sample_pat_command(url=url, admin_user=admin_user, keep=keep)
    typer.echo()
    typer.secho("=== dhis2 dev sample oauth2-client ===", fg=typer.colors.MAGENTA, bold=True)
    sample_oauth2_client_command(url=url, admin_user=admin_user, keep=keep)
