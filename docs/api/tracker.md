# Tracker reads

Typed instance models returned by `/api/tracker/*` reads: `TrackerTrackedEntity`, `TrackerEnrollment`, `TrackerEvent`, `TrackerRelationship` + nested value types + `EventStatus` / `EnrollmentStatus` StrEnums.

Tracker models are version-scoped because `/api/tracker/*` shapes drift across DHIS2 majors. Import from the version your client is pinned to: `from dhis2w_client.generated.v42.tracker import TrackerBundle, TrackerEvent, ...`. The matching write path lives on `client.tracker` (register / enroll / add_event / outstanding) — see [the tracker plugin architecture](../architecture/tracker.md).

## When to reach for it

- Reading instance data from `/api/tracker/trackedEntities`, `/api/tracker/enrollments`, `/api/tracker/events` with typed results.
- Parsing a raw tracker bundle response (e.g. from a file fixture or a webhook) into typed models before processing.
- Branching on `EventStatus` / `EnrollmentStatus` exhaustively via `match`.

## Worked example — read tracked entities, enrollments, events

`client.tracker.tracked_entities`, `.enrollments`, and `.events` are the read side of the write verbs below. Each GETs the matching `/api/tracker/*` endpoint with the standard query surface: `program`, `org_unit` (one id or a sequence) with `ou_mode`, `status`, `fields`, `filter`, `page` / `page_size`, `updated_after` (an ISO string, a `date`, or a `datetime`), and `extra_params` for the rest (`order`, `enrolledAfter`, `assignedUser`, ...). `events` also scopes by `program_stage`, `enrollment`, and `occurred_after`. `status` filters by enrollment status on the first two reads and by event status on `events`.

The page envelope is returned as parsed JSON: the rows live under `instances` on current majors, and under the resource's own name on older minors, beside the paging fields. Parse a row with the generated model when a typed view is wanted:

```python
from dhis2w_client.generated.v42.tracker import TrackerEvent
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import profile_from_env


async with open_client(profile_from_env()) as client:
    page = await client.tracker.events(
        program="IpHINAT79UW",
        org_unit="ImspTQPwCqd",
        ou_mode="DESCENDANTS",
        occurred_after="2026-01-01",
        page_size=10,
    )
    for row in page.get("instances") or page.get("events") or []:
        event = TrackerEvent.model_validate(row)
        print(f"{event.event}  status={event.status}  ou={event.orgUnit}")
```

## Worked example — register a tracked entity, enroll, add events

The write side lives on `client.tracker`. `register` returns a typed `RegisterResult` carrying the freshly-generated UIDs + the underlying `WebMessageResponse`; `add_event` returns an `EventResult` with the new event UID + its response envelope:

```python
async with open_client(profile_from_env()) as client:
    # 1. Register a new tracked entity + enroll in one call.
    result = await client.tracker.register(
        program="IpHINAT79UW",
        org_unit="DiszpKrYNg8",
        tracked_entity_type="nEenWmSyUEp",
        attributes={"w75KJ2mc4zz": "Jane", "zDhUuAYrxNC": "Doe"},
    )
    print(f"TE={result.tracked_entity}  enrollment={result.enrollment}  status={result.response.status}")

    # 2. Add an event to the new enrollment.
    event = await client.tracker.add_event(
        program="IpHINAT79UW",
        program_stage="A03MvHHogjR",
        enrollment=result.enrollment,
        org_unit="DiszpKrYNg8",
        data_values={"a3kGcGDCuk6": "BCG"},
    )
    print(f"event={event.event}  status={event.response.status}")
```

## Worked example — outstanding follow-up

```python
async with open_client(profile_from_env()) as client:
    # ACTIVE enrollments missing events on a non-repeatable stage —
    # the "what's due" report. `program` is positional; `org_unit`
    # narrows the OU subtree (DESCENDANTS by default).
    rows = await client.tracker.outstanding("IpHINAT79UW", org_unit="ImspTQPwCqd")
    for row in rows:
        print(f"  enrollment={row.enrollment}  TE={row.tracked_entity}  missing={row.missing_stages}")
```

## Related examples

- [`examples/client/tracker_reads.py`](https://github.com/winterop-com/dhis2w-utils/blob/main/examples/client/tracker_reads.py) — page through one program's tracked entities, active enrollments, and recent events with typed row parsing.
- [`examples/client/tracker_lifecycle.py`](https://github.com/winterop-com/dhis2w-utils/blob/main/examples/client/tracker_lifecycle.py) — full register + enroll + add event lifecycle.
- [`examples/client/tracker_clinic_intake.py`](https://github.com/winterop-com/dhis2w-utils/blob/main/examples/client/tracker_clinic_intake.py) — canonical tracker-program intake via `client.tracker.register / add_event / outstanding`.
- [`examples/client/tracker_event_program.py`](https://github.com/winterop-com/dhis2w-utils/blob/main/examples/client/tracker_event_program.py) — WITHOUT_REGISTRATION event-only flow.

::: dhis2w_client.generated.v42.tracker
