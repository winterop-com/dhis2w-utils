#!/usr/bin/env bash
# `d2w metadata get <resource> <uid>` — fetch one object by UID.
set -euo pipefail

# A concise Rich summary by default: id, name, code, the common metadata, and
# the notable extras, with the remaining keys named rather than printed.
d2w metadata get dataElements fClA2Erf6IO

# The Sierra Leone root organisation unit.
d2w metadata get organisationUnits ImspTQPwCqd

# --fields narrows what DHIS2 returns; --json prints the payload for jq.
d2w --json metadata get dataElements fClA2Erf6IO --fields "id,name,valueType,domainType" | jq .
