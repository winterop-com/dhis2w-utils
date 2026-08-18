#!/usr/bin/env bash
# d2w fhir init --refresh — bring an existing project's scaffold-managed files up to date.
set -euo pipefail

d2w fhir init demo-refresh --id dhis2.fhir.refreshdemo \
    --canonical http://example.org/fhir/refresh-demo --publisher "Demo Org"

cd demo-refresh

# The identity comes off the project itself - fhir.toml, ig/fsh.ini, ig/sushi-config.yaml -
# so a refresh takes no identity flags, and fhir.toml is never written. A file is rewritten
# only when the current scaffold render reproduces every line already on disk, in order: a
# refresh adds what the scaffold gained (a new path-resource glob, a new .gitignore entry)
# and never drops a line you wrote. A file carrying anything the scaffold would not produce
# is left byte-identical and reported as skipped.
#
# The case it exists for: a project scaffolded before a sushi-config path-resource glob
# landed compiles fine - SUSHI recurses into input/resources on its own - while the IG
# publisher, which does not recurse, drops those resources from the published guide.
#
# The consequence to know: a scaffold line you deliberately deleted comes back, because a
# deletion leaves the file a subsequence of the render. Comment such a line out instead.
echo "# a line of my own" >> .gitignore
d2w fhir init . --refresh

# The edited .gitignore was refreshed - the render reproduces every line, the added one stays.
tail -1 .gitignore

cd .. && rm -rf demo-refresh
