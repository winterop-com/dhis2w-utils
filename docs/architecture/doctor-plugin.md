# Doctor plugin

One command that diagnoses a DHIS2 instance. Three probe categories, three
sub-commands, one unified report shape:

```
d2w doctor metadata     # workspace-specific instance-health checks
d2w doctor integrity    # DHIS2's own /api/dataIntegrity/summary
d2w doctor bugs         # BUGS.md workaround drift detection

d2w doctor              # default: metadata + integrity
d2w doctor --all        # includes bugs
```

Runs as `d2w doctor`, `doctor_run` / `doctor_metadata` / `doctor_integrity`
/ `doctor_bugs` MCP tools, or the library-level `service.run_doctor(...)` —
same probe set, three surfaces.

## The three categories

### `metadata` — workspace instance-health (primary)

Answers "what's wrong with this instance's configuration?" — classes of
misconfiguration DHIS2 won't flag at startup but that cost operators real
time. Each probe returns `offending_uids` so you can jump straight to
fixing them.

| Probe | What it checks | DHIS2 integrity equivalent |
| --- | --- | --- |
| `dataSets:dataElements` | Data sets with 0 dataSetElements (nothing to collect) | — |
| `dataSets:orgUnits` | Data sets with 0 organisationUnits (users can't enter data) | `datasets_not_assigned_to_org_units` |
| `dataElements` | Aggregate DEs not attached to any dataSet (orphan) | `data_elements_without_datasets` |
| `dataElements:categoryCombo` | Data elements missing a categoryCombo (broken metadata) | — |
| `programs` | Programs with 0 programStages (unusable) | — |
| `programStages:dataElements` | Program stages with 0 programStageDataElements (can't capture data) | — |
| `programIndicators:expression` | Program indicators with empty `expression` (unusable) | — |
| `programIndicators:orphanRefs` | Program indicators referencing a stage or data-element UID that no longer exists | — |
| `userGroups` | User groups with 0 members (likely stale) | — |
| `userRoles` | User roles with 0 assigned users (dead roles) | `user_roles_with_no_users` |
| `users:userRoles` | Users with 0 userRoles (locked out of every authority-gated feature) | — |
| `categoryCombos` | Category combos with 0 categories (excluding built-in `default`) | — |
| `organisationUnitGroups` | OU groups with 0 members (stale) | — |
| `organisationUnitGroupSets` | OU group sets with 0 groups (unusable in analytics) | — |
| `organisationUnits:parent` | Non-root OUs missing a `parent` reference (broken hierarchy) | — |
| `organisationUnits:hierarchyDepth` | Gaps in distinct levels or > 10 levels of depth | — |
| `dashboards` | Dashboards with 0 items (empty landing pages) | `dashboards_no_items` |
| `visualizations` | Visualizations with 0 data dimensions (empty charts) | — |
| `indicators:expressions` | Indicators with empty numerator OR denominator (unusable) | — |
| `validationRules:expressions` | Validation rules with an empty left-side or right-side expression (unusable) | — |

**Overlap with DHIS2's built-in data-integrity.** 4 of 20 metadata probes
duplicate a DHIS2 check. The overlap is intentional — our probes surface
the offending UIDs immediately (without requiring a prior `dataintegrity
run` sweep) and the tables stay readable with UIDs in the `offending_uids`
column. Prefer the workspace probe when you want a quick answer; prefer
`d2w maintenance dataintegrity result <check> --details` when you need
DHIS2-authoritative reporting or the full issue description/recommendation
DHIS2 ships per check.

### `integrity` — DHIS2's own data-integrity (authoritative)

Wraps `/api/dataIntegrity/summary`. DHIS2 ships ~40 built-in checks
(organisation-unit coverage, indicator expression validity, duplicate
category options, period-type mismatches, dashboards without items, etc.).
Each DHIS2 check becomes one `ProbeResult` — `pass` when 0 issues, `warn`
when >0. Severity is carried in the message.

The integrity probes `skip` with a hint if DHIS2 hasn't run its checks yet
— kick them off with `d2w maintenance dataintegrity run --watch` first.

### `bugs` — workspace drift detection (maintenance)

Verifies BUGS.md workarounds still apply. When DHIS2 fixes an upstream
bug a `pass` probe flips to `warn`, giving the workspace a nudge to clean
up the corresponding workaround without manually watching every DHIS2
release note. Not usually the right default for operators — run via
`d2w doctor bugs` when doing workspace maintenance.

Current `bugs` probes cover: DHIS2 version floor, `/api/me` auth,
`/api/loginConfig` summary, `/.well-known/openid-configuration`,
BUGS.md #1 (analytics `.json` suffix), #4 (OAuth2 endpoints), #8
(UserRole `authorities` schema pluralization), #11 (custom-logo flag),
#13 (`MOD_Z_SCORE` rejection).

## Statuses

- `pass` — metadata probe found no offenders / integrity check reports 0
  issues / bug workaround still effective / requirement satisfied.
- `warn` — something is worth looking at, but it's not build-blocking.
- `fail` — a hard requirement (auth, version) failed. CLI exits 1.
- `skip` — the category can't run here (e.g. OAuth2 not configured,
  DHIS2 data-integrity never run).

The CLI renders a Rich table; `--json` emits the `DoctorReport` pydantic
model for scripting / CI. The MCP tools return the same structured type.

## Example output

```
                   d2w doctor — http://localhost:8080 (DHIS2 2.42.4)
┏━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━┓
┃ probe             ┃ category  ┃ status ┃ message                   ┃ offending   ┃
┡━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━┩
│ dataSets:dataEl.. │ metadata  │  PASS  │ all 1 data sets reference │             │
│                   │           │        │ >=1 data element          │             │
│ dataElements      │ metadata  │  WARN  │ 5 aggregate DE(s) orphan  │ AJVnk...    │
│ programs          │ metadata  │  PASS  │ all 2 programs have >=1   │             │
│                   │           │        │ stage                     │             │
│ userRoles         │ metadata  │  WARN  │ 1 user role(s) dead       │ YHt5Wbp4..  │
│ integrity:dashb.. │ integrity │  PASS  │ 0 issues [severity=WARN]  │             │
│ integrity:orgs_.. │ integrity │  WARN  │ 5 issues [severity=ERROR] │             │
│ ...               │ ...       │ ...    │ ...                       │ ...         │
└───────────────────┴───────────┴────────┴───────────────────────────┴─────────────┘
85 pass / 10 warn / 0 fail / 0 skip (95 probes)
```

## Adding a new metadata probe

1. Add an `async def probe_<name>(client: Dhis2Client) -> ProbeResult` to
   `probes_metadata.py`. Use the `_list_all` helper for DHIS2 listing calls
   and `_summarise` to build the ProbeResult.
2. Append it to the `METADATA_PROBES` tuple so `run_doctor` picks it up.
3. Add a row in the `metadata` table above.
4. Add a respx test in `test_doctor_plugin.py` covering at least one
   success + one drift / failure case.

Probes within a category run concurrently (`asyncio.gather`) — a new probe
adds one more HTTP request, not one more round-trip latency.

## Library API

```python
from dhis2w_core.v42.plugins.doctor import service
from dhis2w_core.profile import profile_from_env

# Default: metadata + integrity.
report = await service.run_doctor(profile_from_env())

# Categories are explicit — mix and match:
report = await service.run_doctor(
    profile_from_env(),
    categories=("metadata",),
)
for probe in report.probes:
    if probe.status == "warn":
        print(f"{probe.name}: {probe.message}")
        for uid in probe.offending_uids:
            print(f"  -> {uid}")
```

## Not covered here

- **Behavioural quirks that require a write** (soft-delete on
  `/api/dataValueSets`, `organisationUnits` capture-scope DESCENDANT
  rule, bulk-import 409 reporting) — probing them would mutate state.
  Documented in `BUGS.md`; not automated.
- **UI bugs** (login-app `html { transparent }` at non-100% zoom) —
  needs a browser; not reachable from an HTTP probe.
- **dhis.conf audit / changelog settings** — DHIS2 doesn't expose these
  via the API.
- **Full expression syntax validation** — would require calling
  `/api/expressions/validate` or `/api/indicators/expression/description`
  per indicator / validation-rule / predictor, so a probe run scales linearly
  with those collections. `programIndicators:orphanRefs` is the closest
  fast-path approximation today (catches referential breakage without per-item
  API calls). DHIS2's own data-integrity check
  `program_indicators_with_invalid_expressions` covers full syntax validation
  server-side once a `dataintegrity run` has fired.
