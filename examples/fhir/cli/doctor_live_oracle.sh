#!/usr/bin/env bash
# d2w fhir doctor --live — the oracle: served resources deep-compared against the instance.
# Needs the serve extra and docker for the compile phase; minutes per run, so
# `make verify-examples` skips it for the same reasons it skips doctor_probe.sh.
set -euo pipefail

# --live adds the oracle: the phase doctor exists for. Every served DHIS2 UID is resolved
# back against the collection it names, and a seeded sample per family (organisation units,
# option sets, data sets, programs) is deep-compared field by field against the object it
# derives from. The instance is the authority and the served resource is the claim on
# trial; a mismatch names the field path it was found at. --samples sizes the per-family
# sample, and the seed makes a rerun compare the same objects.
d2w fhir doctor --live --samples 3
