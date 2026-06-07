#!/usr/bin/env bash
# `dhis2 customize` — brand the DHIS2 login page + top menu.
# Run via `uv run bash examples/v43/cli/customize_login.sh` so the `dhis2` entry resolves.
set -euo pipefail

# Read-only: what does the instance currently advertise?
dhis2 customize show

# Apply everything in infra/login-customization/ (logos + preset.json) in one call.
dhis2 customize apply infra/login-customization/

# Individual knobs — same effect, finer-grained.
dhis2 customize logo-front  infra/login-customization/logo_front.png
dhis2 customize logo-banner infra/login-customization/logo_banner.png

# Tweak specific strings without touching preset.json.
dhis2 system settings set applicationTitle "dhis2-utils local"
dhis2 system settings set keyApplicationIntro "Seeded fixture — admin / district credentials."
dhis2 system settings set keyApplicationNotification "Development instance. Don't reuse credentials."
dhis2 system settings set keyApplicationFooter "Powered by dhis2-utils"

# Drop a stylesheet for the authenticated UI (login app ignores /api/files/style —
# post-auth pages serve it). Uncomment when you have a theme to apply.
# dhis2 customize style path/to/my-theme.css

# JSON dump of /api/loginConfig — useful for asserting applied state in CI.
dhis2 --json customize show | head -20
