# Validate the instance

**Who this is for:** the operator gating a build, and the implementer sizing
up an instance's codes before generating anything.

**Before you start:** a d2w with a profile for your instance. A project is
optional - see [scope](#read-the-scope-column) for what having one changes.

**You will be able to:**

- run the FHIR-safety check and read its verdict off the terminal
- say what an error, a warning, and an info each cost your build
- use the code-source dial to preview a code migration
- hand the written report to whoever owns the metadata

## Run it

```console
$ d2w fhir validate
running 5 step(s)
[1/5] connecting: http://localhost:8080
[2/5] selection: 2 data sets, 4 programs, 3 stages, 70 data elements, 12 option
sets, 5 categories, 1,332 organisation units
[3/5] instance sweep: 40 collections, 1,614 objects
[4/5] option sets: 12 read
[5/5] findings: 41 finding(s)
wrote /home/you/demo-ig/reports/fhir-validate-report.md
wrote /home/you/demo-ig/reports/fhir-validate-report.csv
wrote /home/you/demo-ig/reports/fhir-validate-report.pdf
                                 fhir validate
┌───────────────────┬──────────────────────────────────────────────────────────┐
│profile            │ local_basic (fhir.toml)                                  │
│resource types     │ 40                                                       │
│objects swept      │ 1614                                                     │
│option sets        │ 12                                                       │
│options            │ 48                                                       │
│attributes         │ 4                                                        │
│errors             │ 0                                                        │
│warnings           │ 8                                                        │
│infos              │ 33                                                       │
│selection findings │ 0 errors, 8 warnings, 20 infos                           │
│code coverage      │ 1/1428 (selection objects whose code can serve as an     │
│                   │ identity stem)                                           │
│code source        │ id                                                       │
└───────────────────┴──────────────────────────────────────────────────────────┘
               findings by category (5)
┏━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━┓
┃Severity ┃ Scope     ┃ Category              ┃ Count┃
┡━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━┩
│warning  │ selection │ template-hostile-name │ 8    │
│info     │ selection │ spaced-code           │ 20   │
│info     │ instance  │ invalid-code          │ 1    │
│info     │ instance  │ missing-code          │ 1    │
│info     │ instance  │ template-hostile-name │ 11   │
└─────────┴───────────┴───────────────────────┴──────┘
ok: passed: 8 selection warning(s), 20 selection info(s), 13 instance finding(s);
full findings in /home/you/demo-ig/reports/fhir-validate-report.md
```

The default output is a status view, not the finding firehose: the summary
table, a rollup with one row per (severity, scope, category), **every error
individually** - because an error is what gates the build and you need the
object without opening a file - and one closing line. `instance` rows render
dimmed so the build path carries the visual weight. A national instance
raises hundreds of warnings; reading them one row at a time is what the
written report is for. `--details` puts every finding on the terminal too.

## Read severity as build impact

Every finding is graded by what it does to *your* build, not by abstract
hygiene:

| Severity | Meaning |
| --- | --- |
| error | Your build will abort. A build-aborting `<` code on an in-scope identifier surface - the very codes `d2w fhir generate` refuses through the same predicate. The only findings that gate exit 1. |
| warning | An in-scope degradation the build survives - a code falling back to the UID, a name malforming its page. |
| info | Instance hygiene: the same defects on objects the build never reads - a code-migration watchlist, not build noise. |

The summary's **code coverage** line counts how many in-scope objects carry
a code usable as an identity stem - the R4 `id` bar, stricter than the R4
`code` datatype. It is the number to watch grow before switching
`[generate.naming]` `source` from `"id"` toward `"code"`.

### Read the scope column

Before anything is graded, the run resolves the configured selection into an
emission scope - the same selection semantics `generate` uses, so validate
and generate can never disagree about what is on the build path. Every
finding carries the verdict as its `scope`: `selection` for objects the
configured IG emits, `instance` for the rest.

Outside a project every selection table is empty, which selects everything
of its kind - so the whole instance grades as being on the build path.
Inside a project, findings grade against that project's own selection.

## Know what the four passes cover

| Pass | What it covers |
| --- | --- |
| Instance-wide sweep | Every object's code in every collection `/api/metadata` returns, checked against the R4 `code` datatype; per-type duplicates; organisation units with no code at all. |
| Deep option-set pass | Exactly what code-mode generation would do with each option set's options, over the same projections the emitter consumes. |
| Code-stem pass | Exactly what a code-sourced `[generate.naming]` `source` does with each in-scope object of the naming surfaces (option sets, categories, org units, data sets, programs, program stages). |
| Deep attribute pass | Every DHIS2 attribute the instance left uncoded - `info`, a coverage signal about how legible the `D2AttributeValue` extension is to a consumer without the instance. |

Every pass also checks the object's **name** for one thing that has nothing
to do with codes: `template-hostile-name`, a warning on any name carrying
`<`, `>`, or `&`, which the IG publisher's template injects into HTML
unescaped and then strict-parses - the page renders malformed until the name
changes in DHIS2.

Its sibling `template-hostile-code` is the one that aborts builds: an
**error** on an in-scope code containing `<`, raised only on the collections
whose codes become identifier values (`optionSets`, `categories`,
`organisationUnits`, `dataSets`, `programs`, `programStages`). The publisher
writes identifier values into a table cell unescaped, fails in its *last*
pass - so on a large IG one hostile code costs the entire build before it
says so. The same finding here takes seconds. `>` and `&` cost a malformed
page rather than an aborted build, so they stay warnings. Generation does
not escape its way around either finding: names and identifier values are
what a consumer matches on, and an IG that disagrees with its instance is
worse than a malformed page. The fix is in DHIS2, which is what the finding
is for.

## Preview a code migration with `--code-source`

The option-pass findings are gated on the effective code source - the
`--code-source` flag when given, otherwise `concept_code_source` from
`fhir.toml`. In `id` mode (the default) `invalid-code`, `missing-code`, and
`duplicate-code` are downgraded to `info` and their message says so, because
generation is not reading those codes yet. Run with `code` to see what
switching would cost:

```bash
d2w fhir validate --code-source code
```

The code-stem pass works the same dial for naming: under
`source = "code-or-id"` a missing, unusable, or colliding code is a
`code-stem-fallback` warning (that object's ids fall back to the UID); under
`source = "code"` the same object is a `code-stem-refusal` **error** -
`d2w fhir generate` refuses the run through the same defect predicate, so a
validate error equals a generate refusal. `spaced-code` is the info-grade
neighbour: a code with spaces is FHIR-valid but emits in the quoted
`#"..."` FSH form.

## Hand over the report

`--output-dir` names a directory, created if needed; the files inside are
always `fhir-validate-report.md` / `.csv` / `.pdf`. The default is
`reports/` under the project root, or under the working directory when there
is no project. `--format` takes a comma list of `md`, `csv`, `pdf`; all
three are written by default, and each written path is echoed.

| File | Shape |
| --- | --- |
| `.md` | Findings grouped under one section per resource type, a Scope column on every row. |
| `.csv` | One row per finding: `severity,scope,category,resource_type,uid,name,code,message`. For spreadsheets and for diffing two runs. |
| `.pdf` | Cover page with summary counts, clickable table of contents, one bookmarked section per resource type with severity-tinted rows. Noto Sans with a Noto Sans Lao fallback, so Lao-script names render. |

The human-facing renderings print a code with its control characters escaped
(`BLUE\nBLUE` reads on one line) and wrap a code with leading or trailing
spaces in double quotes (`" M "`), so an invisible character is visible; the
CSV and JSON carry the raw code. The scaffolded `.gitignore` covers
`reports/` - the reports are regenerable snapshots of instance state; pin
one deliberately (`git add -f`) when handing it over.

## Wire it into CI

Exit 1 when there are errors - `--fail` is the default - which makes the
command a CI gate. `--no-fail` exits 0 regardless, and drops the red

```text
error: N error(s) found; exiting 1 (--no-fail to suppress)
```

line with it. `d2w --json fhir validate` emits the full findings list as
JSON on stdout in place of the tables; progress narration stays on stderr
(one plain `[k/N] label: summary` line per step when stderr is redirected,
which is the form a CI log wants; `--no-progress` silences it). The exit-1
gate still applies, so CI reads the findings off stdout and the job still
fails on errors. MCP exposes the same check as the read-only
`fhir_validate` tool; file writing stays CLI-only.

Next: [Generate the IG source](201-generate.md)
