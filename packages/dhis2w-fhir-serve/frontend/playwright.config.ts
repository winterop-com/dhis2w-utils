import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { defineConfig, devices } from '@playwright/test'

/**
 * The browser suite runs against a REAL `d2w fhir serve --ui`, not a mock.
 *
 * WHY. Everything this UI does depends on the router table of a FastAPI app that
 * mounts a SPA behind its own catch-all routes. A mocked API cannot fail the way
 * that arrangement fails - the interesting bug is `/assets/index-<hash>.js`
 * coming back as an OperationOutcome, or a path typo landing on the SPA shell
 * with a 200 - so the thing under test has to be the actual server serving the
 * actual bundle. The unit tests already cover everything a mock could.
 *
 * THE PORT IS ITS OWN. 8377 rather than the 8080 default: 8080 is where a local
 * DHIS2 stack lives on these machines, and an e2e run that fights it (or worse,
 * silently talks to it) is a bad afternoon. Nothing else in this workspace binds
 * 8377.
 *
 * TWO PREREQUISITES, NEITHER RUN AUTOMATICALLY.
 *
 *   pnpm build                        # the bundle `--ui` serves; without it the
 *                                     # server refuses to start, in one line
 *   pnpm exec playwright install chromium
 *
 * Both are deliberate: `pnpm build` writes into the Python package, and
 * downloading a browser is not something a test command should do behind
 * someone's back. `make e2e-frontend` documents the pair.
 *
 * THE FIXTURE PROJECT is written fresh by the webServer command, from the same
 * builder the pytest suite uses (`tests/fixture_project.py`) - so the IG the
 * browser sees is the IG the Python tests prove the capture path against, with
 * one copy of the goldens in the workspace. The spool is emptied on each run, so
 * "the Responses page shows the receipt" can only be true because this run
 * posted one.
 */

const here = path.dirname(fileURLToPath(import.meta.url))

/** The workspace root, from which `uv run` resolves the environment and the paths below. */
const repositoryRoot = path.resolve(here, '../../..')

/** Where the fixture IG project is written. Gitignored; regenerated on every run. */
const fixtureProject = 'packages/dhis2w-fhir-serve/frontend/e2e/.fixture-project'

/** The builder that writes it, run as a script rather than through pytest. */
const fixtureBuilder = 'packages/dhis2w-fhir-serve/tests/fixture_project.py'

/** The port the suite's own server binds. See the note above on why it is not 8080. */
export const E2E_PORT = 8377

export const E2E_BASE_URL = `http://127.0.0.1:${String(E2E_PORT)}`

export default defineConfig({
    testDir: './e2e',
    // ONE SERVER, ONE SPOOL, ONE WORKER. The suite drives a single
    // `d2w fhir serve --ui` process, and several specs assert on what is in its
    // spool - "the listing was empty before this run posted anything", "the
    // overview's Received count is the count the server reports". Neither is
    // true if another file is posting receipts at the same moment, so the suite
    // runs strictly in file order rather than fanning out across workers. The
    // specs are fast; a shared mutable server is not something to race.
    fullyParallel: false,
    forbidOnly: Boolean(process.env.CI),
    retries: process.env.CI ? 1 : 0,
    workers: 1,
    reporter: process.env.CI ? 'github' : 'list',
    use: {
        baseURL: E2E_BASE_URL,
        trace: 'retain-on-failure',
    },
    projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
    webServer: {
        command: [
            `uv run python ${fixtureBuilder} ${fixtureProject}`,
            `uv run d2w fhir serve ${fixtureProject} --ui --host 127.0.0.1 --port ${String(E2E_PORT)}`,
        ].join(' && '),
        cwd: repositoryRoot,
        // `/metadata` rather than `/`: it is the one path that proves the FHIR
        // routes are up, and a shell served before the store finished loading
        // would make every spec race the lifespan.
        url: `${E2E_BASE_URL}/metadata`,
        reuseExistingServer: !process.env.CI,
        stdout: 'pipe',
        stderr: 'pipe',
        timeout: 120_000,
    },
})
