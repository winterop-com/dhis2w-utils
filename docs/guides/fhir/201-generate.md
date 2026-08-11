# Generate the IG source

**Who this is for:** the operator regenerating an IG after a metadata change,
and the implementer running generation for the first time.

**Before you start:** a scaffolded project pointing at your instance
([Set up an IG project](201-set-up-a-project.md)), ideally after a clean
[validate](201-validate.md) - generate refuses the codes validate marks as
build-aborting.

**You will be able to:**

- run the whole pipeline, or one target of it, and read the summary
- say which directory each target owns and what a re-run does to it
- narrow the selection so a national instance stays reviewable
- find the notes a run raised and know which ones repeat validate

## Run the whole pipeline

```console
$ d2w fhir generate
running 8 step(s)
[1/8] instance metadata: 9 questionnaire target(s), 12 option set(s), 5
categories, 1,332 organisation unit(s)
[2/8] foundation: 16 written, 0 unchanged
[3/8] option sets: 36 written, 0 unchanged
[4/8] categories: 15 written, 0 unchanged
[5/8] questionnaires: 21 written, 0 unchanged
[6/8] examples: 9 written, 0 unchanged, 1 note
[7/8] organisation units: 2667 written, 0 unchanged
[8/8] pages: 15 written, 0 unchanged
full pipeline: 2,779 file(s) written across 7 target(s)
                               fhir generate (7)
┏━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━┳━━━━━━┓
┃Target         ┃ Directory                       ┃ Written ┃ Unchanged ┃ Deleted ┃ Notes┃
┡━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━╇━━━━━━┩
│foundation     │ ig/input/fsh/foundation         │ 16      │ 0         │ 0       │ 0    │
│option-sets    │ ig/input/resources/terminology, │ 36      │ 0         │ 0       │ 0    │
│               │ resources/concept-maps          │         │           │         │      │
│categories     │ ig/input/resources/categories,  │ 15      │ 0         │ 0       │ 0    │
│               │ resources/concept-maps          │         │           │         │      │
│questionnaires │ ig/input/fsh/data-sets,         │ 21      │ 0         │ 0       │ 0    │
│               │ fsh/event-programs,             │         │           │         │      │
│               │ fsh/tracker-programs,           │         │           │         │      │
│               │ fsh/data-dictionary,            │         │           │         │      │
│               │ resources/assignments,          │         │           │         │      │
│               │ resources/attribute-option-comb │         │           │         │      │
│               │ os, resources/concept-maps      │         │           │         │      │
│examples       │ ig/input/fsh/examples           │ 9       │ 0         │ 0       │ 1    │
│org-units      │ ig/input/fsh/organization,      │ 2667    │ 0         │ 0       │ 0    │
│               │ resources/registry              │         │           │         │      │
│pages          │ ig/input/pagecontent            │ 15      │ 0         │ 0       │ 0    │
└───────────────┴─────────────────────────────────┴─────────┴───────────┴─────────┴──────┘
note: 1 note(s) across 1 target(s); full list in
/home/you/demo-ig/reports/fhir-generate-notes.md (--details to print)
```

The bare run is the one to reach for: it reads the instance once and every
target builds off that single result, where seven separate commands each
open a client of their own. `make generate` is the same command through the
project's pinned toolchain. Re-running against an unchanged instance
converges to zero:

```console
$ d2w fhir generate
running 8 step(s)
[1/8] instance metadata: 9 questionnaire target(s), 12 option set(s), 5
categories, 1,332 organisation unit(s)
[2/8] foundation: 0 written, 16 unchanged
[3/8] option sets: 0 written, 36 unchanged
[4/8] categories: 0 written, 15 unchanged
[5/8] questionnaires: 0 written, 21 unchanged
[6/8] examples: 0 written, 9 unchanged, 1 note
[7/8] organisation units: 0 written, 2667 unchanged
[8/8] pages: 0 written, 15 unchanged
full pipeline: 0 file(s) written across 7 target(s)
```

## Know the eight targets

```text
d2w fhir generate                All seven, in that order, off one pass over the instance
d2w fhir generate foundation     Identifier aliases + the extensions + the capture contract
d2w fhir generate option-sets    Option sets -> CodeSystem/ValueSet pairs
d2w fhir generate categories     Categories -> CodeSystem/ValueSet pairs
d2w fhir generate questionnaires Data sets + event programs + tracker programs -> Questionnaires
d2w fhir generate examples       Example QuestionnaireResponses answering those Questionnaires
d2w fhir generate org-units      Organisation units -> Organization/Location instances
d2w fhir generate pages          Narrative site pages + per-artifact intros
d2w fhir generate load-set       Synthetic QuestionnaireResponse corpus into load/ (not IG source)
```

Name a target when you want that target alone - a tight edit loop on one
directory. A solo run prints its own detail table and all of its notes:

```console
$ d2w fhir generate pages
running 2 step(s)
[1/2] instance metadata: 9 questionnaire target(s), 1,332 organisation unit(s)
[2/2] pages: 0 written, 15 unchanged
                              fhir generate pages
┌──────────────┬──────────────────────────┐
│profile       │ local_basic (fhir.toml)  │
│project       │ /home/you/demo-ig        │
│target        │ ig/input/pagecontent     │
│files written │ 0                        │
│unchanged     │ 15                       │
│files deleted │ 0                        │
│pages         │ 6                        │
│intros        │ 9                        │
└──────────────┴──────────────────────────┘
```

What each target writes, and where:

| Target | Writes |
| --- | --- |
| `foundation` | `ig/input/fsh/foundation/` - the identifier aliases and NamingSystems, the `D2Period` / `D2FormType` / `D2AttributeValue` and tracker extensions, the response profiles, `$generate`, and the capture CapabilityStatement. Depends on `fhir.toml` alone; never touches DHIS2. Prerequisite for a compiling IG. |
| `option-sets` | Pre-built CodeSystem/ValueSet JSON into `ig/input/resources/terminology/`, ConceptMaps into `resources/concept-maps/`. |
| `categories` | Its own CodeSystem/ValueSet JSON into `ig/input/resources/categories/`, ConceptMaps into `resources/concept-maps/`. |
| `questionnaires` | One Questionnaire per data set (`fsh/data-sets/`), per event program (`fsh/event-programs/`), per tracker stage plus the program's registration form (`fsh/tracker-programs/<program stem>/`), the shared data dictionary (`fsh/data-dictionary/`), assignment Lists (`resources/assignments/`), and attribute-option-combo terminology (`resources/attribute-option-combos/`). |
| `examples` | One `Usage: #example` response per target into `fsh/examples/<target stem>-<n>.fsh`. |
| `org-units` | Profiles and level terminology into `fsh/organization/`; the registry as pre-built JSON - `Organization-<stem>.json` + `Location-<stem>.json` per unit - into `resources/registry/`. |
| `pages` | Six site pages plus per-artifact intros into `ig/input/pagecontent/` - markdown, not FSH. |
| `load-set` | Test data into `load/` beside `ig/`, for posting at a running facade ([Serve the IG](201-serve.md)). Gitignored; the bare run never writes it. |

What the artifacts contain - the extensions, the identifier slices, the
value-type mapping, the stems in those file names - is the reference
material in
[Identifiers and the D2 extensions](401-identifiers-and-extensions.md) and
[Terminology and ConceptMaps](401-terminology-and-conceptmaps.md).

**Each target owns its subdirectories and syncs each one**: writes what
changed, leaves what did not, deletes generated files that no longer belong.
A JSON sync owns its directory outright - it deletes every `*.json` the run
did not produce - which is why each terminology pair gets a directory of its
own. `concept-maps/` is the one shared directory; ownership there is stated
by file-name prefix. The `tracker-programs/` sweep prunes a per-program
subdirectory it emptied. Hand-authored files are safe by the same rule the
whole tree follows: the sweep only deletes files carrying the generated
header, so `ig/input/pagecontent/index.md` and any markdown you drop beside
it survive every regenerate.

**The pre-built resources are not committed.** The scaffolded `.gitignore`
covers `ig/input/resources/` - thousands of regenerable files - while
`ig/input/fsh/` is committed, so the FSH diff after a metadata change is
still there to review.

## Narrow the selection

Absent or empty selection tables mean *all of that kind on the instance*.
A national instance carries hundreds of forms, so an IG meant for review
names the handful of UIDs it is about:

```toml
[generate.data_sets]
include_ids = ["BfMAe6Itzgt"]       # Child Health

[generate.event_programs]
include_ids = ["VBqh0ynB2wv"]       # Malaria case registration

[generate.tracker_programs]
include_ids = ["IpHINAT79UW"]       # Child Programme - registration + one per stage

[generate.organisation_units]
max_level = 4                       # or root = "<uid>" for one sub-hierarchy
```

Or seed the same lists while scaffolding: `d2w fhir init --data-set ...
--event-program ... --tracker-program ... --max-level 4` (offline; written
as given). Points worth knowing:

- **The two program tables select opposite `programType`s**, and a UID
  listed under the wrong one fails the run by name rather than being quietly
  reshaped. With empty lists the sweep routes each program by its live type.
- **The option-set closure**: a selected form binding an option set outside
  `[generate.option_sets] include_ids` pulls the set in anyway, with a note.
  Validate resolves scope the same way, so the two never disagree.
- **Registry scale**: every organisation unit emits two instances, and the
  IG publisher renders a page per resource, so the registry sets the wall
  clock of `make build`. `org-units` warns once a registry passes 10,000
  instances, naming both dials (`max_level`, `root`). See
  [Build and publish the guide](201-build-and-publish.md).
- **Examples**: `[generate.examples]` `per_target` sets responses per form
  (0 disables the target); `source = "synthetic"` (default, deterministic,
  no data endpoint called) or `"instance"` (answers from the values the
  server holds - deliberate on production, since real captured values land
  in a document you are about to publish).
- **Locales**: `[generate] locales = []` means every locale found on the
  instance; list BCP-47 or DHIS2-style tags (`pt_BR` and `pt-BR` both work)
  to narrow. Only `NAME` translations are emitted.

## Read the notes

Each target raises aggregate notes - a selection entry that matched nothing,
an option set the closure pulled in, a form skipped for a `linkId`
collision. A note carries a **kind**, and three kinds (`code-fallback`,
`code-collision`, `stem-fallback`) are restatements of what validate already
reports. A bare run counts them - the echoes separately - and writes them
all to `reports/fhir-generate-notes.md`, grouped by target:

```text
note: 3 note(s) across 2 target(s) (+8 validate echoes); full list in
reports/fhir-generate-notes.md (--details to print)
```

Read that as: generation found three things worth your attention, and eight
more it would only be repeating `d2w fhir validate` to tell you about.
Nothing is hidden - the file carries every note, echoes under a trailing
`### Restatements of validate findings` heading. `--details` prints every
note inline instead; a solo target always prints all of its notes. From the
demo run above:

```console
$ cat reports/fhir-generate-notes.md
# fhir generate notes

- Profile: local_basic (http://localhost:8080)
- Generated: 2026-08-10T19:38:19+00:00

## examples

- 1 questions take an attachment, a geometry document, or a reference to a
DHIS2 object the IG does not publish; left unanswered in the synthetic
examples: Birth certificate (uf3svrmp8Oj)
```

Every command with an instance behind it narrates its steps on stderr - a
spinner on a terminal, one plain `[k/N] label: summary` line per step when
redirected. `--no-progress` turns it off; `d2w --json fhir generate` implies
it and puts the per-target file lists and counts on stdout as JSON.

## Check the site pages landed

`pages` is the last target and the only one writing markdown: `forms.md`,
`registry.md`, `terminology.md`, `identifiers.md`, `periods.md`, and
`capture.md` - the scaffolded site menu - plus per-artifact intros the
publisher injects into matching artifact pages (`Questionnaire-<stem>-intro.md`
always; CodeSystem and Organization intros only when the DHIS2 object
carries a description). `index.md` is scaffolded once and is yours. Every
DHIS2 name and description on these pages is escaped on the way in, so a
data set called "Mortality < 5 years by gender" renders as text rather than
aborting the publisher's HTML parse.

Next: [Build and publish the guide](201-build-and-publish.md)
