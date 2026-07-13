# Sharing explorer: advanced plan

Author: Morten Svanaes

Status: DRAFT for iteration. This extends PR 7 (`sharing`) of `SECURITY-SCANNER-PLAN.md`
with an opt-in, static, interactive visualization of the DHIS2 access graph. It is a
design document, not yet implemented.

## Decisions locked (2026-06-20)

1. **Access depth: effective access + provenance.** Compute the full transitive closure
   (who can actually read/write each object) with the via-path, not just declared edges.
   The org-unit / superuser / sub-object boundaries are shown in the UI, never silently
   dropped.
2. **Viewer scope: full multi-view.** Object tree + exposure triage + by-principal +
   by-role/authority pivots, plus the force-directed graph and matrix heatmap visual modes.
3. **Viz library: vendor d3.** Bundled as package data, offline, no CDN.
4. **Delivery: split.** Because the locked viewer scope is large, the split is a three-PR
   sequence (7a data layer, 7b core explorer, 7c advanced visual modes) rather than 7a/7b.
   See "PR structure" below.

## The one-sentence pitch

It is not a "sharing viewer". It is an **effective-access reasoning engine** over the
unified metadata + identity graph, rendered as a single self-contained static artifact you
can open from the audit report (or ship as a standalone app), that answers the question a
flat findings list never can: **"who, concretely, can read or write this object, and by
what path did they get that access?"**

## Why a flat findings list is not enough

PR 7 as currently planned emits findings: "dataSet X is public-write (HIGH)", "SQL view Y
is externally accessible (HIGH)". That is correct and necessary, but it is a *reduction*.
It throws away the structure that makes the answer actionable:

- A finding says "public-write". It does not say *which 1,243 specific accounts* that
  resolves to, or that 9 of them are disabled service accounts, or that 4 are superusers
  who could already do it anyway.
- A finding says "shared with group 'Interns'". It does not say that 'Interns' has 312
  members, that 'Interns' is *managed by* 'Field Coordinators', or that the same group also
  has write access to 40 other data-bearing objects.
- A finding is per-object. The real risk lives in the *topology*: one over-broad group that
  touches everything, one role with `ALL` whose members bypass sharing entirely, one
  externally-readable SQL view that joins three patient tables.

The graph keeps all of that. The findings become one *view* of the graph; the explorer is
another; a future standalone app is a third. Same data contract underneath.

## Ultrathink: the data structure of DHIS2 metadata

The central insight (yours): **users, roles, and groups are also metadata.** They are not
edge labels on a sharing relation. They are first-class nodes with their own subgraph. That
means there are two graphs that share their principal nodes, and the interesting questions
live in the *intersection*.

### Graph A: the identity / RBAC graph (capability)

What a principal is *allowed to do at all*, system-wide:

```
User --HAS_ROLE--> UserRole --GRANTS--> Authority      (e.g. F_DATAVALUE_ADD, ALL)
User --MEMBER_OF--> UserGroup
UserGroup --MANAGES--> UserGroup                         (managedGroups: admin delegation,
                                                          NOT membership inheritance)
```

`ALL` authority on any of a user's roles makes them a superuser: they **bypass sharing
entirely**. That single fact reshapes every "who can access this" answer, which is why the
identity graph cannot be ignored when reasoning about sharing.

### Graph B: the sharing / ACL graph (per-object exposure)

What can access a *specific object*. Every shareable metadata object carries a `sharing`
block:

```json
{
  "sharing": {
    "owner": "<userUid>",
    "external": false,
    "public": "rwrw----",
    "users":      { "<uid>": { "id": "<uid>", "access": "rw------" } },
    "userGroups": { "<uid>": { "id": "<uid>", "access": "r-------" } }
  }
}
```

Modeled as edges:

```
Object --SHARES{access}--> User
Object --SHARES{access}--> UserGroup
Object --SHARES{access}--> PUBLIC      (pseudo-principal: every authenticated user)
Object --SHARES{access}--> EXTERNAL    (pseudo-principal: anyone, no login at all)
Object --OWNED_BY--------> User        (owner has implicit full access)
```

### The access string (verified against DHIS2 source)

From `dhis-service-acl/.../AccessStringHelper.java`, the 8-char access string decodes as:

| Pos | Meaning        | Char |
|-----|----------------|------|
| 0   | metadata read  | `r`  |
| 1   | metadata write | `w`  |
| 2   | data read      | `r`  |
| 3   | data write     | `w`  |
| 4-7 | reserved       | `-`  |

So `rwrw----` is full metadata + full data (the `CATEGORY_OPTION_DEFAULT`), `rw------` is
metadata only (`CATEGORY_NO_DATA_SHARING_DEFAULT`), `r-r-----` is read metadata + read data,
`--------` is no access (`DEFAULT`). Every access string in the graph is decoded once into a
typed `AccessBits { metaRead, metaWrite, dataRead, dataWrite }` so the UI never parses
characters and the data axis is never confused with the metadata axis. Data bits only carry
meaning on data-bearing types (dataSet, program, programStage, trackedEntityType,
categoryOption, ...); on metadata-only types (dashboard, document, sqlView, visualization,
map, indicator, ...) they are inert and the UI greys them out.

### The join: the User node ties A and B together

The same `UserNode` is a member of groups (A), holds roles that grant authorities (A), and
is the target of direct shares (B). That is the whole point. The explorer lets you stand on
any node and traverse outward across *both* graphs:

- Stand on an **object**: walk B outward to principals, then A outward through each group to
  its members and each member's authorities. -> "who can touch this, and what else can they do?"
- Stand on a **user**: walk A (their groups/roles/authorities) and B-reversed (every object
  shared to them directly or via a group). -> "what can this person actually reach?"
- Stand on a **role/authority**: walk A-reversed to the users who hold it, then B to what
  their sharing unlocks. -> "who has `ALL`? who can run SQL views? what does that expose?"

### Effective access: the transitive closure (the headline computation)

For an object `O`, the **effective readers** (and separately writers, for metadata and for
data) is the materialized set:

```
effective_readers(O, axis) =
      { owner(O) }
    ∪ { u : direct SHARES(O -> u) has axis-read }
    ∪ { u : u MEMBER_OF g and SHARES(O -> g) has axis-read }
    ∪ ( all authenticated users WITH authority to read type(O)   if PUBLIC has axis-read )
    ∪ { anyone, anonymously }                                    if EXTERNAL has axis-read
    ∪ { u : u is superuser (role grants ALL) }                   # bypass, always
```

Every membership in that set carries **provenance**: a `via` list explaining *how*
(`direct`, `group:<uid>`, `public`, `external`, `superuser`, `owner`). The UI surfaces this
as: *"Alice can WRITE DATA on 'HIV Case Surveillance' because she is in group 'M&E
Officers' which has `--rw----` data sharing."* Provenance is what turns a scary aggregate
("1,243 readers") into an audit trail.

**Honesty boundaries (shown in the UI, never silently dropped):**

- Org-unit scoping is *not* modeled. DHIS2 data access is further restricted by a user's
  capture / data-view org units, which live outside the sharing block. So effective *data*
  readers is an over-approximation; the UI labels it "sharing-level; org-unit scope narrows
  this further."
- Superuser bypass is shown explicitly as its own provenance kind, so a reader can see
  "of these 1,243, 1,180 are only here because they are superusers."
- Category/program option-combo sharing and tracker program-stage sharing have nuances we
  model at the object level, not the sub-object level, in v1.

LOCKED: effective access + provenance is the headline (decision 1).

## The artifact: static, opt-in, self-contained

Mirrors the existing data-driven HTML report bundle exactly
(`packages/dhis2w-core/src/dhis2w_core/security_core/report/html.py` -> `report.dc.html` +
`support.js` + logo + per-run `report-data.js`). The explorer is a **second bundle** written
into the same run folder, only when explicitly requested:

```
<run-folder>/
  report.dc.html        report-data.js     support.js     dhis2-logo.png   # existing report
  sharing-explorer.html                                                    # NEW: opt-in
  sharing-data.js        # window.__SHARING__ = { ...the graph... }
  sharing-runtime.js     # the viewer (parses window.__SHARING__, renders, all interaction)
  <viz-lib>.js           # vendored, offline, no CDN (DECISION 3)
```

- Off by default. Enabled by `--sharing-graph` (alias `--visualize`). The report's `sharing`
  section gets a banner: "Interactive explorer generated: open sharing-explorer.html",
  with finding rows deep-linking into the explorer (`sharing-explorer.html#object/<uid>`).
- Self-contained and offline: vendored viz lib, inline CSS, no external assets. Same
  guardrail as the report bundle. Reuses the shipped light/dark theme toggle.
- Heavy generation is acknowledged: building the graph + closure is the cost, hence opt-in.

## The viewer UX

Default view is the **object-centric collapsible tree** you asked for. The power comes from
*pivoting the same graph*:

1. **By object (default tree).** Root -> object types (with per-type severity heat and
   counts) -> flagged objects -> sharing breakdown (Public / External / Groups / Users) ->
   expand a group to its members. Each node shows decoded access chips `[M:rw] [D:r-]`.
2. **By principal (reverse tree).** Pick a user or group -> every object they can reach and
   the access path. "What can 'Interns' actually see?"
3. **By role / authority.** Pick a role or authority -> who holds it -> what it unlocks.
   "Who has `ALL`? Who can run SQL views?"
4. **By exposure (triage).** A flat, severity-sorted risk list: external objects first, then
   public-write data-bearing, then public-read sensitive, then broadly-readable SQL views.
   This view *is* the PR 7 findings, rendered live and clickable.

Alternate visual modes (toggle, same data):

- **Force-directed graph** for topology: spot hub groups, the "everything shared with
  Administrators" star, clusters of co-shared objects. Filterable by type / severity /
  principal to avoid a hairball.
- **Matrix heatmap**: object-type (rows) x group (columns), cell = strongest access. "This
  group has write to everything" jumps out instantly.
- **Sankey** (optional, later): principal -> access level -> object-type flow, for "where
  does write concentrate."

Cross-cutting interactions: search/filter by name/type/principal/access/severity; click a
node for a detail panel (raw sharing block, decoded bits, effective reader/writer counts
with provenance, link to the matching finding); an "effective access" expander on any object
("Who can read this? (1,243)" grouped by path); a "why?" on any (user, object) pair showing
the provenance path(s); deep-linkable URL-hash state so the report can jump straight to a node.

LOCKED: full multi-view (decision 2). Sequenced across PRs so each stays reviewable: the
tree + triage + by-principal + by-role/authority pivots land in 7b; the force-directed graph
and matrix heatmap land in 7c. The end-state is the full multi-view; the sequencing is purely
about PR size.

## Scale strategy (this is what makes or breaks it)

Real instances: tens of thousands of metadata objects, thousands of users, hundreds of
groups/roles. We cannot embed everything naively.

- **Tier the data.** (1) Always include the full *principal* subgraph (users, groups, roles,
  authorities, memberships); bounded, thousands not millions. (2) Always include every
  object with *non-default* sharing (public-write, external, any explicit user/group share
  beyond owner); the security-relevant slice, usually a small fraction. (3) Only with
  `--sharing-graph-full` (and under `--max-objects`) include the full object inventory.
- **Aggregate the boring.** Owner-only / default-shared objects roll into a per-type count
  ("4,812 dataElements with default sharing") rather than individual nodes.
- **Pseudo-node edges, not fan-out.** Public/External are single nodes; a public object has
  one edge to `PUBLIC`, never N edges to N users. The N-user fan-out only happens inside the
  effective-access closure, and even there we store counts + grouped provenance, listing
  individuals lazily in the UI from the principal set.
- **Compact encoding for the big graph.** Nodes as arrays, edges as integer index references
  (not repeated uid strings), so the force-graph payload stays small and gzip-friendly.
- **Truncation is loud, in the artifact.** "Showing 5,000 of 48,210 objects (capped by
  --max-objects)" rendered prominently in the explorer, not just in a log line. A viewer that
  looks complete but is not is worse than the markdown truncation note.

`DECISION 4`: default object scope = non-default-sharing-only (recommended) vs full
inventory behind `--sharing-graph-full`.

## Architecture and the standalone-app path

The contract is the **graph JSON** (`window.__SHARING__`), versioned with a `schemaVersion`.
Everything is a pure function of that contract, which is what makes the standalone app cheap
later:

```
security_core/sharing/
  model.py      SharingGraph + node/edge models (AccessBits, ObjectNode, UserNode,
                UserGroupNode, RoleNode, ShareEdge, MembershipEdge, RoleGrantEdge,
                ManageEdge, EffectiveEdge, Provenance, TypeSummary). Pydantic, frozen.
  builder.py    build_sharing_graph(...): raw fetched data -> SharingGraph (UI-agnostic).
  effective.py  compute_effective_access(graph): the transitive closure + provenance.
  check.py      evaluate_sharing(graph) -> list[AuditFinding]   (PR 7 findings = a reduction)
  view.py       graph -> window.__SHARING__ JS payload (mirrors report/view.py)
  explorer.py   ExplorerRenderer.emit(folder, graph): writes sharing-data.js + copies the
                fixed explorer template/runtime/viz-lib from package data (mirrors html.py)

security_core/report/assets/      (new files alongside report.dc.html / support.js)
  sharing-explorer.html
  sharing-runtime.js
  <viz-lib>.js
```

Per-tree wiring in `dhis2w_core.v{41,42,43}.plugins.security.audit`: a `_run_sharing(client)`
that pages the sharing-bearing endpoints, builds the graph once, derives findings from it,
and (when `--sharing-graph` is set) hands the graph to the explorer emitter. Registered in
`_RUNNERS` like every other check. **The graph is built once and is the single source: the
`sharing` findings and the explorer are both projections of it.** Version divergence (e.g.
older trees that lack a field, or `/api/routes`-style 2.41+ endpoints) folds into the same PR
with a BUGS.md entry, per the three-tree rule.

Standalone app, later and cheap: the same `sharing-explorer.html` + `sharing-runtime.js`,
plus a loader that fetches the graph live from a DHIS2 instance (via `dhis2w-client`) instead
of reading the embedded `sharing-data.js`. Because the builder is UI-agnostic and the schema
is versioned, the app is "new workspace member + live loader", not a rewrite; consistent
with the architecture's "new surfaces land as new members."

LOCKED: vendor d3 (decision 3), bundled as package data, offline, no CDN. Revisit only if
bundle size becomes a problem.

## Guardrails (same contract as the rest of the audit)

- GET-only, paged, capped by `--max-objects`, with loud truncation. No writes, ever.
- One fetch pass shared between the `sharing` check and the explorer (build the graph once).
- Effective-access boundaries (org-unit scope, superuser bypass, sub-object sharing) stated
  in the UI, never silently assumed. A confidently-wrong "who can see this" is dangerous.
- New allowlist entries for the sharing-bearing endpoints are reviewed changes, listed in the
  PR.

## PR structure

The locked scope (effective access + full multi-view) is far too big for one PR (CLAUDE.md
target ~15 files, three trees). Three-PR sequence, each independently reviewable and each
shipping its tests over the three trees, examples, FEATURES.md rows, docs, and BUGS.md
entries where divergence surfaces:

- **PR 7a: sharing data layer + findings.** `security_core/sharing/{model,builder,check}.py`,
  the per-tree `_run_sharing` wiring, the `sharing` findings, `--format json` exposure of the
  graph, tests over three trees. No UI, no closure yet. Independently useful: a
  machine-readable access graph plus the PR 7 findings the base plan promised.
- **PR 7b: core explorer.** `effective.py` (the transitive closure + provenance), `view.py`
  (the `window.__SHARING__` payload), `explorer.py` (the bundle emitter), the vendored d3 +
  explorer template/runtime as package data, the `--sharing-graph` flag, the report deep-link
  banner. Viewer modes: object tree + exposure triage + by-principal + by-role/authority
  pivots. Tests: payload-shape + closure correctness + a smoke render.
- **PR 7c: advanced visual modes.** The force-directed graph and the matrix heatmap modes on
  top of 7b's payload, plus the compact columnar encoding for large graphs and the
  loud-truncation banner. Mostly runtime (`sharing-runtime.js`) plus any encoding changes in
  `view.py`.

LOCKED: split delivery (decision 4); sequenced as 7a/7b/7c because the locked viewer scope is
larger than a two-PR split can hold reviewably.

## Open questions to resolve during build

- Exact set of sharing-bearing object types to inventory by default, and their data-bearing
  classification (verify against the DHIS2 schema endpoint, not guessed).
- Whether to read sharing via per-type `?fields=...,sharing` listing or the metadata export;
  cost and completeness trade-off at scale.
- Whether `managedGroups` is worth surfacing in v1 (it is the admin-delegation relation, very
  relevant to "who can grant access") or deferred with the boundary-crossing graph work the
  base plan already defers.
- Compact-encoding format for the large graph (columnar arrays + index refs); design when
  the force-graph lands.
