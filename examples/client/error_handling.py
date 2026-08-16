"""Error handling — Dhis2ApiError, WebMessage conflicts, AuthenticationError.

Every DHIS2 non-2xx is raised as `Dhis2ApiError` with the full JSON body
attached. `error.web_message` lazily parses the body into a typed
`WebMessageResponse` so callers can inspect `conflicts[]`, `importCount`,
`rejectedIndexes[]`, and `errorReports[]` without re-parsing strings.

Usage:
    uv run python examples/client/error_handling.py

Env: same as 01_whoami.py.
"""

from __future__ import annotations

from _runner import run_example
from dhis2w_client import (
    AuthenticationError,
    BasicAuth,
    DataValue,
    DataValueSet,
    Dhis2ApiError,
    Dhis2Client,
)
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import profile_from_env


async def demo_409_with_conflicts(client: Dhis2Client) -> None:
    """Push a data value for a period outside the dataset's open-future window.

    DHIS2 returns 409 with a populated `conflicts[]` block describing the
    rejection — classic `E7641` (period past open-future-period window).
    """
    future = DataValueSet(
        dataValues=[
            DataValue(
                dataElement="fClA2Erf6IO",
                period="202712",  # far-future period the seeded dataset won't accept
                orgUnit="PMa2VCrupOd",
                value="99",
            ),
        ],
    )
    try:
        await client.post_raw("/api/dataValueSets", future.model_dump(exclude_none=True))
    except Dhis2ApiError as exc:
        print(f"\n[Dhis2ApiError] {exc.status_code}: {exc.message}")
        envelope = exc.web_message
        if envelope is None:
            print("  body was not a WebMessage dict")
            return
        counts = envelope.import_count()
        if counts is not None:
            print(
                f"  import_count: imported={counts.imported} updated={counts.updated}"
                f" ignored={counts.ignored} deleted={counts.deleted}"
            )
        for conflict in envelope.conflicts():
            print(f"  conflict: {conflict.property} = {conflict.value} [{conflict.errorCode}]")
        print(f"  rejected_indexes: {envelope.rejected_indexes()}")


async def demo_404(client: Dhis2Client) -> None:
    """GET a resource that doesn't exist — 404 -> Dhis2ApiError."""
    try:
        await client.resources.data_elements.get("nonexistent123")
    except Dhis2ApiError as exc:
        print(f"\n[Dhis2ApiError] {exc.status_code}: {exc.message}")
        if isinstance(exc.body, dict):
            print(f"  body message: {exc.body.get('message')}")


async def demo_auth_failure(base_url: str) -> None:
    """Wrong basic-auth password raises `AuthenticationError` (401)."""
    bad = Dhis2Client(base_url, auth=BasicAuth(username="admin", password="definitely-wrong"))
    try:
        async with bad as client:
            await client.system.me()
    except AuthenticationError as exc:
        print(f"\n[AuthenticationError] {exc}")
    except Dhis2ApiError as exc:
        # DHIS2 sometimes responds 400 (instead of 401) when the *credential
        # shape* is rejected (unknown PAT token, malformed header). Still a
        # typed `Dhis2ApiError` with a useful body.
        print(f"\n[Dhis2ApiError] {exc.status_code}: {exc.message}")


async def main() -> None:
    """Exercise the three error paths callers are most likely to hit."""
    async with open_client(profile_from_env()) as client:
        await demo_409_with_conflicts(client)
        await demo_404(client)
        # demo_auth_failure spins up a separate client with deliberately-wrong creds,
        # so pass through the base URL of the connected one.
        await demo_auth_failure(client.base_url)


if __name__ == "__main__":
    run_example(main)
