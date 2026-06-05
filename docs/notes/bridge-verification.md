# Bridge verification — capable model + local-model re-benchmark (reads + writes)

Verification of the hardened `dhis2w-mcp-bridge` after the read-surface work. Three parts: a
capable model (me) driving the bridge, a 6-model qwen benchmark scoring **tool-call parse
reliability** + correctness + writes, and a self-review of remaining gaps. Reads ran against
play42 (read-only); writes against local_basic (create-only, auto-cleaned). gemma excluded
(LM Studio's gemma4 parser fails on complex tool calls — a host bug, not ours).

## TL;DR / recommendation

- **Tool-call parse reliability: 100% for every qwen model** (0 failures / 48 calls). qwen's
  serialization is solid in LM Studio — the gemma parse failures do not occur. Use qwen.
- **Best driver: `qwen/qwen3.5-4b`** — 100% parse, correct reads incl. the analytics name→UID
  query, AND it completed BOTH writes (by discovering `metadata data-elements create` via
  `--help`), at reasonable speed (8–36s).
- **`qwen2.5-7b`** — excellent reads, fast; but failed writes (guessed `metadata create
  dataElements`, which doesn't exist). Great read-only driver.
- **`qwen/qwen3.6-27b`** — most correct on the hard join + asked for write confirmation (nice),
  but far too slow (240–370s on complex prompts). Not interactive.
- **`qwen2.5-coder-3b`** — fast, clean simple reads, but invents a `profile:"prod"` and guesses
  fake analytics UIDs / wrong write verbs. OK for simple reads only.
- **`qwen2.5-3b`** — weakest; misuses `metadata search` (`--filter` instead of a positional
  query) and wrong command structures. Avoid.

## Part 1 — me (capable model) driving the bridge: PASS

From the docstring alone I ran every read and a write round-trip with zero friction:
count (1332), the level-2 join (`organisationUnitLevels level:eq:2`→"District" + the 13
districts), `metadata search`, `metadata usage` (reverse lookup), the nested filter
`dataSetElements.dataSet.id:eq:` (123 DEs), `metadata export -o file`, event-analytics
`<stage>.<de>`, and a dataElement create→get→rename→delete (cleanup verified). The read-only
guard refused the write (126). The docstring additions (search/usage/presets/nested/export)
were all used directly — they paid off.

## Part 2 — qwen benchmark (6 models × 8 prompts)

Parsed = LM Studio produced a valid tool call. **Every cell parsed (no host-layer failures).**

| model | parse | simple reads | level2 | level2+join | analytics | writes | speed |
|---|---|---|---|---|---|---|---|
| qwen3.5-4b | 100% | all ok | ok (join) | table (level name weak) | **correct** | **both created** (via --help) | 8–36s |
| qwen2.5-7b | 100% | all ok | ok | partial | **correct** | **failed** (guessed `metadata create`) | 5–32s |
| qwen3.6-27b | 100% | all ok | ok | **best — full join → "District"** | **correct** | 1 created, 1 asked-to-confirm | **240–370s (too slow)** |
| qwen3.6-35b-a3b | 100% | all ok | looped | empty | **correct** | created DE via --help; DEG failed | 9–60s |
| qwen2.5-coder-3b | 100% | ok (but invents profile:"prod") | ok | nested-field guess | failed (fake UID) | failed (`metadata create`) | **6–9s (fastest)** |
| qwen2.5-3b | 100% | search misuse | confused | confused | failed | failed | 4–18s |

Findings:
- **Reads are solid on the capable qwens.** Models reliably used `--filter level:eq:2`,
  `name:$ilike:ANC`, `metadata list organisationUnitLevels` for the level name, and the
  analytics `--dim dx:/pe:/ou:` name→UID flow — exactly the patterns the hardened docs teach.
- **The level-2 + level-name JOIN is borderline** even for capable models — only 27b nailed it
  cleanly; 3.5-4b got the table but mislabeled the level name; 35b looped/empty. Expected: a
  cross-resource join is at the edge of small-model planning.
- **Writes split cleanly by behavior: discover vs guess.** Models that ran `metadata
  data-elements create --help` first (3.5-4b, 35b, 27b) succeeded; models that *guessed*
  `metadata create dataElements` / `metadata createDataElement` (coder-3b, 2.5-3b, 7b) looped
  on exit-2 and never recovered. The single most common wrong guess is **`metadata create
  <type>`** (the real shape is `metadata <type-kebab> create`).
- **Good safety signal:** 27b emitted "This will modify your DHIS2 instance… Do you confirm?"
  before the write — the docstring's "confirm before writes" landing.
- **Minor model errors:** coder-3b invented `profile:"prod"` (hit a different server → wrong
  count); 2.5-3b used `metadata search --filter` (search takes a positional query); the
  `metadata list dataElement` (singular) misses were caught by the did-you-mean hint (it
  worked — 2.5-3b recovered to `dataElements`).

## Part 3 — self-review: my remaining gaps (all write-side)

Even as a capable model, where I succeeded only via prior DHIS2 knowledge the docs don't give:
- **No write/authoring primer in the docstring.** For `indicator create` I had to know to look
  up an `indicatorType` UID (no authoring group) and the `#{deUID}` expression syntax. The
  docstring is read-only-focused.
- **Sharing's singular type-name trap** — `metadata share dataElement` (singular) vs the plural
  used everywhere else; the docstring's "plural camelCase" rule points the wrong way here.
- **Relationship mutators break the JSON contract** — `data-sets add-element` returns
  `+ element … total=1` (plain text) at exit 0, contradicting "success ⇒ JSON".

The benchmark **confirms** these: a `WRITES` primer in the docstring (the `metadata
<type-kebab> create` pattern, "no `metadata create <type>`", "relationship verbs print a
summary not JSON", "sharing uses the singular type") would convert the write failures
(coder-3b, 7b) into successes — 3.5-4b already proves a 4B can author once it discovers the
shape. This is the top item for the write phase.

## Top actionable items (write phase, when ready)

1. **Add a compact WRITES section to the `dhis2_cli` docstring** — the `metadata <type-kebab>
   create` pattern + "there is no `metadata create <type>`"; this is the highest-leverage fix
   (it flips guess→discover and rescued every read fix's equivalent on the write side).
2. `--json` on the relationship mutators (add-element/add-member/etc.) — keep the JSON contract.
3. `metadata share` accept the plural type; clearer error on the singular/plural mismatch.
4. (host) gemma-4-e4b needs a newer LM Studio / fixed gemma4 tool-call parser to be usable.

Raw data: `/tmp/bench_v3_report.md` (ephemeral). Benchmark harness pattern + this report are
the durable record.
