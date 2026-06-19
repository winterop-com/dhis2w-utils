"""The SharingGraph contract: the single versioned access graph every projection reads.

The `sharing` findings and the (later) interactive explorer are both reductions over one graph
built once per scan, never derived independently. Users, roles, and groups are first-class nodes,
not edge labels: the `UserNode` is the join between the identity/RBAC graph (HAS_ROLE, MEMBER_OF,
MANAGES) and the sharing/ACL graph (SHARES). Every DHIS2 access string is decoded once into a typed
`AccessBits` so no projection ever parses access characters and the data axis is never confused with
the metadata axis.

The access string is verified against the DHIS2 source (`AccessStringHelper`): position 0 is
metadata read, 1 metadata write, 2 data read, 3 data write, 4-7 reserved. `rwrw----` is full
metadata + data, `rw------` metadata only, `r-r-----` read metadata + read data, `--------` none.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict

# The current SharingGraph wire-schema version. Bump when the serialized shape changes so a viewer
# reading an embedded graph can refuse a payload it does not understand.
SHARING_SCHEMA_VERSION = 1

# Honesty boundaries surfaced in every graph and the explorer UI, never silently assumed: a
# confidently-wrong "who can see this" is more dangerous than an explicit caveat.
SHARING_CAVEATS: tuple[str, ...] = (
    "Effective access is computed at the sharing level only; a user's org-unit capture and "
    "data-view scope narrows actual data access further.",
    "Superusers (any role granting the ALL authority) bypass sharing entirely and can reach every "
    "object regardless of its sharing block.",
    "Sub-object sharing (category option combos, program-stage sharing) is modeled at the object "
    "level, not the sub-object level.",
)


class PrincipalKind(StrEnum):
    """The kind of principal an explicit share edge points at."""

    USER = "user"
    GROUP = "group"


class ProvenanceKind(StrEnum):
    """How a user ends up with effective access to an object (populated by the closure in PR 7b)."""

    DIRECT = "direct"
    GROUP = "group"
    PUBLIC = "public"
    EXTERNAL = "external"
    SUPERUSER = "superuser"
    OWNER = "owner"


class AccessBits(BaseModel):
    """The four meaningful bits of a DHIS2 8-char access string, decoded once at build time."""

    model_config = ConfigDict(frozen=True)

    meta_read: bool = False
    meta_write: bool = False
    data_read: bool = False
    data_write: bool = False

    @classmethod
    def decode(cls, access: str | None) -> AccessBits:
        """Decode an 8-char access string into typed bits (pos 0 meta-read, 1 meta-write, 2/3 data)."""
        chars = access or ""

        def _is(position: int, expected: str) -> bool:
            return len(chars) > position and chars[position] == expected

        return cls(
            meta_read=_is(0, "r"),
            meta_write=_is(1, "w"),
            data_read=_is(2, "r"),
            data_write=_is(3, "w"),
        )

    @property
    def grants_nothing(self) -> bool:
        """True when no bit is set (the `--------` default), so this access conveys no rights."""
        return not (self.meta_read or self.meta_write or self.data_read or self.data_write)

    @property
    def has_write(self) -> bool:
        """True when either the metadata-write or data-write bit is set."""
        return self.meta_write or self.data_write


class ObjectNode(BaseModel):
    """One shareable metadata object: its identity, owner, and intrinsic public/external exposure."""

    model_config = ConfigDict(frozen=True)

    uid: str
    type: str
    name: str
    code: str | None = None
    data_bearing: bool = False
    owner: str | None = None
    public: AccessBits = AccessBits()
    external: bool = False


class UserNode(BaseModel):
    """One user account: the join between the identity graph and the sharing graph."""

    model_config = ConfigDict(frozen=True)

    uid: str
    username: str
    display_name: str | None = None
    disabled: bool = False
    last_login: str | None = None
    superuser: bool = False
    two_factor: bool | None = None


class UserGroupNode(BaseModel):
    """One user group: a principal that an object can be shared with, with its member count."""

    model_config = ConfigDict(frozen=True)

    uid: str
    name: str
    member_count: int = 0


class RoleNode(BaseModel):
    """One user role: the authorities it grants and whether it confers superuser (ALL)."""

    model_config = ConfigDict(frozen=True)

    uid: str
    name: str
    authorities: list[str] = []
    grants_all: bool = False
    member_count: int = 0


class ShareEdge(BaseModel):
    """An explicit share from an object to a user or group, with the decoded access it grants."""

    model_config = ConfigDict(frozen=True)

    object_uid: str
    principal_kind: PrincipalKind
    principal_uid: str
    access: AccessBits


class MembershipEdge(BaseModel):
    """A user's membership in a group (MEMBER_OF)."""

    model_config = ConfigDict(frozen=True)

    user_uid: str
    group_uid: str


class RoleGrantEdge(BaseModel):
    """A role granted to a user (HAS_ROLE)."""

    model_config = ConfigDict(frozen=True)

    user_uid: str
    role_uid: str


class ManageEdge(BaseModel):
    """A group's admin-delegation over another group (MANAGES, not membership inheritance)."""

    model_config = ConfigDict(frozen=True)

    manager_group_uid: str
    managed_group_uid: str


class EffectiveGrant(BaseModel):
    """One access path to an object: how it is granted, the access it confers, and who it resolves to.

    Grants are principal-level, never expanded to individual users, so the closure stays bounded on
    instances with large groups: a group grant carries the group uid and its member count rather than
    one edge per member. `principal_uid` is the user uid for owner/direct grants, the group uid for
    group grants, and None for the public/external/superuser pseudo-principals.
    """

    model_config = ConfigDict(frozen=True)

    kind: ProvenanceKind
    principal_uid: str | None = None
    access: AccessBits
    subject_count: int = 0


class EffectiveAccess(BaseModel):
    """The computed effective access to one object: the grant paths plus per-axis effective-user counts.

    Each `*_count` is the number of distinct enabled users who hold that axis (owner, direct shares,
    group members, and superusers, who bypass sharing). When the matching `public_*` flag is set the
    audience is every authenticated user, so the count is the enabled-user total and the UI should say
    "all users" rather than show a bare number. `external` marks the object as reachable anonymously.
    """

    model_config = ConfigDict(frozen=True)

    object_uid: str
    grants: list[EffectiveGrant] = []
    meta_readers: int = 0
    meta_writers: int = 0
    data_readers: int = 0
    data_writers: int = 0
    public_meta_read: bool = False
    public_meta_write: bool = False
    public_data_read: bool = False
    public_data_write: bool = False
    external: bool = False


class TypeSummary(BaseModel):
    """Per-type accounting: how many objects exist, how many were retained, and public/external counts."""

    model_config = ConfigDict(frozen=True)

    type: str
    total: int = 0
    with_custom_sharing: int = 0
    public_count: int = 0
    external_count: int = 0
    data_bearing: bool = False


class SharingGraph(BaseModel):
    """The unified access graph: object/principal nodes and the sharing/identity edges between them.

    Built once per scan and serialized as `window.__SHARING__` for the explorer. The `sharing`
    findings, the explorer views, and any future standalone app are all projections of this one
    object. `target` and `generated_at` are stamped by the CLI, never produced in the core, so the
    builder stays deterministic and testable.
    """

    model_config = ConfigDict(frozen=True)

    schema_version: int = SHARING_SCHEMA_VERSION
    target: str
    generated_at: str
    objects: list[ObjectNode] = []
    users: list[UserNode] = []
    groups: list[UserGroupNode] = []
    roles: list[RoleNode] = []
    shares: list[ShareEdge] = []
    memberships: list[MembershipEdge] = []
    role_grants: list[RoleGrantEdge] = []
    manages: list[ManageEdge] = []
    effective: list[EffectiveAccess] = []
    type_summary: list[TypeSummary] = []
    truncated: bool = False
    truncation_note: str | None = None
    caveats: list[str] = []
