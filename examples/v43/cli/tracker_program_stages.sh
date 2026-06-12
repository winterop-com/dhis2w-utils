#!/usr/bin/env bash
# Tracker schema authoring — step 3: ProgramStage + PSDE.
#
# Completes the tracker-schema authoring stretch. Given a Program
# created in step 2, attach stages (visits), wire DataElements into
# each stage with flags (`compulsory`, `displayInReports`,
# `allowFutureDate`), reorder the in-stage entry form.
#
#   d2w metadata program-stages   /api/programStages
#
# This example creates a Person TET + a tracker Program + a visit
# stage + two DEs on the stage, reorders, then tears everything down.
set -euo pipefail

# ---------------------------------------------------------------------------
# Foundations: one TEA, a Person TET, a tracker Program.
# ---------------------------------------------------------------------------

TEA_OUT=$(d2w --json metadata tracked-entity-attributes create \
    --name "Example stage demo given name" \
    --short-name "ExStgGivN" \
    --value-type TEXT)
TEA_UID=$(printf '%s' "$TEA_OUT" | python -c 'import json,sys; print(json.load(sys.stdin)["id"])')

TET_OUT=$(d2w --json metadata tracked-entity-types create \
    --name "Example stage demo person" \
    --short-name "ExStgPers" \
    --allow-audit-log \
    --feature-type NONE \
    --min-attrs 1)
TET_UID=$(printf '%s' "$TET_OUT" | python -c 'import json,sys; print(json.load(sys.stdin)["id"])')

PRG_OUT=$(d2w --json metadata programs create \
    --name "Example demo ANC-like program" \
    --short-name "ExStgPrg" \
    --program-type WITH_REGISTRATION \
    --tracked-entity-type "$TET_UID" \
    --display-incident-date)
PRG_UID=$(printf '%s' "$PRG_OUT" | python -c 'import json,sys; print(json.load(sys.stdin)["id"])')
d2w metadata programs add-attribute "$PRG_UID" "$TEA_UID" --mandatory

# ---------------------------------------------------------------------------
# Pick two aggregate DEs to attach to the stage (normally you'd mint
# tracker-domain DEs; Play exposes aggregate DEs for this demo).
# ---------------------------------------------------------------------------

DES_JSON=$(d2w --json metadata list dataElements --page-size 2 --fields "id,name")
DE_A=$(printf '%s' "$DES_JSON" | python -c 'import json,sys; print(json.load(sys.stdin)[0]["id"])')
DE_B=$(printf '%s' "$DES_JSON" | python -c 'import json,sys; print(json.load(sys.stdin)[1]["id"])')

# ---------------------------------------------------------------------------
# A first-visit stage with the two DEs, reorder, tear down.
# ---------------------------------------------------------------------------

STAGE_OUT=$(d2w --json metadata program-stages create \
    --name "Example demo visit stage" \
    --program "$PRG_UID" \
    --sort-order 1 \
    --min-days 0 \
    --standard-interval 30)
STAGE_UID=$(printf '%s' "$STAGE_OUT" | python -c 'import json,sys; print(json.load(sys.stdin)["id"])')
echo "created stage $STAGE_UID under program $PRG_UID"

d2w metadata program-stages add-element "$STAGE_UID" "$DE_A" --compulsory --sort-order 0
d2w metadata program-stages add-element "$STAGE_UID" "$DE_B" --sort-order 1
d2w metadata program-stages get "$STAGE_UID"

# Swap their order.
d2w metadata program-stages reorder "$STAGE_UID" "$DE_B" "$DE_A"

# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------

d2w metadata program-stages remove-element "$STAGE_UID" "$DE_A"
d2w metadata program-stages remove-element "$STAGE_UID" "$DE_B"
d2w metadata program-stages delete "$STAGE_UID" --yes

d2w metadata programs remove-attribute "$PRG_UID" "$TEA_UID"
d2w metadata programs delete "$PRG_UID" --yes
d2w metadata tracked-entity-types delete "$TET_UID" --yes
d2w metadata tracked-entity-attributes delete "$TEA_UID" --yes
