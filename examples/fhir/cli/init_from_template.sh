#!/usr/bin/env bash
# d2w fhir init --template — scaffold a project whose guide is already generated.
set -euo pipefail

# A template is a guide somebody already generated against a real DHIS2 instance, shipped as
# the tree that guide's ig/input/ held. Scaffolding from one writes the ordinary scaffold and
# lays that tree down beside it, so the project compiles with `make sushi` and serves with
# `d2w fhir serve` without ever reaching an instance.
#
# --list-templates names them and says where each is read from: a bundled template rides the
# installed package, a checkout one is read from examples/fhir/igs/ of this repository and
# exists only in a clone of it.
d2w fhir init --list-templates

workspace="$(mktemp -d)"
trap 'rm -rf "${workspace}"' EXIT

# The identity flags mean the same thing they do without a template, and they reach further:
# Questionnaire.url, CodeSystem.url, and every valueSet reference under ig/input/ state the
# canonical in full, so --canonical is rewritten through the whole laid-down tree rather than
# through the identity files alone.
d2w fhir init "${workspace}/demo" \
    --template patient-summary \
    --id dhis2.fhir.templatedemo \
    --canonical http://example.org/fhir/template-demo \
    --publisher "Demo Org"

# What landed: the scaffold files, plus the template's own ig/input/ tree beside them.
ls "${workspace}/demo"
ls "${workspace}/demo/ig/input"

# The canonical the payload publishes under is this project's, not the one it was generated
# under - which is what makes a template a starting point rather than a copy of a guide.
grep -m1 canonical "${workspace}/demo/ig/sushi-config.yaml"
