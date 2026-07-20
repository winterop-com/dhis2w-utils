# Security report assets

Author: Morten Svanaes

This directory holds the static assets bundled into the standalone HTML security
report produced by the `security_core` report renderer.

## Files

- `report.dc.html`: the report template shell.
- `dhis2-logo.png`: the DHIS2 logo used in the report header.
- `support.js`: the client-side runtime that renders the report. It turns
  server-supplied finding data into DOM, and holds the client-side
  HTML-escaping and text-building logic for the report UI.

## support.js is hand-maintained

`support.js` is hand-maintained vanilla JavaScript, the same status as
`sharing-runtime.js` in the sibling `../../sharing/assets/` directory: this
file IS the source, edited directly, with no build step and no external
toolchain required. Its header comment documents the same convention.

## DHIS2 logo trademark note

"DHIS2" and the DHIS2 logo are trademarks of the University of Oslo (HISP).
`dhis2-logo.png` is used here to identify the DHIS2 instance the report was
generated from; this is not an endorsement by, or affiliation with, the DHIS2
project or the University of Oslo.

`dhis2-logo.png` in this directory is an intentional byte-identical copy of
`../../sharing/assets/dhis2-logo.png` (same source asset, bundled separately
because the report and the sharing explorer are independent, self-contained
HTML bundles copied into the run folder). Do not replace either copy with a
symlink: each bundle must stay self-contained and portable on its own.

## Sibling assets

The sharing explorer assets in `../../sharing/assets/` follow the same
hand-maintained convention:

- `sharing-runtime.js` is hand-maintained vanilla JavaScript with its source
  header comment in place. No separate build source is required.
- `d3.min.js` is the vendored d3 library (d3js.org v7.9.0), a third-party
  distribution used as-is.
