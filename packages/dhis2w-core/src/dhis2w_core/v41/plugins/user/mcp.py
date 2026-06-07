"""FastMCP tool registration for the `user` plugin.

Read tools (`user_list`, `user_get`, `user_me`) are always safe.
`user_invite` creates a real user and dispatches email, so it's gated
behind the same write-tools-require-writing-creds convention other
plugins use: the tool is exposed, but callers driving autonomous
agents should scope profiles with read-only PATs if they don't want
writes.
"""

from __future__ import annotations

from typing import Any

from dhis2w_client.generated.v41.oas import User
from dhis2w_client.v41.envelopes import WebMessageResponse

from dhis2w_core.profile import resolve_profile
from dhis2w_core.v41.plugins.user import service
from dhis2w_core.v41.plugins.user.service import UserInvite


def register(mcp: Any) -> None:
    """Register user tools — list/get/me + invite/reinvite/reset-password."""

    @mcp.tool()
    async def user_list(
        fields: str = "id,username,displayName,email,disabled,lastLogin",
        filters: list[str] | None = None,
        root_junction: str | None = None,
        order: list[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        profile: str | None = None,
    ) -> list[User]:
        """List DHIS2 users.

        Accepts the full metadata query surface: fields selector, repeatable
        `filters` / `order`, `root_junction`, paging. `paging=False` returns
        every user in one response.
        """
        return await service.list_users(
            resolve_profile(profile),
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=paging,
        )

    @mcp.tool()
    async def user_get(
        uid_or_username: str,
        fields: str | None = None,
        profile: str | None = None,
    ) -> User:
        """Fetch one user by UID or username."""
        return await service.get_user(resolve_profile(profile), uid_or_username, fields=fields)

    @mcp.tool()
    async def user_invite(
        email: str,
        first_name: str,
        surname: str,
        username: str | None = None,
        user_role_uids: list[str] | None = None,
        org_unit_uids: list[str] | None = None,
        profile: str | None = None,
    ) -> WebMessageResponse:
        """Create a user + dispatch the invitation email (POST /api/users/invite)."""
        invite = UserInvite(
            email=email,
            firstName=first_name,
            surname=surname,
            username=username,
            userRoles=[{"id": uid} for uid in (user_role_uids or [])],
            organisationUnits=[{"id": uid} for uid in (org_unit_uids or [])],
        )
        return await service.invite_user(resolve_profile(profile), invite)

    @mcp.tool()
    async def user_reinvite(uid: str, profile: str | None = None) -> WebMessageResponse:
        """Re-send the invitation email for a pending user."""
        return await service.reinvite_user(resolve_profile(profile), uid)

    @mcp.tool()
    async def user_reset_password(uid: str, profile: str | None = None) -> WebMessageResponse:
        """Trigger DHIS2's password-reset email for a user."""
        return await service.reset_password(resolve_profile(profile), uid)
