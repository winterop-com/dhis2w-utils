#!/usr/bin/env bash
# d2w --json fhir doctor — the typed DoctorReport on stdout, for jq and for CI.
# Needs the serve extra and docker for the compile phase; minutes per run, so
# `make verify-examples` skips it for the same reasons it skips doctor_probe.sh.
set -euo pipefail

# --json carries the typed DoctorReport on stdout while the narration stays on stderr, so a
# caller pipes it straight into jq. One run, read twice below.
d2w --json fhir doctor --no-progress > doctor-report.json

# Every phase, its outcome, and its evidence line.
jq -r '.phases[] | "\(.phase)\t\(.outcome)\t\(.evidence)"' doctor-report.json

# The failed phases in one field, for a CI gate that wants the sentence rather than the
# exit code alone.
jq -r '[.phases[] | select(.outcome == "fail") | .phase]' doctor-report.json

rm -f doctor-report.json
