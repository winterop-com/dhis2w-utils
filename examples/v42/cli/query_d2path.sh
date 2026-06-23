#!/usr/bin/env bash
# d2path — the expression language, evaluated over a local JSON document.
#
# d2path is what goes inside where/select/transform, but you can run a bare
# expression against any JSON with `d2w query d2path '<expr>' --input <file>`
# (offline — no profile needed). It is FHIRPath/JSONPath-compatible and uses
# collection semantics: every expression yields a list, and navigation flattens.
set -euo pipefail

doc="$(mktemp /tmp/patient-XXXXXX.json)"
cat > "$doc" <<'JSON'
{
  "resourceType": "Patient",
  "active": true,
  "gender": "male",
  "name": [
    { "use": "official", "given": ["Ada", "Lovelace"], "family": "King" },
    { "use": "nick", "given": ["Countess"] }
  ],
  "telecom": [ { "system": "phone", "value": "555-0100" }, { "system": "email", "value": "ada@x.org" } ]
}
JSON

# Navigation + filtering a repeating element.
d2w query d2path 'name.where(use = "official").family' --input "$doc"
d2w query d2path 'name.given.first()' --input "$doc"
d2w query d2path 'name.given.count()' --input "$doc"

# Operators and booleans.
d2w query d2path 'gender = "male" and active = true' --input "$doc"
d2w query d2path 'gender in ["male", "female"]' --input "$doc"
d2w query d2path '(1 + 2) * 3' --input "$doc"

# Functions: strings, conditionals, joins.
d2w query d2path 'name.where(use = "official").family.upper()' --input "$doc"
d2w query d2path 'iif(gender = "male", "M", "F")' --input "$doc"
d2w query d2path 'name.given.join(" ")' --input "$doc"
d2w query d2path 'telecom.where(system = "phone").value' --input "$doc"

rm -f "$doc"
