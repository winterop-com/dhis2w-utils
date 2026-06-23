#!/usr/bin/env bash
# Run the committed d2ql program library (examples/d2ql/*.d2ql) via `d2w query run`.
#
# The programs are standalone, version-agnostic .d2ql files — keep your real
# queries in files like these under version control and run them the same way.
# This thin runner is what `make verify-examples` executes; the programs
# themselves are documented in examples/d2ql/README.md.
set -euo pipefail

for program in examples/d2ql/*.d2ql; do
  echo "### $program"
  d2w query run "$program"
done

# Inspect a program without running it (offline):
d2w query ast "$(cat examples/d2ql/immunisation-library.d2ql)"
d2w query explain "$(cat examples/d2ql/analytics-rollup.d2ql)"
