#!/usr/bin/env bash
# d2w fhir generate — a run that rewrites FSH removes the compile those sources no longer match.
set -euo pipefail

# ig/fsh-generated/ is SUSHI's output and nobody else's: `make sushi` writes it from ig/input/fsh/,
# and check-artifacts, serve, forward and `make build` all read it. So a generate that rewrites a FSH
# source removes it rather than leave new sources beside a compile of the old ones. The foundation
# target reads fhir.toml alone - no DHIS2 client is opened - so this whole example runs offline.
d2w fhir init demo-stale-compile --id dhis2.fhir.staledemo \
    --canonical http://example.org/fhir/stale-demo --publisher "Demo Org"
cd demo-stale-compile

d2w fhir generate foundation

# Stand in for a SUSHI run: one compiled resource where SUSHI writes them.
mkdir -p ig/fsh-generated/resources
echo '{"resourceType": "CodeSystem", "id": "d2-period-type-cs"}' \
    > ig/fsh-generated/resources/CodeSystem-d2-period-type-cs.json

# Regenerating unchanged sources writes nothing, so the compile is still of the sources on disk and
# is left where it is - the tight edit loop costs no recompile.
d2w fhir generate foundation
ls ig/fsh-generated/resources

# Now make one source stale. Deleting a generated file is the cheap stand-in for the real case: a
# metadata change, or `--substitute-hostile-names` rewriting every name the guide publishes.
rm ig/input/fsh/foundation/d2-aliases.fsh

# The run rewrites that source, so it removes the compile and says so:
#   note: removed ig/fsh-generated: it held SUSHI's compile of FSH sources this run rewrote, ...
d2w fhir generate foundation

# Gone. `make sushi` in the project writes it again from the sources this run left behind, and
# `make build` compiles before it publishes, so a build needs nothing extra.
test ! -d ig/fsh-generated && echo "the compile is gone - run 'make sushi' to compile these sources"

cd .. && rm -rf demo-stale-compile
