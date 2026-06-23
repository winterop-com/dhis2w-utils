#!/usr/bin/env bash
# d2ql definitions + sinks — reusable libraries and writing results to files.
#
# A program may begin with `define`s, turning a `.d2ql` file into a reusable
# library. Reference a scalar define or a function parameter with the `$` sigil;
# `$this` is the current row inside where/select/transform. End a pipeline with
# `>>` to write the result (format inferred from the extension).
set -euo pipefail

# A scalar define, referenced as `$Name`.
d2w query eval 'define MinLevel: 3
organisationUnits | where level >= $MinLevel | select name, level | limit 5'

# A function: parameters are read as `$param` in the body.
d2w query eval 'define function isAnc(de): $de.name like "ANC"
dataElements | where isAnc($this) | select name | limit 5'

# A named query used as a source, plus a function — composed.
d2w query eval 'define Aggregates: dataElements | where domainType = "AGGREGATE"
define function isImmunisation(de): $de.name like "BCG" or $de.name like "measles" or $de.name like "Penta"
Aggregates | where isImmunisation($this) | select id, name | limit 5'

# Sinks: write the result instead of returning it (csv / json / ndjson).
d2w query eval 'dataElements | select id, name >> "/tmp/elements.csv"'
d2w query eval 'dataElements | where domainType = "AGGREGATE" | transform { code: id, label: name } >> "/tmp/aggregates.json"'
d2w query eval 'dataElements | select id, name >> "/tmp/elements.ndjson"'

# `--out FILE` is the CLI equivalent of an in-program sink.
d2w query eval 'dataElements | select id, name | limit 100' --out /tmp/sample.csv
