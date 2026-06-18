# Plan: redesign the security audit HTML report

Author: Morten Svanaes
Status: proposed (awaiting go-ahead to implement)
Scope: the `html` output of `d2w security audit`

## Goal

Replace the current plain-table `report.html` with the new "Claude design" report
(in `DHIS2_Security_Report_Redesign/`). The new report is a data-driven page: a fixed
HTML template (`*.dc.html`) plus a runtime (`support.js`) read all content from a
`window.__REPORT__` object emitted into `report-data.js`. Per scan we only generate
`report-data.js`; the template, runtime, and logo are fixed assets shipped with the package.

## Locked decisions

1. Delivery: multi-file bundle. Each run folder gets `report.dc.html`, `support.js`,
   `dhis2-logo.png` (copied, fixed) and `report-data.js` (generated). The user opens
   `report.dc.html`.
2. Scope: replace the `html` format. The existing plain-table `HtmlRenderer` is removed;
   the new design becomes the `html` output. `md` / `txt` / `csv` / `report.jsonl` / `manifest.json`
   are unchanged.

## How the new template actually works (and one gotcha)

`support.js` is a small client-side framework. It parses the `<x-dc>` subtree of
`report.dc.html`, runs the `class Component extends DCLogic` defined in the inline
`<script data-dc-script>`, and interpolates `{{ ... }}` expressions against the object
returned by `renderVals()`. Directives `sc-for` / `sc-if` drive lists and conditionals.
`{{ ... }}` interpolation applies to any text node or attribute in the subtree, not only
inside directives (confirmed in `support.js`).

`renderVals()` lives inside `report.dc.html` (not `support.js`), so all template logic is
editable there. `support.js` is the generic runtime and stays byte-for-byte unchanged
(the prompt requires this).

Gotcha that the prompt.txt understates: in the shipped design, only the table-of-contents
and the section bodies are data-bound. The hero headline/subtitle, the meta strip
(target / profile / version / scanner / started), the five scorecard numbers, the
"total findings / across N control areas" box, and the footer line are hardcoded to the
sample values (see `DHIS2 Security Audit.dc.html` lines ~45-105, 123-124, 205). So
"regenerate only report-data.js" is not yet true. We do a one-time edit to the template to
bind those to `window.__REPORT__`; after that, the template really is fixed and only
`report-data.js` changes per scan.

## Data contract (`window.__REPORT__`)

```
window.__REPORT__ = {
  meta:      { target, profile, version, scanner, started },
  scorecard: { CRITICAL, HIGH, MEDIUM, WARN, INFO },   // verbatim totals
  sections: [
    {
      title:  string,
      status: ["[ok]", "(optional note)"],             // note entry is optional
      groups: [
        { finding, sev, count, sampleDetail, items: [ { name, last } ] }
      ]
    }
  ]
}
```

UI rules baked into the runtime:
- `count > 1` -> the group renders as a collapsible list of `items` (the name grid);
  each item shows `name` and, when `last` is set, a "last YYYY-MM-DD" subline.
- `count === 1` -> a single static finding row (`items` ignored).
- `sev` must be one of `CRITICAL | HIGH | MEDIUM | WARN | INFO`.
- Section tally chips and the left-rail counts are computed by the runtime as
  `sum(group.count)` per severity. The hero scorecard must equal those sums.

## Mapping our model -> `window.__REPORT__`

Source models live in `security_core/`:
`AuditReport { manifest: RunManifest, results: list[CheckResult], summary: AuditSummary }`,
`CheckResult { check, label, status, findings: list[AuditFinding], note }`,
`AuditFinding { check, severity, title, detail, subject, evidence }`.

| `window.__REPORT__` | Source |
| --- | --- |
| `meta.target` | `manifest.target` |
| `meta.profile` | `manifest.profile` |
| `meta.version` | `manifest.dhis2_version` (fallback `"unknown"`) |
| `meta.scanner` | `manifest.scanner_version` |
| `meta.started` | `manifest.started_at` |
| `scorecard.{SEV}` | `summary.{critical,high,medium,warn,info}` |
| `section.title` | `result.label` |
| `section.status` | `["[" + result.status.value + "]"]` plus `["(" + result.note + ")"]` when `note` is set |
| `group.finding` | finding `title` |
| `group.sev` | finding `severity` |
| `group.count` | number of findings folded into the group |
| `group.sampleDetail` | representative finding `detail` (first in the group) |
| `group.items[].name` | finding `subject` |
| `group.items[].last` | finding `evidence["last"]` when present, else `null` |

### Grouping (the one real modelling decision)

The new design folds the many per-user hygiene findings into one collapsible group
(e.g. "Privileged account never logged in", count 104) while keeping the role findings as
separate single rows even though several share the title "Role holds dangerous authorities".
There is no purely mechanical rule (group-by-title, or by title+severity) that reproduces
both behaviours, because grouping is an intent the check has, not something derivable from
the row text.

Recommended: make grouping explicit on the finding.

- Add `group_key: str | None = None` to `AuditFinding`.
- A check sets `group_key` on rows that should fold together (same non-null key within one
  check -> one collapsible group). `group_key = None` -> the finding is its own single row.
- `build_report_view` groups a check's findings by `group_key` (preserving first-seen order),
  emits `count = len(group)`, `sampleDetail = group[0].detail`, and `items` from
  `subject` / `evidence["last"]`. For single-count groups, `items = []`.

This reproduces the design exactly and is explicit (no magic), matching the repo's style.

Concrete check changes:
- Hygiene (`security_core/hygiene.py`): set `group_key` per finding-kind
  ("never-logged-in", "stale", "no-email", "disabled-privileged"); set
  `evidence={"last": user.last_login}` on the stale finding so items show the date.
  The seed-admin and inventory findings stay `group_key=None` (single rows).
- Roles / settings / authorities / credential-probe / version: no change ->
  `group_key=None` -> one row each, as in the sample.

Invariant to assert in tests: for every severity, `scorecard[sev]` equals
`sum(group.count for group in all groups if group.sev == sev)`. This holds by construction
because both come from the same findings, and it is exactly what makes the hero scorecard
and the section chips agree. Worked check against the sample data:
- CRITICAL: role-ALL (1) + credential probe (1) = 2
- HIGH: never-logged-in (104) + dangerous-role HIGH (3) = 107
- MEDIUM: lockout (1) + dangerous-role MEDIUM (1) + seed admin (1) + stale (19) = 22
- WARN: passwords-never-expire (1) + no-email (121) = 122
- INFO: authorities (7) + inventory (1) = 8

## Architecture changes (file by file)

Shared, single location unless noted.

1. New `security_core/report/view.py`
   - Pydantic view-models mirroring the contract: `ReportMeta`, `Scorecard`,
     `ItemView`, `GroupView`, `SectionView`, `ReportView`.
   - `build_report_view(report: AuditReport) -> ReportView` does the mapping + grouping above.
   - `ReportView.to_report_data_js() -> str` returns
     `"window.__REPORT__ = " + self.model_dump_json() + ";\n"`.

2. New `security_core/report/assets/` (shipped package data)
   - `report.dc.html` — the edited, fully data-bound template (see template edits below).
   - `support.js` — copied verbatim from the design folder, never edited.
   - `dhis2-logo.png` — copied verbatim.

3. `security_core/report/html.py` — rewrite as the bundle emitter
   - Keep the class name `HtmlRenderer` and `name = "html"` to minimise import churn in
     `__init__.py` and the three `audit.py` files.
   - It is no longer a pure string renderer (it must write several files), so add a
     folder-aware emit path (next item).

4. `security_core/report/base.py` — extend the renderer contract minimally
   - Add `emit(self, folder: Path, report: AuditReport) -> None`.
   - Provide a tiny default for the existing string renderers (text/csv/markdown):
     write `render(report)` to `folder / f"report.{suffix}"`. Implement once (small mixin
     or a module-level `emit_renderer(renderer, folder, report)` helper) so csv/text/markdown
     are untouched.
   - `HtmlRenderer.emit` writes `report-data.js` from `build_report_view(report)` and copies
     the three assets out of package data via
     `importlib.resources.files("dhis2w_core.security_core.report") / "assets"`.

5. `security_core/streaming.py` — `ReportWriter.finalize`
   - Replace the `report.{suffix}` write loop with `renderer.emit(folder, report)` (or the
     helper), so the bundle and the string formats finalize through one path.

6. `audit.py` in all three trees (`v41`, `v42`, `v43` `plugins/security/audit.py`) — same edit x3
   - `_FINALIZE_RENDERERS` keeps `txt` and `csv`; `html` maps to the new `HtmlRenderer`.
   - `DEFAULT_FORMATS` stays `("md", "txt", "csv", "html")`.
   - `rerender_report` builds output through the same emit path so `d2w security report`
     (re-render) reproduces the bundle.

7. `security_core/__init__.py`
   - Keep exporting `HtmlRenderer`. Add `ReportView` (+ the sub-models) and
     `build_report_view` to the imports and `__all__`.

### Template edits (one-time, in `assets/report.dc.html`)

- Bind the meta strip cells to `{{ meta.target }}`, `{{ meta.profile }}`, `{{ meta.version }}`,
  `{{ meta.scanner }}`, `{{ meta.started }}` (and the target `href`).
- Bind the five scorecard numbers to `{{ scorecard.CRITICAL }}` etc.
- Bind the hero subtitle and the "total findings / across N control areas" box to computed
  values (`totalFindings`, `areaCount`, `heroSubtitle`, and a critical clause shown only when
  `scorecard.CRITICAL > 0`).
- Bind the footer line (`scanner` + date) to `meta`.
- Extend `renderVals()` to return `meta`, `scorecard`, `totalFindings`, `areaCount`,
  `heroSubtitle`, and the footer string, computed from `window.__REPORT__`. The existing
  `toc` / `sectionsVM` logic stays.
- The runtime currently hardcodes the section status pill to a green "OK". Optional small
  improvement: colour it from `result.status` so degraded/error checks read correctly. Not
  required for parity; note as a follow-up.

### Packaging the assets

`dhis2w-core` builds with `uv_build`. Put the assets under the package source tree
(`src/dhis2w_core/security_core/report/assets/`) and configure `uv_build` to include the
non-Python files in the wheel (`[tool.uv.build-backend]`; verify the exact key against the
installed `uv_build` docs before editing). Editing build-backend config by hand is allowed;
the "never hand-edit pyproject" rule is about dependencies only (`uv add`). Access at runtime
via `importlib.resources.files(...)`, never a relative filesystem path.

## Tests (parametrised over the three trees where they already are)

- New `tests/security/test_security_report_view.py`:
  - grouping: per-user hygiene findings fold into one group with the right `count` and
    `items` (with/without `last`); `group_key=None` findings stay single rows.
  - scorecard invariant: `scorecard[sev] == sum(group.count for sev)`.
  - `to_report_data_js()` starts with `window.__REPORT__ =`, is valid JSON between the
    assignment and the trailing `;`, and round-trips.
- Update `tests/security/test_security_report_core.py`: the old HTML string assertions
  become assertions on `report-data.js` content (severity strings, finding titles, escaping
  via JSON) instead of HTML cells.
- Update `tests/security/test_security_audit_cli.py`: a finished run folder now contains
  `report.dc.html`, `report-data.js`, `support.js`, `dhis2-logo.png` (not `report.html`);
  `report.md` / `report.csv` / `report.jsonl` / `manifest.json` unchanged.
- `make lint && make test` must pass (ruff + mypy + pyright strict).

## Docs / examples / changelog (same PR)

- `FEATURES.md`: update the security-audit output description (html is now the redesigned
  bundle; list the four html-bundle files).
- Any `docs/` page or `examples/` that names `report.html` or lists run-folder contents:
  update to the bundle. Grep `report.html`, `HtmlRenderer`, "self-contained HTML" across
  `docs/`, `examples/`, `README.md`. Examples come in three flavours (v41/v42/v43) per the
  repo rules.
- `CHANGELOG.md`: one line for the redesign.
- `make docs-build` after doc edits to surface broken links.

## Risks / edge cases

- Offline fonts: the template pulls Hanken Grotesk / Newsreader / Space Mono from Google
  Fonts. Opened without network the page falls back to the inline stack
  (`-apple-system, sans-serif`) and still renders. Self-hosting the fonts is a possible
  follow-up if fully-offline fidelity is wanted; not in scope.
- `file://` rendering: `report.dc.html` references `./support.js`, `report-data.js`, and
  `dhis2-logo.png` relatively, so the four files must travel together (inherent to the
  multi-file decision). Validate by opening the folder in a browser (or a quick local
  `http.server`) after a real scan.
- Long detail strings / special characters: everything goes through `model_dump_json`, so
  quoting/escaping is handled by Pydantic; no manual HTML escaping needed in `report-data.js`.
- `manifest.dhis2_version` can be `None` -> map to `"unknown"` for `meta.version`.

## Suggested sequencing (each gate: lint + test green)

1. View-models + `build_report_view` + `to_report_data_js()`; unit tests for grouping and the
   scorecard invariant. (No wiring yet.)
2. `group_key` on `AuditFinding` + hygiene grouping/`last` evidence; update hygiene tests.
3. Vendor the assets; edit `report.dc.html` to be fully data-bound; manual browser check
   against a generated `report-data.js`.
4. Renderer/emit plumbing: `base.py` emit, `HtmlRenderer.emit`, `streaming.finalize`,
   `audit.py` wiring x3, `rerender_report`. Remove the old HTML renderer.
5. Update CLI/report-core tests for the new run-folder contents.
6. Docs / FEATURES / examples / CHANGELOG; `make docs-build`.
7. Full `make lint && make test`; open a real run's `report.dc.html` to confirm parity with
   the design.

## Estimated size

Roughly one medium PR. New code is concentrated in `security_core/report/` (one shared
location); the only fan-out is the `audit.py` renderer wiring (same one-line-ish change in
v41/v42/v43) and the three-flavour examples. Well under the ~15-file target if examples are
counted as the small files they are; can split assets-vendoring into its own commit.
