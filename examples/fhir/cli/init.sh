#!/usr/bin/env bash
# d2w fhir init — scaffold a dockerized SUSHI IG project, offline.
set -euo pipefail

# One command writes the whole project: fhir.toml (the committed config), sushi-config.yaml,
# ig.ini, fsh.ini, a hand-authored aliases.fsh stub and index.md, pyproject.toml pinning the
# d2w toolchain, a Makefile driving it, a Dockerfile for the IG publisher, and .gitignore.
# Offline - the selection UIDs and the profile name are written as given, never checked
# against an instance, so a project scaffolds on a plane.
#
# The flags shown are the identity and the selection dials:
#   --id / --canonical / --name / --title / --publisher   the IG's identity
#   --status          draft (the default) or active, driven onto every generated artifact
#   --profile         seeds the `profile` key, so later commands need no -p
#   --data-set / --event-program / --tracker-program      seed the selection tables (repeatable)
#   --max-level       caps the organisation-unit registry depth - the build wall-clock dial
#   --sushi-timeout   the ceiling the IG publisher gives its embedded SUSHI run
d2w fhir init demo-init \
    --id dhis2.fhir.initdemo \
    --canonical http://example.org/fhir/init-demo \
    --publisher "Demo Org" \
    --data-set BfMAe6Itzgt \
    --max-level 2

# What landed: the twelve scaffold files, fhir.toml carrying the seeded selection.
ls demo-init
grep -A2 "generate.data_sets" demo-init/fhir.toml

rm -rf demo-init
