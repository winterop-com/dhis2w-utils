#!/usr/bin/env bash
# `d2w apps ...` — install / uninstall / update DHIS2 apps via /api/apps
# and the configured App Hub (/api/appHub). DHIS2 v42's Spring AS handles
# the install side; App Hub is a read-only catalog proxy.
#
# Installed apps fall into two buckets the plugin cares about:
#   - App Hub apps (`app_hub_id` set) — the main target of `update`.
#     Includes bundled core apps (Reports, Cache Cleaner, Data Visualizer,
#     etc.) — DHIS2 lets the App Hub overwrite the bundled copy in place.
#   - Side-loaded zips (no `app_hub_id`) — SKIPPED by `update --all`,
#     reinstall by running `d2w apps add path/to/file.zip`.
set -euo pipefail

# ---------------------------------------------------------------------------
# List + inspect
# ---------------------------------------------------------------------------

d2w apps list
# `ls` is a hidden alias:
#   d2w apps ls

# Machine-readable variant for scripting.
d2w --json apps list | head

# ---------------------------------------------------------------------------
# App Hub
# ---------------------------------------------------------------------------

# The configured App Hub catalog (proxied server-side). Each row carries
# a top-level `id` (the app id) and a `versions` list whose ids are version
# ids — both are bare UUIDs and easy to confuse (see BUGS.md #46).
d2w apps hub-list --limit 5

# Install from the App Hub (shown as comments — substitute a real id). `add`
# accepts either kind of id: a version id installs that exact version; an app
# id resolves to the app's latest version.
#   d2w apps add <version-id>          # install a specific version
#   d2w apps add <app-id>             # install the app's latest version

# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------

# Preview mode: show which installed apps have a newer version on the App
# Hub without actually installing anything. Re-run without --dry-run to
# apply the updates.
d2w apps update --all --dry-run

# Update every installed app that has a newer App Hub version. Side-loaded
# zips (no `app_hub_id`) are reported as SKIPPED; bundled core apps update
# in place.
d2w apps update --all

# ---------------------------------------------------------------------------
# Reload (no new fetch — re-read every app from disk)
# ---------------------------------------------------------------------------

d2w apps reload
