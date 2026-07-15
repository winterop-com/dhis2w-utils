"""The effective-access closure: who can concretely read or write each object, and by what path.

`compute_effective_access` materializes, per object, the set of grant paths (owner, direct share,
group share, public, superuser, external) and the count of distinct enabled users holding each access
axis. Grants stay principal-level so the closure is bounded on instances with large groups; the count
of individuals is resolved by expanding group memberships once, server-side, and only the totals are
stored. Superusers (any role granting ALL) bypass sharing entirely, so they are counted on every
object regardless of its sharing block.

Honesty boundaries (also carried as graph caveats): the counts are a sharing-level upper bound; a
user's org-unit capture and data-view scope narrows actual data access further, and public access is
modeled as "every authenticated user" without resolving the per-type authority each user would need.
"""

from __future__ import annotations

from dhis2w_core.security_core.sharing.model import (
    AccessBits,
    EffectiveAccess,
    EffectiveGrant,
    PrincipalKind,
    ProvenanceKind,
    ShareEdge,
    SharingGraph,
    UserNode,
)

# The full-access grant an owner and a superuser hold (read+write on metadata and data).
_FULL_ACCESS = AccessBits(meta_read=True, meta_write=True, data_read=True, data_write=True)


def compute_effective_access(graph: SharingGraph) -> list[EffectiveAccess]:
    """Compute the effective access (grants + per-axis enabled-user counts) for every object node."""
    enabled = {user.uid: user for user in graph.users if not user.disabled}
    enabled_count = len(enabled)
    superuser_uids = {uid for uid, user in enabled.items() if user.superuser}
    members_by_group = _members_by_group(graph, enabled)
    shares_by_object = _shares_by_object(graph)
    return [
        _object_effective(
            obj_uid=object_node.uid,
            owner=object_node.owner,
            public=object_node.public,
            external=object_node.external,
            shares=shares_by_object.get(object_node.uid, []),
            enabled=enabled,
            enabled_count=enabled_count,
            superuser_uids=superuser_uids,
            members_by_group=members_by_group,
        )
        for object_node in graph.objects
    ]


def _members_by_group(graph: SharingGraph, enabled: dict[str, UserNode]) -> dict[str, set[str]]:
    """Map each group to the set of its enabled members (disabled accounts cannot exercise access)."""
    members: dict[str, set[str]] = {}
    for membership in graph.memberships:
        if membership.user_uid in enabled:
            members.setdefault(membership.group_uid, set()).add(membership.user_uid)
    return members


def _shares_by_object(graph: SharingGraph) -> dict[str, list[ShareEdge]]:
    """Index the explicit user/group share edges by the object they target."""
    shares: dict[str, list[ShareEdge]] = {}
    for share in graph.shares:
        shares.setdefault(share.object_uid, []).append(share)
    return shares


def _object_effective(
    *,
    obj_uid: str,
    owner: str | None,
    public: AccessBits,
    external: bool,
    shares: list[ShareEdge],
    enabled: dict[str, UserNode],
    enabled_count: int,
    superuser_uids: set[str],
    members_by_group: dict[str, set[str]],
) -> EffectiveAccess:
    """Resolve one object's grant paths and the distinct enabled-user count holding each access axis."""
    # Superusers bypass sharing, so they hold every axis on every object.
    axes: dict[str, set[str]] = {
        "meta_read": set(superuser_uids),
        "meta_write": set(superuser_uids),
        "data_read": set(superuser_uids),
        "data_write": set(superuser_uids),
    }
    grants: list[EffectiveGrant] = []

    if owner is not None and owner in enabled:
        for axis_users in axes.values():
            axis_users.add(owner)
        grants.append(
            EffectiveGrant(kind=ProvenanceKind.OWNER, principal_uid=owner, access=_FULL_ACCESS, subject_count=1)
        )

    for share in shares:
        if share.principal_kind is PrincipalKind.USER:
            if share.principal_uid in enabled:
                _add_axes(axes, {share.principal_uid}, share.access)
            grants.append(
                EffectiveGrant(
                    kind=ProvenanceKind.DIRECT, principal_uid=share.principal_uid, access=share.access, subject_count=1
                )
            )
        else:
            members = members_by_group.get(share.principal_uid, set())
            _add_axes(axes, members, share.access)
            grants.append(
                EffectiveGrant(
                    kind=ProvenanceKind.GROUP,
                    principal_uid=share.principal_uid,
                    access=share.access,
                    subject_count=len(members),
                )
            )

    if not public.grants_nothing:
        grants.append(EffectiveGrant(kind=ProvenanceKind.PUBLIC, access=public, subject_count=enabled_count))
    if superuser_uids:
        grants.append(
            EffectiveGrant(kind=ProvenanceKind.SUPERUSER, access=_FULL_ACCESS, subject_count=len(superuser_uids))
        )
    if external:
        grants.append(EffectiveGrant(kind=ProvenanceKind.EXTERNAL, access=public, subject_count=0))

    return EffectiveAccess(
        object_uid=obj_uid,
        grants=grants,
        meta_readers=_count(axes["meta_read"], enabled_count, public.meta_read),
        meta_writers=_count(axes["meta_write"], enabled_count, public.meta_write),
        data_readers=_count(axes["data_read"], enabled_count, public.data_read),
        data_writers=_count(axes["data_write"], enabled_count, public.data_write),
        public_meta_read=public.meta_read,
        public_meta_write=public.meta_write,
        public_data_read=public.data_read,
        public_data_write=public.data_write,
        external=external,
    )


def _add_axes(axes: dict[str, set[str]], user_uids: set[str], access: AccessBits) -> None:
    """Add the given users to each axis set their access grants."""
    if access.meta_read:
        axes["meta_read"].update(user_uids)
    if access.meta_write:
        axes["meta_write"].update(user_uids)
    if access.data_read:
        axes["data_read"].update(user_uids)
    if access.data_write:
        axes["data_write"].update(user_uids)


def _count(axis_users: set[str], enabled_count: int, is_public: bool) -> int:
    """Effective count for one axis: every enabled user when public grants it, else the distinct set."""
    return enabled_count if is_public else len(axis_users)
