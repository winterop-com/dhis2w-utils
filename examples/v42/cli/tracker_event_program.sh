#!/usr/bin/env bash
# Event-only program workflow — standalone events with no enrollment.
#
# WITHOUT_REGISTRATION programs (a.k.a. "event programs") collect one-off
# data without a tracked entity: community surveys, case-investigation
# forms, outbreak line-listings, supervision visits.
#
# The same `event create` verb handles both program kinds — omit
# `--enrollment` for event programs. The payload becomes a standalone
# `{events: [...]}` bundle with only program + stage + orgUnit set on
# the event (no `enrollment`, no `trackedEntity`).
#
# The seed ships a minimal supervision-visit event program the seed
# builder creates programmatically (infra/scripts/seed/event_program.py).
set -euo pipefail

# Seeded supervision-visit event program — fixed UIDs so scripts can
# reference them across rebuilds.
EVENT_PROGRAM=EVTsupVis01
EVENT_STAGE=EVTsupVS001
DE_BCG=s46m5MS0hxu
DE_MEASLES=YtbsuPPo010

# The seeded event program is assigned to the Sierra Leone root OU.
# For your own event programs, widen the `organisationUnits` list or
# pick any OU the program is explicitly assigned to.
OU_FACILITY=ImspTQPwCqd

# --- Log one event against the event program -------------------------------
# No --enrollment, no --te — just program + stage + where + when + values.

d2w data tracker event create \
    --program "$EVENT_PROGRAM" \
    --stage "$EVENT_STAGE" \
    --at "$OU_FACILITY" \
    --dv "$DE_BCG=12" \
    --dv "$DE_MEASLES=8" \
    --occurred-at 2025-09-10

# --- List events from the event program -----------------------------------
# Read-back still uses the generic event list verb; filter by program UID.

d2w data tracker event list --program "$EVENT_PROGRAM" --org-unit "$OU_FACILITY"

# Event programs don't have enrollments, so `outstanding` doesn't apply —
# there's no "due stage" semantic without an enrollment to anchor against.
# For completeness reporting on event programs, lean on analytics events
# queries (`d2w analytics events ...`) scoped to the program.
