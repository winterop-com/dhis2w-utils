#!/usr/bin/env bash
# Refuse to start a DHIS2 major against a postgres volume another major migrated.
#
# `make down` keeps volumes, so `down` + `up DHIS2_VERSION=<other>` leaves the
# previous major's schema in place. DHIS2 then fails Flyway validation
# ("Detected applied migration not resolved locally"), the Spring context never
# builds, and the container still reports healthy while every request 404s -
# a failure that looks like anything except a schema mismatch.
#
# The last major to run is recorded beside the volume. Mismatch is a hard stop
# pointing at `up-fresh`, which wipes volumes and is the correct way to switch.
set -euo pipefail

requested="${1:?usage: _check_volume_major.sh <vXX>}"
stamp_directory="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/home"
stamp="${stamp_directory}/.volume-major"

mkdir -p "${stamp_directory}"

if [[ -f "${stamp}" ]]; then
    recorded="$(cat "${stamp}")"
    if [[ "${recorded}" != "${requested}" ]]; then
        cat >&2 <<MESSAGE
ERROR: the postgres volume holds a ${recorded} database, and you asked for ${requested}.

DHIS2 refuses to start against a schema another major migrated: Flyway reports
"Detected applied migration not resolved locally", the app context fails, and the
container reports healthy while every request answers 404.

Switch majors with a volume wipe instead:

    make -C infra up-fresh DHIS2_VERSION=${requested}

Or return to ${recorded}:

    make -C infra up DHIS2_VERSION=${recorded}
MESSAGE
        exit 1
    fi
fi

printf '%s' "${requested}" > "${stamp}"
