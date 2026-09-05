# Use official PostGIS image as base — includes PostgreSQL + spatial extensions.
# postgis/postgis publishes 17-3.5 as linux/amd64 only; the amd64 build target
# is set via compose's build.platforms so buildx pulls the right manifest on
# arm64 hosts without a hardcoded --platform here (which buildx now lints).
# The 3.5 line ships only on Debian 11 (bullseye) or Alpine: there is no
# bookworm/trixie Debian tag, and Alpine has no apt, so bullseye it is.
FROM postgis/postgis:17-3.5

# Install wal2json (logical decoding / CDC) and python3-bcrypt (used by
# initdb.sh to hash DHIS2 user passwords).
#
# Deliberately no blanket `apt-get upgrade`: bullseye's index advertises
# package versions its security pool no longer serves, so a full upgrade
# exits 100 on 404s for libperl5.32, tzdata and xz-utils. Installing exactly
# the two packages the stack needs keeps the build reproducible on a machine
# with no cached image layers.
RUN DEBIAN_FRONTEND=noninteractive apt-get update -y && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        postgresql-17-wal2json \
        python3-bcrypt && \
    apt-get clean && rm -rf /var/lib/apt/lists/*
