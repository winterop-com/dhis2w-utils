#!/usr/bin/env bash
# FHIR sync — fill a durable copy of the DHIS2 register, as FHIR, on disk.
#
# `d2w fhir sync` is the one command that writes a project's materialized projection: a copy of the
# mapped scope of a DHIS2 instance, held as the FHIR resources the project's map publishes. The first
# run reads the whole scope; every run after it reads what moved. Nothing here writes to DHIS2, and
# nothing but this command writes to the projection.
#
# Reads an instance through the active profile. No compile step, no port bound, no docker.
set -euo pipefail

# The Child Programme's tracked entity type on the seeded demo database. Naming it keeps the sync to
# the one type this example is about, rather than every type the instance holds.
PERSON_TYPE="nEenWmSyUEp"

d2w fhir init sync-demo --id dhis2.fhir.syncdemo --canonical "http://example.org/fhir/sync-demo" \
    --publisher "Demo Org" --tracker-program IpHINAT79UW --max-level 2

cd sync-demo

# Two tables turn a live facade into a synced one. `[serve.projection]` says this project holds a
# copy and where it lives; `[serve.search]` says a register search is answered from it. Stating the
# second without the first is refused when the file is read, naming both keys.
cat >>fhir.toml <<TOML

[serve.tracked_entities]
tracked_entity_types = ["${PERSON_TYPE}"]

[serve.projection]
store = "sqlite"

[serve.search]
backend = "projection"
TOML

# --dry-run reads the instance exactly as a committing run does, counts what it would change, and
# writes nothing at all — not a row, not a cursor. The posture `[forward] import = false` sets for
# the other half of the loop.
d2w fhir sync --dry-run

# The first real run. It has no watermark to start from, so it reads the whole mapped scope: the
# tracked entity types in scope, bulk-paged, each page projected through the same
# `registered_entity_for` a live register read answers with. The report says what it did per FHIR
# resource type and where each collection's cursor now stands.
d2w fhir sync

# The file it wrote. One SQLite database beside the receipt spool, under a directory the scaffold
# already gitignores — neither is source, and both are things this project can make again.
ls -l .serve/projection.sqlite

# The second run reads what moved. On an unchanged instance that is one request per collection and a
# few dozen bytes. It usually still reports an update or two: an incremental run polls from its own
# watermark less an overlap window, so anything changed in the last few minutes is read again — and
# the counts are read out of the projection rather than assumed, so a re-read row is honestly an
# update rather than a creation. `[serve.projection] overlap_seconds` is the window.
d2w fhir sync

# Every poll carries `includeDeleted=true`. It is not a flag, because its absence is silent: a sync
# without it never learns that anybody left, and does not error. A tombstone removes the row rather
# than archiving a last state — DHIS2 will not answer a read of a deleted entity, so there is no
# final state to archive.

# --rebuild empties the projection and fills it from zero. That is routine rather than a recovery
# step: it is how a change to `[serve.tracked_entities]` or to the published map reaches what is
# already stored. Deleting .serve/projection.sqlite does the same thing.
d2w fhir sync --rebuild

# --json puts the whole SyncReport on stdout and nothing else, so the tables on stderr never have to
# be filtered out. `cursor` is the instant every answer served from this projection states.
d2w --json fhir sync | head -c 400
echo

# From here, `d2w fhir serve --live` answers register searches from what this filled — one indexed
# query instead of one tracker query per key per type, `_content` for a search across every value a
# person holds, and an `X-DHIS2W-Projection-As-Of` on every answer. What it does NOT change is who
# may see whom: each match is read back from the instance under the caller's own credentials.
# See examples/fhir/cli/serve.sh for the server, and docs/fhir/201-serve.md for the posture.

cd .. && rm -rf sync-demo
