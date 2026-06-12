# Tracker plugin

`dhis2w-core/v42/plugins/tracker/` wraps the DHIS2 tracker API at `/api/tracker/*`. This covers the full case-management surface — tracked entities, enrollments, events (both event programs and tracker programs), relationships, and bulk import.

## Typed returns

Read services return typed pydantic models from `dhis2w_client.generated.v42.tracker` (tracker shapes drift between DHIS2 majors, so models are version-scoped):

| Service | Returns |
|---|---|
| `list_tracked_entities` | `list[TrackerTrackedEntity]` |
| `get_tracked_entity` | `TrackerTrackedEntity` |
| `list_enrollments` | `list[TrackerEnrollment]` |
| `list_events` | `list[TrackerEvent]` |
| `list_relationships` | `list[TrackerRelationship]` |
| `push_tracker` | `WebMessageResponse` |

Status fields come back as `StrEnum` values (`EnrollmentStatus`, `EventStatus`) so agents/scripts can match them without stringly-typed drift. See [Typed schemas](typed-schemas.md) for the full model list and the TrackedEntityType metadata ↔ instance relationship.

## What it exposes

| Operation | CLI | MCP tool |
| --- | --- | --- |
| List TrackedEntityTypes | `d2w data tracker type` | `data_tracker_type_list` |
| List tracked entities | `d2w data tracker list <TET_NAME_OR_UID>` | `data_tracker_list` |
| Get one tracked entity | `d2w data tracker get <uid>` | `data_tracker_get` |
| List enrollments | `d2w data tracker enrollment list` | `data_tracker_enrollment_list` |
| List events | `d2w data tracker event list` | `data_tracker_event_list` |
| List relationships | `d2w data tracker relationship list` | `data_tracker_relationship_list` |
| Register + enroll | `d2w data tracker register <program>` | `data_tracker_register` |
| Enroll existing TE | `d2w data tracker enrollment create <te> <program>` | `data_tracker_enroll` |
| Add one event | `d2w data tracker event create` | `data_tracker_event_create` |
| Outstanding stages | `d2w data tracker outstanding <program>` | `data_tracker_outstanding` |
| Bulk import | `d2w data tracker push <file>` | `data_tracker_push` |

## Authoring verbs (register / enroll / add event / outstanding)

The authoring surface layers over `POST /api/tracker` — the same endpoint
the bulk push uses — but wraps it in four workflow-shaped verbs that
build the `{trackedEntities, enrollments, events}` bundle for you. Every
verb pre-generates the new UIDs client-side (so DHIS2 uses them instead
of allocating fresh ones) and returns a typed result carrying those
UIDs alongside the `WebMessageResponse`, so the next verb has what it
needs without parsing `bundleReport`.

### Register + enroll in one call (tracker programs)

```bash
d2w data tracker register IpHINAT79UW \
    --ou <facility-uid> \
    --attr w75KJ2mc4zz=Aminata \
    --attr zDhUuAYrxNC=Kamara \
    --enrolled-at 2024-06-01
```

`--tet` defaults to the program's `trackedEntityType`; pass it
explicitly when the program accepts multiple TETs. `--attr <uid>=<value>`
repeats for each TrackedEntityAttribute on the form. The response shows
the newly assigned `tracked_entity` + `enrollment` UIDs.

### Enroll an existing TE

For patients already in the system, skip the TE creation:

```bash
d2w data tracker enrollment create <te-uid> <program-uid> --at <ou-uid>
```

### Add one event (tracker + event programs)

One verb for both program kinds — pass `--enrollment` for tracker
programs, omit it for event programs:

```bash
# Tracker program — event binds to an enrollment
d2w data tracker event create \
    --enrollment <enrollment-uid> \
    --program <program-uid> \
    --stage <stage-uid> \
    --at <ou-uid> \
    --te <te-uid> \
    --dv fClA2Erf6IO=5 \
    --occurred-at 2024-07-15

# Event program — no enrollment, no TE
d2w data tracker event create \
    --program <event-program-uid> \
    --stage <stage-uid> \
    --at <ou-uid> \
    --dv <de-uid>=<value> \
    --occurred-at 2024-09-10
```

### Outstanding — "what's due" for tracker programs

```bash
d2w data tracker outstanding <program-uid> [--ou <uid>]
```

Returns every ACTIVE enrollment on the program that's missing an event
on any **non-repeatable** program stage. Repeatable stages (weekly
checkups, periodic screenings) are deliberately excluded — their "due"
semantic isn't single-valued.

The CLI renders a Rich table; `--json` emits the typed list (each row:
`enrollment`, `tracked_entity`, `org_unit`, `enrolled_at`,
`missing_stages: list[str]`).

### Client-side API

All four verbs are on `Dhis2Client.tracker`:

```python
async with open_client(profile) as client:
    result = await client.tracker.register(
        program="IpHINAT79UW",
        org_unit=ou_uid,
        tracked_entity_type="nEenWmSyUEp",
        attributes={"w75KJ2mc4zz": "Aminata", "zDhUuAYrxNC": "Kamara"},
        enrolled_at="2024-06-01",
        # Optionally attach the first events inline — they'll land in the
        # same /api/tracker POST, linked to the new enrollment:
        events=[
            {
                "program_stage": "A03MvHHogjR",
                "occurred_at": "2024-06-02",
                "data_values": {"fClA2Erf6IO": "5"},
            },
        ],
    )
    print(result.tracked_entity, result.enrollment, result.events)
```

`register` / `enroll` / `add_event` return typed results
(`RegisterResult`, `EnrollResult`, `EventResult`) with the generated UIDs
+ the `WebMessageResponse`. `outstanding` returns `list[OutstandingEnrollment]`.

All date arguments (`enrolled_at`, `occurred_at`) accept ISO strings,
`datetime.date`, or `datetime.datetime` — the accessor normalises them to
DHIS2's ISO-8601 wire format. Type alias: `DateLike = str | date |
datetime`, re-exported from `dhis2w_client.v42.tracker`.

### Why the UIDs are pre-generated client-side

DHIS2's `/api/tracker` will allocate UIDs server-side if you omit them,
but then the caller has to parse `response.bundleReport.typeReportMap` to
figure out what it just created. Pre-generating via
`dhis2w_client.generate_uid()` (which matches DHIS2's UID algorithm bit
for bit) means the UIDs are known before the POST lands. The verbs
return them on the typed result so the next call in the workflow
(`add_event`, `outstanding`, `metadata usage`) has what it needs with
zero parsing of the bundle report.

## Program types matter

DHIS2 has two program kinds:

- **`WITH_REGISTRATION`** (tracker programs) — support tracked entities, enrollments, events, relationships.
- **`WITHOUT_REGISTRATION`** (event programs) — only events; no tracked entities or enrollments.

Every tracker API call requires a program (or at least a tracked-entity-type), and that program must match the call's kind:

- `data_tracker_list` / `data_tracker_enrollment_list` require a tracker program (or skip them for event-only instances).
- `data_tracker_event_list` works for both kinds.
- `data_tracker_push` accepts any mix — each object in the bundle routes to the right service internally.

The plugin doesn't validate this client-side — DHIS2 returns a 400 "Program specified is not a tracker program" if you pass the wrong kind. The service surfaces that error directly; agents and CLI users see the DHIS2 message.

## `<type>` arg — TrackedEntityType by name or UID

`d2w data tracker list` takes the TrackedEntityType as a positional argument.
Pass a human name (case-insensitive; resolved server-side) or a UID directly:

```bash
d2w data tracker type                      # discover configured types first
d2w data tracker list Person               # by name
d2w data tracker list patient              # case-insensitive
d2w data tracker list tet01234567          # by UID
```

## CLI examples

```bash
# Find a tracker program first
d2w --json metadata list programs --fields id,name,programType \
  | jq '.[] | select(.programType=="WITH_REGISTRATION") | .id'

# List tracked entities of type "Person" under a program
d2w data tracker list Person \
  --program IpHINAT79UW \
  --org-unit ImspTQPwCqd \
  --ou-mode DESCENDANTS \
  --page-size 10

# Fetch one tracked entity by UID (type inferred from the entity)
d2w data tracker get te01234567

# List events (works with either program kind)
d2w data tracker event list \
  --program IpHINAT79UW \
  --org-unit ImspTQPwCqd \
  --status COMPLETED \
  --after 2024-01-01

# Bulk import from a JSON bundle
d2w data tracker push bundle.json --strategy CREATE_AND_UPDATE --dry-run
```

## MCP examples

```python
# Discover configured TrackedEntityTypes
await mcp.call_tool("data_tracker_type_list", {})

# List tracked entities of type "Person"
await mcp.call_tool("data_tracker_list", {
    "type": "Person",
    "program": "IpHINAT79UW",
    "org_unit": "ImspTQPwCqd",
    "ou_mode": "DESCENDANTS",
    "page_size": 10,
})

# List events with status filter
await mcp.call_tool("data_tracker_event_list", {
    "program": "IpHINAT79UW",
    "org_unit": "ImspTQPwCqd",
    "status": "COMPLETED",
    "occurred_after": "2024-01-01",
})

# Push a bundle (mix of entities, enrollments, events)
await mcp.call_tool("data_tracker_push", {
    "bundle": {
        "trackedEntities": [{"trackedEntity": "abc", "trackedEntityType": "X", "orgUnit": "Y"}],
        "enrollments": [{"enrollment": "def", "program": "Z", "orgUnit": "Y", "trackedEntity": "abc", ...}],
        "events": [{"event": "ghi", "program": "Z", "programStage": "S", "orgUnit": "Y", ...}],
    },
    "import_strategy": "CREATE_AND_UPDATE",
    "dry_run": True,
})
```

## Filter parameter reference

**`ou_mode`** values:
- `SELECTED` — only this org unit
- `CHILDREN` — immediate children
- `DESCENDANTS` — all descendants (default for most queries)
- `ACCESSIBLE` — user's accessible unit
- `CAPTURE` — user's capture unit
- `ALL` — superuser only

**`status`** values vary by object:
- Enrollments: `ACTIVE`, `COMPLETED`, `CANCELLED`
- Events: `ACTIVE`, `COMPLETED`, `VISITED`, `SCHEDULE`, `OVERDUE`, `SKIPPED`

**`import_strategy`** values: `CREATE`, `UPDATE`, `CREATE_AND_UPDATE` (default), `DELETE`.

**`atomic_mode`** values:
- `ALL` — fail the whole bundle on any object error (default, safer)
- `OBJECT` — import whatever validates, skip invalid ones

## Bundle shape for `push`

```json
{
  "trackedEntities": [ { "trackedEntity": "...", "trackedEntityType": "...", "orgUnit": "...", "attributes": [...], "enrollments": [...] } ],
  "enrollments":    [ { "enrollment": "...", "program": "...", "orgUnit": "...", "trackedEntity": "...", "events": [...] } ],
  "events":         [ { "event": "...", "program": "...", "programStage": "...", "orgUnit": "...", "dataValues": [...] } ],
  "relationships":  [ { "relationship": "...", "relationshipType": "...", "from": {...}, "to": {...} } ]
}
```

Any key can be omitted. Nested enrollments/events inside a tracked entity are allowed — the tracker import pipeline unwraps them.

## Async import

For bundles larger than ~10k objects, use `async_mode=True`. The server returns a job reference immediately; poll `/api/system/tasks/TRACKER_IMPORT_JOB/{taskId}` for progress. A future helper will wrap the poll loop.

## Not yet exposed

- Single-event GET (`/api/tracker/events/{uid}`) — covered by `data_tracker_event_list` + filter for now.
- Single-enrollment GET.
- Ownership transfer endpoints.

Add them to `service.py` when needed.
