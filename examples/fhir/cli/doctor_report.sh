#!/usr/bin/env bash
# d2w fhir doctor --workspace — keep the run's workspace and hand over its report.
# Needs the serve extra and docker for the compile phase; minutes per run, so
# `make verify-examples` skips it for the same reasons it skips doctor.sh.
set -euo pipefail

# --workspace keeps what the run generated - the scaffolded project, the emitted FSH, the
# compiled resources, and the receipts the capture phase spooled - instead of removing the
# temporary directory when the run ends.
d2w fhir doctor --workspace ./doctor-run
ls doctor-run
ls doctor-run/reports

# The markdown report is the artifact a handover is read from: the phase table, every
# finding with its field path, and the header saying which profile, which instance, which
# DHIS2 version, and when.
head -30 doctor-run/reports/fhir-doctor-report.md

rm -rf doctor-run
