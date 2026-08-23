# Mixed facility example guide

> One of nine in the [example IG catalog](../README.md). Verified by `make verify-igs`.

**The story: one of every capture kind at once.** This is the flagship - the
guide a real facility would publish if it reported everything it does through
one endpoint. Every other guide in the catalog is a slice of this one.

DHIS2's five capture kinds all appear, in six Questionnaires:

| Kind | Form | What it captures |
| --- | --- | --- |
| `aggregate` | `TuL8IOPzpHh` EPI Stock | A month's numbers for a data set at one facility, on a non-default attribute category combination |
| `event` | `lxAQ7Zs9VYR` Antenatal care visit | One visit, no person followed, two program rules riding on the form |
| `tracker` | `IpHINAT79UW` registration | A child registered and enrolled, both DHIS2 UIDs minted by the caller |
| `tracker-event` | `A03MvHHogjR` Birth, `ZzYYXq4fJie` Baby Postnatal | Two visits on that enrollment, twenty-two questions, eleven of them coded |
| `tracked-entity` | `nEenWmSyUEp` Person | A person created and enrolled in nothing |

The tracked-entity form is not selected by hand:
`[generate.tracked_entity_forms]` defaults to the types the selected tracker
programs register, so choosing Child Programme is what puts it there.

## The selection

| Table | Value | Why |
| --- | --- | --- |
| `[generate.data_sets]` | `TuL8IOPzpHh` EPI Stock | Twelve data elements, three of them disaggregated, on a `Project` attribute category combination - the aggregate form with the most to say |
| `[generate.event_programs]` | `lxAQ7Zs9VYR` Antenatal care visit | The instance's only form carrying program rules |
| `[generate.tracker_programs]` | `IpHINAT79UW` Child Programme | Two stages, four tracked entity attributes, eleven coded questions - the richest tracker |
| `[generate.option_sets]` | `OsVaccType1` Vaccine type | Only the vocabulary no form reaches; the eleven the coded questions bind arrive through the form closure |
| `[generate.categories]` | `yY2bQYqNt0o` Project, `Qzh0MSUx4RM` Stock discarded | Both axes the aggregate form disaggregates over, so the combos decompose |
| `[generate.examples]` | `per_target = 2` | Two example responses per form. Enough that a reader sees the shape rather than one specimen, and small enough to stay readable |
| `[generate.organisation_units]` | root `qhqAxPSTUXp` Koinadugu, `max_level = 4` | One district: eleven chiefdoms and seventy facilities. The same district `examples/fhir/client/_fixture.py` scopes its own project to |

## What the compiled guide shows

Six Questionnaires and twelve example QuestionnaireResponses. Twenty-two
terminology resources across eleven option sets, four category resources across
two axes, the `Project` attribute-option-combo pair, and fourteen ConceptMaps
tying every published concept back to the DHIS2 object it came from. 164 registry
resources for Koinadugu's eighty-two organisation units, and three assignment
Lists.

This is the guide to serve if you want to see the whole capture surface at once.
After the generate and the compile below, and with the local DHIS2 stack on 8080:

```bash
uv run --project ../../../.. d2w fhir serve --port 8090
```

SUSHI compiles the FSH into 94 resources.

## Regenerate and compile it

```bash
export DHIS2_PROFILE=local_basic
cd examples/fhir/igs/facility-mixed

uv run --project ../../../.. d2w fhir generate
make setup      # the SUSHI + IG publisher docker image, once per machine
make sushi
```
