# Sharing explorer assets

Author: Morten Svanaes

This directory holds the static assets bundled into the standalone, offline
interactive sharing-graph explorer produced by `d2w security audit
--sharing-graph` (alias `--visualize`).

## Files

- `sharing-explorer.html`: the explorer template shell.
- `sharing-runtime.js`: the client-side runtime that renders the explorer. It
  turns the per-scan `window.__SHARING__` payload into the object tree,
  exposure triage, principal/role pivots, force-directed graph, and matrix
  heatmap views, and holds the client-side HTML-escaping and text-building
  logic for the explorer UI.
- `d3.min.js`: the vendored [d3.js](https://d3js.org) v7.9.0 library, a
  third-party distribution used as-is to drive the force-directed graph and
  matrix heatmap views.
- `dhis2-logo.png`: the DHIS2 logo used in the explorer header.

## sharing-runtime.js is hand-maintained

`sharing-runtime.js` is hand-maintained vanilla JavaScript, the same status as
`support.js` in the sibling `../../report/assets/` directory: this file IS the
source, edited directly, with no build step and no external toolchain
required.

## d3.min.js license (ISC)

`d3.min.js` is vendored unmodified from the official d3 v7.9.0 release
(https://d3js.org, https://github.com/d3/d3) and ships under the ISC license:

```
Copyright 2010-2023 Mike Bostock

Permission to use, copy, modify, and/or distribute this software for any purpose
with or without fee is hereby granted, provided that the above copyright notice
and this permission notice appear in all copies.

THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES WITH
REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF MERCHANTABILITY AND
FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY SPECIAL, DIRECT,
INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING FROM LOSS
OF USE, DATA OR PROFITS, WHETHER IN AN ACTION OF CONTRACT, NEGLIGENCE OR OTHER
TORTIOUS ACTION, ARISING OUT OF OR IN CONNECTION WITH THE USE OR PERFORMANCE OF
THIS SOFTWARE.
```

## DHIS2 logo trademark note

"DHIS2" and the DHIS2 logo are trademarks of the University of Oslo (HISP).
`dhis2-logo.png` is used here to identify the DHIS2 instance the explorer
scanned; this is not an endorsement by, or affiliation with, the DHIS2 project
or the University of Oslo.

`dhis2-logo.png` in this directory is an intentional byte-identical copy of
`../../report/assets/dhis2-logo.png` (same source asset, bundled separately
because the report and the explorer are independent, self-contained HTML
bundles copied into the run folder). Do not replace either copy with a
symlink: each bundle must stay self-contained and portable on its own.

## Sibling assets

The report assets in `../../report/assets/` follow the same hand-maintained
convention:

- `support.js` is hand-maintained vanilla JavaScript with its source header
  comment in place. No separate build source is required.
