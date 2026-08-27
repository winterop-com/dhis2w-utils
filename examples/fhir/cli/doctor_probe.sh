#!/usr/bin/env bash
# d2w fhir doctor — the representative probe: one command, one verdict on whether an instance
# works with the toolchain.
# Needs the serve extra for the serve/capture/forward phases:
# `pip install 'dhis2w-cli[serve]'` or `uv add dhis2w-fhir-serve`.
# Doctor's compile phase runs the dockerized SUSHI build, which is minutes on a cold image, so
# `make verify-examples` skips it: `infra/scripts/verify_examples.py` lists it under "slow
# server-side jobs". It never writes to the instance - the forward phase runs validate-only.
set -euo pipefail

# The whole chain against the ambient profile's instance: connect, scaffold, generate,
# compile, validate, serve, capture, forward, oracle, drift. Ten phases, one verdict line,
# exit 1 only when a phase failed. The first nine happen in a temporary directory that is
# removed when the run ends - doctor never writes to the instance and never publishes anything.
#
# The default probe is small and representative: the first data set, the first event program,
# the first tracker program, and the organisation-unit subtree those forms are assigned inside.
# examples/fhir/cli/doctor_all_targets.sh is the same run over every data set and every program.
#
# The instance is named the way `d2w fhir serve` names it: the root flag, or DHIS2_PROFILE.
# There is no local --profile, so one run is always about one stated instance.
#   d2w -p laos fhir doctor
#
# The run writes reports/fhir-doctor-report.md under the working directory, so this one is made
# from a scratch directory that goes away with it.
workspace="$(mktemp -d)"
trap 'rm -rf "${workspace}"' EXIT
cd "${workspace}"

# The drift phase is the one phase whose subject is a project rather than the throwaway
# workspace, so from a directory holding no fhir.toml it is skipped with that as its reason -
# examples/fhir/cli/doctor_drift.sh is that phase run where it has something to read.
d2w fhir doctor
