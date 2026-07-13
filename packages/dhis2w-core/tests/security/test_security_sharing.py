"""Sharing-check tests: access decoding, the graph builder, the findings reduction, and per-tree wiring.

`AccessBits`, `build_sharing_graph`, `evaluate_sharing`, and `resolve_focus_types` are
version-invariant and tested directly. The `_run_sharing` wiring (which pages the sharing endpoints,
maps the raw payloads into the version-neutral records, builds the graph once, and reduces it to
findings) is exercised against a mock client across all three version trees.
"""

from __future__ import annotations

from importlib import import_module
from pathlib import Path
from types import ModuleType
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from dhis2w_client.errors import Dhis2ApiError
from dhis2w_core.security_core import (
    CheckStatus,
    ExplorerRenderer,
    FetchedGroup,
    FetchedObject,
    FetchedRole,
    FetchedShare,
    FetchedUser,
    Severity,
    SharingGraph,
    TypeInventory,
    build_sharing_graph,
    build_sharing_view,
    compute_effective_access,
    evaluate_sharing,
)
from dhis2w_core.security_core.sharing import AccessBits, PrincipalKind, SchemaShareability, resolve_focus_types

TREES = ("v41", "v42", "v43")


def _titles(findings: list[Any]) -> set[str]:
    """Collect finding titles for membership assertions."""
    return {finding.title for finding in findings}


# ---------------------------------------------------------------------------
# AccessBits: decoded once, positions verified against AccessStringHelper
# ---------------------------------------------------------------------------


def test_access_bits_decode_positions() -> None:
    """Position 0 is meta-read, 1 meta-write, 2 data-read, 3 data-write (per the DHIS2 source)."""
    assert AccessBits.decode("rwrw----") == AccessBits(meta_read=True, meta_write=True, data_read=True, data_write=True)
    assert AccessBits.decode("rw------") == AccessBits(meta_read=True, meta_write=True)
    assert AccessBits.decode("r-r-----") == AccessBits(meta_read=True, data_read=True)
    assert AccessBits.decode("--------").grants_nothing
    assert AccessBits.decode(None).grants_nothing
    assert AccessBits.decode("").grants_nothing


def test_access_bits_helpers() -> None:
    """`has_write` is true for either write bit; `grants_nothing` is true only for the empty default."""
    assert AccessBits.decode("-w------").has_write
    assert AccessBits.decode("---w----").has_write
    assert not AccessBits.decode("r-r-----").has_write
    assert not AccessBits.decode("r-r-----").grants_nothing


# ---------------------------------------------------------------------------
# evaluate_sharing (version-invariant reduction over the graph)
# ---------------------------------------------------------------------------


def _graph(*objects: FetchedObject) -> SharingGraph:
    """Build a graph from object records alone, with empty principals and one matching inventory."""
    inventory = [TypeInventory(type=obj.type, data_bearing=obj.data_bearing, total=1) for obj in objects]
    return build_sharing_graph(
        target="https://x",
        generated_at="2026-06-20T00:00:00Z",
        objects=list(objects),
        users=[],
        roles=[],
        groups=[],
        type_inventory=inventory,
    )


def test_external_object_is_high() -> None:
    """An externally-accessible object is flagged HIGH and folds under the external group key."""
    findings = evaluate_sharing(_graph(FetchedObject(uid="m1", type="map", name="Ext", external=True)))
    external = [f for f in findings if f.title == "Object accessible without authentication"]
    assert external and external[0].severity is Severity.HIGH
    assert external[0].group_key == "sharing-external"
    assert external[0].subject == "Ext"


def test_public_write_data_bearing_is_high() -> None:
    """Public write on a data-bearing object is HIGH under the public-write-data group key."""
    findings = evaluate_sharing(
        _graph(FetchedObject(uid="ds1", type="dataSet", name="HIV", data_bearing=True, public_access="rwrw----"))
    )
    write = [f for f in findings if f.title == "Public write access to data-bearing object"]
    assert write and write[0].severity is Severity.HIGH
    assert write[0].group_key == "sharing-public-write-data"


def test_public_write_metadata_is_medium() -> None:
    """Public metadata write on a non-data-bearing object is MEDIUM, not HIGH."""
    findings = evaluate_sharing(
        _graph(FetchedObject(uid="doc1", type="document", name="Memo", data_bearing=False, public_access="rw------"))
    )
    write = [f for f in findings if f.title == "Public write access to metadata object"]
    assert write and write[0].severity is Severity.MEDIUM
    assert write[0].group_key == "sharing-public-write-metadata"


def test_public_readable_sql_view_is_medium() -> None:
    """A publicly-readable SQL view is its own MEDIUM finding, distinct from the data-read finding."""
    findings = evaluate_sharing(
        _graph(FetchedObject(uid="sv1", type="sqlView", name="Patients", data_bearing=True, public_access="r-r-----"))
    )
    sql = [f for f in findings if f.title == "SQL view readable by all users"]
    assert sql and sql[0].severity is Severity.MEDIUM
    assert sql[0].group_key == "sharing-public-sql-view"
    assert "Public read access to data-bearing object" not in _titles(findings)


def test_public_data_read_data_bearing_is_medium() -> None:
    """Public data read on a (non-SQL-view) data-bearing object is MEDIUM under the read group key."""
    findings = evaluate_sharing(
        _graph(FetchedObject(uid="pr1", type="program", name="TB", data_bearing=True, public_access="r-r-----"))
    )
    read = [f for f in findings if f.title == "Public read access to data-bearing object"]
    assert read and read[0].severity is Severity.MEDIUM
    assert read[0].group_key == "sharing-public-read-data"


def test_read_finding_suppressed_when_external() -> None:
    """An external object that is only publicly readable yields just the external finding, no read row."""
    findings = evaluate_sharing(
        _graph(
            FetchedObject(
                uid="pr1", type="program", name="TB", data_bearing=True, public_access="r-r-----", external=True
            )
        )
    )
    assert _titles(findings) == {"Object accessible without authentication"}


def test_write_and_external_both_flagged() -> None:
    """An object that is both external and publicly writable raises both findings (distinct audiences)."""
    findings = evaluate_sharing(
        _graph(
            FetchedObject(
                uid="ds1", type="dataSet", name="HIV", data_bearing=True, public_access="rwrw----", external=True
            )
        )
    )
    assert "Object accessible without authentication" in _titles(findings)
    assert "Public write access to data-bearing object" in _titles(findings)
    assert "Public read access to data-bearing object" not in _titles(findings)


def test_default_shared_object_has_no_finding() -> None:
    """A private (default-shared) object, even with an explicit group share, raises no public finding."""
    obj = FetchedObject(
        uid="ds1",
        type="dataSet",
        name="Private",
        data_bearing=True,
        public_access="--------",
        group_shares=[FetchedShare(principal_uid="g1", access="rwrw----")],
    )
    assert evaluate_sharing(_graph(obj)) == []


# ---------------------------------------------------------------------------
# build_sharing_graph (version-invariant)
# ---------------------------------------------------------------------------


def test_build_graph_derives_superuser_and_edges() -> None:
    """A user holding an ALL role is a superuser; membership, role-grant, and manage edges are emitted."""
    graph = build_sharing_graph(
        target="https://x",
        generated_at="t",
        objects=[
            FetchedObject(
                uid="ds1",
                type="dataSet",
                name="HIV",
                data_bearing=True,
                public_access="rwr-----",
                user_shares=[FetchedShare(principal_uid="u2", access="rw------")],
                group_shares=[FetchedShare(principal_uid="g1", access="r-------")],
            )
        ],
        users=[
            FetchedUser(uid="u1", username="admin", role_uids=["r_all"], group_uids=["g1"]),
            FetchedUser(uid="u2", username="bob", role_uids=["r_data"]),
        ],
        roles=[
            FetchedRole(uid="r_all", name="Super", authorities=["ALL"], member_count=1),
            FetchedRole(uid="r_data", name="Data", authorities=["F_DATAVALUE_ADD"], member_count=1),
        ],
        groups=[FetchedGroup(uid="g1", name="M&E", member_count=3, managed_group_uids=["g2"])],
        type_inventory=[TypeInventory(type="dataSet", data_bearing=True, total=5)],
    )
    assert next(u for u in graph.users if u.uid == "u1").superuser is True
    assert next(u for u in graph.users if u.uid == "u2").superuser is False
    assert next(r for r in graph.roles if r.uid == "r_all").grants_all is True
    user_share = next(s for s in graph.shares if s.principal_kind is PrincipalKind.USER)
    group_share = next(s for s in graph.shares if s.principal_kind is PrincipalKind.GROUP)
    assert user_share.principal_uid == "u2" and user_share.access.meta_write
    assert group_share.principal_uid == "g1"
    assert any(m.user_uid == "u1" and m.group_uid == "g1" for m in graph.memberships)
    assert any(rg.user_uid == "u1" and rg.role_uid == "r_all" for rg in graph.role_grants)
    assert any(mg.manager_group_uid == "g1" and mg.managed_group_uid == "g2" for mg in graph.manages)


def test_build_graph_type_summary_counts() -> None:
    """Type summary keeps the full server total but counts only retained public/external objects."""
    graph = build_sharing_graph(
        target="https://x",
        generated_at="t",
        objects=[
            FetchedObject(uid="a", type="dataSet", name="A", data_bearing=True, public_access="rwr-----"),
            FetchedObject(
                uid="b", type="dataSet", name="B", data_bearing=True, public_access="--------", external=True
            ),
        ],
        users=[],
        roles=[],
        groups=[],
        type_inventory=[TypeInventory(type="dataSet", data_bearing=True, total=42)],
    )
    summary = next(t for t in graph.type_summary if t.type == "dataSet")
    assert summary.total == 42
    assert summary.with_custom_sharing == 2
    assert summary.public_count == 1  # only A has public bits; B is default-public but external
    assert summary.external_count == 1
    assert summary.data_bearing is True


def test_build_graph_carries_caveats_and_truncation() -> None:
    """The graph always carries the honesty caveats and reflects the truncation flag and note."""
    graph = build_sharing_graph(
        target="https://x",
        generated_at="t",
        objects=[],
        users=[],
        roles=[],
        groups=[],
        type_inventory=[],
        truncated=True,
        truncation_note="capped",
    )
    assert graph.caveats and any("Superuser" in caveat for caveat in graph.caveats)
    assert graph.truncated is True and graph.truncation_note == "capped"
    assert graph.schema_version == 1


def test_non_default_sharing_predicate() -> None:
    """A FetchedObject is retained only when its sharing deviates from the private default."""
    assert not FetchedObject(uid="a", type="dataSet", name="A", public_access="--------").has_non_default_sharing
    assert FetchedObject(uid="a", type="dataSet", name="A", public_access="r-------").has_non_default_sharing
    assert FetchedObject(uid="a", type="dataSet", name="A", external=True).has_non_default_sharing
    assert FetchedObject(
        uid="a", type="dataSet", name="A", group_shares=[FetchedShare(principal_uid="g", access="r-------")]
    ).has_non_default_sharing


# ---------------------------------------------------------------------------
# resolve_focus_types (version-invariant)
# ---------------------------------------------------------------------------


def test_resolve_focus_types_intersects_and_marks_data_bearing() -> None:
    """Only focus types the server reports shareable survive; data-bearing comes from dataShareable."""
    schemas = [
        SchemaShareability(name="dataSet", plural="dataSets", shareable=True, data_shareable=True),
        SchemaShareability(name="document", plural="documents", shareable=True, data_shareable=False),
        SchemaShareability(name="dataElement", plural="dataElements", shareable=True, data_shareable=False),
    ]
    resolved = resolve_focus_types(schemas)
    by_name = {r.name: r for r in resolved}
    assert by_name["dataSet"].data_bearing is True
    assert by_name["document"].data_bearing is False
    assert "dataElement" not in by_name  # not in the curated focus set


def test_resolve_focus_types_drops_non_shareable() -> None:
    """A focus type the server marks non-shareable is dropped from the scan."""
    schemas = [SchemaShareability(name="dataSet", plural="dataSets", shareable=False, data_shareable=True)]
    assert resolve_focus_types(schemas) == []


# ---------------------------------------------------------------------------
# Per-tree wiring: _run_sharing pages the endpoints and reduces to findings
# ---------------------------------------------------------------------------


def _audit_module(tree: str) -> ModuleType:
    """Import the per-tree security audit module under test."""
    return import_module(f"dhis2w_core.{tree}.plugins.security.audit")


def _mock_sharing_client(
    *,
    schemas: list[dict[str, Any]],
    pages: dict[str, list[dict[str, Any]]],
    users: list[dict[str, Any]],
    roles: list[dict[str, Any]],
    groups: list[dict[str, Any]],
) -> MagicMock:
    """A client whose get_raw serves a staged /api/schemas, per-type object pages, and principals."""
    state: dict[str, int] = {}

    def get_raw(path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if path == "/api/schemas":
            return {"schemas": schemas}
        if path == "/api/users":
            return {"users": users}
        if path == "/api/userRoles":
            return {"userRoles": roles}
        if path == "/api/userGroups":
            return {"userGroups": groups}
        plural = path.removeprefix("/api/")
        page_list = pages.get(plural, [])
        index = state.get(plural, 0)
        state[plural] = index + 1
        if index < len(page_list):
            return page_list[index]
        return {plural: [], "pager": {"page": index + 1, "pageCount": index}}

    client = MagicMock()
    client.get_raw = AsyncMock(side_effect=get_raw)
    client.base_url = "https://mock.example"
    return client


def _object(uid: str, name: str, public: str, **extra: Any) -> dict[str, Any]:
    """Build a raw object record with a sharing block, mirroring the live wire shape."""
    sharing: dict[str, Any] = {
        "public": public,
        "external": extra.get("external", False),
        "users": {},
        "userGroups": {},
    }
    if "owner" in extra:
        sharing["owner"] = extra["owner"]
    return {"id": uid, "name": name, "sharing": sharing}


@pytest.mark.parametrize("tree", TREES)
async def test_run_sharing_flags_public_write_and_builds_findings(tree: str, tmp_path: Path) -> None:
    """_run_sharing scans the focus types, builds the graph once, and surfaces the public-write finding."""
    audit = _audit_module(tree)
    client = _mock_sharing_client(
        schemas=[{"name": "dataSet", "plural": "dataSets", "shareable": True, "dataShareable": True}],
        pages={
            "dataSets": [
                {
                    "dataSets": [_object("ds1", "HIV", "rwrw----"), _object("ds2", "Private", "--------")],
                    "pager": {"page": 1, "pageCount": 1, "total": 2},
                }
            ]
        },
        users=[{"id": "u1", "username": "admin", "userRoles": [{"id": "r_all"}]}],
        roles=[{"id": "r_all", "name": "Super", "authorities": ["ALL"], "users": 1}],
        groups=[{"id": "g1", "name": "M&E", "users": 3, "managedGroups": []}],
    )

    result = await audit._run_sharing(client, max_objects=5000, generated_at="t", output_folder=tmp_path)

    assert result.status is CheckStatus.OK
    assert result.note is None
    assert "Public write access to data-bearing object" in _titles(result.findings)
    # ds2 is default-shared, so it produces no finding
    assert all(f.subject != "Private" for f in result.findings)


@pytest.mark.parametrize("tree", TREES)
async def test_run_sharing_degrades_on_api_error(tree: str, tmp_path: Path) -> None:
    """An HTTP error while reading the sharing surface degrades the check rather than a false all-clear."""
    audit = _audit_module(tree)
    client = MagicMock()
    client.get_raw = AsyncMock(side_effect=Dhis2ApiError(500, "boom"))
    client.base_url = "https://mock.example"

    result = await audit._run_sharing(client, max_objects=5000, generated_at="t", output_folder=tmp_path)

    assert result.status is CheckStatus.DEGRADED
    assert result.findings == []


@pytest.mark.parametrize("tree", TREES)
async def test_run_sharing_truncates_at_budget(tree: str, tmp_path: Path) -> None:
    """When the scan budget is hit mid-type, the check notes the loud truncation and still returns OK."""
    audit = _audit_module(tree)
    client = _mock_sharing_client(
        schemas=[{"name": "dataSet", "plural": "dataSets", "shareable": True, "dataShareable": True}],
        pages={
            "dataSets": [
                {
                    "dataSets": [_object("ds1", "A", "rwrw----"), _object("ds2", "B", "rwrw----")],
                    "pager": {"page": 1, "pageCount": 1, "total": 2},
                }
            ]
        },
        users=[],
        roles=[],
        groups=[],
    )

    result = await audit._run_sharing(client, max_objects=1, generated_at="t", output_folder=tmp_path)

    assert result.status is CheckStatus.OK
    assert result.note is not None and "max-objects" in result.note


# ---------------------------------------------------------------------------
# compute_effective_access (version-invariant closure)
# ---------------------------------------------------------------------------


def _effective_graph() -> SharingGraph:
    """A graph with an object exercising owner, direct, group, public, and superuser grant paths."""
    return build_sharing_graph(
        target="x",
        generated_at="t",
        objects=[
            FetchedObject(
                uid="O",
                type="dataSet",
                name="HIV",
                data_bearing=True,
                owner="owner1",
                public_access="r-r-----",  # public meta-read + data-read for all authenticated
                user_shares=[FetchedShare(principal_uid="u_direct", access="-w------")],  # meta-write
                group_shares=[FetchedShare(principal_uid="g1", access="r-rw----")],  # meta+data read, data write
            )
        ],
        users=[
            FetchedUser(uid="owner1", username="owner"),
            FetchedUser(uid="u_direct", username="direct"),
            FetchedUser(uid="m1", username="m1", group_uids=["g1"]),
            FetchedUser(uid="m2", username="m2", group_uids=["g1"]),
            FetchedUser(uid="m3", username="m3", group_uids=["g1"], disabled=True),  # disabled -> not counted
            FetchedUser(uid="su", username="super", role_uids=["r_all"]),
            FetchedUser(uid="bystander", username="nobody"),
        ],
        roles=[FetchedRole(uid="r_all", name="Super", authorities=["ALL"], member_count=1)],
        groups=[FetchedGroup(uid="g1", name="M&E", member_count=3)],
        type_inventory=[TypeInventory(type="dataSet", data_bearing=True, total=1)],
    )


def test_effective_access_counts_and_public_flags() -> None:
    """Public axes resolve to every enabled user; non-public axes to the distinct owner+share+superuser set."""
    eff = compute_effective_access(_effective_graph())
    assert len(eff) == 1
    e = eff[0]
    enabled = 6  # 7 users minus the disabled m3
    # meta-read and data-read are public -> all enabled users
    assert e.public_meta_read and e.meta_readers == enabled
    assert e.public_data_read and e.data_readers == enabled
    # meta-write is not public: owner + direct(-w) + superuser
    assert not e.public_meta_write and e.meta_writers == 3
    # data-write is not public: owner + enabled group members (m1, m2) + superuser
    assert not e.public_data_write and e.data_writers == 4


def test_effective_access_grant_paths() -> None:
    """Every provenance kind is represented; the group grant carries the enabled member count."""
    e = compute_effective_access(_effective_graph())[0]
    kinds = {g.kind.value for g in e.grants}
    assert kinds == {"owner", "direct", "group", "public", "superuser"}
    group_grant = next(g for g in e.grants if g.kind.value == "group")
    assert group_grant.principal_uid == "g1" and group_grant.subject_count == 2  # m3 disabled, excluded


def test_effective_access_external_grant() -> None:
    """An external object gets an external grant and the external flag on its effective access."""
    graph = build_sharing_graph(
        target="x",
        generated_at="t",
        objects=[FetchedObject(uid="O", type="map", name="M", public_access="r-------", external=True)],
        users=[FetchedUser(uid="u1", username="u1")],
        roles=[],
        groups=[],
        type_inventory=[TypeInventory(type="map", total=1)],
    )
    e = compute_effective_access(graph)[0]
    assert e.external is True
    assert any(g.kind.value == "external" for g in e.grants)


def test_effective_access_private_object_only_superusers() -> None:
    """A fully private object is still reachable by superusers (they bypass sharing), and no one else."""
    graph = build_sharing_graph(
        target="x",
        generated_at="t",
        objects=[FetchedObject(uid="O", type="dataSet", name="P", data_bearing=True, public_access="--------")],
        users=[
            FetchedUser(uid="su", username="super", role_uids=["r_all"]),
            FetchedUser(uid="plain", username="plain"),
        ],
        roles=[FetchedRole(uid="r_all", name="Super", authorities=["ALL"], member_count=1)],
        groups=[],
        type_inventory=[TypeInventory(type="dataSet", data_bearing=True, total=1)],
    )
    e = compute_effective_access(graph)[0]
    assert e.meta_readers == 1 and e.data_writers == 1  # only the superuser
    assert {g.kind.value for g in e.grants} == {"superuser"}


# ---------------------------------------------------------------------------
# view payload + explorer bundle emit
# ---------------------------------------------------------------------------


def test_sharing_view_payload_is_assignable_js() -> None:
    """build_sharing_view renders an assignable window.__SHARING__ statement carrying meta + graph."""
    graph = _effective_graph()
    view = build_sharing_view(graph, profile="play", version="2.42.5.1", scanner="0.23.0")
    js = view.to_sharing_data_js()
    assert js.startswith("window.__SHARING__ = ") and js.rstrip().endswith(";")
    import json

    payload = json.loads(js[len("window.__SHARING__ = ") : js.rstrip().rfind(";")])
    assert payload["meta"]["version"] == "2.42.5.1"
    assert payload["meta"]["profile"] == "play"
    assert payload["graph"]["objects"][0]["uid"] == "O"
    assert payload["graph"]["objects"][0]["public"]["data_read"] is True


def test_explorer_emit_writes_self_contained_bundle(tmp_path: Path) -> None:
    """ExplorerRenderer.emit writes sharing-data.js and copies the fixed template, runtime, d3, and logo."""
    view = build_sharing_view(_effective_graph(), profile="p", version="v", scanner="s")
    ExplorerRenderer().emit(tmp_path, view)
    for name in ("sharing-data.js", "sharing-explorer.html", "sharing-runtime.js", "d3.min.js", "dhis2-logo.png"):
        assert (tmp_path / name).exists(), f"missing {name}"
    assert "window.__SHARING__" in (tmp_path / "sharing-data.js").read_text(encoding="utf-8")
    # the vendored d3 is non-trivial; the executable code and images all load from the local bundle
    # (only the cosmetic webfont stylesheet is remote, matching the HTML report), so the explorer runs offline
    assert (tmp_path / "d3.min.js").stat().st_size > 100_000
    html = (tmp_path / "sharing-explorer.html").read_text(encoding="utf-8").lower()
    assert 'src="http' not in html, "scripts and images must load from the local bundle, not a CDN"


# ---------------------------------------------------------------------------
# Per-tree wiring: --sharing-graph captures the graph and computes the closure
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("tree", TREES)
async def test_run_sharing_populates_sink_and_explorer_note(tree: str, tmp_path: Path) -> None:
    """With a graph sink, _run_sharing computes the closure, stashes the graph, persists it, and notes the explorer."""
    audit = _audit_module(tree)
    client = _mock_sharing_client(
        schemas=[{"name": "dataSet", "plural": "dataSets", "shareable": True, "dataShareable": True}],
        pages={
            "dataSets": [
                {"dataSets": [_object("ds1", "HIV", "rwrw----")], "pager": {"page": 1, "pageCount": 1, "total": 1}}
            ]
        },
        users=[{"id": "u1", "username": "admin", "userRoles": [{"id": "r_all"}]}],
        roles=[{"id": "r_all", "name": "Super", "authorities": ["ALL"], "users": 1}],
        groups=[],
    )
    sink: list[SharingGraph] = []

    result = await audit._run_sharing(
        client, max_objects=5000, generated_at="t", output_folder=tmp_path, graph_sink=sink
    )

    assert result.status is CheckStatus.OK
    assert len(sink) == 1
    assert sink[0].effective and sink[0].effective[0].object_uid == "ds1"
    assert "sharing-explorer.html" in (result.note or "")
    persisted = audit._load_sharing_graph(tmp_path)
    assert persisted is not None and persisted.effective and persisted.effective[0].object_uid == "ds1"
