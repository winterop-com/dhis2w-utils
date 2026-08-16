"""Full CRUD lifecycle for an organisation unit.

Shows the four verbs on the typed `client.resources.organisation_units`
accessor — `create`, `get`, `update` (PUT with the whole object), and
`delete` — plus a JSON-Patch update via the escape-hatch `patch_raw`
for the DHIS2 operations the generator doesn't cover yet. Cleans up
even on failure via a try/finally.

UIDs are minted client-side via `dhis2w_client.generate_uid` — same
algorithm as `dhis2w-core/CodeGenerator.java`, no DHIS2 round-trip.

Usage:
    uv run python examples/05_org_unit_crud.py

Env: same as 01_whoami.py.
"""

from __future__ import annotations

from datetime import datetime

from _runner import run_example
from dhis2w_client import NoProfileError, generate_uid, open_client, profile_from_env_raw

# v42 is the canonical baseline: swap `.v42` for `.v41` / `.v43` to pin another major.
from dhis2w_client.generated.v42.common import Reference
from dhis2w_client.generated.v42.schemas import OrganisationUnit

PARENT_UID = "ImspTQPwCqd"  # seeded in infra/v42/dump.sql.gz — "Sierra Leone"


async def main() -> None:
    """Create, read, patch, delete one org unit under the Sierra Leone root."""
    profile = profile_from_env_raw()
    if profile is None:
        raise NoProfileError("set DHIS2_URL + DHIS2_PAT (or DHIS2_USERNAME + DHIS2_PASSWORD)")
    async with open_client(profile) as client:
        uid = generate_uid()
        print(f"minted UID: {uid}")

        new_ou = OrganisationUnit(
            id=uid,
            code=f"EX_OU_{uid}",
            name=f"Example clinic {uid}",
            shortName=f"Ex {uid[:6]}",
            openingDate=datetime(2025, 1, 1),
            parent=Reference(id=PARENT_UID),
        )
        created = await client.resources.organisation_units.create(new_ou)
        print(f"\nCREATE  {created.get('status', '?')}  uid={uid}")

        try:
            fetched = await client.resources.organisation_units.get(
                uid,
                fields="id,code,name,shortName,level,parent[id,name]",
            )
            print(f"READ    id={fetched.id}  name={fetched.name}  shortName={fetched.shortName}")

            # JSON Patch — use patch_raw because the typed accessor models full PUT,
            # not partial patches. The raw body here is a well-typed pydantic-free
            # JSON Patch array (RFC 6902).
            await client.patch_raw(
                f"/api/organisationUnits/{uid}",
                [{"op": "replace", "path": "/shortName", "value": f"Updated {uid[:6]}"}],
            )
            updated = await client.resources.organisation_units.get(uid, fields="id,shortName,lastUpdated")
            print(f"PATCH   shortName={updated.shortName}  lastUpdated={updated.lastUpdated}")
        finally:
            deleted = await client.resources.organisation_units.delete(uid)
            print(f"\nDELETE  {deleted.get('status', '?')}  uid={uid}")


if __name__ == "__main__":
    run_example(main)
