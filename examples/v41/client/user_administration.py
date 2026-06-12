"""User administration via the Python client.

Walkthrough of the user domain:

1. List users (with a typed filter + order + paging).
2. Fetch the authenticated user's full `/api/me` payload.
3. Fetch a specific user by UID.
4. (Commented) invite a new user via POST /api/users/invite.
5. (Commented) reset their password via POST /api/users/{uid}/reset.

Uses the generated `/api/users` resource accessor — the same accessor
the `d2w user list/get` CLI commands sit on. Mutations use the
dedicated `/invite` and `/reset` endpoints that the generated CRUD
doesn't cover.

Usage:
    uv run python examples/v41/client/user_administration.py

Env: same as 01_whoami.py.
"""

from __future__ import annotations

from _runner import run_example
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import profile_from_env


async def main() -> None:
    """Read + print a few user slices; show the POST shapes without hitting them."""
    async with open_client(profile_from_env()) as client:
        # 1. List — same accessor the `d2w user list` CLI uses.
        users = await client.resources.users.list(
            fields="id,username,displayName,email,disabled,lastLogin",
            filters=["disabled:eq:false"],
            order=["lastLogin:desc"],
            page_size=5,
        )
        print(f">>> {len(users)} active users (sorted by lastLogin):")
        for user in users:
            print(f"  {user.id}  {user.username}  last_login={user.lastLogin}")

        # 2. /api/me — the authenticated user's richer profile.
        me = await client.system.me()
        print(f"\n>>> authenticated as {me.username} ({me.id})")
        print(f"    authorities: {len(me.authorities or [])} granted")

        # 3. Fetch a specific user by UID.
        if users:
            first = await client.resources.users.get(str(users[0].id))
            print(f"\n>>> {first.username} email={first.email or '-'}")

        # 4. Invite — commented because it hits real DHIS2 state.
        #
        # from dhis2w_client.v42.envelopes import WebMessageResponse
        # invite_payload = {
        #     "email": "alice@example.com",
        #     "firstName": "Alice",
        #     "surname": "Example",
        #     "username": "alice",
        #     "userRoles": [{"id": "<ROLE_UID>"}],
        #     "organisationUnits": [{"id": "ImspTQPwCqd"}],
        # }
        # raw = await client.post_raw("/api/users/invite", invite_payload)
        # envelope = WebMessageResponse.model_validate(raw)
        # print(f"invited {invite_payload['email']} -> user {envelope.created_uid}")

        # 5. Password reset — commented for the same reason.
        #
        # raw = await client.post_raw(f"/api/users/{uid}/reset", {})
        # envelope = WebMessageResponse.model_validate(raw)
        # assert envelope.status == "OK"


if __name__ == "__main__":
    run_example(main)
