#!/usr/bin/env bash
# `d2w metadata category-combos build` — one-pass create-or-reuse for the
# full Category dimension stack. Idempotent; re-running the same spec is
# a no-op modulo new options getting wired into existing categories.
# Run via `uv run bash examples/v43/cli/category_combo_build.sh` so `d2w` resolves.
set -euo pipefail

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
SPEC="$TMP/spec.json"

# A small disaggregation: Sex (2 options) x Modality (3 options) = 6 COCs.
cat >"$SPEC" <<'EOF'
{
    "name": "DemoSexModality",
    "code": "DEMO_SEX_MOD",
    "data_dimension_type": "DISAGGREGATION",
    "skip_total": false,
    "categories": [
        {
            "name": "DemoSex",
            "short_name": "DemoSex",
            "options": [
                {"name": "DemoMale", "short_name": "DemoM"},
                {"name": "DemoFemale", "short_name": "DemoF"}
            ]
        },
        {
            "name": "DemoModality",
            "short_name": "DemoMod",
            "options": [
                {"name": "DemoInpatient"},
                {"name": "DemoOutpatient"},
                {"name": "DemoOutreach"}
            ]
        }
    ]
}
EOF

# Build (or reuse) the stack, polling for the COC matrix.
d2w metadata category-combos build --spec "$SPEC"

# Re-running the same spec should be idempotent — every entry reused, no creates.
d2w metadata category-combos build --spec "$SPEC"

# JSON output carries every UID + a created-vs-reused breakdown for downstream tooling.
d2w --json metadata category-combos build --spec "$SPEC" | jq '.combo_uid, .coc_count'

# Stdin form — handy when generating the spec from another tool:
# python tools/generate_dimension_spec.py | d2w metadata category-combos build --spec -
