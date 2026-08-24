#!/usr/bin/env bash
# d2w fhir validate --hostile-names — grade an instance under each hostile-names posture.
set -euo pipefail

d2w fhir init demo-validate-posture --id dhis2.fhir.validateposturedemo \
    --canonical http://example.org/fhir/validate-posture-demo --publisher "Demo Org"
cd demo-validate-posture

# The scaffold writes `hostile_names = "substitute"`, so this project publishes a DHIS2 name
# carrying '<' in wording the IG publisher survives - "Vitamin A given to under 5y" where
# DHIS2 states "Vitamin A given to < 5y". Validate reads the same key: those names are graded
# informational, the message names both spellings, and the run exits 0, because nothing about
# them stops the build. The summary's `hostile names` row says which posture produced the
# counts.
d2w fhir validate --output-dir ./posture-reports --format md

# Every finding the substitute posture rewrote away, in the report it wrote.
grep -c "rewritten for publication" posture-reports/fhir-validate-report.md

# The what-if run: the same instance graded as a project publishing every name exactly as
# DHIS2 states it. Those names are errors here, because the publisher strict-parses the pages
# it writes them into and `make build` dies in its last pass. The flag beats fhir.toml and
# changes no file. Read the exit code rather than let `set -e` take the script down.
d2w fhir validate --hostile-names refuse --output-dir ./posture-reports --format md \
    || echo "graded under refuse the same names are errors - that is the gate, not a failure"

# A DHIS2 code carrying '<' is an error under either posture: a code is an identifier a
# consumer joins on, so the substitution hyphenates a space in a code and never rewrites a
# '<'. generate_hostile_names.sh is the generate half of the same decision.
cd .. && rm -rf demo-validate-posture
