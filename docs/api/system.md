# System module

`Me`, `SystemInfo`, `DhisCalendar`, and the small `SystemModule` accessor bound to `Dhis2Client.system`.

::: dhis2w_client.v42.system

## System cache

`Dhis2Client` ships a per-client TTL-bounded cache for system-level reads.

::: dhis2w_client.v42.system_cache

## Calendar

DHIS2 ships nine canonical calendars — the names are the values DHIS2 accepts on the `keyCalendar` system setting. `DhisCalendar` enumerates them; `iso8601` is the server default.

```python
async with Dhis2Client(...) as client:
    name = await client.system.calendar()  # "iso8601" by default
    await client.system.set_calendar(DhisCalendar.ETHIOPIAN)
```

The CLI mirrors this:

```bash
d2w system calendar                    # print current value
d2w system calendar ethiopian          # set new value, with interactive y/N confirmation
d2w system calendar ethiopian --yes    # skip the prompt (CI / scripts)
```

WARNING: only change the calendar when it is genuinely required. Switching `keyCalendar` after data collection has started can leave existing periods unreadable and break analytics. The CLI prints the current value, the new value, and a warning, then prompts `Change calendar? [y/N]` with `N` as the default. Calling `d2w system calendar <same-value>` is a no-op and does not prompt. Library callers do not get this confirmation — `client.system.set_calendar()` writes immediately.

NOTE: a local single-replica `infra/` stack (DHIS2 `2.42.4`) round-trips the write end-to-end for all nine values. On the shared `play.im.dhis2.org/dev-2-42` instance the same call returns `200 OK` with a confirming message but the value does not persist on the next read — a deployment-topology issue, not a `dhis2w-core` regression. See `BUGS.md` entry 32.
