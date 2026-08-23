#!/usr/bin/env bash
# d2w fhir doctor — the drift phase: has the instance moved past the guide you published?
# Needs the serve extra and docker for the compile phase; minutes per run, so
# `make verify-examples` skips it for the same reasons it skips doctor.sh.
set -euo pipefail

# The drift phase is the one phase whose subject is not the throwaway project doctor
# scaffolds. Run doctor from a directory a fhir.toml sits in or above, and it reads the
# artifacts that project already published - the same trees `d2w fhir serve` and
# `d2w fhir check-artifacts` read - and asks the instance for everything they claim.
#
# Five classes, each in both directions and on renames alike: organisation units inside
# the registry scope, options in published option sets, tracked entity attributes on
# registration forms, data elements on data set and stage forms, and program stages a
# tracker program grew that publish no form. Everything is measured inside the project's
# own selection - an organisation unit outside [generate.organisation_units] is not drift,
# because the project never asked for it.
#
# Drift is warning-class and never exits 1: a guide describing the instance as it stood
# last month still serves, still captures, and still forwards. It is out of date, and the
# remedy is stated once on the phase rather than once per row - regenerate, then compile.
cd my-guide
d2w fhir doctor

# Zero drift is one quiet line, and the phase passes:
#   drift  pass  the guide publishes the instance as it now stands: 16 organisation
#   unit(s), 12 option set(s), and 6 form(s) read against the hierarchy under
#   O6uvpzGd5pu down to level 3
#
# Run from anywhere else the phase is skipped with that as its reason, because a project
# doctor generated seconds ago can only agree with the instance.
