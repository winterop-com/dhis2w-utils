"""Typed sharing helpers — read + replace the sharing block on any DHIS2 object.

Shows:
1. `get_sharing(client, resource_type, uid)` — fetch the current block.
2. `SharingBuilder` — fluent builder that keeps existing grants and appends new ones.
3. `apply_sharing(client, resource_type, uid, builder)` — POST /api/sharing.

Uses the seeded Child Programme UID (`IpHINAT79UW`). Grants admin a
user-access grant, reads the block back, then clears everything.

Usage:
    uv run python examples/client/sharing.py

Env: same as 01_whoami.py.
"""

from __future__ import annotations

from _runner import run_example
from dhis2w_client import (
    ACCESS_NONE,
    ACCESS_READ_METADATA,
    ACCESS_READ_WRITE_METADATA,
    SharingBuilder,
    apply_sharing,
    get_sharing,
)
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import profile_from_env

PROGRAM_UID = "IpHINAT79UW"  # Child Programme.


async def main() -> None:
    """Read + mutate the sharing block on one program, then restore it."""
    async with open_client(profile_from_env()) as client:
        me = await client.system.me()
        admin_uid = str(me.id)

        print(f">>> initial sharing for program {PROGRAM_UID}")
        sharing = await get_sharing(client, "program", PROGRAM_UID)
        print(
            f"    publicAccess={sharing.publicAccess}  "
            f"owner={sharing.user.id if sharing.user else '-'}  "
            f"userAccesses={len(sharing.userAccesses or [])}  "
            f"userGroupAccesses={len(sharing.userGroupAccesses or [])}"
        )

        print("\n>>> grant admin metadata r/w + keep everything else")
        builder = SharingBuilder(
            public_access=sharing.publicAccess or ACCESS_READ_METADATA,
            owner_user_id=sharing.user.id if sharing.user else admin_uid,
        )
        # Replay existing grants so we don't drop anyone.
        for user_access in sharing.userAccesses or []:
            if user_access.id and user_access.access:
                builder = builder.grant_user(user_access.id, user_access.access)
        for group_access in sharing.userGroupAccesses or []:
            if group_access.id and group_access.access:
                builder = builder.grant_user_group(group_access.id, group_access.access)
        builder = builder.grant_user(admin_uid, ACCESS_READ_WRITE_METADATA)
        envelope = await apply_sharing(client, "program", PROGRAM_UID, builder)
        print(f"    status: {envelope.httpStatus or envelope.status or '(none)'}")

        print("\n>>> re-read to confirm the grant landed")
        updated = await get_sharing(client, "program", PROGRAM_UID)
        for ua in updated.userAccesses or []:
            print(f"    user {ua.id} access={ua.access} displayName={ua.displayName}")

        print("\n>>> clear added user-access (restore initial state)")
        restored = SharingBuilder(
            public_access=sharing.publicAccess or ACCESS_READ_METADATA,
            owner_user_id=sharing.user.id if sharing.user else None,
        )
        for user_access in sharing.userAccesses or []:
            if user_access.id and user_access.access:
                restored = restored.grant_user(user_access.id, user_access.access)
        for group_access in sharing.userGroupAccesses or []:
            if group_access.id and group_access.access:
                restored = restored.grant_user_group(group_access.id, group_access.access)
        await apply_sharing(client, "program", PROGRAM_UID, restored)
        print("    restored")

        # `access_string` composes the 8-char grant patterns.
        assert ACCESS_NONE == "--------"
        assert ACCESS_READ_WRITE_METADATA == "rw------"


if __name__ == "__main__":
    run_example(main)
