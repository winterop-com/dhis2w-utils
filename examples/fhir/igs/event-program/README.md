# Event program example guide

> One of nine in the [example IG catalog](../README.md). Verified by `make verify-igs`.

**The story: a program without registration.** No person is created, no
enrollment is opened, and nothing is followed over time - a visit happens
somewhere on some date, and its answers are the whole record. In FHIR that is
one Questionnaire and one QuestionnaireResponse, with no subject to resolve
first, which makes it the simplest of the program forms and the one most
integrations reach for first.

`lxAQ7Zs9VYR` Antenatal care visit is the event program here because it is the
one form on the instance carrying program rules:

| Data element | Value type | What it becomes |
| --- | --- | --- |
| `sWoqcoByYmD` WHOMCH Smoking | `BOOLEAN` | A `boolean` item |
| `Ok9OQpitjQr` WHOMCH Smoking cessation counselling | `BOOLEAN` | A `boolean` item, hidden by a rule unless the answer above is true |
| `vANAXwtLwcT` WHOMCH Hemoglobin value | `NUMBER` | A `decimal` item, warned about by a rule below 9 |

Both rules ride on the Questionnaire as `D2ProgramRule` extensions, carrying the
DHIS2 rule id, its condition (`!#{womanSmoking}`, `#{hemoglobin} < 9`), and its
action (`HIDEFIELD`, `SHOWWARNING`). A form filled in outside DHIS2 can honour
them, and a form that ignores them will be told about it on import - which is
the whole reason they are published rather than left behind.

## The selection

| Table | Value | Why |
| --- | --- | --- |
| `[generate.event_programs]` | `lxAQ7Zs9VYR` Antenatal care visit | One stage, three data elements, and the instance's only two program rules. The other event program, `EVTsupVis01`, is the two-question minimum the rest of the catalog uses |
| `[generate.data_sets]` | `TuL8IOPzpHh` EPI Stock | The catalog minimum; a selection table left absent publishes every data set, and there is no way to select none |
| `[generate.tracker_programs]` | `PrAncCare01` ANC follow-up | Likewise the minimum, so the event form is what stands out |
| `[generate.option_sets]` | `OsVaccType1` Vaccine type | No form here binds an option set; an absent table would publish every one the instance holds, including a name the publisher cannot render |
| `[generate.categories]` | `yY2bQYqNt0o` Project, `Qzh0MSUx4RM` Stock discarded | The two axes the aggregate form disaggregates over |
| `[generate.organisation_units]` | root `bL4ooGhyHRQ` Pujehun, `max_level = 4` | One district: twelve chiefdoms and sixty-six facilities |

## What the compiled guide shows

Five Questionnaires with one example response each. The event program's is the
one to read: it declares form type `event`, takes `Location` as its subject type
rather than a person, labels its date `Visit date`, and carries the two program
rules as extensions. Its example answers all three questions at a facility
inside Pujehun. Beside it, 158 registry resources - seventy-nine organisation
units as an Organization and a Location each - and three assignment Lists saying
which of them each form may be reported at.

SUSHI compiles the FSH into 86 resources.

## Regenerate and compile it

```bash
export DHIS2_PROFILE=local_basic
cd examples/fhir/igs/event-program

uv run --project ../../../.. d2w fhir generate
make setup      # the SUSHI + IG publisher docker image, once per machine
make sushi
```
