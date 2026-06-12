"""User groups + user roles via the Python client.

Read + mutate the user group and user role surface without going through the
CLI — everything the `d2w user-group` and `d2w user-role` commands do is
one httpx call over the typed OAS models.

1. List user groups + their member counts.
2. Fetch one group + show its current sharing block.
3. List user roles + their authority counts.
4. Walk one role's authorities.
5. (commented) membership edits.

Usage:
    uv run python examples/v41/client/user_groups_and_roles.py

Env: same as 01_whoami.py.
"""

from __future__ import annotations

from _runner import run_example
from dhis2w_client import get_sharing
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import profile_from_env


async def main() -> None:
    """Enumerate + inspect groups + roles against the seeded fixture."""
    async with open_client(profile_from_env()) as client:
        groups = await client.resources.user_groups.list(fields="id,displayName,users")
        print(f">>> {len(groups)} user groups:")
        for group in groups:
            members = group.users or []
            print(f"  {group.displayName!r:<20}  {group.id}  ({len(members)} member{'s' if len(members) != 1 else ''})")

        if groups:
            first = groups[0]
            print(f"\n>>> sharing block for user group {first.displayName!r} ({first.id}):")
            sharing = await get_sharing(client, "userGroup", str(first.id))
            print(f"    publicAccess={sharing.publicAccess}")
            print(f"    owner={sharing.user.id if sharing.user else '-'}")
            print(f"    userAccesses={len(sharing.userAccesses or [])}")
            print(f"    userGroupAccesses={len(sharing.userGroupAccesses or [])}")

        roles = await client.resources.user_roles.list(fields="id,displayName,authorities,users")
        print(f"\n>>> {len(roles)} user roles:")
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

        # Mutations — uncomment on a real instance.
        #
        # await client.post_raw(f"/api/userGroups/{group_uid}/users/{user_uid}", {})
        # await client.delete_raw(f"/api/userGroups/{group_uid}/users/{user_uid}")
        # await client.post_raw(f"/api/userRoles/{role_uid}/users/{user_uid}", {})
        # await client.delete_raw(f"/api/userRoles/{role_uid}/users/{user_uid}")


if __name__ == "__main__":
    run_example(main)
