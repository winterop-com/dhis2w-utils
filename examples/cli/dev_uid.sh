#!/usr/bin/env bash
# `d2w dev uid` — mint 11-char DHIS2 UIDs client-side.
#
# A UID can be minted without asking the server, so a script decides an object's
# identity before the object exists and references it from the same bundle.
# No connection is opened.
set -euo pipefail

# One UID.
d2w dev uid

# A batch — one per line, so a shell loop or `mapfile` reads them directly.
d2w dev uid -n 5

# Minting the identity first is what lets a bundle reference itself.
MINTED=$(d2w dev uid)
echo "{\"indicatorTypes\":[{\"id\":\"$MINTED\",\"name\":\"Example type $MINTED\",\"factor\":1,\"number\":false}]}"
