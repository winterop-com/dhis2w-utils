"""The sharing access graph: one versioned `SharingGraph` that the findings and explorer project from.

`model.py` is the locked contract (nodes, edges, decoded access). `builder.py` assembles the graph
from version-neutral fetched records. `check.py` reduces the graph into the `sharing` audit findings.
`effective.py` computes the effective-access closure; `view.py` and `explorer.py` (PR 7b) project the
graph into the static d3 explorer bundle.
"""

from __future__ import annotations

from dhis2w_core.security_core.sharing.builder import (
    FetchedGroup,
    FetchedObject,
    FetchedRole,
    FetchedShare,
    FetchedUser,
    TypeInventory,
    build_sharing_graph,
)
from dhis2w_core.security_core.sharing.check import evaluate_sharing
from dhis2w_core.security_core.sharing.effective import compute_effective_access
from dhis2w_core.security_core.sharing.explorer import ExplorerRenderer
from dhis2w_core.security_core.sharing.focus import (
    SHARING_FOCUS_TYPES,
    ResolvedFocusType,
    SchemaShareability,
    SharingFocusType,
    resolve_focus_types,
)
from dhis2w_core.security_core.sharing.model import (
    SHARING_CAVEATS,
    SHARING_SCHEMA_VERSION,
    AccessBits,
    EffectiveAccess,
    EffectiveGrant,
    ManageEdge,
    MembershipEdge,
    ObjectNode,
    PrincipalKind,
    ProvenanceKind,
    RoleGrantEdge,
    RoleNode,
    ShareEdge,
    SharingGraph,
    TypeSummary,
    UserGroupNode,
    UserNode,
)
from dhis2w_core.security_core.sharing.view import SharingExplorerMeta, SharingView, build_sharing_view

__all__ = [
    "SHARING_CAVEATS",
    "SHARING_FOCUS_TYPES",
    "SHARING_SCHEMA_VERSION",
    "AccessBits",
    "EffectiveAccess",
    "EffectiveGrant",
    "ExplorerRenderer",
    "FetchedGroup",
    "FetchedObject",
    "FetchedRole",
    "FetchedShare",
    "FetchedUser",
    "ManageEdge",
    "MembershipEdge",
    "ObjectNode",
    "PrincipalKind",
    "ProvenanceKind",
    "ResolvedFocusType",
    "RoleGrantEdge",
    "RoleNode",
    "SchemaShareability",
    "ShareEdge",
    "SharingExplorerMeta",
    "SharingFocusType",
    "SharingGraph",
    "SharingView",
    "TypeInventory",
    "TypeSummary",
    "UserGroupNode",
    "UserNode",
    "build_sharing_graph",
    "build_sharing_view",
    "compute_effective_access",
    "evaluate_sharing",
    "resolve_focus_types",
]
