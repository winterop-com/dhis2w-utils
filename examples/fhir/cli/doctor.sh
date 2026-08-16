#!/usr/bin/env bash
# FHIR doctor — one command, one verdict on whether an instance works with the toolchain.
# Needs the serve extra for the serve/capture/forward phases:
# `pip install 'dhis2w-cli[serve]'` or `uv add dhis2w-fhir-serve`.
# Doctor's compile phase runs the dockerized SUSHI build, which is minutes on a cold image, so
# `make verify-examples` skips it: `infra/scripts/verify_examples.py` lists it under "slow
# server-side jobs". It never writes to the instance - the forward phase runs validate-only.
set -euo pipefail

# The whole chain against the ambient profile's instance: connect, scaffold, generate,
# compile, validate, serve, capture, forward. Nine phases, one verdict line, exit 1 only
# when a phase failed. Everything happens in a temporary directory that is removed when
# the run ends — doctor never writes to the instance (forward runs validate-only) and
# never publishes anything.
d2w fhir doctor

# The instance is named the way `d2w fhir serve` names it: the root flag, or DHIS2_PROFILE.
# There is no local --profile, so one run is always about one stated instance.
# d2w -p laos fhir doctor
# DHIS2_PROFILE=laos d2w fhir doctor

# --live adds the oracle: the phase doctor exists for. Every served DHIS2 UID is resolved
# back against the collection it names, and a seeded sample per family (organisation units,
# option sets, data sets, programs) is deep-compared field by field against the object it
# derives from. The instance is the authority and the served resource is the claim on trial;
# a mismatch names the field path it was found at.
d2w fhir doctor --live --samples 3

# Keep the workspace to read what the run actually generated — the scaffolded project, the
# emitted FSH, the compiled resources, and the receipts the capture phase spooled.
d2w fhir doctor --workspace ./doctor-run
ls doctor-run
ls doctor-run/reports

# The markdown report is the artifact a handover is read from: the phase table, every
# finding with its field path, and the header saying which profile, which instance, which
# DHIS2 version, and when.
head -30 doctor-run/reports/fhir-doctor-report.md

# --json carries the typed DoctorReport on stdout while the narration stays on stderr, so
# a caller pipes it straight into jq. Every phase, its outcome, and its findings.
d2w --json fhir doctor --no-progress | jq -r '.phases[] | "\(.phase)\t\(.outcome)\t\(.evidence)"'

# The verdict in one field, for a CI gate that wants the sentence rather than the exit code.
d2w --json fhir doctor --no-progress | jq -r '[.phases[] | select(.outcome == "fail") | .phase]'

# The default is a small representative probe: the first data set, the first event program,
# the first tracker program, and the organisation-unit subtree those forms are assigned
# inside. --all-targets takes every data set, every program, and every level instead —
# correspondingly slower, and what you want before committing to a real project.
# d2w fhir doctor --all-targets

rm -rf doctor-run
