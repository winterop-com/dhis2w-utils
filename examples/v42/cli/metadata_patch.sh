#!/usr/bin/env bash
# `d2w metadata patch` — apply RFC 6902 JSON Patch ops to a single metadata object.
#
# DHIS2 supports PATCH on every metadata resource. Targeted partial updates are
# much lighter than round-tripping the full object via PUT — and the
# discriminated `JsonPatchOp` union catches wrong-shape ops at construction time.
set -euo pipefail

# Pick any dataElement UID from the seeded fixture.
target_uid=$(uv run d2w --json metadata list dataElements --page-size 1 | python3 -c "import json,sys; print(json.load(sys.stdin)[0]['id'])")
echo "--- target: dataElements/$target_uid"
uv run d2w --json metadata get dataElements "$target_uid" | python3 -c "import json,sys; d=json.load(sys.stdin); print(f'current: name={d.get(\"name\")!r}, description={d.get(\"description\", \"(none)\")!r}')"

echo ""
echo "=== 1. Inline --set: replace description (JSON values decode automatically)"
uv run d2w metadata patch dataElements "$target_uid" --set '/description=Updated via CLI'

echo ""
echo "=== 2. Inline --set with boolean value (JSON-decoded: true, not 'true')"
uv run d2w metadata patch dataElements "$target_uid" --set '/zeroIsSignificant=false'

echo ""
echo "=== 3. Inline --remove: drop a field"
uv run d2w metadata patch dataElements "$target_uid" --remove '/description'

echo ""
echo "=== 4. Multiple ops in one call (--set + --remove combine into one patch array)"
uv run d2w metadata patch dataElements "$target_uid" \
    --set '/description=Multi-op patch' \
    --set '/shortName=Penta1-M'

echo ""
echo "=== 5. File-based patch — full RFC 6902 shape, every op type available"
cat > /tmp/patch_ops.json <<'JSON'
[
  {"op": "replace", "path": "/description", "value": "File-based patch"},
  {"op": "add", "path": "/code", "value": "DE_PENTA_1"}
]
JSON
uv run d2w metadata patch dataElements "$target_uid" --file /tmp/patch_ops.json

echo ""
echo "=== 6. Revert everything"
uv run d2w metadata patch dataElements "$target_uid" \
    --set '/description=Penta1 doses given' \
    --set '/shortName=PENTA1' \
    --remove '/code'

echo ""
echo "--- final state:"
uv run d2w --json metadata get dataElements "$target_uid" | python3 -c "import json,sys; d=json.load(sys.stdin); print(f'name={d.get(\"name\")!r}, shortName={d.get(\"shortName\")!r}, description={d.get(\"description\", \"(none)\")!r}')"
