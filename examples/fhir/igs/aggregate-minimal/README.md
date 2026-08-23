# Minimal aggregate example guide

> One of nine in the [example IG catalog](../README.md). Verified by `make verify-igs`.

**The story: the smallest complete guide.** Every selection table is set to the
fewest objects the toolchain accepts, the registry covers one district, and no
category axis is published at all. Everything else in the catalog is a diff from
this one - start here, then read
[`aggregate-disaggregated`](../aggregate-disaggregated/), which is this same
selection with the axes turned on.

## The selection

| Table | Value | Why |
| --- | --- | --- |
| `[generate.data_sets]` | `TuL8IOPzpHh` EPI Stock | Twelve data elements, the smaller of the instance's two data sets, and the only one free of names the publisher cannot render |
| `[generate.event_programs]` | `EVTsupVis01` Supervision visit | Two data elements on one stage - the smallest form the instance holds |
| `[generate.tracker_programs]` | `PrAncCare01` ANC follow-up | One stage, three data elements, two tracked entity attributes - the smaller of the two tracker programs |
| `[generate.option_sets]` | `OsVaccType1` Vaccine type | No form here binds an option set, and a table left absent would publish every option set the instance holds - including one whose name aborts the publisher. Five options, every one of them carrying a valid FHIR code |
| `[generate.categories]` | `GLevLNI9wkl` default | The DHIS2 built-in default category alone. This guide publishes the forms and no category axis, which is what makes it the minimum |
| `[generate.organisation_units]` | root `PMa2VCrupOd` Kambia, `max_level = 4` | One district: seven chiefdoms and sixty-two facilities. Every form on this instance is assigned at level 4, so a shallower registry would publish no unit any form reports at |

The last four lines are edited into `fhir.toml` by hand - `d2w fhir init` has
flags for the identity and the three form tables and none for these. A refresh
never writes `fhir.toml`, so they survive `d2w fhir init --refresh`.

## What the compiled guide shows

Five Questionnaires - the data set, the event program, the tracker program's
registration form and its one stage, and the person-only form for the tracked
entity type that program registers - each with one example
QuestionnaireResponse answering it. One CodeSystem/ValueSet pair for the
vocabulary, the data dictionary pairs for the data elements and the category
option combos, three organisation-unit assignment Lists, and 140 registry
resources: seventy organisation units, each an Organization and a Location.

Because no category axis is published, the category option combo dictionary
carries no per-axis property, and the run says so in its notes. That absence is
the point of this guide.

SUSHI compiles the FSH into 86 resources; the registry and the terminology ship
as pre-built JSON beside them and are loaded, not compiled.

## Regenerate and compile it

```bash
export DHIS2_PROFILE=local_basic
cd examples/fhir/igs/aggregate-minimal

uv run --project ../../../.. d2w fhir generate
make setup      # the SUSHI + IG publisher docker image, once per machine
make sushi
```

`make clean` removes everything those two steps wrote. From the repository root,
`make verify-igs` does all of it for all nine guides.
