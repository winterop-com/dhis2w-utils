# Tracker registration example guide

> One of nine in the [example IG catalog](../README.md). Verified by `make verify-igs`.

**The story: a person, an enrollment, and the visits that follow.** A tracker
program is the one DHIS2 form kind whose answers are about somebody rather than
about a place, and it publishes as three kinds of Questionnaire rather than one:

| Form | DHIS2 object | What answering it does |
| --- | --- | --- |
| `Questionnaire-IpHINAT79UW` registration | The program itself | Creates the tracked entity, sets its attributes, and opens an enrollment - both UIDs minted by the caller |
| `Questionnaire-A03MvHHogjR` Birth | Program stage | One event on an existing enrollment: eight questions, three of them coded |
| `Questionnaire-ZzYYXq4fJie` Baby Postnatal | Program stage | One event on the same enrollment: fourteen questions, nine of them coded |
| `Questionnaire-nEenWmSyUEp` | Tracked entity type Person | Creates the person and enrols them in nothing - the same attributes, no program |

The person-only form is not selected by hand. `[generate.tracked_entity_forms]`
defaults to the tracked entity types the selected tracker programs register, so
choosing Child Programme is what puts a `Person` form in the guide.

## The selection

| Table | Value | Why |
| --- | --- | --- |
| `[generate.tracker_programs]` | `IpHINAT79UW` Child Programme | Two stages, four tracked entity attributes, twenty-two stage questions, eleven of them bound to option sets - the richest tracker on the instance |
| `[generate.data_sets]` | `TuL8IOPzpHh` EPI Stock | The catalog minimum; a selection table left absent publishes every data set, and there is no way to select none |
| `[generate.event_programs]` | `EVTsupVis01` Supervision visit | Likewise the minimum, so the tracker forms are what stand out |
| `[generate.option_sets]` | `OsVaccType1` Vaccine type | Only the one vocabulary no form reaches. The eleven option sets Child Programme's coded questions bind - the MNCH sets and Gender - are added by the form closure, so the table does not have to name them |
| `[generate.categories]` | `yY2bQYqNt0o` Project, `Qzh0MSUx4RM` Stock discarded | The two axes the aggregate form disaggregates over |
| `[generate.organisation_units]` | root `qhqAxPSTUXp` Koinadugu, `max_level = 4` | One district: eleven chiefdoms and seventy facilities |

## What the compiled guide shows

Six Questionnaires with one example response each. Twenty-two terminology
resources - eleven CodeSystem/ValueSet pairs, one per option set the coded
questions bind - and fourteen ConceptMaps saying which DHIS2 object each
published concept came from. 164 registry resources for Koinadugu's
eighty-two organisation units.

The registration example is the one worth opening. It mints two DHIS2 UIDs
client-side, one for the tracked entity and one for the enrollment, and carries
both back on the response - so a caller that never reaches DHIS2 still knows
what it created, and a retry names the same objects rather than making a second
person. `examples/fhir/client/build_registration_response.py` builds that same
shape in typed Python.

SUSHI compiles the FSH into 88 resources.

## Regenerate and compile it

```bash
export DHIS2_PROFILE=local_basic
cd examples/fhir/igs/tracker-registration

uv run --project ../../../.. d2w fhir generate
make setup      # the SUSHI + IG publisher docker image, once per machine
make sushi
```
