#!/usr/bin/env bash
#
# One-shot foreground DHIS2 runner:
#   1. start stack detached (so we can run the seed against a live instance)
#   2. block until /api/me responds
#   3. mint PATs + OAuth2 client into infra/home/credentials/.env.auth
#   4. stream logs — feels foreground
#   5. trap Ctrl+C so it tears the stack down on exit (no orphan containers)

set -euo pipefail

DHIS2_VERSION="${DHIS2_VERSION:-43}"
DHIS2_URL="${DHIS2_URL:-http://localhost:8080}"
DHIS2_USER="${DHIS2_USER:-admin}"
DHIS2_PASS="${DHIS2_PASS:-district}"

# Resolve `DHIS2_IMAGE_TAG` (the actual Docker tag) from `DHIS2_VERSION` (the
# minor key) via `infra/versions.env`. Compose reads `DHIS2_IMAGE_TAG` for the
# image and `DHIS2_VERSION` for the dump-path lookup.
# shellcheck source=_resolve_image_tag.sh
. "$(dirname "$0")/_resolve_image_tag.sh"

cd "$(dirname "$0")/.."
INFRA_DIR="$(pwd)"
COMPOSE=(docker compose -f compose.yml -f compose.pgadmin.yml)

cleanup() {
  echo
  echo ">>> Stopping DHIS2 stack ..."
  (cd "$INFRA_DIR" && DHIS2_VERSION="$DHIS2_VERSION" DHIS2_IMAGE_TAG="$DHIS2_IMAGE_TAG" "${COMPOSE[@]}" down)
}
trap cleanup INT TERM

# Wipe any prior volume first: a version switch must not boot a different major's DB (Flyway
# rejects the unknown migrations). The seeded dump reloads on the fresh volume — this is the
# documented "data resets on every make dhis2-run" behaviour.
echo ">>> Resetting volumes for a clean v$DHIS2_VERSION boot ..."
DHIS2_VERSION="$DHIS2_VERSION" DHIS2_IMAGE_TAG="$DHIS2_IMAGE_TAG" "${COMPOSE[@]}" down -v --remove-orphans
echo ">>> Starting DHIS2 v$DHIS2_VERSION (image dhis2/core:$DHIS2_IMAGE_TAG) — detached ..."
DHIS2_VERSION="$DHIS2_VERSION" DHIS2_IMAGE_TAG="$DHIS2_IMAGE_TAG" "${COMPOSE[@]}" up -d --remove-orphans

echo ">>> Waiting for DHIS2 readiness ..."
make -C "$INFRA_DIR" wait DHIS2_URL="$DHIS2_URL" DHIS2_USER="$DHIS2_USER" DHIS2_PASS="$DHIS2_PASS"

echo ">>> Seeding PATs + OAuth2 client ..."
make -C "$INFRA_DIR" seed DHIS2_URL="$DHIS2_URL" DHIS2_USER="$DHIS2_USER" DHIS2_PASS="$DHIS2_PASS"

echo ">>> Writing local_basic profile ..."
make -C "$INFRA_DIR" profile DHIS2_VERSION="$DHIS2_VERSION" DHIS2_URL="$DHIS2_URL" DHIS2_USER="$DHIS2_USER" DHIS2_PASS="$DHIS2_PASS"

echo ">>> Waiting for analytics tables to finish building (analytics-trigger) ..."
# The analytics-trigger sidecar fires POST /api/resourceTables/analytics and polls the task to
# completion ("Analytics tables completed successfully!"). On a fresh volume that work is async, so
# block on it here — otherwise verify-examples (and any post-Ready automation) races a stack whose
# analytics tables are still empty, and every analytics-backed example fails. Same trigger as the
# dhis2-docker stack; this just waits for it. Applies to every version (this script is version-agnostic).
_analytics_ready=0
for _ in $(seq 1 150); do
  if docker logs analytics-trigger 2>&1 | grep -q "Analytics tables completed successfully"; then
    _analytics_ready=1
    break
  fi
  if docker logs analytics-trigger 2>&1 | grep -q "Analytics failed!"; then
    break
  fi
  sleep 6
done
if [ "$_analytics_ready" = "1" ]; then
  echo ">>> Analytics tables ready."
else
  echo ">>> WARNING: analytics tables did not complete — analytics-backed examples/tests may fail."
fi

echo ">>> Ready. Streaming logs (Ctrl+C to stop the stack)."
DHIS2_VERSION="$DHIS2_VERSION" DHIS2_IMAGE_TAG="$DHIS2_IMAGE_TAG" "${COMPOSE[@]}" logs -f dhis2 postgresql analytics-trigger
