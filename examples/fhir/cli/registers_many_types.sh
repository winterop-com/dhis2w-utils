#!/usr/bin/env bash
# Many tracked entity types, one register apiece - and two of them sharing one FHIR resource.
# Needs the serve extra: `pip install 'dhis2w-cli[serve]'` or `uv add dhis2w-fhir-serve`.
# WRITES TO DHIS2: it creates three tracked entity types, one tracked entity attribute, one
# registration programme per type, and one tracked entity per type - and removes every one of them
# before it exits, however it exits. The
# removal includes `d2w maintenance cleanup tracked-entities`, which hard-removes EVERY
# soft-deleted tracked entity on the instance rather than only this script's, because a
# soft-deleted entity still holds its type down (see the cleanup function). That is why this is in
# verify_examples.py's SKIP_BY_DEFAULT: run it by hand, against a stack you can write to.
set -euo pipefail

# A DHIS2 instance tracks whatever the project tracks. Fifty tracked entity types is an ordinary
# number for one that follows people, households, cold-chain equipment, vehicles, water points,
# and lab samples - and FHIR says what a thing is through its resource type, so the guide has to
# say which is which. `[generate.tracked_entity_types]` is where: one line per type.
#
#   [generate.tracked_entity_types]
#   "<type uid>" = "Device"        a fridge, a vehicle, a piece of equipment
#   "<type uid>" = "Specimen"      a lab sample
#   # a type this table never mentions is a Patient
#
# The last line is the rule that keeps a person-tracking project's config empty, and the rule
# that makes a fifty-type instance need a checklist: `d2w fhir validate` prints one, a row per
# type nobody typed.
#
# THIS SCRIPT IS ABOUT WHAT THAT TABLE BECOMES WHEN IT IS SERVED. Three types, two of them
# `Device`, and the whole point is the second half of that sentence: one FHIR resource type is
# ONE register serving the union of its tracked entity types. `GET /Device` is the fridges and
# the vehicles together, each resource still saying which type it is, and `_tag` is how a caller
# asks for one of them alone.

pick_port() {
    local candidate
    for candidate in $(seq 8130 8199); do
        if ! (exec 3<>"/dev/tcp/127.0.0.1/${candidate}") 2>/dev/null; then
            printf '%s\n' "$candidate"
            return 0
        fi
    done
    echo "no free port between 8130 and 8199" >&2
    return 1
}
PORT="${FHIR_MANY_TYPES_PORT:-$(pick_port)}"
BASE="http://127.0.0.1:${PORT}"

WORKSPACE="$(mktemp -d)"
cd "$WORKSPACE"

# --- 1. Three kinds of thing this instance now tracks -------------------------------------------
#
# UIDs are drawn rather than written down: this script runs against a stack that already carries
# demo metadata, and a fixed UID is a collision waiting for the second run.
read -r FRIDGE_TYPE VEHICLE_TYPE SAMPLE_TYPE ASSET_TAG <<<"$(d2w dev uid --count 4 | tr '\n' ' ')"

# `sharing.public` is stated rather than left to the default, because a demo type everybody may
# read is what a demo wants; a real one decides for itself.
cat >demo-types.json <<JSON
{
  "trackedEntityAttributes": [
    {
      "id": "${ASSET_TAG}",
      "name": "Demo asset tag",
      "shortName": "Demo asset tag",
      "valueType": "TEXT",
      "aggregationType": "NONE",
      "unique": true,
      "displayInListNoProgram": true,
      "sharing": {"public": "rw------"}
    }
  ],
  "trackedEntityTypes": [
    {
      "id": "${FRIDGE_TYPE}",
      "name": "Demo cold-chain fridge",
      "shortName": "Demo fridge",
      "sharing": {"public": "rwrw----"},
      "trackedEntityTypeAttributes": [
        {"trackedEntityAttribute": {"id": "${ASSET_TAG}"}, "mandatory": true, "searchable": true}
      ]
    },
    {
      "id": "${VEHICLE_TYPE}",
      "name": "Demo delivery vehicle",
      "shortName": "Demo vehicle",
      "sharing": {"public": "rwrw----"},
      "trackedEntityTypeAttributes": [
        {"trackedEntityAttribute": {"id": "${ASSET_TAG}"}, "mandatory": true, "searchable": true}
      ]
    },
    {
      "id": "${SAMPLE_TYPE}",
      "name": "Demo sample batch",
      "shortName": "Demo sample",
      "sharing": {"public": "rwrw----"},
      "trackedEntityTypeAttributes": [
        {"trackedEntityAttribute": {"id": "${ASSET_TAG}"}, "mandatory": true, "searchable": true}
      ]
    }
  ]
}
JSON

# The removal is written before the creation, in the order DHIS2 needs it, because a bundle it can
# create in one post is not a bundle it can delete in one post. `importStrategy=DELETE` sorts the
# objects the way it sorts a create - referenced first - so a bundle holding a tracked entity type
# AND the attribute that type collects tries to delete the attribute while the type still
# references it, and answers a raw Postgres foreign-key violation (BUGS.md 104). So the types come
# off in one post and the attribute in the next.
cat >delete-types.json <<JSON
{"trackedEntityTypes": [{"id": "${FRIDGE_TYPE}"}, {"id": "${VEHICLE_TYPE}"}, {"id": "${SAMPLE_TYPE}"}]}
JSON
DELETE_PROGRAMMES="${WORKSPACE}/delete-programmes.json"
cat >delete-attribute.json <<JSON
{"trackedEntityAttributes": [{"id": "${ASSET_TAG}"}]}
JSON

# Everything this script creates comes back off the instance before it exits - on the happy path,
# on a failure, and on a Ctrl-C. The trap is armed here, before the first write, so there is no
# window in which something exists and nothing is going to remove it.
CREATED_ENTITIES=""
cleanup() {
    set +e
    echo "--- cleaning up ---"
    if [ -n "${SERVER_PID:-}" ]; then
        kill "${SERVER_PID}" 2>/dev/null
    fi
    if [ -n "${CREATED_ENTITIES}" ]; then
        # shellcheck disable=SC2086 - the UIDs are a deliberate argument list
        d2w data tracker delete ${CREATED_ENTITIES} --yes >/dev/null 2>&1 \
            && echo "removed the tracked entities this run created"
    fi
    # A tracker delete is a SOFT delete, and a soft-deleted tracked entity still holds its type
    # down: the metadata delete answers E4030 "associated with another object: TrackedEntity",
    # and no `/api/tracker/trackedEntities` query will show the row that is holding it, not even
    # with `includeDeleted=true` (BUGS.md 105). The purge is what removes it for real.
    d2w maintenance cleanup tracked-entities --yes >/dev/null 2>&1
    if [ -f "${DELETE_PROGRAMMES}" ]; then
        d2w metadata import "${DELETE_PROGRAMMES}" --strategy DELETE >/dev/null 2>&1 \
            && echo "removed the 3 registration programmes"
    fi
    d2w metadata import "${WORKSPACE}/delete-types.json" --strategy DELETE >/dev/null 2>&1 \
        && echo "removed the 3 tracked entity types"
    d2w metadata import "${WORKSPACE}/delete-attribute.json" --strategy DELETE >/dev/null 2>&1 \
        && echo "removed the tracked entity attribute"
    d2w data tracker type
    cd / && rm -rf "${WORKSPACE}"
}
trap cleanup EXIT

d2w metadata import demo-types.json --strategy CREATE

# `d2w data tracker type` is the instance's own list, which is the list the mapping table is
# written against. On a fifty-type instance this is the fifty rows a project author reads once.
d2w data tracker type | tail -8

# --- 2. A registration programme per type -------------------------------------------------------
#
# One tracker programme apiece, each enrolling its own type, each collecting the asset tag, each
# scoped to the organisation unit the capture reports at. The programme is not decoration:
# `GET /api/tracker/trackedEntities?trackedEntityType=<uid>` answers an EMPTY page - not a
# refusal - for a type no accessible programme tracks, whatever the type's sharing says and
# however many entities of it the instance holds (BUGS.md 106). So a type nothing enrols is a type
# nothing can read back, and a register over it would be honest about the guide and silent about
# the instance.
# The root unit, because `--max-level 2` publishes it and `$generate` reports at a unit the guide
# published and the programme is assigned to. Assign a programme somewhere the registry stops
# short of and DHIS2 answers the forward `E1041 Enrollment OrganisationUnit and Program do not
# match` - the guide and the instance disagreeing about where the thing was registered.
CAPTURE_ORG_UNIT="ImspTQPwCqd"
programme_for() {
    local type_uid="$1" name="$2" short="$3" programme
    programme="$(d2w --json metadata programs create --name "$name" --short-name "$short" \
        --tracked-entity-type "$type_uid" 2>/dev/null | jq -r '.id')"
    d2w metadata programs add-attribute "$programme" "${ASSET_TAG}" --searchable >/dev/null
    d2w metadata programs add-to-ou "$programme" "${CAPTURE_ORG_UNIT}" >/dev/null
    printf '%s\n' "$programme"
}
FRIDGE_PROGRAMME="$(programme_for "${FRIDGE_TYPE}" "Demo fridge monitoring" "Demo fridge prog")"
VEHICLE_PROGRAMME="$(programme_for "${VEHICLE_TYPE}" "Demo vehicle monitoring" "Demo vehicle prog")"
SAMPLE_PROGRAMME="$(programme_for "${SAMPLE_TYPE}" "Demo sample handling" "Demo sample prog")"

cat >delete-programmes.json <<JSON
{"programs": [{"id": "${FRIDGE_PROGRAMME}"}, {"id": "${VEHICLE_PROGRAMME}"}, {"id": "${SAMPLE_PROGRAMME}"}]}
JSON

# --- 3. One line per type -----------------------------------------------------------------------
#
# The programmes are what `[generate.tracker_programs]` selects; the TYPES are what
# `[generate.tracked_entity_types]` types. The two tables answer different questions, and naming a
# type in the second selects nothing - which is why a fifty-type instance's mapping table can name
# every type it holds without the guide growing by a single form.
d2w fhir init demo-many-types --id dhis2.fhir.manytypesdemo \
    --canonical http://example.org/fhir/many-types-demo --publisher "Demo Org" \
    --tracker-program "${FRIDGE_PROGRAMME}" --tracker-program "${VEHICLE_PROGRAMME}" \
    --tracker-program "${SAMPLE_PROGRAMME}" --max-level 2
cd demo-many-types

cat >>fhir.toml <<TOML

[generate.tracked_entity_types]
"${FRIDGE_TYPE}" = "Device"
"${VEHICLE_TYPE}" = "Device"
"${SAMPLE_TYPE}" = "Specimen"

[serve.tracked_entities]
tracked_entity_types = ["${FRIDGE_TYPE}", "${VEHICLE_TYPE}", "${SAMPLE_TYPE}"]
TOML

# `--substitute-hostile-names` answers the one question a run against the seeded demo database
# stops to ask: several of its DHIS2 names carry a raw `<`, which the IG publisher writes into a
# page it then strict-parses. The rewrite changes the published guide and never the instance.
# examples/fhir/cli/generate_hostile_names.sh is that gate's own story.
d2w fhir generate --substitute-hostile-names

# The map the running facade reads its resources off. `fhir.toml` is the generator's input and is
# never read by a server - `D2TET_CM` is, so a served resource and a published `subjectType`
# cannot disagree. One row per type, the type nobody typed included, so a consumer can tell an
# unmapped type from one deliberately published as a person.
grep -E '^\* group\[0\]\.element\[[0-9]+\]\.(display|target\[0\]\.code)' \
    ig/input/fsh/data-dictionary/tracked-entity-types.fsh

# And the registration form of every programme tracking one of those types declares the same
# resource as its `subjectType` - which is what `$generate` reads to type the subject it mints.
# The type owns the nature of the thing, so two programmes over one type cannot disagree.
grep -H 'subjectType' ig/input/fsh/tracker-programs/*/registration.fsh

# --- 4. Serve it, and read what it declares -----------------------------------------------------
start_facade() {
    d2w fhir serve --live --no-ui --port "$PORT" >facade.log 2>&1 &
    SERVER_PID=$!
    for _ in $(seq 1 90); do
        if [ "$(curl -s -o /dev/null -w '%{http_code}' "${BASE}/metadata")" = "200" ]; then
            return 0
        fi
        sleep 1
    done
    echo "the facade did not answer ${BASE}/metadata within 90s:" >&2
    tail -20 facade.log >&2
    return 1
}
start_facade

# Two registers from three types: `Device` appears once, and its documentation names both of the
# tracked entity types behind it. A client learns that before it asks for anything.
curl -s "${BASE}/metadata" >capability.json
jq -r '.rest[0].resource[] | select(.searchParam[]?.name == "_tag")
       | "REGISTER  " + .type + "\n          " + (.documentation | split(": ")[1] | split(". Identity")[0])' \
    capability.json

# --- 5. Capture one registration per type -------------------------------------------------------
#
# `$generate` fills a served form with a synthetic answer, and the subject it mints is typed by
# that form's own `subjectType` - so a fridge registration is about a `Device` without this
# script having to say so anywhere.
capture() {
    local form="$1"
    local seed="$2"
    curl -s "${BASE}/Questionnaire/${form}/\$generate?seed=${seed}" >"registration-${form}.json"
    jq -r '"generated  " + .subject.type + "  " + .subject.identifier.value' "registration-${form}.json"
    CREATED_ENTITIES="${CREATED_ENTITIES} $(jq -r '.subject.identifier.value' "registration-${form}.json")"
    curl -s -o /dev/null -w "posted     %{http_code}\n" -X POST "${BASE}/QuestionnaireResponse" \
        -H 'Content-Type: application/fhir+json' --data-binary "@registration-${form}.json"
}
# One seed per form, because the seed is what the minted subject UID is drawn from: three forms
# filled from one seed would name one tracked entity three times, and DHIS2 would accept the first
# and answer E1002 to the rest.
capture "${FRIDGE_PROGRAMME}" 1
capture "${VEHICLE_PROGRAMME}" 2
capture "${SAMPLE_PROGRAMME}" 3

# The receipts are in the spool; `--import` is the run that posts them to DHIS2. Each one lands as
# a tracked entity of its own type, because the forward leg reads the type off the form rather
# than off the FHIR resource the subject was typed as - which is what keeps the two `Device`
# types two DHIS2 types.
d2w fhir forward --import

# --- 6. Read the registers back -----------------------------------------------------------------
#
# `GET /Device` is the union: the fridge and the vehicle, in one searchset, each resource tagged
# with the DHIS2 type it actually is. A page never mixes types - DHIS2 pages one type at a time,
# so the walk crosses the boundary by following the Bundle's own `next` link, which is what a
# client does anyway and the only thing it has to do to see the whole union.
walk() {
    local url="$1" page
    while [ -n "$url" ]; do
        page="$(curl -s "$url")"
        printf '%s' "$page" | jq -r '.entry[]? | "  " + .resource.id + "  tracked entity type " + .resource.meta.tag[0].code'
        url="$(printf '%s' "$page" | jq -r '.link[]? | select(.relation == "next") | .url')"
    done
}
echo "GET /Device -> $(curl -s "${BASE}/Device?_count=1" | jq -r '.total // "no total"') in the register"
walk "${BASE}/Device?_count=1"

# `_tag` asks that union about one of its halves. It is R4's own token search over `meta.tag`,
# which is the very element each resource states its type in - so the parameter reads what the
# resource says rather than naming a dimension this server invented.
curl -s "${BASE}/Device?_tag=${VEHICLE_TYPE}&_count=10" >vehicles.json
echo "GET /Device?_tag=${VEHICLE_TYPE} -> $(jq -r '.total // "no total"' vehicles.json)"
jq -r '.entry[]? | "  " + .resource.id + "  tracked entity type " + .resource.meta.tag[0].code' vehicles.json
# The `next` link of a narrowed walk carries the tag, so a walk stays inside the type it started
# in rather than falling into the rest of the register at the type boundary.
jq -r '.link[]? | select(.relation == "next") | "  next: " + .url' vehicles.json

# And the sample batch is somewhere else entirely, because its row of the map says so.
curl -s "${BASE}/Specimen?_count=10" >specimens.json
echo "GET /Specimen -> $(jq -r '.total // "no total"' specimens.json) in the register"

# A `_tag` naming a type this resource is not served over is an unsatisfied query rather than a
# malformed one: an empty searchset, and nothing asked of the instance to confirm it.
echo "GET /Device?_tag=${SAMPLE_TYPE} -> $(curl -s "${BASE}/Device?_tag=${SAMPLE_TYPE}" | jq -r '.total')"

# --- 7. The checklist a fifty-type instance needs -----------------------------------------------
#
# `d2w fhir validate` names every tracked entity type the instance holds that this project's
# table does not, one row each, with the config line that would type it. On this run the three
# demo types are typed and the instance's own are not - which is the list a project author works
# down.
d2w --json fhir validate --no-fail >validation.json
jq -r '.findings[] | select(.category == "unmapped-tracked-entity-type")
       | "UNTYPED  " + .name + " (" + .uid + ")  -  " + .message' validation.json

# Everything above is undone by the EXIT trap: the three tracked entities, the three types, and
# the attribute. The instance ends as it began.
