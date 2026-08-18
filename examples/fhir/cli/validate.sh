#!/usr/bin/env bash
# d2w fhir validate — the FHIR-safety gate over an instance's codes and names.
set -euo pipefail

# Reads every code and name the instance holds, grades each finding by what it costs the
# publish (an in-scope '<' in a code on an identifier surface or in any object's name is an
# error - the build aborts on it), and writes fhir-validate-report.md / .csv / .pdf into
# reports/ beside fhir.toml (or under the working directory - no project is required).
# --output-dir names another directory, --format narrows the set, --details lists the
# info-grade findings individually.
#
# The exit code is the whole point: errors exit 1, which is the CI gate. Read it rather
# than let `set -e` take the script down - the seeded Sierra Leone fixture carries names
# FHIR cannot template ("<5 y"), so a run against it exits 1 and that is the gate working.
d2w fhir validate --output-dir ./validate-reports \
    || echo "validate found errors - the CI gate did its job"

ls validate-reports

rm -rf validate-reports
