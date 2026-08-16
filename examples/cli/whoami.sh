#!/usr/bin/env bash
# Simplest possible d2w CLI invocation — who am I, and what version is the server?
# Assumes `d2w profile add local --default` has been run (or DHIS2_URL + DHIS2_PAT are in env).
set -euo pipefail

d2w system whoami
d2w system info

# Add -d / --debug to see every HTTP request the CLI makes (method, URL, status,
# bytes, ms). Debug output is stderr — stdout stays clean for piping.
d2w -d system whoami

# Read system settings (read-only) — one key by name, then the full snapshot.
d2w system settings get applicationTitle
d2w system settings list
