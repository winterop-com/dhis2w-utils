# District registry example guide

> One of eight in the [example IG catalog](../README.md). Verified by `make verify-igs`.

**The story: where the forms are reported.** Every guide publishes an
organisation-unit registry, because a form nobody can say where it was filled in
is not a form. This one is about the registry itself: what an organisation unit
becomes in FHIR, what happens to its boundary, and what turning the
organisation-unit code list on adds.

Each DHIS2 organisation unit becomes **two** resources:

- an **Organization**, which is the administrative body - who runs the facility,
  what it is called, what identifiers it answers to;
- a **Location**, which is the place - where it is, what shape it has, and what
  it is part of.

They are separate in FHIR because they are separate in fact: a health authority
can move, merge, or be renamed without the building changing, and a building
outlives whoever runs it. DHIS2 holds one row for both, so the registry
publishes both and links them.

## Boundaries

Bonthe is the district here because it is the smallest on the instance and
carries the fullest geometry. Forty-two of its sixty-eight units have a
boundary, and each of those Locations carries a `position` plus the boundary
itself, embedded losslessly as GeoJSON in the `location-boundary-geojson`
extension:

| Level | Units | With geometry | GeoJSON type |
| --- | --- | --- | --- |
| 2 - district | 1 | 1 | `MultiPolygon` |
| 3 - chiefdom | 12 | 12 | 6 `MultiPolygon`, 6 `Polygon` |
| 4 - facility | 55 | 29 | `Point` |

The twenty-six facilities with no geometry are published all the same, with a
Location that has no position. A DHIS2 instance that has never captured
coordinates for a clinic is the normal case, not an error.

## The selection

| Table | Value | Why |
| --- | --- | --- |
| `[generate.organisation_units]` | root `lc3eMKXaEfw` Bonthe, `max_level = 4`, `terminology = true` | The smallest district on the instance, taken to the facilities. `terminology = true` is what this guide turns on and the others leave off |
| `[generate.data_sets]` | `TuL8IOPzpHh` EPI Stock | The catalog minimum; a selection table left absent publishes every data set, and there is no way to select none |
| `[generate.event_programs]` | `EVTsupVis01` Supervision visit | Likewise |
| `[generate.tracker_programs]` | `PrAncCare01` ANC follow-up | Likewise |
| `[generate.option_sets]` | `OsVaccType1` Vaccine type | The one vocabulary no form reaches; an absent table would publish every option set, including a name the publisher cannot render |
| `[generate.categories]` | `GLevLNI9wkl` default | No category axis, so the registry is what the guide is about |

## What the compiled guide shows

136 registry resources - sixty-eight organisation units, each an Organization
and a Location - and the two the `terminology = true` dial adds:
`CodeSystem-d2-ou-cs` and `ValueSet-d2-ou-vs`, the organisation-unit code list,
each concept carrying the unit's level as a property. A consumer binding a
question's answer to that ValueSet gets a picker over exactly the units this
guide covers.

Three assignment Lists say which units each form may be reported at, drawn from
DHIS2's own assignment and narrowed to the published tree. The registry page
`registry.md` narrates the hierarchy, and Bonthe's own `partOf` is omitted with a
note, because its parent - Sierra Leone - is outside the selection. That note is
the registry saying where it was cut, rather than quietly pointing at a resource
the guide does not hold.

SUSHI compiles the FSH into 88 resources.

## Regenerate and compile it

```bash
export DHIS2_PROFILE=local_basic
cd examples/fhir/igs/registry-district

uv run --project ../../../.. d2w fhir generate
make setup      # the SUSHI + IG publisher docker image, once per machine
make sushi
```
