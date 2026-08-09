import { fileURLToPath } from 'node:url'

import { defineConfig } from 'vitest/config'

/**
 * Unit tests run in plain Node.
 *
 * What is under test here is the wire layer - the guarded-path regex, the api
 * configuration seam, and the narrow FHIR shapes lib/fhir.ts reads - and none of
 * it needs a DOM. `fetch` is native in Node, so `apiFetch` is exercised for real
 * against a stubbed global rather than through a browser emulation.
 *
 * Deliberately separate from vite.config.ts so tests do not load the React and
 * Tailwind plugins.
 */
export default defineConfig({
    resolve: {
        alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
    },
    test: {
        environment: 'node',
        include: ['src/**/*.test.ts'],
    },
})
