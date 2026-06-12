#!/usr/bin/env bash
# `d2w files` — documents (/api/documents) + file resources (/api/fileResources).
# Covers: external-URL document, binary document upload + download + delete,
# and a standalone fileResource round-trip (the shape data-element images or
# event photos use).
#
# Run via `uv run bash examples/v42/cli/files.sh` so `d2w` resolves. Requires a
# seeded local stack (`make dhis2-run`).

set -euo pipefail

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

# --- documents ---------------------------------------------------------------

# 1. External URL document — no bytes, DHIS2 just stores the link.
d2w files documents upload-url "Workspace README" "https://github.com/winterop-com/dhis2-utils"

# 2. Binary document — workspace drives a two-step under the hood (see BUGS.md #16):
#    upload as fileResource(domain=DOCUMENT), then POST /api/documents with url=<uid>.
echo "hello dhis2" > "$TMP/hello.txt"
UPLOAD=$(d2w files documents upload "$TMP/hello.txt" --name "files-example-readme")
echo "$UPLOAD"
DOC_UID=$(echo "$UPLOAD" | awk '/^uploaded/ {print $2}')

# 3. List only the one we just added.
d2w files documents list --filter "name:eq:files-example-readme"

# 4. Round-trip the bytes through the download endpoint.
d2w files documents download "$DOC_UID" "$TMP/rt.txt"
diff "$TMP/hello.txt" "$TMP/rt.txt" && echo "document bytes match"

# 5. Clean up.
d2w files documents delete "$DOC_UID"

# --- file resources ----------------------------------------------------------

# 1. Upload bytes as a DATA_VALUE fileResource — the shape a file-type data
#    element capture uses. The returned UID is what you'd stamp on the data
#    value; DHIS2 binds the file to the capture event at that point.
printf 'P1\n1 1\n1\n' > "$TMP/pixel.pbm"
DV_UPLOAD=$(d2w files resources upload "$TMP/pixel.pbm" --domain DATA_VALUE)
echo "$DV_UPLOAD"
DV_UID=$(echo "$DV_UPLOAD" | awk '/^uploaded/ {print $2}')

# 2. Metadata read comes back typed (contentType, contentLength, storageStatus).
d2w files resources get "$DV_UID"

# Notes on domains:
# - DATA_VALUE fileResources are only downloadable via the owning DataValue
#   (through /api/dataValueSets/...), not through /api/fileResources/{uid}/data.
#   Calling `d2w files resources download` on one returns 403.
# - ICON re-encodes the upload (DHIS2 generates thumbnails), so the download
#   bytes don't match the upload bytes — use a hash-of-visual-content compare
#   instead of byte-diff when verifying ICON round-trips.
# - MESSAGE_ATTACHMENT passes bytes through unchanged — the cleanest round-trip
#   demo for a standalone fileResource:
echo "message attachment demo" > "$TMP/attach.txt"
MA_UPLOAD=$(d2w files resources upload "$TMP/attach.txt" --domain MESSAGE_ATTACHMENT)
MA_UID=$(echo "$MA_UPLOAD" | awk '/^uploaded/ {print $2}')
d2w files resources download "$MA_UID" "$TMP/attach_rt.txt"
diff "$TMP/attach.txt" "$TMP/attach_rt.txt" && echo "MESSAGE_ATTACHMENT fileResource bytes match"

# fileResources aren't typically deleted directly — DHIS2 reference-counts
# them and cleans unreferenced blobs on its own schedule.
