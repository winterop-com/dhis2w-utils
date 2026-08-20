# Refused names example guide

> One of eight in the [example IG catalog](../README.md). Verified by `make verify-igs`.

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

| Object | Where the `<` is | Who catches it |
| --- | --- | --- |
| `tU7GixyHhsv` data element `Vitamin A given to < 5y` | Its DHIS2 name, which becomes a question label and a concept display | `d2w fhir validate` - an error on the build path |
| `btOyqprQ9e8` category option `<1y` | Its DHIS2 name and its DHIS2 code | `d2w fhir generate` - the refusal above |
| `lVsbKXoF0zX` data element `Weight/height <70` | Its shortName only; its name is clean | Neither. A shortName lands in resource data, not in the page furniture the publisher injects raw |

Both commands are worth running here, because they answer different questions.
Validate answers "what does this instance cost this guide?" and names every
object, graded:

```console
$ uv run --project ../../../.. d2w fhir validate --no-fail
...
template-hostile-name  dataElements  tU7GixyHhsv  'Vitamin A given to < 5y'   error
```

Generate answers "may I write this guide?" and stops at the first object it
cannot write. On this selection that is the category option, because the
category target runs before the questionnaire target - so the two commands name
different objects, and reading only one of them under-reports the instance.

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

The fix is in DHIS2: rename the object. There is no configuration that makes a
`<` publishable, and none is wanted - a guide that escaped the name would
publish a title the instance does not hold.

Where the name cannot be renamed - upstream demo metadata, a production instance
under change control, a name a ministry actually uses - the answer is to leave
the object out of the selection. That is what every other guide in this catalog
does, and it is why each of them names its option sets and its categories
explicitly rather than taking the instance-wide default.

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
