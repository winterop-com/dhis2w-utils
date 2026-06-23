#!/usr/bin/env bash
# d2ql for organisation units — hierarchy, associations, and GeoJSON geometry.
#
# Org units are a tree (level/path/parent) and carry an embedded GeoJSON
# `geometry` object. Geometry is passed through as an opaque object; nested
# geometry paths are NOT DHIS2 filter properties, so those predicates run
# locally (see BUGS.md #45) — `d2w query explain` shows this.
set -euo pipefail

# Walk the hierarchy by level; navigate the parent association.
d2w query eval 'organisationUnits | where level = 2 | select id, name, parent.name as parent | order name asc | limit 5'

# Everything under a root org unit (its UID is in every descendant's path).
d2w query eval 'organisationUnits | where path like "/ImspTQPwCqd" | select name, level | limit 5'

# Count facilities per level.
d2w query eval 'organisationUnits | group by level { facilities: count() } | order level asc'

# Pass the whole GeoJSON geometry through unchanged.
d2w query eval 'organisationUnits | where level = 2 | transform { id: id, name: name, geometry: geometry } | limit 2'

# Filter by geometry type — runs locally (nested geometry path is not pushed down).
d2w query explain 'organisationUnits | where geometry.type = "Point" | select id, name'

# Reshape org units into GeoJSON Features and write a file.
d2w query eval 'organisationUnits | where level = 2 and geometry.type = "Polygon" | transform { type: "Feature", properties: { name: name, level: level }, geometry: geometry } >> "/tmp/districts.json"'
