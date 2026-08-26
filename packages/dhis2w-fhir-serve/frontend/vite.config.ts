import fs from 'node:fs'
import path from 'node:path'
import { defineConfig, type Plugin } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// The bundle is served by `d2w fhir serve --ui`, same-origin, off the FastAPI app
// itself - so it builds straight into the Python package at
// src/dhis2w_fhir_serve/static/ and ships inside the wheel.
//
// That directory is gitignored: this workspace publishes wheels from CI, which
// runs `make build-frontend` before packaging. A committed bundle would only be
// a second copy of the same bytes, going stale between rebuilds.
//
// The dev server proxies every guarded FHIR path to a running `d2w fhir serve`,
// so the UI in dev talks to the same routes it will talk to in production. The
// list is the router table of dhis2w_fhir_serve.routes, not a guess: /metadata
// plus the resource types the read catch-alls answer for. The register serves
// as many resource types as a published D2TET_CM names, so a project serving one
// this list omits adds it here for its own dev server - production needs no such
// list, since the server owns every path ahead of the static mount.
//
// `base: './'` would break nothing here, but '/' is what the server mounts at
// and keeps asset URLs stable however deep a hash route goes.
const target = process.env.VITE_SERVE_TARGET ?? 'http://127.0.0.1:8080'
const proxiedPaths = [
    '/metadata',
    '/spool',
    '/uiconfig',
    '/whoami',
    '/tracked-entities',
    '/evaluate',
    '/$evaluate',
    '/terminology',
    '/cds-services',
    '/Patient',
    '/Specimen',
    '/Questionnaire',
    '/QuestionnaireResponse',
    '/CodeSystem',
    '/ValueSet',
    '/ConceptMap',
    '/Location',
    '/Organization',
    '/List',
]
const proxy = Object.fromEntries(proxiedPaths.map((prefix) => [prefix, { target, changeOrigin: true }]))

const outputDirectory = path.resolve(__dirname, '../src/dhis2w_fhir_serve/static')

/**
 * Put the .gitkeep back after the build wipes the output directory.
 *
 * `emptyOutDir` deletes everything under static/, dotfiles included, so the
 * marker that keeps the directory present in a fresh checkout has to be
 * rewritten by whoever emptied it. Doing it here rather than in the Makefile
 * means `pnpm build` alone leaves a consistent tree, however it was invoked.
 */
function keepOutputDirectory(): Plugin {
    return {
        name: 'keep-output-directory',
        closeBundle() {
            fs.writeFileSync(path.join(outputDirectory, '.gitkeep'), '')
        },
    }
}

export default defineConfig({
    base: '/',
    plugins: [react(), tailwindcss(), keepOutputDirectory()],
    resolve: {
        alias: {
            '@': path.resolve(__dirname, './src'),
        },
    },
    server: { proxy },
    build: {
        outDir: outputDirectory,
        emptyOutDir: true,
    },
})
