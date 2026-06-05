# Small-model MCP bridge — working notes

Working log for making the dhis2 toolkit usable by **small local models** (LM Studio / Ollama
/ llama.cpp) via `dhis2w-mcp-bridge` — a single MCP tool (`dhis2_cli`) that shells out to the
`dhis2` CLI. Tracks the model benchmark + the CLI/bridge read-surface hardening.

- Branch / staging PR: `feat/dhis2-mcp-cli-bridge` (PR #360 — testing PR, split into smaller PRs).
- Done → PR #360 description + commits. Queued → `docs/roadmap.md` ("Small-model bridge"
  follow-ups). Upstream quirk → `BUGS.md` #42. Testing rule: reads → `play42`, writes →
  `local_basic` (never mutate the shared public demo).

## Recommended local models

Benchmark prompt **"get id,code,name,description for all our data elements"** (+ count +
starts-with), driven through the bridge `run_cli` against play42 (1037 data elements).
Ranked by primary-prompt wall-clock; `ok` = correct.

| model | size | primary ok | calls | secs | count s | starts s | notes |
|---|---|---|---|---|---|---|---|
| **gemma-4-e4b** | ~4B (6.9GB) | yes | 1 | (fast) | ~5 | ~9 | follows the docstring best; org-unit-levels/units demo nailed it |
| **qwen2.5-coder-3b** | 1.9GB | yes | 1 | 63 | 3.6 | 25 | best tiny all-rounder |
| qwen2.5-3b | 1.9GB | yes | 1 | 19 | 3.5 | fail | fast but flubbed the filter |
| gemma-4-26b-a4b (MoE) | 18GB | yes | 2 | 35 | 7.6 | 39 | uses `--output` → saves to file, 1-line reply |
| qwen3.6-35b-a3b (MoE) | — | yes | 3 | 47 | 8.6 | 52 | uses `--output` |
| qwen3.5-4b | — | yes | 1 | 62 | 6.3 | 58 | solid |
| qwen2.5-7b | — | yes | 1 | 74 | 4.0 | 38 | solid |
| google/gemma-4-12b | — | yes | 1 | **147** | 13 | 91 | correct but slowest |
| qwen2.5-coder-1.5b | — | **no** | 1 | 6 | 3.4 | 19 | hallucinated "359" on the bulk dump |
| qwen2.5-coder-14b | — | **no** | 6 | — | 6.6 | 61 | loops on the bulk dump |
| llama-3.2-3b | — | **no** | 6 | — | fail | 18 | re-calls instead of answering |
| mn-violet-lotus-12b | — | **no** | 0 | — | fail | fail | won't call tools (prose only) |
| llama-3.2-1b | — | **no** | 1 | — | fail | fail | emits the schema as args |
| gemma-4-31b-jang | — | — | — | — | — | — | won't load |

- **Daily driver: `gemma-4-e4b` or `qwen2.5-coder-3b`.** Avoid llama-3.2-1b/3b, mn-violet-lotus,
  qwen2.5-coder-14b. gemma-4-12b works but is the slowest.
- **Context window doesn't affect decode speed**: qwen2.5-coder-3b at 8k/32k/128k → 72/57/70s,
  identical output tokens. 32k is the sweet spot. (KV-cache toggle not automatable via `lms`.)
- Raw data: was in `/tmp/bench_report.md` + `/tmp/bench_results.json` (ephemeral).

## Read-surface hardening — shipped (on PR #360)

| area | change |
|---|---|
| bridge docstring | rewritten for 3–4B: output contract + top reads first, `get` not `show`, "listing is `metadata list <type>`", analytics/data `--dim` block, "never answer from memory", count shape `{resource,total}` |
| discovery | `metadata type list --json` emits a JSON array; names are **camelCase** wire names (from each accessor's `_path`) matching the docs |
| errors | unknown resource → **did-you-mean** (difflib) + names the real `dhis2 metadata type list` command |
| help | sub-app descriptions say `get` (not `show`); `--page`/`--page-size` explain no-flag=full vs paged-caps-50; filter operators (`ilike` vs `$ilike`), `--all` (not `--all-streams`) |
| bridge robustness | single-string args tokenized (shlex); `doctor metadata` added to read-only allowlist |
| capability | `metadata list --count` (one-request totals), `--output <file>` (bulk dump); typed per-resource `list` consolidated onto generic `metadata list <type>` |

## Read-surface hardening — queued (specs to implement)

From the 6-agent gap sweep (vs play42). Each is ready to apply across v41/v42/v43.

### 1. Help-text fills for analytics/tracker/aggregate reads
Many option helps are empty (no description) and there are no runnable examples. Highest-value
target for small models. Exact proposals (v42 line numbers; mirror to v41/v43):
- `analytics/cli.py` `--dim` (query, ~line 61): "Dimension as 'axis:value', repeatable. axis =
  dx (data element/indicator UID, or DE.COC), pe (period e.g. LAST_12_MONTHS or 202401), ou
  (org-unit UID). dx+pe required. UIDs from `metadata list … --fields id,name`."
- `analytics events query` `--dim` (~line 132): note that aggregate-mode value dim is
  `<stageUID>.<deUID>` WITHOUT a `dx:` prefix (a `dx:` prefix errors "no valid dimension
  options: dx").
- `analytics/cli.py` query/events docstrings: add a complete runnable example
  (`analytics query --dim dx:Uvn6LCg7dVU --dim pe:LAST_12_MONTHS --dim ou:ImspTQPwCqd`).
- `tracker/cli.py` `list_command` + `event_list_command`: fill empty helps for `--org-unit`,
  `--ou-mode` (SELECTED|CHILDREN|DESCENDANTS|ACCESSIBLE|ALL), `--fields`, `--filter`,
  `--program`, `--program-stage`, `--after`/`--before` (ISO YYYY-MM-DD), `--status`; add an
  example (`data tracker list Person --ou ImspTQPwCqd`).
- `aggregate/cli.py get`: docstring example + note period must match the dataSet's periodType
  (Monthly→202401, Yearly→2024) and values usually live at facility level (pass `--children`).
- Period grammar (for docstring/help): relative LAST_12_MONTHS/THIS_YEAR/LAST_4_QUARTERS/…;
  fixed 2024 / 202401 / 2024Q1 / 2024W01; lists `202401;202402`; arbitrary windows via
  `--start-date/--end-date` (YYYY-MM-DD).

### 2. Removed-typed-list discoverability
`metadata <subapp> list` / `show` → bare "No such command" with no pointer. Add hidden
redirect commands via a DRY helper `_register_list_redirect(sub_app, wireName)` that registers
hidden `list`/`ls` → "use `metadata list <wireName>`" and `show <uid>` → "use `metadata get
<wireName> <uid>`" (raise typer.Exit(2)). Apply to the high-traffic authoring sub-apps. NOTE:
under `DHIS2_MCP_READONLY=1` these redirect paths are not in the allowlist, so the bridge
refuses them before the redirect prints — the rewritten docstring already steers models away,
so this is mainly for direct-CLI use (decide whether to allowlist the redirects).

### 3. Analytics 0-row hint (empty-vs-error)
Analytics/data return `[]` silently for a wrong period/org-unit. Add a YELLOW **stderr** hint
on 0 rows echoing the applied dims ("validated but matched no data; check pe:/ou:") in
`analytics/cli.py` query/events/enrollments commands. Stdout JSON + exit code unchanged.

### 4. cli_errors exit-code hardening (defensive — not a current bug)
`cli_errors.py run_app` ends in `sys.exit(0)`; today all errors still exit non-zero (Click
standalone mode owns the code; domain errors → `sys.exit(1)`), so the bridge contract holds.
Harden anyway: `except SystemExit: raise` + change the fallthrough to `raise SystemExit(1)`,
and consider narrowing the broad `except LookupError` so `KeyError`/`IndexError` bugs aren't
masked as clean exit-1 messages.

### 5. CLI bugs (our code)
- **`data tracker list <TET> --program <uid>` always 400s** — the CLI sends both
  `trackedEntityType` (required positional) and `program`; DHIS2 rejects (E1003). Send only
  one scope (prefer `--program` when given). `tracker/cli.py list_command` + `service.py
  list_tracked_entities`, v41/v42/v43.
- **`files documents list --details` shows empty columns** — uses `Document.url` (a filename
  like `pivot-table.pdf`) as the fileResource UID → `/api/fileResources/<filename>` 500
  (swallowed). `/api/documents` exposes no FR UID; source contentType/size from
  `/api/documents/{uid}/data` headers instead. `files/cli.py documents_list_command`,
  v41/v42/v43.

### 6. Also noted
- `metadata get <type> <bad-uid>` → HTTP 405 (upstream, BUGS.md #42); pre-validate UID shape
  (`^[A-Za-z][A-Za-z0-9]{10}$`) locally before the request.
- Re-expose type-specific list filters + migrate docs/examples off the removed typed lists
  (separate, pre-existing roadmap item).
