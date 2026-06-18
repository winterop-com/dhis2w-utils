"""DHIS2 calendar enum in a light module so CLI imports avoid the heavy system accessors + OAS tree."""

from __future__ import annotations

from enum import StrEnum


class DhisCalendar(StrEnum):
    """Canonical DHIS2 calendar names (the values DHIS2 accepts on `keyCalendar`).

    Matches the `@Component` `name()` of every calendar implementation under
    `org.hisp.dhis.calendar.impl` on `dhis2/dhis2w-core` 2.42 — `iso8601` is
    the server default. Pass any of these to `SystemModule.set_calendar()`.
    """

    COPTIC = "coptic"
    ETHIOPIAN = "ethiopian"
    GREGORIAN = "gregorian"
    ISLAMIC = "islamic"
    ISO8601 = "iso8601"
    JULIAN = "julian"
    NEPALI = "nepali"
    PERSIAN = "persian"
    THAI = "thai"
