#!/usr/bin/env bash
# Simplest possible dhis2 CLI invocation — who am I, and what version is the server?
# Assumes `dhis2 profile add local --default` has been run (or DHIS2_URL + DHIS2_PAT are in env).
set -euo pipefail

dhis2 system whoami
dhis2 system info

# Add -d / --debug to see every HTTP request the CLI makes (method, URL, status,
# bytes, ms). Debug output is stderr — stdout stays clean for piping.
dhis2 -d system whoami

# Read system settings (read-only) — one key by name, then the full snapshot.
dhis2 system settings get applicationTitle
dhis2 system settings list
