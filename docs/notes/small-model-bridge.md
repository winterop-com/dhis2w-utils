# Small-model MCP bridge — working notes

Working log for making the dhis2 toolkit usable by **small local models** (LM Studio / Ollama
/ llama.cpp) via `dhis2w-mcp-bridge` — a single MCP tool (`dhis2_cli`) that shells out to the
`dhis2` CLI. Tracks the model benchmark + the CLI/bridge read-surface hardening.

- Branch / staging PR: `feat/dhis2-mcp-cli-bridge` (PR #360 — testing PR, split into smaller PRs).
- Done → PR #360 description + commits. Queued → `docs/roadmap.md` ("Small-model bridge"
  follow-ups). Upstream quirk → `BUGS.md` #42. Testing rule: reads → `play42`, writes →
  `local_basic` (never mutate the shared public demo).

## How to run a round (the rig)

The canonical harness is **`infra/scripts/bridge_round.py`**, wrapped by **`make bridge-round`**.
It drives the real bridge (FastMCP client, same config as `~/.lmstudio/mcp.json`) from LM Studio's
OpenAI-compatible API — `lms chat` can't do this (it doesn't load MCP servers; only the GUI does).

```bash
make bridge-round ROUND=read                                   # play42, readonly (default)
make bridge-round ROUND=write                                  # local_basic, writes on; round-trips minPasswordLength
make bridge-round ROUND=bench                                  # the timed table prompts below
make bridge-round MODEL=qwen/qwen3.5-4b ROUND=read             # any LM Studio model key
```

The target starts `lms server`, loads the model if not already loaded (idempotent — avoids the
ambiguous-id 400 below), then runs the script. `ROUND=write` forces `--profile local_basic` and
captures+restores the setting it touches, so it is safe to re-run.

Gotchas (both cost real time once):

- **Duplicate model instances → HTTP 400.** `lms load` of an already-loaded model creates a second
  instance (`<model>:2`); a bare model id is then ambiguous and the API 400s. The target guards
  against it; if you load by hand, `lms ps` then `lms unload --all`.
- **Echo `type:"function"` on tool calls.** When sending the assistant's tool calls back in the next
  request, each must keep `type:"function"` or LM Studio rejects with `Invalid 'messages'`. The
  harness models this; note it if you hand-roll a host loop.

Testing rule (unchanged): reads → `play42`, writes → `local_basic` (never the shared public demo).

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
| **gemma-4-12b-qat** | 12B (7.2GB) | yes | 1 | 109 | 17 | 33 | qat quant of the 12b below: ~25-40% faster, same accuracy; printed the dump inline (no `--output`) |
| google/gemma-4-12b | — | yes | 1 | **147** | 13 | 91 | correct but slowest (bf16) |
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

### 1. Help-text fills for analytics/tracker/aggregate reads — [SHIPPED]
Filled the empty `--option` helps (tracker list/event-list `--program`/`--org-unit`/`--ou-mode`/
`--fields`/`--filter`/`--status`/`--after`/`--before`/`--te`/`--enrollment`/`--program-stage`,
analytics `--start-date`/`--end-date`/`--ou-mode`), expanded the analytics `--dim` help (dx:/pe:/ou:
prefixes; events aggregate `<stage>.<de>` no-dx: rule), and added runnable examples to the
analytics query/events + aggregate get docstrings. Period/UID detail lives in the bridge docstring.
Original proposals (v42 line numbers; mirrored to v41/v43):
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
- **[SHIPPED] `data tracker list <TET> --program <uid>` always 400s** — fixed: `TYPE` is now
  optional and the command takes a TrackedEntityType OR `--program` (exactly one), sending only
  the chosen scope. v41/v42/v43.
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

## Round 2 — read+write agent sweep (reads → play42, writes → local_basic round-trips)

Five agents exercised read + write across the CLI (all writes were create→verify→delete on
local_basic with `ZZPROBE_` prefixes; zero leftovers, play42 never mutated).

### Shipped from this round
- **Read-only guard fix**: `metadata usage` and `metadata export` are pure reads but were
  refused under `DHIS2_MCP_READONLY=1` — added to the allowlist (+ drift-test verbs).
- **Docstring**: added `metadata search <text>` (the best cross-type name→UID resolver) and
  `metadata usage <uid>` (reverse lookup); `--fields` presets (`:identifiable/:nameable/:owner/
  :all`, `:all,!field`); nested filter paths (`dataSetElements.dataSet.id:eq:`), `in:[a,b]`,
  `null/!null`; and an `export` warning (always `-o`, never to stdout — a full export is ~20MB).
- **`metadata list --filter` help**: documents `in:[]`, `null/!null`, and dotted nested paths.
- **`metadata export --output` help**: payload-size caution.

### Write-surface feasibility for a small model (3–4B)
| operation | feasibility | blocker |
|---|---|---|
| dataElement create/rename/delete | HIGH | 3 obvious flags, no UID lookups |
| aggregate set/delete (data value) | HIGH | inline flags; `--coc` optional |
| dataSet create / add-element | MED-HIGH | one DE UID lookup; add/remove print non-JSON |
| dataElementGroup create / add-members | GOOD | repeatable `-e`, clear |
| orgUnit create/move/delete | GOOD | two positional UIDs on move |
| program create | MED | default WITH_REGISTRATION needs a `-tet` UID; use WITHOUT_REGISTRATION |
| indicator create | MED | needs an indicatorType UID (no authoring group) + `#{de}` expression |
| tracker event create | MED | 4 UIDs + `--dv UID=value` micro-syntax |
| sharing (`metadata share`) | MED | DHIS2 singular type name (`dataElement`) vs plural elsewhere; `rwrw----` string |
| category → categoryCombo chain | LOW | 3-level dependency, `--expected N` for COCs, reverse-order delete; `build --spec` needs JSON |
| optionSet create/delete | LOW | no create/delete verb — must hand-write a `metadata import` bundle |
| userGroup create/delete | LOW | no create/delete verb — `metadata import` only |
| tracker entity/event DELETE | LOW | no inline delete — JSON file + `push --strategy DELETE` (async) |
| route create | LOW | flag-form hangs on the interactive auth prompt; `--file` no-auth shape undocumented |

### Deferred write-surface fixes (queued)
- **`--json` not honored by mutating relationship verbs** (`add-element`/`remove-element`/
  `add-option`/`add-category`/`add-to-ou`/`remove-from-ou`/`add-members`/`remove-members` and
  some `delete`s print a plain-text summary at exit 0) — breaks the bridge "success ⇒ JSON"
  contract. Make them emit JSON under `--json`. Broad sweep, v41/v42/v43.
- **`route create`**: flag-form drops into an interactive auth prompt (hangs without a TTY) and
  `--file` with `auth:{type:none}` crashes with a raw pydantic traceback. Add `--no-auth`/`--auth`,
  accept/normalize a no-auth payload, and replace the traceback with a clean error.
- **`metadata share` accepts only the singular DHIS2 type** (`dataElement`) while get/list want
  plural — accept plural too (or map it) so the vocabulary is consistent.
- **Missing authoring verbs**: `optionSets` and `userGroups` have no `create`/`delete` (only
  `metadata import`); `metadata import` create returns an empty `objectReports` so the new UID
  isn't echoed (forces a follow-up list). Consider create/delete verbs + echoing created UIDs.
- **No inline tracker delete** (`data tracker event/enrollment/entity delete`); `push` is async
  (returns a job, not a confirmation) while `event create` is sync — sibling inconsistency.
- **`data aggregate get` is keyed by dataSet, `set` by dataElement** — a model can't verify its
  own write with the same key; consider a `--de` filter on `get`.
- **Generic 409 on constrained deletes** (e.g. orgUnit with children) — surface the real reason.
- **Stale `pager.total`** after a delete (DHIS2 quirk — `--count` lags the row query briefly).

## Round 3 — gemma-4-12b-qat sweep + security plugin (reads → play42, writes → local_basic)

Drove the **real bridge** (FastMCP client) from LM Studio's OpenAI-compatible API with
`gemma-4-12b-qat`. READ round (play42, `DHIS2_MCP_READONLY=1`) then WRITE round (local_basic,
`DHIS2_MCP_READONLY=0`, minPasswordLength round-tripped 8→10→8).

### Shipped from this round
- **Read-only guard fix**: `security settings` (the new plugin's only command) is a pure
  `GET /api/systemSettings` but was refused under `DHIS2_MCP_READONLY=1` — the model hit
  `exit 126`. Added `("security","settings")` to `READ_ONLY_COMMANDS`. It is path-specific,
  **not** a new verb: `settings` is a read under `security` but a WRITE under `customize`
  (bulk-set), so the verb heuristic can't reach it — added a `READ_ONLY_LEAVES` exception to the
  drift test plus a regression test pinning `security settings` allowed / `customize settings`
  denied. The drift test was blind to the gap because both sides derived from the same verb set.

### Model behaviour (gemma-4-12b-qat)
- **Reads: strong.** Count (1037), ANC-indicator filter, whoami+version all one-shot and fast
  (see table). The qat quant is the sweet spot of the 12b — much faster than bf16, still correct.
- **Multi-step write discovery: weak.** Asked to set a system setting, it never found
  `customize set` — guessed `system`, `metadata search` (looped), `--help` pages, and ran out
  of steps even *with* a hint. The write path itself is fine (confirmed directly through the
  bridge under `READONLY=0`: set→verify→restore all exit 0); the gap is discoverability — system
  settings live under `customize set <key> <value>`, two levels deep under a `dev` group a
  model doesn't associate with "settings".
- **Failure mode: arg-mangling.** At temperature 0.2 it sometimes emitted the whole command as one
  escaped-quote string (`["metadata\", \"search\", ..."]`) → the bridge's space-split produced
  `metadata, search, ...` → "No such command". The existing shlex tokenizer handles spaces but not
  embedded quotes.

### Queued from this round
- **System-setting writes are undiscoverable** for small models. `customize set` is buried;
  consider surfacing a `system setting set <key> <value>` alias (or a top-level hint) so "set a
  system setting" maps to where models look first (`system`).
- **Bridge arg-robustness**: when `args[0]` contains escaped quotes/commas (a JSON-ish blob), the
  shlex split mis-tokenizes. Detect a single-element `args` that looks like packed JSON and parse
  it, or strip stray quotes before splitting.
- **"What is the schema of X?" has no affordance → field hallucination.** From a live LM Studio
  GUI session (gemma-4-12b-qat, `~/Downloads/chat.md`) — confirms the bridge works natively in the
  GUI's MCP client, but the "schema" question failed hard. Asked for a dataElement's schema, the
  model tried `--limit 1` (no such option → exit 2), then a pile of invented `--fields`
  (`name_type`, `options_set_id`, `data_element_type_id_ref_id`, …), and finally answered the
  unrelated "33 data elements". Two root causes + fixes:
  - **[SHIPPED] No command answered "what fields does type X have".** Added a **top-level `dhis2
    schema <type>`** that introspects the **generated model** for `<type>` and prints field names +
    types + required/optional. The DHIS2 major is **auto-detected from the connected server**
    (`/api/system/info`, SNAPSHOT-safe) — no version pin needed — then the matching generated tree
    is introspected. "Schema" here means the toolkit's own typed
    view — today a blend of `/api/schemas` (metadata resources) and `/api/openapi.json`
    (instance-side shapes: tracker writes, envelopes, auth schemes) that codegen merges into
    `dhis2w_client.generated.v{N}.{schemas,oas}` — i.e. exactly what the client parses/accepts, not
    a single live endpoint. **Direction of travel: as the DHIS2 OpenAPI spec matures it becomes the
    single correct source, subsuming `/api/schemas`** — so `schema` prefers the `oas` tree
    (`--source` overrides), treating `schemas` as the shrinking interim complement. **Top-level, not
    under `metadata`**: it resolves *any* modeled type, metadata or instance-side (verified:
    `dataElement`, plural `dataElements`, `WebMessage`), so it isn't confined to the metadata CRUD
    vocabulary. Unknown names list candidates (exit 2) like `metadata search`. Added to the bridge
    read-only allowlist. Verified live across play41/42/43 (no pin, no `DHIS2_VERSION`): each
    auto-detects its own major — v41 `DataElement` carries a `user` field dropped in v42/v43.
  - **[SHIPPED] DHIS2 silently accepts unknown `--fields`** and returns partial data at exit 0, so a
    bad `metadata list --fields` call looked successful and the model never learned it guessed wrong.
    `metadata list` now emits a soft YELLOW stderr warning naming any requested field absent from
    the generated model (union of oas + schemas + tracker), e.g. `name_type, options_set_id`. Plain
    comma-lists only — preset/wildcard/`!exclusion`/nested/dotted expressions are skipped to avoid
    false positives. Non-blocking: the query still runs, the model just gets the corrective signal.

## Round 4 — read + write + performance benchmark (roster)

Full read+write+perf sweep across a curated model roster, plus the capable cloud model as the
correctness reference. Results + methodology + roster live in
[`model-benchmark.md`](model-benchmark.md); re-run with `make bridge-bench`. Headline:
`gemma-4-12b-qat` is the only local model that passed both read and write, and it beats its bf16
sibling on speed at equal correctness. qwens read fast but stall on the write (discoverability of
`customize set`). All five now use `dhis2 schema` for the "what fields" task.

### Validated in a live GUI session (gemma-4-12b-qat, chat.md)
Asked to **create** a dataElement, the model first ran `dhis2_cli(["schema","dataElements"])` to
check the shape before writing — the `schema` command is now part of the natural write workflow,
exactly as intended.

### Shipped from this round
- **[SHIPPED] `dhis2 schema` expands enum fields to their allowed values.** Enum-typed fields now
  render as `valueType: ValueType (TEXT, NUMBER, INTEGER, ...) | None` (all members), so a model can
  pick a valid value on a write without guessing — the gap seen in the create session.

## Round 5 — multi-purpose write (the real bar)

The `bridge-bench` write is single-purpose and *hinted* (one `customize set`). The honest test is
a multi-object write. Drove the champion `gemma-4-26b-a4b-qat` (local_basic, READONLY off) on:
"create a Monthly data set + three INTEGER data elements, attach all three, confirm 3 elements."

- **Construction succeeded.** ~10 steps: created the data set, created 3 data elements, attached all
  three, and verified — even self-correcting `metadata get data-sets` -> `dataSets` mid-run.
- **Termination failed.** After verifying, it did not recognize it was done — it re-issued the create
  (rejected), then looped on `--help` to max steps. No clean final confirmation.

So multi-purpose writes are *partially* in reach of the strongest local model: it can build the
structure, but can't reliably tell it's finished. Smaller models would stall earlier. This is the
real write bar — far above the hinted single-key `bridge-bench` write.

- **CLI usability finding**: `metadata get dataSets` uses the camelCase wire name, but the mutating
  sub-app is `metadata data-sets` (hyphenated). The model tripped on this (step 11), and so did the
  cleanup script. The `dataSets` vs `data-sets` split between read-by-wire-name and the hyphenated
  mutating sub-apps is a real discoverability wart worth smoothing (accept both forms, or alias).

## Round 6 — multi-purpose write at scale: data set + 10 elements

Drove the whole roster on "create a Monthly data set + ten INTEGER data elements, attach all ten,
confirm 10" (local_basic, writes on, ZZMulti-prefixed + cleaned before/after each model, max 30 turns).

| model | dataSet | elements | attached | terminated | calls | secs |
|---|---|---|---|---|---|---|
| gemma-4-26b-a4b-qat | yes | 6/10 | 0/10 | no | 30 | 140 |
| gemma-4-12b-qat | no | 0/10 | 0/10 | no | 30 | 385 |
| gemma-4-12b (bf16) | yes | 7/10 | 0/10 | gave up @19 | 19 | 255 |
| gemma-4-e4b | no | 6/10 | 0/10 | no | 30 | 427 |
| qwen2.5-7b-instruct | no | 10/10 | 0/10 | no | 176 | 606 |
| qwen3.5-4b | yes | 1/10 | 0/10 | gave up @5 | 5 | 27 |

**No model completed it, and `attached=0` for every one.** Two failure modes: (1) pace/step budget —
the 26B was on-track but ran 1 call/turn and the 30-turn cap cut it off mid-build; (2) UID
correlation — qwen2.5-7b had calls to spare (176!) but never wired the elements, because the attach
step requires holding the data set UID and each just-created element UID together. The *wiring* of
many freshly-created objects is the cognitive wall, not the creates.

Caveat: max 30 turns is barely above the ~22-call ideal (1 create + 10 elements + 10 attach +
verify), so on-pace models are under-tested — see the higher-budget champion re-run below. Bottom
line: a 10-object *wired* write is beyond all current local models; the capable-agent oracle does it
100%. This is the real write ceiling, far above the hinted single-key bench write.

### Round 6 follow-ups: budget vs ceiling, and the oracle baseline

- **Higher turn budget doesn't rescue it.** Re-ran the champion `gemma-4-26b-a4b-qat` at **50 turns**
  (vs 30): it did *worse* — data set + only 2/10 elements, 0 attached (vs 6/10 before). Run-to-run it
  swings (6/10 then 2/10) but never attaches. So this is a **coherence ceiling**, not a step-budget
  one: the model loses the thread holding 10 object UIDs and wiring them over a long sequence.
- **The oracle (capable agent) does it 100%.** The same 10-element wired write, driven
  deterministically: data set + 10 elements + 10 attaches → verified "10 elements attached" → cleaned
  up, 0 leftovers. The CLI is fine; the failure is entirely model coherence over a long multi-object
  write. That gap — trivial for a capable agent, a wall for every local model — is the headline.
