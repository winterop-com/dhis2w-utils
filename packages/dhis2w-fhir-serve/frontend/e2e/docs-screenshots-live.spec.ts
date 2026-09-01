import { spawn, type ChildProcess } from 'node:child_process'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { expect, test, type Locator } from '@playwright/test'

import { VIEWPORT, shoot } from './docs-shots.ts'

/**
 * The screenshot producer for the pages a compiled guide cannot draw - NOT a test.
 *
 * SKIPPED BY DEFAULT, twice over: `DOCS_SCREENSHOTS=1` says a shoot is wanted at all, and
 * `D2W_SCREENSHOT_PROJECT` names the FHIR project to shoot against. `make screenshot` sets the
 * first and passes the second through; without a project this file shoots nothing and says so.
 *
 *     cd packages/dhis2w-fhir-serve/frontend
 *     pnpm build
 *     DOCS_SCREENSHOTS=1 D2W_SCREENSHOT_PROJECT=~/dev/ttt/play43 \
 *         pnpm exec playwright test e2e/docs-screenshots-live.spec.ts
 *
 * WHY IT EXISTS. `docs-screenshots.spec.ts` beside it shoots the compiled fixture server, which has
 * no DHIS2 instance behind it - so three surfaces of this app are invisible to it. Metadata health
 * grades an instance's metadata. A tracked entity's record is read out of an instance one subject
 * at a time. The record under the Responses table is that same read, beside the receipts. All three
 * need a live run, and a live run needs somebody's real project and profile.
 *
 * THESE IMAGES ARE ILLUSTRATIVE, NOT PINNED. The instance behind them moves - a demo database is
 * reseeded, a production one gains a subject every day - so the counts, the names, and the findings
 * in these shots are whatever was true on the day of the shoot. That is why nothing here asserts a
 * number and why the subject on screen is discovered rather than named: the shoot picks whatever
 * tracked entity the instance currently holds an answered event for. Frame over value, always.
 *
 * THE PROJECT'S OWN SPOOL IS NEVER TOUCHED. `[serve] spool_dir` is where a receipt lands, and it
 * resolves against the project root - so the server this file starts is pointed at a COPY of the
 * project's `fhir.toml` in a temporary directory, with `spool_dir` rewritten to an absolute path
 * under that same temporary directory. The named project is opened for reading, once, to copy one
 * file out of it. Nothing is written into it, and nothing on this page posts: every request the
 * shoot makes is a GET, so no capture is stored anywhere and none could be forwarded.
 *
 * ITS OWN SERVER, ON ITS OWN PORT. 8378, one past the suite's 8377 and nowhere near the 8095/8096 a
 * developer's own facades sit on. The process is started here rather than through the config's
 * `webServer`, because that one serves the compiled fixture the whole rest of the suite runs
 * against and there is exactly one of it.
 */

const here = path.dirname(fileURLToPath(import.meta.url))

/** The workspace root, from which `uv run` resolves the environment. */
const repositoryRoot = path.resolve(here, '../../../..')

/** Names the FHIR project to serve. Unset, this file shoots nothing. */
const PROJECT_ENVIRONMENT_VARIABLE = 'D2W_SCREENSHOT_PROJECT'

/** The port this file's own server binds. See the note above on why it is not 8377. */
const LIVE_PORT = 8378

const LIVE_BASE_URL = `http://127.0.0.1:${String(LIVE_PORT)}`

/** How long a live store may take to build before the shoot gives up and says so. */
const SERVER_READY_TIMEOUT_MILLISECONDS = 300_000

/** How long one shot may take. Every read on these pages goes to DHIS2 and back. */
const SHOT_TIMEOUT_MILLISECONDS = 180_000

/** How many records of one register the subject search reads before moving to the next register. */
const SCAN_PAGE_SIZE = 25

/** How many records the whole search may read, so an instance holding a million ends rather than grinds. */
const SCAN_BUDGET = 60

/** The identifier system a register puts the DHIS2 tracked entity uid itself under, which names nobody. */
const TRACKED_ENTITY_ID_SYSTEM_SUFFIX = '/id/tracked-entity'

const projectDirectory = process.env[PROJECT_ENVIRONMENT_VARIABLE] ?? ''

/** What the shoot found to shoot: one subject this instance holds an answered event for. */
interface LiveSubject {
    /** The FHIR resource the register serves this subject as, which is the first segment of its route. */
    resource: string
    trackedEntityUid: string
    /** A value that names them - what goes in the search box under the receipts. */
    identifierValue: string
    /** One event of theirs carrying answers, which is the row the shots unfold. */
    eventUid: string
}

/** The shape `/facade/uiconfig` answers with, in the one part this file reads. */
interface UiConfigShape {
    tracked_entities?: { registers?: { resource: string; types?: { uid: string; name: string }[] }[] }
}

/** A FHIR searchset, in the one part this file reads. */
interface BundleShape {
    total?: number
    entry?: { resource: { id: string; identifier?: { system?: string; value?: string }[]; item?: unknown[] } }[]
}

let serverProcess: ChildProcess | null = null
let temporaryProject = ''
let serverOutput = ''
let subject: LiveSubject | null = null

/**
 * Copy the project's `fhir.toml` into a directory of this shoot's own, with the spool moved into it.
 *
 * The rewrite is the safety property, so it is done by removing every `spool_dir` the file states
 * and writing exactly one back: a table that already named a directory - an absolute one, above
 * all - must not survive into the copy. The default would already land inside the copy, since a
 * relative `spool_dir` resolves against the project root and the root is now this directory; the
 * key is written anyway, because a safety property nobody can read in the file is not one.
 */
function stageTemporaryProject(): string {
    const configPath = path.join(projectDirectory, 'fhir.toml')
    if (!fs.existsSync(configPath)) {
        throw new Error(
            `${PROJECT_ENVIRONMENT_VARIABLE} is ${projectDirectory}, which holds no fhir.toml. ` +
                'Name a scaffolded FHIR project directory - the one you serve.',
        )
    }
    const staged = fs.mkdtempSync(path.join(os.tmpdir(), 'd2w-docs-shoot-'))
    const spool = path.join(staged, 'spool')
    const stated = fs
        .readFileSync(configPath, 'utf8')
        .split('\n')
        .filter((line) => !/^\s*spool_dir\s*=/.test(line))
    const serveTable = stated.findIndex((line) => /^\s*\[serve]\s*$/.test(line))
    const spoolKey = `spool_dir = ${JSON.stringify(spool)}`
    if (serveTable === -1) stated.push('', '[serve]', spoolKey)
    else stated.splice(serveTable + 1, 0, spoolKey)
    const written = `${stated.join('\n')}\n`
    fs.writeFileSync(path.join(staged, 'fhir.toml'), written)
    // The whole point of the copy, checked rather than assumed: one spool, under this directory.
    const spoolKeys = written.split('\n').filter((line) => /^\s*spool_dir\s*=/.test(line))
    expect(spoolKeys, written).toEqual([spoolKey])
    return staged
}

/** Start the facade over the staged project, and wait until it answers the one path that proves it is up. */
async function startLiveServer(staged: string): Promise<void> {
    const child = spawn(
        'uv',
        [
            'run',
            'd2w',
            'fhir',
            'serve',
            staged,
            '--live',
            '--ui',
            '--host',
            '127.0.0.1',
            '--port',
            String(LIVE_PORT),
        ],
        { cwd: repositoryRoot, detached: true, stdio: ['ignore', 'pipe', 'pipe'] },
    )
    serverProcess = child
    // Kept so a server that refuses to start can say why, in its own words, rather than as a timeout.
    child.stdout?.on('data', (chunk: Buffer) => (serverOutput += chunk.toString()))
    child.stderr?.on('data', (chunk: Buffer) => (serverOutput += chunk.toString()))

    const deadline = Date.now() + SERVER_READY_TIMEOUT_MILLISECONDS
    while (Date.now() < deadline) {
        if (child.exitCode !== null) {
            throw new Error(`d2w fhir serve exited with ${String(child.exitCode)} before it answered:\n${serverOutput}`)
        }
        try {
            const probe = await fetch(`${LIVE_BASE_URL}/metadata`)
            if (probe.ok) return
        } catch {
            // Not up yet. A live store reads the whole selection out of DHIS2 before it binds.
        }
        await new Promise((resolve) => setTimeout(resolve, 1000))
    }
    throw new Error(
        `d2w fhir serve did not answer ${LIVE_BASE_URL}/metadata within ` +
            `${String(SERVER_READY_TIMEOUT_MILLISECONDS / 1000)}s:\n${serverOutput}`,
    )
}

/** Read JSON off the live server, as the browser would. */
async function readJson<T>(pathAndQuery: string): Promise<T> {
    const response = await fetch(`${LIVE_BASE_URL}${pathAndQuery}`)
    if (!response.ok) throw new Error(`GET ${pathAndQuery} answered ${String(response.status)}`)
    return (await response.json()) as T
}

/**
 * Find one subject to shoot: an identifier somebody can be searched by, and an event carrying answers.
 *
 * DISCOVERED RATHER THAN NAMED, because a uid written into this file is a uid that is right until
 * the instance behind it is reseeded. The registers are tried smallest first - a register of tens is
 * one somebody curated, and one of tens of thousands is generated - which is what keeps the search
 * bounded on an instance holding a lot of subjects and few records.
 */
async function findLiveSubject(): Promise<LiveSubject> {
    const config = await readJson<UiConfigShape>('/facade/uiconfig')
    const registers = config.tracked_entities?.registers ?? []
    const shelves: { resource: string; typeUid: string; total: number }[] = []
    for (const register of registers) {
        for (const type of register.types ?? []) {
            const page = await readJson<BundleShape>(
                `/${register.resource}?_count=1&_tag=${encodeURIComponent(type.uid)}`,
            )
            shelves.push({ resource: register.resource, typeUid: type.uid, total: page.total ?? 0 })
        }
    }
    shelves.sort((left, right) => left.total - right.total)

    let read = 0
    for (const shelf of shelves) {
        if (read >= SCAN_BUDGET) break
        const page = await readJson<BundleShape>(
            `/${shelf.resource}?_count=${String(SCAN_PAGE_SIZE)}&_tag=${encodeURIComponent(shelf.typeUid)}`,
        )
        for (const entry of page.entry ?? []) {
            if (read >= SCAN_BUDGET) break
            read += 1
            const named = (entry.resource.identifier ?? []).find(
                (identifier) =>
                    identifier.value !== undefined &&
                    !(identifier.system ?? '').endsWith(TRACKED_ENTITY_ID_SYSTEM_SUFFIX),
            )
            if (named?.value === undefined) continue
            const events = await readJson<BundleShape>(
                `/facade/tracked-entities/${entry.resource.id}/events?_count=10`,
            )
            const answered = (events.entry ?? []).find((event) => (event.resource.item ?? []).length > 0)
            if (answered === undefined) continue
            return {
                resource: shelf.resource,
                trackedEntityUid: entry.resource.id,
                identifierValue: named.value,
                eventUid: answered.resource.id,
            }
        }
    }
    throw new Error(
        `${LIVE_BASE_URL} served no tracked entity that holds both an identifier value and an event ` +
            `carrying answers, in the first ${String(SCAN_BUDGET)} records of its registers. The record ` +
            'shots need one; serve a project whose instance has tracker data.',
    )
}

/** Open one closed `Unfoldable` and wait for what is inside it, rather than racing the render. */
async function unfold(toggle: Locator): Promise<void> {
    await expect(toggle).toHaveAttribute('aria-expanded', 'false')
    await toggle.click()
    await expect(toggle).toHaveAttribute('aria-expanded', 'true')
}

/** The subject the shoot found, past the discovery - so no shot reads a null. */
function found(): LiveSubject {
    if (subject === null) throw new Error('no live subject was discovered')
    return subject
}

test.describe('live docs screenshots', () => {
    test.skip(
        process.env.DOCS_SCREENSHOTS !== '1' || projectDirectory === '',
        'screenshot producer, not a test - run it through `make screenshot` with D2W_SCREENSHOT_PROJECT set',
    )

    test.use({ viewport: VIEWPORT, baseURL: LIVE_BASE_URL })

    test.beforeAll(async () => {
        test.setTimeout(SERVER_READY_TIMEOUT_MILLISECONDS + 120_000)
        temporaryProject = stageTemporaryProject()
        await startLiveServer(temporaryProject)
        subject = await findLiveSubject()
    })

    test.afterAll(() => {
        if (serverProcess?.pid !== undefined) {
            // The whole group: `uv run` is a parent of the python process that holds the port.
            try {
                process.kill(-serverProcess.pid, 'SIGTERM')
            } catch {
                // Already gone, which is the outcome this asks for.
            }
        }
        if (temporaryProject !== '') fs.rmSync(temporaryProject, { recursive: true, force: true })
    })

    test.beforeEach(() => {
        test.setTimeout(SHOT_TIMEOUT_MILLISECONDS)
    })

    // TWO SHOTS, ONE VISIT. Grading an instance's whole metadata is the slowest read this app makes,
    // and the second image is the first one with a shelf opened - so opening a second page to take
    // it would pay for that read twice to show the same report.
    test('Metadata health, as it opens and with one severity opened onto its findings', async ({ page }) => {
        await page.goto('/#/metadata-health')

        await expect(page.getByRole('heading', { name: 'Metadata health', level: 2 })).toBeVisible()
        // The summary is drawn once the instance has been read and graded, which is the page's one
        // slow read - so this is the wait, and everything under it is already on screen.
        await expect(page.getByTestId('metadata-health-summary')).toBeVisible({ timeout: 120_000 })

        await shoot(page, 'live-metadata-health')

        // Whichever severity this instance actually earns. An instance with no errors draws no
        // Errors shelf at all, so this opens the first shelf on the page rather than a named one.
        const shelf = page.locator('[data-testid$="-section"]').first()
        await expect(shelf).toBeVisible()
        const shelfControls = shelf.getByRole('button')
        await unfold(shelfControls.first())
        // The severity's own control is the first; the DHIS2 collections it holds follow it, and the
        // findings table lives inside one of those. Indexed rather than matched on `aria-expanded`,
        // which the click being waited for is itself changing.
        await unfold(shelfControls.nth(1))
        await expect(shelf.getByRole('table').first()).toBeVisible()
        await shelf.scrollIntoViewIfNeeded()

        await shoot(page, 'live-metadata-health-findings')
    })

    test('the register, listing the subjects this DHIS2 instance holds', async ({ page }) => {
        await page.goto('/#/tracked-entities')

        await expect(page.getByTestId('patient-listing')).toBeVisible({ timeout: 120_000 })

        await shoot(page, 'live-register')
    })

    test("one subject's record, with an event opened onto the answers the instance holds", async ({ page }) => {
        const live = found()
        await page.goto(`/#/tracked-entities/${live.resource}/${live.trackedEntityUid}`)

        const events = page.getByTestId('tracked-entity-events')
        await expect(events).toBeVisible({ timeout: 120_000 })
        const event = page.getByTestId(`tracked-entity-event-${live.eventUid}`)
        await expect(event).toBeVisible()
        await unfold(event.getByRole('button').first())
        // The bar under the page counts the record separately from the list that draws it, so a shot
        // taken the moment the rows appear states nought events beneath a screenful of them.
        await expect(page.getByTestId('status-bar-summary')).toContainText(/[1-9]\d* events?/)
        // Framed on the list rather than on the opened row: what the shot is about is that a record's
        // events sit closed until one is opened, and a frame starting inside the answers shows the
        // answers of nothing in particular.
        await events.evaluate((element) => {
            ;(element.parentElement ?? element).scrollIntoView({ block: 'start' })
        })

        await shoot(page, 'live-register-person-event')
    })

    test('the Responses page: no receipt stored, and the instance read underneath it', async ({ page }) => {
        const live = found()
        await page.goto('/#/responses')

        await expect(page.getByRole('heading', { name: 'Responses', level: 2 })).toBeVisible()
        const record = page.getByTestId('responses-tracked-entity-record')
        await expect(record).toBeVisible({ timeout: 120_000 })

        // The box is found by its role rather than its label: a project keeping a synced copy labels
        // it "Any value a record holds" and one asking DHIS2 directly labels it "Identifier value",
        // and this shoot works either way.
        await record.getByRole('searchbox').fill(live.identifierValue)
        const results = record.getByTestId('patient-search-results')
        await expect(results).toBeVisible({ timeout: 60_000 })
        await results.getByRole('button').first().click()

        const event = record.getByTestId(`tracked-entity-event-${live.eventUid}`)
        await expect(event).toBeVisible({ timeout: 60_000 })
        await unfold(event.getByRole('button').first())

        await shoot(page, 'live-responses-record')
    })
})
