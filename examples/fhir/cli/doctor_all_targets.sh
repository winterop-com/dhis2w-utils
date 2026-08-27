#!/usr/bin/env bash
# d2w fhir doctor --all-targets — the same chain over everything the instance holds.
# Needs the serve extra and docker for the compile phase; slower per run than the default probe,
# so `make verify-examples` skips it for the same reasons it skips doctor_probe.sh.
set -euo pipefail

# The default probe scaffolds a selection: the first data set, the first event program, the
# first tracker program, and the subtree those forms are assigned inside. --all-targets
# scaffolds the selection tables empty instead, and an absent table takes everything of its
# kind - every data set, every program, every organisation-unit level. Correspondingly slower,
# and what you want before committing to a real project: the phases then judge the whole
# instance rather than the corner of it a probe happened to land on.
workspace="$(mktemp -d)"
trap 'rm -rf "${workspace}"' EXIT
cd "${workspace}"

d2w fhir doctor --all-targets
