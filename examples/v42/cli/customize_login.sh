#!/usr/bin/env bash
# `d2w customize` — brand the DHIS2 login page + top menu.
# Run via `uv run bash examples/v42/cli/customize_login.sh` so the `d2w` entry resolves.
set -euo pipefail

# Read-only: what does the instance currently advertise?
d2w customize show

# Apply everything in infra/login-customization/ (logos + preset.json) in one call.
d2w customize apply infra/login-customization/

# Individual knobs — same effect, finer-grained.
d2w customize logo-front  infra/login-customization/logo_front.png
d2w customize logo-banner infra/login-customization/logo_banner.png

# Tweak specific strings without touching preset.json.
d2w system settings set applicationTitle "dhis2-utils local"
d2w system settings set keyApplicationIntro "Seeded fixture — admin / district credentials."
d2w system settings set keyApplicationNotification "Development instance. Don't reuse credentials."
d2w system settings set keyApplicationFooter "Powered by dhis2-utils"

# Drop a stylesheet for the authenticated UI (login app ignores /api/files/style —
# post-auth pages serve it). Uncomment when you have a theme to apply.
# d2w customize style path/to/my-theme.css

# JSON dump of /api/loginConfig — useful for asserting applied state in CI.
d2w --json customize show | head -20
