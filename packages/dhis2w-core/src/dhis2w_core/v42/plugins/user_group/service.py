"""Service layer for the `user-group` plugin — membership + sharing.

Reads ride on the generated `/api/userGroups` CRUD accessor so `list` / `get`
get the metadata query surface for free. Membership edits hit
`/api/userGroups/{uid}/members/{userId}` — DHIS2's dedicated single-member
endpoint that avoids the race of fetching + rewriting the whole group.
Sharing edits go through the typed `apply_sharing` helper.
"""

from __future__ import annotations

from typing import Any, cast

from dhis2w_client.generated.v42.oas import UserGroup
from dhis2w_client.v42 import (
    SharingBuilder,
    SharingObject,
    apply_sharing,
    get_sharing,
)
from dhis2w_client.v42.envelopes import WebMessageResponse

from dhis2w_core.profile import Profile
from dhis2w_core.v42.client_context import open_client


async def list_user_groups(
    profile: Profile,
    *,
    fields: str | None = None,
    filters: list[str] | None = None,
    root_junction: str | None = None,
    order: list[str] | None = None,
    page: int | None = None,
    page_size: int | None = None,
    paging: bool | None = None,
) -> list[UserGroup]:
    """List user groups (forwards every metadata query knob)."""
    async with open_client(profile) as client:
        groups = await client.resources.user_groups.list(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=paging,
        )
    return cast(list[UserGroup], groups)


async def get_user_group(profile: Profile, uid: str, *, fields: str | None = None) -> UserGroup:
    """Fetch one user group by UID."""
    async with open_client(profile) as client:
        group = await client.resources.user_groups.get(uid, fields=fields)
    return cast(UserGroup, group)


async def create_user_group(
    profile: Profile,
    *,
    name: str,
    code: str | None = None,
    uid: str | None = None,
) -> WebMessageResponse:
    """Create a UserGroup; returns the import-summary (new UID in response.uid)."""
    payload: dict[str, Any] = {"name": name}
    if code:
        payload["code"] = code
    if uid:
        payload["id"] = uid
    async with open_client(profile) as client:
        result = await client.resources.user_groups.create(UserGroup.model_validate(payload))
        return WebMessageResponse.model_validate(result)


async def delete_user_group(profile: Profile, uid: str) -> None:
    """Delete a UserGroup by UID."""
    async with open_client(profile) as client:
        await client.resources.user_groups.delete(uid)


async def add_member(profile: Profile, group_uid: str, user_uid: str) -> WebMessageResponse:
    """Add a user to a group via `POST /api/userGroups/{group}/users/{user}`.

    DHIS2 v42 names the collection `users` on UserGroup — `/members/` returns
    E1005 "Property members does not exist on org.hisp.dhis.user.UserGroup".
    """
    async with open_client(profile) as client:
        return await client.post(
            f"/api/userGroups/{group_uid}/users/{user_uid}",
            {},
            model=WebMessageResponse,
        )


async def remove_member(profile: Profile, group_uid: str, user_uid: str) -> WebMessageResponse:
    """Remove a user from a group via `DELETE /api/userGroups/{group}/users/{user}`."""
    async with open_client(profile) as client:
        return await client.delete(
            f"/api/userGroups/{group_uid}/users/{user_uid}",
            model=WebMessageResponse,
        )


async def get_group_sharing(profile: Profile, uid: str) -> SharingObject:
    """Fetch the sharing block for one user group."""
    async with open_client(profile) as client:
        return await get_sharing(client, "userGroup", uid)


async def apply_group_sharing(
    profile: Profile,
    uid: str,
    sharing: SharingObject | SharingBuilder,
) -> WebMessageResponse:
    """Replace the sharing block for one user group."""
    async with open_client(profile) as client:
        return await apply_sharing(client, "userGroup", uid, sharing)
