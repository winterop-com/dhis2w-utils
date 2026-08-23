# Patient summary example guide

> One of nine in the [example IG catalog](../README.md). Verified by `make verify-igs`.

**The story: what a DHIS2 tracker instance can honestly say about one person.** Every
other guide here is about what a form looks like in FHIR. This one is about the
document a clinician asks for - an
[International Patient Summary](https://hl7.org/fhir/uv/ips/STU2/) - and about the
two things nobody but the instance's own operator can state.

DHIS2 has no name field and no sex field, and it marks no data element as an
immunisation. So a patient summary built from a DHIS2 instance is exactly as good as
what somebody wrote down, and this guide writes both halves down and serves the
result. [The IPS design paper](../../../../docs/fhir/design/ips.md) is the argument
in full.

## The two nominations, and the dial

| Table | Value | What it decides |
| --- | --- | --- |
| `[ips] enabled` | `true` | Whether `$summary` is answered at all. False by default: a clinical document about a person is a posture a deployment states rather than one it inherits, and a project that states nothing is refused by the key's own name |
| `[ips.identity] name` | `w75KJ2mc4zz` First name | Which attribute is published as `Patient.name[0].text` |
| `[ips.identity] sex` | `cejWyOfXge6` Gender | Which attribute the gender map reads |
| `[ips.identity.administrative_gender]` | `Female = "female"`, `Male = "male"` | What this instance's two sex values mean in the four words `Patient.gender` is bound to. It is a map rather than a rename because the binding is required |
| `[ips.sections.immunizations] program_stages` | `A03MvHHogjR` Birth, `ZzYYXq4fJie` Baby Postnatal | Which stages' events record doses |
| `[ips.sections.immunizations] dose_data_elements` | The six MCH dose elements | Which values inside those stages are doses |

**The data element is the vaccine and the value is the dose.** Child Programme records
`MCH BCG dose`, `MCH OPV dose`, `MCH Measles dose`, `MCH Penta dose`,
`MCH Yellow fever dose`, and `MCH DPT dose` - one element per vaccine, the value
saying either that the dose was given (a boolean) or which dose of the series it was
(an option code). That is the shape a DHIS2 immunisation form has, and the mapping
states it rather than inferring it.

`[serve.tracked_entities]` is absent, because the register and the record are both on
by default and a summary is a projection of the two.

## The rest of the selection

| Table | Value | Why |
| --- | --- | --- |
| `[generate.tracker_programs]` | `IpHINAT79UW` Child Programme | The instance's immunisation tracker: two stages, six dose elements, four tracked entity attributes |
| `[generate.data_sets]` | `TuL8IOPzpHh` EPI Stock | The catalog minimum; a selection table left absent publishes every data set, and there is no way to select none |
| `[generate.event_programs]` | `EVTsupVis01` Supervision visit | Likewise |
| `[generate.option_sets]` | `OsVaccType1` Vaccine type | Only the one vocabulary no form reaches. The option sets the dose questions bind are added by the form closure |
| `[generate.categories]` | `GLevLNI9wkl` default | No category axis, so the summary is what the guide is about |
| `[generate.organisation_units]` | root `qhqAxPSTUXp` Koinadugu, `max_level = 4` | One district: eleven chiefdoms and seventy facilities, which is where the seeded children are enrolled |

## What the generated guide publishes

Two ConceptMaps that no other guide in this catalog carries, and they are the point:

- **`D2Sex_CM`** takes each value of the nominated sex attribute onto an R4
  `administrative-gender` code. It is the first map this project publishes onto a
  vocabulary that is not DHIS2's own.
- **`D2Section_CM`** takes each nominated program stage and data element onto the
  LOINC code of the IPS section it feeds - `11369-6`, Immunizations. `fhir.toml` is
  the input and the map is the published output, so a consumer can audit which
  recorded values a served summary carries without ever seeing this project's config.

Everything else is the ordinary tracker guide: six Questionnaires with one example
response each, twenty-four terminology resources - twelve CodeSystem/ValueSet pairs,
one per option set the coded questions bind - and 164 registry resources for
Koinadugu's eighty-two organisation units.

SUSHI compiles the FSH into 88 resources.

## What the served summary answers

```bash
export DHIS2_PROFILE=local_basic
cd examples/fhir/igs/patient-summary

uv run --project ../../../.. d2w fhir generate
uv run --project ../../../.. d2w fhir serve --live --port 8141
```

Then, for a child the instance holds:

```bash
curl "http://127.0.0.1:8141/Patient/{uid}/\$summary"
curl "http://127.0.0.1:8141/Patient/\$summary?identifier={value}"
```

Both answer the same document: a FHIR `document` Bundle whose first entry is a
`Composition` typed with the IPS's own LOINC code `60591-5`.

| Section | LOINC | What it carries |
| --- | --- | --- |
| Problems | `11450-4` | An empty reason. This project maps no data element into it |
| Allergies and Intolerances | `48765-2` | An empty reason. Allergy capture is rare in DHIS2 tracker programs, and a mis-mapped allergy is the most dangerous wrong answer a summary can carry |
| Medication Summary | `10160-0` | An empty reason |
| Immunizations | `11369-6` | One `Immunization` per dose the person's own events hold |

**A recorded `false` is not a dose.** A child whose `MCH BCG dose` is `false` gets no
BCG entry: DHIS2 says the vaccine was not given and states no reason, and R4 requires
a reason on a dose that was not given.

**The document says what it is and is not.** `Composition.text` carries one sentence
naming the sections that carry no mapping and stating that the document is a valid IPS
Bundle which does not claim the Creator (IPS) actor's obligations - the IG says in as
many words that those are two separate claims. The same sentence rides the response as
the `X-DHIS2W-Summary-Caveat` header, for whoever reads responses rather than
resources.

## Regenerate and compile it

```bash
export DHIS2_PROFILE=local_basic
cd examples/fhir/igs/patient-summary

uv run --project ../../../.. d2w fhir generate
make setup      # the SUSHI + IG publisher docker image, once per machine
make sushi
```
