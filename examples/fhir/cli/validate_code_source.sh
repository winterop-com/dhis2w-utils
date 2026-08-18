#!/usr/bin/env bash
# d2w fhir validate --code-source code — preview what switching to DHIS2 codes would cost.
set -euo pipefail

# Generation defaults to DHIS2 UIDs for concept codes because they are unique, stable, and
# always FHIR-valid; DHIS2 codes are frequently absent or invalid. The migration path is
# id-first-then-code, and this dial is the readiness probe: in id mode the code findings
# (invalid-code, missing-code, duplicate-code) are informational because nothing reads them
# yet; --code-source code grades them as the errors they would become, so the report is what
# the switch costs right now. Fix the instance, watch the report shrink, then flip
# concept_code_source in fhir.toml.
#
# --no-fail exits 0 despite the errors, which is what a probe wants - the gate run without
# the flag is the CI half (see validate.sh).
d2w fhir validate --code-source code --no-fail --output-dir ./code-probe-reports

ls code-probe-reports

rm -rf code-probe-reports
