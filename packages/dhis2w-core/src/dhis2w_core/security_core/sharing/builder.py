"""Assemble a `SharingGraph` from version-neutral fetched records, decoding access once.

The per-tree wiring fetches the sharing-bearing endpoints, maps each raw record into the `Fetched*`
input models here (so no response dict crosses a module boundary), and calls `build_sharing_graph`.
The builder is UI-agnostic and version-invariant: it decodes every access string, derives each user's
superuser flag from the roles they hold, emits the sharing and identity edges, and rolls per-type
counts into `TypeSummary`. The `sharing` findings and the explorer are both projections of its output.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from dhis2w_core.security_core.sharing.model import (
    SHARING_CAVEATS,
    AccessBits,
    ManageEdge,
    MembershipEdge,
    ObjectNode,
    PrincipalKind,
    RoleGrantEdge,
    RoleNode,
    ShareEdge,
    SharingGraph,
    TypeSummary,
    UserGroupNode,
    UserNode,
)

_ALL_AUTHORITY = "ALL"


class FetchedShare(BaseModel):
    """One explicit user or group share as fetched: the principal uid and its raw access string."""

    model_config = ConfigDict(frozen=True)

    principal_uid: str
    access: str


class FetchedObject(BaseModel):
    """One shareable object as fetched, with its type, data-bearing flag, and raw sharing block."""

    model_config = ConfigDict(frozen=True)

    uid: str
    type: str
    name: str
    code: str | None = None
    data_bearing: bool = False
    owner: str | None = None
    public_access: str | None = None
    external: bool = False
    user_shares: list[FetchedShare] = []
    group_shares: list[FetchedShare] = []

    @property
    def has_non_default_sharing(self) -> bool:
        """True when this object deviates from the private default, so it is worth keeping in the graph.

        The default is public `--------` with no external flag and no explicit user/group shares.
        Anything beyond that (any public bit, external access, or an explicit share) is retained.
        """
        public_custom = not AccessBits.decode(self.public_access).grants_nothing
        return public_custom or self.external or bool(self.user_shares) or bool(self.group_shares)


class FetchedUser(BaseModel):
    """One user account as fetched, with the roles and groups it belongs to."""

    model_config = ConfigDict(frozen=True)

    uid: str
    username: str
    display_name: str | None = None
    disabled: bool = False
    last_login: str | None = None
    two_factor: bool | None = None
    role_uids: list[str] = []
    group_uids: list[str] = []


class FetchedRole(BaseModel):
    """One user role as fetched, with its authorities and member count."""

    model_config = ConfigDict(frozen=True)

    uid: str
    name: str
    authorities: list[str] = []
    member_count: int = 0


class FetchedGroup(BaseModel):
    """One user group as fetched, with its member count and the groups it manages."""

    model_config = ConfigDict(frozen=True)

    uid: str
    name: str
    member_count: int = 0
    managed_group_uids: list[str] = []


class TypeInventory(BaseModel):
    """One shareable type's fetch accounting: its data-bearing flag and the total objects on the server."""

    model_config = ConfigDict(frozen=True)

    type: str
    data_bearing: bool = False
    total: int = 0


class FocusTypeScan(BaseModel):
    """One focus type's paging result: the server-reported total, retained objects, and cap state.

    Returned by each tree's `_scan_focus_type`, which pages `/api/<plural>` for one shareable type
    up to a scan budget. `scanned` counts every object inspected (kept or not); `capped` is set when
    the budget was exhausted before the type's pages ran out, so the caller knows to stop.
    """

    model_config = ConfigDict(frozen=True)

    server_total: int = 0
    kept: list[FetchedObject] = []
    scanned: int = 0
    capped: bool = False


def build_sharing_graph(
    *,
    target: str,
    generated_at: str,
    objects: list[FetchedObject],
    users: list[FetchedUser],
    roles: list[FetchedRole],
    groups: list[FetchedGroup],
    type_inventory: list[TypeInventory],
    truncated: bool = False,
    truncation_note: str | None = None,
) -> SharingGraph:
    """Build the unified access graph from fetched records, decoding access and deriving superusers."""
    role_nodes = [_role_node(role) for role in roles]
    all_role_uids = {role.uid for role in role_nodes if role.grants_all}
    user_nodes = [_user_node(user, all_role_uids) for user in users]
    group_nodes = [UserGroupNode(uid=group.uid, name=group.name, member_count=group.member_count) for group in groups]

    object_nodes = [_object_node(fetched_object) for fetched_object in objects]
    shares = [edge for fetched_object in objects for edge in _share_edges(fetched_object)]
    memberships = [MembershipEdge(user_uid=u.uid, group_uid=g) for u in users for g in u.group_uids]
    role_grants = [RoleGrantEdge(user_uid=u.uid, role_uid=r) for u in users for r in u.role_uids]
    manages = [
        ManageEdge(manager_group_uid=group.uid, managed_group_uid=managed)
        for group in groups
        for managed in group.managed_group_uids
    ]

    return SharingGraph(
        target=target,
        generated_at=generated_at,
        objects=object_nodes,
        users=user_nodes,
        groups=group_nodes,
        roles=role_nodes,
        shares=shares,
        memberships=memberships,
        role_grants=role_grants,
        manages=manages,
        type_summary=_type_summaries(objects, type_inventory),
        truncated=truncated,
        truncation_note=truncation_note,
        caveats=list(SHARING_CAVEATS),
    )


def _role_node(role: FetchedRole) -> RoleNode:
    """Build a role node, flagging it superuser-conferring when it grants the ALL authority."""
    return RoleNode(
        uid=role.uid,
        name=role.name,
        authorities=sorted(set(role.authorities)),
        grants_all=_ALL_AUTHORITY in role.authorities,
        member_count=role.member_count,
    )


def _user_node(user: FetchedUser, all_role_uids: set[str]) -> UserNode:
    """Build a user node, marking it a superuser when any of its roles grants ALL."""
    return UserNode(
        uid=user.uid,
        username=user.username,
        display_name=user.display_name,
        disabled=user.disabled,
        last_login=user.last_login,
        superuser=any(role_uid in all_role_uids for role_uid in user.role_uids),
        two_factor=user.two_factor,
    )


def _object_node(fetched_object: FetchedObject) -> ObjectNode:
    """Build an object node with its public access decoded and its external flag carried through."""
    return ObjectNode(
        uid=fetched_object.uid,
        type=fetched_object.type,
        name=fetched_object.name,
        code=fetched_object.code,
        data_bearing=fetched_object.data_bearing,
        owner=fetched_object.owner,
        public=AccessBits.decode(fetched_object.public_access),
        external=fetched_object.external,
    )


def _share_edges(fetched_object: FetchedObject) -> list[ShareEdge]:
    """Emit one decoded share edge per explicit user and group share on an object."""
    edges = [
        ShareEdge(
            object_uid=fetched_object.uid,
            principal_kind=PrincipalKind.USER,
            principal_uid=share.principal_uid,
            access=AccessBits.decode(share.access),
        )
        for share in fetched_object.user_shares
    ]
    edges.extend(
        ShareEdge(
            object_uid=fetched_object.uid,
            principal_kind=PrincipalKind.GROUP,
            principal_uid=share.principal_uid,
            access=AccessBits.decode(share.access),
        )
        for share in fetched_object.group_shares
    )
    return edges


def _type_summaries(objects: list[FetchedObject], type_inventory: list[TypeInventory]) -> list[TypeSummary]:
    """Roll the retained objects into per-type counts, keyed off the full per-type inventory totals."""
    kept_by_type: dict[str, list[FetchedObject]] = {}
    for fetched_object in objects:
        kept_by_type.setdefault(fetched_object.type, []).append(fetched_object)
    summaries: list[TypeSummary] = []
    for entry in type_inventory:
        kept = kept_by_type.get(entry.type, [])
        summaries.append(
            TypeSummary(
                type=entry.type,
                total=entry.total,
                with_custom_sharing=len(kept),
                public_count=sum(
                    1 for fetched_object in kept if not AccessBits.decode(fetched_object.public_access).grants_nothing
                ),
                external_count=sum(1 for fetched_object in kept if fetched_object.external),
                data_bearing=entry.data_bearing,
            )
        )
    return summaries
