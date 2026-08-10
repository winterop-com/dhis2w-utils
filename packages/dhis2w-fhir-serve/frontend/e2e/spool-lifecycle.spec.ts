import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { expect, request as playwrightRequest, test } from '@playwright/test'

import { E2E_BASE_URL } from '../playwright.config.ts'

/**
 * The forwarded and rejected halves of the lifecycle, driven the way `d2w fhir forward` drives them.
 *
 * No DHIS2 stands behind the fixture server, so nothing in this suite can *earn* a forwarded or
 * rejected receipt - and every other spec therefore only ever sees `received`. But the spool is a
 * directory the forwarder mutates from another process entirely: a forward is a rename into
 * `forwarded/`, a refusal is a rename into `rejected/` plus a `<id>.report.json` beside it, and the
 * server re-reads the tree on every call. So this file does exactly what the forwarder does - posts
 * two real receipts, then renames their files - and asserts the UI over the states no other path
 * reaches: the rejected tile's cause line, the filtered landing, and the import-report rollup on
 * the receipt itself.
 *
 * The seeded files are removed afterwards, so the specs after this one meet the same spool they
 * would have without it.
 */

const AGGREGATE_FORM = 'BfMAe6Itzgt'
const FHIR_JSON = 'application/fhir+json'

const here = path.dirname(fileURLToPath(import.meta.url))

/** The spool of the fixture project the suite's server runs over. */
const spoolDirectory = path.join(here, '.fixture-project', '.serve', 'responses')

/** The DHIS2 error code the seeded report states, with a message quoting instance uids. */
const SEEDED_CODE = 'E1029'
const SEEDED_UID = 'aWpTgkKeXz1'
const SEEDED_MESSAGE =
    `Event \`${SEEDED_UID}\` cannot be reported for organisation unit \`O6uvpzGd5pu\`, ` +
    'which is outside the program\'s assigned units.'

let forwardedId = ''
let rejectedId = ''

/** Post one generated response and answer with the receipt id the server minted for it. */
async function post(seed: number): Promise<string> {
    const api = await playwrightRequest.newContext({ baseURL: E2E_BASE_URL })
    try {
        const generated = await api.get(`/Questionnaire/${AGGREGATE_FORM}/$generate?seed=${String(seed)}`, {
            headers: { Accept: FHIR_JSON },
        })
        expect(generated.status(), await generated.text()).toBe(200)
        const posted = await api.post('/QuestionnaireResponse', {
            headers: { 'Content-Type': FHIR_JSON, Accept: FHIR_JSON },
            data: await generated.json(),
        })
        expect(posted.status(), await posted.text()).toBe(201)
        return (posted.headers()['location'] ?? '').split('/').pop() ?? ''
    } finally {
        await api.dispose()
    }
}

/** Rename one received receipt into another lifecycle directory, which is all a forward run does. */
function move(responseId: string, lifecycle: 'forwarded' | 'rejected'): void {
    const destination = path.join(spoolDirectory, lifecycle)
    fs.mkdirSync(destination, { recursive: true })
    fs.renameSync(
        path.join(spoolDirectory, 'received', `${responseId}.json`),
        path.join(destination, `${responseId}.json`),
    )
}

test.beforeAll(async () => {
    forwardedId = await post(501)
    rejectedId = await post(502)
    move(forwardedId, 'forwarded')
    move(rejectedId, 'rejected')
    // The import report the forwarder writes beside a refusal, in `ForwardImportOutcome`'s shape.
    fs.writeFileSync(
        path.join(spoolDirectory, 'rejected', `${rejectedId}.report.json`),
        JSON.stringify({
            status: 'ERROR',
            created: 0,
            updated: 0,
            ignored: 1,
            issues: [{ error_code: SEEDED_CODE, subject: SEEDED_UID, message: SEEDED_MESSAGE }],
        }),
    )
})

test.afterAll(() => {
    // Leave the spool as the other specs expect it: nothing forwarded, nothing rejected.
    fs.rmSync(path.join(spoolDirectory, 'forwarded', `${forwardedId}.json`), { force: true })
    fs.rmSync(path.join(spoolDirectory, 'rejected', `${rejectedId}.json`), { force: true })
    fs.rmSync(path.join(spoolDirectory, 'rejected', `${rejectedId}.report.json`), { force: true })
})

test('the rejected tile names the top cause with its instances generalised away', async ({ page }) => {
    await page.goto('/')

    await expect(page.getByTestId('spool-rejected-count')).toHaveText('1')
    await expect(page.getByTestId('spool-forwarded-count')).toHaveText('1')

    const rejectedTile = page.getByRole('link', { name: /^Rejected/ })
    // The cause line is the code plus the message - but the message DHIS2 wrote is about one
    // event, and a tile summarising a cause must not read as that single event's story. The
    // backtick-quoted uids become ellipses.
    await expect(rejectedTile).toContainText(SEEDED_CODE)
    await expect(rejectedTile).toContainText('Event ... cannot be reported')
    await expect(rejectedTile).not.toContainText(SEEDED_UID)

    await expect(page.getByRole('link', { name: /^Forwarded/ })).toContainText('accepted by DHIS2')
})

test('the rejected tile lands on the responses already filtered to rejections', async ({ page }) => {
    await page.goto('/')

    await page.getByRole('link', { name: /^Rejected/ }).click()

    await expect(page).toHaveURL(/#\/responses\?lifecycle=rejected$/)
    await expect(page.getByRole('button', { name: /^Rejected/ })).toHaveAttribute('aria-pressed', 'true')
    const row = page.getByRole('row').filter({ hasText: rejectedId })
    await expect(row).toHaveCount(1)
    await expect(row).toContainText('Rejected')
    // The received receipts the earlier specs posted are filtered out, not merely outnumbered:
    // the one rejected receipt is the only body row the table holds.
    await expect(page.getByRole('row').filter({ hasText: 'Child Health' })).toHaveCount(1)
})

test('a rejected receipt shows its badge and the import report rollup', async ({ page }) => {
    await page.goto(`/#/responses/${rejectedId}`)

    await expect(page.getByText('Rejected', { exact: true }).first()).toBeVisible()
    await expect(page.getByRole('heading', { name: 'DHIS2 refused this import' })).toBeVisible()

    // The rollup matches the seeded report: the status, the counts, and the one issue row with
    // the rule, the object, and what DHIS2 said - verbatim here, because this is the detail.
    await expect(page.getByText('ERROR', { exact: true })).toBeVisible()
    const issue = page.getByRole('row').filter({ hasText: SEEDED_CODE })
    await expect(issue).toHaveCount(1)
    await expect(issue).toContainText(SEEDED_UID)
    await expect(issue).toContainText('outside the program')
})

test('a forwarded receipt still reads back, badged as accepted', async ({ page }) => {
    await page.goto(`/#/responses/${forwardedId}`)

    await expect(page.getByText('Forwarded', { exact: true }).first()).toBeVisible()
    // No refusal section: DHIS2 took this one, so there is nothing to explain.
    await expect(page.getByRole('heading', { name: 'DHIS2 refused this import' })).toHaveCount(0)
    await expect(page.getByRole('heading', { name: 'Answers' })).toBeVisible()
})
