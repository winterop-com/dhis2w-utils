#!/usr/bin/env bash
# d2ql basics — the shape of a query: a source, a pipe `|`, and stages.
#
# A d2ql program is read left to right: a SOURCE (here a DHIS2 resource name)
# feeds a chain of STAGES separated by `|`. Run one with `d2w query eval '<program>'`.
# Global flags go before the command: `d2w --profile play42 --json query eval ...`.
set -euo pipefail

# The simplest program: a resource on its own returns rows (cap with `limit`).
d2w query eval 'dataElements | limit 5'

# `select` projects columns; name a column with `as`.
d2w query eval 'dataElements | select id, name as label | limit 5'

# `count` collapses the stream to a single number (a scalar result).
d2w query eval 'dataElements | count'

# `skip` then `limit` pages through results (offset then take).
d2w query eval 'dataElements | select id, name | skip 50 | limit 5'

# `order` sorts; add `desc` to reverse. Multiple keys are comma-separated.
d2w query eval 'dataElements | select id, name | order name asc | limit 5'

# `d2w query ast` shows how a program parses (offline — no server needed).
d2w query ast 'dataElements | select id, name | limit 5'
