# Tracker schema

The authoring flip side of `d2w tracker register / enroll / add-event`. DHIS2's tracker writes need a *schema* on the instance: the `TrackedEntityType` that names the kind of subject, and the `TrackedEntityAttribute`s that describe the fields captured per enrolled TEI. Two accessors cover the leaf half of tracker-schema CRUD:

| Accessor | API path | Purpose |
| --- | --- | --- |
| `client.tracked_entity_attributes` | `/api/trackedEntityAttributes` | Atomic fields on a TEI (National ID, Given Name, DOB, …). CRUD + rename + common toggles (`unique`, `generated`, `confidential`, `inherit`, `pattern`). |
| `client.tracked_entity_types` | `/api/trackedEntityTypes` | The kind of TEI (Person, Case, Animal). CRUD + ordered attribute linkage through `trackedEntityTypeAttributes[]`. |
| `client.programs` | `/api/programs` | Tracker container. Binds a `TrackedEntityType`, a set of TEAs on the enrollment form, a `CategoryCombo`, and the OUs that can capture. CRUD + `add_attribute` / `remove_attribute` for PTEA linkage + `add_organisation_unit` / `remove_organisation_unit` for OU scope. |
| `client.program_stages` | `/api/programStages` | Inner tracker-schema layer. Each stage owns an ordered `programStageDataElements[]` list (a join table with `compulsory` / `displayInReports` / `allowFutureDate` flags). CRUD + `add_element` / `remove_element` / `reorder`. |

## Scope

This page covers the full tracker-schema authoring chain: leaf resources (`TrackedEntityAttribute` + `TrackedEntityType`), the middle layer (`Program` + `programTrackedEntityAttributes[]`), and the inner layer (`ProgramStage` + `programStageDataElements[]`). Optional `ProgramStageSection` grouping (rarely used in the field) is still unauthored — reach for `metadata patch` if you need it.

## TETA join table

Wiring a TEA onto a TET isn't a simple ref list — the link is a `trackedEntityTypeAttributes[]` entry that carries `mandatory`, `searchable`, and `displayInList` flags. The accessor's `add_attribute` / `remove_attribute` helpers round-trip the full TET, mutate the list, and PUT it back so those flags travel without a dedicated endpoint:

```python
async with Dhis2Client(...) as client:
    national_id = await client.tracked_entity_attributes.create(
        name="National ID",
        short_name="NatID",
        unique=True,
        generated=True,
        pattern="RANDOM(#######)",
    )
    person = await client.tracked_entity_types.create(
        name="Person",
        short_name="Person",
        allow_audit_log=True,
        feature_type="NONE",
    )
    await client.tracked_entity_types.add_attribute(
        person.id,
        national_id.id,
        mandatory=True,
        searchable=True,
    )
```

## Self-ref stripping

DHIS2's `/api/trackedEntityTypes/{uid}` read embeds `trackedEntityTypeAttributes[].trackedEntityType = {id: <parent>}` even though that field is the inverse side the importer rejects on PUT. The accessor strips it automatically before every update, mirroring the DataSet + DataSetElement workaround (BUGS tracker parity — same shape as `_strip_self_ref_from_dse`).

## `unique` + `generated` + `pattern`

DHIS2 supports auto-generated attribute values for registration:

- `unique=True` makes the value unique across the instance (National ID, passport number).
- `generated=True` + `pattern` together mean DHIS2 auto-fills the value when a new TEI is registered.
- Common patterns: `"RANDOM(#######)"` for a 7-digit random suffix, `"#(ORGUNIT)(RANDOM)"` to prefix the TEI's OU.

## No `*Spec` builder

Same call as every other authoring accessor — keyword args. Continues the spec-audit data point.

## CLI

```bash
# TrackedEntityAttribute
d2w metadata tracked-entity-attributes create \
    --name "National ID" --short-name NatID --value-type TEXT \
    --unique --generated --pattern "RANDOM(#######)"

# TrackedEntityType + attribute linkage
d2w metadata tracked-entity-types create \
    --name Person --short-name Person --allow-audit-log --feature-type NONE
d2w metadata tracked-entity-types add-attribute <TET_UID> <TEA_UID> --mandatory --searchable
```

Every `list` has an `ls` alias; every destructive verb accepts `--yes` / `-y`.

## MCP

12 tools: `metadata_tracked_entity_attribute_*` (list / get / create / rename / delete), `metadata_tracked_entity_type_*` (list / get / create / rename / add-attribute / remove-attribute / delete).

## Using them with tracker writes

The point of authoring these here is to make the tracker-write plugin usable end-to-end from CLI alone:

```bash
# 1. author the schema
d2w metadata tracked-entity-types create --name Person --short-name Person ...
# 2. use it
d2w tracker register --type <TET_UID> --ou <OU_UID> ...
```

See the [tracker plugin](../architecture/tracker.md) for the write-side reference.

## Program authoring

A `Program` binds everything together. Two flavours: `WITH_REGISTRATION` (tracker — requires a TET, enrolls individual TEIs) and `WITHOUT_REGISTRATION` (event program — captures anonymous events directly).

```python
async with Dhis2Client(...) as client:
    program = await client.programs.create(
        name="Antenatal care",
        short_name="ANC",
        program_type="WITH_REGISTRATION",
        tracked_entity_type_uid=person.id,
        display_incident_date=True,
        only_enroll_once=True,
    )
    await client.programs.add_attribute(
        program.id,
        national_id.id,
        mandatory=True,
        searchable=True,
        sort_order=1,
    )
    await client.programs.add_organisation_unit(program.id, root_ou_uid)
```

### PTEA join table + `mergeMode=REPLACE` quirk

`programTrackedEntityAttributes[]` is a nested join table (DHIS2's wire name is `trackedEntityAttribute` on the entry, not `attribute`). DHIS2 v42's `PUT /api/programs/{uid}` treats nested-list updates **additively by default** — items omitted from the payload are NOT removed. The accessor always passes `?mergeMode=REPLACE` on PUT so `remove_attribute` behaves symmetrically.

### OU scoping

`add_organisation_unit` / `remove_organisation_unit` use DHIS2's per-item shortcut (`POST/DELETE /api/programs/{program}/organisationUnits/{ou}`) — avoids the round-trip PUT entirely.

::: dhis2w_client.v42.tracked_entity_attributes

::: dhis2w_client.v42.tracked_entity_types

::: dhis2w_client.v42.programs

## ProgramStage authoring

Each Program owns a stage sequence (ANC 1st visit, ANC 2nd visit, …). Each stage owns an ordered `programStageDataElements[]` list — a join table with `compulsory`, `displayInReports`, `allowFutureDate`, `allowProvidedElsewhere`, `renderOptionsAsRadio`, `sortOrder` per entry.

```python
stage = await client.program_stages.create(
    name="ANC 1st visit",
    program_uid=program.id,
    sort_order=1,
    repeatable=False,
    min_days_from_start=0,
    standard_interval=30,
)
await client.program_stages.add_element(
    stage.id,
    weight_de.id,
    compulsory=True,
    sort_order=0,
)
await client.program_stages.reorder(stage.id, [second_de.id, weight_de.id])
```

### PSDE ordering helpers

- `add_element(stage_uid, de_uid, compulsory=..., sort_order=...)` — appends a new PSDE entry with typed flags.
- `remove_element(stage_uid, de_uid)` — drops the PSDE entry; other flags on the remaining entries are preserved.
- `reorder(stage_uid, [de_uids])` — replaces the ordered list; PSDE flags are preserved for DEs that stay in the list and `sortOrder` is rewritten to match the new position.

### `mergeMode=REPLACE` quirk

DHIS2 v42's `PUT /api/programStages/{uid}` treats nested-list updates additively by default (same quirk as Programs). The accessor always passes `?mergeMode=REPLACE` on PUT so `remove_element` actually removes the PSDE entry instead of silently retaining it.

### PSDE self-ref strip

The generated PSDE entry carries `programStage = {id: <parent>}` on reads, which DHIS2's importer rejects on PUT (inverse side). Stripped automatically before every update — mirrors DataSet+DSE, TET+TETA, Program+PTEA.

::: dhis2w_client.v42.program_stages
