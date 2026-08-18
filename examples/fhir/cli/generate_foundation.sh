#!/usr/bin/env bash
# d2w fhir generate foundation — the instance-independent artifacts, with no client opened.
set -euo pipefail

d2w fhir init demo-foundation --id dhis2.fhir.foundationdemo \
    --canonical http://example.org/fhir/foundation-demo --publisher "Demo Org"
cd demo-foundation

# The foundation is everything the guide states about DHIS2 itself rather than about one
# instance: the $DHIS2-* identifier aliases and the NamingSystem declaring each, the
# D2Period extension with the period-type terminology, the D2FormType and D2AttributeValue
# extensions, the organisation-unit and tracker-enrollment extensions, the capture contract
# (the response profiles and the D2CaptureServer CapabilityStatement), the $generate
# OperationDefinition, and the aggregate conversion contract (the D2DataValueSet logical
# model and its StructureMap). It reads fhir.toml only - no DHIS2 client is opened - which
# is why it is the one target that runs on a plane.
d2w fhir generate foundation

ls ig/input/fsh/foundation

cd .. && rm -rf demo-foundation
