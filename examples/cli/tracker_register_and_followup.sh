#!/usr/bin/env bash
# Tracker clinic-intake workflow — register, log events, query outstanding.
#
# This is the canonical tracker authoring flow for a WITH_REGISTRATION
# program (a.k.a. "tracker program"): one person, one enrollment, one or
# more events over time.
#
# Seeded Child Programme UIDs (from the Sierra Leone play42 snapshot):
#   program:           IpHINAT79UW  (Child Programme)
#   tracked-entity:    nEenWmSyUEp  (Person)
#   stages:            A03MvHHogjR  (Birth) + ZzYYXq4fJie  (Baby Postnatal)
#   first-name attr:   w75KJ2mc4zz
#   last-name attr:    zDhUuAYrxNC
set -euo pipefail

PROGRAM=IpHINAT79UW
STAGE_BIRTH=A03MvHHogjR
STAGE_POSTNATAL=ZzYYXq4fJie

# Pick a level-4 facility OU to register against.
OU=$(d2w --json metadata list organisationUnits --filter level:eq:4 --page-size 1 --fields id | jq -r '.[0].id')
echo ">>> registering against OU $OU"

# --- 1. Register + enroll in one atomic call -------------------------------
# `register` POSTs a {trackedEntities: [{...enrollments: [...]}]} bundle via
# /api/tracker. DHIS2 assigns the UIDs we pre-generated client-side so the
# response carries them back for downstream reference.

REGISTER=$(d2w --json data tracker register "$PROGRAM" \
    --ou "$OU" \
    --attr w75KJ2mc4zz=Aminata \
    --attr zDhUuAYrxNC=Kamara \
    --enrolled-at 2025-06-01)

TE=$(jq -r '.tracked_entity' <<< "$REGISTER")
ENROLLMENT=$(jq -r '.enrollment' <<< "$REGISTER")
echo ">>> registered TE=$TE enrollment=$ENROLLMENT"

# --- 2. Log the first event (Birth stage) ----------------------------------
# Stage-level event creation. --enrollment binds the event to the intake
# timeline; --dv passes DataElement values.

d2w data tracker event create \
    --enrollment "$ENROLLMENT" \
    --program "$PROGRAM" \
    --stage "$STAGE_BIRTH" \
    --at "$OU" \
    --te "$TE" \
    --occurred-at 2025-06-02

# --- 3. Outstanding stages ------------------------------------------------
# "What's due" report: every ACTIVE enrollment missing events on a
# non-repeatable program stage. Our new enrollment should appear because
# ZzYYXq4fJie (Baby Postnatal) isn't logged yet.

d2w data tracker outstanding "$PROGRAM" --ou "$OU"

# --- 4. Log the follow-up event -------------------------------------------

d2w data tracker event create \
    --enrollment "$ENROLLMENT" \
    --program "$PROGRAM" \
    --stage "$STAGE_POSTNATAL" \
    --at "$OU" \
    --te "$TE" \
    --occurred-at 2025-08-15

# --- 5. Verify it's no longer outstanding ---------------------------------
# Exit status is still 0 even with no hits — "nothing due" is success.

d2w data tracker outstanding "$PROGRAM" --ou "$OU"

# --- 6. Enroll an existing TE in a second program -------------------------
# For patients already in the system, `enrollment create` adds a new
# enrollment without rewriting the TE. Handy for cross-program follow-ups
# (e.g. a tracked child gets routed into a malaria-case-management flow).
#
# Example — if the instance has a second tracker program:
#   d2w data tracker enrollment create "$TE" <other-program-uid> --at "$OU"
