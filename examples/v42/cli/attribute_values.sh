#!/usr/bin/env bash
# Cross-resource AttributeValue workflows via `dhis2 metadata attributes`.
# Works against any DHIS2 resource with an `attributeValues` field:
# dataElements, options, organisationUnits, indicators, dashboards, ...
set -euo pipefail

# --- Read one value --------------------------------------------------------
# Accepts the Attribute's UID or its business code.

dhis2 metadata attributes get options OptVacBCG01 SNOMED_CODE
# → 77656005

# Works on any resource type. SNOMED_CODE happens to be optionAttribute-only
# in the seed; this call returns nothing (exit 1) because the DE has no value
# attached. No HTTP error — just `no value for attribute ...` on stderr.
# dhis2 metadata attributes get dataElements fClA2Erf6IO SNOMED_CODE

# --- Reverse lookup — THE integration killer -------------------------------
# Given an external-system code, return the DHIS2 UIDs it maps to.

dhis2 metadata attributes find options SNOMED_CODE 386661006 \
    --filter optionSet.id:eq:OsVaccType1
# → OptVacMes01  (the Measles option, inside the VACCINE_TYPE set)

# Without the filter constraint, you'd search every option on the instance —
# useful on a cleaned-up dataset, expensive on a large one.
# dhis2 metadata attributes find options SNOMED_CODE 386661006

# Exit 1 on miss — safe in pipelines:
# dhis2 metadata attributes find options SNOMED_CODE NOPE

# --- Round-trip write + delete --------------------------------------------
# Read-merge-write every call; preserves unrelated attribute entries.

dhis2 metadata attributes set options OptVacBCG01 SNOMED_CODE TESTING-XYZ
dhis2 metadata attributes get options OptVacBCG01 SNOMED_CODE         # → TESTING-XYZ
dhis2 metadata attributes delete options OptVacBCG01 SNOMED_CODE       # removes the entry
dhis2 metadata attributes delete options OptVacBCG01 SNOMED_CODE       # no-op (already gone)
dhis2 metadata attributes set options OptVacBCG01 SNOMED_CODE 77656005 # restore
