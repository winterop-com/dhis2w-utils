# Disaggregated aggregate example guide

> One of nine in the [example IG catalog](../README.md). Verified by `make verify-igs`.

**The story: what a data set's category axes become in FHIR.** This is
[`aggregate-minimal`](../aggregate-minimal/)'s selection with the categories
turned on. `diff ../aggregate-minimal/fhir.toml fhir.toml` is the whole lesson:
four lines, and the guide gains a CodeSystem/ValueSet pair per axis, a
per-axis property on every category option combo, and a ConceptMap saying which
DHIS2 combo each published concept came from.

EPI Stock disaggregates two ways at once, which is why it is the data set here:

- **Its own attribute category combination** is `Project` - a data set-level axis
  that qualifies the whole reported form, not one cell of it. It becomes the
  attribute-option-combo pair the Questionnaire references.
- **Three of its twelve data elements** carry `Stock discarded` - an
  element-level axis, so those three questions each become one question per
  combination.

## The selection

| Table | Value | Why |
| --- | --- | --- |
| `[generate.data_sets]` | `TuL8IOPzpHh` EPI Stock | The only data set on the instance with a non-default attribute category combination, and it also carries element-level disaggregation |
| `[generate.event_programs]` | `EVTsupVis01` Supervision visit | The same minimum as `aggregate-minimal`, so the diff stays about the categories |
| `[generate.tracker_programs]` | `PrAncCare01` ANC follow-up | Likewise |
| `[generate.option_sets]` | `OsVaccType1` Vaccine type | Likewise |
| `[generate.categories]` | `yY2bQYqNt0o` Project, `Qzh0MSUx4RM` Stock discarded | Both axes the data set disaggregates over, one at data set level and one at element level. `aggregate-minimal` names the built-in default category here instead, which publishes neither |
| `[generate.examples]` | `per_target = 3` | Three example responses per form instead of one. A disaggregated form is where more than one filled-in example starts to earn its place |
| `[generate.organisation_units]` | root `PMa2VCrupOd` Kambia, `max_level = 4` | The same district as `aggregate-minimal`, so the registry is not part of the diff |

## What the compiled guide shows

The same five Questionnaires as `aggregate-minimal`, now with fifteen example
QuestionnaireResponses rather than five, and two CodeSystem/ValueSet pairs for
the axes with a ConceptMap apiece.

The visible difference is one property, in two places. In `aggregate-minimal`
the category option combo dictionary and the `Project` attribute-option-combo
CodeSystem each declare a single `dhis2-code` property. Here the combo
dictionary also declares `category-Qzh0MSUx4RM` and the attribute-option-combo
CodeSystem also declares `category-yY2bQYqNt0o`, and every concept carries a
`Coding` into the axis it came from. That property is what lets a consumer
decompose a combination back into the options it is made of without knowing
DHIS2.

SUSHI compiles the FSH into 96 resources, ten more than `aggregate-minimal` -
the extra examples and the extra terminology.

## Regenerate and compile it

```bash
export DHIS2_PROFILE=local_basic
cd examples/fhir/igs/aggregate-disaggregated

uv run --project ../../../.. d2w fhir generate
make setup      # the SUSHI + IG publisher docker image, once per machine
make sushi
```
