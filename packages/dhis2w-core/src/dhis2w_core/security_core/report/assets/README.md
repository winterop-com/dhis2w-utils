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

## Provenance gap for support.js (ACTION REQUIRED)

`support.js` is a generated, minified bundle. Its first line declares:

```
// GENERATED from dc-runtime/src/*.ts — do not edit. Rebuild with `cd dc-runtime && bun run build`.
```

The TypeScript source it is generated from, `dc-runtime/src/*.ts` and the
`dc-runtime` build project (a `bun` build), is not checked into this repository.
It is absent from the working tree and from every git ref: a filesystem search of
the developer roots and `git log -S 'dc-runtime'` / `git log -- '**/dc-runtime/**'`
across all branches find only the generated bundle, never the source or a build
script.

Consequence: the report's client-side rendering and escaping layer cannot be
rebuilt or audited from source in this repository. The bundle is an opaque
artifact. For a security tool, the code that renders server-supplied strings into
the browser is exactly the code a reviewer needs to read in source form.

To close the gap:

1. Commit the `dc-runtime` sources (`dc-runtime/src/*.ts`, its `package.json`,
   and the `bun` build configuration) into the repository.
2. Add a documented make target, for example `make security-report-runtime`,
   that runs the `bun run build` step and reproduces `support.js` so the bundle
   can be regenerated and verified byte for byte from the checked-in source.
3. Document the build in the report subpackage docs so the toolchain
   (`bun`) and the rebuild command are discoverable.

## Sibling assets

The sharing explorer assets in `../../sharing/assets/` do not have this gap:

- `sharing-runtime.js` is hand-maintained vanilla JavaScript with its source
  header comment in place. No separate build source is required.
- `d3.min.js` is the vendored d3 library (d3js.org v7.9.0), a third-party
  distribution used as-is.
