"""User roles via the Python client.

Read the user role surface without going through the CLI - everything the
`d2w user role` commands do is one httpx call over the typed OAS models.

1. List user roles + their authority counts.
2. Walk one role's authorities.
3. (commented) membership edits.

Usage:
    uv run python examples/client/user_roles.py

Env: same as 01_whoami.py.
"""

from __future__ import annotations

from _runner import run_example
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import profile_from_env


async def main() -> None:
    """Enumerate + inspect user roles against the seeded fixture."""
    async with open_client(profile_from_env()) as client:
        roles = await client.resources.user_roles.list(fields="id,displayName,authorities,users")
        print(f">>> {len(roles)} user roles:")
        for role in roles:
            authorities = role.authorities or []
            users = role.users or []
            print(f"  {role.displayName!r:<22}  {role.id}  authorities={len(authorities):>3}  users={len(users)}")

        if roles:
            role = roles[0]
            authorities = sorted(role.authorities or [])
            print(f"\n>>> first 10 authorities carried by role {role.displayName!r}:")
            for auth in authorities[:10]:
                print(f"  {auth}")
            if len(authorities) > 10:
                print(f"  ... +{len(authorities) - 10} more")

        # Membership edits - uncomment on a real instance.
        #
        # await client.post_raw(f"/api/userRoles/{role_uid}/users/{user_uid}", {})
        # await client.delete_raw(f"/api/userRoles/{role_uid}/users/{user_uid}")


if __name__ == "__main__":
    run_example(main)
