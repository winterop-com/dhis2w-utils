#!/usr/bin/env bash
# Export a profile's connection settings into the shell as DHIS2_* env vars.
# `d2w profile env` prints `export DHIS2_...` lines (values as-is, including the
# password/token — it's already plaintext in .dhis2/profiles.toml). The command
# only prints to stdout; it cannot change your shell directly. Either copy-paste
# the lines you want or `eval` them. The emitted DHIS2_VERSION is the profile's
# version pin (which major's plugin tree the CLI/MCP binds); the wire client
# still auto-detects on connect. For a redacted view, use `d2w profile show`.
set -euo pipefail

# Print the export lines for the active profile.
d2w profile env

# Load them into a subshell via eval, then list which DHIS2_* vars got set:
( eval "$(d2w profile env)"; env | grep -o '^DHIS2_[A-Z_]*' | sort )

# Target a specific profile by name instead of the active default:
# d2w profile env local_basic
