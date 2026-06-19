"""v41-only — OAuth2 client wire-shape lies: response uses `cid`, not `clientId` (BUGS.md #39).

DHIS2 v41's `/api/oAuth2Clients` endpoint returns the client identifier
under the field `cid` instead of the documented `clientId`. v42 + v43
correctly use `clientId`.

Any code that round-trips an OAuth2 client by reading
`response.json()["clientId"]` will silently miss the value on v41 and
get `None`. The fix is to consult both fields (or specifically the
v41-correct `cid`) and prefer it when present.

This example fetches the existing OAuth2 clients seeded by
`make dhis2-run DHIS2_VERSION=41` and prints both `id` and `cid`
columns so the v41 wire shape is visible.

For the corresponding write-side fix, see
`dhis2w_core/v41/plugins/dev/sample.py` — the `d2w dev sample
oauth2-client` smoke test on v41 reads `fetched.get("cid")` first
and falls back to `clientId` for v42/v43 compatibility.

Usage:
    uv run python examples/v41/client/oauth2_cid_field.py
"""

from __future__ import annotations

from _runner import run_example
from dhis2w_core.profile import profile_from_env
from dhis2w_core.v41.client_context import open_client


async def main() -> None:
    """Fetch OAuth2 clients and show the v41 `cid` wire field."""
    async with open_client(profile_from_env()) as client:
        # `/api/oAuth2Clients` returns dicts with the v41-flavoured shape.
        # We use `get_raw` here because the wire field name diverges from
        # the documented schema — the typed accessor would mask it.
        envelope = await client.get_raw(
            "/api/oAuth2Clients", params={"fields": "id,name,cid,clientId,redirectUris", "paging": "false"}
        )
        rows = envelope.get("oAuth2Clients") or []
        print(f"v41 OAuth2 clients ({len(rows)}):")
        print(f"  {'id':16s}  {'cid (v41 wire)':30s}  {'clientId (v42/v43 docs)':25s}  name")
        for row in rows:
            uid = row.get("id", "?")
            cid = row.get("cid") or "(missing)"
            client_id = row.get("clientId") or "(missing)"
            name = row.get("name") or "(unnamed)"
            print(f"  {uid:16s}  {cid:30s}  {client_id:25s}  {name}")
        print()
        print("Note: on v41, the wire emits the identifier as `cid`. v42/v43 use `clientId`.")
        print("See BUGS.md #39 — the per-version handler is in `dhis2w_core/v41/plugins/dev/sample.py`.")


if __name__ == "__main__":
    run_example(main)
