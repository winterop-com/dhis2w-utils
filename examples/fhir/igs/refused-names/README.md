# Refused names example guide

> One of nine in the [example IG catalog](../README.md). Verified by `make verify-igs`.

**This guide does not build, on purpose.** It is the exhibit: a selection whose
DHIS2 names carry a raw `<`, and a `d2w fhir generate` that refuses to write a
single file because of it. Running it is the point.

```console
$ uv run --project ../../../.. d2w fhir generate
error: category 'EPI/nutrition age' (YNZyaJHiHYq) has category option '<1y'
(btOyqprQ9e8) whose name carries '<'. The IG publisher writes it into pages it
strict-parses after writing, so `make build` aborts in its last pass, once every
resource has already been rendered. Change the name in DHIS2, then run `d2w fhir
validate` for the full report.
$ echo $?
1
```

## What the refusal is standing in for

A DHIS2 name is kept byte-true on the resource it becomes - a Questionnaire's
`title`, a concept's `display` - because a guide that quietly rewrote its
source's names would be lying about the instance. The IG publisher then writes
those names into pages, and re-parses the pages it just wrote, strictly. A `<`
opens a tag. The parse fails.

What makes it worth a refusal rather than a warning is **when** it fails. A `<`
in a name survives every earlier pass, including the publisher's own Checking
Output HTML step, and dies only in the final AI-markdown pass:

```text
Publishing Content Failed: Unable to process page CodeSystem-d2-de-cs.html
...
Caused by: org.hl7.fhir.exceptions.FHIRFormatError: Unable to Parse HTML - ...
        last text = 'Vitamin A given to '
  at org.hl7.fhir.igtools.publisher.AIProcessor.produceMDForResource(...)
```

That is hours in, after every resource has already been rendered, and the
message names a page rather than the object. The gate turns that into two
seconds and the object's own name.

## What is in the selection, and what each half catches

| Object | Where the `<` is | What each command says |
| --- | --- | --- |
| `btOyqprQ9e8` category option `<1y` | Its DHIS2 name and its DHIS2 code | validate: `template-hostile-name` error on the build path. generate: the refusal above, raised by the category target |
| `tU7GixyHhsv` data element `Vitamin A given to < 5y` | Its DHIS2 name, which becomes a question label and a concept display | validate: `template-hostile-name` error on the build path. generate: refused by the questionnaire target, which runs next |
| `lVsbKXoF0zX` data element `Weight/height <70` | Its shortName only; its name is clean | Neither. A shortName lands in resource data, not in the page furniture the publisher injects raw |

**Both offenders are caught by both commands.** That is the parity the gate
keeps, and it runs in both directions: every name validate grades an error on
the build path refuses a generate run, and every name generate refuses is graded
an error on the build path. It holds over every kind of object a selection can
publish - option sets and their options, categories and their category options,
organisation units, data sets, event programs, tracker programs and their
stages, tracked entity types, and the data elements and tracked entity
attributes those forms ask as questions.

The two commands still answer different questions, which is why running both is
worth it. Validate answers "what does this instance cost this guide?" and names
every offender, graded:

```console
$ uv run --project ../../../.. d2w fhir validate --no-fail
...
error  selection  template-hostile-name  categoryOptions  btOyqprQ9e8  <1y
error  selection  template-hostile-name  dataElements     tU7GixyHhsv  Vitamin A given to < 5y
```

Generate answers "may I write this guide?" and stops at the **first** object it
cannot write. On this selection that is the category option, because the
category target runs before the questionnaire target - so generate names one of
the two and validate names both. Deselect `YNZyaJHiHYq` and generate refuses on
`tU7GixyHhsv` instead; it never falls silent.

## The selection

| Table | Value | Why |
| --- | --- | --- |
| `[generate.data_sets]` | `BfMAe6Itzgt` Child Health | The only data set on the instance carrying `<`-named data elements. Thirty-one elements, every one of them on the `Location and age group` category combination |
| `[generate.categories]` | `YNZyaJHiHYq` EPI/nutrition age, `fMZEcRHuamy` Location Fixed/Outreach | The two axes that combination decomposes into. `EPI/nutrition age` holds the `<1y` category option, and selecting it is what makes the refusal fire |
| `[generate.event_programs]` | `EVTsupVis01` Supervision visit | The catalog minimum; a selection table left absent publishes everything of its kind |
| `[generate.tracker_programs]` | `PrAncCare01` ANC follow-up | Likewise |
| `[generate.option_sets]` | `OsVaccType1` Vaccine type | Likewise. Left absent, the run would be refused one step earlier, on option set `Age (<5 - 49) & over` |
| `[generate.organisation_units]` | root `PMa2VCrupOd` Kambia, `max_level = 4` | Beside the point here - the run is refused before the registry is read |

## The fix, and why it is not in this directory

One fix is in DHIS2: rename the object, and the guide keeps repeating its
instance byte for byte. Nothing escapes the name - a guide that escaped it would
publish a title the instance does not hold.

Where the name cannot be renamed - upstream demo metadata, a production instance
under change control, a name a ministry actually uses - there are two answers.
Leave the object out of the selection, which is what every other guide in this
catalog does and why each of them names its option sets and its categories
explicitly rather than taking the instance-wide default. Or publish the name in
the wording it stands for:

```console
$ uv run --project ../../../.. d2w fhir generate --substitute-hostile-names
note: the DHIS2 name '<1y' carries '<', which the IG publisher's build cannot
survive; the guide publishes 'under 1y' and DHIS2 keeps the name it holds
```

That is the answer for an instance whose age bands are all named this way -
`<1y`, `<5`, `Vitamin A given to < 5y` - where renaming them is a change to a
production instance made to satisfy a publisher. DHIS2 is never written to and no
UID moves, so the ConceptMaps still take every published concept back to the
object it came from. The same posture also hyphenates a DHIS2 code carrying a
space, stating the DHIS2 code beside the published one as a `dhis2-code`
concept property; this selection's codes carry none. `[generate]
hostile_names = "substitute"` is the same answer, standing, for one project;
this guide deliberately states neither, so it stays the refusal exhibit. The
whole picture is in [Answer the hostile-name
question](https://winterop-com.github.io/dhis2w-utils/fhir/201-generate/#answer-the-hostile-name-question).

`d2w fhir validate` is the command that tells you which objects those are,
before you have spent anything on a build. It is the CI gate for the same
reason: errors exit 1.

## What `make verify-igs` asserts here

- **validate** must report at least one `template-hostile-name` error on the
  build path. An exhibit that stopped being hostile would be a silent hole.
- **generate** must exit non-zero with a message naming an object whose name
  carries `<`.
- **compile** is skipped: there is no FSH to compile, and that is the point.

## Running it

```bash
export DHIS2_PROFILE=local_basic
cd examples/fhir/igs/refused-names

uv run --project ../../../.. d2w fhir validate --no-fail   # names every offender
uv run --project ../../../.. d2w fhir generate             # refuses, exit 1
```

Related: [Troubleshooting](../../../../docs/fhir/201-troubleshooting.md) carries the
publisher's own message and the fix, and
[Validate the instance](../../../../docs/fhir/201-validate.md) explains the grading.
