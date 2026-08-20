# Strict terminology example guide

> One of eight in the [example IG catalog](../README.md). Verified by `make verify-igs`.

**The story: whose code is the concept's code.** Generation codes every
published concept by its DHIS2 UID, because a UID is unique, stable, and always
a valid FHIR code. DHIS2 codes are none of those things by default - they are
frequently absent, frequently carry spaces, and are only unique if somebody kept
them so. `[generate] concept_code_source = "code"` flips it, and this guide is
what the far side looks like.

The whole trade is one line of the vaccine vocabulary:

| | Concept codes |
| --- | --- |
| Every other guide here (`concept_code_source = "id"`) | `OptVacBCG01`, `OptVacMes01`, `OptVacPlo01`, `OptVacDPT01`, `OptVacHpB01` |
| This guide (`concept_code_source = "code"`) | `BCG`, `MEASLES`, `POLIO`, `DPT`, `HEPB` |

What you gain is a code a human reads and another system may already speak. What
you give up is DHIS2's guarantee: the id side is unique and stable by
construction, the code side is whatever the instance's maintainers typed, and
renaming a code in DHIS2 silently renames a published concept. Move to codes
when the instance's codes are already the identifiers your partners use, not
because they read better.

**Measure before you switch.** `d2w fhir validate --code-source code` grades the
code findings as the errors they would become, so the report is exactly what the
switch costs on that instance today:

```bash
uv run --project ../../../.. d2w fhir validate --code-source code --no-fail
```

On the seeded instance, five of the twelve option sets fail that bar. `MNCH
ARVs` has thirteen options coded `TDF/3TC/NVP - 1` and the like; `MNCH IPT` has
four coded `IPT 1` through `On CTX`; one option is coded `Postive √`. Those five
are excluded from this guide's selection rather than fixed, because the fix
belongs in DHIS2.

## The selection

| Table | Value | Why |
| --- | --- | --- |
| `[generate] concept_code_source` | `"code"` | The one dial this guide exists for |
| `[generate.option_sets]` | `pC3N9N77UmT`, `udkr3ihaeD3`, `x31y45jvIQL`, `OGmE3wUMEzu`, `kzgQRhOCadd`, `XdI8KRJiRoZ`, `OsVaccType1` | The seven option sets on this instance whose every option carries a valid, unique FHIR code. The other five would refuse the run under `concept_code_source = "code"` |
| `[generate.categories]` | `yY2bQYqNt0o` Project, `Qzh0MSUx4RM` Stock discarded | Category options are coded from the same source; these two axes have clean codes, and the instance's other two do not |
| `[generate.data_sets]` | `TuL8IOPzpHh` EPI Stock | The catalog minimum |
| `[generate.event_programs]` | `EVTsupVis01` Supervision visit | Likewise |
| `[generate.tracker_programs]` | `PrAncCare01` ANC follow-up | Likewise. Child Programme is not selected here: its coded questions would pull the five unusable option sets in through the form closure and the run would refuse |
| `[generate.organisation_units]` | root `PMa2VCrupOd` Kambia, `max_level = 4` | One district: seven chiefdoms and sixty-two facilities |
| `[serve] strict_codes` | `true` | The serving half of the same posture: `d2w fhir serve` refuses an answer outside its option list rather than warning about it |

Organisation units are the one surface this dial does not reach: their concepts
are coded by UID whichever source is configured, because an organisation-unit
code list is generated identity rather than borrowed identity.

## What the compiled guide shows

Five Questionnaires with one example response each, and fourteen terminology
resources - seven CodeSystem/ValueSet pairs whose concept codes are DHIS2 codes.
Each pair has a ConceptMap beside it, and the concept property flips with the
source: every other guide's concepts are coded by UID and carry a `dhis2-code`
property holding the DHIS2 code, and here they are coded by code and carry a
`dhis2-id` property holding the UID. Whichever way round, both facts are on the
concept and nothing about where it came from is lost. 140 registry resources for
Kambia's seventy organisation units.

SUSHI compiles the FSH into 86 resources.

## Regenerate and compile it

```bash
export DHIS2_PROFILE=local_basic
cd examples/fhir/igs/terminology-strict

uv run --project ../../../.. d2w fhir generate
make setup      # the SUSHI + IG publisher docker image, once per machine
make sushi
```
